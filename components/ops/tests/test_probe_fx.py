"""Tests for the strike-effects probe (examples/probes/probes/fxprobe.py, the `fxprobe` content).

`Pure` pins what needs no stock data: the timeline (riskiest last, hints apart), the identity, the places, the
wrappers' bindings and the admitted shapes. `Script` builds the script and pins each step's action. `Effects` holds the
launches and the two nuke wrappers to the script-effects gate against the stock GameFx, both ways: the probe passes,
and its wrapper less one binding fails. `Camera` holds the look to Geisa's stock camera paths. `Build` runs the probes'
build.py front end (every gate). Classes that read the stock extraction or the game install skip without them.
"""
from __future__ import annotations

import dataclasses
import os
import unittest

from probe_support import OUT_ROOT, probe_main, template_gdscript
from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.ops.files import read_file
from modkit.ops.gates import check_script_effects, gamefx_file, gamefx_required
from modkit.ops.graph import Node, Str, build_graph, decode, encode, walk
from modkit.ops.maps import CAMPATHS_FILE, GEISA, check_camera_looks, read_camera_paths, view_centre
from modkit.ops.shapes import HINT_S, PENETRATION, STUN
from probes import CONTENTS, fxprobe, nuke, profile

SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
GAMEFX = paths.skip_unless_extracted("glad_201602", "NDF", "GFX", "GameFx.ndfbin")
GEISA_DATA = paths.skip_unless_extracted(GEISA.details, CAMPATHS_FILE)
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
FX = "TGDDescriptorLaunchFXFireAndForgetOnPosition"


def script() -> tuple[list[Node], list[Node]]:
    tpl, _, _ = decode(read_file(template_gdscript()))
    return fxprobe.content().script(tpl)


def raw_script(exports_edit=None) -> bytes:
    roots, exports = script()
    if exports_edit is not None:
        exports = exports_edit(exports)
    return encode(build_graph(roots, exports), "GDScript")


def props(nd: Node) -> dict:
    return dict(nd.props)


class Pure(unittest.TestCase):
    def test_timeline_riskiest_last_and_hints_apart(self):
        names = [s.name for s in fxprobe.TIMELINE]
        self.assertEqual(names, ["F1", "F2", "F3", "F3b", "F4", "F5", "F6", "F7", "F8", "F9", "F10"])
        self.assertEqual(names[-3:-1], ["F8", "F9"])            # the nuke wrappers come last, before the fog's return
        times = [s.t for s in fxprobe.TIMELINE]
        self.assertTrue(all(b - a >= HINT_S for a, b in zip(times, times[1:])), times)   # hints never overlap
        self.assertEqual(fxprobe.TIMELINE[-2].t - fxprobe.TIMELINE[-3].t, 30.0)          # variant 2 30 s after 1
        self.assertEqual([b.t for b in fxprobe.BEATS], [t - fxprobe.LEAD_S for t in times])

    def test_identity_is_its_own(self):
        c = fxprobe.content()
        others = [CONTENTS[n]() for n in ("nuke", "nuke_sov", "spike2")]
        self.assertNotIn(c.scenario, [o.scenario for o in others])
        self.assertNotIn(c.mod_name, [o.mod_name for o in others])
        self.assertEqual(c.deck_swap, nuke.SOV.deck_swap)
        self.assertTrue(all(t.startswith("fx_") for t in c.menu_tokens))

    def test_wrappers_bind_all_four_parameters(self):
        zero, world = fxprobe.wrappers()
        for w, pos in ((zero, (0.0, 0.0, 0.0)), (world, fxprobe.U_WORLD)):
            call = props(w)["Actions"][0]
            bound = dict((k.text, v) for k, v in props(call)["NamedParams"].pairs)
            self.assertEqual(sorted(bound), ["parDirection", "parPosition", "parRadiusPhysical", "parRadiusSuppress"])
            self.assertEqual(props(bound["parPosition"])["Value"].v, pos)
            self.assertEqual(props(call)["Action"].path, fxprobe.FX_NUKE)
        self.assertEqual((zero.export, world.export), (fxprobe.WRAP_ZERO, fxprobe.WRAP_WORLD))


@SCRIPT_DATA
class Script(unittest.TestCase):
    def test_each_step_acts(self):
        roots, exports = script()
        nodes = list(walk(roots))
        launches = [props(n)["DatabaseName"].text for n in nodes if n.cls == FX]
        self.assertEqual(launches.count(fxprobe.FX_MEGA), 10)
        self.assertEqual(launches.count(fxprobe.FX_HE), 5)            # each in a Sequential run 10 times
        self.assertEqual(launches[-2:], [fxprobe.WRAP_ZERO, fxprobe.WRAP_WORLD])
        fow = [props(n)["Fow"].v for n in nodes if n.cls == "TGDDescriptorFow"]
        self.assertEqual(fow, [0, 1])                                 # off at F3, back on at F10
        stress = [(props(n)["DamageType"].v, props(n)["Value"].v) for n in nodes if n.cls == "TGDDescriptorChangeStress"]
        self.assertEqual(stress, [(1, fxprobe.DAMAGE_VALUE), (STUN, fxprobe.STRESS_VALUE)])
        kills = [props(n)["DeathCause"].v for n in nodes if n.cls == "TGDDescriptorKillAllUnit"]
        self.assertEqual(kills, [PENETRATION])
        cams = [props(n) for n in nodes if n.cls == "TGDDescriptorCutsceneStartCameraPath"]
        self.assertEqual([(c["CameraPathName"].text, c["StartFromCurrentCameraPosition"].v) for c in cams],
                         [(fxprobe.CAMERA_PATH, 1)])
        self.assertEqual([e.export for e in exports[-2:]], [fxprobe.WRAP_ZERO, fxprobe.WRAP_WORLD])


@SCRIPT_DATA
@GAMEFX
class Effects(unittest.TestCase):
    def test_the_nuke_declares_four_parameters_with_no_default(self):
        self.assertEqual(sorted(gamefx_required(gamefx_file())[fxprobe.FX_NUKE]),
                         ["parDirection", "parPosition", "parRadiusPhysical", "parRadiusSuppress"])

    def test_the_probe_passes(self):
        self.assertEqual(check_script_effects(raw_script()), 25)

    def test_a_wrapper_missing_a_binding_fails(self):
        def drop(exports):
            out = []
            for e in exports:
                if e.export == fxprobe.WRAP_ZERO:
                    call = props(e)["Actions"][0]
                    pairs = props(call)["NamedParams"]
                    call.props = [("NamedParams", dataclasses.replace(pairs, pairs=pairs.pairs[1:])),
                                  ("Action", props(call)["Action"])]
                out.append(e)
            return out
        with self.assertRaisesRegex(CheckError, r"FxNukeP0: its call to \$/GFX/GameFx/fx_impact_sol_Tactical_Nuke "
                                                r"leaves parPosition unbound \(no default\)"):
            check_script_effects(raw_script(drop))


@GEISA_DATA
@SCRIPT_DATA
class Camera(unittest.TestCase):
    def setUp(self):
        self.cam = (paths.extracted_root() / GEISA.details / CAMPATHS_FILE).read_bytes()

    def test_camp1_looks_at_the_target_area(self):
        key = read_camera_paths(self.cam)[fxprobe.CAMERA_PATH][0]
        cx, cy = GEISA.world_to_px(view_centre(key, GEISA.ground_z))
        self.assertLess(abs(cx - fxprobe.T_PX[0]) + abs(cy - fxprobe.T_PX[1]), 60)
        self.assertEqual(check_camera_looks(raw_script(), self.cam, GEISA), 1)

    def test_a_missing_path_fails(self):
        roots, exports = script()
        cam = next(n for n in walk(roots) if n.cls == "TGDDescriptorCutsceneStartCameraPath")
        cam.props = [(k, Str("Camp9") if k == "CameraPathName" else v) for k, v in cam.props]
        with self.assertRaisesRegex(CheckError, "Camp9"):
            check_camera_looks(encode(build_graph(roots, exports), "GDScript"), self.cam, GEISA)


@SCRIPT_DATA
@GAME
class Build(unittest.TestCase):
    def test_it_builds(self):
        self.assertEqual(probe_main(["--content", "fxprobe", "--out", os.path.join(OUT_ROOT, "fxprobe")]), 0)


if __name__ == "__main__":
    unittest.main()
