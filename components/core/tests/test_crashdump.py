"""Tests for modkit.core.crashdump on synthetic minidumps built here.

Each dump holds one module, a little captured memory and an exception stream whose thread context is filled with
recognisable register values. The CLI must print the in-flight C++ exception's type and message, and nothing about
registers, stacks, addresses or module offsets.
"""
from __future__ import annotations

import contextlib
import io
import os
import re
import struct
import tempfile
import unittest

from modkit.core import crashdump

CXX_CODE = 0xE06D7363      # the MSVC C++ exception code ('msc' | 0xE0 << 24)
CXX_MAGIC = 0x19930520     # the first ExceptionInformation word of an MSVC C++ throw
FAULT = 1                  # the dump's own fault: any code but the C++ one

BASE = 5 << 32             # the module's load address (synthetic)
STACK = 7 << 36            # a captured stack range
HEAP = 9 << 36             # a captured heap range: the throw object and its strings
REG = int.from_bytes(b"REGISTER", "little")  # every register in the thread context holds this
MESSAGE = "Can't load 'Mod/GameData.ndfbin': Property 'DamageType' must be defined"
MANGLED = b".?AVEException@Game@@"

# image-relative layout of the type information (ThrowInfo -> CatchableTypeArray -> CatchableType -> TypeDescriptor),
# all inside the module's read-only data section
RDATA = 8192
TI, CTA, CT, TD = RDATA + 64, RDATA + 96, RDATA + 128, RDATA + 192


def type_info() -> bytes:
    """The image bytes from TI to the end of the TypeDescriptor's name."""
    img = bytearray(TD + 16 + len(MANGLED) + 1 - TI)
    struct.pack_into("<Iiii", img, 0, 0, 0, 0, CTA)                    # ThrowInfo
    struct.pack_into("<ii", img, CTA - TI, 1, CT)                      # CatchableTypeArray: 1 type
    struct.pack_into("<Iiiiiii", img, CT - TI, 0, TD, 0, -1, 0, 40, 0)  # CatchableType
    img[TD - TI + 16:TD - TI + 16 + len(MANGLED)] = MANGLED            # TypeDescriptor name
    return bytes(img)


def heap() -> bytes:
    """The throw object (its message pointer at an offset no reader may assume) and the strings it points at."""
    blob = bytearray(512)
    msg_at, junk_at = 256, 128
    struct.pack_into("<Q", blob, 0, BASE + 8)          # a pointer into the module, not to text
    struct.pack_into("<Q", blob, 8, HEAP + junk_at)    # a pointer to bytes that are not text
    struct.pack_into("<Q", blob, 40, HEAP + msg_at)    # the message
    blob[junk_at:junk_at + 8] = b"\x01\x02\xff\xfe\x00\x00\x00\x00"
    blob[msg_at:msg_at + len(MESSAGE) + 1] = MESSAGE.encode() + b"\0"
    return bytes(blob)


def record(obj: int = HEAP) -> bytes:
    """An in-memory EXCEPTION_RECORD of an MSVC C++ throw."""
    return struct.pack("<IIQQI4x15Q", CXX_CODE, 1, 0, BASE + 4096, 4, CXX_MAGIC, obj, BASE + TI, BASE,
                       *([0] * 11))


def stack(with_record: bool = True) -> bytes:
    """Return-address-like values around the record, as a real stack has."""
    words = struct.pack("<8Q", *(BASE + 4096 + 16 * k for k in range(8)))
    return words + (record() if with_record else bytes(len(record()))) + words


def minidump(ranges, *, image_in_memory: bool = True, memory64: bool = False, exe_path: str = "Game.exe",
             stamp: int = 1234) -> bytes:
    """A minidump with ModuleList, MemoryList (or Memory64List) and Exception streams."""
    ranges = list(ranges) + ([(BASE + TI, type_info())] if image_in_memory else [])
    nstreams = 3
    out = bytearray(32 + 12 * nstreams)

    def put(data: bytes) -> int:
        while len(out) % 8:
            out.append(0)
        at = len(out)
        out.extend(data)
        return at

    name = exe_path.encode("utf-16le")
    name_at = put(struct.pack("<I", len(name)) + name)
    module = struct.pack("<QIIII", BASE, 1 << 20, 0, stamp, name_at) + bytes(108 - 24)
    mod_at = put(struct.pack("<I", 1) + module)
    if memory64:
        base_at = len(out) + 16 + 16 * len(ranges)
        base_at += (-base_at) % 8
        head = struct.pack("<QQ", len(ranges), base_at) + b"".join(
            struct.pack("<QQ", start, len(data)) for start, data in ranges)
        mem_at = put(head)
        while len(out) < base_at:
            out.append(0)
        for _, data in ranges:
            out.extend(data)
        mem = (9, len(head), mem_at)
    else:
        descs = []
        for start, data in ranges:
            descs.append(struct.pack("<QII", start, len(data), put(data)))
        body = struct.pack("<I", len(ranges)) + b"".join(descs)
        mem = (5, len(body), put(body))
    context = bytearray(1232)
    struct.pack_into("<17Q", context, 120, *([REG] * 17))
    ctx_at = put(bytes(context))
    exc = struct.pack("<II", 42, 0) + struct.pack("<IIQQI4x15Q", FAULT, 0, 0, REG, 2, *([REG] * 15)) \
        + struct.pack("<II", len(context), ctx_at)
    exc_at = put(exc)
    struct.pack_into("<4sIII", out, 0, b"MDMP", 42899, nstreams, 32)
    for i, (kind, size, at) in enumerate([(4, len(module) + 4, mod_at), mem, (6, len(exc), exc_at)]):
        struct.pack_into("<III", out, 32 + 12 * i, kind, size, at)
    return bytes(out)


def pe_image(stamp: int) -> bytes:
    """A minimal PE32+ file holding the type information in an .rdata section at its image-relative address."""
    pe, nsec, optsz, align = 64, 2, 240, 512
    data = bytearray(align * 3)
    data[0:2] = b"MZ"
    struct.pack_into("<I", data, 60, pe)
    data[pe:pe + 4] = b"PE\0\0"
    struct.pack_into("<HHIIIHH", data, pe + 4, 34404, nsec, stamp, 0, 0, optsz, 34)
    struct.pack_into("<HQ", data, pe + 24, 523, 0)
    struct.pack_into("<Q", data, pe + 24 + 24, BASE)
    sec = pe + 24 + optsz
    struct.pack_into("<8sIIII", data, sec, b".text", align, 4096, align, align)
    struct.pack_into("<8sIIII", data, sec + 40, b".rdata", align, RDATA, align, 2 * align)
    at = 2 * align + TI - RDATA
    data[at:at + len(type_info())] = type_info()
    return bytes(data)


def run(data: bytes, *extra: str, exe: bytes | None = None) -> tuple[int, str]:
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "crashdump.dmp")
        with open(path, "wb") as fh:
            fh.write(data)
        args = [path, *extra]
        if exe is not None:
            exe_path = os.path.join(d, "Game.exe")
            with open(exe_path, "wb") as fh:
                fh.write(exe)
            args += ["--exe", exe_path]
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = crashdump.main(args)
    return code, out.getvalue()


class CrashdumpTest(unittest.TestCase):
    def test_prints_type_and_message(self):
        code, out = run(minidump([(STACK, stack()), (HEAP, heap())]))
        self.assertEqual(code, 0, out)
        self.assertIn("Game::EException", out)
        self.assertIn(MESSAGE, out)

    def test_output_has_no_registers_stacks_or_addresses(self):
        code, out = run(minidump([(STACK, stack()), (HEAP, heap())]))
        self.assertEqual(code, 0, out)
        self.assertNotRegex(out, r"0x|\+[0-9a-fA-F]{2,}|\b[0-9a-fA-F]{8,}\b")
        for value in (REG, BASE, STACK, HEAP, BASE + 4096):
            self.assertNotIn(str(value), out)
            self.assertNotIn(f"{value:x}", out.lower())
        self.assertNotRegex(out.lower(), r"\b(rip|rsp|rbp|rax|rcx|register|stack|frame|offset)\b")
        self.assertNotIn("REGISTER", out)

    def test_memory64_list(self):
        code, out = run(minidump([(STACK, stack()), (HEAP, heap())], memory64=True))
        self.assertEqual(code, 0, out)
        self.assertIn("Game::EException", out)
        self.assertIn(MESSAGE, out)

    def test_one_line_per_distinct_exception(self):
        code, out = run(minidump([(STACK, stack() + stack()), (HEAP, heap())]))  # the record copied twice
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count(MESSAGE), 1)

    def test_type_read_from_the_exe_when_not_in_memory(self):
        dump = minidump([(STACK, stack()), (HEAP, heap())], image_in_memory=False)
        code, out = run(dump, exe=pe_image(stamp=1234))
        self.assertEqual(code, 0, out)
        self.assertIn("Game::EException", out)
        self.assertIn(MESSAGE, out)

    def test_exe_of_another_build_is_not_trusted(self):
        dump = minidump([(STACK, stack()), (HEAP, heap())], image_in_memory=False)
        code, out = run(dump, exe=pe_image(stamp=999))
        self.assertEqual(code, 0, out)
        self.assertNotIn("Game::EException", out)
        self.assertIn("different build", out)
        self.assertIn(MESSAGE, out)

    def test_type_unknown_without_the_exe(self):
        dump = minidump([(STACK, stack()), (HEAP, heap())], image_in_memory=False, exe_path="NoSuchGame.exe")
        code, out = run(dump)
        self.assertEqual(code, 0, out)
        self.assertIn("--exe", out)
        self.assertIn(MESSAGE, out)

    def test_no_cxx_exception(self):
        code, out = run(minidump([(STACK, stack(with_record=False)), (HEAP, heap())]))
        self.assertEqual(code, 1)
        self.assertIn("no C++ exception", out)
        self.assertNotRegex(out, r"0x")

    def test_not_a_minidump(self):
        code, out = run(b"PK\3\4 not a dump")
        self.assertEqual(code, 1)
        self.assertIn("not a minidump", out)

    def test_decorated_names(self):
        self.assertEqual(crashdump.type_name(".?AVEException@Game@@"), "Game::EException")
        self.assertEqual(crashdump.type_name(".?AVexception@std@@"), "std::exception")
        self.assertEqual(crashdump.type_name(".?AUPlain@@"), "Plain")
        self.assertEqual(crashdump.type_name(".?AV?$Box@H@@"), ".?AV?$Box@H@@")  # templates stay decorated

    def test_message_must_be_text(self):
        self.assertTrue(re.fullmatch(r".*\S.*", MESSAGE))
        blob = bytearray(heap())
        struct.pack_into("<Q", blob, 40, 0)  # drop the message pointer: only the junk pointer is left
        code, out = run(minidump([(STACK, stack()), (HEAP, bytes(blob))]))
        self.assertEqual(code, 0, out)
        self.assertIn("Game::EException", out)
        self.assertIn("no readable message", out)


if __name__ == "__main__":
    unittest.main()
