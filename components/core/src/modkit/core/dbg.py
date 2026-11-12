#!/usr/bin/env python3
"""Read and write Eugen ``.dbg`` source maps (WARNO build 210942 and later), stdlib only.

Since build 210942 every datapack transaction ``<name>.txn`` (scenarios, maps, decor sets) ships beside a
``<name>.dbg``: a debug source map of the transaction's objects. Layout::

    0   u32      size of the text, decompressed (little-endian)
    4   a zstd frame holding the text

The text is one line per object of the ``.txn``'s OBJE table, in object order, each ending in ``\\n``::

    <name>;<source file>;<line>;<column>

``<name>`` is the object's name in its NDF source (the last component of its export path for an exported object), or
empty for an unnamed one; ``<source file>`` is a game path (``ScenariosData:/<scenario>/Scripting/Dialog.ndf``).

Invariants verified on all 167 ``.dbg`` files of a 210942 extraction (scenario, map and decor-set packs): the prefix
equals the decompressed size, the text ends in a newline, every line has those four fields, and the line count equals
the object count of the ``.txn`` beside it. The game's own transactions (``Transactions.dat``) ship ``.txn`` and
``.txn.tag`` without a ``.dbg``.

CLI (run as ``python -m modkit.core.dbg ...``)::

    dump <file.dbg>                   the text, one line per object
"""
from __future__ import annotations

import argparse
import struct
import sys
from typing import NamedTuple, Sequence

try:  # Python 3.14+
    from compression import zstd as _zstd
except ImportError:  # pragma: no cover
    _zstd = None

_SIZE = struct.Struct("<I")
_ENC = "latin-1"  # byte-exact for any text; stock's is ASCII


class DbgError(ValueError):
    """Raised when data is not a well-formed .dbg source map."""


class Line(NamedTuple):
    """One object's source location."""
    name: str
    source: str
    line: int
    column: int


def _need_zstd() -> None:
    if _zstd is None:  # pragma: no cover
        raise DbgError("a .dbg is zstd-compressed: Python 3.14 or newer is needed (compression.zstd)")


def read_text(data: bytes) -> str:
    """The text of a .dbg: the size prefix checked against the decompressed frame."""
    _need_zstd()
    if len(data) < _SIZE.size:
        raise DbgError(f"{len(data)} bytes: too short for a .dbg")
    (size,) = _SIZE.unpack_from(data)
    try:
        body = _zstd.decompress(data[_SIZE.size:])
    except Exception as exc:  # compression.zstd raises its own error type
        raise DbgError(f"the zstd frame does not decompress: {exc}") from None
    if len(body) != size:
        raise DbgError(f"size prefix {size}, but the frame holds {len(body)} bytes")
    return body.decode(_ENC)


def read(data: bytes) -> list[Line]:
    """The lines of a .dbg, one per object, in object order."""
    text = read_text(data)
    if text and not text.endswith("\n"):
        raise DbgError("the text does not end in a newline")
    out = []
    for k, row in enumerate(text.split("\n")[:-1]):
        parts = row.split(";")
        if len(parts) != 4:
            raise DbgError(f"line {k + 1} has {len(parts)} fields, not 4: {row!r}")
        name, source, line, column = parts
        try:
            out.append(Line(name, source, int(line), int(column)))
        except ValueError:
            raise DbgError(f"line {k + 1}: line and column must be integers: {row!r}") from None
    return out


def write_text(text: str, level: int = 19) -> bytes:
    """A .dbg holding `text` as stock lays it out: the size prefix, then one zstd frame (content size, no checksum)."""
    _need_zstd()
    body = text.encode(_ENC)
    return _SIZE.pack(len(body)) + _zstd.compress(body, level)


def write(lines: Sequence[Line], level: int = 19) -> bytes:
    """A .dbg of `lines` (one per object, in object order)."""
    for ln in lines:
        if ";" in ln.name or ";" in ln.source or "\n" in ln.name + ln.source:
            raise DbgError(f"a name or source holds ';' or a newline: {ln}")
    return write_text("".join(f"{ln.name};{ln.source};{ln.line};{ln.column}\n" for ln in lines), level)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m modkit.core.dbg", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("dump", help="print the text, one line per object")
    p.add_argument("path")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    with open(args.path, "rb") as fh:
        sys.stdout.write(read_text(fh.read()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
