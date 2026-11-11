"""Read Eugen Systems TGV v3 textures (WARNO .tgv) and convert them to PNG.

Stdlib only; needs Python 3.14+ for `compression.zstd`.

Layout verified against all 16 single-player Operation map pictures
(challenge_*/.../MapPackAssets/Textures/MapTexture.tgv). All integers are
little-endian. Only what those files exercise is supported; anything else
is rejected with an explicit error rather than guessed.

   0  u32     version = 3
   4  u32     flags = 2 (meaning unknown; constant in every observed file)
   8  u32     width
  12  u32     height
  16  u32     width  (repeat; equal to the above in every observed file)
  20  u32     height (repeat)
  24  u16     mip_count (= 1 in every observed file)
  26  u16     format_len
  28  char    format[format_len], NUL-padded to a 4-byte boundary
  ..  u8[16]  checksum (all zero in every observed file)
  ..  u32     offset, u32 size   -- the mip table; only mip_count = 1 is
                                    verified (offset 0x40 for a 12-char format)
  at offset:  char[4] "ZSTD" | u32 uncompressed_size | one zstd frame
              `size` counts the 8-byte "ZSTD" header plus the frame.
  The file is then zero-padded to a multiple of 4 bytes.

Pixel formats:
  A8B8G8R8_LIN  4 bytes/pixel, memory order R, G, B, A, rows top-down,
                uncompressed_size == width * height * 4. Alpha is real
                (the map pictures have transparent margins).

CLI (run with `python -m modkit.core.tgv ...`):
  info  <tgv>                     header fields and payload checks
  topng <tgv> <png> [--opaque]    decode to an RGBA PNG (--opaque drops alpha); makes the PNG's folders
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path

try:
    from compression import zstd
except ImportError:  # pragma: no cover - depends on interpreter version
    zstd = None

_HEAD = struct.Struct("<IIIIIIHH")  # 28 bytes, up to and including format_len
_MIP = struct.Struct("<II")  # (offset, size)
_PAYLOAD_HEAD = struct.Struct("<4sI")  # ("ZSTD", uncompressed_size)
SUPPORTED_VERSION = 3
BYTES_PER_PIXEL = {"A8B8G8R8_LIN": 4}


class TgvError(ValueError):
    """Raised when a file is not a TGV variant this module can read."""


@dataclass
class TgvHeader:
    version: int
    flags: int
    width: int
    height: int
    width2: int
    height2: int
    mip_count: int
    fmt: str
    checksum: bytes
    mip_offset: int
    mip_size: int
    file_size: int


def parse_header(data: bytes) -> TgvHeader:
    if len(data) < _HEAD.size:
        raise TgvError("file too short for a TGV header")
    version, flags, w, h, w2, h2, mips, flen = _HEAD.unpack_from(data, 0)
    if version != SUPPORTED_VERSION:
        raise TgvError(f"unsupported TGV version {version} (only {SUPPORTED_VERSION} is verified)")
    pos = _HEAD.size
    fmt_raw = data[pos:pos + flen]
    fmt = fmt_raw.split(b"\0", 1)[0].decode("ascii", "replace")
    pos = (pos + flen + 3) & ~3
    checksum = bytes(data[pos:pos + 16])
    pos += 16
    if mips != 1:
        raise TgvError(f"mip_count={mips}: only single-mip files are verified "
                       "(the multi-mip table layout is unknown)")
    if len(data) < pos + _MIP.size:
        raise TgvError("file truncated inside the mip table")
    off, size = _MIP.unpack_from(data, pos)
    return TgvHeader(version, flags, w, h, w2, h2, mips, fmt, checksum, off, size, len(data))


def read_tgv(path: str) -> tuple[TgvHeader, bytes]:
    """Return (header, pixels). Pixels are RGBA8, rows top-down."""
    with open(path, "rb") as f:
        data = f.read()
    hdr = parse_header(data)
    if hdr.fmt not in BYTES_PER_PIXEL:
        raise TgvError(f"pixel format {hdr.fmt!r} is not supported "
                       f"(supported: {', '.join(BYTES_PER_PIXEL)})")
    if (hdr.width, hdr.height) != (hdr.width2, hdr.height2):
        raise TgvError(f"size fields disagree ({hdr.width}x{hdr.height} vs "
                       f"{hdr.width2}x{hdr.height2}); meaning unverified")
    end = hdr.mip_offset + hdr.mip_size
    if hdr.mip_size < _PAYLOAD_HEAD.size or end > len(data):
        raise TgvError(f"mip 0 [{hdr.mip_offset:#x}+{hdr.mip_size:#x}] lies outside the file")
    magic, usize = _PAYLOAD_HEAD.unpack_from(data, hdr.mip_offset)
    if magic != b"ZSTD":
        raise TgvError(f"payload magic {magic!r} is not supported (only b'ZSTD' is verified)")
    if zstd is None:
        raise TgvError("this Python lacks compression.zstd (need 3.14+)")
    expect = hdr.width * hdr.height * BYTES_PER_PIXEL[hdr.fmt]
    if usize != expect:
        raise TgvError(f"payload declares {usize} bytes, {hdr.fmt} {hdr.width}x{hdr.height} "
                       f"needs {expect}")
    dec = zstd.ZstdDecompressor()
    pixels = dec.decompress(data[hdr.mip_offset + _PAYLOAD_HEAD.size:end])
    if not dec.eof or dec.unused_data or len(pixels) != usize:
        raise TgvError(f"zstd frame did not decode to exactly {usize} bytes "
                       f"(got {len(pixels)}, eof={dec.eof}, unused={len(dec.unused_data)})")
    if any(data[end:]):
        raise TgvError(f"non-zero bytes after the payload at {end:#x}")
    return hdr, pixels


def _chunk(kind: bytes, body: bytes) -> bytes:
    return (struct.pack(">I", len(body)) + kind + body
            + struct.pack(">I", zlib.crc32(kind + body) & 0xFFFFFFFF))


def write_png(path: str, width: int, height: int, pixels: bytes, channels: int = 4) -> None:
    """Write 8-bit RGB (channels=3) or RGBA (channels=4) pixels, rows top-down."""
    color_type = {3: 2, 4: 6}[channels]
    stride = width * channels
    if len(pixels) != stride * height:
        raise ValueError(f"expected {stride * height} pixel bytes, got {len(pixels)}")
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # filter: none
        raw += pixels[y * stride:(y + 1) * stride]
    png = (b"\x89PNG\r\n\x1a\n"
           + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color_type, 0, 0, 0))
           + _chunk(b"IDAT", zlib.compress(bytes(raw), 9))
           + _chunk(b"IEND", b""))
    with open(path, "wb") as f:
        f.write(png)


def drop_alpha(rgba: bytes) -> bytes:
    out = bytearray(len(rgba) // 4 * 3)
    out[0::3] = rgba[0::4]
    out[1::3] = rgba[1::4]
    out[2::3] = rgba[2::4]
    return bytes(out)


def cmd_info(args) -> int:
    with open(args.tgv, "rb") as f:
        data = f.read()
    hdr = parse_header(data)
    print(f"version    {hdr.version}")
    print(f"flags      {hdr.flags:#x}")
    print(f"size       {hdr.width}x{hdr.height} (repeat {hdr.width2}x{hdr.height2})")
    print(f"mip_count  {hdr.mip_count}")
    print(f"format     {hdr.fmt}")
    print(f"checksum   {hdr.checksum.hex()}")
    print(f"mip0       offset {hdr.mip_offset:#x} size {hdr.mip_size:#x} "
          f"(file {hdr.file_size:#x})")
    _, pixels = read_tgv(args.tgv)
    alpha = pixels[3::4]
    print(f"payload    {len(pixels)} bytes OK; alpha min {min(alpha)} max {max(alpha)}")
    return 0


def cmd_topng(args) -> int:
    hdr, pixels = read_tgv(args.tgv)
    Path(args.png).parent.mkdir(parents=True, exist_ok=True)  # e.g. maps/preview_full/ in a fresh extraction
    if args.opaque:
        write_png(args.png, hdr.width, hdr.height, drop_alpha(pixels), 3)
    else:
        write_png(args.png, hdr.width, hdr.height, pixels, 4)
    print(f"# {args.tgv}: {hdr.fmt} {hdr.width}x{hdr.height} -> {args.png}", file=sys.stderr)
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="print header fields and check the payload")
    p.add_argument("tgv")
    p.set_defaults(fn=cmd_info)
    p = sub.add_parser("topng", help="decode to PNG")
    p.add_argument("tgv")
    p.add_argument("png")
    p.add_argument("--opaque", action="store_true", help="write RGB, discarding alpha")
    p.set_defaults(fn=cmd_topng)
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except TgvError as e:
        print(f"error: {args.tgv}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
