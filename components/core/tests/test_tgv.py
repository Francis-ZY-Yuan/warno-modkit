"""Tests for modkit.core.tgv: a small TGV v3 texture built here, decoded to PNG by the CLI; the writer, the PNG
reader and frompng; and the writer's byte-identical round trip of every stock menu picture."""
import contextlib
import io
import struct
import tempfile
import unittest
import zlib
from pathlib import Path
from unittest import mock

from modkit.core import paths, tgv

try:
    from compression import zstd
except ImportError:  # pragma: no cover - depends on interpreter version
    zstd = None

PIXELS = bytes([255, 0, 0, 255, 0, 255, 0, 128])  # 2x1 RGBA: opaque red, half-transparent green


def small_tgv(width: int = 2, height: int = 1, pixels: bytes = PIXELS, frame_checksum: bool = False) -> bytes:
    """A TGV v3 file as tgv's docstring lays it out: one A8B8G8R8_LIN mip, its payload a zstd frame at 0x40 (with
    zstd's own content checksum when `frame_checksum`, which stock frames lack)."""
    fmt = b"A8B8G8R8_LIN"
    head = struct.pack("<IIIIIIHH", 3, 2, width, height, width, height, 1, len(fmt)) + fmt + bytes(16)
    frame = zstd.compress(pixels, options={zstd.CompressionParameter.checksum_flag: int(frame_checksum)})
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


def png_file(width: int, height: int, color: int, rows: list[bytes], *, depth: int = 8, filt: int = 0,
             chunks: tuple[tuple[bytes, bytes], ...] = (), interlace: int = 0) -> bytes:
    """A PNG of `rows` (raw sample bytes each), every row written with filter `filt` (0-4), its IDAT split in two."""
    bpp = max(1, {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color] * depth // 8)

    def paeth(a, b, c):
        p = a + b - c
        return min((abs(p - a), 0, a), (abs(p - b), 1, b), (abs(p - c), 2, c))[2]
    raw, prev = bytearray(), bytes(len(rows[0]))
    for row in rows:
        enc = bytearray()
        for i, v in enumerate(row):
            left, up, ul = (row[i - bpp] if i >= bpp else 0), prev[i], (prev[i - bpp] if i >= bpp else 0)
            pred = (0, left, up, (left + up) >> 1, paeth(left, up, ul))[filt]
            enc.append((v - pred) & 255)
        raw += bytes([filt]) + enc
        prev = row
    z = zlib.compress(bytes(raw))

    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    head = struct.pack(">IIBBBBB", width, height, depth, color, 0, 0, interlace)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", head) + b"".join(chunk(k, b) for k, b in chunks)
            + chunk(b"IDAT", z[:len(z) // 2]) + chunk(b"IDAT", z[len(z) // 2:]) + chunk(b"IEND", b""))


# 3x2 RGBA, every channel varied so a wrong filter or channel order shows
RGBA = bytes(range(10, 10 + 24 * 9, 9))


@unittest.skipIf(zstd is None, "needs Python 3.14+ (compression.zstd)")
class WriterTest(unittest.TestCase):
    def test_writes_what_the_reader_reads(self):
        data = tgv.encode_tgv(3, 2, RGBA)
        hdr, pixels = tgv.decode_tgv(data)
        self.assertEqual(pixels, RGBA)
        self.assertEqual((hdr.version, hdr.flags, hdr.width, hdr.height, hdr.width2, hdr.height2, hdr.mip_count,
                          hdr.fmt, hdr.checksum, hdr.mip_offset),
                         (3, 2, 3, 2, 3, 2, 1, "A8B8G8R8_LIN", bytes(16), 0x40))
        end = hdr.mip_offset + hdr.mip_size
        self.assertEqual(len(data), end + (-end % 4))
        self.assertEqual(tgv.roundtrip(data), "")

    def test_a_picture_of_several_blocks_round_trips(self):
        pixels = bytes((x * 7 + y * 13 + (x * y) % 11) & 255 for y in range(200) for x in range(4 * 300))
        data = tgv.encode_tgv(300, 200, pixels)
        self.assertEqual(tgv.decode_tgv(data)[1], pixels)
        self.assertEqual(tgv.roundtrip(data), "")

    def test_refuses_what_it_does_not_write(self):
        with self.assertRaisesRegex(tgv.TgvError, "needs 24 pixel bytes"):
            tgv.encode_tgv(3, 2, RGBA[:-1])
        with self.assertRaisesRegex(tgv.TgvError, "writes A8B8G8R8_LIN only"):
            tgv.encode_tgv(3, 2, RGBA, "BC7_SRGB")
        with self.assertRaisesRegex(tgv.TgvError, "empty"):
            tgv.encode_tgv(0, 2, b"")

    def test_a_file_it_does_not_cover_is_skipped_never_written(self):
        good = tgv.encode_tgv(3, 2, RGBA)
        checksum = good[:0x28] + b"\x01" + good[0x29:]
        flags = good[:4] + struct.pack("<I", 3) + good[8:]
        bc7 = good[:0x1a] + struct.pack("<H", 8) + b"BC7_SRGB\0\0\0\0" + good[0x28:]
        version = struct.pack("<I", 9) + good[4:]
        with mock.patch.object(tgv, "encode_tgv", side_effect=AssertionError("encoded")):
            self.assertEqual(tgv.roundtrip(checksum), "skipped: a non-zero header checksum (the writer writes zero)")
            self.assertEqual(tgv.roundtrip(flags), "skipped: flags 0x3 (the writer writes 0x2)")
            self.assertTrue(tgv.roundtrip(bc7).startswith("skipped: format 'BC7_SRGB'"), tgv.roundtrip(bc7))
            self.assertTrue(tgv.roundtrip(version).startswith("skipped: unsupported TGV version 9"))

    def test_a_difference_is_reported(self):
        stale = small_tgv(3, 2, RGBA, frame_checksum=True)  # the same pixels in other bytes
        self.assertTrue(tgv.roundtrip(stale).startswith("differs: first at byte"), tgv.roundtrip(stale))

    def test_roundtrip_cli_counts_and_fails_on_a_difference(self):
        with tempfile.TemporaryDirectory() as tmp:
            same, other = Path(tmp, "a.tgv"), Path(tmp, "b.tgv")
            same.write_bytes(tgv.encode_tgv(3, 2, RGBA))
            other.write_bytes(small_tgv(3, 2, RGBA, frame_checksum=True))
            out = io.StringIO()
            with contextlib.redirect_stdout(out):
                self.assertEqual(tgv.main(["roundtrip", str(same)]), 0)
                self.assertEqual(tgv.main(["roundtrip", str(same), str(other)]), 1)
            self.assertIn("1 files: 1 byte-identical, 0 skipped, 0 differ", out.getvalue())
            self.assertIn("2 files: 1 byte-identical, 0 skipped, 1 differ", out.getvalue())


@unittest.skipIf(zstd is None, "needs Python 3.14+ (compression.zstd)")
class FrompngTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def read(self, data: bytes) -> tuple[int, int, bytes]:
        path = self.root / "in.png"
        path.write_bytes(data)
        return tgv.read_png(str(path))

    def test_every_filter_decodes(self):
        rows = [RGBA[:12], RGBA[12:]]
        for filt in range(5):
            self.assertEqual(self.read(png_file(3, 2, 6, rows, filt=filt)), (3, 2, RGBA), f"filter {filt}")

    def test_every_colour_type_becomes_rgba(self):
        rgb = [bytes(range(1, 10)), bytes(range(11, 20))]
        self.assertEqual(self.read(png_file(3, 2, 2, rgb, filt=4))[2],
                         bytes([1, 2, 3, 255, 4, 5, 6, 255, 7, 8, 9, 255,
                                11, 12, 13, 255, 14, 15, 16, 255, 17, 18, 19, 255]))
        self.assertEqual(self.read(png_file(2, 1, 0, [b"\x05\x09"], filt=1))[2], bytes([5, 5, 5, 255, 9, 9, 9, 255]))
        self.assertEqual(self.read(png_file(2, 1, 4, [b"\x05\x80\x09\x40"], filt=3))[2],
                         bytes([5, 5, 5, 128, 9, 9, 9, 64]))
        palette = ((b"PLTE", b"\x10\x20\x30\x40\x50\x60"), (b"tRNS", b"\x7f"))
        self.assertEqual(self.read(png_file(3, 1, 3, [b"\x01\x00\x01"], chunks=palette, filt=2))[2],
                         bytes([64, 80, 96, 255, 16, 32, 48, 127, 64, 80, 96, 255]))
        wide = [bytes([0x12, 0x34, 0x56, 0x78, 0x9a, 0xbc, 0xde, 0xf0])]  # one 16-bit RGBA pixel
        self.assertEqual(self.read(png_file(1, 1, 6, wide, depth=16, filt=1))[2], bytes([0x12, 0x56, 0x9a, 0xde]))

    def test_refuses_what_it_does_not_decode(self):
        with self.assertRaisesRegex(tgv.PngError, "interlaced"):
            self.read(png_file(3, 2, 6, [RGBA[:12], RGBA[12:]], interlace=1))
        with self.assertRaisesRegex(tgv.PngError, "colour type 0 at 4 bits"):
            self.read(png_file(2, 1, 0, [b"\x12"], depth=4))
        with self.assertRaisesRegex(tgv.PngError, "not a PNG"):
            self.read(b"GIF89a")

    def test_frompng_writes_the_tgv_topng_reads_back(self):
        png, back, out = self.root / "a.png", self.root / "b.png", self.root / "sub" / "a.tgv"
        tgv.write_png(str(png), 3, 2, RGBA)
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(tgv.main(["frompng", str(png), str(out)]), 0)
            self.assertEqual(tgv.main(["topng", str(out), str(back)]), 0)
        self.assertEqual(tgv.read_tgv(str(out))[1], RGBA)
        self.assertEqual(tgv.read_png(str(back)), (3, 2, RGBA))

    def test_frompng_cli_names_a_bad_png(self):
        bad = self.root / "bad.png"
        bad.write_bytes(b"not a png")
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(tgv.main(["frompng", str(bad), str(self.root / "x.tgv")]), 1)
        self.assertIn("bad.png: not a PNG file", err.getvalue())
        self.assertFalse((self.root / "x.tgv").exists())


MENU_PICTURES = "PC/Texture/*/MapPackAssets/Textures/*.tgv"  # below each scenario's folder


@unittest.skipIf(zstd is None, "needs Python 3.14+ (compression.zstd)")
@paths.skip_unless_extracted("scenarios")
class StockRoundTripTest(unittest.TestCase):
    def test_every_stock_menu_picture_round_trips(self):
        """write(read(f)) == f, byte for byte, for every scenario's menu pictures in the extraction. A file the
        writer does not cover is skipped (never written); none may differ."""
        files = sorted((paths.extracted_root() / "scenarios").glob(f"*/{MENU_PICTURES}"))
        if not files:
            self.skipTest("the extraction holds no scenario menu pictures (re-run warno-setup's extract)")
        got = {f.relative_to(paths.extracted_root()).as_posix(): tgv.roundtrip(f.read_bytes()) for f in files}
        self.assertEqual([f"{k}: {v}" for k, v in got.items() if v.startswith("differs")], [])
        self.assertIn("", got.values())


if __name__ == "__main__":
    unittest.main()
