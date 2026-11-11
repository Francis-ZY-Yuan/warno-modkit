"""Build Operation Open Door.

    python build.py --content op [--out DIR]

DIR defaults to open-door/<content> in the build folder (`build/` beside your modkit.local.toml, or in the working
folder without one, unless you set another; see modkit.core.paths.build_root). Every gate of modkit.ops.build runs
first, then Open Door's extra gates; any failure prints one FAILED line and exits 1. Nothing is read from the
extraction or the game folder until the build runs: with neither configured, the FAILED line names the warno-setup
skill.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the opendoor package beside this file (-I drops it)
from modkit.ops import build as ops_build  # noqa: E402
from opendoor import CONTENTS, profile  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return ops_build.cli(profile.profile, CONTENTS, argv, description=__doc__.split("\n")[0],
                         default_out=profile.default_out)


if __name__ == "__main__":
    sys.exit(main())
