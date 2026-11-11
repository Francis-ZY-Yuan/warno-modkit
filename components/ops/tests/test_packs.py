"""Tests for modkit.ops.items and modkit.ops.packs: build plans, pack read-back and loose files."""
import contextlib
import hashlib
import io
import os
import tempfile
import unittest

from modkit.core import edat
from modkit.core.gates import CheckError
from modkit.ops.graph import Node, Str, build_graph, encode
from modkit.ops.items import Item, details_copy, mem_item, payload, read_provenance
from modkit.ops.packs import verify_packs, write_loose, write_packs


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
        self.items = [mem_item("Definition", "NDF/Scenarios/GDScript/s.ndfbin", gd, "generate", "test"),
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


if __name__ == "__main__":
    unittest.main()
