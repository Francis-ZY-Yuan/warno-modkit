"""Build Operation Twin Strike.

    python build.py --content op [--out DIR] [--stock-names]

DIR defaults to twin-strike/<content> in the build folder (`build/` beside your modkit.local.toml, or in the working
folder without one, unless you set another; see modkit.core.paths.build_root). Every gate of modkit.ops.build runs
first, then Twin Strike's extra gates; any failure prints one FAILED line and exits 1. Nothing is read from the
extraction or the game folder until the build runs: with neither configured, the FAILED line names the warno-setup
skill.

--stock-names builds the deck's fallback (twinstrike.forces.STOCK_NAMES): its pages and platoons carry names of the
game's own, and the build ships neither of the op's deck dictionaries. Build it into another --out: it is the retry if
a launch of the default build shows a dictionary error naming one of the deck's ts_* tokens.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))  # the twinstrike package beside this file (-I drops it)
from modkit.ops import build as ops_build  # noqa: E402
from twinstrike import CONTENTS, forces, profile  # noqa: E402

STOCK_NAMES_FLAG = "--stock-names"


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if STOCK_NAMES_FLAG in argv:
        argv.remove(STOCK_NAMES_FLAG)
        forces.STOCK_NAMES = True   # read when the build makes the profile and the content
    return ops_build.cli(profile.profile, CONTENTS, argv, description=__doc__.split("\n")[0],
                         default_out=profile.default_out)


if __name__ == "__main__":
    sys.exit(main())
