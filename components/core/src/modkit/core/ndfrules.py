"""WARNO's own load-time property checks, read from your WARNO.exe, and the gate that applies them to generated files.

Purpose: this module reads your own WARNO.exe, read-only, to find the load-time checks your mod must pass. It writes
nothing to the exe and runs nothing from it; stdlib only.

When the game loads an NDF object it runs that class's validation, which first runs its parent class's and then tests
the object's own properties. A failure is fatal: the game exits with an error such as "Can't load '<file>': Invalid
property in object '<anonymous> (<class>)': Property 'DamageType' must be defined". Each test reports through one of
the game's message templates:

  defined          "Property '%1' must be defined": the property is still zero (a null reference, an empty list or
                   string, a 0 int or enum, a 0.0 float)
  ge gt le lt eq   "Property '%1' must be greater or egal than '%2' ..." etc.: a value against a constant
  range, lt_prop, le_prop   a value in a range, or against another property
  cond             "Failed condition for property '%1': '%2'": a condition on the property, such as FKey.IsValid()
  custom           any other message (free text such as "failed condition 'FData.Fov > 0'")

`extract` finds these checks for every class and writes them to `ndfrules.tsv` in the data folder (see
`modkit.core.paths.data_dir`), one row per check. `check_file` applies them to a generated file: it evaluates
`defined` and the constant comparisons, and refuses an object whose class has a check it cannot evaluate unless that
check is in REVIEWED with the reason it holds. On a class in PROPERTIES it also refuses any property that no rule
names until that property is reviewed there (what the game's validation does with it, and stock's use). The table
records WARNO.exe's size; `check_file` fails when the installed exe differs, so a game update asks for a fresh
`extract` instead of trusting stale rules.

CLI (``python -m modkit.core.ndfrules ...``):
  extract [exe]        rewrite the table from WARNO.exe (default: the configured game folder's) and list what changed
  verify               apply the table to the stock files of the extraction (expect no violations)
  show <class>...      the rows of these classes
"""
from __future__ import annotations

import collections
import dataclasses
import glob
import os
import re
import struct
import sys
from dataclasses import dataclass
from pathlib import Path

from modkit.core import ndfbin
from modkit.core import paths
from modkit.core.gates import CheckError, check

TABLE_NAME = "ndfrules.tsv"
EXE_NAME = "WARNO.exe"

TEMPLATES = {  # message -> kind; the thrower helpers are found through these strings
    b"Property '%1' must be defined": "defined",
    b"Property '%1' must be in range ]%2; %3], current value is '%4'": "range",
    b"Property '%1' must be in range [%2; %3], current value is '%4'": "range",
    b"Property '%1' must be in range ]%2; %3[, current value is '%4'": "range",
    b"Property '%1' must be in range [%2; %3[, current value is '%4'": "range",
    b"Property '%1' must be less than property '%2', current values are respectively '%3' and '%4'": "lt_prop",
    b"Property '%1' must be less or equal than property '%2', current values are respectively '%3' and '%4'":
        "le_prop",
    b"Property '%1' must be less or equal to '%2', current value is '%3'": "le",
    b"Property '%1' must be equal to '%2', current value is '%3'": "eq",
    b"Property '%1' must be less than '%2', current value is '%3'": "lt",
    b"Property '%1' must be greater than '%2', current value is '%3'": "gt",
    b"Property '%1' must be greater or egal than '%2', current value is '%3'": "ge",
}
COND = "Failed condition for property '%1': '%2'"  # formatted inline, thrown through a generic helper
COMPARE = {"ge": lambda v, b: v >= b, "gt": lambda v, b: v > b, "le": lambda v, b: v <= b,
           "lt": lambda v, b: v < b, "eq": lambda v, b: v == b}
HELPER_MAX = 128  # bytes: a thrower helper only formats its message and throws, so it is a small function
SLOT_MARGIN = 4   # the validate slot must hold at least this many times more checkers than any other slot
CHAIN_SHARE = 0.9  # of the checking routines at that slot, at least this share must chain to the root validation

# Checks the gate cannot read on its own, on classes a generator emits: (class, kind, property or message) ->
# (how to evaluate it, what the game's check does). "nonzero" evaluates it as a `defined` check; "holds" trusts the
# reason.
REVIEWED: dict[tuple[str, str, str], tuple[str, str]] = {
    ("TCutsceneDescriptor", "cond", "Key"): (
        "nonzero", "the condition is the Key's localisation token being valid, which fails only for a zero token; "
                   "every stock object of the class sets Key (none leaves it out)"),
}

# Classes whose every property the gate must know: on an object of one of these, a property that none of the class's
# rules names fails the gate until it is reviewed here, {class: {property: evidence}}. The evidence says what the
# game's validation does with it and what stock does. A property with no rule passes the validation whatever its
# value, so a new one (a property no stock file sets, admitted by a content's extra_shapes) is reviewed first, not
# trusted. One evidence entry per class names every property the validation tests, so a re-extract that finds a new
# check makes the review stale (test_ndfrules checks it).
PROPERTIES: dict[str, dict[str, str]] = {
    "TGDDescriptorProductionUnites": {  # a generated one may set Group and Transporter, which no stock object does
        "Group": "the validation tests only Camp, Position and TypeUnit (defined), ExperienceLevel >= 0 and "
                 "NbUnit >= 1, never Group; the 6 stock objects leave Group out; the game's own scenario API sets "
                 "it (SetGroup)",
        "Transporter": "the validation never tests it (see Group); the 6 stock objects leave it out; the game's own "
                       "scenario API sets it (SetTransporter). The 'transporter is not a transport' check belongs "
                       "to deck descriptors (TDeckDescriptor), not this class",
        "ProduceOutMap": "the validation never tests it (see Group); all 6 stock objects set it True",
    },
}

# What a failure the gate cannot settle asks the modder to do. REVIEWED and PROPERTIES live in the installed core,
# which an update replaces, so a review goes in the build's own reviewed_pending and upstream, never into them.
REVIEW_REMEDY = ("if you have checked it against the game and stock, put this gate's message in your build's "
                 "reviewed_pending (warno-gates), and send the review upstream so a toolkit release adds it")


@dataclass(frozen=True)
class Rule:
    cls: str
    kind: str
    prop: str       # the property the message names ('' when the throw names none)
    bound: str      # the constant(s) of a comparison, or the other property of lt_prop/le_prop
    detail: str     # custom: the message; else ''
    validate: int   # a grouping key: the rows of one validation routine share it (kept in the table, never printed)
    stock: int = 0    # objects of the class in the stock files
    omitted: int = 0  # of those, how many leave the property out (its C++ default then passes the check)


def table_path() -> Path:
    """The rules table: `ndfrules.tsv` in the data folder."""
    return paths.data_dir() / TABLE_NAME


def exe_path() -> Path:
    """The installed WARNO.exe (read only)."""
    return paths.game_dir() / EXE_NAME


# --------------------------------------------------------------------------- extract

class _Exe:
    """WARNO.exe mapped read-only, with pedis's decoder pointed at it."""

    def __init__(self, path: str):
        from modkit.core import pedis
        from modkit.core.pexref import PE
        self.pe = pe = PE(path)
        self.pedis = pedis
        pedis.bind(pe)
        self.lo, self.buf = pe.text()
        self.rdata = next((va, bytes(pe.m[raw:raw + rs])) for n, va, vs, raw, rs in pe.secs if n == ".rdata")

    def q(self, rva: int) -> int | None:
        o = self.pe.rva2off(rva)
        return struct.unpack_from("<Q", self.pe.m, o)[0] if o is not None else None

    def cstr(self, rva: int) -> str:
        o = self.pe.rva2off(rva)
        if o is None:
            return ""
        s = bytes(self.pe.m[o:o + 300]).split(b"\0")[0]
        return s.decode("latin-1") if s and all(32 <= c < 127 for c in s) else ""

    def insns(self, fn: int) -> list[tuple[int, str]]:
        b, e = self.pe.func_of(fn) or (fn, fn + 256)
        r, out = b, []
        while r < e:
            try:
                n, t = self.pedis.decode(r)
            except Exception:  # noqa: BLE001 - keep going past an undecodable byte
                n, t = 1, "??"
            out.append((r, t))
            r += n
        return out

    def rip_refs(self, target: int) -> list[int]:
        """Instructions whose RIP-relative lea/mov operand is `target`."""
        out = []
        for mt in re.finditer(rb"[\x8D\x8B][\x05\x0D\x15\x1D\x25\x2D\x35\x3D]", self.buf):
            i = mt.start() + 1
            if i + 5 <= len(self.buf) and self.lo + i + 5 + struct.unpack_from("<i", self.buf, i + 1)[0] == target:
                out.append(self.lo + i)
        return out

    def branch_sites(self, opcodes: bytes, targets) -> list[tuple[int, int]]:
        """(site, target) of every rel32 call/jump (`opcodes`: E8 call, E9 jmp) whose target is in `targets`."""
        out = []
        for mt in re.finditer(b"[" + re.escape(opcodes) + b"]", self.buf):
            i = mt.start()
            if i + 5 <= len(self.buf):
                t = self.lo + i + 5 + struct.unpack_from("<i", self.buf, i + 1)[0]
                if t in targets:
                    out.append((self.lo + i, t))
        return out

    def fn_size(self, rva: int) -> int:
        f = self.pe.func_of(rva)
        return f[1] - f[0] if f else 1 << 30


CALL, JMP = b"\xE8", b"\xE9"


def _branch(t: str) -> tuple[str, int] | None:
    m = re.match(r"(call|jmp|j[a-z]+) ([0-9a-f]+)$", t)
    return (m.group(1), int(m.group(2), 16)) if m else None


def find_helpers(x: _Exe) -> tuple[dict[int, str], int, int]:
    """({helper: kind}, the root validation, the C++ throw). Every helper calls the throw; any other small function
    that calls it directly is a `custom` thrower."""
    helpers = {}
    for text, kind in TEMPLATES.items():
        hits = [mt.start() for mt in re.finditer(re.escape(text + b"\0"), x.pe.m)]
        check(len(hits) == 1, f"message {text!r} found {len(hits)} times in the exe")
        for site in x.rip_refs(x.pe.off2rva(hits[0])):
            f = x.pe.func_of(site)
            if f and f[1] - f[0] <= HELPER_MAX:
                helpers[f[0]] = kind
    must = [h for h, k in helpers.items() if k == "defined"]
    check(len(must) == 1, f"{len(must)} 'must be defined' helpers")
    calls = [b for _, t in x.insns(must[0]) if (b := _branch(t)) and b[0] == "call"]
    throw = calls[-1][1]  # format, build the exception, throw it
    for site, _ in x.branch_sites(CALL, {throw}):
        f = x.pe.func_of(site)
        if f and f[1] - f[0] <= HELPER_MAX and f[0] not in helpers:
            helpers[f[0]] = "custom"
    # the root: the function the validations call first, before any check (most common first call of the callers of
    # 'must be defined')
    firsts = collections.Counter()
    for site, _ in x.branch_sites(CALL + JMP, {must[0]}):
        f = x.pe.func_of(site)
        first = next((b for _, t in x.insns(f[0]) if (b := _branch(t)) and b[0] == "call"), None) if f else None
        if first:
            firsts[first[1]] += 1
    base = firsts.most_common(1)[0][0]
    return helpers, base, throw


def vtables(x: _Exe) -> list[tuple[str, int]]:
    """(class name, vtable) for every RTTI complete object locator in .rdata, primary and secondary bases."""
    va, blob = x.rdata
    cols = {}
    for i in range(0, len(blob) - 24, 4):
        sig, _, _, td, _, self_ = struct.unpack_from("<IIIIII", blob, i)
        if sig == 1 and self_ == va + i:
            name = x.cstr(td + 16)
            m = re.match(r"\.\?A[UV]([A-Za-z_]\w*)@", name)
            if m:
                cols[va + i] = m.group(1)
    out = []
    for i in range(0, len(blob) - 7, 8):
        p = struct.unpack_from("<Q", blob, i)[0] - x.pe.base
        if p in cols:
            out.append((cols[p], va + i + 8))
    return out


def vtable_functions(x: _Exe, vt: int, limit: int = 256) -> list[int]:
    """The entries of the vtable at `vt`, up to the first one that does not point into the code."""
    out = []
    for k in range(limit):
        v = x.q(vt + 8 * k)
        if v is None or not x.pe.tva <= v - x.pe.base < x.pe.tva + x.pe.tlen:
            break
        out.append(v - x.pe.base)
    return out


def pick_slot(counts: collections.Counter) -> int:
    """The vtable index that holds the property checkers, from {index: vtables holding a checker there}. It must
    stand out: SLOT_MARGIN times any other index, else the exe is not laid out as this module expects."""
    check(bool(counts), "no vtable holds a function that calls a property-check message helper")
    (slot, n), *rest = counts.most_common(2)
    check(not rest or n >= SLOT_MARGIN * rest[0][1],
          f"the validation's vtable index is ambiguous: {counts.most_common(3)} (index: vtables)")
    return slot


def checking_routines(x: _Exe, helpers: dict[int, str]) -> set[int]:
    """The functions that call a property-check message helper (the template ones; `custom` throwers serve other
    code too)."""
    templates = {h for h, k in helpers.items() if k != "custom"}
    return {f[0] for site, _ in x.branch_sites(CALL + JMP, templates) if (f := x.pe.func_of(site))}


def validate_slot(x: _Exe, helpers: dict[int, str], tabs: list[tuple[str, int]],
                  checkers: set[int] | None = None) -> int:
    """The vtable index of the validation method, read from the exe: the index at which vtables hold the checking
    routines."""
    checkers = checking_routines(x, helpers) if checkers is None else checkers
    counts = collections.Counter(k for _, vt in tabs for k, fn in enumerate(vtable_functions(x, vt))
                                 if fn in checkers)
    return pick_slot(counts)


def check_chain(at_slot: set[int], validates: set[int]) -> tuple[int, int]:
    """(chained, found): of the checking routines found at the chosen vtable index, how many chain to the root
    validation. Nearly all must: at a wrong index they would not, and the table would quietly miss checks."""
    found, chained = len(at_slot), len(at_slot & validates)
    check(found > 0 and chained >= CHAIN_SHARE * found,
          f"only {chained} of the {found} checking routines at the chosen vtable index chain to the root validation: "
          f"the index is wrong, and the table would miss checks")
    return chained, found


def stamp_line(exe_size: int, helpers: int, chained: int, found: int, files: int) -> str:
    """Line 1 of the table: what it was read from. It names no place in the exe."""
    return (f"WARNO.exe {exe_size} bytes; {helpers} helpers; {chained} of {found} checking routines chain to the root "
            f"validation; {files} stock files")


def first_target(x: _Exe, fn: int) -> int | None:
    """The first call or jump-out of `fn` (a validation calls its parent's first; a trivial one just tail-jumps)."""
    b, e = x.pe.func_of(fn) or (fn, fn)
    for _, t in x.insns(fn)[:40]:
        br = _branch(t)
        if br and (br[0] == "call" or not b <= br[1] < e):
            return br[1]
    return None


def checks_in(x: _Exe, fn: int, helpers: dict[int, str]) -> list[tuple[str, str, str, str]]:
    """(kind, property, bound, detail) of every helper call in `fn`; arguments read back to the block start."""
    ins = x.insns(fn)
    out = []
    for k, (r, t) in enumerate(ins):
        br = _branch(t)
        if not br or br[0] not in ("call", "jmp") or br[1] not in helpers:
            continue
        kind, args, strs = helpers[br[1]], {}, []
        for _, a in reversed(ins[max(0, k - 30):k]):  # back to the block start: a jump, a ret or another throw
            ab = _branch(a)
            if a.startswith("ret") or ab and (ab[0] != "call" or ab[1] in helpers):
                break
            m = re.match(r"lea (\w+), \[([0-9a-f]+)\]$", a)
            if m and (s := x.cstr(int(m.group(2), 16))):
                strs.insert(0, s)
                args.setdefault(m.group(1), s)
            m = re.match(r"(?:mov|xor) (r8d|r9d|edx), (0x-?[0-9a-f]+|-?\d+|r8d|r9d|edx)$", a)
            if m:
                v = m.group(2)
                args.setdefault(m.group(1), "0" if v == m.group(1) else str(int(v, 0)))
            m = re.match(r"sse\.57 (xmm[23]), (xmm[23])$", a)  # xorps x, x
            if m and m.group(1) == m.group(2):
                args.setdefault(m.group(1), "0.0")
            m = re.match(r"sse\.10/0xf3 (xmm[23]), \[([0-9a-f]+)\]$", a)  # movss x, [const]
            if m:
                o = x.pe.rva2off(int(m.group(2), 16))
                args.setdefault(m.group(1), repr(struct.unpack_from("<f", x.pe.m, o)[0]) if o else "?")
        if kind == "custom":
            if COND in strs:  # "Failed condition for property '%1': '%2'": the property, then the condition
                rest = [s for s in strs if s != COND]
                out.append(("cond", rest[0] if rest else "", "", rest[1] if len(rest) > 1 else ""))
            else:
                out.append((kind, "", "", " | ".join(strs)))
            continue
        prop = args.get("rcx", "")
        if kind in ("lt_prop", "le_prop"):
            bound = args.get("rdx", "")
        elif kind == "range":
            bound = ";".join(args.get(a, "?") for a in (("xmm2", "xmm3") if "xmm2" in args else ("r8d", "r9d")))
        elif kind == "defined":
            bound = ""
        else:
            bound = args.get("xmm2", args.get("r8d", "?"))
        out.append((kind, prop, bound, ""))
    return out


def extract(path: str | os.PathLike | None = None) -> tuple[list[Rule], str]:
    path = str(path or exe_path())
    x = _Exe(path)
    helpers, base, _ = find_helpers(x)
    tabs = vtables(x)
    checkers = checking_routines(x, helpers)
    at = validate_slot(x, helpers, tabs, checkers)
    slot = {vt: (x.q(vt + 8 * at) or 0) - x.pe.base for _, vt in tabs}
    validates, changed = {base}, True  # the validations: the root, or whatever starts by calling one
    while changed:
        changed = False
        for fn in set(slot.values()) - validates:
            if x.pe.func_of(fn) and first_target(x, fn) in validates:
                validates.add(fn)
                changed = True
    chained, found = check_chain(set(slot.values()) & checkers, validates)
    memo: dict[int, list] = {base: []}

    def rules_of(fn: int) -> list:
        if fn not in memo:
            parent = first_target(x, fn)
            memo[fn] = (rules_of(parent) if parent in validates else []) + [c + (fn,) for c in checks_in(x, fn, helpers)]
        return memo[fn]

    rules = set()
    for name, vt in tabs:
        fn = slot[vt]
        if fn in validates:
            rules.update(Rule(name, *c) for c in rules_of(fn))
    # A property the file leaves out keeps the member's C++ default, which may pass: count how often stock does that.
    classes = {r.cls for r in rules}
    seen, omitted, files = collections.Counter(), collections.Counter(), 0
    for nb in stock_files():
        files += 1
        for ob in nb.objects:
            cls = nb.cname(ob.cls)
            if cls in classes:
                seen[cls] += 1
                names = {nb.pname(p) for p, _ in ob.props}
                omitted.update((cls, r.prop) for r in rules if r.cls == cls and r.prop not in names)
    rules = {dataclasses.replace(r, stock=seen[r.cls], omitted=omitted[r.cls, r.prop]) for r in rules}
    stamp = stamp_line(os.stat(path).st_size, len(helpers), chained, found, files)
    return sorted(rules, key=lambda r: (r.cls, r.kind, r.prop, r.bound, r.detail, r.validate)), stamp


COLUMNS = "class\tkind\tproperty\tbound\tdetail\tvalidate\tstock\tomitted"


def _row(r: Rule) -> str:
    """A table row: the validate column is only a grouping key in the file."""
    return f"{r.cls}\t{r.kind}\t{r.prop}\t{r.bound}\t{r.detail}\t{r.validate:#x}\t{r.stock}\t{r.omitted}"


def _shown(r: Rule) -> str:
    """A rule as `show` and `extract` print it: everything but the grouping key."""
    return f"{r.cls}\t{r.kind}\t{r.prop}\t{r.bound}\t{r.detail}\t{r.stock}\t{r.omitted}"


def write_table(rules: list[Rule], stamp: str, path: str | os.PathLike | None = None) -> Path:
    path = Path(path) if path is not None else table_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(f"# {stamp}; written by modkit.core.ndfrules extract\n{COLUMNS}\n")
        for r in rules:
            fh.write(_row(r) + "\n")
    return path


# --------------------------------------------------------------------------- gate

def load_table(path: str | os.PathLike | None = None) -> tuple[dict[str, list[Rule]], int]:
    """({class: rules}, the WARNO.exe size the table was read from)."""
    path = Path(path) if path is not None else table_path()
    check(path.is_file(), f"no rules table at {path}: run `python -m modkit.core.ndfrules extract` (warno-setup)")
    with open(path, encoding="utf-8") as fh:
        head = fh.readline()
        m = re.match(r"# WARNO\.exe (\d+) bytes", head)
        check(bool(m), f"{path}: no WARNO.exe stamp on line 1")
        check(fh.readline().rstrip("\n") == COLUMNS, f"{path}: unexpected columns (re-run extract)")
        by_cls = collections.defaultdict(list)
        for line in fh:
            c, kind, prop, bound, detail, validate, stock, omitted = line.rstrip("\n").split("\t")
            by_cls[c].append(Rule(c, kind, prop, bound, detail, int(validate, 16), int(stock), int(omitted)))
    return dict(by_cls), int(m.group(1))


def check_exe(size: int, path: str | os.PathLike | None = None) -> None:
    """The installed WARNO.exe is the one the table was read from (a game update can change any rule). Without a
    configured or present exe there is nothing to compare."""
    if path is None:
        try:
            path = exe_path()
        except paths.NotConfigured:
            return
    if os.path.isfile(path):
        check(os.path.getsize(path) == size,
              f"WARNO.exe is {os.path.getsize(path)} bytes, the rules table was read from {size}: re-run "
              f"`python -m modkit.core.ndfrules extract`, review what it lists as changed, then rebuild")


def _number(nb: ndfbin.NdfBin, v: ndfbin.Value) -> float | None:
    return v.v if v.tag in (0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x13, 0x18, 0x19) else None


def is_zero(nb: ndfbin.NdfBin, v: ndfbin.Value) -> bool:
    """The value a C++ member keeps when the file does not set it: 0, 0.0, false, an empty list or string, a loc
    token or GUID of zero bytes."""
    if v.tag in (0x11, 0x12, 0x08):
        return len(v.v) == 0
    if v.tag in (0x07, 0x1C):
        return not nb.strings[v.v]
    if v.tag in (0x1A, 0x1D, 0x25):
        return not any(v.v)
    n = _number(nb, v)
    return n is not None and n == 0


def _zero(r: Rule, v: ndfbin.Value | None, nb: ndfbin.NdfBin) -> str | None:
    """Why the property fails a non-zero test, or None: a zero value always fails; a missing one only when no stock
    object of the class leaves it out (else the C++ default it then keeps passes)."""
    if v is not None and is_zero(nb, v):
        return "the game rejects a zero value"
    if v is None and not r.omitted:
        return f"it is left out, and none of the {r.stock} stock objects of the class leaves it out"
    return None


def violations(nb: ndfbin.NdfBin, rules: dict[str, list[Rule]], reviewed: dict | None = REVIEWED,
               properties: dict[str, dict[str, str]] | None = PROPERTIES) -> list[str]:
    """Every check an object of `nb` fails, or that `check` cannot evaluate and nobody reviewed (reviewed=None:
    skip those), and every property of a PROPERTIES class that no rule names and nobody reviewed (properties=None:
    skip those)."""
    out = []
    for i, ob in enumerate(nb.objects):
        cls = nb.cname(ob.cls)
        props = {nb.pname(p): v for p, v in ob.props}
        if properties is not None and cls in properties:
            named = {r.prop for r in rules.get(cls, ())}
            tested = sorted(p for p in named if p)
            what = (f"the game's validation of {cls} tests only {', '.join(tested)}" if tested
                    else f"the table holds no check of {cls}")
            out += [f"#{i} {cls}: property '{p}' is unknown to the gate: no rule names it and it is not reviewed; "
                    f"{what}; {REVIEW_REMEDY}" for p in props if p not in named and p not in properties[cls]]
        for r in rules.get(cls, ()):
            where, v = f"#{i} {cls}", props.get(r.prop)
            if r.kind == "defined":
                if why := _zero(r, v, nb):
                    out.append(f"{where}: Property '{r.prop}' must be defined: {why}")
            elif r.kind in COMPARE and re.fullmatch(r"-?[\d.]+(e-?\d+)?", r.bound):
                n = _number(nb, v) if v is not None else None
                if n is not None and not COMPARE[r.kind](n, float(r.bound)):
                    out.append(f"{where}: {r.prop} = {n} fails '{r.kind} {r.bound}'")
            elif reviewed is not None:
                how = reviewed.get((cls, r.kind, r.prop or r.detail))
                if how is None:
                    bound = f" {r.bound}" if r.bound else ""
                    out.append(f"{where}: unreviewed game check {r.kind} {r.prop or r.detail!r}{bound}: "
                               f"{REVIEW_REMEDY}")
                elif how[0] == "nonzero" and (why := _zero(r, v, nb)):
                    out.append(f"{where}: Property '{r.prop}' fails '{r.detail}': {why}")
    return out


def check_file(raw: bytes, what: str, table: str | os.PathLike | None = None) -> int:
    """Gate: the generated file `raw` passes every load-time check WARNO.exe makes. Returns the objects checked."""
    rules, size = load_table(table)
    check_exe(size)
    nb, _, _ = ndfbin.decode(raw)
    bad = violations(nb, rules)
    check(not bad, f"{what}: {len(bad)} objects fail WARNO's load-time checks:\n  " + "\n  ".join(bad))
    return len(nb.objects)


# --------------------------------------------------------------------------- CLI

def stock_files(files: list[str] | None = None, skipped: list[str] | None = None):
    """Each readable stock ndfbin of the current build, parsed (with its path as `nb.path`). By default every
    ndfbin of the extraction except those under its optional `older/` folder (earlier game builds, which this exe
    never loads). A file that does not parse is left out, and its path appended to `skipped` when given."""
    root = str(paths.extracted_root())
    older = os.path.join(root, "older")  # not stock
    for p in files if files is not None else sorted(glob.glob(os.path.join(root, "**", "*.ndfbin"), recursive=True)):
        if os.path.commonpath([p, older]) == older:
            continue
        try:
            with open(p, "rb") as fh:
                nb, _, _ = ndfbin.decode(fh.read())
        except Exception:  # noqa: BLE001 - a foreign format: nothing to compare
            if skipped is not None:
                skipped.append(p)
            continue
        nb.path = p
        yield nb


def verify() -> int:
    """The table read right: no stock file breaks an evaluated rule. Returns the number of violations. Fails
    (CheckError) when no stock file was read, since then it proves nothing; files it could not parse are counted."""
    rules, _ = load_table()
    bad, files, objects, skipped = 0, 0, 0, []
    for nb in stock_files(skipped=skipped):
        files, objects = files + 1, objects + len(nb.objects)
        found = violations(nb, rules, reviewed=None)
        for v in found:
            print(f"{paths.rel_source(nb.path)}: {v}")
        bad += len(found)
    check(files > 0, f"no stock ndfbin was read ({len(skipped)} skipped as unparseable) under "
                     f"{paths.extracted_root()}: `python -m modkit.core.setup check` says what is missing, and "
                     f"`python -m modkit.core.setup extract` builds it (warno-setup)")
    print(f"{files} stock files ({objects} objects), {len(skipped)} skipped as unparseable, {bad} violations")
    return bad


def _table_rows(path: Path) -> list[str]:
    """The rules of the table at `path` as printed, or [] when there is none to compare with."""
    if not path.is_file():
        return []
    try:
        rules, _ = load_table(path)
    except (CheckError, ValueError):
        return []
    return [_shown(r) for rs in rules.values() for r in rs]


def _changes(old: list[str], new: list[str], limit: int = 40) -> list[str]:
    """What a re-extract changed, for review: the removed and added rows."""
    gone, came = sorted(set(old) - set(new)), sorted(set(new) - set(old))
    out = [f"{len(gone)} rows removed, {len(came)} added since the previous table"]
    for sign, rows in (("-", gone), ("+", came)):
        out += [f"  {sign} {row}" for row in rows[:limit]]
        if len(rows) > limit:
            out.append(f"  {sign} ... {len(rows) - limit} more")
    return out


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    try:
        if args[:1] == ["extract"]:
            rules, stamp = extract(args[1] if len(args) > 1 else None)
            target = table_path()
            old = _table_rows(target)
            write_table(rules, stamp, target)
            kinds = collections.Counter(r.kind for r in rules)
            print(f"{stamp}\n{len(rules)} rules on {len({r.cls for r in rules})} classes ({dict(kinds)}) -> {target}")
            if old:
                print("\n".join(_changes(old, [_shown(r) for r in rules])))
            return 0
        if args[:1] == ["verify"]:
            return 1 if verify() else 0
        if args[:1] == ["show"]:
            rules, _ = load_table()
            for c in args[1:]:
                for r in rules.get(c, []):
                    print(_shown(r))
            return 0
    except (paths.NotConfigured, CheckError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
