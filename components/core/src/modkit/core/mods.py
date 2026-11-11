"""Installed and built mods, read back (read only): the active list, where each mod is, its own Config.ini, its packs.

* The installed mods are the folders of the mods folder (``modkit.core.install.mod_root``, where the share installer
  puts a mod), and the ``ActivatedMods`` line of its ``Config.ini`` is the active list: entries separated by ``|``, a
  ``;`` starting a comment (``activated_mods``).
* An entry names a mod the way the game writes it there (see ``modkit.core.install``): by its folder name or, for a mod
  with a non-zero ``[Properties]`` ``ID`` (a Workshop item), by that ID. ``find_mod`` resolves an entry: a folder of
  the mods folder by that name; else one whose own ``Config.ini`` holds that ID; else the Workshop item of that ID, in
  the folder Steam keeps it in (``modkit.core.paths.workshop_dir``).
* A mod's own ``Config.ini``: ``mod_id`` reads its ID as the share installer does (no leading zeros; '' for 0, none
  or no file), ``mod_name`` its ``[Properties]`` Name; ``modkit.core.install.is_gameplay`` tells a Gameplay mod.
* ``scenario_packs`` lists a mod's ``Scenarios/*.dat`` packs, and ``read_pack`` reads the entries of one that a
  filter keeps (``modkit.core.edat``).

Nothing here writes.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Callable

from modkit.core import edat, install

CONFIG = "Config.ini"
_ACTIVATED = re.compile(r"(?m)^[ \t]*ActivatedMods[ \t]*=[ \t]*([^;\r\n]*)")
_ID = re.compile(r"(?m)^[ \t]*ID[ \t]*=[ \t]*([0-9]+)")       # the share installer's Get-ModId rule
_NAME = re.compile(r"(?m)^[ \t]*Name[ \t]*=[ \t]*([^;\r\n]*)")


def _config_text(mod_dir: Path) -> str | None:
    try:
        return (Path(mod_dir) / CONFIG).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def mod_id(mod_dir: Path) -> str:
    """The mod's [Properties] ID without leading zeros, as the share installer reads it; '' for ID 0, no ID or no
    Config.ini."""
    m = _ID.search(_config_text(mod_dir) or "")
    return m.group(1).lstrip("0") if m else ""


def mod_name(mod_dir: Path) -> str:
    """The mod's [Properties] Name, else its folder's name."""
    m = _NAME.search(_config_text(mod_dir) or "")
    return (m.group(1).strip() if m else "") or Path(mod_dir).name


def activated_mods(root: Path | None = None) -> list[str] | None:
    """The entries of the ActivatedMods line of the mods folder's Config.ini (`root`, default
    modkit.core.install.mod_root()), in order; [] for no line, None for no Config.ini."""
    text = _config_text(Path(root) if root is not None else install.mod_root())
    if text is None:
        return None
    m = _ACTIVATED.search(text)
    return [e.strip() for e in m.group(1).split("|") if e.strip()] if m else []


def installed_mods(root: Path | None = None) -> list[Path]:
    """Every mod folder of the mods folder (`root`, default modkit.core.install.mod_root()), sorted by name."""
    folder = Path(root) if root is not None else install.mod_root()
    if not folder.is_dir():
        return []
    return sorted((p for p in folder.iterdir() if p.is_dir()), key=lambda p: p.name.lower())


def workshop_items(workshop: Path | None) -> list[Path]:
    """Every Workshop item folder of the Workshop content folder `workshop` (modkit.core.paths.workshop_dir), sorted."""
    if workshop is None or not Path(workshop).is_dir():
        return []
    return sorted(p for p in Path(workshop).iterdir() if p.is_dir())


def find_mod(entry: str, root: Path, workshop: Path | None) -> Path | None:
    """The folder an ActivatedMods `entry` names: the mods folder's folder of that name; else one whose own Config.ini
    ID is the entry; else the Workshop item of that ID (under `workshop`); None when none is found."""
    local = Path(root) / entry
    if local.is_dir():
        return local
    if entry.isdigit():
        wanted = entry.lstrip("0")
        for folder in installed_mods(root):
            if mod_id(folder) == wanted:
                return folder
        if workshop is not None and (Path(workshop) / entry).is_dir():
            return Path(workshop) / entry
    return None


def scenario_packs(mod_dir: Path) -> list[Path]:
    """The mod's scenario packs, Scenarios/*.dat, sorted."""
    folder = Path(mod_dir) / "Scenarios"
    return sorted(folder.glob("*.dat")) if folder.is_dir() else []


def read_pack(path: Path, keep: Callable[[str], bool]) -> list[tuple[str, bytes]]:
    """(inner path, bytes) of each entry of the pack at `path` whose inner path `keep` accepts, in index order. Raises
    edat.EdatError or OSError for a pack that does not read."""
    return [(e.path, edat.read_entry(str(path), e)) for e in edat.read_index(str(path)) if keep(e.path)]
