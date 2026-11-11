"""Tests for modkit.core.tgv: a small TGV v3 texture built here, decoded to PNG by the CLI."""
import contextlib
import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path

from modkit.core import tgv

try:
    from compression import zstd
except ImportError:  # pragma: no cover - depends on interpreter version
    zstd = None

PIXELS = bytes([255, 0, 0, 255, 0, 255, 0, 128])  # 2x1 RGBA: opaque red, half-transparent green


def small_tgv(width: int = 2, height: int = 1, pixels: bytes = PIXELS) -> bytes:
    """A TGV v3 file as tgv's docstring lays it out: one A8B8G8R8_LIN mip, its payload a zstd frame at 0x40."""
    fmt = b"A8B8G8R8_LIN"
    head = struct.pack("<IIIIIIHH", 3, 2, width, height, width, height, 1, len(fmt)) + fmt + bytes(16)
    frame = zstd.compress(pixels)
    body = head + struct.pack("<II", 0x40, 8 + len(frame))
    body += bytes(0x40 - len(body)) + b"ZSTD" + struct.pack("<I", len(pixels)) + frame
    return body + bytes(-len(body) % 4)


def png_pixels(data: bytes) -> tuple[int, int, int, bytes]:
    """(width, height, channels, pixels) of a PNG write_png wrote (one IDAT, filter 0 on every row)."""
    w, h, _, color = struct.unpack(">IIBB", data[16:26])
    channels = {2: 3, 6: 4}[color]
    length = struct.unpack(">I", data[33:37])[0]
    raw = zlib.decompress(data[41:41 + length])
    stride = w * channels + 1
    return w, h, channels, b"".join(raw[y * stride + 1:(y + 1) * stride] for y in range(h))


@unittest.skipIf(zstd is None, "needs Python 3.14+ (compression.zstd)")
class TopngTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.src = self.root / "MapTexture.tgv"
        self.src.write_bytes(small_tgv())

    def topng(self, *args: str) -> int:
        with contextlib.redirect_stderr(io.StringIO()):
            return tgv.main(["topng", str(self.src), *args])

    def test_decodes_to_png(self):
        out = self.root / "x.png"
        self.assertEqual(self.topng(str(out)), 0)
        self.assertEqual(png_pixels(out.read_bytes()), (2, 1, 4, PIXELS))
        self.assertEqual(self.topng(str(out), "--opaque"), 0)
        self.assertEqual(png_pixels(out.read_bytes()), (2, 1, 3, bytes([255, 0, 0, 0, 255, 0])))

    def test_makes_the_output_folders(self):
        """A fresh extraction has no maps/preview_full/ yet: topng makes the folders it writes into."""
        out = self.root / "extracted" / "maps" / "preview_full" / "map.png"
        self.assertEqual(self.topng(str(out)), 0)
        self.assertTrue(out.read_bytes().startswith(b"\x89PNG\r\n\x1a\n"))


if __name__ == "__main__":
    unittest.main()
