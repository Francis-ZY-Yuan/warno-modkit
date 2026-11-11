"""Re-keying a stock scenario's files to a new id: the paths, the table edits, and the rows the dump gate checks them by.

A clone of a stock Operation rewrites its Definition files: the scenario id in STRG/TRAN entries (``replace_text``),
whole entries such as the map name (``swap_exact``), the scenario GUID, the menu tokens, a few plain properties
(``ScalarEdit``) and, in each ``.tag`` sidecar, the MD5 hashes of the source file names (``tag_name_hashes``). A
``Rekey`` holds every value of one such clone; ``rekey_definition`` and ``rekey_tag`` apply it and ``dump_rows``
lists the changes it may make. ``modkit.ops.gates.check_dump_diff`` then compares typed dumps line by line: every new
line must equal the stock line with the applicable ``DumpRow`` patterns applied.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Iterable, Mapping

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.core.ndfbin import Value
from modkit.ops.graph import all_values, decode, encode


def def_path(kind: str, ext: str, scenario: str) -> str:
    """A Definition entry's inner path: NDF/Scenarios/<kind>/<scenario>.<ext>."""
    return f"NDF/Scenarios/{kind}/{scenario}.{ext}"


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


def tag_name_hashes(scenario: str, sources: Iterable[str]) -> dict[str, bytes]:
    """{source file: MD5 of 'ScenariosData:/<scenario>/<source file>'}: the first hash of each pair a scenario's .tag
    sidecars hold, for each of its `sources` (paths below the scenario's ScenariosData folder)."""
    return {f: hashlib.md5(f"ScenariosData:/{scenario}/{f}".encode("latin-1")).digest() for f in sources}


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
    tag_sources: tuple[str, ...]    # the source files the .tag sidecars name (tag_name_hashes)
    tag_dropped: tuple[str, ...]    # tag_sources named only by a dropped kind's .tag (no dump row)


# The Definition kinds holding the scenario GUID once each (TChallengeMapInfo.GUID, TScenarioLoadInfo.GUID).
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
    """A stock .tag sidecar re-keyed: its one BaseName -> Scenarios/<kind>/<scenario>, and the source-name hash of
    each of rk.tag_sources from the template's to the new id's; the rest kept."""
    nb, _, image = decode(raw)
    check(ndfbin.encode_image(nb) == image, f"{kind}.tag: stock image does not round-trip")
    check(replace_text(nb.strings, rk.source, rk.scenario) == 1, f"{kind}.tag: expected one BaseName to re-key")
    old, new = tag_name_hashes(rk.source, rk.tag_sources), tag_name_hashes(rk.scenario, rk.tag_sources)
    swap = {old[f]: new[f] for f in rk.tag_sources}
    hits = 0
    for _, _, x in all_values(nb):
        if x.tag == 0x22 and x.v[0].tag == 0x25 and x.v[0].v in swap:
            x.v[0].v = swap[x.v[0].v]
            hits += 1
    check(hits >= 1, f"{kind}.tag: no scenario source-name hash found")
    left = [x for _, _, x in all_values(nb) if x.tag == 0x25 and x.v in old.values()]
    check(not left, f"{kind}.tag: {len(left)} {rk.source} source-name hashes left")
    return encode(nb, f"{kind}.tag")


def dump_rows(rk: Rekey) -> list[DumpRow]:
    """Every typed-dump change rekey_definition and rekey_tag may make with `rk`, as (label, entries it may touch,
    pattern, replacement)."""
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
    old, new = tag_name_hashes(rk.source, rk.tag_sources), tag_name_hashes(rk.scenario, rk.tag_sources)
    rows += [DumpRow(f"tag name hash {f}", tuple(f"{k}.tag" for k in rk.kinds),
                     re.escape(f"hash16:{old[f].hex()},"), f"hash16:{new[f].hex()},")
             for f in rk.tag_sources if f not in rk.tag_dropped]
    return rows
