"""A minimal x86-64 instruction decoder for reading MSVC-compiled code (read-only; stdlib only).

It covers the common integer/SSE subset; unknown opcodes print as 'db xx' and decoding carries on. RIP-relative
operands are resolved to their target. Call `bind` with a `pexref.PE` before `decode`.
"""
from __future__ import annotations

import struct

m = None        # the mapped file
rva2off = None  # image-relative address -> file offset
STRS = None     # optional: an object whose .at(target) names the string at a RIP-relative target


def bind(pe, strings=None) -> None:
    """Decode from `pe` (a `pexref.PE`); `strings`, when given, annotates RIP-relative string operands."""
    global m, rva2off, STRS
    m, rva2off, STRS = pe.m, pe.rva2off, strings


def note(t):
    sa = STRS.at(t) if STRS is not None else None
    return f"  ; {sa[2][:90]!r}" if sa and sa[0] == 0 else ""


R64 = ["rax", "rcx", "rdx", "rbx", "rsp", "rbp", "rsi", "rdi", "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"]
R32 = ["eax", "ecx", "edx", "ebx", "esp", "ebp", "esi", "edi"] + [f"r{i}d" for i in range(8, 16)]
R16 = ["ax", "cx", "dx", "bx", "sp", "bp", "si", "di"] + [f"r{i}w" for i in range(8, 16)]
R8R = ["al", "cl", "dl", "bl", "spl", "bpl", "sil", "dil"] + [f"r{i}b" for i in range(8, 16)]
R8L = ["al", "cl", "dl", "bl", "ah", "ch", "dh", "bh"]
CC = ["o", "no", "b", "ae", "e", "ne", "be", "a", "s", "ns", "p", "np", "l", "ge", "le", "g"]
ALU = ["add", "or", "adc", "sbb", "and", "sub", "xor", "cmp"]
SHF = ["rol", "ror", "rcl", "rcr", "shl", "shr", "sal", "sar"]


class D:
    def __init__(s, rva):
        s.rva = rva
        s.o = rva2off(rva)
        s.p = s.o

    def u8(s):
        v = m[s.p]; s.p += 1; return v

    def i8(s):
        v = struct.unpack_from("<b", m, s.p)[0]; s.p += 1; return v

    def i16(s):
        v = struct.unpack_from("<h", m, s.p)[0]; s.p += 2; return v

    def i32(s):
        v = struct.unpack_from("<i", m, s.p)[0]; s.p += 4; return v

    def i64(s):
        v = struct.unpack_from("<q", m, s.p)[0]; s.p += 8; return v


def reg(n, size, rex):
    if size == 8:
        return R64[n]
    if size == 4:
        return R32[n]
    if size == 2:
        return R16[n]
    return R8R[n] if rex else R8L[n]


def decode(rva):
    d = D(rva)
    rex = 0; opsz16 = False; rep = None
    while True:
        b = m[d.p]
        if b == 0x66:
            opsz16 = True; d.p += 1
        elif b in (0xF2, 0xF3):
            rep = b; d.p += 1
        elif b in (0x2E, 0x3E, 0x26, 0x64, 0x65, 0x36, 0xF0):
            d.p += 1
        else:
            break
    if 0x40 <= m[d.p] <= 0x4F:
        rex = m[d.p]; d.p += 1
    W = bool(rex & 8); RR = (rex >> 2) & 1; X = (rex >> 1) & 1; B = rex & 1
    osz = 8 if W else (2 if opsz16 else 4)
    fix = []  # deferred rip-relative

    def modrm(size, xmm=False):
        mr = d.u8()
        mod, rg, rm = mr >> 6, ((mr >> 3) & 7) | (RR << 3), mr & 7
        if mod == 3:
            n = rm | (B << 3)
            return rg, (f"xmm{n}" if xmm else reg(n, size, rex)), None
        if rm == 4:
            sib = d.u8()
            sc, ix, bs = sib >> 6, ((sib >> 3) & 7) | (X << 3), sib & 7
            parts = []
            if bs == 5 and mod == 0:
                disp = d.i32()
                base = None
            else:
                base = R64[bs | (B << 3)]
                disp = d.i8() if mod == 1 else d.i32() if mod == 2 else 0
            if base:
                parts.append(base)
            if ix != 4:
                parts.append(f"{R64[ix]}*{1 << sc}")
            s = "+".join(parts)
            if disp:
                s += f"{disp:+#x}"
            return rg, f"[{s}]", None
        if rm == 5 and mod == 0:
            disp = d.i32()
            return rg, "RIP", disp
        base = R64[rm | (B << 3)]
        disp = d.i8() if mod == 1 else d.i32() if mod == 2 else 0
        return rg, f"[{base}{disp:+#x}]" if disp else f"[{base}]", None

    def mem(r):  # resolve rip operands once instruction length is known
        rg, op, disp = r
        if disp is not None:
            fix.append(disp)
            return rg, "@RIP@"
        return rg, op

    op = d.u8()
    txt = None
    if op == 0x0F:
        op2 = d.u8()
        if 0x80 <= op2 <= 0x8F:
            t = d.p + 4 - d.o + rva + d.i32()
            txt = f"j{CC[op2 - 0x80]} {t:x}"
        elif 0x90 <= op2 <= 0x9F:
            rg, o = mem(modrm(1)); txt = f"set{CC[op2 - 0x90]} {o}"
        elif 0x40 <= op2 <= 0x4F:
            rg, o = mem(modrm(osz)); txt = f"cmov{CC[op2 - 0x40]} {reg(rg, osz, rex)}, {o}"
        elif op2 in (0xB6, 0xB7, 0xBE, 0xBF):
            rg, o = mem(modrm(1 if op2 in (0xB6, 0xBE) else 2))
            txt = f"{'movzx' if op2 < 0xB8 else 'movsx'} {reg(rg, osz, rex)}, {'byte' if op2 in (0xB6, 0xBE) else 'word'} {o}"
        elif op2 == 0xAF:
            rg, o = mem(modrm(osz)); txt = f"imul {reg(rg, osz, rex)}, {o}"
        elif op2 == 0x1F:
            mem(modrm(osz)); txt = "nop"
        elif op2 in (0x10, 0x11, 0x28, 0x29, 0x6F, 0x7F, 0x57, 0xEF, 0xD6, 0x7E, 0x6E, 0x2E, 0x2F, 0x58, 0x59, 0x5C, 0x5E,
                     0x5A, 0x2A, 0x2C, 0x2D, 0x54, 0x55, 0x56, 0x14, 0x16, 0x12, 0x13, 0x17, 0xC6, 0x70, 0x60, 0x62, 0x6C,
                     0xD4, 0xFE, 0xFA, 0x66, 0x76, 0x74, 0xD7, 0x51, 0x5D, 0x5F, 0xC2, 0x3A, 0x38, 0xC5, 0xC4):
            if op2 in (0x3A,):
                d.u8()
            gpr = op2 in (0x7E, 0x6E, 0x2A, 0x2C, 0x2D, 0xD7, 0xC5)
            rg, o = mem(modrm(osz, xmm=not gpr))
            if op2 in (0x70, 0xC6, 0xC2, 0x3A, 0xC4, 0xC5):
                d.u8()
            txt = f"sse.{op2:02x}{'/' + hex(rep) if rep else ''}{'/66' if opsz16 else ''} xmm{rg}, {o}"
        elif op2 in (0xA3, 0xAB, 0xB3, 0xBB):
            rg, o = mem(modrm(osz)); txt = f"bt* {o}, {reg(rg, osz, rex)}"
        elif op2 == 0xBA:
            rg, o = mem(modrm(osz)); i = d.u8(); txt = f"bt*{rg & 7} {o}, {i}"
        elif op2 in (0xBC, 0xBD, 0xB8):
            rg, o = mem(modrm(osz)); txt = f"bsf/bsr/popcnt {reg(rg, osz, rex)}, {o}"
        elif op2 in (0xB0, 0xB1, 0xC0, 0xC1):
            rg, o = mem(modrm(osz)); txt = f"cmpxchg/xadd {o}, {reg(rg, osz, rex)}"
        elif op2 == 0x0B:
            txt = "ud2"
        elif op2 in (0xA2, 0x31, 0x05):
            txt = f"0f{op2:02x}"
        elif op2 == 0x18 or op2 == 0x0D:
            mem(modrm(osz)); txt = "prefetch"
        elif op2 in (0xC8, 0xC9, 0xCA, 0xCB, 0xCC, 0xCD, 0xCE, 0xCF):
            txt = f"bswap {reg((op2 - 0xC8) | (B << 3), osz, rex)}"
        elif op2 in (0xA4, 0xA5, 0xAC, 0xAD):
            rg, o = mem(modrm(osz))
            if op2 in (0xA4, 0xAC):
                d.u8()
            txt = f"shld/shrd {o}, {reg(rg, osz, rex)}"
        else:
            txt = f"db 0f {op2:02x}"
    elif op < 0x40 and (op & 7) < 6:
        k = ALU[op >> 3]; f = op & 7
        if f == 4:
            txt = f"{k} al, {d.i8():#x}"
        elif f == 5:
            txt = f"{k} {reg(0, osz, rex)}, {d.i32() if osz != 2 else d.i16():#x}"
        else:
            size = 1 if f in (0, 2) else osz
            rg, o = mem(modrm(size))
            r = reg(rg, size, rex)
            txt = f"{k} {o}, {r}" if f < 2 else f"{k} {r}, {o}"
    elif 0x50 <= op <= 0x57:
        txt = f"push {R64[(op - 0x50) | (B << 3)]}"
    elif 0x58 <= op <= 0x5F:
        txt = f"pop {R64[(op - 0x58) | (B << 3)]}"
    elif op == 0x63:
        rg, o = mem(modrm(4)); txt = f"movsxd {reg(rg, osz, rex)}, {o}"
    elif op in (0x68, 0x6A):
        txt = f"push {d.i32() if op == 0x68 else d.i8():#x}"
    elif op in (0x69, 0x6B):
        rg, o = mem(modrm(osz)); i = d.i32() if op == 0x69 else d.i8()
        txt = f"imul {reg(rg, osz, rex)}, {o}, {i:#x}"
    elif 0x70 <= op <= 0x7F:
        t = d.p + 1 - d.o + rva + d.i8()
        txt = f"j{CC[op - 0x70]} {t:x}"
    elif op in (0x80, 0x81, 0x83):
        size = 1 if op == 0x80 else osz
        rg, o = mem(modrm(size))
        i = d.i8() if op in (0x80, 0x83) else (d.i16() if osz == 2 else d.i32())
        txt = f"{ALU[rg & 7]} {'byte ' if size == 1 else ''}{o}, {i:#x}"
    elif op in (0x84, 0x85, 0x86, 0x87, 0x88, 0x89, 0x8A, 0x8B):
        size = 1 if op in (0x84, 0x86, 0x88, 0x8A) else osz
        rg, o = mem(modrm(size)); r = reg(rg, size, rex)
        k = {0x84: "test", 0x85: "test", 0x86: "xchg", 0x87: "xchg"}.get(op, "mov")
        txt = f"{k} {r}, {o}" if op in (0x8A, 0x8B) else f"{k} {o}, {r}"
    elif op == 0x8D:
        rg, o = mem(modrm(osz)); txt = f"lea {reg(rg, osz, rex)}, {o}"
    elif op == 0x90:
        txt = "nop"
    elif 0x91 <= op <= 0x97:
        txt = f"xchg rax, {R64[(op - 0x90) | (B << 3)]}"
    elif op == 0x98:
        txt = "cdqe" if W else "cwde"
    elif op == 0x99:
        txt = "cqo" if W else "cdq"
    elif op in (0xA8, 0xA9):
        txt = f"test {'al' if op == 0xA8 else reg(0, osz, rex)}, {d.u8() if op == 0xA8 else d.i32():#x}"
    elif op in (0xA4, 0xA5, 0xAA, 0xAB):
        txt = f"{'rep ' if rep else ''}{'movs' if op < 0xA8 else 'stos'}"
    elif 0xB0 <= op <= 0xB7:
        txt = f"mov {reg((op - 0xB0) | (B << 3), 1, rex)}, {d.u8():#x}"
    elif 0xB8 <= op <= 0xBF:
        n = (op - 0xB8) | (B << 3)
        txt = f"mov {reg(n, osz, rex)}, {(d.i64() if W else d.i32()):#x}"
    elif op in (0xC0, 0xC1, 0xD0, 0xD1, 0xD2, 0xD3):
        size = 1 if op in (0xC0, 0xD0, 0xD2) else osz
        rg, o = mem(modrm(size))
        c = d.u8() if op in (0xC0, 0xC1) else (1 if op in (0xD0, 0xD1) else "cl")
        txt = f"{SHF[rg & 7]} {o}, {c}"
    elif op == 0xC3:
        txt = "ret"
    elif op == 0xC2:
        d.i16(); txt = "ret imm"
    elif op in (0xC6, 0xC7):
        size = 1 if op == 0xC6 else osz
        rg, o = mem(modrm(size))
        i = d.u8() if size == 1 else (d.i16() if size == 2 else d.i32())
        txt = f"mov {'byte ' if size == 1 else ('qword ' if size == 8 else 'dword ')}{o}, {i:#x}"
    elif op == 0xCC:
        txt = "int3"
    elif op == 0xE8:
        t = d.p + 4 - d.o + rva + d.i32()
        txt = f"call {t:x}"
    elif op == 0xE9:
        t = d.p + 4 - d.o + rva + d.i32()
        txt = f"jmp {t:x}"
    elif op == 0xEB:
        t = d.p + 1 - d.o + rva + d.i8()
        txt = f"jmp {t:x}"
    elif op in (0xF6, 0xF7):
        size = 1 if op == 0xF6 else osz
        rg, o = mem(modrm(size))
        k = ["test", "test", "not", "neg", "mul", "imul", "div", "idiv"][rg & 7]
        if (rg & 7) < 2:
            i = d.u8() if size == 1 else d.i32()
            txt = f"test {'byte ' if size == 1 else ''}{o}, {i:#x}"
        else:
            txt = f"{k} {o}"
    elif op in (0xFE, 0xFF):
        size = 1 if op == 0xFE else osz
        rg, o = mem(modrm(8 if (op == 0xFF and (rg_peek := (m[d.p] >> 3) & 7) in (2, 4, 6)) else size))
        k = ["inc", "dec", "call", "callf", "jmp", "jmpf", "push", "?"][rg & 7]
        txt = f"{k} {o}"
    else:
        txt = f"db {op:02x}"
    ln = d.p - d.o
    for disp in fix:
        t = rva + ln + disp
        txt = txt.replace("@RIP@", f"[{t:x}]") + note(t)
    return ln, txt
