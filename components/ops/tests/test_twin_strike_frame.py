"""Tests for Twin Strike's frame (examples/twin-strike: twinstrike.profile, .strings and .op, and build.py): the op
loads with every unit in place. The mission on it is test_twin_strike_mission's.

`Identity`, `Profile`, `Items`, `Ranges`, `Camera` and `Strings` need no stock data: the identity beside Open Door and
the probes, the profile's settings, where every item stands and in which camp, the guns' bands, the opening camera's
keys and the string table. `Script` builds the frame's script from Survivors' and pins its shapes: the camps, the
setup before LoadingDone (the village's owner), the opening camera after it, the deck's adds and locks and the groups
of the pre-placed units. `Build` builds the op through its build.py front end, every gate included. Classes that read
the stock extraction or the game install skip without them."""
from __future__ import annotations

import contextlib
import dataclasses
import io
import math
import os
import re
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid
from unittest import mock

from test_gates_stock import MENU_SPANS
from twin_strike_support import (
    GAME, LAYOUT_DATA, OUT_ROOT, SCRIPT_DATA, TWIN_STRIKE, build_main, build_profile, gru, quiet_build,
)
from modkit.core import edat, paths, tgv, trad
from modkit.core.gates import CheckError
from modkit.ops import INGAME_DIC, gates, leveldesign, menuart
from modkit.ops import testing as ops_testing
from modkit.ops.bricks import unit_path
from modkit.ops.files import read_file
from modkit.ops.graph import decode, nodes_of, walk
from modkit.ops.items import MENU_ART
from modkit.ops.maps import CAMPATHS_FILE, START_CAMERA_MIN_HEIGHT, TWIN_CITIES, view_centre
from modkit.ops.profile import (
    SOVIET_PLAYER_CAMP_ROWS, SOVIET_PLAYER_DECK_SWAP, SOVIET_PLAYER_SIDES, STOCK_ASSETS, SURVIVORS, extracted,
)
from modkit.ops.rekey import def_path
from modkit.ops.script import BRICK_DEFAULT, PRODUCTION_DECK
from modkit.ops.shapes import GRU_WORLD, TRANSPORTER_SHAPE
from modkit.ops.strings import LANGS
from modkit.ops.testing import cmp_of, last, of, prop, remove_out, subs, token
from modkit.ops.zones import point_in_polygon
from twinstrike import CONTENTS, forces, map as ts_map, op, profile, strings

OUT = os.path.join(OUT_ROOT, "op")
GD = "$/GDScript"
# Each menu token's element of MapConfiguration's DescriptionTextElements: Survivors' own, re-keyed (Build checks it).
MENU_ELEMENTS = {"ts_name": "MissionName", "ts_cname": "TitreObjectifs", "ts_headr": "TexteForcesEnPresence",
                 "ts_order": "TextePresentationScenario", "ts_recap": "TexteObjectifs",
                 "ts_vic": "VictoryOperationOutcomeText", "ts_def": "DefeatOperationOutcomeText"}
MENU_PICTURES = ("MapTexture", "CornerLogo", "MissionCountry", "EndgameBlazon")  # DescriptionTextureElements


def units(text: str) -> int:
    """`text`'s length in UTF-16 code units, as the game measures it."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def item(name: str):
    (it,) = [x for x in op.ITEMS if x.name == name]
    return it


def px(it) -> tuple[float, float]:
    return TWIN_CITIES.world_to_px((it.x, it.y))


def spawns(group: str):
    return [it for it in op.ITEMS if it.addon == "Spawn" and it.group == group]


class LazyPaths(unittest.TestCase):
    def test_unconfigured_import_and_build(self):
        """Importing the example resolves no path; build.py with neither the extraction nor the game folder
        configured prints one FAILED line naming warno-setup and exits 1, no traceback, nothing written."""
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            code = textwrap.dedent(f"""
                import runpy, sys
                from modkit.core import paths
                paths._code_dirs = lambda: []          # only the working folder (empty) is searched
                sys.path.insert(0, {str(TWIN_STRIKE)!r})
                import twinstrike, twinstrike.forces, twinstrike.map, twinstrike.op, twinstrike.profile
                import twinstrike.strings
                sys.argv = ["build.py", "--content", "op", "--out", {out!r}]
                runpy.run_path({str(TWIN_STRIKE / "build.py")!r}, run_name="__main__")
            """)
            env = {k: v for k, v in os.environ.items() if not k.startswith("MODKIT_")}
            r = subprocess.run([sys.executable, "-c", code], cwd=tmp, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            (line,) = r.stderr.strip().splitlines()
            self.assertTrue(line.startswith("FAILED: ") and "warno-setup" in line, line)
            self.assertFalse(os.path.exists(out))


class Identity(unittest.TestCase):
    def test_identity(self):
        """challenge_OperationTwinStrike in TwinStrike, uuid5 GUID under warno-twinstrike, menu prefix ts, title
        "Operation Twin Strike"; the title check holds the two titles only."""
        c = op.content()
        self.assertEqual(sorted(CONTENTS), ["op"])
        self.assertEqual((c.name, c.scenario, c.mod_name), ("op", "challenge_OperationTwinStrike", "TwinStrike"))
        self.assertEqual(leveldesign.scenario_guid(c.scenario, profile.GUID_NAMESPACE),
                         uuid.uuid5(uuid.NAMESPACE_URL, "warno-twinstrike/challenge_OperationTwinStrike").bytes)
        self.assertEqual(c.menu_renames, tuple((f"op13_{k}", f"ts_{k}") for k in
                                               ("name", "order", "headr", "cname", "recap", "vic", "def")))
        self.assertEqual(profile.MENU_TOKENS, tuple(dict(c.menu_renames).values()))
        self.assertEqual(sorted(strings.STRINGS["SCENARIO_DEFINITION"]), sorted(profile.MENU_TOKENS))
        self.assertEqual(c.menu_tokens, profile.TITLE_TOKENS)
        self.assertEqual(profile.TITLE_TOKENS, ("ts_name", "ts_cname"))
        self.assertEqual(strings.ENGLISH["SCENARIO_DEFINITION"]["ts_name"], "Operation Twin Strike")
        self.assertEqual(strings.ENGLISH["SCENARIO_DEFINITION"]["ts_cname"], "OPERATION TWIN STRIKE")
        self.assertEqual(CONTENTS["op"]().scenario, profile.SCENARIO)

    def test_installs_beside_open_door_and_the_probes(self):
        """Twin Strike's scenario, GUID, mod folder and menu-token prefix are its own: no Open Door or probe content
        shares one [[content-identity-unique]]."""
        from open_door_support import CONTENTS as OPEN_DOOR
        from open_door_support import profile as od_profile
        from probes import CONTENTS as PROBES
        mine = op.content()
        prefix = mine.menu_tokens[0].split("_")[0]
        for name, make in (*OPEN_DOOR.items(), *PROBES.items()):
            other = make()
            with self.subTest(content=name):
                self.assertNotEqual(other.scenario, mine.scenario)
                self.assertNotEqual(other.mod_name, mine.mod_name)
                self.assertNotEqual(other.menu_tokens[0].split("_")[0], prefix)
        self.assertNotEqual(profile.GUID_NAMESPACE, od_profile.GUID_NAMESPACE)


class Profile(unittest.TestCase):
    def test_the_soviet_player_shape(self):
        """The camps, sides and menu deck are modkit.ops.profile's Soviet-player shape, not a copy."""
        self.assertIs(profile.CAMP_ROWS, SOVIET_PLAYER_CAMP_ROWS)
        self.assertIs(profile.CAMPS, SOVIET_PLAYER_SIDES)
        self.assertIs(profile.DECK_SWAP, SOVIET_PLAYER_DECK_SWAP)
        self.assertEqual(profile.CAMPS[profile.PLAYER], "joueur")
        self.assertEqual({side: profile.camp_index(side) for side in profile.CAMPS},
                         {"Soviet": 0, "SovietAlly": 1, "NATO2": 2, "NATO": 3})
        self.assertEqual(set(profile.CAMP_TOKENS), {name for name, _, _ in SOVIET_PLAYER_CAMP_ROWS})

    def test_settings(self):
        """Survivors on Twin Cities: no map Details copied (the cut and the camera are generated), the cut's and the
        camera's stock shape sources, the five extra gates, the end funnel's export, and RedJuggernaut's three menu
        emblems with the op's own generated map picture."""
        p = profile.profile()
        self.assertIs(p.template, SURVIVORS)
        stock_art = {name: stock for name, stock in p.menu_art.items() if isinstance(stock, str)}
        self.assertEqual(stock_art, dict.fromkeys(("CornerLogo", "MissionCountry", "EndgameBlazon"),
                                                  "challenge_RedJuggernaut"))
        self.assertEqual(set(p.menu_art) - set(stock_art), {"MapTexture"})
        self.assertTrue(callable(p.menu_art["MapTexture"]))
        self.assertEqual((p.map_details, p.map_copies, p.ground_z), (TWIN_CITIES.details, (), TWIN_CITIES.ground_z))
        self.assertEqual(p.map_strings, {"_3x3_Railway": "_3x3_TwinCities"})
        self.assertEqual(p.map_trans, {"Railway": "TwinCities"})
        self.assertIs(p.deck_swap, SOVIET_PLAYER_DECK_SWAP)
        self.assertEqual((p.player_camp, p.enemy_camp), ("joueur", "ordinateur_SOV"))
        self.assertEqual([g.name for g in p.extra_gates], ["units", "no-template-name", "grid", "zone-layout",
                                                           "menu-order", "fire-range"])
        self.assertEqual(profile.PRODUCTION_TYPE, PRODUCTION_DECK)
        self.assertEqual(p.extra_items, (ts_map.CUT.items, ts_map.CAMERA.items))
        self.assertLessEqual({"out/PlayableZone.ndfbin", "out/IAStratZone.ndfbin", "out/IAStrat_PathCache.ndfbin",
                              CAMPATHS_FILE}, set(p.shape_sources))
        self.assertEqual(p.end_exports, (f"{GD}/TS/EndFunnel",))


class Items(unittest.TestCase):
    def test_every_item_is_inside_the_cut_and_named_once(self):
        """Every item, the guns' spawn tag among them: a unit created outside the playable zone stands on its edge
        [[created-units-stand-in-zone]]."""
        x0, y0, x1, y1 = ts_map.CUT_PX
        names = [it.name for it in op.ITEMS]
        self.assertEqual(len(names), len(set(names)))
        for it in op.ITEMS:
            with self.subTest(item=it.name):
                x, y = px(it)
                self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1, (x, y))

    def test_the_map_items_are_kept(self):
        self.assertEqual(op.ITEMS[:len(ts_map.items())], ts_map.items())

    def test_garrison(self):
        """Design 6.3's garrison, pre-placed and auto-spawned in the NATO camp (Camp_3), every unit of each row at its
        post, inside the village's command zone and its detector circle, facing the Soviet box."""
        garrison = spawns("garrison")
        self.assertEqual([it.unit for it in garrison],
                         [r.descriptor for r in forces.force_rows("garrison") for _ in range(r.count)])
        zone, ring = item(op.VILLAGE_ZONE), item(op.VILLAGE_RING)
        radius = ring.radius_gru * GRU_WORLD
        for it in garrison:
            with self.subTest(item=it.name):
                self.assertEqual((it.ranking, it.camp, it.disable_auto_spawn), ("Camp_3", 3, False))
                self.assertEqual(it.rotation, op.GARRISON_FACING)
                self.assertTrue(point_in_polygon(it.x, it.y, list(zone.polygon)))
                self.assertLess(math.dist((it.x, it.y), (ring.x, ring.y)), radius)
        self.assertTrue(-math.pi < op.GARRISON_FACING < 0)   # world y grows south: a negative heading faces north

    def test_no_gun_is_preplaced(self):
        """The division artillery is created for each fire at GUN_SPAWN (a Name tag), never pre-placed: no Spawn item
        holds a 2S7M or a BM-27, and nothing stands in the player's AI ally's camp (Camp_1)."""
        self.assertEqual([it for it in op.ITEMS if it.unit in ("2S7M_Malka_SOV", "BM27_Uragan_SOV")], [])
        self.assertEqual([it for it in op.ITEMS if it.ranking == "Camp_1"], [])
        self.assertEqual((item(op.GUN_SPAWN).addon, px(item(op.GUN_SPAWN))), ("Name", ts_map.POINTS["GUN_SPAWN"]))

    def test_fobs_ring_and_tags(self):
        """The FOBs are the map's, in the player's camp, as forces' rows say; the village's circle is 40 px round
        VILLAGE; a Name tag stands at each place the mission names."""
        fobs = [it for it in op.ITEMS if it.addon == "Spawn" and it.unit == forces.FOB_UNIT]
        self.assertEqual([(it.ranking, px(it)) for it in fobs],
                         [("Camp_0", ts_map.POINTS[r.spawn]) for r in forces.ROWS if r.group == "fob"])
        ring = item(op.VILLAGE_RING)
        self.assertEqual(px(ring), ts_map.POINTS["VILLAGE"])
        self.assertAlmostEqual(ring.radius_gru * GRU_WORLD / TWIN_CITIES.world_per_px, op.VILLAGE_RING_PX)
        for name, point in op.TAGS.items():
            self.assertEqual((item(name).addon, px(item(name))), ("Name", ts_map.POINTS[point]))
        self.assertLessEqual({"GUN_SPAWN", "ASSEMBLY", "BOX_W", "BOX_C", "VILLAGE"}, set(op.TAGS.values()))
        self.assertEqual({op.BOX_TAGS[k]: op.TAGS[op.BOX_TAGS[k]] for k in op.BOX_TAGS},
                         {"TS_BoxW": "BOX_W", "TS_BoxC": "BOX_C"})

    def test_the_ring_counts_the_village_only(self):
        """The circle stays inside the village's command zone from north to south and reaches neither fire box nor
        the centre lane's turn."""
        zone = item(op.VILLAGE_ZONE)
        ys = [TWIN_CITIES.world_to_px(p)[1] for p in zone.polygon]
        vx, vy = ts_map.POINTS["VILLAGE"]
        self.assertTrue(min(ys) <= vy - op.VILLAGE_RING_PX and vy + op.VILLAGE_RING_PX <= max(ys))
        for place in ("BOX_W", "BOX_C", "TURN_C"):
            self.assertGreater(math.dist(ts_map.POINTS[place], (vx, vy)), op.VILLAGE_RING_PX)


class Ranges(unittest.TestCase):
    """Design 3's bands: the 2S7M fires at 7,000-35,000 GRU, the BM-27 at 10,000-35,000. From GUN_SPAWN every target
    of each battery lies inside its band, with 500 GRU to spare for a battery laid out around the point (the
    fire-range gate checks the built files)."""

    MARGIN = 500.0

    def check_band(self, battery: str, low: float, targets: tuple[str, ...]):
        for target in targets:
            d = gru(ts_map.POINTS["GUN_SPAWN"], ts_map.POINTS[target])
            with self.subTest(battery=battery, target=target):
                self.assertTrue(low + self.MARGIN <= d <= 35000 - self.MARGIN, d)

    def test_heavy_guns_reach_the_village_the_boxes_and_assembly(self):
        self.check_band(op.HEAVY, 7000.0, ("VILLAGE", "BOX_W", "BOX_C", "ASSEMBLY"))

    def test_rockets_reach_the_boxes(self):
        self.check_band(op.ROCKETS, 10000.0, ("BOX_W", "BOX_C"))

    def test_in_the_allied_camp_in_the_corner(self):
        """The batteries are the player's ally's (SovietAlly), so the player's units never engage them, created in the
        cut's north-west corner, outside the Soviet box (the gate checks the alliance on the built script)."""
        self.assertEqual(op.GUN_CAMP, "SovietAlly")
        x, y = ts_map.POINTS["GUN_SPAWN"]
        cx0, cy0, _, _ = ts_map.CUT_PX
        sx0, _, _, _ = ts_map.SOV_DZ
        self.assertTrue(cx0 <= x < sx0 and cy0 <= y, (x, y))


class Camera(unittest.TestCase):
    """The opening camera [[start-camera-before-loading-done]]: TS_Open, three keys flown in OPENING_S, then TS_Start,
    its last key; and the strike's shot, TS_Strike."""

    def test_the_move_comes_down_and_turns_south(self):
        """Each key 40 degrees down, from 720,000 to 400,000 above the ground, never below stock's lowest start camera;
        the eyes over the map north of the cut, moving west and south, the heading turning to due south; 6 to 10 s."""
        keys = ts_map.CAMERA.path_keys()
        self.assertEqual(len(keys), 3)
        heights = [eye[2] - TWIN_CITIES.ground_z for eye, _ in keys]
        self.assertEqual([round(h) for h in heights], [720000, 540000, 400000])
        self.assertGreaterEqual(min(heights), START_CAMERA_MIN_HEIGHT)
        eyes = [TWIN_CITIES.world_to_px(eye[:2]) for eye, _ in keys]
        for (ex, ey), (eye, d) in zip(eyes, keys):
            self.assertAlmostEqual(math.degrees(math.asin(-d[2])), 40.0)
            self.assertTrue(0 <= ex <= 768 and 0 <= ey < ts_map.CUT_PX[1])
        self.assertEqual([round(c, 1) for e in eyes for c in e], [179.7, 13.5, 129.6, 39.2, 105.0, 58.8])
        self.assertTrue(eyes[0][0] > eyes[1][0] > eyes[2][0] and eyes[0][1] < eyes[1][1] < eyes[2][1])
        headings = [math.degrees(math.atan2(d[1], d[0])) for _, d in keys]
        self.assertTrue(headings[0] > headings[1] > headings[2] == 90.0)
        self.assertTrue(6.0 <= ts_map.OPENING_S <= 10.0)

    def test_the_last_view_has_the_soviet_box_near_and_the_village_beyond(self):
        """The last view centres on (105, 245) px: inside the cut, between the village and the Soviet box's middle on
        x, south of the box and north of the village; the eye stands north of the box, so the box is in the view."""
        last = ts_map.OPENING_KEYS[-1]
        cx, cy = TWIN_CITIES.world_to_px(view_centre(ts_map.CAMERA.path_keys()[-1], TWIN_CITIES.ground_z))
        self.assertAlmostEqual(cx, 105.0)
        self.assertAlmostEqual(cy, 245.0)
        self.assertEqual((last.at_px, last.facing), ((105.0, 245.0), (0.0, 1.0)))
        bx0, by0, bx1, by1 = ts_map.SOV_DZ
        vx, vy = ts_map.POINTS["VILLAGE"]
        self.assertTrue(vx < cx < (bx0 + bx1) / 2 and by1 < cy < vy)
        _, eye_y = TWIN_CITIES.world_to_px(ts_map.CAMERA.path_keys()[-1][0][:2])
        self.assertLess(eye_y, by0)

    def test_the_file_holds_the_move_its_end_and_the_strike_shot(self):
        """TS_Open (three keys) then TS_Start, one key, the move's last, then the strike's shot TS_Strike, one key; the
        camera gate passes it."""
        (it,) = ts_map.CAMERA.items()
        self.assertEqual((it.pack, it.path, it.action, it.fixture),
                         ("Details", CAMPATHS_FILE, "generate", "CamPaths_LevelDesign.txt"))
        nb, _, _ = decode(b"".join(it.chunks()))
        self.assertEqual([nb.cname(ob.cls) for ob in nb.objects],
                         ["TCameraPath", *["TCameraPathKey"] * 6, *(["TCameraPath", "TCameraPathKey", "TCameraPathKey"]
                                                                    * 2)])
        self.assertEqual(nb.strings, [b"TS_Open", b"TS_Start", b"TS_Strike"])
        self.assertEqual(ts_map.CAMERA.check(b"".join(it.chunks())),
                         "TS_Open (3 keys) then TS_Start, its last key: every eye over the map, at least 390,000 above "
                         "the ground (stock's lowest start camera 376,057), the last view centred on (105.0, 245.0) "
                         "px, inside the cut; one-key shot TS_Strike on (156.0, 500.0) px, inside the cut")

    def test_the_strike_shot_frames_the_zone(self):
        """TS_Strike [[camera-shot-from-current-position]]: one key looking at ASSEMBLY, the strike zone's centre,
        facing south, 40 degrees down from 390,000 above the ground (BlackHorsesLastStand's cam_02 stands 390,270 up
        at 40 degrees; the camera gate's floor is 376,057); its eye over the cut, north of the zone, so the whole zone
        (R round ASSEMBLY) lies ahead of it; flown in 4 s (stock's mid-battle shots: 3 to 10 s), then held 11 s."""
        shot = ts_map.STRIKE_SHOT
        self.assertEqual((shot.name, shot.key.at_px, shot.key.facing), ("TS_Strike", ts_map.POINTS["ASSEMBLY"],
                                                                         (0.0, 1.0)))
        (eye, d) = shot.key.key(TWIN_CITIES)
        self.assertEqual(round(eye[2] - TWIN_CITIES.ground_z), 390000)
        self.assertGreaterEqual(eye[2] - TWIN_CITIES.ground_z, START_CAMERA_MIN_HEIGHT)
        self.assertAlmostEqual(math.degrees(math.asin(-d[2])), 40.0)
        ex, ey = TWIN_CITIES.world_to_px(eye[:2])
        self.assertEqual((round(ex, 1), round(ey, 1)), (156.0, 318.4))
        x0, y0, x1, y1 = ts_map.CUT_PX
        self.assertTrue(x0 <= ex <= x1 and y0 <= ey <= y1)
        ax, ay = ts_map.POINTS["ASSEMBLY"]
        self.assertLess(ey, ay - op.STRIKE_R_PX)                         # the zone's north edge lies ahead of the eye
        self.assertTrue(3.0 <= shot.seconds <= 5.0)
        self.assertEqual((shot.seconds, shot.hold), (4.0, 11.0))

    @LAYOUT_DATA
    def test_the_last_view_centres_where_camp0_does(self):
        """The layout's own camp0 camera, the deployment view of the stock zone the Soviet box is cut from, centres its
        view 244.8 px down the map; the last view centres there too, to within half a pixel."""
        nb, _, _ = decode(read_file(extracted(f"{TWIN_CITIES.details}/{CAMPATHS_FILE}")))
        props = [{nb.pname(pi): v for pi, v in ob.props} for ob in nb.objects]
        (camp0,) = [p for ob, p in zip(nb.objects, props)
                    if nb.cname(ob.cls) == "TCameraPath" and nb.strings[p["Name"].v] == b"camp0"]
        (eye,) = [props[k.v.index]["Coord"].v for k in camp0["PositionKeyVector"].v]
        (d,) = [props[k.v.index]["Coord"].v for k in camp0["DirectionKeyVector"].v]
        _, cy = TWIN_CITIES.world_to_px(view_centre((eye, d), TWIN_CITIES.ground_z))
        self.assertAlmostEqual(cy, ts_map.OPENING_KEYS[-1].at_px[1], delta=0.5)


class Strings(unittest.TestCase):
    def test_english_only_in_both_columns(self):
        """The SC column is the English text until the Chinese build: plain ASCII (the glyph gate's printable set)."""
        for dic, tokens in strings.STRINGS.items():
            for tok, (en, zh) in tokens.items():
                with self.subTest(token=tok):
                    self.assertEqual(en, zh)
                    self.assertTrue(all(" " <= ch <= "~" or ch == "\n" for ch in en), en)
                    trad.token_key(tok)
        self.assertEqual(set(strings.STRINGS), set(profile.DICTIONARIES))

    def test_every_token_is_ts_and_unique(self):
        toks = [t for tokens in strings.ENGLISH.values() for t in tokens]
        self.assertEqual(len(toks), len(set(toks)))
        self.assertTrue(all(t.startswith("ts_") for t in toks))

    def test_what_the_whole_op_needs(self):
        """The camp names, the start hint, every phase's hint, the objectives P1, P2, P3 (each road's), B1 and B2 with
        their labels, the five choice dialogs and every ending (design 4.2, 5.8)."""
        loc, dialog = strings.ENGLISH["Scripting/Localization"], strings.ENGLISH["Scripting/Dialog"]
        self.assertLessEqual(set(profile.CAMP_TOKENS.values()), set(loc))
        self.assertLessEqual({"ts_hdep", "ts_hph1", "ts_hprep", "ts_hfall", "ts_hph3", "ts_hbn2", "ts_hrel",
                              "ts_hph5"}, set(loc))
        for obj in ("ts_p1", "ts_p2", "ts_p3r", "ts_p3w", "ts_b1", "ts_b2", "ts_b2n"):
            self.assertLessEqual({obj, f"{obj}l"}, set(loc))
        self.assertEqual(set(strings.BUTTONS), {"ts_dprep", "ts_dfire1", "ts_dfire2", "ts_dplan", "ts_drel"})
        self.assertLessEqual(set(strings.BUTTONS), set(dialog))
        self.assertLessEqual({f"ts_d{g}{s}" for g in ("tot", "maj", "min") for s in "rw"}, set(dialog))
        self.assertLessEqual({"ts_dfail", "ts_dlost", "ts_dempty"}, set(dialog))
        self.assertIn("VILLAGE", loc["ts_hdep"])

    def test_dialogs_take_no_variables(self):
        for tok, text in strings.ENGLISH["Scripting/Dialog"].items():
            self.assertNotRegex(text, r"%\d", tok)

    def test_menu_texts_in_stocks_form(self):
        """The menu's five texts that are not titles each run inside stock's English range for their element
        (test_gates_stock.MENU_SPANS), without markup or placeholders. The briefing opens with its date and time, its
        order number and a blank line, and holds stock's four numbered points; the forces line is two lines; the text
        under the title is three paragraphs."""
        menu = strings.ENGLISH["SCENARIO_DEFINITION"]
        self.assertEqual(set(menu), set(MENU_ELEMENTS))
        for tok in sorted(set(menu) - set(profile.TITLE_TOKENS)):
            (lo, hi), _ = MENU_SPANS[MENU_ELEMENTS[tok]]
            with self.subTest(token=tok):
                self.assertTrue(lo <= units(menu[tok]) <= hi, f"{tok}: {units(menu[tok])} units, stock {lo}-{hi}")
                self.assertNotRegex(menu[tok], r"#\w+\{|%\d")
        for tok in profile.TITLE_TOKENS:
            self.assertLessEqual(units(menu[tok]), 30)
        lines = menu["ts_order"].split("\n")
        self.assertRegex(lines[0], r"^July [0-9]{1,2}, 1989, [0-9]{2}:[0-9]{2} UTC$")   # design 1: early July 1989
        self.assertRegex(lines[1], r"^Combat Order No\. \S+$")
        self.assertEqual(lines[2], "")
        self.assertEqual([line[:3] for line in lines if re.match(r"\d\. ", line)], ["1. ", "2. ", "3. ", "4. "])
        self.assertEqual(menu["ts_headr"].count("\n"), 1)
        self.assertEqual(menu["ts_recap"].count("\n\n"), 2)

    @paths.skip_unless_extracted("glad_201602", "Localisation", "Core")
    def test_buttons_are_ingame_tokens_in_every_language(self):
        """Every dialog button is a token of the game's INTERFACE_INGAME dictionary in all 8 languages
        [[dialog-button-ingame-dictionary]]."""
        for lang in LANGS:
            keys = gates.ingame_keys(os.path.join(str(paths.extracted_root()), INGAME_DIC.format(lang=lang)))
            for dialog, pair in strings.BUTTONS.items():
                for button in pair:
                    with self.subTest(lang=lang, button=button):
                        self.assertIn(trad.token_key(button), keys)


@SCRIPT_DATA
class Script(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        cls.roots, cls.exports = op.content().script(tpl)
        cls.nodes = list(walk(cls.roots))
        (cls.main,) = [nd for nd in cls.nodes if nd.export == f"{GD}/TS/Main"]

    def test_camps(self):
        """The RootDescriptor's CampList: Survivors' four camps with the Soviet-player scalars, each named by its token;
        Main's SetDecks give each its deck."""
        (root,) = [nd for nd in self.nodes if nd.export == f"{GD}/RootDescriptor"]
        camps = prop(root, "CampList")
        self.assertEqual([last(c) for c in camps], [name for name, _, _ in SOVIET_PLAYER_CAMP_ROWS])
        for camp, (name, scalars, _) in zip(camps, SOVIET_PLAYER_CAMP_ROWS):
            self.assertEqual([(p, v.v) for p, v in camp.props[:-1]], [(p, v) for p, _, v in scalars])
            self.assertEqual(token(prop(camp, "PlayerName")), profile.CAMP_TOKENS[name])
        decks = [(last(prop(n, "Camp")), prop(n, "DeckIdentifier").text) for n in subs(self.main)[:4]]
        self.assertEqual(decks, [(name, deck) for name, _, deck in SOVIET_PLAYER_CAMP_ROWS])
        self.assertEqual(decks[0], ("joueur", "OP_BASE_RJ_Player"))

    def test_setup_ends_with_the_village_owner_and_the_camera_opens_after_loading_done(self):
        """Before LoadingDone: the deployment's setup, then NATO owns the village's zone (RedJuggernaut #73's place).
        After it, before the HUD returns, the opening camera, where DelayedRetribution opens (#64, #65 before #67):
        the camera flies TS_Open in OPENING_S, then snaps to TS_Start [[start-camera-before-loading-done]]. Nothing
        before LoadingDone moves the camera: the deployment phase, which starts there, loses it."""
        kids = subs(self.main)
        names = [k.cls.removeprefix("TGDDescriptor") for k in kids]
        self.assertEqual(names, ["SetDeck"] * 4 + ["ForceDisplayUIElement", "ChangeProductionType",
                                                   "SetRessourceForTeam", "SetIncomeToTeam",
                                                   "SetCommandZoneOwnerAndForceConvergence", "LoadingDone",
                                                   "EncapsuleCutscene", "EncapsuleCutscene", "ForceDisplayUIElement",
                                                   "Simultaneous"])
        owner, move, end = kids[8], kids[10], kids[11]
        self.assertEqual(last(prop(owner, "Camp")), "ordinateur_SOV")
        self.assertEqual([last(t) for t in prop(owner, "Positions")], [op.VILLAGE_ZONE])
        (fly,), (snap,) = subs(move), subs(end)
        self.assertEqual([(n.cls, prop(n, "CameraPathName").text) for n in (fly, snap)],
                         [("TGDDescriptorCutsceneStartCameraPath", "TS_Open"),
                          ("TGDDescriptorCutsceneStartCameraPath", "TS_Start")])
        self.assertEqual((ts_map.CAMERA.move, ts_map.CAMERA.end), ("TS_Open", "TS_Start"))
        self.assertEqual((prop(fly, "TimeInSecond").v, prop(snap, "TimeInSecond")), (ts_map.OPENING_S, None))
        self.assertEqual([prop(n, "CanBeSkippedWithEscape").v for n in (fly, snap)], [1, 1])
        self.assertEqual(of(list(walk(kids[:9])), "Camera"), [])
        self.assertEqual([k for k, _ in kids[7].props], ["Camp"])        # no income: stock leaves the amount out
        self.assertEqual(prop(kids[6], "Quantite").v, op.DEPLOY_POINTS)
        self.assertEqual(prop(kids[5], "ProductionType").v, PRODUCTION_DECK)   # the buy menu's BATTLEGROUP view

    def test_after_loading_done(self):
        """Main's Simultaneous: the frame's two load beats first (the mission's after them), the refresh loop, then the
        wait for "Launch battle" (the start hint beside it) before the timed beats (test_twin_strike_mission). The HUD
        restore leaves the buy menu's switch at Default."""
        kids = subs(self.main)
        self.assertNotIn(("ShowProdMenuSwitchMenuTypeButtons"), [p for p, _ in kids[-2].props])
        *_, refresh, battle = subs(kids[-1])
        launched = subs(battle)[0]
        self.assertEqual(refresh.export, profile.REFRESH_EXPORT)
        self.assertEqual(launched.cls, "TGDDescriptorCompetition")
        (hint,) = of(list(walk([launched])), "LDHint")
        self.assertEqual(token(prop(hint, "Info")), "ts_hdep")
        self.assertEqual(op.PROD_MENU_SWITCH, BRICK_DEFAULT)

    def test_deck_adds_and_locks(self):
        """AddUnitToDeck for every start card, the motor rifles carried by their BMP-2s, and then for the Soviet
        player's supply; then, last and beside each other, one LockDeckUnit per locked type, each until ts_fallen = 1
        [[add-unit-to-deck]]."""
        deck = subs(subs(self.main)[-1])[0]
        *adds, locks = subs(deck)
        got = [(prop(n, "TypeUnit").path, prop(n, "NbUnitsToAdd").v,
                prop(n, "Transporter").path if prop(n, "Transporter") else None) for n in adds]
        self.assertEqual(got, [(unit_path(u), n, unit_path(t) if t else None)
                               for u, n, t in (*forces.START_ADDS, *forces.SUPPLY)])
        self.assertTrue(all(last(prop(n, "Camp")) == "joueur" for n in adds))
        self.assertEqual(locks.cls, "TGDDescriptorSimultaneous")
        units = []
        for race in subs(locks):
            wait, lock = subs(race)
            self.assertEqual(race.cls, "TGDDescriptorCompetition")
            self.assertEqual(cmp_of(prop(wait, "Condition")), (op.FALLEN, 0, 1))
            (deck_unit,) = prop(lock, "Units")
            units.append(prop(deck_unit, "Unit").path)
        self.assertEqual(units, [unit_path(u) for u in forces.START_LOCKS])
        self.assertIn(TRANSPORTER_SHAPE, op.content().extra_shapes)

    def test_the_garrison_holds_the_village(self):
        """The garrison's group from its 14 Camp_3 spawns, then, as stock gives a garrison in a camp with no AI: HOLD
        POSITION when idle and Aggressive when fired on (Survivors #188/#189's place), and a Hold smart order at the
        village, last (RedJuggernaut #249)."""
        union, idle, shot, hold = subs(subs(subs(self.main)[-1])[1])
        self.assertEqual((last(prop(union, "GroupDestination")), [last(s) for s in prop(union, "ListGroupSource")]),
                         (op.GARRISON, [it.name for it in spawns("garrison")]))
        self.assertEqual((idle.cls, last(prop(idle, "Group")), prop(idle, "IdleBehavior").v),
                         ("TGDDescriptorSetIdleROEBehavior", op.GARRISON, 2))
        self.assertEqual((shot.cls, last(prop(shot, "Group")), prop(shot, "ShotReactionBehavior").v),
                         ("TGDDescriptorSetShotReactionROEBehavior", op.GARRISON, 2))
        self.assertEqual([(k, v.v if hasattr(v, "v") else last(v)) for k, v in hold.props],
                         [("Position", "TS_Village"), ("SmartOrderType", 2), ("UnitGroup", op.GARRISON)])
        self.assertEqual(hold.cls, "TGDDescriptorLaunchSmartOrder")

    def test_exports(self):
        """The names the mission uses are exported: the flag, the groups, the circle and the tags."""
        exported = {nd.export for nd in self.exports}
        for var in (op.FALLEN, op.GROUPE_JOUEUR, op.GARRISON, op.HEAVY, op.ROCKETS, op.GUNS):
            self.assertIn(f"{GD}/TS/Variables/{var}", exported)
        self.assertIn(f"{GD}/GdItems/CircularZones/{op.VILLAGE_RING}", exported)
        for name in op.TAGS:
            self.assertIn(f"{GD}/GdItems/Tags/{name}", exported)


@SCRIPT_DATA
@LAYOUT_DATA
@GAME
class Build(unittest.TestCase):
    """The op built through build.py's front end (every gate, the extra four included) into a temporary folder."""

    @classmethod
    def setUpClass(cls):
        remove_out(OUT)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cls.code = build_main(["--content", "op", "--out", OUT])
        cls.log = out.getvalue()

    @classmethod
    def tearDownClass(cls):
        remove_out(OUT)

    def test_builds(self):
        self.assertEqual(self.code, 0, self.log)
        self.assertTrue(os.path.isfile(os.path.join(OUT, "TwinStrike", "Config.ini")))
        self.assertTrue(os.path.isfile(os.path.join(OUT, profile.OVERLAY)))
        dumps = set(os.listdir(os.path.join(OUT, "dumps")))
        self.assertLessEqual({"GDScript.txt", "LevelDesign.txt", "PlayableZone.txt", "IAStratZone.txt",
                              "IAStrat_PathCache.txt", "CamPaths_LevelDesign.txt"}, dumps)

    def test_the_gates_that_hold_the_frame(self):
        """Every standard gate passes (the end funnel holding all nine endings; the script-effects gate holding the
        strike's look, its nuke through the script's own wrapper; the garrison the one smart-ordered group), and the
        extra gates: the 57 unit
        types the op names (the supply's, the carriers', the ATGM teams', the Kubs' and the fighters' among them), no
        Survivors name, the cut's 40 tiles, the zones and arrivals, and the fire range: GUN_SPAWN's batteries in the
        player's alliance, its 9 battery-target pairs in range; every unit the script creates inside the playable
        zone."""
        for line in ("1 player reinforcement locations and 1 aerial corridors",
                     "12 never-finishing script actions",              # the three locks and the nine endings
                     "1 HUD restores with the buy-menu switch Default",
                     "9 TriggerEndGame, each under $/GDScript/TS/EndFunnel",
                     "19 script effect launches, each a self-contained GameFx effect",   # the flash's 19
                     "1 smart-ordered groups, none ordered again after its smart order",
                     "gate 3 units: 57 unit descriptors exist",
                     "gate 3 no-template-name: 15 re-keyed or generated dumps without Survivors",
                     "gate 3 grid: 40 AI tiles and 1,560 path costs of twincities_op/SM_SU_3x3_TwinCities_03_Details",
                     "gate 3 zone-layout: 3 zones and 2 arrivals laid out by stock's rules",
                     "CreateUnitOnPosition, each inside the shipped playable zone",
                     "gate 3 fire-range: TS_GunSpawn's batteries in Allie, the player's alliance (0), standing inside "
                     "the playable zone; 9 battery-target pairs on 3 targets, each inside its band (closest: "
                     "TS_Village from 2S7M_Malka_SOV, 846 GRU inside)",
                     "gate 5 package: all 43 entries lie under challenge_OperationTwinStrike; no Gameplay file",
                     "CamPaths_LevelDesign 13 objects vs 35 stock files"):   # gate 2: canonical, stock shapes
            self.assertIn(line, self.log)

    def test_the_shipped_camera_passes_the_camera_gate(self):
        """The camera gate on the camera paths file read back from the written Details pack, where the game reads it:
        the move and its end, the strike's shot, every eye over the map and 390,000 or more above the ground, the last
        view and the shot's in the cut."""
        path = os.path.join(OUT, "TwinStrike", "Scenarios", f"{profile.SCENARIO}_Details.dat")
        entries = {e.path: edat.read_entry(path, e) for e in edat.read_index(path)}
        self.assertIn("the last view centred on (105.0, 245.0) px, inside the cut; one-key shot TS_Strike on (156.0, "
                      "500.0) px, inside the cut", ts_map.CAMERA.check(entries[CAMPATHS_FILE]))

    def test_the_fog_lift_builds_when_on(self):
        """STRIKE_FOG_LIFT on (the play sheet's switch): the op still passes every gate, the shape gate admitting the
        fog switch, and its script holds the switch twice, off then on."""
        out = os.path.join(OUT_ROOT, "fog-lift")
        with mock.patch.object(op, "STRIKE_FOG_LIFT", True):
            items = quiet_build(op.content(), out)
        (gd,) = [it for it in items if it.path.endswith(f"GDScript/{profile.SCENARIO}.ndfbin")]
        nb, _, _ = decode(b"".join(gd.chunks()))
        fows = [{nb.pname(pi): v for pi, v in ob.props}["Fow"].v for ob in nb.objects
                if nb.cname(ob.cls) == "TGDDescriptorFow"]
        self.assertEqual(sorted(fows), [0, 1])
        remove_out(out)

    def test_the_camera_gate_fails_the_strike_shot_on_the_ground(self):
        """The camera gate holds the strike's shot too: the same op with TS_Strike brought down to 100,000 above the
        ground (stock's mid-battle shots go as low as 97,021, but the gate keeps every key above its floor) fails the
        build with the gate's line, before anything is written."""
        low = dataclasses.replace(ts_map.STRIKE_SHOT, key=dataclasses.replace(ts_map.STRIKE_KEY, height=100000.0))
        camera = dataclasses.replace(ts_map.CAMERA, shots=(low,))
        bad = dataclasses.replace(build_profile(), extra_items=(ts_map.CUT.items, camera.items))
        out = os.path.join(OUT_ROOT, "bad-strike-camera")
        with self.assertRaisesRegex(CheckError, r"^camera path TS_Strike key 0: its eye stands 100,000 above the "
                                                r"ground, below stock's lowest start camera \(376,057, "
                                                r"BlackHorsesLastStand's camera_start\)$"):
            ops_testing.quiet_build(bad, op.content(), out)
        self.assertFalse(os.path.exists(out))
        remove_out(out)

    def test_the_camera_gate_fails_a_key_at_ground_level(self):
        """The camera gate's proof (it passes this build, above): the same op with the opening move's middle key
        brought down to the ground fails the build with the gate's line, before anything is written."""
        keys = list(ts_map.OPENING_KEYS)
        keys[1] = dataclasses.replace(keys[1], height=0.0)
        ground = dataclasses.replace(ts_map.CAMERA, keys=tuple(keys))
        bad = dataclasses.replace(build_profile(), extra_items=(ts_map.CUT.items, ground.items))
        out = os.path.join(OUT_ROOT, "bad-camera")
        with self.assertRaisesRegex(CheckError, r"^camera path TS_Open key 1: its eye stands 0 above the ground, below "
                                                r"stock's lowest start camera \(376,057, BlackHorsesLastStand's "
                                                r"camera_start\)$"):
            ops_testing.quiet_build(bad, op.content(), out)
        self.assertFalse(os.path.exists(out))
        remove_out(out)

    def test_details_are_all_generated(self):
        """The cut's three files and the opening camera's are generated; nothing of the layout is copied."""
        with open(os.path.join(OUT, "MANIFEST.tsv"), encoding="utf-8") as fh:
            rows = [line.rstrip("\n").split("\t") for line in fh]
        details = {r[1]: r[3] for r in rows[1:] if r[0] == "Details"}
        self.assertEqual(rows[0][:4], ["pack", "inner_path", "bytes", "action"])
        self.assertEqual({k: details[k] for k in (*gates.IA_GRID_FILES, gates.PLAYABLE_FILE, CAMPATHS_FILE)},
                         dict.fromkeys((*gates.IA_GRID_FILES, gates.PLAYABLE_FILE, CAMPATHS_FILE), "generate"))
        self.assertEqual(set(details.values()), {"generate"})

    @staticmethod
    def moved_spawn(x: float, y: float):
        """The op's content with GUN_SPAWN's tag moved to (x, y) px."""
        moved = tuple(dataclasses.replace(it, x=x * TWIN_CITIES.world_per_px, y=y * TWIN_CITIES.world_per_px)
                      if it.name == op.GUN_SPAWN else it for it in op.ITEMS)
        return dataclasses.replace(op.content(), items=moved)

    def test_the_in_zone_gate_fails_the_played_spawn(self):
        """The in-zone gate's proof (it passes this build, above): the same op with GUN_SPAWN back at (140, 14) px,
        4,577 GRU north of the cut, where the play's batteries stood on the cut's edge and the player's Ka-50s killed
        them [[created-units-stand-in-zone]], fails the build with the gate's line."""
        out = os.path.join(OUT_ROOT, "bad-zone")
        with self.assertRaisesRegex(CheckError, r"^9 of \d+ CreateUnitOnPosition create units outside the playable "
                                                r"zone:\n  2S7M_Malka_SOV is created at TS_GunSpawn, 4,577 GRU N of the "
                                                r"playable zone: it stands on the zone's edge"):
            quiet_build(self.moved_spawn(140, 14), out)
        remove_out(out)

    def test_the_fire_range_gate_fails_an_enemy_camp(self):
        """The fire-range gate's proof: the same op with its batteries in the NATO2 camp, as played (Alliance 1, the
        player's enemy), fails the build with the gate's line (the script is generated during the build)."""
        out = os.path.join(OUT_ROOT, "bad-camp")
        with mock.patch.object(op, "GUN_CAMP", "NATO2"), \
                self.assertRaisesRegex(CheckError, r"(?s)fire range:\n  2S7M_Malka_SOV is created at TS_GunSpawn in "
                                                   r"ordinateur_DDR, outside the player's alliance \(0\): the player's "
                                                   r"units engage it"):
            quiet_build(op.content(), out)
        remove_out(out)

    def test_the_fire_range_gate_fails_a_spawn_out_of_range(self):
        """The fire-range gate's proof: the same op with GUN_SPAWN moved to (65, 240) px, inside the cut, where BOX W
        is 8,000 GRU off, inside the BM-27's 10,000 GRU minimum, fails the build with the gate's line."""
        out = os.path.join(OUT_ROOT, "bad-spawn")
        with self.assertRaisesRegex(CheckError, r"(?s)fire range:\n.*TS_BoxW is 8,000 GRU from where BM27_Uragan_SOV "
                                                r"stands at TS_GunSpawn, outside its ShootOnPosition band "
                                                r"\(10,000-35,000 GRU\)"):
            quiet_build(self.moved_spawn(65, 240), out)
        remove_out(out)

    def test_the_menu_deck_is_rjs(self):
        """MapConfiguration's LocalPlayerDeck is OP_BASE_RJ_Player (SOVIET_PLAYER_DECK_SWAP), Survivors' is gone."""
        path = os.path.join(OUT, "TwinStrike", "Scenarios", f"{profile.SCENARIO}_Definition.dat")
        entries = {e.path: edat.read_entry(path, e) for e in edat.read_index(path)}
        nb, _, _ = decode(entries[f"NDF/Scenarios/MapConfiguration/{profile.SCENARIO}.ndfbin"])
        strings_ = [s.decode("latin-1") for s in nb.strings]
        self.assertIn("OP_BASE_RJ_Player", strings_)
        self.assertNotIn("OP_NORTH_SURV_PLAYER", strings_)

    def pack(self, name: str) -> dict[str, bytes]:
        path = os.path.join(OUT, "TwinStrike", "Scenarios", f"{profile.SCENARIO}_{name}.dat")
        return {e.path: edat.read_entry(path, e) for e in edat.read_index(path)}

    def map_configuration(self):
        return decode(self.pack("Definition")[def_path("MapConfiguration", "ndfbin", profile.SCENARIO)])[0]

    def test_menu_texts_land_on_their_elements(self):
        """MapConfiguration's DescriptionTextElements name each ts_* menu token at its element (MENU_ELEMENTS; the
        warning order's name is ts_name too), so the briefing shows as the briefing and the titles as titles."""
        nb = self.map_configuration()
        (info,) = [nd for nd in nodes_of(nb) if nd.cls == "TChallengeMapInfo"]
        got = {nb.strings[key.v].decode(): int.from_bytes(tok.v, "little")
               for key, tok in dict(info.props)["DescriptionTextElements"].v}
        want = {element: trad.token_key(tok) for tok, element in MENU_ELEMENTS.items()}
        want["MissionNameInWarningOrder"] = trad.token_key("ts_name")
        self.assertEqual({element: got.get(element) for element in want}, want)

    def test_menu_art_is_red_juggernauts(self):
        """The menu pictures' FileNames are Survivors' re-keyed, unchanged: ScenariosData:/<scenario>/MapPackAssets/
        Textures/<name>.png. Behind them, the Assets pack's CornerLogo, MissionCountry and EndgameBlazon are
        RedJuggernaut's files byte for byte and MapTexture is the op's own card (test_menu_card); MANIFEST.tsv names
        each one's source and lists Survivors' four as given up."""
        def file_names(nb) -> set[str]:
            return {nb.strings[dict(nd.props)["FileName"].v].decode() for nd in nodes_of(nb)
                    if nd.cls == "TUIAutoRegisteredResourceTexture"}

        stock_mc = def_path("MapConfiguration", "ndfbin", SURVIVORS.source)
        survivors = decode(read_file(os.path.join(SURVIVORS.path("definition"), *stock_mc.split("/"))))[0]
        mine = file_names(self.map_configuration())
        self.assertEqual(mine, {name.replace(SURVIVORS.source, profile.SCENARIO) for name in file_names(survivors)})
        self.assertEqual(mine, {f"ScenariosData:/{profile.SCENARIO}/MapPackAssets/Textures/{name}.png"
                                for name in MENU_PICTURES})
        assets = self.pack("Assets")
        with open(os.path.join(OUT, "MANIFEST.tsv"), encoding="utf-8") as fh:
            rows = {r[1]: r for r in (line.rstrip("\n").split("\t") for line in fh)}
        for name in MENU_PICTURES:
            stock = profile.MENU_ART[name]
            if not isinstance(stock, str):
                continue
            folder = extracted(STOCK_ASSETS.format(stock))
            with self.subTest(picture=name, stock=stock):
                self.assertEqual(assets[MENU_ART.format(profile.SCENARIO, name)],
                                 read_file(os.path.join(folder, *MENU_ART.format(stock, name).split("/"))))
                row = rows[MENU_ART.format(profile.SCENARIO, name)]
                self.assertEqual((row[0], row[3], row[4]),
                                 ("Assets", "copy", f"extracted/scenarios/{stock}/{MENU_ART.format(stock, name)}"))
        given_up = {k: r[3:] for k, r in rows.items() if r[0] == "-" and "MapPackAssets" in k}
        self.assertEqual(given_up, {f"extracted/scenarios/{SURVIVORS.source}/{MENU_ART.format(SURVIVORS.source, n)}":
                                    ["drop", f"menu art: challenge_RedJuggernaut's {n} ships in its place"
                                     if isinstance(stock, str) else f"menu art: a generated {n} ships in its place"]
                                    for n, stock in profile.MENU_ART.items()})

    def test_menu_card(self):
        """The Assets pack's MapTexture is modkit.ops.menuart's card for the op, byte for byte: Survivors' card titled
        TWIN STRIKE over the cut of Twin Cities, with the two sides' ground and stickers. It parses with the TGV reader
        at the stock card's size and format, and MANIFEST.tsv names it generated, from the stock card and the map."""
        inner = MENU_ART.format(profile.SCENARIO, "MapTexture")
        shipped = self.pack("Assets")[inner]
        card = menuart.build_card(profile.CARD_TITLE, menuart.cut_view(ts_map.CUT), profile.CARD_ZONES,
                                  profile.CARD_STICKERS)
        self.assertEqual(shipped, card.tgv)
        hdr, _ = tgv.decode_tgv(shipped)
        self.assertEqual((hdr.width, hdr.height, hdr.fmt, tgv.unwritable(hdr)), (*menuart.SURVIVORS.size,
                                                                                 "A8B8G8R8_LIN", ""))
        with open(os.path.join(OUT, "MANIFEST.tsv"), encoding="utf-8") as fh:
            rows = {r[1]: r for r in (line.rstrip("\n").split("\t") for line in fh)}
        pack, _, _, action, source = rows[inner][:5]
        self.assertEqual((pack, action), ("Assets", "generate"))
        self.assertEqual(source, profile.MENU_ART["MapTexture"](None)[1])
        self.assertIn(f"extracted/{menuart.SURVIVORS_CARD} titled 'TWIN STRIKE'", source)
        self.assertIn(f"extracted/{TWIN_CITIES.picture('Preview')}", source)


if __name__ == "__main__":
    unittest.main()
