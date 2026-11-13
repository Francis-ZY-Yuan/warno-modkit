"""Tests for modkit.ops.maps (the stock map record and the review overlay; its opening camera is
test_opening_camera's) and modkit.ops.forces (force tables)."""
from __future__ import annotations

import csv
import os
import shutil
import tempfile
import unittest

from modkit.core import paths
from modkit.ops.forces import (
    GEISA_SOVIET_ROWS, formation, group_rows, group_total, rows_of, scaled, share_count,
)
from modkit.ops.models import ForceRow
from modkit.ops.files import read_file
from modkit.ops.graph import decode
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA, GEISA_BOXES, GEISA_POINTS
from modkit.ops.profile import Content, extracted
from modkit.ops.rekey import TXN, def_path
from modkit.ops.zones import point_in_polygon


class Geisa(unittest.TestCase):
    def test_frame(self):
        self.assertEqual(GEISA.px_to_world((10, 20)), (25600.0, 51200.0))
        self.assertEqual(GEISA.world_to_px(GEISA.px_to_world((395, 402))), (395.0, 402.0))
        self.assertEqual(GEISA.picture("Minimap"), "basemaps/_4x3_geisa/PC/Texture/_4x3_geisa/Minimap.tgv")

    def test_player_arrivals(self):
        got = GEISA.player_arrivals("X")
        self.assertEqual([it.name for it in got], ["X_RL_W1", "X_RL_W2", "X_AC_W1", "X_AC_W2"])
        self.assertEqual({it.num_alliance for it in got}, {None})
        rl = got[1]   # P0_AutoName_7, the road at the west edge
        self.assertEqual((rl.start, rl.end, (rl.x, rl.y)),
                         ((11677.0, 1514376.0), (64050.0, 1515041.0), (37863.496, 1514708.5)))

    @paths.skip_unless_extracted("geisa_op", "_4x3_geisa_10vs10_CONQ_Details", "out", "PlayableZone.ndfbin")
    def test_playable_polygon_holds_the_arrivals(self):
        ring = GEISA.playable_polygon()
        self.assertEqual(ring[0], ring[-1])
        for it in GEISA.player_arrivals("X"):
            with self.subTest(item=it.name):
                self.assertTrue(point_in_polygon(*it.end, ring))

    @paths.skip_unless_extracted("geisa_op", "_4x3_geisa_10vs10_CONQ_Details", "out", "PlayableZone.ndfbin")
    def test_playable_zone_scale(self):
        """The ring spans most of the minimap in both axes, and no more than it (a scale off by 2x fails either way)."""
        xs, ys = zip(*(GEISA.world_to_px(p) for p in GEISA.playable_polygon()))
        for span, full in ((max(xs) - min(xs), GEISA.minimap_px[0]), (max(ys) - min(ys), GEISA.minimap_px[1])):
            self.assertGreaterEqual(span, 0.9 * full)
            self.assertLessEqual(span, full)

    @paths.skip_unless_extracted("geisa_op", "_4x3_geisa_10vs10_CONQ_Details", "_provenance.tsv")
    def test_copies_are_the_newest_layout(self):
        """Every file GEISA ships byte for byte is in the extracted Details, from the newest revision that holds it:
        the 197351 CamPaths (341 B), not the 183203 one."""
        with open(extracted(f"{GEISA.details}/_provenance.tsv"), encoding="utf-8", newline="") as fh:
            rows = {row[0]: row for row in csv.reader(fh, delimiter="	") if row}
        self.assertLessEqual(set(GEISA.copies), rows.keys())
        self.assertEqual(rows["CamPaths_LevelDesign.ndfbin"][1:4:2], ["197351", "341"])
        self.assertEqual(rows["out/PlayableZone.ndfbin"][1], "193438")

    @paths.skip_unless_extracted("geisa_op", "_4x3_geisa_10vs10_CONQ_Definition")
    def test_names_the_definition_holds(self):
        """GEISA.name is the map scenario's ScenarioInfo.RootDatapackName, and env_settings the EnvironmentSettings
        name its MapConfiguration imports: the two names a profile swaps in for its template's map."""
        folder = extracted("geisa_op/_4x3_geisa_10vs10_CONQ_Definition")
        nb, _, _ = decode(read_file(os.path.join(folder, def_path("ScenarioInfo", TXN, "_4x3_geisa_10vs10_CONQ"))))
        self.assertEqual([nb.strings[v.v].decode("latin-1") for ob in nb.objects for pi, v in ob.props
                          if nb.pname(pi) == "RootDatapackName"], [GEISA.name])
        nb, _, _ = decode(read_file(os.path.join(folder, def_path("MapConfiguration", TXN,
                                                                  "_4x3_geisa_10vs10_CONQ"))))
        names = [s.decode("latin-1") for s in nb.trans]
        self.assertIn(GEISA.env_settings, names)

    @paths.skip_unless_extracted("geisa_op", "_4x3_geisa_10vs10_CONQ_Details", "out", "PlayableZone.ndfbin")
    @paths.skip_unless_extracted("basemaps", "_4x3_geisa")
    def test_overlay_output(self):
        content = Content("t", (LdItem("Tags", "A", *GEISA.px_to_world((100, 100)), "Name"),), None, {}, (),
                          scenario="challenge_T", mod_name="T", menu_renames=())
        out = tempfile.mkdtemp()
        try:
            line = GEISA.overlay_output("overlay.png")(content, out)
            self.assertTrue(os.path.isfile(os.path.join(out, "overlay.png")))
            self.assertIn("1 marks, 1 rings", line)
        finally:
            shutil.rmtree(out, ignore_errors=True)


class SharedPlaces(unittest.TestCase):
    """The named places on Geisa that more than one example op uses: one table, read-only."""

    def test_points(self):
        self.assertEqual((GEISA_POINTS["NECK_MID"], GEISA_POINTS["SACK_MID"], GEISA_POINTS["CORNER_PACT"]),
                         ((395, 402), (340, 406), (734, 54)))
        self.assertEqual((GEISA_POINTS["ENTRY_SE"], GEISA_POINTS["FARM_ROAD"]), ((756.0, 585.0), (616, 488)))
        self.assertEqual(GEISA_POINTS["PL_BLUE"], GEISA_POINTS["VILLAGE_E"])
        for name, (x, y) in GEISA_POINTS.items():
            with self.subTest(point=name):
                self.assertTrue(0 <= x < GEISA.minimap_px[0] and 0 <= y < GEISA.minimap_px[1])
        with self.assertRaises(TypeError):
            GEISA_POINTS["NECK_MID"] = (0, 0)  # type: ignore[index]

    def test_boxes(self):
        self.assertEqual(dict(GEISA_BOXES), {"TOWN_SW": (90, 610, 190, 700)})
        with self.assertRaises(TypeError):
            GEISA_BOXES["X"] = (0, 0, 1, 1)  # type: ignore[index]


class SharedForces(unittest.TestCase):
    def test_soviet_rows(self):
        """The Soviet groups more than one example op creates, at 1x, each spawning at a shared point."""
        totals = {g: group_total(GEISA_SOVIET_ROWS, g) for g in dict.fromkeys(r.group for r in GEISA_SOVIET_ROWS)}
        self.assertEqual(totals, {"main_body": 63, "pocket_ad": 6, "relief": 55, "opener_battery": 6, "probe": 4})
        self.assertEqual({r.camp for r in GEISA_SOVIET_ROWS}, {"PACT"})
        self.assertLessEqual({r.spawn for r in GEISA_SOVIET_ROWS}, set(GEISA_POINTS))
        self.assertEqual([(r.unit, r.count, r.transport) for r in GEISA_SOVIET_ROWS if r.group == "main_body"],
                         [("T80BV_SOV", 30, None), ("T80BV_CMD_SOV", 1, None), ("BMP_2_SOV", 10, None),
                          ("MotRifles_SOV", 9, "BMP_2_SOV"), ("BRDM_2_Konkurs_SOV", 3, None),
                          ("2S3M_Akatsiya_SOV", 6, None), ("BMP_1_CMD_SOV", 1, None), ("MTLB_supply_SOV", 3, None)])
        self.assertFalse(any(r.fixed for r in GEISA_SOVIET_ROWS))
        self.assertIsInstance(GEISA_SOVIET_ROWS, tuple)


class Forces(unittest.TestCase):
    ROWS = tuple(rows_of("a", "E", "P1", "first", ForceRow("Tank", 10), ForceRow("Rifles", 5, "Truck"))
                 + rows_of("b", "F", "P2", "second", ForceRow("Heli", 3), fixed=True))

    def test_rows_of(self):
        self.assertEqual(self.ROWS[1], ForceRow("Rifles", 5, "Truck", group="a", camp="E", spawn="P1", echelon="first"))
        self.assertTrue(self.ROWS[2].fixed)
        self.assertEqual(group_total(self.ROWS, "a"), 15)

    def test_scaled(self):
        self.assertEqual([r.count for r in scaled(self.ROWS, 1.5)], [15, 8, 3])   # 7.5 rounds up; fixed stays
        self.assertEqual([r.count for r in scaled(self.ROWS, 0.01)], [1, 1, 3])   # never below 1
        self.assertEqual([r.count for r in group_rows(self.ROWS, "a", 2.0)], [20, 10])
        with self.assertRaises(ValueError):
            scaled(self.ROWS, 0)

    def test_share_count(self):
        self.assertEqual([share_count(s, 40) for s in (0.28, 0.42, 0.55)], [11, 17, 22])
        self.assertEqual((share_count(0.01, 5), share_count(2.0, 5), share_count(0.5, 0)), (1, 5, 0))

    def test_formation(self):
        self.assertEqual(formation((100, 100), 4, 8.0, 2), [(96.0, 96.0), (104.0, 96.0), (96.0, 104.0), (104.0, 104.0)])
        self.assertEqual(formation((0, 0), 3, 10.0, 3), [(-10.0, 0.0), (0.0, 0.0), (10.0, 0.0)])
        with self.assertRaises(ValueError):
            formation((0, 0), 1, 1.0, 0)


if __name__ == "__main__":
    unittest.main()
