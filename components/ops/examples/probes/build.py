"""Build one of the probe mods.

    python build.py --content {empty,spike,spike_safe,spike2,nuke,nuke_sov} [--out DIR]

DIR defaults to probes/<content> in the build folder (`build/` beside your modkit.local.toml, or in the working
folder without one, unless you set another; see modkit.core.paths.build_root). Every gate of modkit.ops.build runs
first; any failure prints one FAILED line and exits 1.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the probes package beside this file (-I drops it)
from modkit.ops import build as ops_build  # noqa: E402
from probes import CONTENTS, profile  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    return ops_build.cli(profile.profile, CONTENTS, argv, description=__doc__.split("\n")[0],
                         default_out=profile.default_out)


if __name__ == "__main__":
    sys.exit(main())
