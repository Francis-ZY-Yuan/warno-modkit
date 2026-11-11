"""Unwrap and decompile WARNO's XYZ0 Python modules (compiled Python 2.5).

WARNO ships its level-design Python layer (mission scripts `effetmap.xyz` and
the `leveldesign*` library) as XYZ0 envelopes around compressed Python 2.5
marshal code objects. Layout (offsets in bytes):

     0  char[4]  "XYZ0"
     4  u8[4]    0a 0d f2 b3  = the Python 2.5 pyc magic (62131), byte-reversed
     8  ...      20 header bytes whose meaning depends on the codec:
                   zlib era (<= rev 193438): u32 BE raw size @8, 16 opaque bytes @12
                   zstd era (>= rev 197351): 16 opaque bytes @8, u32 LE raw size @24
    28  ...      compressed stream: zstd if it starts 28 b5 2f fd, else zlib

The decompressed bytes are a bare marshal stream (a module code object, `c`).
Prefixing the 2.5 magic `b3 f2 0d 0a` and a zero timestamp makes a valid .pyc.

Decompilation uses uncompyle6 + xdis from the project venv. The decompiled
code is game data: this tool never imports or executes it.

CLI (run with `python -m modkit.core.xyz ...`):
  unwrap    <xyz> <pyc>             write a Python 2.5 .pyc
  decompile <xyz-or-dir> <out>      decompile one file or a whole tree
      file: <out> is the target .py, or a directory to receive <stem>.py
      dir:  every *.xyz below it, written to <out>/<relative path>.py
  Prints one TSV status line per module (ok / partial / failed) and a summary.
"""
from __future__ import annotations

import argparse
import io
import os
import struct
import sys
import zlib
from compression import zstd

MAGIC = b"XYZ0" + bytes.fromhex("0a0df2b3")
PYC25_HEADER = bytes.fromhex("b3f20d0a") + b"\0\0\0\0"  # magic 62131 + zero timestamp
ZSTD_FRAME = bytes.fromhex("28b52ffd")
BODY_OFFSET = 28

# uncompyle6 writes these markers into the output when a code object fails.
_FAIL_MARKERS = ("--- This code section failed: ---", "Parse error at or near", "# Deparsing stopped due to parse error")


class XyzError(ValueError):
    """Raised for a file that is not a well-formed XYZ0 module."""


def unwrap(raw: bytes) -> tuple[bytes, str]:
    """Return (marshal bytes, codec name) for one XYZ0 file's contents."""
    if raw[:8] != MAGIC:
        raise XyzError(f"bad magic {raw[:8].hex()}")
    body = raw[BODY_OFFSET:]
    if body[:4] == ZSTD_FRAME:
        codec, data = "zstd", zstd.decompress(body)
        declared = struct.unpack_from("<I", raw, 24)[0]
    else:
        codec, data = "zlib", zlib.decompress(body)
        declared = struct.unpack_from(">I", raw, 8)[0]
    if len(data) != declared:
        raise XyzError(f"{codec}: declared {declared} bytes, got {len(data)}")
    if data[:1] != b"c":
        raise XyzError(f"payload is not a marshal code object (first byte {data[:1]!r})")
    return data, codec


def to_pyc(marshal_data: bytes) -> bytes:
    """Wrap a Python 2.5 marshal code object as a .pyc file."""
    return PYC25_HEADER + marshal_data


def decompile_pyc(pyc: bytes, out: io.TextIOBase) -> str:
    """Decompile .pyc bytes into `out`. Returns 'ok', 'partial' or raises."""
    from uncompyle6.main import decompile  # venv package; imported lazily
    from xdis.load import load_module_from_file_object

    version, timestamp, magic_int, co, is_pypy, source_size, _ = load_module_from_file_object(io.BytesIO(pyc), "<xyz>")
    buf = io.StringIO()
    decompile(co, bytecode_version=version, out=buf, timestamp=timestamp, magic_int=magic_int,
              is_pypy=is_pypy, source_size=source_size)
    text = buf.getvalue()
    out.write(text)
    return "partial" if any(m in text for m in _FAIL_MARKERS) else "ok"


def _write_text(path: str, text: str) -> None:
    os.makedirs(os.path.dirname(os.path.abspath(path)) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(text)


def decompile_file(src: str, dst: str) -> tuple[str, str]:
    """Decompile one .xyz to dst (.py). Returns (status, detail).

    On failure the .py still gets written, holding whatever uncompyle6 managed
    plus the error, so a reader can see where it stopped.
    """
    with open(src, "rb") as fh:
        raw = fh.read()
    try:
        data, codec = unwrap(raw)
    except (XyzError, zlib.error, zstd.ZstdError) as exc:
        return "failed", f"unwrap: {exc}"
    out = io.StringIO()
    try:
        status = decompile_pyc(to_pyc(data), out)
        detail = codec
    except Exception as exc:  # uncompyle6 raises many types (ParserError, IndexError, ...)
        status, detail = "failed", f"{type(exc).__name__}: {str(exc).splitlines()[0][:200] if str(exc) else ''}"
        out.write(f"\n# xyz.py: decompilation failed: {detail}\n")
    _write_text(dst, out.getvalue())
    return status, detail


def iter_xyz(root: str):
    """Yield every *.xyz path below root, sorted."""
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            if name.lower().endswith(".xyz"):
                yield os.path.join(dirpath, name)


def cmd_decompile(src: str, out: str) -> int:
    if os.path.isdir(src):
        jobs = [(p, os.path.join(out, os.path.splitext(os.path.relpath(p, src))[0] + ".py")) for p in iter_xyz(src)]
    elif out.lower().endswith(".py"):
        jobs = [(src, out)]
    else:
        jobs = [(src, os.path.join(out, os.path.splitext(os.path.basename(src))[0] + ".py"))]
    counts: dict[str, int] = {}
    for xyz, py in jobs:
        status, detail = decompile_file(xyz, py)
        counts[status] = counts.get(status, 0) + 1
        print(f"{status}\t{xyz}\t{py}\t{detail}", flush=True)
    summary = ", ".join(f"{k} {v}" for k, v in sorted(counts.items()))
    print(f"# {len(jobs)} modules: {summary or 'none found'}", file=sys.stderr)
    return 0 if counts.get("failed", 0) == 0 else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("unwrap", help="XYZ0 -> Python 2.5 .pyc")
    p.add_argument("xyz")
    p.add_argument("pyc")
    p = sub.add_parser("decompile", help="XYZ0 file or tree -> .py source")
    p.add_argument("src", help="an .xyz file or a directory searched recursively")
    p.add_argument("out", help="target .py (file mode) or output directory")
    args = ap.parse_args(argv)
    sys.setrecursionlimit(max(sys.getrecursionlimit(), 20000))  # deep keyword-call nesting in mission scripts

    if args.cmd == "unwrap":
        with open(args.xyz, "rb") as fh:
            data, codec = unwrap(fh.read())
        os.makedirs(os.path.dirname(os.path.abspath(args.pyc)), exist_ok=True)
        with open(args.pyc, "wb") as fh:
            fh.write(to_pyc(data))
        print(f"{codec}: {len(data)} marshal bytes -> {args.pyc}")
        return 0
    return cmd_decompile(args.src, args.out)


if __name__ == "__main__":
    sys.exit(main())
