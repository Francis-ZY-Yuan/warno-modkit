"""modkit.core.dbg: the .dbg source map's layout, written and read back, and held to every stock .dbg."""
from __future__ import annotations

import struct
import unittest

from modkit.core import dbg, ndfbin, paths

LINES = [dbg.Line("", "ScenariosData:/challenge_X/Scripting/Dialog.ndf", 3, 1),
         dbg.Line("RootDescriptor", "ScenariosData:/challenge_X/Scripting/EffetMap.ndf", 2, 23)]


class Layout(unittest.TestCase):
    def test_round_trip(self):
        raw = dbg.write(LINES)
        self.assertEqual(dbg.read(raw), LINES)
        (size,) = struct.unpack_from("<I", raw)
        text = dbg.read_text(raw)
        self.assertEqual(size, len(text))
        self.assertEqual(text, ";ScenariosData:/challenge_X/Scripting/Dialog.ndf;3;1\n"
                               "RootDescriptor;ScenariosData:/challenge_X/Scripting/EffetMap.ndf;2;23\n")
        self.assertEqual(raw[4:8], b"\x28\xb5\x2f\xfd")  # one zstd frame after the prefix

    def test_empty(self):
        self.assertEqual(dbg.read(dbg.write([])), [])

    def test_bad_data_is_named(self):
        raw = dbg.write(LINES)
        with self.assertRaisesRegex(dbg.DbgError, "size prefix 1"):
            dbg.read(struct.pack("<I", 1) + raw[4:])
        with self.assertRaisesRegex(dbg.DbgError, "3 fields, not 4"):
            dbg.read(dbg.write_text("a;b;1\n"))
        with self.assertRaisesRegex(dbg.DbgError, "newline"):
            dbg.read(dbg.write_text("a;b;1;1"))
        with self.assertRaisesRegex(dbg.DbgError, "integers"):
            dbg.read(dbg.write_text("a;b;x;1\n"))
        with self.assertRaisesRegex(dbg.DbgError, "';'"):
            dbg.write([dbg.Line("a;b", "s", 1, 1)])
        with self.assertRaisesRegex(dbg.DbgError, "too short"):
            dbg.read(b"\x00")


class Stock(unittest.TestCase):
    @paths.skip_unless_extracted("scenarios")
    def test_every_stock_dbg_is_one_line_per_object(self):
        """Every stock scenario's .dbg reads (prefix = text size, four fields a line) with one line per object of the
        .txn beside it, and its text written again reads back the same."""
        files = sorted((paths.extracted_root() / "scenarios").glob("*/NDF/Scenarios/*/*.dbg"))
        self.assertGreaterEqual(len(files), 100, "the extraction holds too few stock .dbg files")
        for f in files:
            with self.subTest(f.relative_to(paths.extracted_root()).as_posix()):
                raw = f.read_bytes()
                lines = dbg.read(raw)
                nb, _, _ = ndfbin.decode(f.with_suffix(".txn").read_bytes())
                self.assertEqual(len(lines), len(nb.objects))
                self.assertEqual(dbg.read(dbg.write(lines)), lines)
                exported = {i: p.rsplit("/", 1)[-1] for p, i in ndfbin.tree_paths(nb, nb.exports)}
                for i, name in exported.items():
                    self.assertEqual(lines[i].name, name)


if __name__ == "__main__":
    unittest.main()
