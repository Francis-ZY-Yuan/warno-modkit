"""File helpers for builds: long-path reads, streamed digests, provenance strings, sorted walks."""
from __future__ import annotations

import hashlib
import os
from typing import Iterable

from modkit.core import paths


def long_path(path: str) -> str:
    """Absolute path usable beyond MAX_PATH on Windows (some voice file names are ~95 chars)."""
    path = os.path.abspath(path)
    return "\\\\?\\" + path if os.name == "nt" and not path.startswith("\\\\?\\") else path


# What fetches a declared stock file an extraction lacks (one made before a component declared it, say).
SETUP_FIX = ("run python -m modkit.core.setup check, then python -m modkit.core.setup extract (the warno-setup "
             "skill)")


def _missing(path: str, exc: FileNotFoundError) -> FileNotFoundError:
    """The error for a file `path` that is not there: under the extraction, one line naming the stock file by its
    provenance (extracted/...) and the setup commands that fetch it; anywhere else, the OS error as it was."""
    where = paths.rel_source(path)
    if not where.startswith("extracted/"):
        return exc
    return FileNotFoundError(f"missing stock file {where}: the extraction lacks it; {SETUP_FIX}")


def _open(path: str):
    try:
        return open(long_path(path), "rb")
    except FileNotFoundError as exc:
        raise _missing(path, exc) from None


def read_file(path: str) -> bytes:
    """The bytes of `path`. A stock file missing from the extraction raises FileNotFoundError naming the fix."""
    with _open(path) as fh:
        return fh.read()


def rel_source(src_dir: str, inner: str) -> str:
    """'extracted/'-relative, '/'-separated provenance of an input file (see modkit.core.paths.rel_source)."""
    return paths.rel_source(src_dir) + "/" + inner


def walk_files(root: str, sub: str) -> list[str]:
    base = long_path(root)
    out = []
    for dirpath, _, files in os.walk(os.path.join(base, sub)):
        out += [os.path.relpath(os.path.join(dirpath, f), base).replace(os.sep, "/") for f in files]
    return sorted(out)


def file_chunks(path: str, chunk: int = 1 << 20) -> Iterable[bytes]:
    with _open(path) as fh:
        while data := fh.read(chunk):
            yield data


def stream_digest(chunks: Iterable[bytes]) -> tuple[int, bytes]:
    h, n = hashlib.sha256(), 0
    for c in chunks:
        h.update(c)
        n += len(c)
    return n, h.digest()
