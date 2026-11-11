#!/usr/bin/env python3
"""Decode (and re-encode) Eugen CNDF ``.ndfbin`` files (WARNO), stdlib only.

Container: ``EUG0`` v1 ``CNDF`` header (40 bytes), compression mode at byte 12
(0 = none, 1 = raw LZ4 block, 2 = zstd frame, 3 = zlib), u32 body size at 40 and
the compressed stream at 44 when compressed.  The decompressed image is
header(40) + body; section offsets in the ``TOC0`` footer are absolute in that
image.  Tables: OBJE TOPO CHNK CLAS PROP STRG TRAN IMPR EXPR.

The in-memory model (:class:`NdfBin`) mirrors the tables one to one so that
:func:`encode_body` can rebuild the decompressed body byte for byte.

CLI::

    python -m modkit.core.ndfbin dump <file.ndfbin> [-o out.txt] [--flat]
    python -m modkit.core.ndfbin roundtrip <file.ndfbin> [...]
    python -m modkit.core.ndfbin info <file.ndfbin>

Localisation values (tag 0x1D) are 6-bit packed tokens; see :func:`token_hash`.

Python 3.14+ is needed for zstd (``compression.zstd``); LZ4/zlib/none work on
any Python 3.10+.
"""
from __future__ import annotations

import argparse
import struct
import sys
import zlib
from dataclasses import dataclass, field

try:  # Python 3.14+
    from compression import zstd as _zstd
except ImportError:  # pragma: no cover
    _zstd = None

HEADER_SIZE = 40
OBJ_END = 0xABABABAB
REF_OBJECT = 0xBBBBBBBB
REF_IMPORT = 0xAAAAAAAA
NONE_IDX = 0xFFFFFFFF

MODE_NONE, MODE_LZ4, MODE_ZSTD, MODE_ZLIB = 0, 1, 2, 3


# --------------------------------------------------------------------------- LZ4

def lz4_block_decompress(src: bytes, usize: int | None = None) -> bytes:
    """Decode one raw LZ4 block (no frame).  Pure Python."""
    dst = bytearray()
    i, n = 0, len(src)
    while i < n:
        tok = src[i]
        i += 1
        ll = tok >> 4
        if ll == 15:
            while True:
                b = src[i]
                i += 1
                ll += b
                if b != 255:
                    break
        dst += src[i:i + ll]
        i += ll
        if i >= n:
            break
        off = src[i] | (src[i + 1] << 8)
        i += 2
        if off == 0:
            raise ValueError('lz4: zero offset')
        ml = tok & 15
        if ml == 15:
            while True:
                b = src[i]
                i += 1
                ml += b
                if b != 255:
                    break
        ml += 4
        st = len(dst) - off
        if st < 0:
            raise ValueError('lz4: offset before start')
        if off >= ml:
            dst += dst[st:st + ml]
        else:  # overlapping copy
            for k in range(ml):
                dst.append(dst[st + k])
    if usize is not None and len(dst) != usize:
        raise ValueError(f'lz4: got {len(dst)} bytes, expected {usize}')
    return bytes(dst)


def lz4_block_store(data: bytes) -> bytes:
    """Encode ``data`` as a valid LZ4 block made of literals only (no matches).

    Not size-efficient, but any LZ4 block decoder accepts it.
    """
    out = bytearray()
    ll = len(data)
    if ll >= 15:
        out.append(0xF0)
        rem = ll - 15
        while rem >= 255:
            out.append(255)
            rem -= 255
        out.append(rem)
    else:
        out.append(ll << 4)
    out += data
    return bytes(out)


# --------------------------------------------------------------------------- model

@dataclass
class Value:
    """One tagged value.  ``tag`` is the u32 type tag.

    payload by tag:
      0x00 bool, 0x01 int (u8), 0x02 int32, 0x03 uint32, 0x04 uint64, 0x05/0x06 float,
      0x07/0x1C STRG index, 0x08 bytes (UTF-16LE), 0x09 :class:`Ref`,
      0x0B/0x21 tuple of floats, 0x0E/0x1F tuple of ints, 0x0C/0x0D/0x1A/0x1D/0x25 bytes,
      0x11 list[Value], 0x12 list[tuple[Value, Value]], 0x13 int64, 0x14/0x1E bytes,
      0x18 int16, 0x19 uint16, 0x22 tuple[Value, Value].
    """
    tag: int
    v: object
    extra: object = None  # 0x1E: marker byte


@dataclass
class Ref:
    kind: int          # REF_OBJECT or REF_IMPORT (or something unknown)
    index: int         # object index / import index
    cls: int | None = None  # class index (object refs only)


@dataclass
class Obj:
    cls: int
    props: list[tuple[int, Value]] = field(default_factory=list)


@dataclass
class Node:
    """IMPR/EXPR path-tree node."""
    tran: int
    obj: int
    children: list['Node'] = field(default_factory=list)


@dataclass
class NdfBin:
    mode: int = MODE_ZSTD
    version: int = 1
    header_size: int = HEADER_SIZE
    sections: list[str] = field(default_factory=list)   # TOC order
    section_layout: list[str] = field(default_factory=list)  # on-disk order
    objects: list[Obj] = field(default_factory=list)
    topo: list[int] = field(default_factory=list)
    chnk: list[tuple[int, int]] = field(default_factory=list)
    classes: list[bytes] = field(default_factory=list)
    props: list[tuple[bytes, int]] = field(default_factory=list)
    strings: list[bytes] = field(default_factory=list)
    trans: list[bytes] = field(default_factory=list)
    imports: Node | None = None
    exports: Node | None = None
    unknown_sections: dict[str, bytes] = field(default_factory=dict)

    # ---- convenience
    def cname(self, i: int) -> str:
        return self.classes[i].decode('latin-1') if 0 <= i < len(self.classes) else f'<class#{i}>'

    def pname(self, i: int) -> str:
        return self.props[i][0].decode('latin-1') if 0 <= i < len(self.props) else f'<prop#{i}>'

    def tname(self, i: int) -> str:
        return self.trans[i].decode('latin-1') if 0 <= i < len(self.trans) else f'<tran#{i}>'

    # ---- interning helpers for writers.  Eugen's files list CLAS and PROP in
    # first-use order (objects scanned in index order); appending keeps existing
    # indices stable but new entries then sit at the end.
    def intern_class(self, name: str) -> int:
        b = name.encode('latin-1')
        if b not in self.classes:
            self.classes.append(b)
        return self.classes.index(b)

    def intern_prop(self, name: str, cls: int) -> int:
        """Return the (name, cls) PROP entry, appending it if missing.  Note: for a
        property inherited from a common C++ base, Eugen's files share one entry whose
        owner is the first class that used it (seen in LevelDesign/Items.sav); pass
        that owner as ``cls`` to reuse it.  GDScript classes declare their own."""
        b = name.encode('latin-1')
        for k, (n, owner) in enumerate(self.props):
            if n == b and owner == cls:
                return k
        self.props.append((b, cls))
        return len(self.props) - 1

    def intern_string(self, s: str) -> int:
        b = s.encode('latin-1')
        if b not in self.strings:
            self.strings.append(b)
        return self.strings.index(b)

    def intern_tran(self, s: str) -> int:
        b = s.encode('latin-1')
        if b not in self.trans:
            self.trans.append(b)
        return self.trans.index(b)


# --------------------------------------------------------------------------- reading

class _R:
    __slots__ = ('b', 'p')

    def __init__(self, b: bytes, p: int = 0):
        self.b, self.p = b, p

    def u32(self) -> int:
        v = struct.unpack_from('<I', self.b, self.p)[0]
        self.p += 4
        return v

    def take(self, n: int) -> bytes:
        v = self.b[self.p:self.p + n]
        if len(v) != n:
            raise ValueError(f'truncated read of {n} at {self.p}')
        self.p += n
        return bytes(v)

    def unpack(self, fmt: str):
        v = struct.unpack_from(fmt, self.b, self.p)
        self.p += struct.calcsize(fmt)
        return v


_FIXED = {  # tag -> struct format (scalar or tuple)
    0x00: '<?', 0x01: '<B', 0x02: '<i', 0x03: '<I', 0x04: '<Q', 0x05: '<f', 0x06: '<d',
    0x07: '<I', 0x0B: '<3f', 0x0E: '<3i', 0x13: '<q', 0x18: '<h', 0x19: '<H',
    0x1C: '<I', 0x1F: '<2i', 0x21: '<2f',
}
_RAW = {0x0C: 16, 0x0D: 4, 0x1A: 16, 0x1D: 8, 0x25: 16}


def read_value(r: _R) -> Value:
    tag = r.u32()
    if tag in _FIXED:
        fmt = _FIXED[tag]
        v = r.unpack(fmt)
        if tag == 0x00:
            # keep the raw byte so non-0/1 bools survive a round trip
            r.p -= 1
            v = r.b[r.p]
            r.p += 1
            return Value(tag, v)
        return Value(tag, v[0] if len(v) == 1 else tuple(v))
    if tag in _RAW:
        return Value(tag, r.take(_RAW[tag]))
    if tag == 0x08:
        n = r.u32()
        return Value(tag, r.take(n))
    if tag == 0x09:
        kind = r.u32()
        if kind == REF_OBJECT:
            idx, cls = r.u32(), r.u32()
            return Value(tag, Ref(kind, idx, cls))
        if kind == REF_IMPORT:
            return Value(tag, Ref(kind, r.u32()))
        raise ValueError(f'unknown reference kind 0x{kind:08X} at {r.p - 4}')
    if tag == 0x11:
        n = r.u32()
        return Value(tag, [read_value(r) for _ in range(n)])
    if tag == 0x12:
        n = r.u32()
        return Value(tag, [(read_value(r), read_value(r)) for _ in range(n)])
    if tag == 0x22:
        k = read_value(r)
        return Value(tag, (k, read_value(r)))
    if tag == 0x14:
        n = r.u32()
        return Value(tag, r.take(n))
    if tag == 0x1E:
        n = r.u32()
        marker = r.take(1)[0]
        return Value(tag, r.take(n), marker)
    raise ValueError(f'unknown value tag 0x{tag:02X} at {r.p - 4}')


def _strtab(b: bytes, off: int, size: int) -> list[bytes]:
    out, p, end = [], off, off + size
    while p < end:
        n = struct.unpack_from('<I', b, p)[0]
        out.append(bytes(b[p + 4:p + 4 + n]))
        p += 4 + n
    if p != end:
        raise ValueError('string table overruns its section')
    return out


def _tree(b: bytes, off: int, size: int) -> Node | None:
    if size == 0:
        return None

    def node(p: int) -> tuple[Node, int]:
        tran, obj, cnt = struct.unpack_from('<III', b, p)
        arr = p + 12
        offs = struct.unpack_from(f'<{cnt}I', b, arr)
        nd = Node(tran, obj)
        end = arr + 4 * cnt
        for o in offs:
            ch, ch_end = node(arr + o)
            nd.children.append(ch)
            end = max(end, ch_end)
        return nd, end

    root, end = node(off)
    if end != off + size:
        raise ValueError(f'path tree size mismatch: parsed to {end - off}, section {size}')
    return root


def decompress(raw: bytes) -> tuple[dict, bytes]:
    """Return (header dict, decompressed image = header + body)."""
    magic, ver, cndf, mode, footer, hsize, full = struct.unpack_from('<4sI4sIQQQ', raw, 0)
    if magic != b'EUG0' or cndf != b'CNDF':
        raise ValueError(f'not an EUG0/CNDF file: {raw[:12]!r}')
    hdr = dict(version=ver, mode=mode, footer=footer, header_size=hsize, full_size=full)
    if mode == MODE_NONE:
        body = raw[hsize:]
    else:
        bsize = struct.unpack_from('<I', raw, 40)[0]
        hdr['body_size'] = bsize
        stream = raw[44:]
        if mode == MODE_LZ4:
            body = lz4_block_decompress(stream, bsize)
        elif mode == MODE_ZSTD:
            if _zstd is None:
                raise RuntimeError('zstd needs Python 3.14+ (compression.zstd)')
            body = _zstd.decompress(stream)
        elif mode == MODE_ZLIB:
            body = zlib.decompress(stream)
        else:
            raise ValueError(f'unknown compression mode {mode}')
        if len(body) != bsize:
            raise ValueError(f'body size {len(body)} != declared {bsize}')
    image = bytes(raw[:hsize]) + bytes(body)
    if len(image) != full:
        raise ValueError(f'image size {len(image)} != declared {full}')
    return hdr, image


def parse_image(image: bytes, hdr: dict) -> NdfBin:
    nb = NdfBin(mode=hdr['mode'], version=hdr['version'], header_size=hdr['header_size'])
    foot = hdr['footer']
    if image[foot:foot + 4] != b'TOC0':
        raise ValueError('missing TOC0 footer')
    cnt = struct.unpack_from('<I', image, foot + 4)[0]
    secs: dict[str, tuple[int, int]] = {}
    for k in range(cnt):
        nm, off, sz = struct.unpack_from('<8sQQ', image, foot + 8 + 24 * k)
        name = nm.rstrip(b'\0').decode('ascii')
        secs[name] = (off, sz)
        nb.sections.append(name)
    if foot + 8 + 24 * cnt != len(image):
        raise ValueError('trailing bytes after TOC0')
    nb.section_layout = sorted(nb.sections, key=lambda s: secs[s][0])
    # contiguity check (needed for a byte-exact rebuild)
    pos = nb.header_size
    for s in nb.section_layout:
        off, sz = secs[s]
        if off != pos:
            raise ValueError(f'section {s} at {off}, expected contiguous {pos}')
        pos += sz
    if pos != foot:
        raise ValueError(f'gap before footer: {pos} != {foot}')

    def sec(name):
        return secs.get(name, (0, 0))

    o, s = sec('CLAS'); nb.classes = _strtab(image, o, s)
    o, s = sec('STRG'); nb.strings = _strtab(image, o, s)
    o, s = sec('TRAN'); nb.trans = _strtab(image, o, s)
    o, s = sec('PROP')
    p, end = o, o + s
    while p < end:
        n = struct.unpack_from('<I', image, p)[0]
        name = bytes(image[p + 4:p + 4 + n])
        owner = struct.unpack_from('<I', image, p + 4 + n)[0]
        nb.props.append((name, owner))
        p += 8 + n
    o, s = sec('TOPO'); nb.topo = list(struct.unpack_from(f'<{s // 4}I', image, o))
    o, s = sec('CHNK')
    nb.chnk = [struct.unpack_from('<II', image, o + 8 * k) for k in range(s // 8)]
    o, s = sec('IMPR'); nb.imports = _tree(image, o, s)
    o, s = sec('EXPR'); nb.exports = _tree(image, o, s)
    for name in nb.sections:
        if name not in {'OBJE', 'TOPO', 'CHNK', 'CLAS', 'PROP', 'STRG', 'TRAN', 'IMPR', 'EXPR'}:
            o, s = secs[name]
            nb.unknown_sections[name] = bytes(image[o:o + s])
    # objects
    o, s = sec('OBJE')
    r = _R(image, o)
    end = o + s
    while r.p < end:
        ob = Obj(r.u32())
        while True:
            pi = r.u32()
            if pi == OBJ_END:
                break
            ob.props.append((pi, read_value(r)))
        nb.objects.append(ob)
    if r.p != end:
        raise ValueError('OBJE overrun')
    return nb


def decode(raw: bytes) -> tuple[NdfBin, dict, bytes]:
    """A whole .ndfbin file's bytes, any compression -> (parsed file, header dict, decompressed image)."""
    hdr, image = decompress(raw)
    return parse_image(image, hdr), hdr, image


def load(path: str) -> tuple[NdfBin, dict, bytes]:
    """decode() of the file at `path`."""
    with open(path, 'rb') as fh:
        return decode(fh.read())


# --------------------------------------------------------------------------- writing

def write_value(out: bytearray, v: Value) -> None:
    tag = v.tag
    out += struct.pack('<I', tag)
    if tag == 0x00:
        out.append(v.v)
    elif tag in _FIXED:
        fmt = _FIXED[tag]
        out += struct.pack(fmt, *v.v) if isinstance(v.v, tuple) else struct.pack(fmt, v.v)
    elif tag in _RAW:
        assert len(v.v) == _RAW[tag]
        out += v.v
    elif tag in (0x08, 0x14):
        out += struct.pack('<I', len(v.v)) + v.v
    elif tag == 0x1E:
        out += struct.pack('<IB', len(v.v), v.extra) + v.v
    elif tag == 0x09:
        ref: Ref = v.v
        if ref.kind == REF_OBJECT:
            out += struct.pack('<III', ref.kind, ref.index, ref.cls)
        else:
            out += struct.pack('<II', ref.kind, ref.index)
    elif tag == 0x11:
        out += struct.pack('<I', len(v.v))
        for e in v.v:
            write_value(out, e)
    elif tag == 0x12:
        out += struct.pack('<I', len(v.v))
        for k, e in v.v:
            write_value(out, k)
            write_value(out, e)
    elif tag == 0x22:
        write_value(out, v.v[0])
        write_value(out, v.v[1])
    else:
        raise ValueError(f'cannot write tag 0x{tag:02X}')


def _write_strtab(items) -> bytes:
    out = bytearray()
    for b in items:
        out += struct.pack('<I', len(b)) + b
    return bytes(out)


def _write_tree(root: Node | None) -> bytes:
    if root is None:
        return b''
    out = bytearray()

    def emit(nd: Node) -> None:
        start = len(out)
        out.extend(struct.pack('<III', nd.tran, nd.obj, len(nd.children)))
        arr = len(out)
        out.extend(b'\0' * (4 * len(nd.children)))
        for k, ch in enumerate(nd.children):
            struct.pack_into('<I', out, arr + 4 * k, len(out) - arr)
            emit(ch)
        del start

    emit(root)
    return bytes(out)


def encode_sections(nb: NdfBin) -> dict[str, bytes]:
    obje = bytearray()
    for ob in nb.objects:
        obje += struct.pack('<I', ob.cls)
        for pi, val in ob.props:
            obje += struct.pack('<I', pi)
            write_value(obje, val)
        obje += struct.pack('<I', OBJ_END)
    prop = bytearray()
    for name, owner in nb.props:
        prop += struct.pack('<I', len(name)) + name + struct.pack('<I', owner)
    sec = {
        'OBJE': bytes(obje),
        'TOPO': struct.pack(f'<{len(nb.topo)}I', *nb.topo),
        'CHNK': b''.join(struct.pack('<II', *c) for c in nb.chnk),
        'CLAS': _write_strtab(nb.classes),
        'PROP': bytes(prop),
        'STRG': _write_strtab(nb.strings),
        'TRAN': _write_strtab(nb.trans),
        'IMPR': _write_tree(nb.imports),
        'EXPR': _write_tree(nb.exports),
    }
    sec.update(nb.unknown_sections)
    return sec


def encode_image(nb: NdfBin) -> bytes:
    """Rebuild the decompressed image (40-byte header + body incl. TOC0)."""
    sec = encode_sections(nb)
    layout = nb.section_layout or nb.sections
    body = bytearray()
    offs = {}
    pos = nb.header_size
    for s in layout:
        offs[s] = (pos, len(sec[s]))
        body += sec[s]
        pos += len(sec[s])
    footer = pos
    toc = bytearray(b'TOC0' + struct.pack('<I', len(nb.sections)))
    for s in nb.sections:
        o, n = offs[s]
        toc += struct.pack('<8sQQ', s.encode('ascii'), o, n)
    body += toc
    full = nb.header_size + len(body)
    hdr = struct.pack('<4sI4sIQQQ', b'EUG0', nb.version, b'CNDF', nb.mode, footer, nb.header_size, full)
    hdr += b'\0' * (nb.header_size - len(hdr))
    return hdr + bytes(body)


def encode_file(nb: NdfBin, mode: int | None = None, level: int = 19) -> bytes:
    """Encode a complete file.  Compressed bytes will not match Eugen's
    encoder bit for bit, but the decompressed image does."""
    mode = nb.mode if mode is None else mode
    keep = nb.mode
    nb.mode = mode
    try:
        image = encode_image(nb)
    finally:
        nb.mode = keep
    hdr, body = image[:nb.header_size], image[nb.header_size:]
    if mode == MODE_NONE:
        return hdr + body
    if mode == MODE_LZ4:
        stream = lz4_block_store(body)
    elif mode == MODE_ZSTD:
        if _zstd is None:
            raise RuntimeError('zstd needs Python 3.14+')
        stream = _zstd.compress(body, level=level)
    elif mode == MODE_ZLIB:
        stream = zlib.compress(body, 9)
    else:
        raise ValueError(mode)
    return hdr + struct.pack('<I', len(body)) + stream


# --------------------------------------------------------------------------- analysis helpers

def tree_paths(nb: NdfBin, root: Node | None) -> list[tuple[str, int]]:
    """Leaf (and inner) nodes carrying an index -> ('$/A/B', index)."""
    out: list[tuple[str, int]] = []
    if root is None:
        return out

    def walk(nd: Node, prefix: str) -> None:
        name = nb.tname(nd.tran)
        path = name if not prefix else prefix + '/' + name
        if nd.obj != NONE_IDX:
            out.append((path, nd.obj))
        for ch in nd.children:
            walk(ch, path)

    walk(root, '')
    return out


def iter_values(v: Value):
    yield v
    if v.tag == 0x11:
        for e in v.v:
            yield from iter_values(e)
    elif v.tag == 0x12:
        for k, e in v.v:
            yield from iter_values(k)
            yield from iter_values(e)
    elif v.tag == 0x22:
        yield from iter_values(v.v[0])
        yield from iter_values(v.v[1])


def object_refs(ob: Obj):
    for _, val in ob.props:
        for x in iter_values(val):
            if x.tag == 0x09 and x.v.kind == REF_OBJECT:
                yield x.v.index


# --------------------------------------------------------------------------- localisation tokens

# Eugen localisation keys (tag 0x1D values, .dic TRAD keys, Python ``long`` text ids) are
# not hashes in the cryptographic sense: they are a token of up to 10 characters packed
# 6 bits per character, first character most significant.  Verified on every key of the
# SCENARIO_DEFINITION / Dialog dictionaries and on TokenBoutonChoix0='SI_NEXT'.
TOKEN_ALPHABET = ' 0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ_abcdefghijklmnopqrstuvwxyz'


def token_hash(token: str) -> int:
    """'op13_name' -> 14869937622248618 (the integer stored little-endian in 0x1D)."""
    if len(token) > 10:
        raise ValueError('localisation tokens are at most 10 characters')
    h = 0
    for ch in token:
        h = (h << 6) | TOKEN_ALPHABET.index(ch)
    return h


def token_unhash(h: int) -> str | None:
    """Inverse of :func:`token_hash`; None when ``h`` is not a clean packed token."""
    if h <= 0 or h >> 60:
        return None
    out = []
    while h:
        d = h & 63
        if d == 0:
            return None
        out.append(TOKEN_ALPHABET[d])
        h >>= 6
    return ''.join(reversed(out))


def loc_value(token: str) -> Value:
    return Value(0x1D, token_hash(token).to_bytes(8, 'little'))


def as_f32(*xs: float) -> tuple[float, ...]:
    """Each of `xs` as a float32 field (float32, vec3, float2) stores it: rounded to single precision, read back."""
    return struct.unpack(f'<{len(xs)}f', struct.pack(f'<{len(xs)}f', *xs))


# --------------------------------------------------------------------------- text dump

_TAGNAMES = {
    0x00: 'bool', 0x01: 'int8', 0x02: 'int32', 0x03: 'uint32', 0x04: 'uint64', 0x05: 'float32',
    0x06: 'float64', 0x07: 'string', 0x08: 'wstring', 0x09: 'ref', 0x0B: 'vec3', 0x0C: 'color128',
    0x0D: 'color32', 0x0E: 'int3', 0x11: 'list', 0x12: 'maplist', 0x13: 'int64', 0x14: 'blob',
    0x18: 'int16', 0x19: 'uint16', 0x1A: 'guid', 0x1C: 'path', 0x1D: 'loc', 0x1E: 'zipblob',
    0x1F: 'int2', 0x21: 'float2', 0x22: 'pair', 0x25: 'hash16',
}


def fmt_guid(b: bytes) -> str:
    """16 bytes as stored.  The four 8-hex groups are the big-endian int32 words that
    the Python layer passes as GUID1..GUID4 (signed) to UnitGroup/LDPosition/Detecteur."""
    h = b.hex()
    return 'GUID:{' + '-'.join(h[k:k + 8] for k in range(0, 32, 8)) + '}'


def _q(s: str, quote: str = "'") -> str:
    return quote + s.replace('\\', '\\\\').replace(quote, '\\' + quote) + quote


def _float(x: float) -> str:
    r = repr(x)
    # shortest repr that survives a float32 round trip
    for nd in range(1, 10):
        t = f'{x:.{nd}g}'
        if abs(float(t)) > 3.4028234663852886e38:  # rounded past FLT_MAX (e.g. the path caches' FLT_MAX costs)
            continue
        if struct.unpack('<f', struct.pack('<f', float(t)))[0] == x:
            r = repr(float(t))
            break
    if 'e' not in r and '.' not in r and 'n' not in r:
        r += '.0'
    return r


class Dumper:
    def __init__(self, nb: NdfBin, flat: bool = False, typed: bool = False):
        self.nb = nb
        self.flat = flat
        self.typed = typed
        self.exp_name: dict[int, str] = {}
        for path, idx in tree_paths(nb, nb.exports):
            self.exp_name.setdefault(idx, path)
        self.imp_name: dict[int, str] = {}
        for path, idx in tree_paths(nb, nb.imports):
            self.imp_name.setdefault(idx, path)
        self.refcount = [0] * len(nb.objects)
        for ob in nb.objects:
            for t in object_refs(ob):
                if 0 <= t < len(self.refcount):
                    self.refcount[t] += 1
        self.topo = set(nb.topo)
        self.printed: set[int] = set()

    def oname(self, i: int) -> str:
        return self.exp_name.get(i, f'obj_{i}')

    def inline_ok(self, i: int) -> bool:
        return (not self.flat and i not in self.exp_name and self.refcount[i] == 1
                and 0 <= i < len(self.nb.objects))

    def val(self, v: Value, ind: int) -> str:
        nb = self.nb
        t = v.tag
        pre = f'<{_TAGNAMES.get(t, hex(t))}> ' if self.typed and t not in (0x09, 0x11, 0x12, 0x22) else ''
        if t == 0x00:
            s = 'True' if v.v == 1 else ('False' if v.v == 0 else f'bool({v.v})')
        elif t in (0x05, 0x06):
            s = _float(v.v) if t == 0x05 else repr(v.v)
        elif t in (0x0B, 0x21):
            s = '[' + ', '.join(_float(x) for x in v.v) + ']'
        elif t in (0x0E, 0x1F):
            s = '[' + ', '.join(str(x) for x in v.v) + ']'
        elif t == 0x07:
            s = _q(nb.strings[v.v].decode('latin-1')) if v.v < len(nb.strings) else f'<strg#{v.v}>'
        elif t == 0x1C:
            s = _q(nb.strings[v.v].decode('latin-1'), '"') if v.v < len(nb.strings) else f'<strg#{v.v}>'
        elif t == 0x08:
            s = 'w' + _q(v.v.decode('utf-16-le', 'replace'))
        elif t == 0x1A:
            s = fmt_guid(v.v)
        elif t == 0x1D:
            n = int.from_bytes(v.v, 'little')
            tok = token_unhash(n)
            if n == 0:
                s = 'loc:0'
            elif tok is not None:
                s = f"loc'{tok}'"
            else:
                s = f'loc:0x{n:016x}'
        elif t in (0x0C, 0x0D):
            s = 'RGBA[' + ', '.join(str(x) for x in v.v) + ']' if t == 0x0D else 'color128:' + v.v.hex()
        elif t == 0x25:
            s = 'hash16:' + v.v.hex()
        elif t in (0x14, 0x1E):
            s = f'blob[{len(v.v)}]:' + v.v[:64].hex() + ('...' if len(v.v) > 64 else '')
        elif t == 0x09:
            s = self.ref(v.v, ind)
        elif t == 0x11:
            if not v.v:
                return '[]'
            items = [self.val(e, ind + 1) for e in v.v]
            if all('\n' not in x for x in items) and sum(len(x) + 2 for x in items) < 100:
                return '[' + ', '.join(items) + ']'
            pad = '    ' * (ind + 1)
            return '[\n' + ''.join(f'{pad}{x},\n' for x in items) + '    ' * ind + ']'
        elif t in (0x12,):
            if not v.v:
                return 'MAP[]'
            pad = '    ' * (ind + 1)
            return 'MAP[\n' + ''.join(
                f'{pad}({self.val(k, ind + 1)}, {self.val(e, ind + 1)}),\n' for k, e in v.v) + '    ' * ind + ']'
        elif t == 0x22:
            return f'({self.val(v.v[0], ind)}, {self.val(v.v[1], ind)})'
        else:
            s = repr(v.v)
        return pre + s

    def ref(self, r: Ref, ind: int) -> str:
        if r.kind == REF_IMPORT:
            return self.imp_name.get(r.index, f'<import#{r.index}>')
        i = r.index
        if not (0 <= i < len(self.nb.objects)):
            return f'<bad obj ref {i}>'
        if self.inline_ok(i) and i not in self.printed:
            self.printed.add(i)
            return self.obj_body(i, ind, header=False)
        return self.oname(i)

    def obj_body(self, i: int, ind: int, header: bool = True) -> str:
        nb = self.nb
        ob = nb.objects[i]
        pad = '    ' * (ind + 1)
        cname = nb.cname(ob.cls)
        lines = []
        if header:
            tags = []
            if i in self.topo:
                tags.append('topo')
            tags.append(f'#{i}')
            lines.append(f'{self.oname(i)} is {cname}   // {" ".join(tags)}')
            lines.append('    ' * ind + '(')
        else:
            lines.append(f'{cname}   // #{i}')
            lines.append('    ' * ind + '(')
        for pi, v in ob.props:
            lines.append(f'{pad}{nb.pname(pi)} = {self.val(v, ind + 1)}')
        lines.append('    ' * ind + ')')
        return '\n'.join(lines)

    def dump(self, title: str = '', hdr: dict | None = None) -> str:
        nb = self.nb
        out = []
        out.append(f'// {title}')
        if hdr:
            out.append('// header: ' + ', '.join(f'{k}={v}' for k, v in hdr.items()))
        out.append(f'// objects={len(nb.objects)} classes={len(nb.classes)} props={len(nb.props)} '
                   f'strings={len(nb.strings)} trans={len(nb.trans)} topo={len(nb.topo)} chnk={nb.chnk}')
        out.append(f'// sections (TOC order): {" ".join(nb.sections)}')
        imps = tree_paths(nb, nb.imports)
        out.append(f'\n// ---- imports ({len(imps)})')
        for path, idx in sorted(imps, key=lambda x: x[1]):
            out.append(f'// import #{idx} = {path}')
        exps = tree_paths(nb, nb.exports)
        out.append(f'\n// ---- exports ({len(exps)})')
        for path, idx in exps:
            out.append(f'// export {path} -> #{idx} {nb.cname(nb.objects[idx].cls) if idx < len(nb.objects) else "?"}')
        out.append('\n// ---- objects')
        # roots first: objects that cannot be inlined, in index order
        for i in range(len(nb.objects)):
            if i in self.printed or self.inline_ok(i):
                continue
            self.printed.add(i)
            out.append(self.obj_body(i, 0))
            out.append('')
        # anything inline-able but never reached (e.g. dangling or cyclic)
        for i in range(len(nb.objects)):
            if i not in self.printed:
                self.printed.add(i)
                out.append('// (unreached)')
                out.append(self.obj_body(i, 0))
                out.append('')
        return '\n'.join(out) + '\n'


# --------------------------------------------------------------------------- CLI

def cmd_dump(args) -> int:
    nb, hdr, _ = load(args.file)
    text = Dumper(nb, flat=args.flat, typed=args.typed).dump(args.file, hdr)
    if args.output:
        with open(args.output, 'w', encoding='utf-8', newline='\n') as fh:
            fh.write(text)
    else:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stdout.write(text)
    return 0


def cmd_roundtrip(args) -> int:
    bad = 0
    for path in args.files:
        with open(path, 'rb') as fh:
            raw = fh.read()
        hdr, image = decompress(raw)
        nb = parse_image(image, hdr)
        again = encode_image(nb)
        ok = again == image
        # also: full file re-encode, then decode again
        f2 = encode_file(nb)
        h2, im2 = decompress(f2)
        ok2 = im2 == image
        if not (ok and ok2):
            bad += 1
            first = next((k for k in range(min(len(again), len(image))) if again[k] != image[k]), None)
            print(f'FAIL {path}: image_equal={ok} file_reencode_equal={ok2} first_diff={first} '
                  f'len {len(again)} vs {len(image)}')
        else:
            print(f'OK   {path}: mode={hdr["mode"]} image={len(image)} B objects={len(nb.objects)} '
                  f'(compressed {len(raw)} B orig, {len(f2)} B re-encoded)')
    return 1 if bad else 0


def cmd_info(args) -> int:
    nb, hdr, image = load(args.file)
    print(hdr)
    print('sections', nb.sections)
    print('objects', len(nb.objects), 'classes', len(nb.classes), 'props', len(nb.props),
          'strings', len(nb.strings), 'trans', len(nb.trans), 'topo', len(nb.topo), 'chnk', nb.chnk)
    from collections import Counter
    c = Counter(nb.cname(o.cls) for o in nb.objects)
    for k, n in c.most_common():
        print(f'{n:6d} {k}')
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    d = sub.add_parser('dump', help='dump to NDF-like text')
    d.add_argument('file')
    d.add_argument('-o', '--output')
    d.add_argument('--flat', action='store_true', help='never inline single-use objects')
    d.add_argument('--typed', action='store_true', help='prefix scalars with their type tag')
    d.set_defaults(fn=cmd_dump)
    r = sub.add_parser('roundtrip', help='decode -> encode -> compare decompressed image')
    r.add_argument('files', nargs='+')
    r.set_defaults(fn=cmd_roundtrip)
    i = sub.add_parser('info', help='summary and class histogram')
    i.add_argument('file')
    i.set_defaults(fn=cmd_info)
    args = ap.parse_args(argv)
    return args.fn(args)


if __name__ == '__main__':
    sys.exit(main())
