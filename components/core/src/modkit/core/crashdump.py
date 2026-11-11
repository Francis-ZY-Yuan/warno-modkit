"""Read the error message out of a WARNO crash dump (stdlib only).

Purpose: when WARNO shows "has stopped working", it leaves a minidump, ``crashdump.dmp``, in a ``CrashRpt_<id>``
folder under your temp folder. The visible crash is often a second fault while the game tears its interface down to
report an error; the real cause is the C++ exception still in flight, whose message is the game's own error text
(for example a dictionary or load error). This module finds that exception in the dump's captured memory and prints
its type and message. It prints nothing else from the dump, reads your own WARNO.exe read-only when it needs the
type's name, and writes nothing.

  python -m modkit.core.crashdump DUMP [--exe WARNO.exe]

``--exe`` names the game's executable when the dump's own record of its path does not lead to it (a dump copied from
another machine); it must be the build that crashed.
"""
from __future__ import annotations

import argparse
import os
import struct
import sys
from dataclasses import dataclass, field

CXX_EXCEPTION = 0xE06D7363  # the exception code of every MSVC C++ throw
STREAM_MODULES, STREAM_MEMORY, STREAM_EXCEPTION, STREAM_MEMORY64 = 4, 5, 6, 9  # minidump stream types
OBJECT_SPAN = 128     # bytes of the thrown object searched for pointers to its message
MESSAGE_MAX = 4096    # longest message read
MESSAGE_MIN = 4       # shortest text taken for a message


class DumpError(RuntimeError):
    pass


@dataclass(frozen=True)
class Module:
    base: int
    size: int
    stamp: int
    path: str


@dataclass
class InFlight:
    """One C++ exception found in the dump: its thrown type's name (None when unreadable) and its messages."""
    type_name: str | None
    messages: list[str] = field(default_factory=list)
    type_note: str = ""


class Minidump:
    """The streams of a minidump this module needs: modules, captured memory and the exception."""

    def __init__(self, data: bytes):
        self.b = b = data
        if len(b) < 32 or b[:4] != b"MDMP":
            raise DumpError("not a minidump (no MDMP signature)")
        _, _, nstreams, diroff = struct.unpack_from("<4sIII", b, 0)
        self.streams: dict[int, list[tuple[int, int]]] = {}
        for i in range(nstreams):
            kind, size, at = struct.unpack_from("<III", b, diroff + 12 * i)
            self.streams.setdefault(kind, []).append((size, at))
        self.modules = self._modules()
        self.memory = self._memory()  # (start, size, file offset), sorted

    def _modules(self) -> list[Module]:
        out = []
        for _, at in self.streams.get(STREAM_MODULES, [])[:1]:
            for i in range(struct.unpack_from("<I", self.b, at)[0]):
                base, size, _, stamp, name = struct.unpack_from("<QIIII", self.b, at + 4 + 108 * i)
                n = struct.unpack_from("<I", self.b, name)[0]
                out.append(Module(base, size, stamp, self.b[name + 4:name + 4 + n].decode("utf-16le", "replace")))
        return out

    def _memory(self) -> list[tuple[int, int, int]]:
        out = []
        for _, at in self.streams.get(STREAM_MEMORY, [])[:1]:
            for i in range(struct.unpack_from("<I", self.b, at)[0]):
                out.append(struct.unpack_from("<QII", self.b, at + 4 + 16 * i))
        for _, at in self.streams.get(STREAM_MEMORY64, [])[:1]:
            n, data = struct.unpack_from("<QQ", self.b, at)
            for i in range(n):
                start, size = struct.unpack_from("<QQ", self.b, at + 16 + 16 * i)
                out.append((start, size, data))
                data += size
        return sorted(out)

    def read(self, addr: int, n: int) -> bytes | None:
        """`n` bytes of captured memory at `addr`, or None."""
        for start, size, off in self.memory:
            if start <= addr and addr + n <= start + size:
                return self.b[off + addr - start:off + addr - start + n]
        return None

    def read_upto(self, addr: int, n: int) -> bytes | None:
        """Up to `n` bytes of captured memory from `addr` to the end of its range, or None."""
        for start, size, off in self.memory:
            if start <= addr < start + size:
                end = min(start + size, addr + n)
                return self.b[off + addr - start:off + end - start]
        return None

    def module_at(self, addr: int) -> Module | None:
        return next((m for m in self.modules if m.base <= addr < m.base + m.size), None)

    def cxx_records(self) -> list[tuple[int, int, int]]:
        """(thrown object, its ThrowInfo, image base) of every MSVC C++ exception record: the dump's own exception,
        then every record found in captured memory, in memory order."""
        out = []
        code = struct.pack("<I", CXX_EXCEPTION)
        for _, at in self.streams.get(STREAM_EXCEPTION, [])[:1]:
            out += self._record(self.b, at + 8)
        for start, size, off in self.memory:
            blob = self.b[off:off + size]
            i = blob.find(code)
            while i >= 0:
                out += self._record(blob, i)
                i = blob.find(code, i + 4)
        return out

    def _record(self, blob: bytes, i: int) -> list[tuple[int, int, int]]:
        """An x64 EXCEPTION_RECORD at `blob[i]` of a C++ throw: 4 parameters, the last the base of a loaded module."""
        if i + 64 > len(blob):
            return []
        code, _, _, _, nparams = struct.unpack_from("<IIQQI", blob, i)
        if code != CXX_EXCEPTION or nparams != 4:
            return []
        _, obj, throw_info, image = struct.unpack_from("<4Q", blob, i + 32)
        if not obj or not any(m.base == image for m in self.modules):
            return []
        return [(obj, throw_info, image)]


def type_name(decorated: str) -> str:
    """'.?AVEException@Game@@' -> 'Game::EException'; anything this cannot read is returned as it is."""
    for prefix in (".?AV", ".?AU"):
        if decorated.startswith(prefix) and decorated.endswith("@@") and "?" not in decorated[len(prefix):]:
            parts = [p for p in decorated[len(prefix):-2].split("@") if p]
            if parts:
                return "::".join(reversed(parts))
    return decorated


def _text(raw: bytes | None) -> str | None:
    if not raw or b"\0" not in raw:
        return None
    try:
        s = raw.split(b"\0")[0].decode("utf-8")
    except UnicodeDecodeError:
        return None
    return s if len(s) >= MESSAGE_MIN and s.isprintable() else None


def messages(dump: Minidump, obj: int) -> list[str]:
    """The texts the thrown object points at, in the object's order: pointer-sized words that lead to a
    NUL-terminated printable string in captured memory."""
    raw = next((r for n in range(OBJECT_SPAN, 0, -8) if (r := dump.read(obj, n))), None)
    out = []
    for k in range(0, len(raw or b"") - 7, 8):
        s = _text(dump.read_upto(struct.unpack_from("<Q", raw, k)[0], MESSAGE_MAX))
        if s is not None and s not in out:
            out.append(s)
    return out


class _Image:
    """Image-relative reads of the module that threw: from captured memory, else from its file on disk."""

    def __init__(self, dump: Minidump, base: int, exe: str | None):
        self.dump, self.base, self.pe, self.note = dump, base, None, ""
        module = dump.module_at(base)
        path = exe or (module.path if module else None)
        if path and os.path.isfile(path):
            from modkit.core.pexref import PE
            try:
                pe = PE(path)
            except Exception:  # noqa: BLE001 - not a readable PE file
                self.note = f"{os.path.basename(path)} is not a readable executable"
            else:
                if module and pe.stamp != module.stamp:
                    pe.close()
                    self.note = f"{os.path.basename(path)} is a different build from the one that crashed"
                else:
                    self.pe = pe

    def read(self, offset: int, n: int, partial: bool = False) -> bytes | None:
        """`n` bytes at `offset` from the image base (with `partial`, up to `n`), or None."""
        addr = self.base + offset
        raw = self.dump.read_upto(addr, n) if partial else self.dump.read(addr, n)
        if raw is None and self.pe is not None:
            off = self.pe.rva2off(offset)
            raw = bytes(self.pe.m[off:off + n]) if off is not None else None
            if raw is not None and len(raw) < n and not partial:
                raw = None
        return raw

    def close(self) -> None:
        if self.pe is not None:
            self.pe.close()


def thrown_type(image: _Image, throw_info: int) -> str | None:
    """The thrown (most derived) type's name: ThrowInfo -> its catchable types -> the first one's type descriptor."""
    ti = image.read(throw_info, 16)
    if ti is None:
        return None
    cta = struct.unpack_from("<i", ti, 12)[0]
    head = image.read(cta, 8)
    if head is None or struct.unpack_from("<i", head, 0)[0] < 1:
        return None
    ct = image.read(struct.unpack_from("<i", head, 4)[0], 8)
    if ct is None:
        return None
    name = image.read(struct.unpack_from("<i", ct, 4)[0] + 16, 256, partial=True)
    if name is None or b"\0" not in name:
        return None
    return type_name(name.split(b"\0")[0].decode("latin-1"))


def in_flight(dump: Minidump, exe: str | None = None) -> list[InFlight]:
    """Every distinct C++ exception in flight, in the order found."""
    out: list[InFlight] = []
    seen = set()
    images: dict[int, _Image] = {}
    try:
        for obj, throw_info, base in dump.cxx_records():
            image = images.get(base) or images.setdefault(base, _Image(dump, base, exe))
            name = thrown_type(image, throw_info - base)
            texts = messages(dump, obj)
            key = (name, tuple(texts))
            if key in seen:
                continue
            seen.add(key)
            note = ""
            if name is None:
                note = image.note or "the type is not in the dump: pass --exe with the game's executable"
            out.append(InFlight(name, texts, note))
    finally:
        for image in images.values():
            image.close()
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("dump", help="the crashdump.dmp file")
    ap.add_argument("--exe", help="the game's executable, when the dump's record of its path does not lead to it")
    args = ap.parse_args(argv)
    try:
        with open(args.dump, "rb") as fh:
            dump = Minidump(fh.read())
        found = in_flight(dump, args.exe)
    except (OSError, DumpError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    if not found:
        print("no C++ exception in flight in this dump, so no game error message to read")
        return 1
    for k, exc in enumerate(found):
        if k:
            print()
        print(f"exception: {exc.type_name or 'unknown type'}" + (f" ({exc.type_note})" if exc.type_note else ""))
        for text in exc.messages or ["(no readable message)"]:
            print(f"message: {text}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
