"""Writing and reading back a build: a scenario's packs, the read-back gate over them, and loose files under the mod
folder; and the game-build check of a mod folder already built.

    python -m modkit.ops.packs check DIR [DIR ...] [--admit CLASS.PROPERTY ...]

reads each mod folder's scenario packs (Scenarios/<scenario>_Definition.dat and _Details.dat) and runs the game-build
gates on them, as a build runs them on its own output: the Definition layout (modkit.ops.gates.check_definition_layout)
and every class and property against stock's (modkit.ops.gates.check_stock_classes). A content's admitted shapes
(Content.extra_shapes) are not in a mod folder: pass each as ``--admit CLASS.PROPERTY``. One line per scenario; a
failure prints one ``FAILED:`` line naming each failed gate and gives exit code 1. Use it on a mod built before a game
update, or one built elsewhere; nothing is written.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Iterable, Sequence

from modkit.core import edat, mods, ndfbin, paths
from modkit.core.gates import CheckError, check
from modkit.ops import gates
from modkit.ops.files import file_chunks, long_path, stream_digest
from modkit.ops.graph import decode
from modkit.ops.items import Item


def write_packs(items: list[Item], mod_root: str, scenario: str, packs: Iterable[str]) -> dict[str, str]:
    """One <mod_root>/Scenarios/<scenario>_<pack>.dat per pack of `packs` that holds items, in that order (loose items
    are write_loose's). Returns {pack: path}."""
    out = {}
    for pack in packs:
        group = [it for it in items if it.pack == pack]
        if not group:
            continue
        path = os.path.join(mod_root, "Scenarios", f"{scenario}_{pack}.dat")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        edat.write_edat_stream(path, [(it.path, it.size, it.chunks) for it in group])
        out[pack] = path
    return out


def verify_packs(items: list[Item], pack_paths: dict[str, str]) -> None:
    """Read every written pack back: entry list, CRC32, payload hash, CNDF round trip."""
    for pack, path in pack_paths.items():
        want = {it.path: it for it in items if it.pack == pack}
        entries = edat.read_index(path)
        check(sorted(e.path for e in entries) == sorted(want), f"{path}: entry list differs from the plan")
        roundtrips = 0
        for e in entries:
            check(edat.verify_entry(path, e), f"{path}: CRC32 mismatch for {e.path}")
            size, digest = stream_digest(edat.iter_entry_chunks(path, e))
            check(size == want[e.path].size and digest == want[e.path].digest,
                  f"{path}: {e.path} differs from its planned payload")
            if pack in ("Definition", "Details"):
                raw = edat.read_entry(path, e)
                if raw[:4] == b"EUG0" and raw[8:12] == b"CNDF":
                    nb, _, image = decode(raw)
                    check(ndfbin.encode_image(nb) == image, f"{path}: {e.path} does not round-trip")
                    roundtrips += 1
        total = sum(e.size for e in entries)
        print(f"  {os.path.basename(path)}: {len(entries)} entries, {total:,} B payload, "
              f"{os.path.getsize(path):,} B file; all CRC32 + SHA-256 match"
              + (f"; {roundtrips} CNDF round-trip" if roundtrips else ""))


def write_loose(items: list[Item], mod_root: str) -> list[str]:
    """Loose (unpacked) files under the mod folder, e.g. a scenario video."""
    out = []
    for it in items:
        if it.pack != "Loose":
            continue
        dest = os.path.join(mod_root, *it.path.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(long_path(dest), "wb") as fh:
            for chunk in it.chunks():
                fh.write(chunk)
        size, digest = stream_digest(file_chunks(dest))
        check(size == it.size and digest == it.digest, f"{dest}: written file differs from its source")
        out.append(dest)
        print(f"  loose {it.path}: {size:,} B; SHA-256 matches {it.source}")
    return out


# --------------------------------------------------------------------------- the game-build check of a built mod

def mod_scenarios(mod_root: str | Path) -> dict[str, dict[str, list[tuple[str, bytes]]]]:
    """{scenario: {pack ('Definition', 'Details', ...): [(inner path, bytes)]}} of the mod folder `mod_root`, from the
    pack names Scenarios/<scenario>_<pack>.dat (modkit.core.mods.scenario_packs). Assets are left unread."""
    out: dict[str, dict[str, list[tuple[str, bytes]]]] = {}
    for pack in mods.scenario_packs(Path(mod_root)):
        scenario, _, kind = pack.stem.rpartition("_")
        if kind in ("Definition", "Details"):
            out.setdefault(scenario, {})[kind] = mods.read_pack(pack, lambda _: True)
    return out


def check_mod(mod_root: str | Path, stock: gates.StockClasses, admitted: Iterable[tuple[str, str]] = ()) -> list[str]:
    """The game-build gates on a built mod folder, one line per scenario: its Definition in this build's layout
    (gates.check_definition_layout), and every class and property of its Definition and Details in `stock` or
    `admitted` (gates.check_stock_classes). Both run on every scenario; any failure raises one CheckError naming each
    failed gate."""
    found = mod_scenarios(mod_root)
    check(bool(found), f"{mod_root}: no Scenarios/<scenario>_Definition.dat or _Details.dat")
    admitted = tuple(admitted)
    lines, failed = [], []
    for scenario, packs in sorted(found.items()):
        try:
            kinds = gates.check_definition_layout(dict(packs.get("Definition", [])), scenario)
            layout = f"{kinds} Definition kinds in this build's layout"
        except CheckError as exc:
            failed.append(f"{scenario}: definition-layout: {exc}")
            layout = None
        shipped = [(f"{kind}:{inner}", raw) for kind in ("Definition", "Details") for inner, raw in packs.get(kind, [])]
        try:
            files, objects = gates.check_stock_classes(shipped, stock, admitted)
            classes = (f"every class and property of {files} files ({objects} objects) is in the {stock.files} stock "
                       f"files'" + (f" or among {len(admitted)} admitted" if admitted else ""))
        except CheckError as exc:
            failed.append(f"{scenario}: stock-classes: {exc}")
            classes = None
        if layout and classes:
            lines.append(f"{scenario}: {layout}; {classes}")
    check(not failed, "\n  ".join(failed))
    return lines


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m modkit.ops.packs", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="the game-build gates on built mod folders")
    p.add_argument("mods", nargs="+", metavar="DIR")
    p.add_argument("--admit", action="append", default=[], metavar="CLASS.PROPERTY",
                   help="a shape the content admits on purpose (its Content.extra_shapes), repeatable")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    admitted = [tuple(a.split(".", 1)) for a in args.admit]
    if any(len(a) != 2 for a in admitted):
        print("FAILED: --admit takes CLASS.PROPERTY", file=sys.stderr)
        return 1
    status = 0
    try:
        stock = gates.stock_classes()
    except (CheckError, paths.NotConfigured, OSError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    for folder in args.mods:
        try:
            for line in check_mod(folder, stock, admitted):
                print(f"{folder}: {line}")
        except (CheckError, edat.EdatError, OSError, ValueError) as exc:
            print(f"FAILED: {folder}: {exc}", file=sys.stderr)
            status = 1
    return status


if __name__ == "__main__":
    sys.exit(main())
