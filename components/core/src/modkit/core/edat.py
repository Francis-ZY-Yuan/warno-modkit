"""Read and write Eugen Systems "edat" archives (the .dat files under WARNO/Data/PC).

Stdlib only. Two on-disk variants exist in a current WARNO install:

* version 2: every archive up to revision 197351 (also the Wargame/SD2 format)
* version 3: every archive shipped with revision 201602

Both share the same path-trie dictionary; they differ in the header and
in the checksum algorithms. Layout summary (all integers little-endian):

  v2 header (65 bytes, packed)        v3 header (36 bytes)
    0  char[4] magic "edat"             0  char[4] magic "edat"
    4  u32     version = 2              4  u32     version = 3
    8  u8[16]  checksum_v1 (zeros)      8  u32     dict_offset
   24  u8      skip                    12  u32     dict_length
   25  u32     dict_offset             16  u64     data_offset
   29  u32     dict_length             24  u64     data_length
   33  u32     data_offset             32  u32     CRC32 of dictionary
   37  u32     data_length
   41  u32     unknown
   45  u32     padding (alignment, 8192)
   49  u8[16]  MD5 of dictionary

  Dictionary = a trie of nodes, starting with a root dir node at dict_offset:
    dir  node: u32 node_len (>0) | u32 next | char name[] NUL
    file node: u32 0             | u32 next | u64 offset | u64 size
               | u8[16] checksum | char name[] NUL
  `name` is a path *fragment*; a file's full path is the concatenation of
  the fragments of its ancestor dirs plus its own name. `next` is the byte
  distance from this node to its next sibling (0 = last sibling). A dir's
  children start at node_start + node_len. A file's payload starts at
  data_offset + offset. Per-file checksum: v2 = MD5, v3 = CRC32 stored in the
  first 4 bytes (rest zero). v2 paths use backslashes; we normalise to "/".

Writer (v3 only; `repack` of stock v3 archives is byte-identical). Stock
layout rules, all reproduced by `write_edat`:
  * files are sorted by the raw bytes of their inner path (case-sensitive);
  * the trie is a byte-level radix trie: siblings are grouped by first byte, a
    lone member becomes a file node holding its whole remaining suffix, a group
    of 2+ becomes a dir node named by the group's longest common prefix;
  * the root is a dir node with an empty name; an empty archive has no
    dictionary at all (dict_length 0, CRC 0);
  * header zero-padded to 256 (= dict_offset); data_offset = dictionary end
    rounded up to 8192; each payload starts 8192-aligned (relative offsets
    in sorted order) and is zero-padded to 8192, so the file size is
    data_offset + data_length.

CLI (run with `python -m modkit.core.edat ...`):
  list    <dat> [--glob P]                       inner paths with sizes
  extract <dat> <outdir> [--glob P] [--exclude P ...] [--verify]
  scan    <data_pc_root> <out_tsv>               index every .dat (dictionaries only)
  pack    <srcdir> <out.dat>                     every file under srcdir -> v3 archive
  repack  <in.dat> <out.dat>                     read all entries, write a v3 archive
"""
from __future__ import annotations

import argparse
import fnmatch
import hashlib
import os
import struct
import sys
import zlib
from collections.abc import Callable, Iterable
from dataclasses import dataclass

MAGIC = b"edat"
_V2_HEADER = struct.Struct("<4sI16sBIIIIII16s")  # 65 bytes
_V3_HEADER = struct.Struct("<4sIIIQQI")  # 36 bytes
_NODE_HEAD = struct.Struct("<II")  # (node_len or 0, next)
_FILE_BODY = struct.Struct("<QQ16s")  # (offset, size, checksum)
_CHUNK = 1 << 20
SECTOR = 8192  # payload alignment and data_offset granularity
V3_DICT_OFFSET = 256  # the 36-byte v3 header is zero-padded up to here


class EdatError(ValueError):
    """Raised when a file is not a readable edat archive."""


@dataclass(frozen=True)
class Header:
    """Archive header. `dict_checksum` is MD5 (v2) or CRC32 LE u32 (v3)."""

    version: int
    dict_offset: int
    dict_length: int
    data_offset: int
    data_length: int
    dict_checksum: bytes


@dataclass(frozen=True)
class Entry:
    """One stored file. `offset` is absolute within the .dat file."""

    path: str
    offset: int
    size: int
    checksum: bytes
    version: int


def read_header(fh) -> Header:
    """Parse the header from an open binary file positioned anywhere."""
    fh.seek(0)
    raw = fh.read(_V2_HEADER.size)
    if len(raw) < 8 or raw[:4] != MAGIC:
        raise EdatError(f"bad magic {raw[:4]!r}")
    version = struct.unpack_from("<I", raw, 4)[0]
    if version == 2:
        _, _, _, _, d_off, d_len, f_off, f_len, _, _, md5 = _V2_HEADER.unpack(raw)
        return Header(2, d_off, d_len, f_off, f_len, md5)
    if version == 3:
        _, _, d_off, d_len, f_off, f_len, crc = _V3_HEADER.unpack_from(raw)
        return Header(3, d_off, d_len, f_off, f_len, struct.pack("<I", crc))
    raise EdatError(f"unsupported edat version {version}")


def _cstr(buf: bytes, pos: int) -> tuple[str, int]:
    """Read a NUL-terminated name at `pos`; return (text, position after NUL)."""
    end = buf.index(b"\0", pos)
    raw = buf[pos:end]
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    return text, end + 1


def parse_dictionary(buf: bytes, header: Header) -> list[Entry]:
    """Walk the path trie in `buf` (the raw dictionary) and return its files."""
    entries: list[Entry] = []
    if not buf:  # dict_length 0: an empty archive (common no-change patch stub)
        return entries
    stack: list[tuple[int, str]] = [(0, "")]  # (node position, parent path)
    while stack:
        pos, parent = stack.pop()
        if not 0 <= pos <= len(buf) - _NODE_HEAD.size:
            raise EdatError(f"dictionary node out of range at {pos}")
        node_len, nxt = _NODE_HEAD.unpack_from(buf, pos)
        if nxt:  # sibling shares our parent; push it first so children come out first
            stack.append((pos + nxt, parent))
        if node_len == 0:  # file node
            rel, size, checksum = _FILE_BODY.unpack_from(buf, pos + _NODE_HEAD.size)
            name, _ = _cstr(buf, pos + _NODE_HEAD.size + _FILE_BODY.size)
            path = (parent + name).replace("\\", "/")
            entries.append(Entry(path, header.data_offset + rel, size, checksum, header.version))
        else:  # dir node: name fragment, children follow the node header
            name, _ = _cstr(buf, pos + _NODE_HEAD.size)
            stack.append((pos + node_len, parent + name))
    return entries


def read_index(dat_path: str) -> list[Entry]:
    """Return every file entry of an edat archive (reads header + dictionary only)."""
    with open(dat_path, "rb") as fh:
        header = read_header(fh)
        fh.seek(header.dict_offset)
        buf = fh.read(header.dict_length)
    if len(buf) != header.dict_length:
        raise EdatError("truncated dictionary")
    return parse_dictionary(buf, header)


def iter_entry_chunks(dat_path: str, entry: Entry, chunk: int = _CHUNK):
    """Yield the payload of `entry` in chunks (for large files)."""
    with open(dat_path, "rb") as fh:
        fh.seek(entry.offset)
        left = entry.size
        while left:
            data = fh.read(min(chunk, left))
            if not data:
                raise EdatError(f"truncated payload for {entry.path}")
            left -= len(data)
            yield data


def read_entry(dat_path: str, entry: Entry) -> bytes:
    """Return the full payload of `entry`."""
    return b"".join(iter_entry_chunks(dat_path, entry))


class _Checker:
    """Incremental per-file checksum matching the archive version."""

    def __init__(self, entry: Entry):
        self.entry = entry
        self.md5 = hashlib.md5() if entry.version == 2 else None
        self.crc = 0

    def update(self, data: bytes) -> None:
        if self.md5 is not None:
            self.md5.update(data)
        else:
            self.crc = zlib.crc32(data, self.crc)

    def ok(self) -> bool:
        if self.md5 is not None:
            return self.md5.digest() == self.entry.checksum
        return struct.pack("<I", self.crc) == self.entry.checksum[:4]


def verify_entry(dat_path: str, entry: Entry) -> bool:
    """True if the payload matches the stored per-file checksum."""
    check = _Checker(entry)
    for data in iter_entry_chunks(dat_path, entry):
        check.update(data)
    return check.ok()


def _safe_join(outdir: str, inner: str) -> str:
    """Join an inner path under `outdir`, refusing absolute or '..' paths."""
    parts = [p for p in inner.split("/") if p not in ("", ".")]
    if not parts or ".." in parts or ":" in parts[0]:
        raise EdatError(f"unsafe inner path {inner!r}")
    return os.path.join(outdir, *parts)


def _matches(path: str, globs: list[str] | None, excludes: list[str] | None) -> bool:
    low = path.lower()
    if globs and not any(fnmatch.fnmatchcase(low, g.lower()) for g in globs):
        return False
    return not (excludes and any(fnmatch.fnmatchcase(low, x.lower()) for x in excludes))


def extract_entry(dat_path: str, entry: Entry, outdir: str, verify: bool = False) -> tuple[str, bool | None]:
    """Write one entry to outdir/<inner path>; return (path, checksum ok or None).

    On Windows the path is given the \\\\?\\ prefix: some inner paths are long
    enough (190+ chars) to exceed MAX_PATH once joined to an output folder.
    """
    target = _safe_join(outdir, entry.path)
    if os.name == "nt" and not target.startswith("\\\\?\\"):
        target = "\\\\?\\" + os.path.abspath(target)
    os.makedirs(os.path.dirname(target), exist_ok=True)
    check = _Checker(entry) if verify else None
    with open(target, "wb") as out:
        for data in iter_entry_chunks(dat_path, entry):
            out.write(data)
            if check:
                check.update(data)
    return target, (check.ok() if check else None)


def extract(dat_path: str, outdir: str, globs=None, excludes=None, verify=False) -> list[tuple[Entry, str, bool | None]]:
    """Extract matching entries under `outdir`, keeping inner paths.

    Returns (entry, written path, checksum ok or None if not verified).
    """
    done = []
    for entry in read_index(dat_path):
        if _matches(entry.path, globs, excludes):
            done.append((entry, *extract_entry(dat_path, entry, outdir, verify)))
    return done


def revision_of(relpath: str) -> str:
    """Revision an archive belongs to: the innermost all-digit folder in its path."""
    revs = [p for p in relpath.replace("\\", "/").split("/")[:-1] if p.isdigit()]
    return revs[-1] if revs else ""


def scan(root: str, out_tsv: str) -> tuple[int, int, int, list[str]]:
    """Index every .dat under `root` into a TSV.

    Returns (archives read, empty archives, entries, errors). Empty archives
    produce no rows.
    """
    n_dat = n_empty = n_ent = 0
    errors: list[str] = []
    dats = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        dats += [os.path.join(dirpath, f) for f in sorted(filenames) if f.lower().endswith(".dat")]
    with open(out_tsv, "w", encoding="utf-8", newline="\n") as out:
        out.write("revision\tdat_relpath\tinner_path\tsize\n")
        for dat in dats:
            rel = os.path.relpath(dat, root).replace(os.sep, "/")
            try:
                entries = read_index(dat)
            except (EdatError, OSError, struct.error) as exc:
                errors.append(f"{rel}: {exc}")
                continue
            rev = revision_of(rel)
            n_dat += 1
            n_empty += not entries
            for e in entries:
                out.write(f"{rev}\t{rel}\t{e.path}\t{e.size}\n")
            n_ent += len(entries)
    return n_dat, n_empty, n_ent, errors


# --------------------------------------------------------------------------- writer

ChunkSource = Callable[[], Iterable[bytes]]  # called once; yields the payload


def _align(n: int, a: int = SECTOR) -> int:
    return -(-n // a) * a


def _encode_path(path: str) -> bytes:
    """Inner path as stored in v3: '/' separators, UTF-8 (stock names are all ASCII)."""
    raw = path.replace("\\", "/").encode("utf-8")
    if not raw or b"\0" in raw:
        raise EdatError(f"bad inner path {path!r}")
    return raw


def _encode_group(group: list[tuple[bytes, bytes]]) -> bytes:
    """One trie node (with `next` = 0) for sibling suffixes sharing a first byte."""
    if len(group) == 1:
        name, body = group[0]
        return _NODE_HEAD.pack(0, 0) + body + name + b"\0"
    prefix = os.path.commonprefix([name for name, _ in group])
    children = _encode_siblings([(name[len(prefix):], body) for name, body in group])
    return _NODE_HEAD.pack(_NODE_HEAD.size + len(prefix) + 1, 0) + prefix + b"\0" + children


def _encode_siblings(group: list[tuple[bytes, bytes]]) -> bytes:
    """Encode sorted (suffix, file body) pairs as a run of sibling nodes.

    Each node's `next` is its encoded length (subtree included), 0 on the last.
    An empty suffix (a path that is a prefix of another) stands alone; it sorts
    first, so it becomes a file node with an empty name. Stock archives never
    contain one.
    """
    nodes: list[bytes] = []
    i = 0
    while i < len(group):
        first, j = group[i][0][:1], i + 1
        while first and j < len(group) and group[j][0][:1] == first:
            j += 1
        nodes.append(_encode_group(group[i:j]))
        i = j
    out = bytearray()
    for k, node in enumerate(nodes):
        nxt = len(node) if k + 1 < len(nodes) else 0
        out += node[:4] + struct.pack("<I", nxt) + node[8:]
    return bytes(out)


def build_dictionary(records: list[tuple[bytes, bytes]]) -> bytes:
    """Dictionary for (inner path, 32-byte file body) records sorted by path.

    The file body is `_FILE_BODY.pack(relative offset, size, checksum)`.
    The dictionary's length depends only on the paths.
    """
    if not records:
        return b""
    return _NODE_HEAD.pack(_NODE_HEAD.size + 1, 0) + b"\0" + _encode_siblings(records)


def v3_header(dictionary: bytes, data_offset: int, data_length: int) -> bytes:
    """The 36-byte v3 header, zero-padded to dict_offset (256)."""
    head = _V3_HEADER.pack(MAGIC, 3, V3_DICT_OFFSET, len(dictionary),
                           data_offset, data_length, zlib.crc32(dictionary))
    return head.ljust(V3_DICT_OFFSET, b"\0")


def write_edat_stream(out_path: str, files: list[tuple[str, int, ChunkSource]], version: int = 3) -> None:
    """Write a v3 archive from (inner path, size, chunk source) triples.

    Payloads are streamed once: the data section is written first (CRC32
    computed on the fly), then the header and dictionary are written over the
    zeroed space in front of it. Input order does not matter.
    """
    if version != 3:
        raise EdatError(f"writing edat version {version} is not implemented (v3 only)")
    items = sorted(((_encode_path(p), size, src) for p, size, src in files), key=lambda t: t[0])
    for a, b in zip(items, items[1:]):
        if a[0] == b[0]:
            raise EdatError(f"duplicate inner path {a[0].decode('utf-8')!r}")
    blank = _FILE_BODY.pack(0, 0, b"")
    dict_len = len(build_dictionary([(name, blank) for name, _, _ in items]))
    data_offset = _align(V3_DICT_OFFSET + dict_len)
    records: list[tuple[bytes, bytes]] = []
    with open(out_path, "wb") as out:
        out.write(b"\0" * data_offset)
        rel = 0
        for name, size, src in items:
            crc = done = 0
            for chunk in src():
                out.write(chunk)
                crc = zlib.crc32(chunk, crc)
                done += len(chunk)
            if done != size:
                raise EdatError(f"{name.decode('utf-8')}: expected {size} bytes, got {done}")
            out.write(b"\0" * (_align(size) - size))
            records.append((name, _FILE_BODY.pack(rel, size, struct.pack("<I", crc))))
            rel += _align(size)
        dictionary = build_dictionary(records)
        assert len(dictionary) == dict_len
        out.seek(0)
        out.write(v3_header(dictionary, data_offset, rel) + dictionary)


def write_edat(out_path: str, files: list[tuple[str, bytes]], version: int = 3) -> None:
    """Write a v3 archive from in-memory (inner path with '/', payload) pairs."""
    write_edat_stream(out_path, [(p, len(b), lambda b=b: (b,)) for p, b in files], version)


def _iter_file(path: str, chunk: int = _CHUNK):
    with open(path, "rb") as fh:
        while data := fh.read(chunk):
            yield data


def pack(srcdir: str, out_path: str) -> int:
    """Pack every file under `srcdir` (inner path = relative path with '/').

    Returns the entry count.
    """
    root = os.path.abspath(srcdir)
    out_norm = os.path.normcase(os.path.abspath(out_path))
    if out_norm.startswith(os.path.normcase(root).rstrip(os.sep) + os.sep):
        raise EdatError("pack output must not be inside the source directory")
    if os.name == "nt" and not root.startswith("\\\\?\\"):
        root = "\\\\?\\" + root  # long inner paths, as in extract_entry
    files: list[tuple[str, int, ChunkSource]] = []
    for dirpath, _, filenames in os.walk(root):
        for f in filenames:
            full = os.path.join(dirpath, f)
            inner = os.path.relpath(full, root).replace(os.sep, "/")
            files.append((inner, os.path.getsize(full), lambda full=full: _iter_file(full)))
    write_edat_stream(out_path, files)
    return len(files)


def repack(in_path: str, out_path: str) -> int:
    """Read every entry of `in_path` and write them to a v3 archive at `out_path`.

    Returns the entry count.
    """
    if os.path.exists(out_path) and os.path.samefile(in_path, out_path):
        raise EdatError("repack output would overwrite its input")
    entries = read_index(in_path)
    write_edat_stream(out_path, [(e.path, e.size, lambda e=e: iter_entry_chunks(in_path, e))
                                 for e in entries])
    return len(entries)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("list", help="print inner paths with sizes")
    p.add_argument("dat")
    p.add_argument("--glob", action="append", help="fnmatch pattern on inner path (case-insensitive)")
    p = sub.add_parser("extract", help="extract entries keeping inner paths")
    p.add_argument("dat")
    p.add_argument("outdir")
    p.add_argument("--glob", action="append", help="only paths matching (repeatable)")
    p.add_argument("--exclude", action="append", help="skip paths matching (repeatable)")
    p.add_argument("--verify", action="store_true", help="check per-file checksums")
    p = sub.add_parser("scan", help="index all .dat dictionaries under a Data/PC root")
    p.add_argument("root")
    p.add_argument("out_tsv")
    p = sub.add_parser("pack", help="pack every file under a directory into a v3 archive")
    p.add_argument("srcdir")
    p.add_argument("out")
    p = sub.add_parser("repack", help="rewrite all entries of an archive as v3")
    p.add_argument("dat")
    p.add_argument("out")
    args = ap.parse_args(argv)

    if args.cmd == "list":
        entries = [e for e in read_index(args.dat) if _matches(e.path, args.glob, None)]
        for e in entries:
            print(f"{e.size:>12}  {e.path}")
        print(f"# {len(entries)} entries, {sum(e.size for e in entries)} bytes", file=sys.stderr)
    elif args.cmd == "extract":
        done = extract(args.dat, args.outdir, args.glob, args.exclude, args.verify)
        bad = [d for d in done if d[2] is False]
        for e, _, ok in bad:
            print(f"CHECKSUM MISMATCH {e.path}", file=sys.stderr)
        print(f"# extracted {len(done)} entries, {sum(d[0].size for d in done)} bytes"
              + (f", {len(bad)} checksum mismatches" if args.verify else ""), file=sys.stderr)
        return 1 if bad else 0
    elif args.cmd == "scan":
        n_dat, n_empty, n_ent, errors = scan(args.root, args.out_tsv)
        for err in errors:
            print(f"ERROR {err}", file=sys.stderr)
        print(f"# indexed {n_dat} archives ({n_empty} empty), {n_ent} entries, "
              f"{len(errors)} errors", file=sys.stderr)
        return 1 if errors else 0
    elif args.cmd in ("pack", "repack"):
        n = pack(args.srcdir, args.out) if args.cmd == "pack" else repack(args.dat, args.out)
        print(f"# wrote {args.out}: {n} entries, {os.path.getsize(args.out)} bytes (edat v3)",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
