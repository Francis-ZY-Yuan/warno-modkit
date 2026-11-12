"""Tests for probe 3 (examples/probes/probes/nuke.py, the `nuke` and `nuke_sov` contents).

`Pure` pins what needs no stock data: the timeline and step order, the effect names, the geometry, the identities, and
`nuke_sov`'s camp scalars and decks against `nuke`'s. `Script` builds each content's script and pins its steps, the
effects, the death causes, the detector's camp filter and the victims. `Effects` holds the effects to the
script-effects gate against the stock GameFx. `Build` runs the probes' build.py front end (every gate) for both
contents and checks the player's deck in the Definition. Classes that read the stock extraction or the game install
skip without them.
"""
from __future__ import annotations

import os
import unittest

from probe_support import OUT_ROOT, probe_main, template_gdscript
from modkit.core import edat, paths
from modkit.ops.files import read_file
from modkit.ops.gates import check_script_effects, effect_violations, gamefx_declarations, gamefx_file
from modkit.ops import profile as ops_profile
from modkit.ops.graph import Imp, Node, build_graph, decode, encode, walk
from modkit.ops.rekey import TXN, def_path
from probes import CONTENTS, nuke, profile
from probes.nuke import NUKE, SOV

SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
GAMEFX = paths.skip_unless_extracted("transactions", "NDF", "GFX", "GameFx.txn")   # gates.gamefx_file()
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
WAIT, SEQ = "TGDDescriptorWaitDuration", "TGDDescriptorSequential"
FX = "TGDDescriptorLaunchFXFireAndForgetOnPosition"
KILL, DETECT = "TGDDescriptorKillAllUnit", "TGDConditionDetectUnitDansDetecteur"
CAMP = "$/GDScript/RootDescriptor/"


def roots(name: str) -> list[Node]:
    tpl, _, _ = decode(read_file(template_gdscript()))
    return CONTENTS[name]().script(tpl)[0]


def props(nd: Node) -> dict:
    return dict(nd.props)


def steps(name: str) -> dict[str, Node]:
    """Each step's Sequential[WaitDuration t, action], keyed by step name: the unexported Sequentials of Main's last
    Simultaneous that open with a WaitDuration, in order."""
    main = next(nd for nd in walk(roots(name)) if nd.export == f"{profile.FOLDER}/Main")
    simul = props(main)["SubActions"][-1]
    found = [k for k in props(simul)["SubActions"]
             if k.cls == SEQ and k.export is None and props(k)["SubActions"][0].cls == WAIT]
    return dict(zip((s.name for s in nuke.VARIANTS[name].timeline if s.t > 0), found, strict=True))


def of_class(nd: Node, cls: str) -> list[Node]:
    return [n for n in walk([nd]) if n.cls == cls]


class Pure(unittest.TestCase):
    def test_timeline_and_order(self):
        self.assertEqual([(s.name, s.t) for s in nuke.TIMELINE],
                         [("N1", 20.0), ("N2", 40.0), ("N3", 70.0), ("N4", 100.0)])
        self.assertEqual([b.check for b in nuke.BEATS], ["N1", "N2", "N3", "N4"])
        self.assertTrue(all(b.t is None for b in nuke.BEATS))   # from LoadingDone, not from "Launch battle"

    def test_effect_names_and_death_causes(self):
        """N2 is the script-only mega bomb; N3 the design's fallback stack, the 203 mm barrage and black smoke (N1b's
        203 mm is the same effect alone). The first play's nuke names are kept only as what the gate refuses."""
        self.assertEqual(nuke.FX_MEGA, "$/GFX/GameFx/fx_HE_Mega_Bomb_ForScript")
        self.assertEqual(nuke.FX_STACK, ("$/GFX/GameFx/fx_HE_Artillery_203mm_ForScript_RandomPosition",
                                         "$/GFX/GameFx/fx_FumeeNoire_ForScript_RandomPosition"))
        self.assertEqual(nuke.FX_HE, nuke.FX_STACK[0])
        self.assertEqual(nuke.FX_CRASHED, ("$/GFX/GameFx/fx_impact_sol_Tactical_Nuke",
                                           "$/GFX/GameFx/fx_impact_Tactical_Nuke"))
        self.assertEqual(nuke.PENETRATION, 2)

    def test_geometry(self):
        ax, ay = nuke.POINT_A_PX
        bx, by = nuke.POINT_B_PX
        apart_m = ((ax - bx) ** 2 + (ay - by) ** 2) ** 0.5 * 2560 / 215
        self.assertTrue(550 < apart_m < 650, apart_m)
        radius_m = nuke.DETECTOR_PX * 2560 / 215
        self.assertTrue(280 < radius_m < 320, radius_m)
        self.assertGreater(apart_m, radius_m)   # A's circle does not reach B
        self.assertEqual(nuke.VICTIM_COUNT, 5)

    def test_identities_are_distinct(self):
        for key in ("scenario", "mod_name", "prefix"):
            with self.subTest(key=key):
                self.assertNotEqual(getattr(NUKE, key), getattr(SOV, key))
        self.assertNotIn(NUKE.scenario, (profile.SCENARIO, "challenge_OpenDoorTest"))

    def test_victims(self):
        self.assertEqual((NUKE.victim_unit, NUKE.victim_side), ("T80BV_SOV", "PACT"))
        self.assertEqual((SOV.victim_unit, SOV.victim_side), ("M1A1HA_Abrams_US", "NATO"))

    def test_nuke_keeps_the_probes_camps(self):
        self.assertEqual(NUKE.camp_rows, profile.CAMP_ROWS)
        self.assertIsNone(NUKE.deck_swap)

    def test_sov_camp_scalars_and_decks(self):
        rows = {name: ({p: v for p, _, v in scalars}, deck) for name, scalars, deck in SOV.camp_rows}
        red = {"AllianceStyle": 4, "Nationalite": 1}     # REDFOR, PACT; Alliance 0 is the default
        blue = {"Alliance": 1, "AllianceStyle": 3}       # BLUFOR, NATO (the default); Alliance 1
        self.assertEqual(rows["joueur"], (red, "OP_BASE_RJ_Player"))
        self.assertEqual(rows["Allie"], (red, "OP_NORTH_SURV_SOV"))
        self.assertEqual(rows["ordinateur_DDR"], (blue, "OP_BASE_RJ_IA"))
        self.assertEqual(rows["ordinateur_SOV"], (blue, "OP_NORTH_SURV_BEL"))
        self.assertEqual(SOV.deck_swap, {profile.SURVIVORS_PLAYER_DECK: "OP_BASE_RJ_Player"})
        self.assertEqual(SOV.sides[SOV.player], "joueur")

    def test_sov_takes_the_shared_shape(self):
        """nuke_sov's camp rows, sides and deck swap are modkit.ops.profile's, not a copy (Twin Strike takes them
        too); the Survivors deck it swaps is the one both example profiles name."""
        self.assertIs(SOV.camp_rows, ops_profile.SOVIET_PLAYER_CAMP_ROWS)
        self.assertIs(SOV.sides, ops_profile.SOVIET_PLAYER_SIDES)
        self.assertIs(SOV.deck_swap, ops_profile.SOVIET_PLAYER_DECK_SWAP)
        self.assertIs(profile.SURVIVORS_PLAYER_DECK, ops_profile.SURVIVORS_PLAYER_DECK)
        self.assertEqual([deck for _, _, deck in SOV.camp_rows][0], ops_profile.RJ_PLAYER_DECK)


@SCRIPT_DATA
class Script(unittest.TestCase):
    def test_each_step_runs_at_its_time(self):
        for name in ("nuke", "nuke_sov"):
            with self.subTest(content=name):
                got = steps(name)
                waits = {k: props(props(n)["SubActions"][0])["Duree"].v for k, n in got.items()}
                self.assertEqual(waits, {s.name: s.t for s in nuke.VARIANTS[name].timeline if s.t > 0})

    def test_sov_timeline_and_new_steps(self):
        self.assertEqual([(s.name, s.t) for s in nuke.SOV_TIMELINE],
                         [("N0", 0.0), ("N1", 20.0), ("N1b", 25.0), ("N2", 40.0), ("N3", 70.0), ("N5", 90.0),
                          ("N6", 110.0), ("N4", 130.0)])
        self.assertEqual([b.check for b in nuke.SOV_BEATS], [s.name for s in nuke.SOV_TIMELINE])
        self.assertEqual({s.name for s in nuke.VARIANTS["nuke"].timeline} & {"N0", "N1b", "N5", "N6"}, set())
        for name in ("N5", "N6"):   # no hint panel (15 s) overlaps the next step's
            self.assertGreaterEqual(nuke.SOV_TIMELINE[[s.name for s in nuke.SOV_TIMELINE].index(name) + 1].t
                                    - {s.name: s.t for s in nuke.SOV_TIMELINE}[name], 15.0)

    def test_sov_cards_effect_battery_and_unlock(self):
        r = roots("nuke_sov")
        cards = {props(n)["TypeUnit"].path.rsplit("/", 1)[-1]: n for n in walk(r) if n.cls == "TGDDescriptorAddUnitToDeck"}
        self.assertEqual(sorted(k.split("Descriptor_Unit_")[-1] for k in cards),
                         ["Mi_8TZ_SOV", "MotRifles_SOV", "T80U_SOV", "Ural_4320_SOV"])
        for unit, n, _ in ops_profile.SOVIET_PLAYER_SUPPLY:   # the Soviet player's supply, the shared constant
            supply = next(c for k, c in cards.items() if k.endswith(f"Descriptor_Unit_{unit}"))
            self.assertEqual(props(supply)["NbUnitsToAdd"].v, n)
            self.assertNotIn("Transporter", props(supply))
        rifles = next(n for k, n in cards.items() if "MotRifles_SOV" in k)
        self.assertTrue(props(rifles)["Transporter"].path.endswith("BMP_2_SOV"))
        self.assertEqual(props(rifles)["NbUnitsToAdd"].v, 2)
        self.assertNotIn("Transporter", props(next(n for k, n in cards.items() if "T80U" in k)))
        locks = [n for n in walk(r) if n.cls == "TGDDescriptorLockDeckUnit"]
        self.assertEqual(len(locks), 1)
        self.assertTrue(props(props(locks[0])["Units"][0])["Unit"].path.endswith("T80U_SOV"))
        got = steps("nuke_sov")
        fx = of_class(got["N1b"], FX)
        self.assertEqual([props(n)["DatabaseName"].text for n in fx], [nuke.FX_HE])
        self.assertTrue(nuke.FX_HE.endswith("fx_HE_Artillery_203mm_ForScript_RandomPosition"))
        made = of_class(got["N5"], "TGDDescriptorCreateUnitOnPosition")
        self.assertEqual(len(made), 1)
        self.assertEqual(props(made[0])["Camp"].export, CAMP + SOV.sides["SovietAlly"])
        self.assertEqual(SOV.sides["SovietAlly"], "Allie")
        self.assertEqual(props(made[0])["NbUnit"].v, 2)
        self.assertTrue(props(made[0])["TypeUnit"].path.endswith("2S7M_Malka_SOV"))
        order = of_class(got["N5"], "TGDDescriptorGiveOrderStandard")
        self.assertEqual([props(o)["OrderType"].v for o in order], [31])
        self.assertTrue(props(order[0])["Position"].export.endswith("/NK_Target"))
        sets = of_class(got["N6"], "TGDDescriptorModifieVariableInteger")
        self.assertEqual(len(sets), 1)
        self.assertEqual(of_class(steps("nuke")["N1"], FX), [])
        self.assertEqual([n for n in walk(roots("nuke")) if n.cls in ("TGDDescriptorAddUnitToDeck",
                                                                       "TGDDescriptorLockDeckUnit")], [])

    def test_battery_range_covers_the_target(self):
        gru = 2560.0 / 73.6   # GRU per minimap px
        bx, by = nuke.BATTERY_PX
        tx, ty = nuke.TARGET_PX
        dist = ((bx - tx) ** 2 + (by - ty) ** 2) ** 0.5 * gru
        self.assertTrue(7000 < dist < 35000, dist)

    def test_effects_penetration_and_vanished(self):
        """N2 launches the mega bomb on A; N3 launches its two effects together on B (one Simultaneous holding both
        launches, before the wait and the kill)."""
        for name in ("nuke", "nuke_sov"):
            with self.subTest(content=name):
                got = steps(name)
                self.assertEqual([props(n)["DatabaseName"].text for n in of_class(got["N2"], FX)], [nuke.FX_MEGA])
                self.assertEqual([props(n)["DatabaseName"].text for n in of_class(got["N3"], FX)],
                                 list(nuke.FX_STACK))
                for step, point in (("N2", "NK_PointA"), ("N3", "NK_PointB")):
                    self.assertTrue(all(props(n)["Position"].export.endswith(f"/{point}")
                                        for n in of_class(got[step], FX)))
                together = [n for n in of_class(got["N3"], "TGDDescriptorSimultaneous")
                            if [k.cls for k in props(n)["SubActions"]] == [FX, FX]]
                self.assertEqual(len(together), 1)
                self.assertEqual(of_class(got["N1"], FX), [])
                kill2, kill3 = of_class(got["N2"], KILL), of_class(got["N3"], KILL)
                self.assertEqual([props(n)["DeathCause"].v for n in kill2], [nuke.PENETRATION])
                self.assertEqual(len(kill3), 1)
                self.assertNotIn("DeathCause", props(kill3[0]))   # Vanished is the default, left out

    def test_detector_filters_on_the_victims_camp(self):
        for v in (NUKE, SOV):
            with self.subTest(content=v.name):
                got = steps(v.name)
                for step, ring in (("N2", "NK_RingA"), ("N3", "NK_RingB")):
                    det = of_class(got[step], DETECT)
                    self.assertEqual(len(det), 1)
                    self.assertTrue(props(det[0])["Detecteur"].export.endswith(f"/{ring}"))
                    team = props(det[0])["Contrainte"]
                    self.assertEqual(team.cls, "TGDContrainteOnUnitTeam")
                    self.assertEqual(props(team)["Camp"].export, CAMP + v.sides[v.victim_side])
                    self.assertNotEqual(props(team)["Camp"].export, CAMP + v.sides[v.player])

    def test_victims_created_pinned_and_not_ordered(self):
        for v in (NUKE, SOV):
            with self.subTest(content=v.name):
                n1 = steps(v.name)["N1"]
                made = of_class(n1, "TGDDescriptorCreateUnitOnPosition")
                self.assertEqual(len(made), 2)
                for nd in made:
                    p = props(nd)
                    self.assertEqual(p["NbUnit"].v, 5)
                    self.assertEqual(p["Camp"].export, CAMP + v.sides[v.victim_side])
                    self.assertIsInstance(p["TypeUnit"], Imp)
                    self.assertTrue(p["TypeUnit"].path.endswith(v.victim_unit))
                self.assertEqual(len(of_class(n1, "TGDDescriptorGereObjectif")), 2)
                self.assertEqual(of_class(n1, "TGDDescriptorGiveOrderStandard"), [])

    def test_script_ships_each_contents_decks(self):
        for v in (NUKE, SOV):
            with self.subTest(content=v.name):
                decks = {props(nd)["Camp"].export.rsplit("/", 1)[-1]: props(nd)["DeckIdentifier"].text
                         for nd in walk(roots(v.name)) if nd.cls == "TGDDescriptorSetDeck"}
                self.assertEqual(decks, {name: deck for name, _, deck in v.camp_rows})
        self.assertIsNone(CONTENTS["nuke"]().deck_swap)
        self.assertEqual(CONTENTS["nuke_sov"]().deck_swap, SOV.deck_swap)


@SCRIPT_DATA
@GAMEFX
class Effects(unittest.TestCase):
    """The driver's script-effects gate (modkit.ops.gates.check_script_effects) against the stock GameFx: the three
    effects probe 3 launches now are self-contained, the two the first play crashed on are not."""

    def test_the_three_effects_pass_and_the_nuke_names_fail(self):
        declared = gamefx_declarations(gamefx_file())
        self.assertEqual(effect_violations([nuke.FX_MEGA, *nuke.FX_STACK, nuke.FX_HE], declared), [])
        bad = effect_violations(nuke.FX_CRASHED, declared)
        self.assertEqual(len(bad), 2)
        self.assertTrue(all(" declares " in line for line in bad), bad)

    def test_each_contents_script_passes(self):
        """N2 launches one effect, N3 two; nuke_sov adds N1b's."""
        tpl, _, _ = decode(read_file(template_gdscript()))
        for name, launches in (("nuke", 3), ("nuke_sov", 4)):
            with self.subTest(content=name):
                raw = encode(build_graph(*CONTENTS[name]().script(tpl)), "GDScript")
                self.assertEqual(check_script_effects(raw), launches)


@SCRIPT_DATA
@GAME
class Build(unittest.TestCase):
    def test_both_build_and_the_player_deck_follows(self):
        for name, deck in (("nuke", profile.PLAYER_DECK), ("nuke_sov", "OP_BASE_RJ_Player")):
            with self.subTest(content=name):
                out = os.path.join(OUT_ROOT, f"nuke-{name}")
                self.assertEqual(probe_main(["--content", name, "--out", out]), 0)
                c = CONTENTS[name]()
                path = os.path.join(out, c.mod_name, "Scenarios", f"{c.scenario}_Definition.dat")
                entries = {e.path: edat.read_entry(path, e) for e in edat.read_index(path)}
                nb, _, _ = decode(entries[def_path("MapConfiguration", TXN, c.scenario)])
                strings = [s.decode("latin-1") for s in nb.strings]
                self.assertIn(deck, strings)
                self.assertNotIn(profile.SURVIVORS_PLAYER_DECK, strings)


if __name__ == "__main__":
    unittest.main()
