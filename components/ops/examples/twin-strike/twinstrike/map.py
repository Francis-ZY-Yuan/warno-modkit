"""Where Twin Strike puts things on Twin Cities: the cut, its named places, the zones, the player's arrivals and FOBs.

Positions are minimap pixels of the whole map (768 x 768): one is 2,560 world units on both axes, with no flip
(modkit.ops.maps.TWIN_CITIES.px_to_world). The op plays on CUT, a box of the stock layout SM_SU_3x3_TwinCities_03 cut
on its own AI grid [[ai-grid-tiles-playable-zone]]: CUT.items ships the box as the playable zone and the 40 tiles
inside it as the AI grid, and CUT.gate() holds both (modkit.ops.maps.Cut).

POINTS is every named place of the design (docs/design.md section 3), each checked on the Minimap's roads and the
Preview's satellite picture, and moved where it was off (the reason beside it); PATHS are the routes through them.
Every place lies inside the cut but GUN_SPAWN, where the division's batteries are created for each fire, out of the
player's sight north of it (the fire-range gate holds it there).
items() is every LevelDesign item the map gives the op:
- the one command zone, the village: the stock zone AutoName_5's polygon, Points and position, copied into a
  generated zone (VILLAGE_CZ);
- two deployment zones, generated from their boxes: Soviet (alliance 0, the player's) north, NATO (alliance 1) south;
- the player's arrivals, a reinforcement location and an aerial corridor entering at the cut's north edge, each End
  in the Soviet box, so cards bought after the launch arrive [[arrival-end-in-zone]] [[deployment-phase-recipe]];
- the player's two FOBs at FOB_W and FOB_E, pre-placed in Camp 0 as stock places a player's FOB (Marauders
  C0_FOB_UK_2, SigurdsStrike C0_FOB_TCH_1): no deck holds one.
Zone conditions find their zone by a tag's point [[zone-lookup-by-point]]: the village zone's item stands inside its
polygon, and every lane point on a road its column keeps to [[fast-move-and-attack-keeps-roads]].
CAMERA is the op's opening camera (modkit.ops.maps.OpeningCamera): a move from high over the cut down to a view of the
Soviet box and the village, then a snap to its last key, both run right after LoadingDone. Its paths ship in place of
the layout's camera paths, held to the camera gate.

`python -m twinstrike.map overlay OUT.png` (from this example's folder) draws every point, the cut, the zones, the
arrivals and the routes on Twin Cities' Preview picture, for review (never committed: it is the game's picture).
"""
from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import TWIN_CITIES, CameraKey, Cut, OpeningCamera
from modkit.ops.shapes import Minimap
from modkit.ops.zones import rect_polygon

# The cut: x 0-216, y 146-524 px, the box the design picked (cut A). Its edges name the layout's tile edges at x 0 and
# 216.125, y 145.603 and 523.603 px (Cut.box); 40 tiles cover it, up to the stock grid's 1/8 px seams.
CUT_PX = (0, 146, 216, 524)
CUT = Cut(TWIN_CITIES, CUT_PX)

# The named places (design section 3), checked on the Minimap (road pixels read 55 and up, fields 40-48, forest below
# 36) and the Preview. Moves are at most 20 px.
POINTS: dict[str, tuple[float, float]] = {
    # the objective: the village's crossroads, where its north-south road meets the middle street; the centre of the
    # stock village zone (69.1, 376.6)
    "VILLAGE": (69, 377),
    # where the assault starts: open fields in the Soviet box, between the north road (x 78) and the junction at
    # (127, 201)
    "SOV_ENTRY": (110, 190),
    # the assault: on the road that crosses the north fields, then across the fields 6 px east of the north road
    # (x 77-80), into the village from the north
    "ASSAULT_N": (110, 215),
    "ASSAULT_S": (85, 300),
    # where the NATO waves are created, one per lane. W: on the south road (y 511, x 40-64) just west of the main road;
    # the design's (60, 510) was 1 px north of its pixels. C: on the east road (x 162-164 here); the design's
    # (170, 510) was 7 px east of it, in a field.
    "NATO_ENTRY_W": (60, 511),
    "NATO_ENTRY_C": (163, 510),
    # the fire boxes, one on each lane. W: on the main road south of the village (x 64-66 here), which the west lane
    # drives straight north; the design's (75, 470) was 10 px east of it, in a field. C: on the east road (x 178-180);
    # the design's (170, 455) was 10 px west of it, on a small wood.
    "BOX_W": (65, 470),
    "BOX_C": (180, 455),
    # the centre lane's turn west: on the road that leaves the east road at (187, 412) and runs west across the stream
    # into the village's south street; the design's (150, 390) was 19 px north of it, in the field below the middle
    # street's road (y 379 here), which meets the east road only further north
    "TURN_C": (150, 409),
    # battalion 2's assembly area, the nuke zone's centre: open field west of the east road (fields x 130-163 here);
    # the design's (170, 500) was 14 px east, on a small wood (x 169-175, y 497-505) beside the road
    "ASSEMBLY": (156, 500),
    # the division artillery's first place, in the forest of the cut's north-west corner (forest from x 0 to 30),
    # outside the Soviet box: 17 px north of the design's (15, 175), where the village was 7,273 GRU off, 273 over the
    # 2S7M's 7,000 minimum, a margin a battery laid out around the point loses (a gun 10 px south of it stands 6,937
    # GRU off); here the village is 7,846 GRU off, and BOX_W 10,991 against the BM-27's 10,000. Pre-placed guns there
    # drove south and died in the first play; it is now GUN_SPAWN's fallback (below), unbuilt.
    "GUNS": (15, 158),
    # Where the division's batteries are created for each fire, then removed (design 5.4): the one point outside the
    # cut. The fire-range gate holds it to its rules, from the shipped Details and the unit database:
    # - outside the cut, inside Twin Cities' map bounds (0-768 px);
    # - north of the cut's north edge (y 145.6) by at least the longest ground vision range of every unit the player
    #   can field, so none sees it: 4,250 GRU (122 px, the MiG-23ML; every other is 3,500 or less). It stands 131.6 px,
    #   4,577 GRU, north of the edge;
    # - every fire target inside the band of each battery that fires on it: the village 12,865 GRU off, BOX W 16,074,
    #   BOX C 15,402 and ASSEMBLY 16,914, against the 2S7M's 7,000-35,000 and the BM-27's 10,000-35,000.
    # North of the cut the Minimap is dimmed (its frame lines run at x 9 and y 10-11), so the spot was read off the
    # Preview: open fields between the forest band (x 75-110) and the north-east fields, 3 px south of the frame.
    # The fallback, unbuilt: the ally camp (SovietAlly), the batteries created inside the cut's north-west corner at
    # GUNS, seen for about a minute per fire.
    "GUN_SPAWN": (140, 14),
    # the player's FOBs: open fields in the Soviet box, W between the forest-edge track (x 35) and the north road
    # (x 78), E west of the east road (x 202-205)
    "FOB_W": (62, 198),
    "FOB_E": (188, 198),
}
# The routes through them, each ending in the village.
PATHS: dict[str, tuple[str, ...]] = {
    "ASSAULT": ("ASSAULT_N", "ASSAULT_S", "VILLAGE"),               # south across the fields
    "LANE_W": ("NATO_ENTRY_W", "BOX_W", "VILLAGE"),                 # north up the main road
    "LANE_C": ("NATO_ENTRY_C", "BOX_C", "TURN_C", "VILLAGE"),       # north up the east road, then west
}
MAP = Minimap(TWIN_CITIES, POINTS)

# The village's command zone: the stock zone AutoName_5 of SM_SU_3x3_TwinCities_03 as it ships, its polygon (x 6.125
# to 132.125, y 331.603 to 421.603 px), its 2 Points and its item's position (72, 384 px), in world units. It is
# copied into a generated zone: the stock CommandZone file holds AutoName_6 (the left twin, outside the cut) and
# AutoName_8 (the crossroads, across the cut's east edge) too, and a zone file ships whole, one LevelDesign item per
# area. The generated area's Center is the same centroid, at the map's ground_z (the stock area's own z is 22,473.6).
VILLAGE_CZ = rect_polygon((15680.0, 848903.0, 338240.0, 1079303.0))
VILLAGE_CZ_AT = (184320.0, 983040.0)
VILLAGE_CZ_POINTS = 2
# The deployment boxes, inside the cut. Soviet: the stock north zone's western part (it runs y 157.6-211.6), clear of
# GUNS and the cut's west forest. NATO: the south strip, north of the cut's south edge.
SOV_DZ = (40, 158, 210, 212)
NATO_DZ = (6, 490, 210, 520)
# The player's arrivals (Start, End), entering at the cut's north edge (y 145.6), each End in the Soviet box. The
# reinforcement location runs down the north road (x 73 at y 152, x 78 from y 182), where the stock layout's own
# entry P0_AutoName_21 runs; the aerial corridor comes in over the middle of the box.
RL_N = ((73, 152), (78, 182))
AC_N = ((125, 152), (125, 180))
FOB_UNIT = "FOB_SOV"
# The opening camera [[start-camera-before-loading-done]]. The layout's own camera paths stand north of the cut (camp0
# over (186, 91) px) or off the map's south edge (camp1), so the op ships its own: right after LoadingDone the camera
# flies TS_Open in OPENING_S, then snaps to TS_Start, its last key, and the deployment phase opens there. Each key is
# given by the view it shows (CameraKey: the point it looks at, its heading, its height above ground_z and how far it
# looks down), all 40 degrees down, the pitch of stock's start cameras (BlackHorsesLastStand, Gotterdammerung and
# TheKitzingenRuse 40.0, BackhandBlow 39.7, RedJuggernaut 39.3):
# - high and wide: 720,000 above the ground over the cut's north-east, looking south-south-west at its middle, the
#   whole cut ahead (stock's highest opening views stand 754,000-781,000 up: Gotterdammerung, TheKitzingenRuse,
#   TheHydra);
# - on the way down, turning to the south;
# - the playable view: 400,000 up, facing south as the player attacks, centred on y 245 px, where the layout's own
#   camp0 view of this deployment zone centres (244.8), and on x 105, between the village (x 69) and the middle of
#   the Soviet box (x 125): the box in the near part of the view, the village beyond it. Eleven of stock's twelve
#   deployment-phase Operations hand the camera over 312,898 to 604,542 above the ground, 34.7 to 40 degrees down,
#   where their opening move ends (RunningTheGauntlet's convoy close-up, 119,565, aside); stock's lowest start camera
#   stands 376,057 up (the camera gate's floor).
# The eyes stand at (179.7, 13.5), (129.6, 39.2) and (105, 58.8) px: over the map, north of the cut.
OPENING_KEYS = (
    CameraKey((130.0, 345.0), (-0.15, 1.0), 720000.0, 40.0),
    CameraKey((112.0, 290.0), (-0.07, 1.0), 540000.0, 40.0),
    CameraKey((105.0, 245.0), (0.0, 1.0), 400000.0, 40.0),
)
# Eight seconds, easing in and out (BaseCamera's camera-path mover ramps 2 s each way). Stock's opening moves mostly
# take 5 to 20 s a path (Gotterdammerung 5, Marauders 8-12, TheKitzingenRuse 7-17, DelayedRetribution and TheHydra 20;
# RedJuggernaut's first 34, beside its dialogs).
OPENING_S = 8.0
CAMERA = OpeningCamera(CUT, "TS_Open", "TS_Start", OPENING_KEYS, OPENING_S)


def items() -> list[LdItem]:
    """Every LevelDesign item the map gives the op: the village's command zone, the two deployment zones, the player's
    arrivals and FOBs."""
    return [
        LdItem("CommandPoints", "TS_CZ_Village", *VILLAGE_CZ_AT, "CommandPoints", polygon=VILLAGE_CZ,
               points=VILLAGE_CZ_POINTS),
        MAP.zone_item("DeploymentZone", "TS_DZ_Soviet", SOV_DZ, "DeploymentZone"),
        MAP.zone_item("DeploymentZone", "TS_DZ_NATO", NATO_DZ, "DeploymentZone", alliance=1),
        MAP.arrival_item("ReinforcementLocations", "TS_RL_N", *RL_N, "ReinforcementLocation"),
        MAP.arrival_item("AerialCorridors", "TS_AC_N", *AC_N, "AerialCorridor"),
        MAP.item("Camp_0", "C0_FOB_SOV_1", "FOB_W", "Spawn", unit=FOB_UNIT),
        MAP.item("Camp_0", "C0_FOB_SOV_2", "FOB_E", "Spawn", unit=FOB_UNIT),
    ]


def overlay(out: str) -> str:
    """Writes `out`: Twin Cities' Preview with every point, the cut, the zones, the arrivals (Start to End) and the
    routes. Returns the build-log line."""
    to_px = TWIN_CITIES.world_to_px
    cut = list(map(to_px, rect_polygon(CUT.box())))
    zones = (list(map(to_px, it.polygon)) for it in items() if it.polygon)
    arrivals = ((to_px(it.start), to_px(it.end)) for it in items() if it.start is not None)
    routes = (tuple(POINTS[name] for name in route) for route in PATHS.values())
    return TWIN_CITIES.render_overlay(out, POINTS, (cut, *zones, *arrivals, *routes))


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    draw = sub.add_parser("overlay", help="draw the points, the cut, the zones, the arrivals and the routes on the "
                                          "Preview")
    draw.add_argument("out", help="the PNG to write")
    args = ap.parse_args(argv)
    try:
        print(overlay(args.out))
    except (paths.NotConfigured, OSError, CheckError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
