"""Tests for modkit.ops.zones (geometry, Details builders and readers) and the zone gates of modkit.ops.gates
(check_details_generators, check_grid, check_grid_subset, check_zone_layout, arrival_violations by side)."""
import dataclasses
import math
import os
import tempfile
import unittest

from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.gates import (
    arrival_violations, check_details_generators, check_grid, check_grid_subset, check_zone_layout, grid_gate,
    zone_layout_gate,
)
from modkit.ops.graph import Node, Str, build_graph, decode, encode, f32
from modkit.ops.leveldesign import LD_SHARED, LdItem, leveldesign_graph, zone_area
from modkit.ops.models import Zone, ZoneArea
from modkit.ops.zones import (
    area_bbox, area_name, as_f32, camera_paths_graph, heading, ia_grid, ia_grid_subset, ia_zone_graph, lerp,
    path_cache_graph, playable_zone_graph, point_in_polygon, polygon_centroid, read_ia_grid, read_playable_polygon,
    read_zone_areas, rect_polygon, zone_areas_graph,
)
from modkit.ops.items import mem_item

SQUARE = rect_polygon((0, 0, 100, 100))


class GeometryTest(unittest.TestCase):
    def test_lerp_rounds(self):
        self.assertEqual(lerp((0, 0), (10, 5), 0.5), (5, 2))  # 2.5 rounds to even
        self.assertEqual(lerp((0, 0), (10, 5), 1.0), (10, 5))

    def test_rect_polygon_is_closed(self):
        self.assertEqual(SQUARE, ((0, 0), (100, 0), (100, 100), (0, 100), (0, 0)))

    def test_heading(self):
        self.assertAlmostEqual(heading((0, 0), (0, 1)), math.pi / 2)
        self.assertAlmostEqual(heading((1, 1), (0, 1)), math.pi)

    def test_centroid(self):
        self.assertEqual(polygon_centroid(list(SQUARE)), (50.0, 50.0))
        tri = [(0, 0), (6, 0), (0, 6), (0, 0)]
        self.assertEqual(polygon_centroid(tri), (2.0, 2.0))

    def test_point_in_polygon(self):
        self.assertTrue(point_in_polygon(50, 50, list(SQUARE)))
        self.assertFalse(point_in_polygon(150, 50, list(SQUARE)))
        self.assertFalse(point_in_polygon(50, -1, list(SQUARE)))

    def test_as_f32(self):
        self.assertEqual(as_f32(0.1, 2.0), (0.10000000149011612, 2.0))


def zone_file() -> bytes:
    areas = [
        ZoneArea(SQUARE, (50.0, 50.0, 10.0), "TGameDesignAddOn_DeploymentZone",
                 [("Name", Str("DZ_A")), ("Ranking", Str("DeploymentZone")), ("GUID", Value(0x1A, bytes(16)))]),
        ZoneArea(rect_polygon((200, 0, 300, 100)), (250.0, 50.0, 10.0), "TGameDesignAddOn_CommandPoints",
                 [("Name", Str("CZ_B")), ("Points", Value(0x02, 3))], 1.5),
    ]
    return encode(build_graph(zone_areas_graph(areas), []), "zones")


class ZoneFileTest(unittest.TestCase):
    def test_round_trip(self):
        raw = zone_file()
        areas = read_zone_areas(raw)
        self.assertEqual([a.addon for a in areas],
                         ["TGameDesignAddOn_DeploymentZone", "TGameDesignAddOn_CommandPoints"])
        self.assertEqual(areas[0].prop("Name"), "DZ_A")
        self.assertEqual(areas[1].prop("Points"), 3)
        self.assertIsNone(areas[0].prop("Points"))
        self.assertIsNone(areas[0].rotation)
        self.assertEqual(areas[1].rotation, as_f32(1.5)[0])
        self.assertEqual(areas[0].polygon[0], (0.0, 0.0))
        self.assertEqual([a.zone() for a in areas], [Zone("DZ_A", SQUARE, None, 0), Zone("CZ_B", areas[1].polygon, 3, 0)])
        again = encode(build_graph(zone_areas_graph(areas), []), "zones")
        self.assertEqual(decode(again)[2], decode(raw)[2])

    def test_unexpected_area_props(self):
        bad = build_graph([Node("TMapAreaSet", [("Areas", [Node("TMapArea", [("Center", Value(0x0B, (0.0, 0.0, 0.0)))])])])], [])
        with self.assertRaises(CheckError):
            read_zone_areas(encode(bad, "bad"))


class BuilderShapeTest(unittest.TestCase):
    def test_playable_zone(self):
        (area_set,) = playable_zone_graph(list(SQUARE), (50, 50, 1))
        (area,) = area_set.props[0][1]
        self.assertEqual([n for n, _ in area.props], ["BasePolygon2D", "Center"])
        self.assertEqual(area.props[1][1], Value(0x0B, (50.0, 50.0, 1.0)))

    def test_camera_paths(self):
        (path,) = camera_paths_graph([("Start", [(1, 2, 3)], [(0, 0, -1)])])
        self.assertEqual([n for n, _ in path.props], ["PositionKeyVector", "DirectionKeyVector", "Name"])
        self.assertEqual(path.props[0][1][0].props, [("Coord", Value(0x0B, (1.0, 2.0, 3.0)))])

    def test_path_cache_navgraph_optional(self):
        c = Value(0x0B, (0.0, 0.0, 0.0))
        (holder,) = path_cache_graph([(None, "a", "b", c, c, f32(1)), (Value(0x02, 3), "a", "b", c, c, f32(2))])
        first, second = holder.props[0][1]
        self.assertEqual(first.props[0][0], "ZoneStartTag")
        self.assertEqual(second.props[0], ("NavGraph", Value(0x02, 3)))

    def test_ia_zone(self):
        pts = [Value(0x21, (0.0, 0.0)), Value(0x21, (1.0, 0.0))]
        (area_set,) = ia_zone_graph([(pts, Value(0x0B, (0.5, 0.0, 0.0)), [("Name", Str("Z0"))])])
        (area,) = area_set.props[0][1]
        self.assertEqual(area.props[2][1].cls, "TGameDesignAddOn_IAStratZoneInfos")


class GeneratorGateTest(unittest.TestCase):
    def test_unrebuildable_file_fails(self):
        """A PlayableZone with a property the generator does not write is not rebuilt, and the gate says so."""
        nb = build_graph([Node("TMapAreaSet", [("Areas", [Node("TMapArea", [
            ("BasePolygon2D", [Value(0x21, (float(x), float(y))) for x, y in SQUARE]),
            ("Center", Value(0x0B, (50.0, 50.0, 0.0))), ("Extra", Value(0x02, 1))])])])], [])
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "PlayableZone.ndfbin")
            with open(path, "wb") as fh:
                fh.write(encode(nb, "pz"))
            with self.assertRaisesRegex(CheckError, "does not rebuild it"):
                check_details_generators([path], [], [], [])

    def test_nothing_to_check(self):
        self.assertEqual(check_details_generators([], [], [], []), 0)


def stock(*rel: str) -> str:
    return os.path.join(paths.extracted_root(), "scenarios", *rel)


class StockTest(unittest.TestCase):
    @paths.skip_unless_extracted("scenarios", "challenge_HoldUntilRelieved")
    @paths.skip_unless_extracted("scenarios", "challenge_BlackHorsesLastStand")
    @paths.skip_unless_extracted("scenarios", "challenge_DelayedRetribution")
    @paths.skip_unless_extracted("scenarios", "challenge_Survivors")
    def test_generators_rebuild_stock_files(self):
        zones = [stock("challenge_BlackHorsesLastStand", "out", "PlayableZone.ndfbin")]
        cams = [stock("challenge_DelayedRetribution", "CamPaths_LevelDesign.ndfbin"),
                stock("challenge_Survivors", "CamPaths_LevelDesign.ndfbin")]
        grids = [stock("challenge_BlackHorsesLastStand")]
        deploy = [stock("challenge_HoldUntilRelieved", "out", "DeploymentZone.ndfbin"),
                  stock("challenge_HoldUntilRelieved", "out", "CommandZone.ndfbin")]
        self.assertEqual(check_details_generators(zones, cams, grids, deploy), 7)

    @paths.skip_unless_extracted("scenarios", "challenge_BlackHorsesLastStand", "out", "IAStratZone.ndfbin")
    def test_ia_grid_reader(self):
        areas, entries = read_ia_grid(stock("challenge_BlackHorsesLastStand", "out", "IAStratZone.ndfbin"),
                                      stock("challenge_BlackHorsesLastStand", "out", "IAStrat_PathCache.ndfbin"))
        self.assertGreater(len(areas), 1)
        names = {area_name(a) for a in areas}
        self.assertEqual(len(names), len(areas))
        self.assertTrue(all(e[1] in names and e[2] in names for e in entries))
        x0, y0, x1, y1 = area_bbox(areas[0])
        self.assertLess(x0, x1)
        self.assertLess(y0, y1)

    @paths.skip_unless_extracted("scenarios", "challenge_HoldUntilRelieved", "out", "DeploymentZone.ndfbin")
    def test_stock_zone_centres_are_centroids(self):
        """Every stock zone's Center x/y is its polygon's area centroid at float32 (what polygon_centroid serves)."""
        with open(stock("challenge_HoldUntilRelieved", "out", "DeploymentZone.ndfbin"), "rb") as fh:
            areas = read_zone_areas(fh.read())
        self.assertTrue(areas)
        for a in areas:
            self.assertEqual(tuple(a.center[:2]), as_f32(*polygon_centroid(list(a.polygon))))


def grid(n: int = 3, size: float = 10.0, graphs=(None, Value(0x02, 3))):
    """An n x n AI grid of size-wide tiles from (0, 0), as read_ia_grid gives it: (areas, every unordered pair of
    tiles once per navigation graph)."""
    areas = []
    for j in range(n):
        for i in range(n):
            x0, y0 = i * size, j * size
            ring = [(x0, y0), (x0 + size, y0), (x0 + size, y0 + size), (x0, y0 + size), (x0, y0)]
            areas.append(([Value(0x21, p) for p in ring], Value(0x0B, (x0 + size / 2, y0 + size / 2, 0.0)),
                          [("Name", Str(f"Z{j}_{i}"))]))
    names = [area_name(a) for a in areas]
    c, cost = Value(0x0B, (0.0, 0.0, 0.0)), f32(1.0)
    entries = [(nav, a, b, c, c, cost) for nav in graphs for k, a in enumerate(names) for b in names[k + 1:]]
    return areas, entries


class GridTest(unittest.TestCase):
    """Stock's rule for a shipped AI grid: its tiles span the playable zone, and the path cache holds every pair."""

    def test_a_grid_that_spans_its_zone_passes(self):
        areas, entries = grid()
        self.assertEqual(check_grid(areas, entries, (0, 0, 30, 30), tolerance=0), (9, 72))
        self.assertEqual(check_grid(areas, entries, (0, 0, 25, 30), tolerance=5), (9, 72))

    def test_a_grid_wider_than_its_zone_fails(self):
        """The whole map's grid under a smaller playable zone (the crash the rule comes from)."""
        areas, entries = grid()
        with self.assertRaisesRegex(CheckError, r"playable zone \(0, 0, 20, 20\): the AI grid spans "
                                                r"\(0.0, 0.0, 30.0, 30.0\), 10 world off on one side \(at most 5\)"):
            check_grid(areas, entries, (0, 0, 20, 20), tolerance=5)

    def test_a_path_cache_without_every_pair_once_fails(self):
        areas, entries = grid()
        with self.assertRaisesRegex(CheckError, r"path cache: \{None: 36, 3: 35\} entries per NavGraph for 9 tiles"):
            check_grid(areas, entries[:-1], (0, 0, 30, 30))


class GridSubsetTest(unittest.TestCase):
    """A generator's cut of a map's own AI grid for a smaller playable zone: the tiles inside it, and the path costs
    between them, on tile edges and covering it exactly."""

    def test_subset_keeps_the_tiles_inside_and_their_pairs(self):
        areas, entries = grid()
        kept, costs = ia_grid_subset(areas, entries, (0, 0, 20, 20))
        self.assertEqual([area_name(a) for a in kept], ["Z0_0", "Z0_1", "Z1_0", "Z1_1"])
        self.assertEqual(len(costs), 2 * 6)  # every unordered pair of 4 tiles, once per navigation graph
        self.assertTrue(all({e[1], e[2]} <= {"Z0_0", "Z0_1", "Z1_0", "Z1_1"} for e in costs))

    def test_a_subset_on_grid_edges_passes(self):
        areas, entries = grid()
        self.assertEqual(check_grid_subset(areas, entries, (10, 0, 30, 20)), (4, 12))
        self.assertEqual(check_grid_subset(areas, entries, (0, 0, 30, 30)), (9, 72))

    def test_edges_off_the_grid_fail(self):
        areas, entries = grid()
        with self.assertRaisesRegex(CheckError, r"playable zone \(0, 0, 25, 20\): its edges are not edges of the "
                                                r"AI grid's tiles"):
            check_grid_subset(areas, entries, (0, 0, 25, 20))

    def test_tiles_that_do_not_cover_it_fail(self):
        areas, entries = grid()
        holed = [a for a in areas if area_name(a) != "Z0_1"]
        with self.assertRaisesRegex(CheckError, r"the 3 AI tiles inside it do not cover it exactly"):
            check_grid_subset(holed, entries, (0, 0, 20, 20))

    def test_a_path_cache_without_every_pair_once_fails(self):
        """The kept grid is held to stock's rule with no tolerance."""
        areas, entries = grid()
        with self.assertRaisesRegex(CheckError, r"path cache: \{None: 7, 3: 6\} entries per NavGraph for 4 tiles, "
                                                r"want every unordered pair once"):
            check_grid_subset(areas, entries + entries[:1], (0, 0, 20, 20))


LAYOUT_NS, LAYOUT_SCENARIO, GROUND_Z = "test", "challenge_T", 10.0
BOX = (0, 0, 1000, 1000)
# Every generator convention check_zone_layout knows, as a profile that writes its zones from formulas asks for them.
CONVENTIONS = dict(margin=50, ground_z=GROUND_Z, sides=(0, 1), exact=True, dz_only=True)


def arrival(start: tuple[int, int], end: tuple[int, int], rotation: float | None = None, name: str = "RL",
            side: int | None = None) -> LdItem:
    """A reinforcement location from `start` to `end` at their midpoint, facing `end` unless `rotation`, of alliance
    `side` (None: the player's)."""
    return LdItem("ReinforcementLocations", name, *lerp(start, end, 0.5), "ReinforcementLocation",
                  rotation=heading(start, end) if rotation is None else rotation, start=start, end=end,
                  num_alliance=side)


def layout_items(**change: LdItem | None) -> list[LdItem]:
    """Two deployment zones (one per alliance), a command zone and a player reinforcement location ending in the
    player's zone, every field as the zone rules want it; `change` replaces an item (None drops it) by its Name."""
    items = {
        "DZ_P": LdItem("DeploymentZone", "DZ_P", 250, 250, "DeploymentZone", rotation=0.5,
                       polygon=rect_polygon((100, 100, 400, 400))),
        "DZ_E": LdItem("DeploymentZone", "DZ_E", 750, 750, "DeploymentZone", rotation=-2.5,
                       polygon=rect_polygon((600, 600, 900, 900)), alliance=1),
        "CZ": LdItem("CommandPoints", "CZ", 500, 200, "CommandPoints", rotation=1.0,
                     polygon=rect_polygon((450, 150, 550, 250)), points=1),
        "RL": arrival((60, 250), (200, 250)),
    }
    items.update(change)
    return [it for it in items.values() if it is not None]


def layout_files(items: list[LdItem], ground_z: float = GROUND_Z,
                 nudge: tuple[float, float] = (0.0, 0.0)) -> tuple[bytes, bytes, bytes]:
    """(LevelDesign, DeploymentZone, CommandZone) of `items`, generated as a build generates them; `nudge` moves every
    zone's Center off the exact centroid, as stock's sit."""
    ld = encode(build_graph(leveldesign_graph(items, LAYOUT_SCENARIO, LAYOUT_NS), [], LD_SHARED), "LD")

    def area(it: LdItem) -> ZoneArea:
        a = zone_area(it, LAYOUT_SCENARIO, LAYOUT_NS, ground_z)
        cx, cy, cz = a.center
        return dataclasses.replace(a, center=(cx + nudge[0], cy + nudge[1], cz))
    zones = [encode(build_graph(zone_areas_graph([area(it) for it in items if it.addon == addon]), []), addon)
             for addon in ("DeploymentZone", "CommandPoints")]
    return ld, zones[0], zones[1]


class ZoneLayoutTest(unittest.TestCase):
    """The deployment and command zones and the arrivals, read back from the shipped LevelDesign and zone files:
    stock's clauses always, a generator's conventions when asked for."""

    def strict(self, items: list[LdItem], ground_z: float = GROUND_Z, **conventions):
        """check_zone_layout with every convention on (CONVENTIONS, overridden by `conventions`)."""
        return check_zone_layout(*layout_files(items, ground_z), BOX, **{**CONVENTIONS, **conventions})

    def stock(self, items: list[LdItem], ground_z: float = GROUND_Z, nudge=(0.0, 0.0)):
        """check_zone_layout with stock's clauses only."""
        return check_zone_layout(*layout_files(items, ground_z, nudge), BOX)

    def test_a_generated_layout_passes(self):
        layout = self.strict(layout_items())
        self.assertEqual({side: [z.name for z in zones] for side, zones in layout.deployment.items()},
                         {0: ["DZ_P"], 1: ["DZ_E"]})
        self.assertEqual(sorted(name for _, name in layout.margins),
                         ["CommandPoints/CZ", "DeploymentZone/DZ_E", "DeploymentZone/DZ_P"])
        self.assertEqual(min(layout.margins), (100, "DeploymentZone/DZ_E"))
        self.assertEqual([it["Name"] for it in layout.arrivals], ["RL"])
        self.assertEqual(len(layout.items), 4)

    # --- stock's clauses

    def test_item_position_lies_in_its_polygon(self):
        moved = LdItem("DeploymentZone", "DZ_P", 450, 250, "DeploymentZone", rotation=0.5,
                       polygon=rect_polygon((100, 100, 400, 400)))
        with self.assertRaisesRegex(CheckError, r"DeploymentZone/DZ_P: item Position \(450.0, 250.0\) lies outside "
                                                r"its polygon"):
            self.stock(layout_items(DZ_P=moved))

    def test_both_copies_agree(self):
        ld, _, cz = layout_files(layout_items())
        _, dz, _ = layout_files(layout_items(DZ_E=None))
        with self.assertRaisesRegex(CheckError, r"DeploymentZone: the LevelDesign items and the Details areas differ "
                                                r"\(by GUID\)"):
            check_zone_layout(ld, dz, cz, BOX)

    def test_centre_near_the_centroid(self):
        """Stock's Centres sit within CENTROID_TOLERANCE of the area centroid; only the exact convention wants it to
        the float32."""
        self.stock(layout_items(), nudge=(0.05, -0.05))
        with self.assertRaisesRegex(CheckError, r"DeploymentZone/DZ_P: Center .* is not exactly the float32 "
                                                r"centroid \(exact\)"):
            check_zone_layout(*layout_files(layout_items(), nudge=(0.05, 0.0)), BOX, exact=True)
        with self.assertRaisesRegex(CheckError, r"DeploymentZone/DZ_P: Center .* is not the polygon's centroid"):
            self.stock(layout_items(), nudge=(0.5, 0.0))

    def test_zones_inside_the_playable_zone(self):
        wide = LdItem("DeploymentZone", "DZ_E", 750, 750, "DeploymentZone", rotation=-2.5,
                      polygon=rect_polygon((600, 600, 1100, 900)), alliance=1)
        with self.assertRaisesRegex(CheckError, r"DeploymentZone/DZ_E: bbox leaves the playable zone by 100 world"):
            self.stock(layout_items(DZ_E=wide))

    def test_an_arrival_starts_inside_the_playable_zone(self):
        with self.assertRaisesRegex(CheckError, r"ReinforcementLocations/RL: Start or End outside the playable zone"):
            self.stock(layout_items(RL=arrival((-60, 250), (200, 250))))

    def test_an_arrival_faces_its_end(self):
        self.stock(layout_items(RL=arrival((60, 250), (200, 250), rotation=0.005)))
        with self.assertRaisesRegex(CheckError, r"ReinforcementLocations/RL: Rotation 1.0 is .* rad off the "
                                                r"Start -> End heading"):
            self.stock(layout_items(RL=arrival((60, 250), (200, 250), rotation=1.0)))

    def test_an_arrival_sits_at_its_midpoint(self):
        off = LdItem("ReinforcementLocations", "RL", 140, 250, "ReinforcementLocation", rotation=0.0,
                     start=(60, 250), end=(200, 250))
        with self.assertRaisesRegex(CheckError, r"ReinforcementLocations/RL: Position \(140.0, 250.0\) is off the "
                                                r"Start -> End midpoint"):
            self.stock(layout_items(RL=off))

    def test_a_player_arrival_ends_in_a_player_zone_or_a_command_zone(self):
        self.stock(layout_items(RL=arrival((60, 200), (500, 200))))  # its End in the command zone only
        with self.assertRaisesRegex(CheckError, r"1 player arrivals end outside every player deployment zone and "
                                                r"command zone:\n  RL: End \(200, 500\) lies in no player deployment "
                                                r"zone and no command zone"):
            self.stock(layout_items(RL=arrival((60, 500), (200, 500))))

    def test_stock_clauses_ask_for_no_convention(self):
        """Unequal ground, a Center a little off, no enemy zone, a zone at the edge, a command-zone End, a Rotation a
        little off: stock has each of these, and the stock clauses pass them."""
        edge = LdItem("DeploymentZone", "DZ_P", 250, 250, "DeploymentZone", rotation=0.5,
                      polygon=rect_polygon((0, 100, 400, 400)))
        self.stock(layout_items(DZ_P=edge, DZ_E=None, RL=arrival((60, 200), (500, 200), rotation=0.004)),
                   ground_z=11.0, nudge=(0.05, 0.05))

    # --- a generator's conventions

    def test_margin(self):
        with self.assertRaisesRegex(CheckError, r"DeploymentZone/DZ_P: bbox 100 world inside the playable zone, "
                                                r"need 150 \(margin\)"):
            self.strict(layout_items(), margin=150)

    def test_ground_z(self):
        with self.assertRaisesRegex(CheckError, r"DeploymentZone/DZ_P: Center .* is not the centroid at z 10.0 "
                                                r"\(ground_z\)"):
            self.strict(layout_items(), ground_z=11.0)

    def test_sides(self):
        with self.assertRaisesRegex(CheckError, r"deployment zones for alliances \[0\], want one or more for 0 and 1 "
                                                r"and no other \(sides\)"):
            self.strict(layout_items(DZ_E=None))

    def test_exact_arrivals(self):
        with self.assertRaisesRegex(CheckError, r"ReinforcementLocations/RL: Position/Rotation are not the "
                                                r"midpoint/heading of Start -> End \(exact\)"):
            self.strict(layout_items(RL=arrival((60, 250), (200, 250), rotation=0.005)))

    def test_dz_only(self):
        """An End in a command zone only passes stock's clause and fails dz_only; so does an enemy arrival outside
        its side's deployment zone, while one inside passes."""
        with self.assertRaisesRegex(CheckError, r"1 alliance-0 arrivals end outside every deployment zone of their "
                                                r"side \(dz_only\):\n  RL: End \(500, 200\) lies in no player "
                                                r"deployment zone"):
            self.strict(layout_items(RL=arrival((60, 200), (500, 200))))
        self.strict(layout_items(RL_E=arrival((950, 750), (800, 750), name="RL_E", side=1)))
        with self.assertRaisesRegex(CheckError, r"1 alliance-1 arrivals end outside every deployment zone of their "
                                                r"side \(dz_only\):\n  RL_E: End \(950, 400\) lies in no alliance-1 "
                                                r"deployment zone, "):
            self.strict(layout_items(RL_E=arrival((990, 400), (950, 400), name="RL_E", side=1)))


class ArrivalSidesTest(unittest.TestCase):
    """arrival_violations by side: the player's (the default, stock's -1 rule) or another alliance's."""

    def test_each_side_checks_its_own_entries(self):
        items = layout_items(RL_E=arrival((950, 750), (800, 750), name="RL_E", side=1),
                             RL_X=arrival((990, 400), (950, 400), name="RL_X", side=1))
        ld, dz, cz = layout_files(items)
        self.assertEqual(arrival_violations(ld, dz, cz), ({"ReinforcementLocation": 1, "AerialCorridor": 0}, []))
        counts, bad = arrival_violations(ld, dz, None, command_zones=False, side=1)
        self.assertEqual(counts, {"ReinforcementLocation": 2, "AerialCorridor": 0})
        self.assertEqual(len(bad), 1)
        self.assertRegex(bad[0], r"^RL_X: End \(950, 400\) lies in no alliance-1 deployment zone, [\d,]+ \w+ of DZ_E$")

    def test_either_side_goes_to_the_zone_it_ends_in(self):
        """NumAlliance -1 (stock multiplayer) is the player's unless its End lies only in another alliance's zone."""
        items = layout_items(RL=arrival((60, 250), (200, 250), side=-1),
                             RL_E=arrival((950, 750), (800, 750), name="RL_E", side=-1))
        ld, dz, cz = layout_files(items)
        self.assertEqual(arrival_violations(ld, dz, None, command_zones=False)[0]["ReinforcementLocation"], 1)
        self.assertEqual(arrival_violations(ld, dz, None, command_zones=False, side=1)[0]["ReinforcementLocation"], 1)
        check_zone_layout(ld, dz, cz, BOX, dz_only=True)


def shipped(files: dict[str, bytes]) -> list:
    """Planned Details items holding `files` ({inner path: bytes}), as a build plans them."""
    return [mem_item("Details", inner, raw, "generate", "t") for inner, raw in files.items()]


def playable(box: tuple[float, float, float, float]) -> bytes:
    """A PlayableZone file whose ring is `box`."""
    x0, y0, x1, y1 = box
    return encode(build_graph(playable_zone_graph(list(rect_polygon(box)), ((x0 + x1) / 2, (y0 + y1) / 2, 0.0)), []),
                  "PlayableZone")


def grid_files(n: int = 3, size: float = 10.0) -> dict[str, bytes]:
    areas, entries = grid(n, size)
    return {"out/IAStratZone.ndfbin": encode(build_graph(ia_zone_graph(areas), []), "IAStratZone"),
            "out/IAStrat_PathCache.ndfbin": encode(build_graph(path_cache_graph(entries), []), "PathCache")}


class ShippedGatesTest(unittest.TestCase):
    """Stock's zone rules as a profile's extra gates, read from the Details a build plans to ship."""

    def test_readers_take_bytes(self):
        self.assertEqual(read_playable_polygon(playable((0, 0, 30, 20))), list(rect_polygon((0, 0, 30, 20))))
        files = grid_files()
        areas, entries = ia_grid(files["out/IAStratZone.ndfbin"], files["out/IAStrat_PathCache.ndfbin"])
        self.assertEqual((len(areas), len(entries)), (9, 72))
        self.assertEqual([area_name(a) for a in areas], [area_name(a) for a in grid()[0]])

    def test_grid_gate(self):
        """Stock's tolerance applies (gates.GRID_TOLERANCE): a 30,000 wide grid spans a 30,000 zone, not 20,000."""
        items = shipped({"out/PlayableZone.ndfbin": playable((0, 0, 30000, 30000)), **grid_files(3, 10000.0)})
        self.assertEqual(grid_gate(items, None), "9 AI tiles and 72 path costs under the shipped playable zone "
                                                 "(0, 0)..(30,000, 30,000)")
        wide = shipped({"out/PlayableZone.ndfbin": playable((0, 0, 20000, 20000)), **grid_files(3, 10000.0)})
        with self.assertRaisesRegex(CheckError, "the AI grid spans"):
            grid_gate(wide, None)
        with self.assertRaisesRegex(CheckError, "ships no out/IAStrat_PathCache.ndfbin"):
            grid_gate(items[:2], None)

    def test_zone_layout_gate(self):
        ld, dz, cz = layout_files(layout_items())
        files = {"out/PlayableZone.ndfbin": playable(BOX), "out/LevelDesign.ndfbin": ld,
                 "out/DeploymentZone.ndfbin": dz, "out/CommandZone.ndfbin": cz}
        self.assertEqual(zone_layout_gate(shipped(files), None),
                         "3 zones and 1 arrivals laid out by stock's rules under the shipped playable zone (closest: "
                         "DeploymentZone/DZ_E, 100 world inside)")
        small = {**files, "out/PlayableZone.ndfbin": playable((0, 0, 800, 800))}
        with self.assertRaisesRegex(CheckError, "DZ_E: bbox leaves the playable zone"):
            zone_layout_gate(shipped(small), None)
        no_zones = {k: v for k, v in files.items() if k != "out/CommandZone.ndfbin"}
        with self.assertRaisesRegex(CheckError, "CommandPoints: the LevelDesign items and the Details areas differ"):
            zone_layout_gate(shipped(no_zones), None)


if __name__ == "__main__":
    unittest.main()
