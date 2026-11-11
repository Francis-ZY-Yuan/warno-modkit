"""Tests for modkit.core.ndfbin's file reader: `decode` (bytes) and `load` (a path), on a small file built here.

Run as `python -m unittest discover -s components/core/tests -t components/core/tests`. Needs no stock data.
"""
from __future__ import annotations

import os
import tempfile
import unittest

from modkit.core import ndfbin
from modkit.core.ndfbin import NdfBin, Obj, Value

SECTIONS = ["OBJE", "TOPO", "CHNK", "CLAS", "PROP", "STRG", "TRAN", "IMPR", "EXPR"]


def small() -> NdfBin:
    """One exported object of one class, with an int and a string property."""
    nb = NdfBin(sections=list(SECTIONS), section_layout=list(SECTIONS))
    cls = nb.intern_class("TThing")
    nb.objects.append(Obj(cls, [(nb.intern_prop("Count", cls), Value(0x02, 7)),
                                (nb.intern_prop("Label", cls), Value(0x07, nb.intern_string("seven")))]))
    nb.topo = [0]
    nb.chnk = [(0, 1)]
    nb.exports = ndfbin.Node(nb.intern_tran("Thing"), 0)
    return nb


class Decode(unittest.TestCase):
    def test_every_compression_mode(self):
        """decode reads a file of each compression mode back to the image encode_image wrote."""
        nb = small()
        want = ndfbin.encode_image(nb)
        for mode in (ndfbin.MODE_NONE, ndfbin.MODE_LZ4, ndfbin.MODE_ZSTD, ndfbin.MODE_ZLIB):
            with self.subTest(mode=mode):
                back, hdr, image = ndfbin.decode(ndfbin.encode_file(nb, mode))
                self.assertEqual(hdr["mode"], mode)
                self.assertEqual(image[nb.header_size:], want[nb.header_size:])
                self.assertEqual((back.cname(back.objects[0].cls), back.strings, back.objects[0].props),
                                 ("TThing", [b"seven"], nb.objects[0].props))
                self.assertEqual(ndfbin.tree_paths(back, back.exports), [("Thing", 0)])

    def test_load_is_decode_of_the_file(self):
        raw = ndfbin.encode_file(small(), ndfbin.MODE_ZSTD)
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "thing.ndfbin")
            with open(path, "wb") as fh:
                fh.write(raw)
            self.assertEqual(ndfbin.load(path), ndfbin.decode(raw))

    def test_refuses_other_bytes(self):
        with self.assertRaisesRegex(ValueError, "not an EUG0/CNDF file"):
            ndfbin.decode(b"RIFF" + bytes(60))


if __name__ == "__main__":
    unittest.main()
