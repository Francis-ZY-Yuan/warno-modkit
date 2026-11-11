"""A read-only view of a PE32+ executable: sections, functions and the code bytes (stdlib only).

It maps the file read-only; nothing in it is executed or changed. Functions come from the exception directory
(.pdata), so any code address can be given the function that contains it. Addresses are image-relative (RVAs), the
PE format's own unit.
"""
from __future__ import annotations

import bisect
import mmap
import struct


class PE:
    def __init__(self, path: str):
        self.fh = open(path, "rb")
        self.m = m = mmap.mmap(self.fh.fileno(), 0, access=mmap.ACCESS_READ)
        pe = struct.unpack_from("<I", m, 0x3C)[0]
        nsec = struct.unpack_from("<H", m, pe + 6)[0]
        self.stamp = struct.unpack_from("<I", m, pe + 8)[0]  # the build's link time stamp
        optsz = struct.unpack_from("<H", m, pe + 20)[0]
        opt = pe + 24
        self.base = struct.unpack_from("<Q", m, opt + 24)[0]
        exc_rva, exc_size = struct.unpack_from("<II", m, opt + 112 + 3 * 8)
        self.secs = []
        for i in range(nsec):
            s = pe + 24 + optsz + 40 * i
            vsize, va, rsize, raw = struct.unpack_from("<IIII", m, s + 8)
            self.secs.append((m[s:s + 8].rstrip(b"\0").decode(), va, vsize, raw, rsize))
        text = next(s for s in self.secs if s[0] == ".text")
        self.tva, self.tlen = text[1], min(text[2], text[4])
        eo = self.rva2off(exc_rva)
        self.funcs = sorted(struct.unpack_from("<II", m, eo + 12 * i) for i in range(exc_size // 12))
        self.starts = [b for b, e in self.funcs]
        self.startset = set(self.starts)

    def close(self) -> None:
        self.m.close()
        self.fh.close()

    def rva2off(self, r):
        for n, va, vs, raw, rs in self.secs:
            if va <= r < va + rs:
                return raw + r - va

    def off2rva(self, o):
        for n, va, vs, raw, rs in self.secs:
            if raw <= o < raw + rs:
                return va + o - raw

    def func_of(self, rva):
        i = bisect.bisect_right(self.starts, rva) - 1
        if i >= 0 and self.funcs[i][0] <= rva < self.funcs[i][1]:
            return self.funcs[i]
        return None

    def text(self, lo=None, hi=None):
        lo = self.tva if lo is None else lo
        hi = self.tva + self.tlen if hi is None else hi
        o = self.rva2off(lo)
        return lo, self.m[o:o + (hi - lo)]
