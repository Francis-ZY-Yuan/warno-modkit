"""Tests for modkit.ops.items and modkit.ops.packs: build plans, pack read-back, loose files, and the game-build check
of a built mod folder (python -m modkit.ops.packs check)."""
import contextlib
import hashlib
import io
import os
import tempfile
import unittest
from unittest import mock

from modkit.core import edat
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops import gates, packs
from modkit.ops.graph import Node, Str, build_graph, encode
from modkit.ops.items import Item, details_copy, mem_item, payload, read_provenance
from modkit.ops.packs import check_mod, verify_packs, write_loose, write_packs
from modkit.ops.rekey import DBG, TAG, TAG_CLASS, TXN, def_path, generated_dbg


def write_pack(path: str, items: list[Item]) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    edat.write_edat_stream(path, [(it.path, it.size, it.chunks) for it in items])


class ItemTest(unittest.TestCase):
    def test_mem_item(self):
        it = mem_item("Assets", "a/b.bin", b"abc", "generate", "test", fixture="b.txt")
        self.assertEqual((it.size, it.digest), (3, hashlib.sha256(b"abc").digest()))
        self.assertEqual(payload(it), b"abc")
        self.assertEqual(payload(it), b"abc")  # chunks() can be called again
        self.assertEqual((it.stock, it.fixture), (None, "b.txt"))


class DetailsCopyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.src = self.tmp.name
        os.makedirs(os.path.join(self.src, "out"))
        with open(os.path.join(self.src, "out", "A.ndfbin"), "wb") as fh:
            fh.write(b"12345")
        with open(os.path.join(self.src, "_provenance.tsv"), "w", encoding="utf-8", newline="") as fh:
            fh.write("out/A.ndfbin\tpack.dat\t0\t5\n\nout/B.ndfbin\tpack.dat\t5\t9\n")

    def tearDown(self):
        self.tmp.cleanup()

    def test_read_provenance(self):
        self.assertEqual(read_provenance(self.src), [("out/A.ndfbin", 5), ("out/B.ndfbin", 9)])

    def test_details_copy(self):
        sizes = dict(read_provenance(self.src))
        it = details_copy(self.src, "out/A.ndfbin", sizes)
        self.assertEqual((it.pack, it.path, it.action, payload(it)), ("Details", "out/A.ndfbin", "copy", b"12345"))
        self.assertTrue(it.source.endswith("/out/A.ndfbin"))

    def test_details_copy_checks_the_provenance(self):
        with self.assertRaisesRegex(CheckError, "not in"):
            details_copy(self.src, "out/A.ndfbin", {})
        with self.assertRaisesRegex(CheckError, "provenance says 6"):
            details_copy(self.src, "out/A.ndfbin", {"out/A.ndfbin": 6})


class PackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.mod = os.path.join(self.tmp.name, "MyOp")
        gd = encode(build_graph([Node("TRoot", [("Name", Str("x"))])], []), "gd")
        self.items = [mem_item("Definition", def_path("GDScript", TXN, "s"), gd, "generate", "test"),
                      mem_item("Definition", "NDF/a.txt", b"plain", "copy", "test"),
                      mem_item("Assets", "PC/b.bin", b"\x00" * 100, "copy", "test"),
                      mem_item("Loose", "Videos/c.webm", b"video", "copy", "test")]
        self.paths = {}
        for pack in ("Definition", "Assets"):
            self.paths[pack] = os.path.join(self.mod, "Scenarios", f"s_{pack}.dat")
            write_pack(self.paths[pack], [it for it in self.items if it.pack == pack])

    def tearDown(self):
        self.tmp.cleanup()

    def test_verify_packs(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            verify_packs(self.items, self.paths)
        self.assertIn("s_Definition.dat: 2 entries", out.getvalue())
        self.assertIn("1 CNDF round-trip", out.getvalue())

    def test_verify_packs_catches_a_changed_payload(self):
        changed = [mem_item("Assets", "PC/b.bin", b"\x01" * 100, "copy", "test") if it.path == "PC/b.bin" else it
                   for it in self.items]
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(CheckError, "differs from its planned"):
            verify_packs(changed, self.paths)

    def test_verify_packs_catches_a_missing_entry(self):
        extra = self.items + [mem_item("Assets", "PC/d.bin", b"d", "copy", "test")]
        with contextlib.redirect_stdout(io.StringIO()), self.assertRaisesRegex(CheckError, "entry list"):
            verify_packs(extra, self.paths)

    def test_write_packs(self):
        out = os.path.join(self.tmp.name, "Out")
        paths = write_packs(self.items, out, "s", ("Definition", "Details", "Assets"))
        self.assertEqual(paths, {pack: os.path.join(out, "Scenarios", f"s_{pack}.dat")
                                 for pack in ("Definition", "Assets")})
        self.assertEqual(list(paths), ["Definition", "Assets"])
        with contextlib.redirect_stdout(io.StringIO()):
            verify_packs(self.items, paths)
        self.assertEqual(sorted(e.path for e in edat.read_index(paths["Assets"])), ["PC/b.bin"])

    def test_write_loose(self):
        with contextlib.redirect_stdout(io.StringIO()):
            written = write_loose(self.items, self.mod)
        self.assertEqual(written, [os.path.join(self.mod, "Videos", "c.webm")])
        with open(written[0], "rb") as fh:
            self.assertEqual(fh.read(), b"video")


def definition(scenario: str, kinds=("MapConfiguration", "ScenarioInfo"), cls: str = "TRoot"
               ) -> list[tuple[str, bytes]]:
    """A Definition pack's entries in build 210942's layout: each kind's .txn (one `cls` object), its .txn.tag (one
    TNDFTagFile) and its .dbg (one line per object)."""
    tag = encode(build_graph([Node(TAG_CLASS, [("ConfigHash", Value(0x13, 7))])], []), "tag")
    out = []
    for kind in kinds:
        raw = encode(build_graph([Node(cls, [("Name", Str(scenario))])], []), kind)
        out += [(def_path(kind, TXN, scenario), raw), (def_path(kind, TAG, scenario), tag),
                (def_path(kind, DBG, scenario), generated_dbg(raw, scenario, f"ScenariosData:/{scenario}/S.ndf"))]
    return out


class CheckModTest(unittest.TestCase):
    """The game-build gates on a mod folder already built (check_mod, `python -m modkit.ops.packs check`): per
    scenario, the Definition in build 210942's layout, and every class and property in stock's or admitted."""

    STOCK = gates.StockClasses(frozenset({"TRoot", TAG_CLASS}),
                               frozenset({("TRoot", "Name"), (TAG_CLASS, "ConfigHash")}), 2)
    OLD = "TGDDescriptorLaunchEffetStandard"   # build 201602's script root, which 210942 does not have

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = tmp.name

    def mod(self, name: str, scenario: str, definition_entries: list[tuple[str, bytes]]) -> str:
        """A mod folder holding `scenario`'s Definition pack and a Details pack of one stock-shaped file."""
        root = os.path.join(self.tmp, name)
        os.makedirs(os.path.join(root, "Scenarios"))
        details = [("out/LevelDesign.ndfbin", encode(build_graph([Node("TRoot", [("Name", Str("d"))])], []), "LD"))]
        for pack, entries in (("Definition", definition_entries), ("Details", details)):
            edat.write_edat(os.path.join(root, "Scenarios", f"{scenario}_{pack}.dat"), entries)
        return root

    def old_build(self) -> str:
        """A mod built for build 201602: its MapConfiguration in NDF/Scenarios/MapConfiguration/, its script root
        class gone from 210942."""
        raw = encode(build_graph([Node(self.OLD, [("Name", Str("x"))])], []), "GDScript")
        return self.mod("Old", "challenge_O", [("NDF/Scenarios/MapConfiguration/challenge_O.ndfbin", raw)])

    def test_a_210942_build_passes(self):
        """4 CNDF files of 4 objects in Definition (the .dbg are not CNDF) and 1 in Details."""
        self.assertEqual(check_mod(self.mod("New", "challenge_A", definition("challenge_A")), self.STOCK),
                         ["challenge_A: 2 Definition kinds in this build's layout; every class and property of 5 "
                          "files (5 objects) is in the 2 stock files'"])

    def test_a_201602_build_fails_both_gates(self):
        with self.assertRaises(CheckError) as cm:
            check_mod(self.old_build(), self.STOCK)
        layout, classes = str(cm.exception).split("\n  ")
        self.assertRegex(layout, r"^challenge_O: definition-layout: Definition:NDF/Scenarios/MapConfiguration/"
                                 r"challenge_O\.ndfbin: not NDF/Scenarios/challenge_O/<Kind>\.txn")
        self.assertRegex(classes, rf"^challenge_O: stock-classes: 2 classes or properties no stock file of this game "
                                  rf"build holds: class {self.OLD} \(Definition:NDF/Scenarios/MapConfiguration/"
                                  rf"challenge_O\.ndfbin\); {self.OLD}\.Name ")

    def test_an_admitted_shape_passes(self):
        """A shape no stock file holds fails the classes gate alone (its layout is right), and passes once admitted
        (--admit CLASS.PROPERTY: a content's extra_shapes)."""
        entries = definition("challenge_A") + definition("challenge_A", ("GDScript",), cls=self.OLD)
        folder = self.mod("Admit", "challenge_A", entries)
        with self.assertRaises(CheckError) as cm:
            check_mod(folder, self.STOCK)
        self.assertRegex(str(cm.exception), rf"^challenge_A: stock-classes: 2 classes or properties no stock file of "
                                            rf"this game build holds: class {self.OLD} \(Definition:NDF/Scenarios/"
                                            rf"challenge_A/GDScript\.txn\); {self.OLD}\.Name ")
        self.assertNotIn("definition-layout", str(cm.exception))
        self.assertEqual(check_mod(folder, self.STOCK, [(self.OLD, "Name")]),
                         ["challenge_A: 3 Definition kinds in this build's layout; every class and property of 7 "
                          "files (7 objects) is in the 2 stock files' or among 1 admitted"])

    def test_a_folder_without_scenario_packs_fails(self):
        os.makedirs(os.path.join(self.tmp, "Empty"))
        with self.assertRaisesRegex(CheckError, r"Empty: no Scenarios/<scenario>_Definition\.dat or _Details\.dat"):
            check_mod(os.path.join(self.tmp, "Empty"), self.STOCK)

    def test_the_command_line(self):
        """One line per scenario of a passing mod on stdout; one FAILED line per failing mod on stderr, exit 1."""
        good, old = self.mod("New", "challenge_A", definition("challenge_A")), self.old_build()
        out, err = io.StringIO(), io.StringIO()
        with mock.patch.object(gates, "stock_classes", return_value=self.STOCK), contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            self.assertEqual(packs.main(["check", good]), 0)
            self.assertEqual(packs.main(["check", good, old]), 1)
            self.assertEqual(packs.main(["check", good, "--admit", "NoProperty"]), 1)
        self.assertEqual(out.getvalue().splitlines(), [f"{good}: challenge_A: 2 Definition kinds in this build's "
                                                       f"layout; every class and property of 5 files (5 objects) is "
                                                       f"in the 2 stock files'"] * 2)
        failed = [line for line in err.getvalue().splitlines() if line.startswith("FAILED: ")]
        self.assertEqual(len(failed), 2)
        self.assertTrue(failed[0].startswith(f"FAILED: {old}: challenge_O: definition-layout: "), failed[0])
        self.assertEqual(failed[1], "FAILED: --admit takes CLASS.PROPERTY")


if __name__ == "__main__":
    unittest.main()
