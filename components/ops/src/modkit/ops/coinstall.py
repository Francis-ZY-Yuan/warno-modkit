"""The co-install check: what every Operation must keep unique, across the mods a player runs at once.

    python -m modkit.ops.coinstall [--all] [--build DIR ...] [--mods DIR] [--workshop DIR]

A build's gates see that build alone [[check-against-every-active-mod]]; this check reads every mod a player would
run together and the stock Operations, read only, and fails (exit 1, one ``FAILED:`` line per clash naming both sides
and the value) when two of them share:

* a non-zero menu order (``OrderToChainMission``) in the Operations menu's map pack: the game stops at start on a
  duplicate [[operation-menu-registration]]; 0 means no order and never clashes;
* a MapConfiguration GUID (an Operations menu entry's);
* a scenario id, the name every pack, path and folder of a scenario is keyed by (``Scenarios/<scenario>_*.dat``);
* a mod folder, when two checked mods would install into one.

The stock side is ``modkit.ops.gates.stock_operations``: the menu-order gate's reader, which needs the extraction.

**Which mods.** By default the active list: every ``ActivatedMods`` entry of the mods folder's ``Config.ini``
(``modkit.core.mods``), each found as the game names it, a local folder by name or a Workshop item by its ID (in the
Workshop folder Steam keeps beside the game, ``modkit.core.paths.workshop_dir``). ``--all`` checks every installed
mod and every Workshop item instead. ``--build DIR`` (repeatable) adds a built mod folder as if it were active; it
replaces an installed mod of the same folder or ID, as installing it would. An entry that cannot be found on disk is a
``WARNING`` naming it, never skipped silently.

**A Workshop item's own Config.ini** is read like a local mod's: its ``[Properties]`` Name labels it, and its ID is
compared with the item's folder (Steam names the folder by the item's ID; a different or zero ID in the file is a
``WARNING``, since the game's list may then name the mod by its folder). A Gameplay mod (cluster lines under
``[Config]``, or a Gameplay file: ``modkit.core.install.is_gameplay``) is a ``WARNING``: while one is active, no
Operation starts [[gameplay-mod-relaunch]].

**Text tokens** shared between two mods are a ``WARNING``, never a failure: the game rejects some duplicate
localisation registrations, but which (per dictionary, per language, or per mod) is not known yet. The charset row,
which every dictionary holds (stock's included), and the empty token are ignored.

Nothing is written: not the mods folder, its Config.ini, nor any Workshop folder.
"""
from __future__ import annotations

import argparse
import struct
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, Sequence

from modkit.core import edat, install, mods, ndfbin, paths, trad
from modkit.core.gates import CheckError
from modkit.ops.gates import StockOperation, menu_entries, stock_operations
from modkit.ops.rekey import TXN, def_entry

MAP_CONFIG = "MapConfiguration"                   # the Definition kind the Operations menu is read from
OLD_MAP_CONFIG = "NDF/Scenarios/MapConfiguration/"  # where a build for 201602 put it, which 210942 never reads
IGNORED_KEYS = frozenset({trad.CHARSET_KEY, 0})   # the charset row every dictionary holds, and the empty token
EXAMPLES = 5                                      # shared token keys named per pair of mods


@dataclass
class Menu:
    """One Operations menu entry of a mod: its scenario, its menu order and its MapConfiguration GUID."""
    scenario: str
    order: int | None
    guid: bytes | None


@dataclass
class Mod:
    """What the check reads of one mod: where it is, how it is named, its scenarios, menu entries and text keys."""
    label: str                          # its name and where it is from, for messages
    folder: Path
    kind: str                           # "local", "workshop" or "build"
    scenarios: set[str] = field(default_factory=set)
    menus: list[Menu] = field(default_factory=list)
    keys: dict[int, set[str]] = field(default_factory=dict)   # token key -> the dictionaries holding it
    warnings: list[str] = field(default_factory=list)


def read_mod(folder: Path, kind: str) -> Mod:
    """Read the mod at `folder`: its scenarios (from its pack names), the Operations menu entries of its
    MapConfigurations (NDF/Scenarios/<scenario>/MapConfiguration.txn, where build 210942 looks for them) and the keys
    of its dictionaries. A pack that does not read, a Workshop item whose Config.ini ID is not its folder's, a Gameplay
    mod, and a MapConfiguration in build 201602's layout (one the game no longer lists) become warnings."""
    folder = Path(folder)
    name = mods.mod_name(folder)
    mod = Mod(f"{name} ({kind}{'' if name == folder.name else ' ' + folder.name})", folder, kind)
    if not (folder / mods.CONFIG).is_file():
        mod.warnings.append(f"{mod.label}: no {mods.CONFIG}")
    elif install.is_gameplay(folder):
        mod.warnings.append(f"{mod.label}: a Gameplay mod; while it is active, no Operation starts")
    if kind == "workshop" and mods.mod_id(folder) != folder.name.lstrip("0"):
        mod.warnings.append(f"{mod.label}: its Config.ini ID is {mods.mod_id(folder) or '0'}, not its Workshop item "
                            f"{folder.name}")
    for pack in mods.scenario_packs(folder):
        mod.scenarios.add(pack.stem.rsplit("_", 1)[0])
        try:
            entries = mods.read_pack(pack, lambda p: is_menu_file(p) or p.startswith(OLD_MAP_CONFIG)
                                     or p.endswith(".dic"))
        except (edat.EdatError, OSError) as exc:
            mod.warnings.append(f"{mod.label}: {pack.name} does not read ({exc})")
            continue
        for inner, raw in entries:
            try:
                if inner.endswith(".dic"):
                    for key, _ in trad.read_dic(raw):
                        mod.keys.setdefault(key, set()).add(inner)
                elif inner.startswith(OLD_MAP_CONFIG):
                    mod.warnings.append(f"{mod.label}: {pack.name}:{inner} is a build 201602 MapConfiguration, which "
                                        f"this game build never reads: its Operation is not listed until the mod is "
                                        f"rebuilt")
                else:
                    scenario = def_entry(inner)[0]
                    for entry in menu_entries(ndfbin.decode(raw)[0]):
                        mod.menus.append(Menu(scenario, entry.order, entry.guid))
            except (trad.TradError, ValueError, KeyError, IndexError, struct.error) as exc:
                mod.warnings.append(f"{mod.label}: {pack.name}:{inner} does not read ({exc})")
    return mod


def is_menu_file(inner: str) -> bool:
    """Whether a Definition pack's entry `inner` is a scenario's MapConfiguration.txn, the file the Operations menu is
    built from (modkit.ops.gates.SCANNED_KINDS)."""
    entry = def_entry(inner)
    return entry is not None and entry[1:] == (MAP_CONFIG, TXN)


def clashes(checked: Sequence[Mod], stock: Iterable[StockOperation]) -> list[str]:
    """One line per clash between two checked mods, or a mod and a stock Operation (`stock`): a non-zero menu order,
    a MapConfiguration GUID, a scenario id or a mod folder held twice."""
    stock = tuple(stock)
    out: list[str] = []

    def held(what: str, owners: dict, value: str) -> None:
        if len(owners) > 1:
            out.append(f"{what} {value} is held by {' and '.join(owners)}")

    orders: dict[int, dict[str, None]] = defaultdict(dict)
    guids: dict[bytes, dict[str, None]] = defaultdict(dict)
    for op in stock:
        orders[op.order][f"the stock Operation {op.scenario}"] = None
        if op.guid:
            guids[op.guid][f"the stock Operation {op.scenario}"] = None
    for mod in checked:
        for menu in mod.menus:
            if menu.order:   # 0 (or none) is no order, never a duplicate
                orders[menu.order][f"{menu.scenario} of {mod.label}"] = None
            if menu.guid:
                guids[menu.guid][f"{menu.scenario} of {mod.label}"] = None
    for order, owners in sorted(orders.items()):
        held("OrderToChainMission", owners, str(order))
    for guid, owners in sorted(guids.items()):
        held("the MapConfiguration GUID", owners, ndfbin.fmt_guid(guid))
    scenarios: dict[str, dict[str, None]] = defaultdict(dict)
    for op in stock:
        scenarios[op.scenario][f"the stock Operation {op.scenario}"] = None
    for mod in checked:
        for scenario in mod.scenarios:
            scenarios[scenario][mod.label] = None
    for scenario, owners in sorted(scenarios.items()):
        held("the scenario id", owners, scenario)
    folders: dict[str, dict[str, None]] = defaultdict(dict)
    for mod in checked:
        folders[mod.folder.name.lower()][f"{mod.label} in {mod.folder.parent}"] = None
    for name, owners in sorted(folders.items()):
        held("the mod folder", owners, name)
    return out


def shared_tokens(checked: Sequence[Mod]) -> list[str]:
    """One warning line per pair of mods whose dictionaries share token keys (IGNORED_KEYS aside), naming up to
    EXAMPLES of them."""
    out = []
    for i, a in enumerate(checked):
        for b in checked[i + 1:]:
            shared = sorted(set(a.keys) & set(b.keys) - IGNORED_KEYS)
            if shared:
                names = ", ".join(trad._key_name(k) for k in shared[:EXAMPLES])
                out.append(f"{a.label} and {b.label} share {len(shared)} text token keys ({names}"
                           + (", ..." if len(shared) > EXAMPLES else "") + ")")
    return out


def gather(root: Path, workshop: Path | None, every: bool,
           builds: Sequence[Path]) -> tuple[list[tuple[Path, str]], list[str]]:
    """The mod folders to check, with their kind ("local", "workshop" or "build"), and warnings: the active list of
    the mods folder `root` (or, with `every`, every installed mod and Workshop item), each --build folder replacing an
    installed mod of the same folder name or ID."""
    found: list[tuple[Path, str]] = []
    notes: list[str] = []
    if every:
        found += [(p, "local") for p in mods.installed_mods(root)]
        found += [(p, "workshop") for p in mods.workshop_items(workshop)]
    else:
        entries = mods.activated_mods(root)
        if entries is None:
            notes.append(f"no {mods.CONFIG} in {root}: no mod is active")
        for entry in entries or ():
            folder = mods.find_mod(entry, root, workshop)
            if folder is None:
                notes.append(f"the active mod {entry} is not on disk (not in {root}"
                             + (f", nor in the Workshop folder {workshop}" if workshop is not None else
                                "; no Workshop folder found") + "): not checked")
                continue
            found.append((folder, "workshop" if workshop is not None and folder.parent == Path(workshop) else "local"))
    for build in builds:
        build = Path(build)
        ident = mods.mod_id(build)
        kept = []
        for folder, kind in found:
            if folder.name.lower() == build.name.lower() or (ident and mods.mod_id(folder) == ident):
                notes.append(f"--build {build} replaces the installed {folder.name}")
            else:
                kept.append((folder, kind))
        found = kept + [(build, "build")]
    return found, notes


def run(root: Path, workshop: Path | None, every: bool, builds: Sequence[Path]) -> int:
    """The check: print what each mod holds, the warnings and one FAILED line per clash; 0 when nothing clashes."""
    found, notes = gather(root, workshop, every, builds)
    checked = [read_mod(folder, kind) for folder, kind in found]
    for mod in checked:
        menus = "; ".join(f"{m.scenario}: order {m.order}, GUID {ndfbin.fmt_guid(m.guid) if m.guid else 'none'}"
                          for m in mod.menus) or "no Operation"
        print(f"{mod.label}: {len(mod.scenarios)} scenarios; {menus}; {len(set(mod.keys) - IGNORED_KEYS)} text keys")
    for line in notes + [w for mod in checked for w in mod.warnings] + shared_tokens(checked):
        print(f"WARNING: {line}")
    try:
        stock = stock_operations()
    except (paths.NotConfigured, CheckError) as exc:
        print(f"FAILED: the stock Operations could not be read: {exc}")
        return 1
    bad = clashes(checked, stock)
    for line in bad:
        print(f"FAILED: {line}")
    if bad:
        return 1
    print(f"ok: {len(checked)} mods and the {len({op.scenario for op in stock})} stock Operations share no menu order, "
          f"MapConfiguration GUID, scenario id or mod folder")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    ap.add_argument("--all", action="store_true", help="every installed mod and Workshop item, not only the active")
    ap.add_argument("--build", action="append", default=[], type=Path, metavar="DIR",
                    help="a built mod folder, checked as if it were active (repeatable)")
    ap.add_argument("--mods", type=Path, help="the mods folder (default: where the share installer installs)")
    ap.add_argument("--workshop", type=Path, help="the Workshop content folder (default: found from the game install)")
    args = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
    root = args.mods if args.mods is not None else install.mod_root()
    workshop = args.workshop if args.workshop is not None else paths.workshop_dir()
    return run(root, workshop, args.all, args.build)


if __name__ == "__main__":
    sys.exit(main())
