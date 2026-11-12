#!/usr/bin/env python3
"""Read and write Eugen ``TRAD`` localisation dictionaries (WARNO ``.dic``), stdlib only.

Layout (all integers little-endian)::

    0   char[4]  "TRAD"
    4   u32      row count N
    8   N x 16-byte rows: u64 key | u32 text_offset (bytes, absolute) | u32 length (UTF-16 units)
    8+16N        string pool: UTF-16LE texts, no terminator, no padding, no alignment

Invariants verified on all 4,423 ``.dic`` files of a WARNO install (revisions 169425..201602):

* Rows are sorted by key as an **unsigned** u64 (ascending); keys are unique.
* Keys are 6-bit packed tokens (``ndfbin.token_hash``), plus one special row.
* Every file has a **charset row**: key ``0x8000000000000000`` (so always the last row), whose
  text is the set of distinct characters used by the other texts, ordered by the number of
  rows containing the character (descending).  Its text is always the last one in the pool.
  The tie order among equal counts is not reproducible from the data (``build_dic`` breaks ties
  by first appearance, which matches the stock files exactly in ~17% of cases; the
  document-frequency ordering itself holds in 100%).
* The pool is contiguous: each text starts where the previous one ended.  Texts are never
  deduplicated (identical strings are stored twice).  An empty text has length 0 and points at
  the current pool position (i.e. at the next text).  Pool order is the authoring order, not
  the key order, so :func:`read_dic` returns entries in pool order and :func:`write_dic` lays the
  pool out in list order while sorting the rows; that makes ``write_dic(read_dic(x)) == x``.

CLI (run as ``python -m modkit.core.trad ...``)::

    dump <file.dic> [--json]          token (or 0xKEY) TAB text, one row per line in pool order
    build <in.json> <out.dic>         JSON object {token: text} -> .dic (charset row added)
    dump-pack <pack.dat> [glob]       dump every .dic inside an EDat pack (glob on inner path)
"""
from __future__ import annotations

import argparse
import collections
import fnmatch
import json
import struct
import sys

from modkit.core.ndfbin import token_hash, token_unhash

MAGIC = b'TRAD'
CHARSET_KEY = 1 << 63
_HEAD = struct.Struct('<4sI')
_ROW = struct.Struct('<QII')
_ENC = 'utf-16-le'
_ERR = 'surrogatepass'  # keep lone surrogates byte-exact


class TradError(ValueError):
    """Raised when data is not a well-formed TRAD dictionary."""


def read_dic(data: bytes) -> list[tuple[int, str]]:
    """Return ``[(key, text), ...]`` in string-pool order (the order the texts sit in the file).

    Rows are always key-sorted, so the pool order is the only ordering information a file
    carries.  Empty texts are placed before the text that shares their offset.
    """
    if len(data) < _HEAD.size:
        raise TradError('truncated header')
    magic, n = _HEAD.unpack_from(data)
    if magic != MAGIC:
        raise TradError(f'bad magic {magic!r}')
    pool = _HEAD.size + _ROW.size * n
    if pool > len(data):
        raise TradError(f'{n} rows do not fit in {len(data)} bytes')
    rows = [_ROW.unpack_from(data, _HEAD.size + _ROW.size * i) for i in range(n)]
    order = sorted(range(n), key=lambda i: (rows[i][1], rows[i][2] != 0, i))
    out = []
    for i in order:
        key, off, length = rows[i]
        end = off + 2 * length
        if off < pool or end > len(data):
            raise TradError(f'text of key {key:#x} out of range ({off}..{end})')
        out.append((key, data[off:end].decode(_ENC, _ERR)))
    return out


def write_dic(entries) -> bytes:
    """Serialise ``(key, text)`` pairs: rows sorted by unsigned key, pool in the given order.

    Writes exactly what it is given (no charset row is added; see :func:`build_dic`).
    """
    entries = list(entries)
    keys = [k for k, _ in entries]
    if len(set(keys)) != len(keys):
        dup = sorted(k for k, c in collections.Counter(keys).items() if c > 1)
        raise TradError('duplicate keys: ' + ', '.join(_key_name(k) for k in dup[:5]))
    pos = _HEAD.size + _ROW.size * len(entries)
    rows, blobs = [], []
    for key, text in entries:
        if not 0 <= key < 1 << 64:
            raise TradError(f'key {key!r} is not a u64')
        blob = text.encode(_ENC, _ERR)
        rows.append((key, pos, len(blob) // 2))
        blobs.append(blob)
        pos += len(blob)
    rows.sort()
    out = bytearray(_HEAD.pack(MAGIC, len(rows)))
    for row in rows:
        out += _ROW.pack(*row)
    out += b''.join(blobs)
    return bytes(out)


def charset(texts) -> str:
    """Charset-row text for ``texts``: distinct characters, most widely used first.

    Primary order (as in every stock file): number of texts containing the character,
    descending.  Ties: first appearance.
    """
    df: collections.Counter[str] = collections.Counter()
    first: dict[str, int] = {}
    for text in texts:
        for ch in dict.fromkeys(text):
            df[ch] += 1
            first.setdefault(ch, len(first))
    return ''.join(sorted(first, key=lambda ch: (-df[ch], first[ch])))


def token_key(token: str) -> int:
    """Packed key for a human token, rejecting anything that would not decode back to it."""
    try:
        key = token_hash(token)
    except ValueError:
        key = None
    if not token or key is None or token_unhash(key) != token:
        raise TradError(f'{token!r} is not a localisation token (1-10 chars from 0-9 A-Z a-z _)')
    return key


def build_dic(mapping: dict[str, str]) -> bytes:
    """Build a stock-shaped ``.dic`` from ``{token: text}``.

    Rows key-sorted, texts in ``mapping`` order, charset row (key ``0x8000000000000000``) last.
    """
    entries = [(token_key(tok), text) for tok, text in mapping.items()]
    entries.append((CHARSET_KEY, charset(text for _, text in entries)))
    return write_dic(entries)


# --------------------------------------------------------------------------- CLI

def _key_name(key: int) -> str:
    return token_unhash(key) or f'0x{key:016x}'


def _escape(text: str) -> str:
    return (text.replace('\\', '\\\\').replace('\n', '\\n')
            .replace('\r', '\\r').replace('\t', '\\t'))


def _print_entries(entries, as_json: bool) -> None:
    if as_json:
        obj = {_key_name(k): t for k, t in entries if k != CHARSET_KEY}
        print(json.dumps(obj, ensure_ascii=False, indent=2))
        return
    for key, text in entries:
        print(f'{_key_name(key)}\t{_escape(text)}')


def cmd_dump(args) -> int:
    with open(args.dic, 'rb') as fh:
        _print_entries(read_dic(fh.read()), args.json)
    return 0


def cmd_build(args) -> int:
    with open(args.json_in, encoding='utf-8-sig') as fh:  # tolerate a BOM (PowerShell 5.1)
        mapping = json.load(fh)
    if not isinstance(mapping, dict) or not all(isinstance(v, str) for v in mapping.values()):
        raise TradError('input must be a JSON object of token -> string')
    data = build_dic(mapping)
    with open(args.dic_out, 'wb') as fh:
        fh.write(data)
    print(f'# wrote {args.dic_out}: {len(mapping)} entries + charset, {len(data)} bytes',
          file=sys.stderr)
    return 0


def cmd_dump_pack(args) -> int:
    from modkit.core import edat  # lazy: only this command needs the archive reader
    pat = args.glob.lower()
    hits = [e for e in edat.read_index(args.pack)
            if e.path.lower().endswith('.dic') and fnmatch.fnmatchcase(e.path.lower(), pat)]
    for e in hits:
        entries = read_dic(edat.read_entry(args.pack, e))
        print(f'== {e.path}  ({len(entries)} rows, {e.size} bytes)')
        _print_entries(entries, False)
    print(f'# {len(hits)} .dic files', file=sys.stderr)
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding='utf-8', errors='backslashreplace')
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    sub = ap.add_subparsers(dest='cmd', required=True)
    p = sub.add_parser('dump', help='print rows of a .dic in pool order')
    p.add_argument('dic')
    p.add_argument('--json', action='store_true', help='JSON {token: text} (charset row omitted)')
    p.set_defaults(func=cmd_dump)
    p = sub.add_parser('build', help='build a .dic from a JSON object token -> text')
    p.add_argument('json_in')
    p.add_argument('dic_out')
    p.set_defaults(func=cmd_build)
    p = sub.add_parser('dump-pack', help='dump .dic files straight from an EDat pack')
    p.add_argument('pack')
    p.add_argument('glob', nargs='?', default='*', help='fnmatch on inner path, case-insensitive')
    p.set_defaults(func=cmd_dump_pack)
    args = ap.parse_args(argv)
    try:
        return args.func(args)
    except TradError as exc:
        print(f'error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    sys.exit(main())
