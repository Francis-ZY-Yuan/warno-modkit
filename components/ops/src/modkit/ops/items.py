"""Build plans: one ``Item`` per output entry (pack, inner path, payload source, digest, provenance), and the plan of
a scenario cloned from a stock template: its Definition, Details and Assets packs."""
from __future__ import annotations

import csv
import fnmatch
import hashlib
import os
from dataclasses import dataclass
from typing import Callable, Iterable, Mapping, NamedTuple

from modkit.core import txntag
from modkit.core.gates import CheckError, check
from modkit.ops.files import read_file, rel_source, walk_files
from modkit.ops.graph import decode
from modkit.ops.rekey import (
    DBG, TAG, TXN, Rekey, def_path, generated_dbg, rekey_dbg, rekey_definition, rekey_tag, repath,
)

ChunkSource = Callable[[], Iterable[bytes]]


@dataclass
class Item:
    """One entry of an output pack."""
    pack: str
    path: str
    size: int
    chunks: ChunkSource
    digest: bytes            # SHA-256 of the planned payload
    action: str              # copy | rekey | tag | generate
    source: str              # provenance for MANIFEST.tsv
    stock: bytes | None = None  # stock payload of a re-keyed ndfbin/.tag (dump-diff gate)
    fixture: str | None = None  # expected-dump file of a generated ndfbin (fixture gate)


def mem_item(pack: str, path: str, payload: bytes, action: str, source: str,
             stock: bytes | None = None, fixture: str | None = None) -> Item:
    return Item(pack, path, len(payload), lambda p=payload: (p,), hashlib.sha256(payload).digest(),
                action, source, stock, fixture)


def payload(item: Item) -> bytes:
    return b"".join(item.chunks())


def read_provenance(src_dir: str) -> list[tuple[str, int]]:
    """(inner path, size) rows of a merged extract's _provenance.tsv."""
    with open(os.path.join(src_dir, "_provenance.tsv"), encoding="utf-8", newline="") as fh:
        return [(row[0], int(row[3])) for row in csv.reader(fh, delimiter="\t") if row]


def details_copy(src_dir: str, inner: str, sizes: dict[str, int]) -> Item:
    raw = read_file(os.path.join(src_dir, *inner.split("/")))
    check(inner in sizes, f"{inner}: not in {rel_source(src_dir, '_provenance.tsv')}")
    check(len(raw) == sizes[inner], f"{inner}: {len(raw)} B on disk, provenance says {sizes[inner]}")
    return mem_item("Details", inner, raw, "copy", rel_source(src_dir, inner))


# --------------------------------------------------------------------------- the build plan of a cloned scenario

Generated = tuple[bytes, str, str]  # (payload, provenance for MANIFEST.tsv, expected-dump fixture name)

# Where a generated .txn's source map (modkit.ops.rekey.generated_dbg) says its objects come from: the kind's own
# name under the scenario's Scripting folder, the folder stock's GDScript sources sit in.
GENERATED_SOURCE = "ScenariosData:/{scenario}/Scripting/{kind}.ndf"


def plan_definition(rk: Rekey, src_dir: str, generated: Mapping[str, Generated],
                    transactions: Callable[[Mapping[str, bytes]], Mapping[str, txntag.Transaction]]) -> list[Item]:
    """The Definition pack: for each of rk.kinds, the template's .txn, .txn.tag and .dbg from `src_dir` re-keyed to
    rk.scenario (rekey_definition, rekey_tag, rekey_dbg); a kind in `generated` ships that .txn instead, with the
    template's tag re-keyed and its own source map (generated_dbg at GENERATED_SOURCE). Each tag holds the ConfigHash
    of its kind's transaction: `transactions` maps the planned entries (inner path -> bytes) to {kind: transaction}
    (modkit.ops.gates.definition_transactions), and a kind it leaves out fails the plan."""
    items, tags = [], []
    for kind in rk.kinds:
        stock = {ext: read_file(os.path.join(src_dir, *def_path(kind, ext, rk.source).split("/")))
                 for ext in (TXN, TAG, DBG)}
        source = {ext: rel_source(src_dir, def_path(kind, ext, rk.source)) for ext in (TXN, TAG, DBG)}
        new = {ext: def_path(kind, ext, rk.scenario) for ext in (TXN, TAG, DBG)}
        if kind in generated:
            raw, label, fixture = generated[kind]
            items.append(mem_item("Definition", new[TXN], raw, "generate", label, fixture=fixture))
            dbg_raw = generated_dbg(raw, rk.scenario, GENERATED_SOURCE.format(scenario=rk.scenario, kind=kind))
            dbg_item = mem_item("Definition", new[DBG], dbg_raw, "generate", f"{label}: its source map")
        else:
            raw = rekey_definition(stock[TXN], kind, rk)
            items.append(mem_item("Definition", new[TXN], raw, "rekey", source[TXN], stock[TXN]))
            objects = len(decode(raw)[0].objects)
            dbg_item = mem_item("Definition", new[DBG], rekey_dbg(stock[DBG], kind, rk, objects), "rekey",
                                source[DBG], stock[DBG])
        tags.append((kind, len(items), new[TAG], stock[TAG], source[TAG]))
        items.append(dbg_item)
    known = transactions({it.path: payload(it) for it in items})
    for kind, at, inner, raw, source in reversed(tags):
        check(kind in known, f"{inner}: no data names the transaction of {kind}, so its tag's ConfigHash is unknown")
        items.insert(at, mem_item("Definition", inner, rekey_tag(raw, kind, rk, txntag.config_hash(known[kind])), "tag",
                                  source, raw))
    return items


def plan_details(layout: Iterable[tuple[str, str | None]], generated: Mapping[str, Generated]) -> list[Item]:
    """The Details pack, one entry per `layout` row (inner path, stock folder) in order: the `generated` file when
    there is one, else the stock folder's file byte for byte (details_copy). A row without a folder must be
    generated."""
    items: list[Item] = []
    sizes: dict[str, dict[str, int]] = {}
    for inner, src_dir in layout:
        if inner in generated:
            raw, source, fixture = generated[inner]
            items.append(mem_item("Details", inner, raw, "generate", source, fixture=fixture))
            continue
        check(src_dir is not None, f"{inner}: not generated, and no stock folder to copy it from")
        if src_dir not in sizes:
            sizes[src_dir] = dict(read_provenance(src_dir))
        items.append(details_copy(src_dir, inner, sizes[src_dir]))
    return items


class AssetRule(NamedTuple):
    """What a build does with a template Assets file: the first rule whose fnmatch `pattern` matches decides."""
    pattern: str
    action: str  # 'copy' (re-pathed to the new id) or 'drop'
    why: str


def asset_rule(inner: str, rules: Iterable[tuple[str, str, str]]) -> tuple[str, str]:
    """(action, why) of the first of `rules` ((pattern, action, why), AssetRule or plain) whose pattern matches."""
    for pattern, action, why in rules:
        if fnmatch.fnmatchcase(inner, pattern):
            return action, why
    raise CheckError(f"Assets file without a rule: {inner}")


def plan_assets(dics: Iterable[tuple[str, bytes, str]], src_dir: str, subtrees: Iterable[str],
                rules: Iterable[tuple[str, str, str]], source: str, scenario: str
                ) -> tuple[list[Item], list[tuple[str, str]]]:
    """The Assets pack: the generated dictionaries `dics` ((inner path, payload, provenance)), then every file under
    the `subtrees` of the template's `src_dir` by asset_rule: a copy re-pathed from `source` to `scenario`, a drop
    listed. Returns (items, dropped: (inner path, why))."""
    rules = tuple(rules)
    items = [mem_item("Assets", inner, raw, "generate", provenance) for inner, raw, provenance in dics]
    dropped = []
    for sub in subtrees:
        for inner in walk_files(src_dir, sub):
            action, why = asset_rule(inner, rules)
            if action == "drop":
                dropped.append((inner, why))
                continue
            raw = read_file(os.path.join(src_dir, *inner.split("/")))
            items.append(mem_item("Assets", repath(inner, source, scenario), raw, "copy", rel_source(src_dir, inner)))
    return items, dropped


MENU_ART = "PC/Texture/{}/MapPackAssets/Textures/{}.tgv"
"""A scenario's menu picture in its Assets, by scenario id and picture name: the file behind its MapConfiguration's
DescriptionTextureElements entry of that name (FileName ScenariosData:/<scenario>/MapPackAssets/Textures/<name>.png)."""


def menu_art(items: Iterable[Item], art: Mapping[str, tuple[str, str]], source: str, scenario: str,
             made: Mapping[str, tuple[bytes, str]] | None = None) -> tuple[list[Item], list[tuple[str, str]]]:
    """The planned Assets `items` with each menu picture `art` names (picture name -> (stock scenario, that scenario's
    Assets folder)) copied from that scenario in place of the template's: the same inner path, which the re-keyed
    MapConfiguration names, now holding the stock scenario's file byte for byte, with that file as its source. Each
    picture `made` names (picture name -> (its bytes, its source line)) ships there the same way, generated.
    Returns (items, the template's pictures given up: (inner path, why), listed with the dropped files)."""
    out, given_up = list(items), []

    def replace(name: str, raw: Callable[[], bytes], action: str, source_line: str, why: str) -> None:
        mine = MENU_ART.format(scenario, name)
        at = [k for k, it in enumerate(out) if it.pack == "Assets" and it.path == mine]
        check(len(at) == 1, f"menu art {name}: the template's {MENU_ART.format(source, name)} is not shipped, so there "
                            f"is no menu picture to replace (the asset rules must copy it)")
        out[at[0]] = mem_item("Assets", mine, raw(), action, source_line)
        given_up.append((MENU_ART.format(source, name), why))
    for name, (stock, stock_dir) in art.items():
        theirs = MENU_ART.format(stock, name)
        replace(name, lambda: read_file(os.path.join(stock_dir, *theirs.split("/"))), "copy",
                rel_source(stock_dir, theirs), f"menu art: {stock}'s {name} ships in its place")
    for name, (raw, source_line) in (made or {}).items():
        replace(name, lambda: raw, "generate", source_line, f"menu art: a generated {name} ships in its place")
    return out, given_up
