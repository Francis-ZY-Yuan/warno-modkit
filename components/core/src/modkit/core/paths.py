"""Where the local data lives: the stock extraction, the game install (and the Workshop folder beside it), the data
folder and the build folder.

This is the only module that knows. Lookup order for each location:

1. the environment variable (``MODKIT_EXTRACTED``, ``MODKIT_GAME_DIR``, ``MODKIT_DATA``, ``MODKIT_BUILD``);
2. ``modkit.local.toml`` (keys ``extracted``, ``game_dir``, ``data_dir`` and ``build_dir``; relative values
   are relative to the folder holding the toml), searched upward from the working folder, then upward
   from the file of the code that asked, then from this package.

The data folder holds what the toolkit derives from your own install (such as ``ndfrules.tsv``);
when it is not set it defaults to ``modkit-data`` beside the extraction folder. It is never inside a
package or a repository's tracked files.

The build folder is where builds write by default, and the only folder a rebuild may delete a previous
output in; when it is not set it defaults to ``build`` beside the ``modkit.local.toml`` that was found, else
to ``build`` in the working folder. It always has a value: a build told where to write needs no setting.

The Workshop content folder is not a setting: it is found from the game install, where Steam keeps it
(``workshop_dir``).

When any other location is not set, ``NotConfigured`` is raised; its message names the ``warno-setup`` skill.
"""
from __future__ import annotations

import os
import re
import sys
import tomllib
import unittest
from pathlib import Path

CONFIG_NAME = "modkit.local.toml"
ENV_EXTRACTED = "MODKIT_EXTRACTED"
ENV_GAME_DIR = "MODKIT_GAME_DIR"
ENV_DATA = "MODKIT_DATA"
ENV_BUILD = "MODKIT_BUILD"
DATA_NAME = "modkit-data"
BUILD_NAME = "build"


class NotConfigured(RuntimeError):
    """The extraction or the game install location is not set."""


def _not_configured(what: str, env: str, key: str) -> NotConfigured:
    return NotConfigured(
        f"{what} is not configured: set {env}, or put `{key} = \"...\"` in {CONFIG_NAME}. "
        f"Run the warno-setup skill to create it.")


def _caller_file() -> str | None:
    """File of the nearest frame outside this module."""
    frame = sys._getframe(1)
    while frame is not None:
        name = frame.f_code.co_filename
        if os.path.abspath(name) != os.path.abspath(__file__) and not name.startswith("<"):
            return name
        frame = frame.f_back
    return None


def _code_dirs() -> list[Path]:
    """Folders to search upward from after the working folder: the asking code's, then this package's."""
    out = []
    caller = _caller_file()
    if caller:
        out.append(Path(os.path.abspath(caller)).parent)
    out.append(Path(os.path.abspath(__file__)).parent)
    return out


def _find_config() -> Path | None:
    for start in [Path.cwd(), *_code_dirs()]:
        for folder in [start, *start.parents]:
            candidate = folder / CONFIG_NAME
            if candidate.is_file():
                return candidate
    return None


def local_config(root: Path | None = None) -> dict:
    """The parsed ``modkit.local.toml``: the one in ``root`` when given, else the one the lookup would use.
    An absent file reads as an empty dict."""
    config = (Path(root) / CONFIG_NAME) if root is not None else _find_config()
    if config is None or not config.is_file():
        return {}
    with open(config, "rb") as fh:
        return tomllib.load(fh)


def _setting(env: str, key: str, what: str) -> Path:
    value = os.environ.get(env)
    if value:
        return Path(value)
    config = _find_config()
    if config is not None:
        with open(config, "rb") as fh:
            raw = tomllib.load(fh).get(key)
        if raw:
            path = Path(raw)
            return path if path.is_absolute() else Path(os.path.normpath(config.parent / path))
    raise _not_configured(what, env, key)


def extracted_root() -> Path:
    """The folder holding the stock extraction."""
    return _setting(ENV_EXTRACTED, "extracted", "The stock extraction folder")


def game_dir() -> Path:
    """The WARNO install folder (read only)."""
    return _setting(ENV_GAME_DIR, "game_dir", "The WARNO game folder")


def workshop_dir() -> Path | None:
    """The game's Steam Workshop content folder, where Steam installs the Workshop items the game loads (read only):
    ``<library>/steamapps/workshop/content/<app id>``, in the Steam library that holds the game install
    (``<library>/steamapps/common/<folder>``), the app id taken from that library's ``appmanifest_<id>.acf`` whose
    installdir is the install's folder. None when the install is not configured, does not sit in a Steam library, or
    has no Workshop folder; this never raises."""
    try:
        game = game_dir()
        if game.parent.name.lower() != "common":
            return None
        steamapps = game.parent.parent
        for acf in sorted(steamapps.glob("appmanifest_*.acf")):
            m = re.search(r'"installdir"\s+"([^"]*)"', acf.read_text(encoding="utf-8", errors="replace"))
            if m and m.group(1).lower() == game.name.lower():
                folder = steamapps / "workshop" / "content" / acf.stem.removeprefix("appmanifest_")
                return folder if folder.is_dir() else None
    except (NotConfigured, OSError):
        return None
    return None


def game_build() -> str | None:
    """The current game build, read only from the install: the newest numeric folder under ``Data/PC`` (the
    data packs are named by build number). None when the install is not configured or holds no such folder;
    this never raises, so a check that wants the version can skip itself."""
    try:
        folder = game_dir() / "Data" / "PC"
        builds = [p.name for p in folder.iterdir() if p.is_dir() and p.name.isdigit()]
    except (NotConfigured, OSError):
        return None
    return max(builds, key=int) if builds else None


def data_dir() -> Path:
    """The folder for data derived from your install: ``MODKIT_DATA``, else the toml's ``data_dir``, else
    ``modkit-data`` beside the extraction folder."""
    try:
        return _setting(ENV_DATA, "data_dir", "The data folder")
    except NotConfigured:
        pass
    try:
        root = extracted_root()
    except NotConfigured:
        raise _not_configured("The data folder", ENV_DATA, "data_dir") from None
    return Path(os.path.normpath(root.parent / DATA_NAME))


def build_root() -> Path:
    """The build folder: where builds write by default, and the only folder a rebuild may delete a previous output
    in. ``MODKIT_BUILD``, else the toml's ``build_dir``, else ``build`` beside the ``modkit.local.toml`` found, else
    ``build`` in the working folder. Never raises."""
    try:
        return _setting(ENV_BUILD, "build_dir", "The build folder")
    except NotConfigured:
        pass
    config = _find_config()
    return Path(os.path.normpath((config.parent if config is not None else Path.cwd()) / BUILD_NAME))


def _skip_unless(root_fn, rel: tuple[str, ...], what: str):
    try:
        target = root_fn().joinpath(*rel)
    except NotConfigured as exc:
        return unittest.skip(str(exc))
    if target.exists():
        return unittest.skipUnless(True, "")
    return unittest.skip(f"{what} not found: {target} (see the warno-setup skill)")


def skip_unless_extracted(*rel: str):
    """Decorator for stock-data tests: skips cleanly when the extraction (or ``rel`` in it) is absent."""
    return _skip_unless(extracted_root, rel, "Extracted data")


def skip_unless_game_dir(*rel: str):
    """Decorator for tests that read the game install: skips cleanly when it (or ``rel`` in it) is absent."""
    return _skip_unless(game_dir, rel, "Game data")


def skip_unless_data(*rel: str):
    """Decorator for tests that read derived data: skips cleanly when the data folder (or ``rel`` in it) is absent."""
    return _skip_unless(data_dir, rel, "Derived data")


def _posix(path: Path) -> str:
    return str(path).replace(os.sep, "/")


def rel_source(path: str | os.PathLike) -> str:
    """Provenance string of an input file.

    Under the extraction: ``extracted/`` plus the '/'-separated path below it. Under the game install:
    the '/'-separated path below it. Anything else: the path itself, '/'-separated.
    """
    p = Path(os.path.abspath(path))
    try:
        below = _posix(p.relative_to(os.path.abspath(extracted_root())))
        return "extracted" if below == "." else "extracted/" + below
    except (ValueError, NotConfigured):
        pass
    try:
        return _posix(p.relative_to(os.path.abspath(game_dir())))
    except (ValueError, NotConfigured):
        return _posix(p)
