"""Tests for the opening camera: modkit.ops.maps.CameraKey and OpeningCamera, the camera gate (check_camera_paths and
read_camera_paths), the canonical gate on camera paths files, and the stock facts they rest on (the ops knowledge record
start-camera-before-loading-done).

`Keys`, `Opening`, `Gate` and `Canonical` are synthetic, on Geisa's frame: no stock data. `Stock` reads the 16 stock
challenges of the extraction and skips without it."""
from __future__ import annotations

import dataclasses
import glob
import math
import os
import unittest

from modkit.core import ndfbin, paths
from modkit.core.gates import CheckError
from modkit.ops import gates
from modkit.ops.files import read_file
from modkit.ops.graph import Node, Str, build_graph, decode, encode, nodes_of, walk
from modkit.ops.items import payload
from modkit.ops.maps import (
    CAMERA_SHAPE_SOURCES, CAMPATHS_FILE, GEISA, START_CAMERA_MIN_HEIGHT, CameraKey, CameraShot, Cut, OpeningCamera,
    read_camera_paths, view_centre,
)
from modkit.ops.profile import extracted
from modkit.ops.script import ROOT_CLASS
from modkit.ops.testing import prop, subs
from modkit.ops.zones import camera_paths_graph

CUT = Cut(GEISA, (100.0, 200.0, 600.0, 800.0))
HIGH = CameraKey((350.0, 600.0), (0.0, 1.0), 700000.0, 40.0)    # its eye at y 274 px
LOW = CameraKey((350.0, 500.0), (0.0, 1.0), 400000.0, 40.0)     # its eye at y 314 px, its view on (350, 500)
CAMERA = OpeningCamera(CUT, "Op_Open", "Op_Start", (HIGH, LOW), 8.0)
SHOT = CameraShot("Op_Shot", CameraKey((300.0, 450.0), (0.0, 1.0), 390000.0, 40.0), 4.0, 11.0)   # its eye at y 268 px
WITH_SHOT = dataclasses.replace(CAMERA, shots=(SHOT,))
FLOOR = f"below stock's lowest start camera ({START_CAMERA_MIN_HEIGHT:,.0f}, BlackHorsesLastStand's camera_start)"


def cam_file(*paths_: tuple[str, list, list]) -> bytes:
    """A camera paths file of (name, eyes, directions) paths, as zones.camera_paths_graph writes it."""
    return encode(build_graph(camera_paths_graph(list(paths_)), []), CAMPATHS_FILE)


def key_node(xyz: tuple, tag: int = 0x0B) -> Node:
    return Node("TCameraPathKey", [("Coord", ndfbin.Value(tag, tuple(float(c) for c in xyz)))])


class Keys(unittest.TestCase):
    def test_key(self):
        """The eye stands back from the point along the view, `height` above ground_z; the direction is a unit vector
        `pitch_deg` down, heading along `facing` (normalised), and the view's centre line meets the ground at the
        point."""
        key = CameraKey((100.0, 300.0), (3.0, 4.0), 100000.0, 30.0).key(GEISA)
        eye, d = key
        self.assertAlmostEqual(math.hypot(*d), 1.0)
        self.assertAlmostEqual(d[2], -0.5)
        self.assertAlmostEqual(d[0] / d[1], 0.75)
        self.assertAlmostEqual(eye[2], GEISA.ground_z + 100000.0)
        cx, cy = view_centre(key, GEISA.ground_z)
        self.assertAlmostEqual(cx, 100.0 * GEISA.world_per_px, places=3)
        self.assertAlmostEqual(cy, 300.0 * GEISA.world_per_px, places=3)
        ex, ey = GEISA.world_to_px(eye[:2])
        self.assertLess(ex, 100.0)
        self.assertLess(ey, 300.0)

    def test_bad_facing_or_pitch(self):
        for facing, pitch in (((0.0, 0.0), 30.0), ((0.0, 1.0), 0.0), ((0.0, 1.0), 90.0)):
            with self.subTest(facing=facing, pitch=pitch), self.assertRaises(CheckError):
                CameraKey((1.0, 1.0), facing, 1000.0, pitch).key(GEISA)


class Opening(unittest.TestCase):
    def test_the_file_holds_the_move_then_its_end(self):
        """One generated Details item, CamPaths_LevelDesign.ndfbin, dumped: camera_paths_graph's of the move's keys,
        then the end, the move's last key alone."""
        (it,) = CAMERA.items()
        self.assertEqual((it.pack, it.path, it.action, it.fixture),
                         ("Details", CAMPATHS_FILE, "generate", "CamPaths_LevelDesign.txt"))
        self.assertIn("opening camera Op_Open then Op_Start, ending on x 350, y 500 px", it.source)
        keys = [k.key(GEISA) for k in (HIGH, LOW)]
        _, _, image = decode(payload(it))
        self.assertEqual(image, ndfbin.encode_image(build_graph(camera_paths_graph(CAMERA.paths()), [])))
        got = read_camera_paths(payload(it))
        self.assertEqual(list(got), ["Op_Open", "Op_Start"])
        self.assertEqual(got["Op_Start"], got["Op_Open"][-1:])
        for (eye, d), (e, dd) in zip(got["Op_Open"], keys):
            self.assertEqual((eye, d), (ndfbin.as_f32(*e), ndfbin.as_f32(*dd)))
        self.assertEqual(set(CAMERA_SHAPE_SOURCES), {CAMPATHS_FILE})

    def test_cutscenes(self):
        """The move (8 s, easing in and out, skippable), then the snap to its end (bricks.g_camera)."""
        move, end = CAMERA.cutscenes()
        (m,), (e,) = subs(move), subs(end)
        self.assertEqual((prop(m, "CameraPathName").text, prop(m, "TimeInSecond").v), ("Op_Open", 8.0))
        self.assertEqual((prop(e, "CameraPathName").text, prop(e, "TimeInSecond")), ("Op_Start", None))
        for nd in (move, end):
            self.assertEqual(prop(nd, "BlockPlayerActions").v, 1)
            self.assertEqual(prop(subs(nd)[0], "CanBeSkippedWithEscape").v, 1)

    def test_shots_ship_after_the_end(self):
        """A shot's one key ships after the opening's two paths, in the same file; the item's source names it."""
        (it,) = WITH_SHOT.items()
        self.assertIn("ending on x 350, y 500 px; shot Op_Shot on x 300, y 450 px", it.source)
        got = read_camera_paths(payload(it))
        self.assertEqual(list(got), ["Op_Open", "Op_Start", "Op_Shot"])
        (eye, d), = got["Op_Shot"]
        e, dd = SHOT.key.key(GEISA)
        self.assertEqual((eye, d), (ndfbin.as_f32(*e), ndfbin.as_f32(*dd)))

    def test_shot_cutscene(self):
        """A shot's one node: EncapsuleCutscene(BlockPlayerActions)[CutsceneSequential[the path flown from the current
        camera in `seconds`, easing in and out, skippable, then CutsceneWaitDuree `hold`]]."""
        cut = SHOT.cutscene()
        (seq,) = subs(cut)
        fly, wait = subs(seq)
        self.assertEqual((cut.cls, prop(cut, "BlockPlayerActions").v, seq.cls),
                         ("TGDDescriptorEncapsuleCutscene", 1, "TGDDescriptorCutsceneSequential"))
        self.assertEqual([(k, getattr(v, "text", getattr(v, "v", None))) for k, v in fly.props],
                         [("CameraPathName", "Op_Shot"), ("TimeInSecond", 4.0), ("AccelerationActivated", 1),
                          ("DecelerationActivated", 1), ("StartFromCurrentCameraPosition", 1),
                          ("CanBeSkippedWithEscape", 1), ("VisibleByAlliedOfSpecifiedCamp", 1)])
        self.assertEqual((wait.cls, wait.props), ("TGDDescriptorCutsceneWaitDuree",
                                                  [("WaitDuration", ndfbin.Value(0x05, 11.0))]))


class Gate(unittest.TestCase):
    """check_camera_paths: it passes the camera, and fails each rule it holds with one line."""

    def assertFails(self, raw: bytes, message: str):
        with self.assertRaises(CheckError) as cm:
            CAMERA.check(raw)
        self.assertIn(message, str(cm.exception))

    def test_passes(self):
        self.assertEqual(CAMERA.check(CAMERA.details()),
                         "Op_Open (2 keys) then Op_Start, its last key: every eye over the map, at least 400,000 above "
                         "the ground (stock's lowest start camera 376,057), the last view centred on (350.0, 500.0) "
                         "px, inside the cut")

    def test_fails_a_key_at_ground_level(self):
        """The gate's proof: a move whose first key stands on the ground fails the build when it plans the file."""
        ground = dataclasses.replace(CAMERA, keys=(dataclasses.replace(HIGH, height=0.0), LOW))
        with self.assertRaises(CheckError) as cm:
            ground.items()
        self.assertEqual(str(cm.exception), f"camera path Op_Open key 0: its eye stands 0 above the ground, {FLOOR}")

    def test_fails_a_key_below_the_floor(self):
        low = dataclasses.replace(CAMERA, keys=(HIGH, dataclasses.replace(LOW, height=START_CAMERA_MIN_HEIGHT - 1)))
        self.assertFails(low.details(), f"camera path Op_Open key 1: its eye stands 376,056 above the ground, {FLOOR}")

    def test_fails_an_eye_off_the_map(self):
        off = dataclasses.replace(CAMERA, keys=(CameraKey((350.0, 100.0), (0.0, 1.0), 700000.0, 40.0), LOW))
        self.assertFails(off.details(), "camera path Op_Open key 0: its eye at")
        self.assertFails(off.details(), "px is off the map")

    def test_fails_a_last_view_outside_the_cut(self):
        out = dataclasses.replace(CAMERA, keys=(HIGH, dataclasses.replace(LOW, at_px=(50.0, 500.0))))
        self.assertFails(out.details(), "camera path Op_Open: its last view centres on (50.0, 500.0) px, outside the "
                                        "cut x 100..600, y 200..800 px")

    def test_fails_a_snap_for_a_move(self):
        self.assertFails(dataclasses.replace(CAMERA, keys=(LOW,)).details(),
                         "camera path Op_Open: one key is a snap, not a move")

    def test_fails_an_end_off_the_last_key(self):
        (e0, d0), (e1, d1) = CAMERA.path_keys()
        self.assertFails(cam_file(("Op_Open", [e0, e1], [d0, d1]), ("Op_Start", [e0], [d0])),
                         "camera path Op_Start is not the one key Op_Open ends on")

    def test_fails_other_paths(self):
        raw = cam_file(*CAMERA.paths(), ("Other", [CAMERA.path_keys()[0][0]], [CAMERA.path_keys()[0][1]]))
        self.assertFails(raw, "the camera paths file holds ['Op_Open', 'Op_Start', 'Other'], not the opening's "
                              "Op_Open and Op_Start")

    def test_fails_a_direction_not_looking_down(self):
        (e0, _), (e1, d1) = CAMERA.path_keys()
        for bad in ((0.0, 0.766, 0.643), (0.0, 2.0, -1.0)):
            with self.subTest(direction=bad):
                self.assertFails(cam_file(("Op_Open", [e0, e1], [bad, d1]), ("Op_Start", [e1], [d1])),
                                 "camera path Op_Open key 0: its direction")

    def test_fails_a_key_shape_stock_lacks(self):
        """A Coord that is no vec3, a TCameraPath with its key lists swapped, or with fewer directions than
        positions: none is stock's shape."""
        (e0, d0), (e1, d1) = CAMERA.path_keys()
        end = Node("TCameraPath", [("PositionKeyVector", [key_node(e1)]), ("DirectionKeyVector", [key_node(d1)]),
                                   ("Name", Str("Op_Start"))])
        cases = {
            "holds one vec3 Coord in stock": [("PositionKeyVector", [key_node(e0[:2], 0x21), key_node(e1)]),
                                               ("DirectionKeyVector", [key_node(d0), key_node(d1)])],
            "a stock TCameraPath holds": [("DirectionKeyVector", [key_node(d0), key_node(d1)]),
                                          ("PositionKeyVector", [key_node(e0), key_node(e1)])],
            "2 position and 1 direction keys": [("PositionKeyVector", [key_node(e0), key_node(e1)]),
                                                ("DirectionKeyVector", [key_node(d1)])],
        }
        for message, props in cases.items():
            with self.subTest(message):
                move = Node("TCameraPath", [*props, ("Name", Str("Op_Open"))])
                self.assertFails(encode(build_graph([move, end], []), CAMPATHS_FILE), message)


class Shots(unittest.TestCase):
    """check_camera_paths with a mid-battle shot: it passes the camera and its shot, and fails each shot rule."""

    def assertFails(self, raw: bytes, message: str, camera: OpeningCamera = WITH_SHOT):
        with self.assertRaises(CheckError) as cm:
            camera.check(raw)
        self.assertIn(message, str(cm.exception))

    def test_passes(self):
        """The line names the shot; with no shot it is the opening's line, unchanged (Gate.test_passes)."""
        self.assertEqual(WITH_SHOT.check(WITH_SHOT.details()),
                         "Op_Open (2 keys) then Op_Start, its last key: every eye over the map, at least 390,000 above "
                         "the ground (stock's lowest start camera 376,057), the last view centred on (350.0, 500.0) "
                         "px, inside the cut; one-key shot Op_Shot on (300.0, 450.0) px, inside the cut")

    def test_fails_a_missing_or_unnamed_shot(self):
        """The file must hold the opening's paths and the shots, nothing else: a shot left out of the file, or a path
        the camera does not name, fails."""
        self.assertFails(CAMERA.details(), "the camera paths file holds ['Op_Open', 'Op_Start'], not the opening's "
                                           "Op_Open and Op_Start and the shots Op_Shot")
        with self.assertRaises(CheckError) as cm:
            CAMERA.check(WITH_SHOT.details())
        self.assertIn("holds ['Op_Open', 'Op_Shot', 'Op_Start'], not the opening's Op_Open and Op_Start",
                      str(cm.exception))

    def test_fails_a_shot_of_two_keys(self):
        (e, d) = SHOT.key.key(GEISA)
        self.assertFails(cam_file(*CAMERA.paths(), ("Op_Shot", [e, e], [d, d])),
                         "camera path Op_Shot: a shot is one key, flown from the current camera position, not 2")

    def test_fails_a_shot_outside_the_cut(self):
        out = dataclasses.replace(WITH_SHOT, shots=(dataclasses.replace(
            SHOT, key=dataclasses.replace(SHOT.key, at_px=(650.0, 450.0))),))
        self.assertFails(out.details(), "camera path Op_Shot: its view centres on (650.0, 450.0) px, outside the cut "
                                        "x 100..600, y 200..800 px", out)

    def test_fails_a_shot_below_the_floor(self):
        """The floor holds a shot too, though stock's mid-battle shots go as low as 97,021: a shot at 100,000 fails
        the build when it plans the file."""
        low = dataclasses.replace(WITH_SHOT, shots=(dataclasses.replace(
            SHOT, key=dataclasses.replace(SHOT.key, height=100000.0)),))
        with self.assertRaises(CheckError) as cm:
            low.items()
        self.assertEqual(str(cm.exception), f"camera path Op_Shot key 0: its eye stands 100,000 above the ground, "
                                            f"{FLOOR}")


class Canonical(unittest.TestCase):
    """gates.check_canonical admits a camera paths file's one root per path (stock's layout), and nothing more."""

    def test_one_root_per_camera_path(self):
        gates.check_canonical(CAMERA.details(), frozenset(), CAMPATHS_FILE, import_rule="trie")

    def test_other_roots_still_fail(self):
        (e0, d0), _ = CAMERA.path_keys()
        path = camera_paths_graph([("Op_Open", [e0], [d0])])[0]
        other = Node("TMapAreaSet", [("Areas", [])])
        twice = [Node("TGDDescriptorLoadingDone"), Node("TGDDescriptorLoadingDone")]
        for roots in ([path, other], [other, path], twice):
            with self.subTest(roots=[r.cls for r in roots]):
                with self.assertRaisesRegex(CheckError, r"unexported roots \[0, \d+\], expected only #0"):
                    gates.check_canonical(encode(build_graph(roots, []), "X"), frozenset(), "X", import_rule="trie")


# --------------------------------------------------------------------------- stock

DEPLOYMENT_PHASE = 1   # GameRules InitialGamePhase of an Operation that opens in the deployment phase
# The camera paths stock starts right before LoadingDone (scenario, the CutsceneStartCameraPath's object number, its
# path): the five start cameras of deployment-phase Operations, and Sledgehammer's ground-level shot behind its video,
# which its intro climbs from (a Command-phase Operation). Build 210942's numbers: each is 201602's + 2, the two objects
# (SplashSoundDescriptor and its TSoundStream) every stock challenge's GDScript gained before them.
PRE_LOADING_DONE = [
    ("challenge_BackhandBlow", 199, "camera_start"),
    ("challenge_BlackHorsesLastStand", 147, "camera_start"),
    ("challenge_Gotterdammerung", 150, "CamStart"),
    ("challenge_RedJuggernaut", 129, "CamStart"),
    ("challenge_Sledgehammer", 306, "camera_01"),
    ("challenge_TheKitzingenRuse", 145, "CamStart"),
]
# The twelve Operations that open in the deployment phase.
DEPLOYMENT_OPS = ["challenge_BackhandBlow", "challenge_BlackHorsesLastStand", "challenge_DelayedRetribution",
                  "challenge_GloryOrAttrition", "challenge_Gotterdammerung", "challenge_HoldUntilRelieved",
                  "challenge_Marauders", "challenge_RedJuggernaut", "challenge_RunningTheGauntlet",
                  "challenge_TheDieburgSalient", "challenge_TheHydra", "challenge_TheKitzingenRuse"]
# Opening moves stock ends with a snap to their last key, before the HUD returns: (scenario, move, end).
MOVE_THEN_END = [("challenge_DelayedRetribution", "camera_intro", "camera_intro_end"),
                 ("challenge_GloryOrAttrition", "camera_intro", "camera_intro_end"),
                 ("challenge_TheHydra", "camera_start", "camera_intro_end")]


def scripts() -> dict[str, tuple[ndfbin.NdfBin, list[Node]]]:
    """Each stock challenge's GDScript (NDF/Scenarios/<scenario>/GDScript.txn), decoded and as Nodes
    (graph.nodes_of), by scenario."""
    out = {}
    for path in sorted(glob.glob(extracted("scenarios/challenge_*/NDF/Scenarios/challenge_*/GDScript.txn"))):
        nb, _, _ = decode(read_file(path))
        out[os.path.basename(os.path.dirname(path))] = nb, nodes_of(nb)
    return out


def same_key(a: tuple, b: tuple) -> bool:
    """Two keys are one to within stock's rounding: eyes 1 world unit apart at most, directions 1e-6."""
    return math.dist(a[0], b[0]) <= 1.0 and math.dist(a[1], b[1]) <= 1e-6


def stock_paths(scenario: str) -> dict:
    return read_camera_paths(read_file(extracted(f"scenarios/{scenario}/{CAMPATHS_FILE}")))


def ground_z(scenario: str) -> float:
    """The scenario's ground: its playable zone's Center z, or, where the playable zone is empty (the whole map), the
    highest Center z of its deployment and command zones (so a key's height there is never overstated)."""
    def centres(inner: str) -> list[float]:
        nb, _, _ = decode(read_file(extracted(f"scenarios/{scenario}/{inner}")))
        return [{nb.pname(pi): v for pi, v in ob.props}["Center"].v[2] for ob in nb.objects
                if nb.cname(ob.cls) == "TMapArea"]
    playable = centres("out/PlayableZone.ndfbin")
    return playable[0] if playable else max(centres("out/DeploymentZone.ndfbin") + centres("out/CommandZone.ndfbin"))


@paths.skip_unless_extracted("scenarios", "challenge_BlackHorsesLastStand", CAMPATHS_FILE)
class Stock(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.scripts = scripts()

    def test_every_stock_camera_paths_file_keeps_the_key_shape_and_is_canonical(self):
        """read_camera_paths (the gate's key shape) and gates.check_canonical pass every stock camera paths file the
        shape gate reads (CAMERA_SHAPE_SOURCES): 36 files, each of two paths or more (201602's 35 and the new
        scenario CampagneStrat_Invasion_of_Cuba's)."""
        files = sorted({p for pat in CAMERA_SHAPE_SOURCES[CAMPATHS_FILE] for p in glob.glob(extracted(pat))})
        self.assertEqual(len(files), 36)
        for path in files:
            with self.subTest(file=path):
                raw = read_file(path)
                self.assertGreaterEqual(len(read_camera_paths(raw)), 2)
                gates.check_canonical(raw, frozenset(), path, import_rule="trie")

    def test_the_camera_paths_started_right_before_loading_done(self):
        """Six stock challenges start a camera path in the EncapsuleCutscene that LoadingDone follows in a Sequential;
        the five Operations that open in the deployment phase start a start camera there, and every key of theirs stands
        START_CAMERA_MIN_HEIGHT or more above the ground: the lowest is BlackHorsesLastStand's camera_start. The sixth,
        Sledgehammer (Command phase), starts at the ground, below its playable zone's Center z."""
        found, heights = [], {}
        for scenario, (nb, nodes) in self.scripts.items():
            index = {id(nd): k for k, nd in enumerate(nodes)}
            for seq in (nd for nd in nodes if nd.cls == "TGDDescriptorSequential"):
                kids = subs(seq) or []
                for before, after in zip(kids, kids[1:]):
                    if before.cls == "TGDDescriptorEncapsuleCutscene" and after.cls == "TGDDescriptorLoadingDone":
                        for cam in (n for n in walk([before]) if n.cls == "TGDDescriptorCutsceneStartCameraPath"):
                            name = nb.strings[prop(cam, "CameraPathName").v].decode("latin-1")
                            found.append((scenario, index[id(cam)], name))
                            ground = ground_z(scenario)
                            heights[scenario] = [eye[2] - ground for eye, _ in stock_paths(scenario)[name]]
        self.assertEqual(sorted(found), PRE_LOADING_DONE)
        rules = {s: self.rules(s) for s, _, _ in found}
        start = {s: h for s, h in heights.items() if rules[s] == DEPLOYMENT_PHASE}
        self.assertEqual(sorted(start), [s for s, _, _ in PRE_LOADING_DONE if s != "challenge_Sledgehammer"])
        self.assertEqual(min(h for hs in start.values() for h in hs), START_CAMERA_MIN_HEIGHT)
        self.assertEqual(min(start["challenge_BlackHorsesLastStand"]), START_CAMERA_MIN_HEIGHT)
        self.assertLess(max(heights["challenge_Sledgehammer"]), 0)

    def test_deployment_phase_operations_set_their_camera_after_loading_done(self):
        """Every Operation that opens in the deployment phase (12 of 16) runs a camera path after its LoadingDone, in
        the order its script runs; DelayedRetribution, GloryOrAttrition and TheHydra end their opening move with a
        snap to its last key (to within their editor's rounding, a fraction of a world unit)."""
        deployment = []
        for scenario, (_, nodes) in self.scripts.items():
            if self.rules(scenario) != DEPLOYMENT_PHASE:
                continue
            deployment.append(scenario)
            (root,) = [nd for nd in nodes if nd.cls == ROOT_CLASS]
            order = [nd.cls for nd in walk([prop(root, "EffetMap")])]
            done = order.index("TGDDescriptorLoadingDone")
            with self.subTest(scenario=scenario):
                self.assertIn("TGDDescriptorCutsceneStartCameraPath", order[done + 1:])
        self.assertEqual(sorted(deployment), DEPLOYMENT_OPS)
        for scenario, move, end in MOVE_THEN_END:
            with self.subTest(scenario=scenario):
                keys = stock_paths(scenario)
                self.assertGreaterEqual(len(keys[move]), 2)
                self.assertEqual(len(keys[end]), 1)
                self.assertTrue(same_key(keys[end][0], keys[move][-1]), (keys[end], keys[move][-1]))

    def test_mid_battle_shots_fly_one_key_from_the_current_camera(self):
        """The shot's stock (camera-shot-from-current-position): 18 CutsceneStartCameraPath nodes in 5 challenges set
        StartFromCurrentCameraPosition, 10 of them in exactly the order bricks.g_camera writes for a shot; 17 fly a
        one-key path (BackhandBlow's camera_intro2, two keys at one eye, aside), in 3 to 37 s; every key stands 97,021
        to 433,526 above its ground, 26.5 to 40 degrees down."""
        written = [k for k, _ in subs(subs(CameraShot("x", HIGH, 4.0, 1.0).cutscene())[0])[0].props]
        nodes_, orders, keys, times, scenarios = 0, 0, [], [], set()
        for scenario, (nb, nodes) in self.scripts.items():
            for cam in (nd for nd in nodes if nd.cls == "TGDDescriptorCutsceneStartCameraPath"
                        and prop(nd, "StartFromCurrentCameraPosition") is not None):
                nodes_ += 1
                scenarios.add(scenario)
                orders += [k for k, _ in cam.props] == written
                times.append(prop(cam, "TimeInSecond").v)
                path = stock_paths(scenario)[nb.strings[prop(cam, "CameraPathName").v].decode("latin-1")]
                keys.append((len(path), [(eye[2] - ground_z(scenario), math.degrees(math.asin(-d[2])))
                                         for eye, d in path]))
        self.assertEqual((nodes_, len(scenarios), orders), (18, 5, 10))
        self.assertEqual(sum(n == 1 for n, _ in keys), 17)
        self.assertEqual((min(times), max(times)), (3.0, 37.0))
        heights = [h for _, ks in keys for h, _ in ks]
        pitches = [p for _, ks in keys for _, p in ks]
        self.assertEqual((round(min(heights)), round(max(heights))), (97021, 433526))
        self.assertEqual((round(min(pitches), 1), round(max(pitches), 1)), (26.5, 40.0))

    def rules(self, scenario: str) -> int:
        (rules,) = [nd for nd in self.scripts[scenario][1] if nd.cls == "TGDSpecificTacticalGameRules"]
        return prop(rules, "InitialGamePhase").v


if __name__ == "__main__":
    unittest.main()
