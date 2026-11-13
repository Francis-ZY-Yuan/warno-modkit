"""What the Open Door tests share: the example (and the probes, which Open Door installs beside) on sys.path, its
profile's bindings of the shared gates, the readers the geometry and script tests use, and quiet builds. Not a test
module itself.

The examples are found from this component's own folder (a clone's components/ops, or an installed plugin's folder),
and the test builds go to a temporary folder, the profile's build root while the tests run."""
from __future__ import annotations

import atexit
import dataclasses
import shutil
import sys
import tempfile
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1]   # the ops component: its tests/, examples/, src/, ...
OPEN_DOOR = COMPONENT / "examples" / "open-door"
PROBES = COMPONENT / "examples" / "probes"
sys.path.insert(0, str(OPEN_DOOR))
sys.path.insert(0, str(PROBES))

from modkit.core import paths  # noqa: E402
from modkit.ops import build as ops_build  # noqa: E402
from modkit.ops import gates, leveldesign, testing  # noqa: E402
from modkit.ops.graph import Node  # noqa: E402
from modkit.ops.leveldesign import ZONE_FILES, LdItem  # noqa: E402
from modkit.ops.maps import GEISA  # noqa: E402
from modkit.ops.profile import Content  # noqa: E402
from modkit.ops.testing import last, prop  # noqa: E402
from modkit.ops.zones import point_in_polygon  # noqa: E402
from opendoor import CONTENTS, profile  # noqa: E402

OUT_ROOT = tempfile.mkdtemp(prefix="modkit-ops-open-door-")   # test builds, removed after each test
atexit.register(shutil.rmtree, OUT_ROOT, True)
# What the tests read: Survivors' Definition (every script's input), Geisa's Details and pictures, the game's unit
# database (the build's unit gate). A class needing one skips without it.
SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
MAP_DATA = paths.skip_unless_extracted("geisa_op", "_4x3_geisa_10vs10_CONQ_Details")
PICTURES = paths.skip_unless_extracted("basemaps", "_4x3_geisa")
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
PACT = f"$/GDScript/RootDescriptor/{profile.CAMPS['PACT']}"
JOUEUR = f"$/GDScript/RootDescriptor/{profile.CAMPS['NATO']}"
ROAD_LUMINANCE = 55   # Minimap: road pixels 55-69, built-up 70+; fields and forest below 50 (probe 2's road reading)
TRACK_LUMINANCE = 40  # Minimap: a forest track reads 43-49, the forest about 30 (op.POINTS_OP)


def build_profile():
    """Open Door's profile with OUT_ROOT as its build root, so a rebuild may clear a test build there."""
    return dataclasses.replace(profile.profile(), build_root=OUT_ROOT)


def quiet_build(content: Content, out_dir: str):
    """Open Door's build of `content` (every gate) with its report swallowed."""
    return testing.quiet_build(build_profile(), content, out_dir)


def build_main(argv: list[str]) -> int:
    """Open Door's build.py front end."""
    return ops_build.cli(build_profile, CONTENTS, argv)


def details_files(items, scenario: str = profile.SCENARIO) -> dict[str, bytes]:
    """The generated Details files of `items` under Open Door's profile, keyed to `scenario`."""
    return ops_build.details_files(profile.profile(), items, scenario)


def scenario_guid(scenario: str) -> bytes:
    return leveldesign.scenario_guid(scenario, profile.GUID_NAMESPACE)


def ld_guid(it, scenario: str) -> bytes:
    return leveldesign.ld_guid(it, scenario, profile.GUID_NAMESPACE)


def gd_tags(items, scenario: str = profile.SCENARIO):
    return leveldesign.gd_tags(items, scenario, profile.GUID_NAMESPACE)


# Open Door's settings in the shared gates (its sides, its funnel)

def check_tiers(content, roots, details) -> int:
    return gates.check_tiers(content, roots, details, profile.CAMPS["NATO"], profile.CAMPS["PACT"])


def tier_violations(tiered, roots, details):
    return gates.tier_violations(tiered, roots, details, profile.CAMPS["NATO"], profile.CAMPS["PACT"])


def zone_owner_actions(roots):
    return gates.zone_owner_actions(roots, profile.CAMPS["NATO"], profile.CAMPS["PACT"])


def check_end_funnel(roots) -> tuple[int, bool]:
    return gates.check_end_funnel(roots, (profile.END_FUNNEL, profile.END_RACE))


# --------------------------------------------------------------------------- readers

def zones_holding(details: dict[str, bytes], addon: str, p: tuple[float, float]) -> list[tuple[str, int]]:
    """(Name, alliance) of every area of the shipped `addon` zone file holding minimap point `p`."""
    x, y = GEISA.px_to_world(p)
    return [(z.name, z.alliance) for z in gates.zone_polygons(details.get(ZONE_FILES[addon]))
            if point_in_polygon(x, y, z.polygon)]


def end_px(it: LdItem) -> tuple[float, float]:
    return GEISA.world_to_px(it.end)


def cmp_count(op: Node) -> tuple[int, int]:
    """(operator, value) of a TGDOperatorIntegerCompare against a constant (Equal and 0 when omitted)."""
    kind, value = prop(op, "OperatorType"), prop(op, "Value")
    return kind.v if kind is not None else 0, value.v if value is not None else 0


def cmp_vars(cond: Node) -> tuple[str, int, str]:
    """(variable, operator, other variable) of a TGDConditionVariable comparing two variables."""
    op = prop(cond, "Operator")
    return last(prop(cond, "Variable")), cmp_count(op)[0], last(prop(op, "Variable"))


def road_steps(luminance, a: tuple[float, float], b: tuple[float, float], snap: int = 4) -> int | None:
    """The fewest 8-connected steps over road or built-up pixels of Geisa's Minimap (luminance >= ROAD_LUMINANCE) from
    `a` to `b`, each first moved to the nearest road pixel within `snap` px; None when no road joins them."""
    def ok(p: tuple[int, int]) -> bool:
        return 0 <= p[0] < GEISA.minimap_px[0] and 0 <= p[1] < GEISA.minimap_px[1] and luminance(p) >= ROAD_LUMINANCE

    def near(p: tuple[float, float]) -> tuple[int, int] | None:
        x, y = round(p[0]), round(p[1])
        hits = [(abs(dx) + abs(dy), (x + dx, y + dy)) for dx in range(-snap, snap + 1) for dy in range(-snap, snap + 1)
                if ok((x + dx, y + dy))]
        return min(hits)[1] if hits else None

    start, goal = near(a), near(b)
    if start is None or goal is None:
        return None
    seen, frontier, steps = {start}, [start], 0
    while frontier:
        if goal in seen:
            return steps
        nxt = []
        for x, y in frontier:
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    p = (x + dx, y + dy)
                    if p not in seen and ok(p):
                        seen.add(p)
                        nxt.append(p)
        frontier, steps = nxt, steps + 1
    return None
