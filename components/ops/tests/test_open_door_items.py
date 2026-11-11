"""Tests for Open Door's geometry: every item of the op in both tier modes, against the playable zone, the shipped
zone files and Geisa's Minimap (the lanes' roads included)."""
from __future__ import annotations

import math
import unittest

from modkit.core import tgv
from modkit.ops import gates
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA
from modkit.ops.profile import extracted
from modkit.ops.zones import point_in_polygon
from open_door_support import (
    MAP_DATA, PICTURES, SCRIPT_DATA, details_files, end_px, road_steps, zones_holding, ROAD_LUMINANCE, TRACK_LUMINANCE,
)
from opendoor import forces, profile
from opendoor import op as mission
from opendoor.map import MAP, POINTS
from modkit.ops.maps import GEISA_BOXES, GEISA_POINTS
from probes import spike as probe1   # the op takes some of its values from the probes
from probes import spike2 as probe2

px_of, radius_px, box_px = MAP.px_of, MAP.radius_px, MAP.box_px


@SCRIPT_DATA
@MAP_DATA
@PICTURES
class Items(unittest.TestCase):
    """The op's geometry (one place: mission.items), in both tier modes."""

    @classmethod
    def setUpClass(cls):
        cls.items = {mode: mission.items(mode) for mode in mission.TIER_MODES}
        cls.details = {mode: details_files(cls.items[mode], profile.SCENARIO) for mode in mission.TIER_MODES}
        hdr, rgba = tgv.read_tgv(extracted(GEISA.picture("Minimap")))
        cls.minimap_w, cls.minimap = hdr.width, tgv.drop_alpha(rgba)
        cls.ring = GEISA.playable_polygon()

    def luminance(self, p: tuple[float, float]) -> int:
        i = (round(p[1]) * self.minimap_w + round(p[0])) * 3
        return sum(self.minimap[i:i + 3]) // 3

    def by_name(self, mode: str = "tiered") -> dict[str, LdItem]:
        return {it.name: it for it in self.items[mode]}

    def test_default_mode_and_items(self):
        """"tiered" is the default (pl_blue hands the towns over, pl_green the necks); ITEMS is the default mode's; the
        two modes differ by the five fixed-mode deployment zones only; names are unique."""
        self.assertEqual(mission.TIER_MODE, "tiered")
        self.assertEqual(mission.ITEMS, mission.items("tiered"))
        tiered, fixed = self.by_name("tiered"), self.by_name("fixed")
        self.assertEqual(len(tiered), len(self.items["tiered"]))
        self.assertEqual(sorted(set(fixed) - set(tiered)), sorted(f"OD_DZ_{t.name[3:]}" for t in mission.TIERS))
        self.assertEqual({n: it for n, it in fixed.items() if n in tiered}, tiered)

    def test_inside_the_playable_zone(self):
        """Every point, Start and End, and every item's point and polygon (Geisa's west-edge entries start at the map
        edge and are not checked)."""
        for name, p in [*mission.POINTS_OP.items(), *((t.name + " start", t.start) for t in mission.TIERS),
                        *((t.name + " end", t.end) for t in mission.TIERS)]:
            with self.subTest(point=name):
                self.assertTrue(point_in_polygon(*GEISA.px_to_world(p), self.ring), (name, p))
        west = {it.name for it in GEISA.player_arrivals("OD")}
        for it in self.items["fixed"]:
            if it.name in west:
                continue
            with self.subTest(item=it.name):
                for p in it.polygon or ((it.x, it.y),):
                    self.assertTrue(point_in_polygon(*p, self.ring), (it.name, GEISA.world_to_px(p)))

    def test_points_op(self):
        """The mission's points sit where their reasons say: the east Starts and the lane waypoints on a road or
        built-up pixel of Geisa's Minimap, the neck Starts on a forest track, as do ENTRY_SE and FARM_ROAD (the captured
        T-80U's), places shared with the probes; the design's points are unchanged (design 3)."""
        for name in ("START_TOWN_NE", "START_VILLAGE_E", "START_TOWN_SE", "SACK_S", "ANVIL_C", "ENTRY_SE", "FARM_ROAD"):
            with self.subTest(road=name):
                self.assertGreaterEqual(self.luminance(mission.px(name)), ROAD_LUMINANCE)
        for name in ("START_NECK_MID", "START_NECK_S"):
            with self.subTest(track=name):
                self.assertGreaterEqual(self.luminance(mission.POINTS_OP[name]), TRACK_LUMINANCE)
        self.assertEqual((mission.px("ENTRY_SE"), mission.px("FARM_ROAD")), ((756.0, 585.0), (616, 488)))
        self.assertFalse(set(mission.POINTS_OP) & set(POINTS))
        self.assertEqual(POINTS["SACK_MID"], (340, 406))
        self.assertLessEqual(math.dist(mission.POINTS_OP["ANVIL_C"], (138, 480)), 5)  # design 3's anvil vertex

    def test_shared_places_are_read_not_copied(self):
        """Every place Open Door shares with the probes comes from the one shared table: its own points name none of
        them, its POINTS hold every one at the shared value, and Town SW's zone is the shared box."""
        from opendoor.map import OWN_POINTS
        self.assertFalse(set(OWN_POINTS) & set(GEISA_POINTS))
        self.assertFalse(set(mission.POINTS_OP) & set(GEISA_POINTS))
        self.assertEqual({k: POINTS[k] for k in GEISA_POINTS}, dict(GEISA_POINTS))
        self.assertIs(mission.ANVIL_CZ["OD_CZ_SW"], GEISA_BOXES["TOWN_SW"])
        self.assertIs(probe1.CZ_SW, GEISA_BOXES["TOWN_SW"])

    def test_tiers(self):
        """The tiers: the east Starts on a road 40-85 px W of their town; the neck Starts on the jaws' tracks, N of NECK
        MID (x about 380) and S of NECK S, outside the neck's zone; each End END_INSET_PX inside its zone's edge facing
        the Start, east Ends outside the town's rearguard zone (its zone minus the west 12 px)."""
        self.assertEqual([(t.name, t.tier, t.cz) for t in mission.TIERS],
                         [("OD_RL_TownNE", "east", "OD_CZ_TownNE"), ("OD_RL_VillageE", "east", "OD_CZ_VillageE"),
                          ("OD_RL_TownSE", "east", "OD_CZ_TownSE"), ("OD_RL_NeckMid", "neck", "OD_CZ_NeckMid"),
                          ("OD_RL_NeckS", "neck", "OD_CZ_NeckS")])
        tiers = {t.name: t for t in mission.TIERS}
        for t, town in zip(mission.TIERS[:3], ("TOWN_NE", "VILLAGE_E", "TOWN_SE")):
            with self.subTest(tier=t.name):
                x, y = POINTS[town]
                self.assertTrue(40 <= x - t.start[0] <= 85, t.start)
                self.assertLess(abs(t.start[1] - y), 20)
                self.assertEqual(t.end, (x - 30 + 6, y))
                self.assertLess(t.end[0], mission.rearguard_box(town)[0])
        mid, s = tiers["OD_RL_NeckMid"], tiers["OD_RL_NeckS"]
        (mx, my), (sx, sy) = POINTS["NECK_MID"], POINTS["NECK_S"]
        self.assertLessEqual(abs(mid.start[0] - 380), 5)
        self.assertLess(mid.start[1], my - 30)
        self.assertGreater(s.start[1], sy + 30)
        self.assertEqual((mid.end, s.end), ((mx, my - 24), (sx, sy + 24)))
        for it in self.items["tiered"]:
            if it.name in tiers:
                t = tiers[it.name]
                with self.subTest(item=it.name):
                    self.assertEqual((it.ranking, it.addon, it.num_alliance), ("ReinforcementLocations",
                                                                               "ReinforcementLocation", None))
                    self.assertEqual((GEISA.world_to_px(it.start), end_px(it)), (t.start, t.end))
                    self.assertAlmostEqual(it.rotation, math.atan2(it.end[1] - it.start[1], it.end[0] - it.start[0]))
                    self.assertEqual((it.x, it.y), ((it.start[0] + it.end[0]) / 2, (it.start[1] + it.end[1]) / 2))

    def test_tier_ends_in_their_zone_only(self):
        """Read from the shipped zone files: in "tiered" mode each End lies in its own command zone and in no
        deployment zone; in "fixed" mode in its own small player deployment zone too, and no other."""
        for t in mission.TIERS:
            with self.subTest(tier=t.name):
                self.assertEqual(zones_holding(self.details["tiered"], "CommandPoints", t.end), [(t.cz, 0)])
                self.assertEqual(zones_holding(self.details["tiered"], "DeploymentZone", t.end), [])
                self.assertEqual(zones_holding(self.details["fixed"], "CommandPoints", t.end), [(t.cz, 0)])
                self.assertEqual(zones_holding(self.details["fixed"], "DeploymentZone", t.end),
                                 [(f"OD_DZ_{t.name[3:]}", 0)])
                dz = self.by_name("fixed")[f"OD_DZ_{t.name[3:]}"]
                self.assertEqual(box_px(dz), (t.end[0] - 6, t.end[1] - 6, t.end[0] + 6, t.end[1] + 6))

    def test_zones(self):
        """The command zones (60 px squares; the anvil's on ANVIL_N and ANVIL_C, probe 1's OD_CZ_SW) keep apart; no
        deployment zone touches a neck zone (in "fixed" mode only the neck tier's own); the west arrivals end in the
        anvil zone, which holds the three anvil command zones; every command zone is forced to NATO at load."""
        items = self.by_name("tiered")
        czs = [it for it in self.items["tiered"] if it.addon == "CommandPoints"]
        self.assertEqual([it.name for it in czs], list(mission.OWNED_AT_LOAD))
        self.assertEqual(sorted(mission.OWNED_AT_LOAD), sorted({*mission.TOWN_CZ, *mission.NECK_CZ, *mission.ANVIL_CZ}))
        for k, a in enumerate(czs):
            self.assertEqual(a.points, probe1.CZ_POINTS)
            for b in czs[k + 1:]:
                self.assertFalse(gates.polygons_overlap(a.polygon, b.polygon), (a.name, b.name))
        for name, point in {**mission.TOWN_CZ, **mission.NECK_CZ}.items():
            x, y = POINTS[point]
            self.assertEqual(box_px(items[name]), (x - 30, y - 30, x + 30, y + 30))
        self.assertEqual(box_px(items["OD_CZ_SW"]), probe1.CZ_SW)
        for mode in mission.TIER_MODES:
            for dz in (it for it in self.items[mode] if it.addon == "DeploymentZone"):
                for neck in mission.NECK_CZ:
                    with self.subTest(mode=mode, dz=dz.name, neck=neck):
                        own = dz.name == f"OD_DZ_RL_{neck.removeprefix('OD_CZ_')}"
                        self.assertEqual(gates.polygons_overlap(dz.polygon, items[neck].polygon), own)
        anvil = items["OD_DZ_Anvil"]
        self.assertEqual(box_px(anvil), (13, 250, 260, 800))
        for it in GEISA.player_arrivals("OD"):
            self.assertTrue(point_in_polygon(*it.end, list(anvil.polygon)), it.name)
        for name in mission.ANVIL_CZ:
            self.assertTrue(all(point_in_polygon(*p, list(anvil.polygon)) for p in items[name].polygon), name)
        for name, point in mission.TOWN_DZ.items():
            x, y = POINTS[point]
            self.assertEqual((items[name].alliance, box_px(items[name])), (None, (x - 18, y - 30, x + 30, y + 30)))
        self.assertEqual(box_px(items["OD_DZ_Shoulder"]), (490, 251, 550, 311))

    def test_rings(self):
        """The circles: the sack's five (the lane exits and the kill zone) W of the necks and clear of every neck and
        anvil zone; each approach just E of its neck's zone and clear of it; the rear exit at EDGE W."""
        items = self.by_name()
        rings = [it for it in self.items["tiered"] if it.addon == "CircularZone"]
        self.assertEqual([it.name for it in rings], list(mission.RINGS))
        for it in rings:
            point, radius = mission.RINGS[it.name]
            with self.subTest(ring=it.name):
                self.assertEqual((it.ranking, px_of(it)), ("CircularZones", mission.px(point)))
                self.assertAlmostEqual(radius_px(it), radius, places=6)

        def gap(ring: LdItem, zone: str) -> float:  # px from the circle to the square (negative: overlap)
            x0, y0, x1, y1 = box_px(items[zone])
            (x, y), r = px_of(ring), radius_px(ring)
            return math.hypot(max(x0 - x, 0, x - x1), max(y0 - y, 0, y - y1)) - r

        zones = [*mission.NECK_CZ, *mission.ANVIL_CZ]
        sack = (("OD_RingSackMid", "OD_CZ_NeckMid"), ("OD_RingSackS", "OD_CZ_NeckS"),
                ("OD_RingPlainN", "OD_CZ_NeckMid"), ("OD_RingPlainC", "OD_CZ_NeckMid"),
                ("OD_RingPlainS", "OD_CZ_NeckMid"))
        self.assertEqual(mission.SACK_RINGS, tuple(name for name, _ in sack))   # the sack count reads these five
        for name, neck in sack:
            with self.subTest(sack=name):
                self.assertTrue(all(gap(items[name], z) > 0 for z in zones), [gap(items[name], z) for z in zones])
                self.assertLess(px_of(items[name])[0] + radius_px(items[name]), box_px(items[neck])[0])  # W of it
        self.assertEqual(mission.B6_PAIRS, (("OD_CZ_NeckMid", "OD_RingApprMid"), ("OD_CZ_NeckS", "OD_RingApprS")))
        for neck, name in mission.B6_PAIRS:
            with self.subTest(approach=name):
                self.assertTrue(0 < gap(items[name], neck) <= 10, gap(items[name], neck))
                self.assertGreater(px_of(items[name])[0], box_px(items[neck])[2])
        self.assertEqual(px_of(items["OD_RingRear"]), POINTS["EDGE_W"])

    def test_hidden_units(self):
        """The jaws: one hidden player spawn per unit of the force table's rows at FORCE_SCALE, in a formation centred
        on RESERVE N and HIDE S, outside every zone; OD_Captured: a hidden T80U_SOV Camp_0 item at (616, 488), outside
        every command zone."""
        for group, (prefix, point, cols) in mission.JAWS.items():
            with self.subTest(jaw=group):
                jaw = [it for it in self.items["fixed"] if it.group == group]
                want = [r.descriptor for r in forces.force_rows(group) for _ in range(r.count)]
                self.assertEqual([it.unit for it in jaw], want)
                self.assertEqual(len(jaw), forces.group_total(forces.ROWS, group))
                self.assertEqual({(it.ranking, it.camp, it.disable_auto_spawn) for it in jaw}, {("Camp_0", 0, True)})
                self.assertEqual([it.name for it in jaw], [f"{prefix}_{k + 1:02d}" for k in range(len(jaw))])
                xs, ys = zip(*(px_of(it) for it in jaw))
                self.assertEqual(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2), POINTS[point])
                for it in jaw:
                    for addon in ("CommandPoints", "DeploymentZone"):
                        self.assertEqual(zones_holding(self.details["fixed"], addon, px_of(it)), [], it.name)
        cap = self.by_name()["OD_Captured"]
        self.assertEqual((cap.ranking, cap.addon, cap.unit, cap.camp, cap.disable_auto_spawn, px_of(cap)),
                         ("Camp_0", "Spawn", "T80U_SOV", 0, True, (616.0, 488.0)))
        self.assertEqual(zones_holding(self.details["fixed"], "CommandPoints", px_of(cap)), [])

    def test_first_echelon_lanes_on_the_minimap(self):
        """Each first-echelon lane, from its entry tag to the town it seizes (the command zone's own point, its town's),
        lies on Geisa's roads, as probe 2's traffic did (the probe tests' test_traffic_road_on_the_minimap): the towns
        on built-up pixels, ENTRY SE on its road, ENTRY E within 3 px of one (probe 2's reaches). ENTRY N (a shared
        point) sits on the faint E-W road nearest the north edge, which the Minimap draws at 33-36
        against the forest's 24-29 either side: a minor road, darker than ROAD_LUMINANCE."""
        items = self.by_name("fixed")
        self.assertEqual([(c.key, c.entry, c.town) for c in mission.FE_COMPANIES],
                         [("n", "OD_EntryN", "OD_CZ_TownNE"), ("c", "OD_EntryE", "OD_CZ_VillageE"),
                          ("s", "OD_EntrySE", "OD_CZ_TownSE")])
        for c in mission.FE_COMPANIES:
            with self.subTest(town=c.town):
                self.assertEqual(px_of(items[c.town]), mission.px(mission.TOWN_CZ[c.town]))
                self.assertGreaterEqual(self.luminance(px_of(items[c.town])), 70)       # built-up
        for name, reach in (("OD_EntrySE", 0), ("OD_EntryE", 3)):
            with self.subTest(entry=name):
                p = px_of(items[name])
                self.assertGreaterEqual(max(self.luminance((p[0] + dx, p[1] + dy)) for dx in range(-reach, reach + 1)
                                            for dy in range(-reach, reach + 1)), ROAD_LUMINANCE)
        north = px_of(items["OD_EntryN"])
        self.assertEqual(north, POINTS["ENTRY_N"])
        self.assertGreaterEqual(self.luminance(north), 33)
        self.assertLessEqual(max(self.luminance((north[0], north[1] + dy)) for dy in (-10, 8)), 29)

    def test_main_body_lanes_on_roads(self):
        """Each lane's entry and waypoints (their tags) stand on Geisa's roads or built-up pixels (ENTRY E within 3 px
        of one, as probe 2's), and a road joins each waypoint to the next (8-connected road pixels); each
        blocking leg's timeout is LEG_PACE_S_PER_PX on that road's length, rounded up to 10 s, at least LEG_MIN_S;
        both lanes end at the rear exit (OD_RingRear's centre). MID passes NECK MID and SACK MID, BOTTOM Town SE,
        NECK S, SACK S and Town SW (design 3's passage and defile)."""
        items = self.by_name()
        self.assertEqual({lane: [l.entry, *(leg.to for leg in l.legs)] for lane, l in mission.LANES.items()},
                         {"MID": ["OD_EntryE", "OD_NeckMid", "OD_SackMid", "OD_AnvilC", "OD_RearExit"],
                          "BOTTOM": ["OD_EntrySE", "OD_TownSE", "OD_NeckS", "OD_SackS", "OD_TownSW", "OD_RearExit"]})
        self.assertEqual(px_of(items["OD_RearExit"]), px_of(items["OD_RingRear"]))
        self.assertAlmostEqual(mission.LEG_PACE_S_PER_PX * 362, probe2.TRAFFIC_LEG_S)
        for lane, l in mission.LANES.items():
            points = [px_of(items[name]) for name in (l.entry, *(leg.to for leg in l.legs))]
            for name, p in zip((l.entry, *(leg.to for leg in l.legs)), points):
                with self.subTest(lane=lane, waypoint=name):
                    reach = 3 if name == "OD_EntryE" else 0
                    around = range(-reach, reach + 1)
                    best = max(self.luminance((p[0] + dx, p[1] + dy)) for dx in around for dy in around)
                    self.assertGreaterEqual(best, ROAD_LUMINANCE)
            for leg, a, b in zip(l.legs, points, points[1:]):
                with self.subTest(lane=lane, leg=leg.to):
                    steps = road_steps(self.luminance, a, b)
                    self.assertIsNotNone(steps)
                    self.assertLessEqual(steps, 1.5 * math.dist(a, b) + 10)   # the road, not a detour across the map
                    if leg.timeout is not None:
                        want = max(mission.LEG_MIN_S, mission.LEG_PACE_S_PER_PX * steps)
                        self.assertTrue(want <= leg.timeout <= want + 10 + 5, (steps, want, leg.timeout))

    def test_captured_tank(self):
        """The captured cards' backup: OD_Captured is hidden (DisableAutoSpawn), Camp 0, a T80U_SOV, at probe 2's
        NATO CMD spot on a road (FARM_ROAD), in no command zone, no deployment zone and no circle, so nothing counts it
        before it is revealed."""
        cap = self.by_name("fixed")["OD_Captured"]
        self.assertEqual((cap.camp, cap.disable_auto_spawn, cap.unit, px_of(cap)),
                         (0, True, "T80U_SOV", (616.0, 488.0)))
        self.assertGreaterEqual(self.luminance(px_of(cap)), ROAD_LUMINANCE)
        for mode in mission.TIER_MODES:
            for addon in ("CommandPoints", "DeploymentZone"):
                self.assertEqual(zones_holding(self.details[mode], addon, px_of(cap)), [], (mode, addon))
        for ring in (it for it in self.items["fixed"] if it.addon == "CircularZone"):
            self.assertGreater(math.dist(px_of(cap), px_of(ring)), radius_px(ring), ring.name)

    def test_tags(self):
        """The spawn and waypoint tags: the first echelon's three entries and each lane's named waypoints."""
        items = self.by_name()
        for name, point in mission.TAGS.items():
            with self.subTest(tag=name):
                self.assertEqual((items[name].ranking, items[name].addon, px_of(items[name])),
                                 ("Tags", "Name", mission.px(point)))
        self.assertEqual({mission.TAGS[n] for n in ("OD_EntryN", "OD_EntryE", "OD_EntrySE")},
                         {"ENTRY_N", "ENTRY_E", "ENTRY_SE"})



# The nine places design 3 fixes, exact (the rest of the table is read off the storyline map).
DESIGN_POINTS = {"TOWN_NE": (658, 232), "VILLAGE_E": (700, 475), "TOWN_SE": (645, 590), "SHOULDER": (520, 281),
                 "RESERVE_N": (352, 270), "NECK_MID": (395, 402), "LZ_MID": (386, 382), "NECK_S": (468, 600),
                 "HIDE_S": (522, 740)}


def distance_to_segment(p: tuple[float, float], a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from point p to the segment a-b."""
    dx, dy = b[0] - a[0], b[1] - a[1]
    t = 0.0 if dx == dy == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / (dx * dx + dy * dy)))
    return math.hypot(p[0] - (a[0] + t * dx), p[1] - (a[1] + t * dy))


class Places(unittest.TestCase):
    """opendoor.map's named points: pure data, and their frame."""

    def test_frame(self):
        self.assertEqual(GEISA.px_to_world((386, 382)), (988160.0, 977920.0))
        self.assertEqual(GEISA.world_to_px(GEISA.px_to_world((395.5, 402.25))), (395.5, 402.25))
        self.assertEqual(GEISA.px_to_world(GEISA.minimap_px), (1966080.0, 2621440.0))

    def test_design_points(self):
        for name, px in DESIGN_POINTS.items():
            with self.subTest(point=name):
                self.assertEqual(POINTS[name], px)
        self.assertEqual(POINTS["PL_BLUE"], POINTS["VILLAGE_E"])

    def test_points_cover_spawns(self):
        self.assertLessEqual({r.spawn for r in forces.ROWS}, POINTS.keys())

    @MAP_DATA
    def test_points_inside_playable_zone(self):
        """Every named point, the op's own included, is inside Geisa's playable ring and at least 8 px from each
        edge."""
        ring = [GEISA.world_to_px(p) for p in GEISA.playable_polygon()]
        for name, (x, y) in {**POINTS, **mission.POINTS_OP}.items():
            with self.subTest(point=name):
                self.assertTrue(point_in_polygon(x, y, ring), "outside the playable zone")
                near = min(distance_to_segment((x, y), a, b) for a, b in zip(ring, ring[1:]))
                self.assertGreaterEqual(near, 8.0, f"{near:.1f} px from an edge")


if __name__ == "__main__":
    unittest.main()
