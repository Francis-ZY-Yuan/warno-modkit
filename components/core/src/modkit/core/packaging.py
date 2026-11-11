"""What every WARNO mod folder ships: Config.ini, Gen/Version.ndf, and the files that make a mod "Gameplay"; and
writing a mod folder with its build manifest."""
from __future__ import annotations

import os
import shutil
from pathlib import Path
from typing import Iterable, Protocol, Sequence

from modkit.core import paths
from modkit.core.gates import check

CONFIG_HEADER = "[Config] ; Used for mod compatibility check, do not modify"  # the last line of CONFIG_INI
# Same keys, comments and spacing as the Config.ini of a mod made with the game's own mod tools (LF, no BOM; the
# empty values keep their trailing space after '='). Fill `{name}` with the mod's folder name.
CONFIG_INI = "".join(line + "\n" for line in [
    "[Properties]",
    "Name = {name}",
    "Description = ",
    "TagList =  ; Mod Steam Tags, do not modify",
    "PreviewImagePath = ",
    "CosmeticOnly = 0 ; Do your mod affect gameplay or not ? If activated, the mod will not be shared when creating a lobby",
    "ID = 0 ; Mod Steam ID, do not modify",
    "Version = 0 ; Value to increment when an update in this mod is incompatible with the current version",
    "DeckFormatVersion = 0 ; At least 1 for Gameplay mods. Increment this value to invalidate all decks for this mod",
    "ModGenVersion = 201602 ; ModGen revision, do not modify",
    "",
    # Cluster=md5 lines go here when a mod changes a GFX cluster; this one changes none.
    CONFIG_HEADER,
])

# Byte-identical to Gen/Version.ndf in current (201602) Workshop mods.
VERSION_NDF = b"version is '201602'\n"

# A mod is tagged Gameplay when it ships a file under its Gen folder whose path ends with one of these (the Gameplay
# tag's FilesForTag in the game's NDF/ModManager.ndfbin). While a Gameplay mod is active, starting an Operation makes
# the game relaunch with every mod switched off, so an Operation mod ships none of them.
GAMEPLAY_FILES = (
    "GFX/Constantes.ndfbin",
    "GFX/Deck.ndfbin",
    "GFX/Depiction.ndfbin",
    "GFX/Division.ndfbin",
    "GFX/EffectCapacity.ndfbin",
    "GFX/Pawn.ndfbin",
    "GFX/Resources.ndfbin",
    "GFX/Skirmish.ndfbin",
    "GFX/TeamAlliance.ndfbin",
    "GFX/Terrains.ndfbin",
    "GFX/Unit.ndfbin",
    "GFX/UnitConstantes.ndfbin",
    "GFX/VisionRules.ndfbin",
    "GFX/Weapon.ndfbin",
    "GFX/WorldInterface.ndfbin",
    "InitialisationGameDistanceUnits.ndfbin",
)


_GAMEPLAY_LOWER = tuple(f.lower() for f in GAMEPLAY_FILES)


def is_gameplay_file(rel: str) -> bool:
    """Whether the game tags a mod that ships `rel` (its path in the mod folder, '/'-separated) Gameplay: the path is
    under Gen/ and ends with one of GAMEPLAY_FILES. Case is ignored: the game reads the mod's files through Windows
    paths, where case names no other file, so any spelling counts (the stricter reading; a Gameplay file missed costs
    the player a relaunch with every mod switched off)."""
    low = rel.lower()
    return low.startswith("gen/") and low.endswith(_GAMEPLAY_LOWER)


# --------------------------------------------------------------------------- writing a mod folder

ID_LINE = "ID = {id} ;"  # the Config.ini line holding the mod's Steam ID; CONFIG_INI writes 0, as every unpublished mod


def check_mod_id(mod_id: object) -> int:
    """`mod_id` (a mod's Steam Workshop ID, 0 until its first upload) if it is a non-negative integer that fits in a
    uint64; raises what gates.check raises otherwise (a bool is no ID)."""
    check(isinstance(mod_id, int) and not isinstance(mod_id, bool) and 0 <= mod_id < 2 ** 64,
          f"the Workshop ID {mod_id!r} is not a non-negative integer that fits in a uint64")
    return mod_id


def config_ini(mod_name: str, *, mod_id: int, extra_config_rows: Iterable[str]) -> str:
    """CONFIG_INI for the mod folder `mod_name` with ID = `mod_id` (check_mod_id), and `extra_config_rows` (whole
    lines, such as a changed cluster's '<key>=<md5>') under [Config]."""
    check_mod_id(mod_id)
    text = CONFIG_INI.format(name=mod_name)
    old = ID_LINE.format(id=0)
    check(text.count(old) == 1, "Config.ini template changed: cannot set the mod ID")
    check(text.endswith(CONFIG_HEADER + "\n"), "Config.ini template changed: it no longer ends with [Config]")
    return text.replace(old, ID_LINE.format(id=mod_id)) + "".join(row + "\n" for row in extra_config_rows)


def write_mod_files(mod_root: str, mod_name: str, *, mod_id: int, extra_config_rows: Iterable[str]) -> None:
    """The two files every mod folder holds: Config.ini (config_ini; ASCII, LF) and Gen/Version.ndf (VERSION_NDF)."""
    with open(os.path.join(mod_root, "Config.ini"), "w", encoding="ascii", newline="\n") as fh:
        fh.write(config_ini(mod_name, mod_id=mod_id, extra_config_rows=extra_config_rows))
    os.makedirs(os.path.join(mod_root, "Gen"), exist_ok=True)
    with open(os.path.join(mod_root, "Gen", "Version.ndf"), "wb") as fh:
        fh.write(VERSION_NDF)


class ManifestEntry(Protocol):
    """A shipped entry as MANIFEST.tsv lists it."""
    pack: str
    path: str
    size: int
    action: str
    source: str


def write_manifest(entries: Iterable[ManifestEntry], dropped: Iterable[tuple[str, str]], out_dir: str, *,
                   packs: Sequence[str], extra_manifest_rows: Iterable[tuple[str, str, str]]) -> str:
    """out_dir/MANIFEST.tsv, beside the mod folder so it is never installed: a header; one row per shipped entry
    (pack, inner path, bytes, action, source), by pack in `packs` order (then 'Loose') and by path; one row per
    `extra_manifest_rows` (name, action, source), a manifest row of the op's own; then one row per dropped
    source file (inner path, why). Returns its path."""
    order = (*packs, "Loose")
    path = os.path.join(out_dir, "MANIFEST.tsv")
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("pack\tinner_path\tbytes\taction\tsource\n")
        for it in sorted(entries, key=lambda i: (order.index(i.pack), i.path)):
            fh.write(f"{it.pack}\t{it.path}\t{it.size}\t{it.action}\t{it.source}\n")
        for name, action, source in extra_manifest_rows:
            fh.write(f"-\t{name}\t\t{action}\t{source}\n")
        for inner, why in dropped:
            fh.write(f"-\t{inner}\t\tdrop\t{why}\n")
    return path


def clean_out(out_dir: str, names: Iterable[str], root: str | os.PathLike | None = None) -> None:
    """Remove a previous build's folders `names` from `out_dir`; a folder not strictly inside `root` (the build tree,
    default `paths.build_root()`) is refused, never deleted. Both paths are resolved first ('..', links, case), so
    the test is on the real folders, not on how they were spelled."""
    real_root = Path(root if root is not None else paths.build_root()).resolve()
    for name in names:
        target = Path(out_dir, name).resolve()
        if target.is_dir():
            check(real_root in target.parents, f"refusing to delete {target}: not under {real_root}")
            shutil.rmtree(target)
