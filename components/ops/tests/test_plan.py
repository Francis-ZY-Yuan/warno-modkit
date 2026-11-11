"""Tests for the build plan of a cloned scenario in modkit.ops.items: plan_definition, plan_details, plan_assets."""
import os
import tempfile
import unittest

from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.graph import Node, Str, build_graph, decode, encode
from modkit.ops.items import AssetRule, asset_rule, payload, plan_assets, plan_definition, plan_details
from modkit.ops.rekey import Rekey, def_path, tag_name_hashes

SOURCE, NEW = "challenge_A", "challenge_B"
G_OLD, G_NEW = bytes(range(16)), bytes(range(16, 32))


def table(kinds=("GDScript", "ScenarioInfo")) -> Rekey:
    return Rekey(SOURCE, NEW, G_OLD, G_NEW, {}, "ta_", (), {}, {}, {}, kinds, ("Scenario.ndf",), ())


def write(root: str, inner: str, raw: bytes) -> None:
    path = os.path.join(root, *inner.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def ndfbin_file(kind: str) -> bytes:
    props = [("Name", Str(SOURCE))] + ([("GUID", Value(0x1A, G_OLD))] if kind == "ScenarioInfo" else [])
    return encode(build_graph([Node("TInfo", props)], []), kind)


def tag_file(kind: str) -> bytes:
    hashes = tag_name_hashes(SOURCE, ("Scenario.ndf",)).values()
    pairs = [Value(0x22, (Value(0x25, h), Value(0x25, bytes(16)))) for h in hashes]
    return encode(build_graph([Node("TTagFile", [("BaseName", Str(f"Scenarios/{kind}/{SOURCE}")),
                                                 ("Hashes", pairs)])], []), f"{kind}.tag")


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()


class PlanDefinitionTest(TempDirTest):
    def setUp(self):
        super().setUp()
        for kind in ("GDScript", "ScenarioInfo"):
            write(self.root, def_path(kind, "ndfbin", SOURCE), ndfbin_file(kind))
            write(self.root, def_path(kind, "tag", SOURCE), tag_file(kind))

    def test_rekeys_every_kind_or_ships_the_generated_one(self):
        gd = b"generated script"
        items = plan_definition(table(), self.root, {"GDScript": (gd, "generated (test)", "GDScript.txt")})
        self.assertEqual([(it.path, it.action) for it in items],
                         [(def_path("GDScript", "ndfbin", NEW), "generate"), (def_path("GDScript", "tag", NEW), "tag"),
                          (def_path("ScenarioInfo", "ndfbin", NEW), "rekey"),
                          (def_path("ScenarioInfo", "tag", NEW), "tag")])
        self.assertEqual((payload(items[0]), items[0].source, items[0].fixture, items[0].stock),
                         (gd, "generated (test)", "GDScript.txt", None))
        info = items[2]
        self.assertEqual(info.stock, ndfbin_file("ScenarioInfo"))
        self.assertTrue(info.source.endswith(def_path("ScenarioInfo", "ndfbin", SOURCE)), info.source)
        nb, _, _ = decode(payload(info))
        self.assertEqual(nb.strings, [NEW.encode()])

    def test_without_generated_kinds_every_file_is_rekeyed(self):
        items = plan_definition(table(), self.root, {})
        self.assertEqual([it.action for it in items], ["rekey", "tag", "rekey", "tag"])

    def test_missing_template_file(self):
        with self.assertRaises(OSError):
            plan_definition(table(("GDScript", "ScenarioLoader")), self.root, {})


class PlanDetailsTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.stock, self.other = os.path.join(self.root, "stock"), os.path.join(self.root, "other")
        for folder, files in ((self.stock, {"out/Z.ndfbin": b"zz", "out/C.ndfbin": b"ccc"}),
                              (self.other, {"Cam.ndfbin": b"m"})):
            for inner, raw in files.items():
                write(folder, inner, raw)
            with open(os.path.join(folder, "_provenance.tsv"), "w", encoding="utf-8", newline="") as fh:
                fh.write("".join(f"{inner}\tp.dat\t0\t{len(raw)}\n" for inner, raw in files.items()))

    def test_layout_in_order_generated_or_copied(self):
        layout = [("out/LD.ndfbin", None), ("out/Z.ndfbin", self.stock), ("out/C.ndfbin", self.stock),
                 ("Cam.ndfbin", self.other)]
        items = plan_details(layout, {"out/LD.ndfbin": (b"ld", "generated (items)", "LD.txt"),
                                     "out/C.ndfbin": (b"cz", "generated (zones)", "C.txt")})
        self.assertEqual([(it.path, it.action, payload(it)) for it in items],
                         [("out/LD.ndfbin", "generate", b"ld"), ("out/Z.ndfbin", "copy", b"zz"),
                          ("out/C.ndfbin", "generate", b"cz"), ("Cam.ndfbin", "copy", b"m")])
        self.assertEqual([it.fixture for it in items], ["LD.txt", None, "C.txt", None])

    def test_an_entry_without_a_folder_must_be_generated(self):
        with self.assertRaisesRegex(CheckError, "no stock folder"):
            plan_details([("out/LD.ndfbin", None)], {})


class PlanAssetsTest(TempDirTest):
    RULES = (AssetRule(f"PC/Texture/{SOURCE}/Menu/*.tgv", "copy", "menu pictures"),
             AssetRule("PC/*", "drop", "not referenced"),
             AssetRule(f"Localisation/{SOURCE}/*", "drop", "replaced"))

    def setUp(self):
        super().setUp()
        for inner in (f"PC/Texture/{SOURCE}/Menu/a.tgv", f"PC/Texture/{SOURCE}/Portrait/b.tgv",
                      f"Localisation/{SOURCE}/X-US.dic", "Map/ignored.bin"):
            write(self.root, inner, inner.encode())

    def test_dictionaries_then_rules(self):
        dics = [(f"Localisation/{NEW}/D-US.dic", b"dic", "strings")]
        items, dropped = plan_assets(dics, self.root, ("Localisation", "PC"), self.RULES, SOURCE, NEW)
        self.assertEqual([(it.path, it.action) for it in items],
                         [(f"Localisation/{NEW}/D-US.dic", "generate"), (f"PC/Texture/{NEW}/Menu/a.tgv", "copy")])
        self.assertEqual(payload(items[1]), f"PC/Texture/{SOURCE}/Menu/a.tgv".encode())
        self.assertEqual(dropped, [(f"Localisation/{SOURCE}/X-US.dic", "replaced"),
                                   (f"PC/Texture/{SOURCE}/Portrait/b.tgv", "not referenced")])

    def test_plain_tuples_and_the_first_rule_wins(self):
        rules = [("PC/*", "drop", "first"), ("PC/*", "copy", "second")]
        self.assertEqual(asset_rule("PC/x", rules), ("drop", "first"))
        self.assertEqual(asset_rule("PC/x", self.RULES), ("drop", "not referenced"))

    def test_every_file_needs_a_rule(self):
        with self.assertRaisesRegex(CheckError, "without a rule: Map/ignored.bin"):
            plan_assets([], self.root, ("Map",), self.RULES, SOURCE, NEW)


if __name__ == "__main__":
    unittest.main()
