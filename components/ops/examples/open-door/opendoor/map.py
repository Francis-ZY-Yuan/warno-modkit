"""Where Open Door puts things on Geisa: its named points, in minimap pixels.

Positions are minimap pixels (768 x 1024): one is 2560 world units on both axes, with no flip
(modkit.ops.maps.GEISA.px_to_world). POINTS is every named point the mission's design and its build use: the places
the probes use too, read from the shared table (modkit.ops.maps.GEISA_POINTS), and Open Door's own below. The
mission's build points (Starts, lane waypoints, the kill zone) are opendoor.op's POINTS_OP, each with its reason.

`python -m opendoor.map overlay OUT.png` (from this example's folder) draws every point and the playable ring on
Geisa's Preview picture, for review.
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from modkit.core import paths
from modkit.ops.maps import GEISA, GEISA_POINTS
from modkit.ops.shapes import Minimap

# Open Door's own named points: the design's counter-recon screen posts, the anvil's ends and the NATO corner battery.
# Each sits where the storyline map draws it, checked on the Minimap and Preview and moved at most 20 px where it was
# off a road or clearing (the reason beside it).
OWN_POINTS: dict[str, tuple[float, float]] = {
    "SCREEN_N": (440, 177), "SCREEN_C": (470, 326), "SCREEN_SW": (449, 692), "SCREEN_SE": (593, 683),
    "ANVIL_N": (200, 298), "ANVIL_S": (98, 792),
    "CORNER_NATO": (40, 1000),  # on the forest track that runs N-S at x 38..43 here (24 px west was dense forest)
}
POINTS: dict[str, tuple[float, float]] = {**GEISA_POINTS, **OWN_POINTS}
MAP = Minimap(GEISA, POINTS)


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    draw = sub.add_parser("overlay", help="draw POINTS and the playable ring on Geisa's Preview")
    draw.add_argument("out", help="the PNG to write")
    args = ap.parse_args(argv)
    marks = {name: px for name, px in POINTS.items() if name != "PL_BLUE"}  # PL_BLUE sits on VILLAGE_E's label
    try:
        ring = [GEISA.world_to_px(p) for p in GEISA.playable_polygon()]
        print(GEISA.render_overlay(args.out, marks, [ring]))
    except (paths.NotConfigured, OSError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
