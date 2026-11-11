"""Read and write Eugen Systems TGV v3 textures (WARNO .tgv), and convert them to and from PNG.

Stdlib only; needs Python 3.14+ for `compression.zstd`.

Layout verified against every stock scenario's menu pictures (the 91
`<scenario>/PC/Texture/<scenario>/MapPackAssets/Textures/*.tgv` of the
challenge and CampagneStrat scenarios, MapTexture.tgv among them) and the
maps' Preview and Minimap pictures. All integers are little-endian. Only
what those files exercise is supported; anything else is rejected with an
explicit error rather than guessed.

   0  u32     version = 3
   4  u32     flags = 2 (meaning unknown; constant in every observed file)
   8  u32     width
  12  u32     height
  16  u32     width  (repeat; equal to the above in every observed file)
  20  u32     height (repeat)
  24  u16     mip_count (= 1 in every observed file)
  26  u16     format_len
  28  char    format[format_len], NUL-padded to a 4-byte boundary
  ..  u8[16]  checksum: zero in every menu picture; the maps' Preview, Minimap
              and Overview pictures carry a non-zero one (not an MD5 of the
              pixels, the payload or the file; unknown)
  ..  u32     offset, u32 size   -- the mip table; only mip_count = 1 is
                                    verified (offset 0x40 for a 12-char format)
  at offset:  char[4] "ZSTD" | u32 uncompressed_size | one zstd frame
              `size` counts the 8-byte "ZSTD" header plus the frame.
  The file is then zero-padded to a multiple of 4 bytes.

Pixel formats:
  A8B8G8R8_LIN  4 bytes/pixel, memory order R, G, B, A, rows top-down,
                uncompressed_size == width * height * 4. Alpha is real
                (the map pictures have transparent margins).

Writing (encode_tgv) is the inverse of reading, for what the menu pictures
use: one A8B8G8R8_LIN mip, flags 2, a zero checksum, the mip at the end of
the header. Its payload is one zstd frame at level 6 with the content size,
in whole 128 KB blocks: stock's frames are exactly that. libzstd 1.5.7
added a block pre-splitter, on by default, that cuts some blocks short;
the writer turns it off (ZSTD_c_blockSplitterLevel = 1, an experimental
parameter Python's CompressionParameter does not name), so every stock
menu picture round-trips byte for byte (`roundtrip`). A file the writer
does not cover (`unwritable`) is reported, never rewritten.

CLI (run with `python -m modkit.core.tgv ...`):
  info      <tgv>                  header fields and payload checks
  topng     <tgv> <png> [--opaque] decode to an RGBA PNG (--opaque drops alpha); makes the PNG's folders
  frompng   <png> <tgv>            encode an 8- or 16-bit, non-interlaced PNG as A8B8G8R8_LIN; makes the folders
  roundtrip <tgv>...               re-encode each file and compare, byte for byte; exit 1 on any difference
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

# What the writer produces, as every stock menu picture has it.
WRITE_FORMAT = "A8B8G8R8_LIN"
WRITE_FLAGS = 2
ZSTD_LEVEL = 6
# zstd's ZSTD_c_blockSplitterLevel (experimental, libzstd 1.5.7 and newer): 1 keeps whole 128 KB blocks, as the
# libzstd that wrote stock did. Older libzstd has no pre-splitter and no such parameter.
_ZSTD_BLOCK_SPLITTER_LEVEL = 1017


class TgvError(ValueError):
    """Raised when a file is not a TGV variant this module can read."""


class PngError(ValueError):
    """Raised when a PNG is not a variant read_png decodes."""


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
        return decode_tgv(f.read())


def decode_tgv(data: bytes) -> tuple[TgvHeader, bytes]:
    """read_tgv on a file's bytes."""
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


# --------------------------------------------------------------------------- writing

def _header_size(fmt: str) -> int:
    """Bytes before the payload: the fixed fields, the format padded to 4, the checksum and a one-mip table."""
    return ((_HEAD.size + len(fmt.encode("ascii")) + 3) & ~3) + 16 + _MIP.size


def _compress(pixels: bytes) -> bytes:
    options = {zstd.CompressionParameter.compression_level: ZSTD_LEVEL}
    if zstd.zstd_version_info >= (1, 5, 7):
        options[_ZSTD_BLOCK_SPLITTER_LEVEL] = 1
    return zstd.compress(pixels, options=options)


def encode_tgv(width: int, height: int, pixels: bytes, fmt: str = WRITE_FORMAT) -> bytes:
    """A TGV v3 file of `pixels` (RGBA8, rows top-down) as stock menu pictures are: one mip, flags 2, a zero
    checksum, a zstd payload (the module docstring). The inverse of decode_tgv for every file `unwritable` passes."""
    if fmt != WRITE_FORMAT:
        raise TgvError(f"the writer writes {WRITE_FORMAT} only, not {fmt!r}")
    if zstd is None:
        raise TgvError("this Python lacks compression.zstd (need 3.14+)")
    if width <= 0 or height <= 0:
        raise TgvError(f"size {width}x{height} is empty")
    expect = width * height * BYTES_PER_PIXEL[fmt]
    if len(pixels) != expect:
        raise TgvError(f"{fmt} {width}x{height} needs {expect} pixel bytes, got {len(pixels)}")
    name = fmt.encode("ascii")
    head = _HEAD.pack(SUPPORTED_VERSION, WRITE_FLAGS, width, height, width, height, 1, len(name)) + name
    head += bytes(-len(head) % 4) + bytes(16)  # the format, NUL-padded to 4; the checksum, zero
    frame = _compress(bytes(pixels))
    out = (head + _MIP.pack(len(head) + _MIP.size, _PAYLOAD_HEAD.size + len(frame))
           + _PAYLOAD_HEAD.pack(b"ZSTD", len(pixels)) + frame)
    return out + bytes(-len(out) % 4)


def write_tgv(path: str, width: int, height: int, pixels: bytes, fmt: str = WRITE_FORMAT) -> None:
    """encode_tgv, written to `path` (its folders made)."""
    data = encode_tgv(width, height, pixels, fmt)
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def unwritable(hdr: TgvHeader) -> str:
    """Why encode_tgv cannot reproduce a file with this header ('' when it covers it)."""
    if hdr.fmt != WRITE_FORMAT:
        return f"format {hdr.fmt!r} (the writer writes {WRITE_FORMAT})"
    if hdr.flags != WRITE_FLAGS:
        return f"flags {hdr.flags:#x} (the writer writes {WRITE_FLAGS:#x})"
    if hdr.mip_count != 1:
        return f"{hdr.mip_count} mips (the writer writes one)"
    if (hdr.width, hdr.height) != (hdr.width2, hdr.height2):
        return "the two size fields disagree"
    if any(hdr.checksum):
        return "a non-zero header checksum (the writer writes zero)"
    if hdr.mip_offset != _header_size(hdr.fmt):
        return f"its payload at {hdr.mip_offset:#x}, not right after the header"
    return ""


def roundtrip(data: bytes) -> str:
    """'' when encode_tgv(decode_tgv(data)) is `data`, byte for byte; else 'skipped: <why>' for a file the writer
    does not cover (nothing is encoded), or 'differs: <where>'."""
    try:
        why = unwritable(parse_header(data))
    except TgvError as e:  # a version or mip layout the reader rejects: not one the writer covers either
        why = str(e)
    if why:
        return f"skipped: {why}"
    hdr, pixels = decode_tgv(data)
    out = encode_tgv(hdr.width, hdr.height, pixels, hdr.fmt)
    if out == data:
        return ""
    at = next((i for i, (a, b) in enumerate(zip(out, data)) if a != b), min(len(out), len(data)))
    return f"differs: first at byte {at:#x} ({len(out)} bytes written, {len(data)} read)"


# --------------------------------------------------------------------------- PNG

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


_PNG_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}  # colour type -> samples per pixel


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    return a if pa <= pb and pa <= pc else b if pb <= pc else c


def _unfilter(raw: bytes, height: int, stride: int, bpp: int) -> bytearray:
    """The PNG scanlines of `raw` (a filter byte, then `stride` bytes, per row) with their filters undone."""
    if len(raw) < height * (stride + 1):
        raise PngError(f"image data holds {len(raw)} bytes, {height} rows of {stride} need {height * (stride + 1)}")
    out = bytearray(height * stride)
    prev = bytes(stride)
    for y in range(height):
        kind, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        if kind == 1:
            for i in range(bpp, stride):
                line[i] = (line[i] + line[i - bpp]) & 255
        elif kind == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif kind == 3:
            for i in range(stride):
                line[i] = (line[i] + (((line[i - bpp] if i >= bpp else 0) + prev[i]) >> 1)) & 255
        elif kind == 4:
            for i in range(stride):
                left, upleft = (line[i - bpp], prev[i - bpp]) if i >= bpp else (0, 0)
                line[i] = (line[i] + _paeth(left, prev[i], upleft)) & 255
        elif kind != 0:
            raise PngError(f"row {y}: unknown filter {kind}")
        out[y * stride:(y + 1) * stride] = line
        prev = line
    return out


def read_png(path: str) -> tuple[int, int, bytes]:
    """(width, height, pixels) of a PNG, the pixels RGBA8, rows top-down. Grey, grey+alpha, RGB, RGBA and palette
    images (with tRNS alpha), 8 or 16 bits a sample (16 keeps the high byte), not interlaced; anything else raises
    PngError."""
    with open(path, "rb") as f:
        data = f.read()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise PngError("not a PNG file")
    pos, chunks, idat = 8, {}, bytearray()
    while pos + 8 <= len(data):
        length, kind = struct.unpack_from(">I4s", data, pos)
        body = data[pos + 8:pos + 8 + length]
        if len(body) != length:
            raise PngError(f"chunk {kind!r} is truncated")
        if kind == b"IDAT":
            idat += body
        else:
            chunks.setdefault(kind, body)
        pos += 12 + length
        if kind == b"IEND":
            break
    if b"IHDR" not in chunks:
        raise PngError("no IHDR chunk")
    width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", chunks[b"IHDR"])
    if color not in _PNG_CHANNELS or depth not in (8, 16) or (color == 3 and depth != 8):
        raise PngError(f"colour type {color} at {depth} bits a sample is not supported (8 or 16 bits; palettes 8)")
    if interlace:
        raise PngError("interlaced PNGs are not supported")
    nbytes = depth // 8
    bpp = _PNG_CHANNELS[color] * nbytes
    rows = _unfilter(zlib.decompress(bytes(idat)), height, width * bpp, bpp)
    samples = rows if nbytes == 1 else rows[0::2]  # 16-bit samples are big-endian: keep the high byte
    n = width * height
    out = bytearray(n * 4)
    if color == 6:
        out[:] = samples
    elif color == 2:
        out[0::4], out[1::4], out[2::4], out[3::4] = samples[0::3], samples[1::3], samples[2::3], b"\xff" * n
    elif color in (0, 4):
        grey = samples[0::2] if color == 4 else samples
        out[0::4], out[1::4], out[2::4] = grey, grey, grey
        out[3::4] = samples[1::2] if color == 4 else b"\xff" * n
    else:
        plte = chunks.get(b"PLTE", b"")
        alpha = chunks.get(b"tRNS", b"")
        table = [plte[i * 3:i * 3 + 3] + bytes([alpha[i] if i < len(alpha) else 255]) for i in range(len(plte) // 3)]
        if samples and max(samples) >= len(table):
            raise PngError(f"a pixel names palette entry {max(samples)}, the palette has {len(table)}")
        out[:] = b"".join(table[i] for i in samples)
    return width, height, bytes(out)


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


def cmd_frompng(args) -> int:
    width, height, pixels = read_png(args.png)
    write_tgv(args.tgv, width, height, pixels)
    print(f"# {args.png}: {width}x{height} -> {args.tgv} ({WRITE_FORMAT})", file=sys.stderr)
    return 0


def cmd_roundtrip(args) -> int:
    same, skipped, differ = 0, [], []
    for name in args.tgv:
        with open(name, "rb") as f:
            got = roundtrip(f.read())
        if not got:
            same += 1
        else:
            (skipped if got.startswith("skipped") else differ).append(f"{name}: {got}")
    for line in skipped + differ:
        print(line)
    print(f"{len(args.tgv)} files: {same} byte-identical, {len(skipped)} skipped, {len(differ)} differ")
    return 1 if differ else 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("info", help="print header fields and check the payload")
    p.add_argument("tgv")
    p.set_defaults(fn=cmd_info, name="tgv")
    p = sub.add_parser("topng", help="decode to PNG")
    p.add_argument("tgv")
    p.add_argument("png")
    p.add_argument("--opaque", action="store_true", help="write RGB, discarding alpha")
    p.set_defaults(fn=cmd_topng, name="tgv")
    p = sub.add_parser("frompng", help=f"encode a PNG as a {WRITE_FORMAT} TGV")
    p.add_argument("png")
    p.add_argument("tgv")
    p.set_defaults(fn=cmd_frompng, name="png")
    p = sub.add_parser("roundtrip", help="re-encode each TGV and compare, byte for byte")
    p.add_argument("tgv", nargs="+")
    p.set_defaults(fn=cmd_roundtrip, name="tgv")
    args = ap.parse_args(argv)
    try:
        return args.fn(args)
    except (TgvError, PngError) as e:
        where = getattr(args, args.name)
        print(f"error: {where if isinstance(where, str) else ', '.join(where)}: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
