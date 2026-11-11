"""Tests for Twin Cities support and Twin Strike's map: modkit.ops.maps' TWIN_CITIES record and its Cut (the playable
zone and AI grid of an op on a box of a stock layout), gates.check_grid_subset's seam, shapes.Minimap.arrival_item,
and the example's twinstrike.map (its cut, named places, zones, arrivals and FOBs).

The synthetic tests write a small layout into a temporary extraction with the toolkit's own builders. The stock tests
read Twin Cities' small layout SM_SU_3x3_TwinCities_03 and skip without the extraction."""
from __future__ import annotations

import contextlib
import csv
import dataclasses
import io
import math
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modkit.core import ndfrules, paths, tgv
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops import build as ops_build
from modkit.ops import gates
from modkit.ops.files import read_file
from modkit.ops.graph import Str, build_graph, decode, encode, f32
from modkit.ops.items import mem_item, payload
from modkit.ops.leveldesign import LD_FILE, LD_SHARED, ZONE_FILES, LdItem, leveldesign_graph, read_ld_items, zone_area
from modkit.ops.maps import (
    CUT_SHAPE_SOURCES, SNAP_PX, TWIN_CITIES, WORLD_PER_MINIMAP_PX, Cut, StockMap,
)
from modkit.ops.profile import extracted
from modkit.ops.shapes import GRU_WORLD, Minimap
from modkit.ops.zones import (
    area_name, heading, ia_grid, ia_zone_graph, path_cache_graph, playable_zone_graph, point_in_polygon,
    polygon_centroid, read_playable_polygon, read_zone_areas, rect_polygon, zone_areas_graph, zone_prop,
)

TWIN_STRIKE = Path(__file__).resolve().parents[1] / "examples" / "twin-strike"
sys.path.insert(0, str(TWIN_STRIKE))

from twinstrike import map as ts_map  # noqa: E402

LAYOUT = "twincities_op/SM_SU_3x3_TwinCities_03_Details"
LAYOUT_DATA = paths.skip_unless_extracted("twincities_op", "SM_SU_3x3_TwinCities_03_Details", "out")
DEFINITION_DATA = paths.skip_unless_extracted("twincities_op", "SM_SU_3x3_TwinCities_03_Definition")
PICTURES = paths.skip_unless_extracted("basemaps", "_3x3_TwinCities")
ROAD_LUMINANCE = 55   # Twin Cities' Minimap: road and street pixels 55-66, fields 40-49, forest 19-36
FIELD_LUMINANCE = 40
FOREST_LUMINANCE = 36
CUT_WORLD = (0.0, 372743.0, 553280.0, 1340423.0)   # cut A on the layout's tile edges: x 0..216.125, y 145.6..523.6 px
NAMESPACE, SCENARIO = "test-twin", "challenge_TwinTest"


def gru(a: tuple[float, float], b: tuple[float, float]) -> float:
    """The distance between two minimap points in GRU (shapes.GRU_WORLD world units each)."""
    return math.dist(a, b) * WORLD_PER_MINIMAP_PX / GRU_WORLD


# --------------------------------------------------------------------------- a synthetic layout

SYN = StockMap(name="_1x1_Syn", env_settings="Syn", details="syn_op/Syn_Details", copies=(), ground_z=5.0,
               minimap_px=(40, 40), world_per_px=10.0)


def syn_grid(n: int = 3, size: float = 100.0, skip: str = "", shift: float = 0.0, gap: float = 0.0):
    """An n x n grid of `size`-world tiles named Z<row>_<col>, without tile `skip`, tile Z0_1 moved `shift` world
    east (seams: a gap after Z0_0 and an overlap of Z0_2) and tile Z0_0 `gap` world narrower (a seam: a gap after it),
    and its path cache: every pair once in two navigation graphs."""
    areas = []
    for j in range(n):
        for i in range(n):
            name = f"Z{j}_{i}"
            if name == skip:
                continue
            x0, y0 = i * size + (shift if name == "Z0_1" else 0.0), j * size
            x1 = x0 + size - (gap if name == "Z0_0" else 0.0)
            areas.append(([Value(0x21, p) for p in rect_polygon((x0, y0, x1, y0 + size))],
                          Value(0x0B, (x0 + size / 2, y0 + size / 2, 0.0)), [("Name", Str(name))]))
    names = [area_name(a) for a in areas]
    c, cost = Value(0x0B, (0.0, 0.0, 0.0)), f32(1.0)
    entries = [(nav, a, b, c, c, cost) for nav in (None, Value(0x03, 3)) for k, a in enumerate(names)
               for b in names[k + 1:]]
    return areas, entries


class SyntheticLayout(unittest.TestCase):
    """A temporary extraction holding SYN's AI grid (syn_grid's), the extraction while a test runs."""
    grid: dict = {}

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        env = mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        self.write_grid(**self.grid)

    def write_grid(self, **kw) -> None:
        areas, entries = syn_grid(**kw)
        out = self.root.joinpath(*SYN.details.split("/"), "out")
        out.mkdir(parents=True, exist_ok=True)
        (out / "IAStratZone.ndfbin").write_bytes(encode(build_graph(ia_zone_graph(areas), []), "IAStratZone"))
        (out / "IAStrat_PathCache.ndfbin").write_bytes(encode(build_graph(path_cache_graph(entries), []), "PathCache"))


class CutTest(SyntheticLayout):
    """A cut's items on the synthetic 3 x 3 grid of 10 px tiles: a box on the tile edges ships the box and its tiles;
    one off the edges, or over a hole, fails when the build plans the items (one FAILED line: build.run)."""

    def test_a_tile_aligned_box_ships_its_tiles_and_their_costs(self):
        cut = Cut(SYN, (10, 0, 30, 20))
        items = cut.items(None)
        self.assertEqual([(it.pack, it.path, it.action, it.fixture) for it in items],
                         [("Details", "out/PlayableZone.ndfbin", "generate", "PlayableZone.txt"),
                          ("Details", "out/IAStratZone.ndfbin", "generate", "IAStratZone.txt"),
                          ("Details", "out/IAStrat_PathCache.ndfbin", "generate", "IAStrat_PathCache.txt")])
        self.assertEqual(items[0].source, "generated (cut x 10..30, y 0..20 px of syn_op/Syn_Details)")
        files = {it.path: payload(it) for it in items}
        self.assertEqual(read_playable_polygon(files["out/PlayableZone.ndfbin"]),
                         list(rect_polygon((100, 0, 300, 200))))
        nb, _, _ = decode(files["out/PlayableZone.ndfbin"])
        (center,) = [v.v for ob in nb.objects for pi, v in ob.props if nb.pname(pi) == "Center"]
        self.assertEqual(center, (200.0, 100.0, 5.0))     # the box's centre at the map's ground_z
        areas, entries = ia_grid(files["out/IAStratZone.ndfbin"], files["out/IAStrat_PathCache.ndfbin"])
        self.assertEqual([area_name(a) for a in areas], ["Z0_1", "Z0_2", "Z1_1", "Z1_2"])
        self.assertEqual(len(entries), 2 * 6)             # every pair of the 4 tiles, in each navigation graph
        self.assertEqual(cut.check_shipped(items), "4 AI tiles and 12 path costs of syn_op/Syn_Details, cut on its "
                                                   "tile edges to the shipped playable zone x 10..30, y 0..20 px "
                                                   "(seams up to 0 world)")
        self.assertEqual(cut.gate().name, "grid")

    def test_the_whole_grid_is_a_cut_too(self):
        items = Cut(SYN, (0, 0, 30, 30)).items(None)
        areas, entries = ia_grid(payload(items[1]), payload(items[2]))
        self.assertEqual((len(areas), len(entries)), (9, 72))

    def test_an_edge_within_half_a_pixel_names_the_tile_edge(self):
        self.assertEqual(Cut(SYN, (10.4, 0, 29.5, 20)).box(), (100.0, 0.0, 300.0, 200.0))
        self.assertEqual(SNAP_PX, 0.5)

    def test_an_off_edge_box_fails_at_build(self):
        with self.assertRaisesRegex(CheckError, r"^cut x 0\.\.25, y 0\.\.20 px of syn_op/Syn_Details: its x1 edge "
                                                r"lies 5\.00 px from the nearest AI tile edge \(20 px\); a cut's "
                                                r"edges are tile edges, named to within 0\.5 px$"):
            Cut(SYN, (0, 0, 25, 20)).items(None)

    def test_a_box_over_a_hole_fails_at_build(self):
        self.write_grid(skip="Z0_1")
        with self.assertRaisesRegex(CheckError, r"^playable zone \(0\.0, 0\.0, 200\.0, 200\.0\): the 3 AI tiles inside "
                                                r"it do not cover it exactly$"):
            Cut(SYN, (0, 0, 20, 20)).items(None)

    def test_the_failure_is_one_failed_line(self):
        """build.run turns the cut's failure, raised while it plans the profile's extra items, into one line."""
        def fail():
            return Cut(SYN, (0, 0, 25, 20)).items(None)
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(ops_build.run(fail, lambda: None, str(self.root)), 1)
        self.assertEqual(err.getvalue().count("\n"), 1)
        self.assertRegex(err.getvalue(), r"^FAILED: cut x 0\.\.25, y 0\.\.20 px of syn_op/Syn_Details: its x1 edge")


class CutGateTest(SyntheticLayout):
    """The cut's `grid` gate, on the Details a build plans to ship."""

    def shipped(self, files: dict[str, bytes]) -> list:
        return [mem_item("Details", inner, raw, "generate", "t") for inner, raw in files.items()]

    def test_the_whole_grid_under_a_cut_fails(self):
        """The crash the rule comes from: the map's whole grid shipped under a smaller playable zone."""
        cut = Cut(SYN, (10, 0, 30, 20))
        files = {it.path: payload(it) for it in cut.items(None)}
        whole = {it.path: payload(it) for it in Cut(SYN, (0, 0, 30, 30)).items(None)}
        for inner in gates.IA_GRID_FILES:
            with self.subTest(file=inner):
                with self.assertRaisesRegex(CheckError, rf"^{inner}: the shipped AI grid is not the cut of "
                                                        rf"syn_op/Syn_Details's grid under the shipped playable zone "
                                                        rf"x 10\.\.30, y 0\.\.20 px$"):
                    cut.check_shipped(self.shipped({**files, inner: whole[inner]}))

    def test_a_playable_zone_that_is_not_a_rectangle_fails(self):
        cut = Cut(SYN, (10, 0, 30, 20))
        files = {it.path: payload(it) for it in cut.items(None)}
        ring = [(100.0, 0.0), (300.0, 0.0), (300.0, 200.0), (150.0, 250.0), (100.0, 200.0), (100.0, 0.0)]
        files["out/PlayableZone.ndfbin"] = encode(build_graph(playable_zone_graph(ring, (0, 0, 0)), []), "PZ")
        with self.assertRaisesRegex(CheckError, "the shipped playable zone is not a rectangle"):
            cut.check_shipped(self.shipped(files))

    def test_missing_files_fail(self):
        cut = Cut(SYN, (10, 0, 30, 20))
        items = cut.items(None)
        with self.assertRaisesRegex(CheckError, "the mod ships no out/PlayableZone.ndfbin"):
            cut.check_shipped(items[1:])
        with self.assertRaisesRegex(CheckError, "the mod ships no out/IAStrat_PathCache.ndfbin"):
            cut.check_shipped(items[:2])


class SeamTest(SyntheticLayout):
    """A grid whose tiles do not quite meet (Twin Cities' layout: 1/8 px seams): the map's grid_seam admits them."""
    grid = {"gap": 2.0}   # Z0_0 2 world narrow: a 2-world gap before Z0_1

    def test_the_seam_admits_the_grid(self):
        box = (0.0, 0.0, 300.0, 200.0)
        areas, entries = syn_grid(gap=2.0)
        with self.assertRaisesRegex(CheckError, r"the 6 AI tiles inside it do not cover it exactly$"):
            gates.check_grid_subset(areas, entries, box)
        with self.assertRaisesRegex(CheckError, r"do not cover it exactly \(seams of up to 1 world aside\)$"):
            gates.check_grid_subset(areas, entries, box, seam=1.0)
        self.assertEqual(gates.check_grid_subset(areas, entries, box, seam=2.0), (6, 30))
        with self.assertRaisesRegex(CheckError, "do not cover it exactly"):
            Cut(SYN, (0, 0, 30, 20)).items(None)
        seamed = dataclasses.replace(SYN, grid_seam=2.0)
        items = Cut(seamed, (0, 0, 30, 20)).items(None)
        self.assertIn("(seams up to 2 world)", Cut(seamed, (0, 0, 30, 20)).check_shipped(items))

    def test_an_overlap_wider_than_the_seam_fails(self):
        """Z0_1 2 world east: a gap and an overlap whose areas cancel; past the seam, the overlap still fails."""
        areas, entries = syn_grid(shift=2.0)
        with self.assertRaisesRegex(CheckError, r"\(seams of up to 1 world aside\)$"):
            gates.check_grid_subset(areas, entries, (0.0, 0.0, 300.0, 200.0), seam=1.0)
        self.assertEqual(gates.check_grid_subset(areas, entries, (0.0, 0.0, 300.0, 200.0), seam=2.0), (6, 30))

    def test_the_seam_never_fills_a_hole(self):
        areas, entries = syn_grid(skip="Z1_1", shift=2.0)
        with self.assertRaisesRegex(CheckError, r"the 5 AI tiles inside it do not cover it exactly"):
            gates.check_grid_subset(areas, entries, (0.0, 0.0, 300.0, 200.0), seam=50.0)

    def test_seam_edges(self):
        self.assertEqual(gates.seam_edges([0.0, 1.0, 98.0, 100.0, 102.0, 200.0], (0.0, 200.0), 2.0),
                         {0.0: 0.0, 1.0: 0.0, 98.0: 98.0, 100.0: 98.0, 102.0: 98.0, 200.0: 200.0})
        self.assertEqual(gates.seam_edges([1.0, 3.0], (2.0,), 1.0), {1.0: 2.0, 2.0: 2.0, 3.0: 2.0})


class ArrivalItemTest(unittest.TestCase):
    def test_midpoint_and_heading(self):
        mm = Minimap(SYN, {"A": (1, 2)})
        it = mm.arrival_item("ReinforcementLocations", "RL", "A", (1, 6), "ReinforcementLocation")
        self.assertEqual((it.ranking, it.name, it.addon), ("ReinforcementLocations", "RL", "ReinforcementLocation"))
        self.assertEqual((it.start, it.end, (it.x, it.y)), ((10.0, 20.0), (10.0, 60.0), (10.0, 40.0)))
        self.assertEqual(it.rotation, heading((10.0, 20.0), (10.0, 60.0)))
        self.assertAlmostEqual(it.rotation, math.pi / 2)
        self.assertIsNone(it.num_alliance)


# --------------------------------------------------------------------------- Twin Strike's map (no game)

def details(items) -> dict[str, bytes]:
    """The LevelDesign and zone files of `items`, as a build generates them (TWIN_CITIES' ground_z)."""
    out = {LD_FILE: encode(build_graph(leveldesign_graph(items, SCENARIO, NAMESPACE), [], LD_SHARED), "LevelDesign")}
    for addon, inner in ZONE_FILES.items():
        out[inner] = encode(build_graph(zone_areas_graph([zone_area(it, SCENARIO, NAMESPACE, TWIN_CITIES.ground_z)
                                                          for it in items if it.addon == addon]), []), inner)
    return out


class TwinStrikeMapTest(unittest.TestCase):
    """twinstrike.map: the cut, the named places and routes, and the LevelDesign items it gives the op."""

    @classmethod
    def setUpClass(cls):
        cls.items = {it.name: it for it in ts_map.items()}
        cls.px = ts_map.MAP.box_px

    def test_the_cut(self):
        self.assertEqual(ts_map.CUT_PX, (0, 146, 216, 524))
        self.assertEqual((ts_map.CUT.map, ts_map.CUT.box_px), (TWIN_CITIES, ts_map.CUT_PX))

    def test_items(self):
        self.assertEqual(sorted(self.items), ["C0_FOB_SOV_1", "C0_FOB_SOV_2", "TS_AC_N", "TS_CZ_Village",
                                              "TS_DZ_NATO", "TS_DZ_Soviet", "TS_RL_N"])
        self.assertEqual(len(ts_map.items()), len(self.items))

    def test_every_point_lies_in_the_cut(self):
        """Every place but GUN_SPAWN, which stands north of the cut, inside the map (768 x 768 px)."""
        x0, y0, x1, y1 = ts_map.CUT_PX
        for name, (x, y) in ts_map.POINTS.items():
            with self.subTest(point=name):
                self.assertEqual(x0 < x < x1 and y0 < y < y1, name != "GUN_SPAWN", (name, (x, y)))
        x, y = ts_map.POINTS["GUN_SPAWN"]
        self.assertTrue(x0 < x < x1 and 0 < y < y0)
        for it in self.items.values():
            for p in (*(it.polygon or ()), (it.x, it.y), *((it.start, it.end) if it.start else ())):
                with self.subTest(item=it.name, p=p):
                    x, y = TWIN_CITIES.world_to_px(p)
                    self.assertTrue(x0 <= x <= x1 and y0 < y < y1, (it.name, (x, y)))

    def test_routes(self):
        """Every route runs through named points and ends in the village; the lanes start at the NATO entries."""
        for name, route in ts_map.PATHS.items():
            with self.subTest(route=name):
                self.assertLessEqual(set(route), set(ts_map.POINTS))
                self.assertEqual(route[-1], "VILLAGE")
        self.assertEqual((ts_map.PATHS["LANE_W"][0], ts_map.PATHS["LANE_C"][0]), ("NATO_ENTRY_W", "NATO_ENTRY_C"))
        self.assertEqual((ts_map.PATHS["LANE_W"][1], ts_map.PATHS["LANE_C"][1]), ("BOX_W", "BOX_C"))

    def test_deployment_boxes(self):
        """Soviet (alliance 0) north, NATO (alliance 1) south, both inside the cut and apart; the NATO entries and
        ASSEMBLY in the NATO box, the FOBs and SOV_ENTRY in the Soviet box, GUNS outside it."""
        sov, nato = self.items["TS_DZ_Soviet"], self.items["TS_DZ_NATO"]
        self.assertEqual((sov.alliance, nato.alliance), (None, 1))
        self.assertEqual((self.px(sov), self.px(nato)), (ts_map.SOV_DZ, ts_map.NATO_DZ))
        self.assertFalse(gates.polygons_overlap(sov.polygon, nato.polygon))
        self.assertLess(self.px(sov)[3], self.px(nato)[1])
        cx0, cy0, cx1, cy1 = ts_map.CUT_PX
        for x0, y0, x1, y1 in (ts_map.SOV_DZ, ts_map.NATO_DZ):
            self.assertTrue(cx0 <= x0 < x1 < cx1 and cy0 < y0 < y1 < cy1)
        for zone, names in ((sov, ("SOV_ENTRY", "FOB_W", "FOB_E")),
                            (nato, ("NATO_ENTRY_W", "NATO_ENTRY_C", "ASSEMBLY"))):
            for name in names:
                with self.subTest(point=name):
                    self.assertTrue(point_in_polygon(*TWIN_CITIES.px_to_world(ts_map.POINTS[name]), zone.polygon))
        self.assertFalse(point_in_polygon(*TWIN_CITIES.px_to_world(ts_map.POINTS["GUNS"]), sov.polygon))

    def test_arrivals_end_in_the_soviet_box(self):
        """Both of the player's entries (NumAlliance left out) come in at the cut's north edge, north of the Soviet
        box, and end inside it (gates.check_arrivals' rule); each is laid out as stock's: the item at the midpoint,
        Rotation the heading."""
        sov = self.items["TS_DZ_Soviet"].polygon
        for name, addon in (("TS_RL_N", "ReinforcementLocation"), ("TS_AC_N", "AerialCorridor")):
            it = self.items[name]
            with self.subTest(arrival=name):
                self.assertEqual((it.addon, it.num_alliance), (addon, None))
                self.assertTrue(point_in_polygon(*it.end, sov))
                self.assertFalse(point_in_polygon(*it.start, sov))
                self.assertLess(TWIN_CITIES.world_to_px(it.start)[1], ts_map.SOV_DZ[1])
                self.assertEqual((it.x, it.y), ((it.start[0] + it.end[0]) / 2, (it.start[1] + it.end[1]) / 2))
                self.assertEqual(it.rotation, heading(it.start, it.end))
        self.assertEqual(gates.check_arrivals(list(self.items.values()), details(list(self.items.values()))), (1, 1))

    def test_zone_layout_keeps_every_generator_convention(self):
        """The zones and arrivals, read back from the files a build generates, keep stock's clauses and every generator
        convention (exact centroids and headings, Centers at ground_z, a deployment zone per side, Ends in their own
        side's deployment zone) under the cut."""
        files = details(list(self.items.values()))
        layout = gates.check_zone_layout(files[LD_FILE], files[ZONE_FILES["DeploymentZone"]],
                                         files[ZONE_FILES["CommandPoints"]], CUT_WORLD, ground_z=TWIN_CITIES.ground_z,
                                         sides=(0, 1), exact=True, dz_only=True)
        self.assertEqual((len(layout.margins), len(layout.arrivals)), (3, 2))
        self.assertGreater(min(layout.margins)[0], 0)

    def test_village_zone(self):
        """AutoName_5 as it ships (its polygon, Points and item position), holding VILLAGE; its Center x/y is the
        stock area's, (176,960, 964,103)."""
        cz = self.items["TS_CZ_Village"]
        self.assertEqual((cz.ranking, cz.addon, cz.points, cz.rotation), ("CommandPoints", "CommandPoints", 2, None))
        self.assertEqual(cz.polygon, rect_polygon((15680.0, 848903.0, 338240.0, 1079303.0)))
        self.assertEqual((cz.x, cz.y), (184320.0, 983040.0))
        self.assertEqual(TWIN_CITIES.world_to_px((cz.x, cz.y)), (72.0, 384.0))
        self.assertEqual(polygon_centroid(list(cz.polygon)), (176960.0, 964103.0))
        self.assertTrue(point_in_polygon(*TWIN_CITIES.px_to_world(ts_map.POINTS["VILLAGE"]), cz.polygon))

    def test_fobs_in_the_stock_shape(self):
        """Camp_0 spawns of FOB_SOV with no Camp, experience or auto-spawn switch: the add-on Marauders' C0_FOB_UK_2
        has (Name, Ranking, GUID, AutoNameBase, ClassName), at FOB_W and FOB_E."""
        fobs = [self.items["C0_FOB_SOV_1"], self.items["C0_FOB_SOV_2"]]
        self.assertEqual([(it.ranking, it.addon, it.unit, it.camp, it.experience, it.disable_auto_spawn, it.rotation)
                          for it in fobs], [("Camp_0", "Spawn", "FOB_SOV", None, None, False, None)] * 2)
        self.assertEqual([self.px_of(it) for it in fobs], [ts_map.POINTS["FOB_W"], ts_map.POINTS["FOB_E"]])
        nb, _, _ = decode(details(fobs)[LD_FILE])
        spawns = [[nb.pname(pi) for pi, _ in ob.props] for ob in nb.objects
                  if nb.cname(ob.cls) == "TGameDesignAddOn_Spawn"]
        self.assertEqual(spawns, [["Name", "Ranking", "GUID", "AutoNameBase", "ClassName"]] * 2)
        self.assertEqual({it["ClassName"] for it in read_ld_items(details(fobs)[LD_FILE])},
                         {"$/GFX/Unit/Descriptor_Unit_FOB_SOV"})

    def px_of(self, it: LdItem) -> tuple[float, float]:
        return ts_map.MAP.px_of(it)

    def test_the_guns_bands(self):
        """Design section 3: from GUN_SPAWN, where each fire's battery is created, both the 2S7M (7,000-35,000 GRU) and
        the BM-27 (10,000-35,000) reach the village, the boxes and ASSEMBLY, the closest 2,865 GRU past the BM-27's
        minimum; the spot stands 4,577 GRU north of the cut's tile edge (y 145.603)."""
        p = ts_map.POINTS
        got = [round(gru(p["GUN_SPAWN"], p[n])) for n in ("VILLAGE", "BOX_W", "BOX_C", "ASSEMBLY")]
        self.assertEqual(got, [12865, 16074, 15402, 16914])
        self.assertTrue(all(10000 <= d <= 35000 for d in got))
        self.assertEqual(round(gru(p["GUN_SPAWN"], (p["GUN_SPAWN"][0], 145.603))), 4577)

    def test_the_fallback_at_guns_keeps_the_bands(self):
        """The unbuilt fallback, batteries inside the cut's north-west corner at GUNS: the 2S7M (7,000-35,000 GRU)
        reaches every target, the BM-27 (10,000-35,000) the boxes and ASSEMBLY but not the village; each with at least
        500 GRU to spare, which a battery laid out around GUNS needs."""
        p = ts_map.POINTS
        village = gru(p["GUNS"], p["VILLAGE"])
        self.assertTrue(7000 + 500 <= village <= 10000 - 500, village)
        for name in ("BOX_W", "BOX_C", "ASSEMBLY"):
            with self.subTest(target=name):
                self.assertTrue(10000 + 500 <= gru(p["GUNS"], p[name]) <= 35000 - 500)
        self.assertEqual([round(gru(p["GUNS"], p[n])) for n in ("VILLAGE", "BOX_W", "BOX_C", "ASSEMBLY")],
                         [7846, 10991, 11818, 12867])
        self.assertEqual([round(gru(p["VILLAGE"], p[n])) for n in ("BOX_W", "BOX_C", "ASSEMBLY")], [3238, 4719, 5240])


# --------------------------------------------------------------------------- the stock layout

@LAYOUT_DATA
class TwinCitiesRecordTest(unittest.TestCase):
    """TWIN_CITIES' fields, read off the stock files."""

    def test_ground_z_is_the_layouts_playable_zone_center(self):
        nb, _, _ = decode(read_file(extracted(f"{LAYOUT}/out/PlayableZone.ndfbin")))
        (center,) = [v.v for ob in nb.objects for pi, v in ob.props if nb.pname(pi) == "Center"]
        self.assertEqual(center[2], TWIN_CITIES.ground_z)
        self.assertEqual(TWIN_CITIES.details, LAYOUT)

    def test_copies_are_the_newest_camera_paths(self):
        """The only file an op on a cut ships byte for byte: the newest CamPaths (197351, 341 B)."""
        with open(extracted(f"{LAYOUT}/_provenance.tsv"), encoding="utf-8", newline="") as fh:
            rows = {row[0]: row for row in csv.reader(fh, delimiter="\t") if row}
        self.assertEqual(TWIN_CITIES.copies, ("CamPaths_LevelDesign.ndfbin",))
        self.assertEqual(rows["CamPaths_LevelDesign.ndfbin"][1:4:2], ["197351", "341"])
        self.assertFalse(set(TWIN_CITIES.copies) & {gates.PLAYABLE_FILE, *gates.IA_GRID_FILES})

    @paths.skip_unless_extracted("twincities_op", "_3x3_TwinCities_10vs10_CONQ_Details", "out")
    def test_world_per_px(self):
        """The 10vs10 conquest's playable zone is the whole map: 768 minimap px of WORLD_PER_MINIMAP_PX each."""
        ring = read_playable_polygon(read_file(extracted(
            "twincities_op/_3x3_TwinCities_10vs10_CONQ_Details/out/PlayableZone.ndfbin")))
        xs, ys = zip(*(TWIN_CITIES.world_to_px(p) for p in ring))
        self.assertEqual((min(xs), min(ys), max(xs), max(ys)), (0.0, 0.0, 768.0, 768.0))
        self.assertEqual(TWIN_CITIES.world_per_px, WORLD_PER_MINIMAP_PX)

    @PICTURES
    def test_minimap_px(self):
        hdr, _ = tgv.read_tgv(extracted(TWIN_CITIES.picture("Minimap")))
        self.assertEqual((hdr.width, hdr.height), TWIN_CITIES.minimap_px)
        hdr, _ = tgv.read_tgv(extracted(TWIN_CITIES.picture("Preview")))
        self.assertEqual((hdr.width, hdr.height), (1536, 1536))

    @DEFINITION_DATA
    def test_names_the_definition_holds(self):
        """name is the layout's ScenarioInfo.RootDatapackName; env_settings the base EnvironmentSettings its
        MapConfiguration imports (its 'evening' entry; the Night, Morning, Noon and Afternoon ones are variants)."""
        folder = extracted("twincities_op/SM_SU_3x3_TwinCities_03_Definition/NDF/Scenarios")
        nb, _, _ = decode(read_file(os.path.join(folder, "ScenarioInfo", "SM_SU_3x3_TwinCities_03.ndfbin")))
        self.assertEqual([nb.strings[v.v].decode("latin-1") for ob in nb.objects for pi, v in ob.props
                          if nb.pname(pi) == "RootDatapackName"], [TWIN_CITIES.name])
        nb, _, _ = decode(read_file(os.path.join(folder, "MapConfiguration", "SM_SU_3x3_TwinCities_03.ndfbin")))
        names = [s.decode("latin-1") for s in nb.trans]
        self.assertIn(TWIN_CITIES.env_settings, names)
        self.assertEqual(sorted(n for n in names if n.startswith(TWIN_CITIES.env_settings)),
                         [TWIN_CITIES.env_settings + s for s in ("", "_Afternoon", "_Morning", "_Night", "_Noon")])

    def test_grid_seam(self):
        """The layout's grid needs exactly its seam under cut A: at 319 world its tiles leave a gap."""
        areas, entries = TWIN_CITIES.ia_grid()
        self.assertEqual(gates.check_grid_subset(areas, entries, CUT_WORLD, seam=TWIN_CITIES.grid_seam), (40, 1560))
        for seam in (0.0, TWIN_CITIES.grid_seam - 1):
            with self.subTest(seam=seam):
                with self.assertRaisesRegex(CheckError, "do not cover it exactly"):
                    gates.check_grid_subset(areas, entries, CUT_WORLD, seam=seam)


@LAYOUT_DATA
class TwinStrikeCutTest(unittest.TestCase):
    """Twin Strike's cut of SM_SU_3x3_TwinCities_03: box A on the layout's tile edges, its 40 tiles."""

    @classmethod
    def setUpClass(cls):
        cls.items = ts_map.CUT.items(None)
        cls.files = {it.path: payload(it) for it in cls.items}

    def test_box_a_keeps_40_tiles(self):
        self.assertEqual(ts_map.CUT.box(), CUT_WORLD)
        areas, entries = ia_grid(self.files["out/IAStratZone.ndfbin"], self.files["out/IAStrat_PathCache.ndfbin"])
        self.assertEqual((len(areas), len(entries)), (40, 2 * 40 * 39 // 2))
        self.assertEqual(read_playable_polygon(self.files["out/PlayableZone.ndfbin"]), list(rect_polygon(CUT_WORLD)))
        self.assertEqual(ts_map.CUT.check_shipped(self.items),
                         "40 AI tiles and 1,560 path costs of twincities_op/SM_SU_3x3_TwinCities_03_Details, cut on "
                         "its tile edges to the shipped playable zone x 0..216.125, y 145.603..523.603 px (seams up "
                         "to 320 world)")

    def test_the_cut_files_keep_gate_2(self):
        """Canonical, only stock shapes (CUT_SHAPE_SOURCES) and, with the rules table, the game's load-time checks."""
        for inner, raw in self.files.items():
            with self.subTest(file=inner):
                gates.check_canonical(raw, frozenset(), inner, import_rule="trie")
                stock, _ = gates.survey_shapes(tuple(extracted(g) for g in CUT_SHAPE_SOURCES[inner]), 16)
                gates.check_shapes(raw, stock, inner)
                try:
                    table = ndfrules.table_path()
                except paths.NotConfigured:
                    continue
                if table.is_file():
                    ndfrules.check_file(raw, inner)

    def test_village_zone_is_autoname_5(self):
        """The village zone is the layout's command zone AutoName_5 as it ships, inside the cut; the layout's other two
        command zones are not (AutoName_8 crosses the cut's east edge, AutoName_6 lies east of it)."""
        stock = read_zone_areas(read_file(extracted(f"{LAYOUT}/out/CommandZone.ndfbin")))
        areas = {zone_prop(a, "Name"): a for a in stock}
        self.assertEqual(sorted(areas), ["AutoName_5", "AutoName_6", "AutoName_8"])
        village = areas["AutoName_5"]
        self.assertEqual((tuple(village[0]), village[2], zone_prop(village, "Points")),
                         (ts_map.VILLAGE_CZ, "TGameDesignAddOn_CommandPoints", ts_map.VILLAGE_CZ_POINTS))
        (item,) = [it for it in read_ld_items(read_file(extracted(f"{LAYOUT}/out/LevelDesign.ndfbin")))
                   if it.get("Name") == "AutoName_5"]
        self.assertEqual((item["addon"], item["pos"]), ("CommandPoints", ts_map.VILLAGE_CZ_AT))
        x0, y0, x1, y1 = CUT_WORLD

        def inside(poly) -> bool:
            return all(x0 <= x <= x1 and y0 <= y <= y1 for x, y in poly)
        self.assertEqual({name: inside(a[0]) for name, a in areas.items()},
                         {"AutoName_5": True, "AutoName_6": False, "AutoName_8": False})


@LAYOUT_DATA
@PICTURES
class TwinStrikePlacesTest(unittest.TestCase):
    """The named places sit where their reasons say, on Twin Cities' Minimap: the lane points, the waves' entries
    and the reinforcement location on road pixels, the open-ground places on fields, GUNS in the corner forest."""

    @classmethod
    def setUpClass(cls):
        hdr, rgba = tgv.read_tgv(extracted(TWIN_CITIES.picture("Minimap")))
        cls.w, cls.minimap = hdr.width, tgv.drop_alpha(rgba)

    def luminance(self, p: tuple[float, float]) -> int:
        i = (round(p[1]) * self.w + round(p[0])) * 3
        return sum(self.minimap[i:i + 3]) // 3

    def test_road_points(self):
        p = ts_map.POINTS
        for name, at in [*((n, p[n]) for n in ("VILLAGE", "ASSAULT_N", "NATO_ENTRY_W", "NATO_ENTRY_C", "BOX_W", "BOX_C",
                                                "TURN_C")),
                         ("RL start", ts_map.RL_N[0]), ("RL end", ts_map.RL_N[1])]:
            with self.subTest(point=name):
                self.assertGreaterEqual(self.luminance(at), ROAD_LUMINANCE)

    def test_open_ground(self):
        for name in ("SOV_ENTRY", "ASSAULT_S", "ASSEMBLY", "FOB_W", "FOB_E"):
            with self.subTest(point=name):
                self.assertTrue(FIELD_LUMINANCE <= self.luminance(ts_map.POINTS[name]) < ROAD_LUMINANCE)

    def test_guns_in_the_corner_forest(self):
        self.assertLess(self.luminance(ts_map.POINTS["GUNS"]), FOREST_LUMINANCE)


@LAYOUT_DATA
@PICTURES
class OverlayTest(unittest.TestCase):
    def test_overlay_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "overlay.png")
            log = io.StringIO()
            with contextlib.redirect_stdout(log):
                self.assertEqual(ts_map.main(["overlay", out]), 0)
            self.assertTrue(os.path.isfile(out))
        self.assertEqual(log.getvalue(), f"overlay.png (1536x1536): {len(ts_map.POINTS)} marks, 9 rings on the "
                                         f"Preview\n")


class OverlayUnconfiguredTest(unittest.TestCase):
    def test_unconfigured_is_one_failed_line(self):
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": os.path.join(tmp, "missing")}), \
                contextlib.redirect_stderr(err):
            self.assertEqual(ts_map.main(["overlay", os.path.join(tmp, "o.png")]), 1)
        self.assertEqual(err.getvalue().count("\n"), 1)
        self.assertTrue(err.getvalue().startswith("FAILED: "))


@paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
@LAYOUT_DATA
class WholeBuildOnTheCutTest(unittest.TestCase):
    """The build driver's tiny op (test_build's), moved onto Twin Cities with the cut: it ships the cut's three files
    and the layout's camera paths, and the `grid` gate holds them; a cut off the tile edges fails with one line."""

    def profile(self, cut: Cut, root: str):
        from test_build import profile
        base = profile(build_root=root)
        return profile(build_root=root, map_strings={"_3x3_Railway": TWIN_CITIES.name},
                       map_trans={"Railway": TWIN_CITIES.env_settings}, map_details=TWIN_CITIES.details,
                       map_copies=TWIN_CITIES.copies, ground_z=TWIN_CITIES.ground_z,
                       shape_sources={**base.shape_sources, **CUT_SHAPE_SOURCES},
                       extra_items=(cut.items,), extra_gates=(cut.gate(),))

    def test_build(self):
        from test_build import content, quiet
        with tempfile.TemporaryDirectory() as tmp:
            items, report = quiet(ops_build.build, self.profile(ts_map.CUT, tmp), content(), os.path.join(tmp, "a"))
            dumps = sorted(os.listdir(os.path.join(tmp, "a", "dumps")))
        details = {it.path: it.action for it in items if it.pack == "Details"}
        self.assertEqual({k: details[k] for k in (gates.PLAYABLE_FILE, *gates.IA_GRID_FILES, *TWIN_CITIES.copies)},
                         {gates.PLAYABLE_FILE: "generate", gates.IA_GRID_FILES[0]: "generate",
                          gates.IA_GRID_FILES[1]: "generate", "CamPaths_LevelDesign.ndfbin": "copy"})
        self.assertIn("gate 3 grid: 40 AI tiles and 1,560 path costs of twincities_op/SM_SU_3x3_TwinCities_03_Details",
                      report)
        self.assertLessEqual({"PlayableZone.txt", "IAStratZone.txt", "IAStrat_PathCache.txt"}, set(dumps))

    def test_a_cut_off_the_tile_edges_is_one_failed_line(self):
        from test_build import content
        bad = Cut(TWIN_CITIES, (0, 146, 213, 524))
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(ops_build.run(lambda: self.profile(bad, tmp), content, os.path.join(tmp, "a")), 1)
        # the console may also hold the game-build warning line (gamebuild.build_warning), never a traceback
        self.assertNotIn("Traceback", err.getvalue())
        self.assertEqual([line for line in err.getvalue().splitlines() if line.startswith("FAILED")], [
            "FAILED: cut x 0..213, y 146..524 px of twincities_op/SM_SU_3x3_TwinCities_03_Details: its x1 edge lies "
            "3.12 px from the nearest AI tile edge (216.125 px); a cut's edges are tile edges, named to within 0.5 px"])


if __name__ == "__main__":
    unittest.main()
