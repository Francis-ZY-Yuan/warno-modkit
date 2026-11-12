"""Which WARNO builds this toolkit was verified on, and a warning when the installed game is on another one.

``VERIFIED_BUILDS`` is the one source of truth, newest last. The installed build is read by ``paths.game_build()``
(the newest data revision in the install's ``Data/PC``, read only), the same value ``setup check`` compares the
extraction against, so the two agree. The warning is only a warning: it never fails a build and changes no output.

``python -m modkit.core.gamebuild`` prints the installed and verified builds and the warning, if any. It exits 0, or
1 when no game install is configured.
"""
from __future__ import annotations

import sys

from modkit.core import paths

VERIFIED_BUILDS: tuple[str, ...] = ("201602", "210942")


def installed_build() -> str | None:
    """The newest data revision in the configured install; None when none is configured or none is found."""
    return paths.game_build()


def build_warning() -> str | None:
    """None when the installed build is unknown or verified; otherwise the one warning line."""
    build = installed_build()
    if build is None or build in VERIFIED_BUILDS:
        return None
    return (f"GAME BUILD: installed {build}; this toolkit was verified on {', '.join(VERIFIED_BUILDS)}. "
            f"Read knowledge/builds.md and knowledge/topics/game-updates.md before trusting a build.")


def main() -> int:
    build = installed_build()
    if build is None:
        try:
            paths.game_dir()
        except paths.NotConfigured as exc:
            print(exc)
            return 1
        print("no game data revision found under the configured install's Data/PC")
        return 0
    print(f"installed build: {build}\nverified builds: {', '.join(VERIFIED_BUILDS)}")
    warning = build_warning()
    if warning:
        print(warning)
    return 0


if __name__ == "__main__":
    sys.exit(main())
