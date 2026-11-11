"""Round-trip tests for the edat v3 writer in modkit.core.edat.

* repack: each stock v3 pack below is read and rewritten; the output must be byte-identical to the
  source and every per-file CRC32 must verify.
* pack: one stock pack is extracted and packed back from the directory; the output must again be
  byte-identical.
* synthetic: edge cases absent from stock packs (zero-size file, a path that is a prefix of another,
  input order) must parse back with matching payloads.

The game install is only read; outputs go to a temporary directory. Stock-pack tests skip when the
game folder is not configured (see the warno-setup skill).
"""
from __future__ import annotations

import os
import tempfile
import unittest

from modkit.core import edat, paths

# (pack relative to Data/PC, note)
PACKS = [
    ("201602/Scenarios/challenge_Survivors_Definition.dat", "10 entries, nested trie"),
    ("197351/201602/Scenarios/challenge_Survivors_Details.dat", "2 entries"),
    ("197351/201602/Scenarios/challenge_Survivors_Assets.dat", "26 entries, 5 MB"),
    ("197351/201602/DataCommon.dat", "13 entries, mid-name splits"),
    ("197351/201602/OutgameWithShowRoom.dat", "empty stub"),
    ("201602/Glad.dat", "356 entries"),
    ("201602/DecorsSets/Fulda_Definition.dat", "1250 entries"),
    ("197351/201602/Data.dat", "87 entries, 68 MB"),
]
PACK_FROM_DIR = "201602/Scenarios/challenge_Survivors_Definition.dat"


def first_difference(a: str, b: str, chunk: int = 1 << 20) -> int | None:
    """Offset of the first differing byte (or the shorter length), None if equal."""
    with open(a, "rb") as fa, open(b, "rb") as fb:
        pos = 0
        while True:
            x, y = fa.read(chunk), fb.read(chunk)
            if x != y:
                n = min(len(x), len(y))
                return pos + next((i for i in range(n) if x[i] != y[i]), n)
            if not x:
                return None
            pos += len(x)


def checksums_ok(dat: str) -> bool:
    return all(edat.verify_entry(dat, e) for e in edat.read_index(dat))


class EdatRoundTrip(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="edat_rt_")
        self.addCleanup(tmp.cleanup)
        self.outdir = tmp.name

    def assert_identical(self, src: str, out: str):
        diff = first_difference(src, out)
        self.assertIsNone(diff, f"differs at byte {diff}")
        self.assertTrue(checksums_ok(out), "per-file CRC32 failed")

    def test_synthetic(self):
        files = [
            ("b/zero.bin", b""),
            ("a/x.ndf", b"payload " * 5000),
            ("a/x.ndf2", b"prefix sibling"),
            ("a/x", b"x"),
            ("A/upper.txt", bytes(range(256)) * 40),
        ]
        out = os.path.join(self.outdir, "synthetic.dat")
        edat.write_edat(out, files)
        entries = edat.read_index(out)
        got = {e.path: edat.read_entry(out, e) for e in entries}
        order = [e.path for e in entries]
        self.assertEqual(got, dict(files))
        self.assertEqual(order, sorted(order, key=lambda p: p.encode()))
        self.assertTrue(checksums_ok(out))
        self.assertTrue(all(e.offset % edat.SECTOR == 0 for e in entries))
        self.assertEqual(os.path.getsize(out) % edat.SECTOR, 0)

    @paths.skip_unless_game_dir("Data", "PC")
    def test_repack(self):
        data_pc = paths.game_dir() / "Data" / "PC"
        for rel, note in PACKS:
            with self.subTest(pack=rel, note=note):
                src = os.path.join(data_pc, *rel.split("/"))
                if not os.path.exists(src):
                    self.skipTest(f"{rel} not in this install")
                out = os.path.join(self.outdir, "repack", rel.replace("/", "__"))
                os.makedirs(os.path.dirname(out), exist_ok=True)
                edat.repack(src, out)
                self.assert_identical(src, out)

    @paths.skip_unless_game_dir("Data", "PC")
    def test_pack_dir(self):
        src = os.path.join(paths.game_dir() / "Data" / "PC", *PACK_FROM_DIR.split("/"))
        if not os.path.exists(src):
            self.skipTest(f"{PACK_FROM_DIR} not in this install")
        tree = os.path.join(self.outdir, "tree")
        edat.extract(src, tree)
        out = os.path.join(self.outdir, "packed_from_dir.dat")
        edat.pack(tree, out)
        self.assert_identical(src, out)


if __name__ == "__main__":
    unittest.main()
