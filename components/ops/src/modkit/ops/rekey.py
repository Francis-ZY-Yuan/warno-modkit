"""Re-keying a stock scenario's files to a new id: the paths, the table edits, and the rows the dump gate checks them by.

Since build 210942 a scenario's Definition pack holds, for each kind of file (``GDScript``, ``MapConfiguration``,
``ScenarioInfo``, ``ScenarioLoader``, ``TrophyDef``), three entries under ``NDF/Scenarios/<scenario>/`` (``def_path``):
``<Kind>.txn`` (the CNDF file itself), ``<Kind>.txn.tag`` (a ``TNDFTagFile``: a ConfigHash and a map of the source
files it was cooked from, by game path, to their hashes) and ``<Kind>.dbg`` (its source map, one line per object:
``modkit.core.dbg``). Build 201602 had ``NDF/Scenarios/<Kind>/<scenario>.ndfbin`` and ``.tag`` instead.

A clone of a stock Operation rewrites its Definition files: the scenario id in STRG/TRAN entries (``replace_text``),
whole entries such as the map name (``swap_exact``), the scenario GUID, the menu tokens and a few plain properties
(``ScalarEdit``); in each ``.txn.tag`` and ``.dbg``, the scenario id of the source file paths (``rekey_tag``,
``rekey_dbg``). The tag's hashes stay stock's: they are the cook's own, and nothing here can recompute them. A
``Rekey`` holds every value of one such clone; ``rekey_definition``, ``rekey_tag`` and ``rekey_dbg`` apply it, and
``dump_rows`` lists the changes it may make. ``modkit.ops.gates.check_dump_diff`` then compares typed dumps (a .dbg's
text) line by line: every new line must equal the stock line with the applicable ``DumpRow`` patterns applied.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Mapping

from modkit.core import dbg, ndfbin
from modkit.core.gates import check
from modkit.core.ndfbin import Value
from modkit.ops.graph import all_values, decode, encode


TXN, TAG, DBG = "txn", "txn.tag", "dbg"   # a Definition kind's three entries: the file, its tag and its source map
DEF_EXTS = (TXN, TAG, DBG)
TAG_CLASS = "TNDFTagFile"                  # a .txn.tag's one object (all 167 stock tags of a 210942 extraction)
DEF_PATH = re.compile(r"NDF/Scenarios/([^/]+)/([^/.]+)\.(txn|txn\.tag|dbg)")


def def_path(kind: str, ext: str, scenario: str) -> str:
    """A Definition entry's inner path: NDF/Scenarios/<scenario>/<kind>.<ext>, `ext` one of DEF_EXTS (build 210942)."""
    check(ext in DEF_EXTS, f"{kind}.{ext}: a Definition entry is a .{TXN}, .{TAG} or .{DBG}")
    return f"NDF/Scenarios/{scenario}/{kind}.{ext}"


def def_entry(inner: str) -> tuple[str, str, str] | None:
    """(scenario, kind, ext) of a Definition entry's inner path (def_path), or None for any other path."""
    m = DEF_PATH.fullmatch(inner)
    return (m[1], m[2], m[3]) if m else None


def repath(inner: str, source: str, scenario: str) -> str:
    """Swap the `source` path component of `inner` for `scenario`."""
    parts = inner.split("/")
    check(source in parts, f"{inner}: no {source} component to re-key")
    return "/".join(scenario if p == source else p for p in parts)


def replace_text(table: list[bytes], old: str, new: str) -> int:
    """Substring-replace `old` in a STRG/TRAN table in place; return the number of entries changed."""
    o, n = old.encode("latin-1"), new.encode("latin-1")
    hits = 0
    for k, s in enumerate(table):
        if o in s:
            table[k] = s.replace(o, n)
            hits += 1
    return hits


def swap_exact(table: list[bytes], swaps: Mapping[str, str]) -> int:
    hits = 0
    for k, s in enumerate(table):
        new = swaps.get(s.decode("latin-1"))
        if new is not None:
            table[k] = new.encode("latin-1")
            hits += 1
    return hits


@dataclass(frozen=True)
class ScalarEdit:
    """One plain-property re-keying row: exactly one site in `kind` holds `old`."""
    kind: str
    cls: str
    prop: str
    old: Value
    new: Value


@dataclass(frozen=True)
class DumpRow:
    """A re-keying row as seen in a typed dump: `pattern` in a stock line becomes `repl`."""
    label: str
    kinds: tuple[str, ...] | None  # entries it may touch (None = any)
    pattern: str
    repl: str


@dataclass(frozen=True)
class Rekey:
    """Every value of one clone's re-keying: the template it starts from and what each Definition file becomes."""
    source: str                     # the template's scenario id
    scenario: str                   # the new id
    guid_source: bytes              # the template's scenario GUID (MapConfiguration, ScenarioInfo)
    guid: bytes                     # the new scenario GUID
    renames: Mapping[str, str]      # menu loc tokens, template's -> new (MapConfiguration)
    token_prefix: str               # the template's menu token prefix: every such token must be renamed
    scalar_edits: tuple[ScalarEdit, ...]
    map_strings: Mapping[str, str]  # whole STRG entries (e.g. ScenarioInfo.RootDatapackName); {} keeps the map
    map_trans: Mapping[str, str]    # whole TRAN entries (e.g. the EnvironmentSettings import's map name)
    deck_swap: Mapping[str, str]    # whole MapConfiguration STRG entries (LocalPlayerDeck), each hit exactly once
    kinds: tuple[str, ...]          # the Definition kinds shipped (re-keyed or generated)


# The Definition kinds holding the scenario GUID once each (TChallengeMapInfo.GUID, TScenarioDefinition.GUID).
GUID_KINDS = ("MapConfiguration", "ScenarioInfo")


def rekey_definition(raw: bytes, kind: str, rk: Rekey) -> bytes:
    """Apply `rk` to a stock Definition ndfbin of `kind`: the id in STRG/TRAN, the map swaps, (MapConfiguration) the
    deck swaps, the GUID (once in GUID_KINDS, nowhere else), the menu tokens and the scalar edits."""
    nb, _, image = decode(raw)
    check(ndfbin.encode_image(nb) == image, f"{kind}: stock image does not round-trip")
    replace_text(nb.strings, rk.source, rk.scenario)
    replace_text(nb.trans, rk.source, rk.scenario)
    swap_exact(nb.strings, rk.map_strings)
    swap_exact(nb.trans, rk.map_trans)
    if kind == "MapConfiguration":
        hits = swap_exact(nb.strings, rk.deck_swap)
        check(hits == len(rk.deck_swap), f"{kind}: {hits} LocalPlayerDeck strings swapped, expected {len(rk.deck_swap)}")
    for table, what in ((nb.strings, "STRG"), (nb.trans, "TRAN")):
        check(len(set(table)) == len(table), f"{kind}: re-keying made duplicate {what} entries")

    old_locs = {ndfbin.token_hash(o): ndfbin.token_hash(n) for o, n in rk.renames.items()}
    guids = 0
    for _, _, x in all_values(nb):
        if x.tag == 0x1A and x.v == rk.guid_source:
            x.v = rk.guid
            guids += 1
        elif x.tag == 0x1D:
            key = int.from_bytes(x.v, "little")
            if key in old_locs:
                x.v = old_locs[key].to_bytes(8, "little")
            tok = ndfbin.token_unhash(key) or ""
            check(not tok.startswith(rk.token_prefix) or key in old_locs, f"{kind}: unmapped token {tok}")
    want = 1 if kind in GUID_KINDS else 0
    check(guids == want, f"{kind}: {guids} GUID sites, expected {want}")

    for ed in rk.scalar_edits:
        if ed.kind != kind:
            continue
        sites = [(ob, k) for ob in nb.objects if nb.cname(ob.cls) == ed.cls
                 for k, (pi, v) in enumerate(ob.props) if nb.pname(pi) == ed.prop and v == ed.old]
        check(len(sites) == 1, f"{kind} {ed.cls}.{ed.prop}: {len(sites)} sites hold {ed.old}, expected 1")
        ob, k = sites[0]
        ob.props[k] = (ob.props[k][0], ed.new)
    return encode(nb, kind)


def rekey_tag(raw: bytes, kind: str, rk: Rekey) -> bytes:
    """A stock .txn.tag re-keyed: the source paths of its one TNDFTagFile (ScenariosData:/<source>/...) to the new id,
    at least one; its ConfigHash and source hashes kept as stock's."""
    nb, _, image = decode(raw)
    what = f"{kind}.{TAG}"
    check(ndfbin.encode_image(nb) == image, f"{what}: stock image does not round-trip")
    classes = [nb.cname(ob.cls) for ob in nb.objects]
    check(classes == [TAG_CLASS], f"{what}: holds {classes}, not one {TAG_CLASS}")
    check(replace_text(nb.strings, rk.source, rk.scenario) >= 1, f"{what}: names no {rk.source} source file")
    left = [t.decode("latin-1") for t in nb.strings + nb.trans if rk.source.encode("latin-1") in t]
    check(not left, f"{what}: {rk.source} left in {left}")
    return encode(nb, what)


def rekey_dbg(raw: bytes, kind: str, rk: Rekey, objects: int) -> bytes:
    """A stock .dbg re-keyed: the id wherever it stands (a source path ScenariosData:/<source>/..., a name; a map of
    template files only, as Survivors' ScenarioLoader's, names none), every line kept in its place. The re-keyed .txn
    beside it keeps stock's objects in order, so the map still holds one line per object: `objects`
    (modkit.core.dbg)."""
    text = dbg.read_text(raw)
    lines = dbg.read(raw)
    check(len(lines) == objects, f"{kind}.{DBG}: {len(lines)} lines for {objects} objects")
    return dbg.write_text(text.replace(rk.source, rk.scenario))


def generated_dbg(raw: bytes, scenario: str, source: str) -> bytes:
    """The source map of a generated .txn `raw`: one line per object in object order, each named as stock names it
    (an exported object by its export path's last component, any other unnamed), at `source` (a game path under the
    scenario's ScenariosData folder), line n for object #n-1 of the typed dump, column 1."""
    nb, _, _ = decode(raw)
    names = {i: path.rsplit("/", 1)[-1] for path, i in ndfbin.tree_paths(nb, nb.exports)}
    check(source.startswith(f"ScenariosData:/{scenario}/"), f"{source}: not under ScenariosData:/{scenario}/")
    return dbg.write([dbg.Line(names.get(i, ""), source, i + 1, 1) for i in range(len(nb.objects))])


def dump_rows(rk: Rekey) -> list[DumpRow]:
    """Every typed-dump (or .dbg text) change rekey_definition, rekey_tag and rekey_dbg may make with `rk`, as (label,
    entries it may touch, pattern, replacement). An entry is named by its kind: '<Kind>' for the .txn,
    '<Kind>.txn.tag' and '<Kind>.dbg' (gates.dump_kind); the id row covers the tags' and source maps' paths."""
    typed = ndfbin.Dumper(ndfbin.NdfBin(), typed=True)
    rows = [DumpRow(f"id {rk.source} -> S", None, re.escape(rk.source), rk.scenario),
            DumpRow("GUID -> G", GUID_KINDS, re.escape(ndfbin.fmt_guid(rk.guid_source)), ndfbin.fmt_guid(rk.guid))]
    rows += [DumpRow(f"loc {o} -> {n}", ("MapConfiguration",), re.escape(f"loc'{o}'"), f"loc'{n}'")
             for o, n in rk.renames.items()]
    rows += [DumpRow(f"{e.prop} {e.old.v} -> {e.new.v}", (e.kind,),
                     re.escape(f"{e.prop} = {typed.val(e.old, 0)}") + "$", f"{e.prop} = {typed.val(e.new, 0)}")
             for e in rk.scalar_edits]
    rows += [DumpRow(f"map {o} -> {n}", ("ScenarioInfo",), re.escape(f"'{o}'"), f"'{n}'")
             for o, n in rk.map_strings.items()]
    rows += [DumpRow(f"map EnvironmentSettings {o} -> {n}", ("MapConfiguration",),
                     re.escape(f"EnvironmentSettings/{o}") + r"\b", f"EnvironmentSettings/{n}")
             for o, n in rk.map_trans.items()]
    rows += [DumpRow(f"deck {o} -> {n}", ("MapConfiguration",), re.escape(f"'{o}'"), f"'{n}'")
             for o, n in rk.deck_swap.items()]
    return rows
