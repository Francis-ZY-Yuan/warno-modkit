"""Tests for Open Door's script: the frame, the load beats and the phase flags (`Script`); the endings and defeats
(`Endings`); the tier gate on the op in both tier modes (`Tiers`)."""
from __future__ import annotations

import unittest

from modkit.core import ndfbin
from modkit.core.gates import CheckError
from modkit.ops import gates, shapes
from modkit.ops.bricks import g_end_game, g_seq, unit_path
from modkit.ops.files import read_file
from modkit.ops.graph import Node, decode, i32, prop_nodes, walk
from modkit.ops.profile import SURVIVORS, Content
from modkit.ops.testing import (
    cmp_of, end_game, last, objective_named, of, parent_of, prop, sets, subs, token,
)
from open_door_support import (
    JOUEUR, PACT, SCRIPT_DATA, check_end_funnel, check_tiers, details_files, tier_violations,
)
from opendoor import forces, profile
from opendoor import op as mission
from opendoor.map import MAP
from probes import spike2 as probe2   # the objective limits probe 2 found in play

px_of, radius_px, box_px = MAP.px_of, MAP.radius_px, MAP.box_px


@SCRIPT_DATA
class Script(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        cls.roots, cls.exports = mission.script(cls.tpl)
        cls.nodes = list(walk(cls.roots))
        (cls.main,) = [n for n in cls.exports if n.export == "$/GDScript/OD/Main"]
        cls.top = subs(cls.main)[-1]                         # Simultaneous[load beats, refresh, Sequential[...]]

    def var(self, name: str) -> Node:
        (v,) = [n for n in self.exports if n.export == f"{profile.VARIABLES}/{name}"]
        return v

    def test_layout(self):
        """The load beats and the refresh loop run from load beside the launch wait (hint od_hdep); then the timed
        beats: the races, phase 1's five, phase 2's three (from H+0:00, each waits for the release) and phases 3 and
        4's two (from H+0:00, each waits for the spring). The deployment setup, before LoadingDone, gives the player
        6,000 points and forces every tier and anvil command zone to NATO (HoldUntilRelieved #107); every later forcing
        is a hand-over to PACT (phase 1: the towns; phase 2: the necks) but the two seals', each a neck back to NATO
        (phase 3)."""
        self.assertEqual([(b.t, b.check) for b in mission.BEATS],
                         [(None, "deck"), (None, "difficulty"), (None, "funnel"), (None, "p2"), (0.0, "anvil"),
                          (0.0, "rear"), (0.0, "p1"), (0.0, "b1"), (0.0, "pl_blue"), (30.0, "captured"),
                          (60.0, "first_echelon"), (0.0, "main_body"), (0.0, "pl_green"), (0.0, "spring"),
                          (0.0, "phase3"), (0.0, "pocket")])
        deck, diff, funnel, guard, refresh, launch = subs(self.top)
        self.assertEqual(refresh.export, "$/GDScript/OD/JoueurRefresh")
        self.assertEqual(funnel.export, profile.END_FUNNEL)
        self.assertEqual(subs(deck)[0].cls, "TGDDescriptorAddUnitToDeck")
        wait, timed = subs(launch)
        self.assertEqual(token(prop(subs(wait)[0], "Info")), "od_hdep")
        self.assertEqual([prop(subs(s)[0], "Duree").v for s in subs(timed)], [0.0] * 5 + [30.0, 60.0] + [0.0] * 5)
        kids = subs(self.main)
        done = next(k for k, n in enumerate(kids) if n.cls == "TGDDescriptorLoadingDone")
        (owner,) = [n for n in kids[:done] if n.cls == "TGDDescriptorSetCommandZoneOwnerAndForceConvergence"]
        self.assertEqual(prop(owner, "Camp").export, JOUEUR)
        self.assertEqual([last(t) for t in prop(owner, "Positions")], list(mission.OWNED_AT_LOAD))
        (points,) = [n for n in kids[:done] if n.cls == "TGDDescriptorSetRessourceForTeam"]
        self.assertEqual(prop(points, "Quantite").v, mission.DEPLOY_POINTS)
        self.assertEqual(mission.DEPLOY_POINTS, 6000)
        later = [n for n in of(self.nodes, "SetCommandZoneOwner") if n is not owner]
        self.assertEqual(len(later), 7)              # each town's, H+12's and the necks' to PACT; the two seals
        self.assertEqual(sorted((prop(n, "Camp").export, tuple(last(z) for z in prop(n, "Positions"))) for n in later
                                if prop(n, "Camp").export == JOUEUR),
                         [(JOUEUR, ("OD_CZ_NeckMid",)), (JOUEUR, ("OD_CZ_NeckS",))])
        self.assertEqual(len([n for n in later if prop(n, "Camp").export == PACT]), 5)
        self.assertEqual(gates.never_finishing_violations(self.roots)[1], [])

    def test_load_deck(self):
        """Design 6.1's start cards, the rearguard's at Experience 0 with the Rifles in M113A3, then the captured cards
        (SigurdsStrike #1042: Camp, NbUnitsToAdd, TypeUnit), then the A-10A lock until od_sprung = 1, last."""
        (deck,) = [b for b in mission.BEATS if b.check == "deck"]
        seq = deck.build(mission.Ctx())
        cards = subs(seq)[:-1]
        want = [*((u, n, t, 0) for u, n, t in mission.REARGUARD_CARDS),
                *((u, n, None, None)
                  for u, n in (*mission.SUPPORT_CARDS, *mission.FOREST_CARDS, *mission.SOVIET_CARDS))]
        self.assertEqual([(prop(c, "TypeUnit").path, prop(c, "NbUnitsToAdd").v,
                           prop(c, "Transporter").path if prop(c, "Transporter") is not None else None,
                           prop(c, "Experience").v if prop(c, "Experience") is not None else None) for c in cards],
                         [(unit_path(u), n, unit_path(t) if t else None, e) for u, n, t, e in want])
        self.assertEqual([u for u, _, _ in mission.REARGUARD_CARDS],
                         ["M1_Abrams_US", "Rifles_US", "M901_TOW_US", "M113_Dragon_US", "AH1F_Cobra_US"])
        self.assertEqual(mission.SOVIET_CARDS, (("T80U_SOV", 2), ("Ka_50_SOV", 2), ("TOS1_Buratino_SOV", 2)))
        for c in cards[-3:]:
            self.assertEqual([k for k, _ in c.props], ["Camp", "NbUnitsToAdd", "TypeUnit"])
        self.assertTrue(all(prop(c, "Camp").export == JOUEUR for c in cards))
        race = subs(seq)[-1]
        until, lock = subs(race)
        self.assertEqual((race.cls, until.cls, lock.cls), ("TGDDescriptorCompetition", "TGDDescriptorWaitCondition",
                                                           "TGDDescriptorLockDeckUnit"))
        self.assertEqual(cmp_of(prop(until, "Condition")), ("od_sprung", 0, 1))
        (unit,) = prop(lock, "Units")
        self.assertEqual(prop(unit, "Unit").path, unit_path("A10_Thunderbolt_II_ATGM_US"))

    def test_knobs(self):
        """The difficulty knobs, (Easy, Medium, Hard): B1 from design 5.7's shares of the first echelon
        (forces.threshold)."""
        self.assertEqual(mission.KNOBS, {"od_b1_n": (10, 15, 20), "od_smin": (15, 20, 24), "od_b6_s": (90, 120, 150),
                                      "od_surr_pct": (45, 35, 25)})
        self.assertEqual(forces.THRESHOLDS["B1"], (0.28, 0.42, 0.55))

    def run_difficulty(self, level: int | None) -> tuple[dict[str, int], list[tuple[str, bool]]]:
        """A model of the difficulty beat for a battle at `level` (None: no difficulty reaches the script, every
        ConditionOnGameDifficulty false): ({variable: value}, [(hint token, after the launch wait)]). Every write
        must come before any launch wait: the values are final at load. A Sequential runs its children in turn, a
        Simultaneous all of them from its own start, and either is past the launch once a child is."""
        values: dict[str, int] = {}
        hints: list[tuple[str, bool]] = []

        def cond(c: Node) -> bool:
            if c.cls == "TGDConditionOnGameDifficulty":
                d = prop(c, "Difficulty")
                return level is not None and level == (d.v if d is not None else 0)
            name, op, value = cmp_of(c)
            self.assertEqual(op, 0)
            return values.get(name, 0) == value

        def run(n: Node, launched: bool) -> bool:
            if n.cls == "TGDDescriptorSequential":
                for k in subs(n):
                    launched = run(k, launched)
                return launched
            if n.cls == "TGDDescriptorSimultaneous":
                return any([run(k, launched) for k in subs(n)])
            if n.cls == "TGDDescriptorIfThenElse":
                branch = prop(n, "EffetIfTrue") if cond(prop(n, "Condition")) else prop(n, "EffetIfFalse")
                return run(branch, launched) if branch is not None else launched
            if n.cls == "TGDDescriptorModifieVariableInteger":
                self.assertIsNone(prop(n, "ModificationType"))
                self.assertFalse(launched, last(prop(n, "Variable1")))
                values[last(prop(n, "Variable1"))] = prop(n, "Value").v if prop(n, "Value") is not None else 0
            elif n.cls == "TGDDescriptorWaitCondition":
                self.assertEqual(prop(prop(n, "Condition"), "Phase").v, mission.BATTLE_PHASE)
                return True
            elif n.cls == "TGDDescriptorWaitDuration":
                self.assertEqual(prop(n, "Duree").v, mission.DIFF_HINT_T)
            elif n.cls == "TGDDescriptorLDHint":
                hints.append((token(prop(n, "Info")), launched))
            else:
                self.fail(n.cls)
            return launched

        (beat,) = [b for b in mission.BEATS if b.check == "difficulty"]
        run(beat.build(mission.Ctx()), False)
        return values, hints

    def test_difficulty(self):
        """The difficulty: od_diff = 9, the knobs at Medium, then three IfThenElse on ConditionOnGameDifficulty (Easy's
        an empty object: HoldUntilRelieved #199) in one Simultaneous; if od_diff is still 9, Medium. Modelled for each
        case: the values are final at load, and the one hint shows only after the launch wait."""
        (beat,) = [b for b in mission.BEATS if b.check == "difficulty"]
        seq = beat.build(mission.Ctx())
        kids = subs(seq)
        self.assertEqual([k.cls.removeprefix("TGDDescriptor") for k in kids],
                         ["ModifieVariableInteger"] * 5 + ["Simultaneous", "IfThenElse"])
        branches = subs(kids[5])
        self.assertEqual([prop(b, "Condition").props for b in branches],
                         [[], [("Difficulty", i32(1))], [("Difficulty", i32(2))]])
        self.assertTrue(all(prop(b, "EffetIfFalse") is None for b in [*branches, kids[6]]))
        self.assertEqual(cmp_of(prop(kids[6], "Condition")), ("od_diff", 0, 9))
        knobs = list(mission.KNOBS)
        for level, name in ((None, "none"), (mission.EASY, "easy"), (mission.MEDIUM, "medium"), (mission.HARD, "hard")):
            with self.subTest(difficulty=name):
                values, hints = self.run_difficulty(level)
                col = mission.MEDIUM if level is None else level
                self.assertEqual(values, {"od_diff": col, **{k: mission.KNOBS[k][col] for k in knobs}})
                self.assertEqual(hints, [(f"od_hdif{9 if level is None else level}", True)])

    def test_flags_declared(self):
        """Every phase flag is an exported TGDVariableInteger with no initial Value (0). The endings write od_end
        (through set_end), phase 1 od_released (once, in pl_blue), phase 2 od_window (pl_green) and od_sprung (spring),
        once each; phases 3 and 4 the seals (od_sealed_mid and od_sealed_s in P5, od_sealed in the pocket beat), once
        each, and the grade's three set_end."""
        self.assertEqual(mission.FLAGS, ("od_released", "od_window", "od_sprung", "od_sealed_mid", "od_sealed_s",
                                      "od_sealed", "od_end"))
        for name in mission.FLAGS:
            with self.subTest(flag=name):
                v = self.var(name)
                self.assertEqual((v.cls, v.props), ("TGDVariableInteger", []))
                writes = [n for n in of(self.nodes, "ModifieVariableInteger") if prop(n, "Variable1") is v]
                self.assertEqual(len(writes), {"od_end": 8}.get(name, 1))  # od_end: anvil x3, rear exit, P2, grade x3
        for name in ("od_diff", *mission.KNOBS, "Groupe_Joueur"):
            self.var(name)

    def test_no_spike_debug(self):
        """No probe shortcut: no SetEffect (reveal() or another) and no run dialog; the objectives are P2, P1 and B1
        (phase 1), P4 and B6 (phase 2), P5 x2, P6 and the CATCH (phases 3 and 4), each one the player should see; the
        dialogs the funnel's six, P1's failure, Corps's automatic spring, the codeword and the backstop's; the one
        multiple-choice dialog is the spring's."""
        self.assertEqual(of(self.nodes, "SetEffect"), [])
        self.assertEqual(sorted(token(prop(o, "ObjectiveText")) for o in of(self.nodes, "GereObjectif")),
                         ["od_b1", "od_b6", "od_catch", "od_p1", "od_p2", "od_p4", "od_p5m", "od_p5s", "od_p6"])
        (choice,) = of(self.nodes, "EncapsuleCutsceneDialogListWithMultipleChoice")
        (text,) = [n for n in walk([choice]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
        self.assertEqual(token(prop(text, "LocalizedText")), "od_dspring")
        self.assertEqual(len(of(self.nodes, "PlayDialogList")), 10)

    def test_tier_handover(self):
        """tier_handover: SetCommandZoneOwnerAndForceConvergence(side, the zones' tags), then the hint in a
        Simultaneous (probe 2's count-race hand-over); only command zones."""
        ctx = mission.Ctx()
        node = mission.tier_handover(ctx, "PACT", ("OD_CZ_NeckMid", "OD_CZ_NeckS"), "od_hx")
        owner, hint = subs(node)
        self.assertEqual((node.cls, owner.cls, hint.cls), ("TGDDescriptorSequential",
                                                           "TGDDescriptorSetCommandZoneOwnerAndForceConvergence",
                                                           "TGDDescriptorSimultaneous"))
        self.assertEqual((prop(owner, "Camp").export, [last(t) for t in prop(owner, "Positions")]),
                         (PACT, ["OD_CZ_NeckMid", "OD_CZ_NeckS"]))
        (ld,) = subs(hint)
        self.assertEqual((token(prop(ld, "Info")), prop(ld, "Time").v), ("od_hx", mission.HINT_S))
        self.assertEqual(prop(subs(mission.tier_handover(ctx, "NATO", ["OD_CZ_NeckS"], "od_hx"))[0], "Camp").export,
                         JOUEUR)
        with self.assertRaisesRegex(CheckError, "OD_DZ_Anvil is not a command zone"):
            mission.tier_handover(ctx, "PACT", ["OD_DZ_Anvil"], "od_hx")

    def test_deploy_hint_names_the_soviet_cards(self):
        """The deploy hint names the captured Soviet cards by unit and count (SOVIET_CARDS), not by factory
        tab (the buy menu opens in Groups mode), in both languages; the deploy-area sentence stays."""
        hdep = mission.STRINGS["Scripting/Localization"]["od_hdep"]
        en, zh = hdep.US, hdep.SC
        names = {"T80U_SOV": ("T-80U tanks", "辆T-80U坦克"), "Ka_50_SOV": ("Ka-50 helicopters", "架Ka-50直升机"),
                 "TOS1_Buratino_SOV": ("TOS-1 rocket launchers", "辆TOS-1火箭炮")}
        numbers = {2: ("two", "两")}
        self.assertEqual([u for u, _ in mission.SOVIET_CARDS], list(names))
        for unit, n in mission.SOVIET_CARDS:
            with self.subTest(unit=unit):
                self.assertIn(f"{numbers[n][0]} {names[unit][0]}", en)
                self.assertIn(f"{numbers[n][1]}{names[unit][1]}", zh)
        self.assertIn("captured Soviet equipment", en)
        self.assertNotRegex(en.lower(), r"\btabs?\b")
        self.assertNotIn("分类", zh)
        self.assertTrue(en.startswith("DEPLOY (6,000 points): the rearguard in Town NE, Village E and Town SE, a force "
                                      "on SHOULDER, the ANVIL in the west. "))
        self.assertTrue(zh.startswith("部署（6,000点）：后卫部署在Town NE、Village E和Town SE，一支部队守住SHOULDER，"
                                      "ANVIL部队部署在西侧。"))

    def test_tokens_are_in_the_table(self):
        tokens = {token(v) for n in self.nodes for _, v in n.props if isinstance(v, ndfbin.Value) and v.tag == 0x1D}
        table = {t for d in mission.STRINGS.values() for t in d}
        buttons = {"SI_NEXT", mission.BUTTON_NOW, mission.BUTTON_WAIT}   # stock INGAME buttons (gate 3 reads them)
        self.assertEqual(sorted(tokens - table - buttons), [])
        self.assertEqual((mission.BUTTON_NOW, mission.BUTTON_WAIT), ("ORD_AIARA", "ORD_HOLDF"))
        self.assertTrue({"od_hdep", "od_hdif0", "od_hdif1", "od_hdif2", "od_hdif9"} <= tokens)


@SCRIPT_DATA
class Endings(unittest.TestCase):
    """The endings: the end funnel, the defeats (design 4) and P2."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        cls.roots, cls.exports = mission.script(cls.tpl)
        cls.nodes = list(walk(cls.roots))
        (cls.funnel,) = [n for n in cls.exports if n.export == profile.END_FUNNEL]

    def var(self, name: str) -> Node:
        (v,) = [n for n in self.exports if n.export == f"{profile.VARIABLES}/{name}"]
        return v

    def beat(self, check: str, ctx: mission.Ctx | None = None) -> tuple[mission.Ctx, Node]:
        (b,) = [b for b in mission.BEATS if b.check == check]
        ctx = ctx or mission.Ctx()
        return ctx, b.build(ctx)

    def in_zones(self, cond: Node, zones: list[str]) -> tuple[str, int, int]:
        """(camp, operator, value) of a ConditionUnitDansZone over exactly the command zones `zones`, ZoneType 1,
        in an And of its own."""
        if cond.cls == "TGDConditionAnd":
            (cond,) = prop(cond, "SousConditions")
        self.assertEqual(cond.cls, "TGDConditionUnitDansZone")
        self.assertEqual([last(t) for t in prop(cond, "Detecteurs")], zones)
        self.assertEqual(prop(cond, "ZoneType").v, 1)
        op = prop(cond, "ComparaisonNbUnits")
        kind, value = prop(op, "OperatorType"), prop(op, "Value")
        return prop(prop(cond, "Contrainte"), "Camp").export, kind.v if kind else 0, value.v if value else 0

    def ancestors(self, node: Node) -> list[Node]:
        out, stack = [], [node]
        while stack:
            cur = stack.pop()
            ups = [n for n in self.nodes if any(k is cur for _, spec in n.props for k in prop_nodes(spec))]
            out += ups
            stack += ups
        return out

    def test_values(self):
        self.assertEqual((mission.END_TOTAL, mission.END_MAJOR, mission.END_MINOR, mission.END_ANVIL, mission.END_REAR,
                          mission.END_LOST), (1, 2, 3, 4, 5, 6))
        self.assertEqual((mission.REAR_N, mission.ANVIL_PACT_N, mission.ANVIL_HOLD_S), (6, 4, 30.0))

    def test_funnel(self):
        """The funnel: wait for od_end >= 1, then per value its dialog and then its TriggerEndGame: Total (6) on 1,
        Major (5) on 2 and 3, a loss (WinningAlliance 1) on 4 to 6, END_LOST the last else. The dialog comes before the
        TriggerEndGame, which is last in its Sequential. It runs from load beside the battle."""
        wait, pick = subs(self.funnel)
        self.assertEqual(cmp_of(prop(wait, "Condition")), ("od_end", 2, 1))
        want = {1: ("od_dtotal", 6, None), 2: ("od_dmajor", 5, None), 3: ("od_dminor", 5, None),
                4: ("od_danvil", 6, 1), 5: ("od_drear", 6, 1), 6: ("od_dlost", 6, 1)}
        got = {}
        for value in range(1, 7):
            if value < 6:
                self.assertEqual((pick.cls, cmp_of(prop(pick, "Condition"))),
                                 ("TGDDescriptorIfThenElse", ("od_end", 0, value)))
                row, nxt = prop(pick, "EffetIfTrue"), prop(pick, "EffetIfFalse")
            else:
                row, nxt = pick, None
            dialog, ending = subs(row)
            (text,) = [n for n in walk([dialog]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
            self.assertEqual((row.cls, dialog.cls, ending.cls),
                             ("TGDDescriptorSequential", "TGDDescriptorEncapsuleCutscene",
                              "TGDDescriptorTriggerEndGame"))
            got[value] = (token(prop(text, "LocalizedText")), *end_game(ending)[1:])
            pick = nxt
        self.assertEqual(got, want)
        self.assertEqual(len(of(self.nodes, "TriggerEndGame")), 6)
        (beat,) = [b for b in mission.BEATS if b.check == "funnel"]
        self.assertIsNone(beat.t)
        self.assertEqual(check_end_funnel(self.roots), (6, True))
        stray = g_seq([g_end_game(shapes.TOTAL_VICTORY)])  # an ending outside the funnel fails gate 3
        with self.assertRaisesRegex(CheckError, "end funnel"):
            check_end_funnel([*self.roots, stray])

    def test_od_end_only_while_zero(self):
        """Every write to od_end is the only node of an IfThenElse(od_end == 0) branch (shapes.set_end), with the
        values the writers mean: the anvil's three zones, the rear exit and P2; the grade's Total, Major and Minor.
        Every TriggerEndGame is under the funnel."""
        end = self.var("od_end")
        writes = [n for n in of(self.nodes, "ModifieVariableInteger") if prop(n, "Variable1") is end]
        self.assertEqual(sorted(sets([w], end)[0] for w in writes),
                         [mission.END_TOTAL, mission.END_MAJOR, mission.END_MINOR] + [mission.END_ANVIL] * 3
                         + [mission.END_REAR, mission.END_LOST])
        for w in writes:
            latch = parent_of(self.nodes, parent_of(self.nodes, w))
            self.assertEqual(latch.cls, "TGDDescriptorIfThenElse")
            self.assertEqual(cmp_of(prop(latch, "Condition")), ("od_end", 0, 0))
        for n in of(self.nodes, "TriggerEndGame"):
            self.assertTrue(any(a is self.funnel for a in self.ancestors(n)))

    def test_zone_race(self):
        """zone_race: Competition[seconds_while loop (reset on a break), WaitCondition(held >= hold_s)]; a streak
        starts on side >= at_least and other <= 0, and breaks on side < at_least or other >= 1, over the union of the
        zones (ZoneType 1, an And each, an Or of Ands for the break)."""
        ctx = mission.Ctx()
        held = ctx.int_var("od_test_held")
        zones = ["OD_CZ_TownNE", "OD_CZ_VillageE"]
        race = mission.zone_race(ctx, zones, "PACT", "NATO", 3, 20.0, held)
        loop, done = subs(race)
        self.assertEqual((race.cls, done.cls, cmp_of(prop(done, "Condition"))),
                         ("TGDDescriptorCompetition", "TGDDescriptorWaitCondition", ("od_test_held", 2, 20)))
        start, comp, reset = subs(loop)
        self.assertEqual(prop(loop, "NbExecutions").v, shapes.FOREVER)
        self.assertEqual([k for k, _ in reset.props], ["Variable1"])  # a bare Set 0: the streak restarts
        self.assertIs(prop(reset, "Variable1"), held)
        tick, stop = subs(comp)
        self.assertEqual(prop(subs(tick)[0], "Duree").v, shapes.POLL_S)
        self.assertEqual([self.in_zones(c, zones) for c in prop(prop(start, "Condition"), "SousConditions")],
                         [(PACT, 2, 3), (JOUEUR, 3, 0)])
        broken = prop(stop, "Condition")
        self.assertEqual((broken.cls, [(c.cls, self.in_zones(c, zones)) for c in prop(broken, "SousConditions")]),
                         ("TGDConditionOr", [("TGDConditionAnd", (PACT, 3, 2)), ("TGDConditionAnd", (JOUEUR, 2, 1))]))
        flipped = mission.zone_race(ctx, zones, "NATO", "PACT", 1, 5.0, held)
        first = prop(subs(subs(flipped)[0])[0], "Condition")
        self.assertEqual([self.in_zones(c, zones) for c in prop(first, "SousConditions")],
                         [(JOUEUR, 2, 1), (PACT, 3, 0)])

    def test_zone_race_tags_resolve(self):
        """Gate 6: every race's tags are command zones of the shipped Details; a race over a deployment zone's tag
        (ZoneType 1 finds no polygon there) fails the gate."""
        content = mission.content()
        details = details_files(content.items, profile.SCENARIO)
        roots = content.script(self.tpl)[0]
        counts = gates.check_zone_tags(roots, details)
        self.assertGreaterEqual(counts["zone lookups"], 3 + 1)
        ctx = mission.Ctx()
        bad = mission.zone_race(ctx, ["OD_DZ_Anvil"], "PACT", "NATO", 4, 30.0, ctx.int_var("od_bad_held"))
        with self.assertRaises(CheckError):
            gates.check_zone_tags([*roots, bad], details)

    def test_anvil(self):
        """Defeat: one race per anvil command zone, PACT >= 4 and NATO none for 30 s, then set_end(END_ANVIL)."""
        ctx, node = self.beat("anvil")
        self.assertEqual(node.cls, "TGDDescriptorSimultaneous")
        self.assertEqual(len(subs(node)), len(mission.ANVIL_CZ))
        for k, (name, seq) in enumerate(zip(mission.ANVIL_CZ, subs(node))):
            race, latch = subs(seq)
            loop, done = subs(race)
            self.assertEqual(cmp_of(prop(done, "Condition")), (f"od_anv_held_{k}", 2, 30))
            start = prop(subs(loop)[0], "Condition")
            self.assertEqual([self.in_zones(c, [name]) for c in prop(start, "SousConditions")],
                             [(PACT, 2, 4), (JOUEUR, 3, 0)])
            self.assertEqual(sets(list(walk([latch])), ctx.int_var("od_end")), [mission.END_ANVIL])
            self.assertEqual(cmp_of(prop(latch, "Condition")), ("od_end", 0, 0))

    def test_rear_exit(self):
        """Defeat: WaitCondition(>= REAR_N main-body vehicles in OD_RingRear), then set_end(END_REAR). Infantry are
        not counted; the types are the main body's vehicle rows."""
        ctx, seq = self.beat("rear")
        wait, latch = subs(seq)
        cond = prop(wait, "Condition")
        self.assertEqual(cond.cls, "TGDConditionDetectUnitDansDetecteur")
        self.assertEqual(last(prop(cond, "Detecteur")), "OD_RingRear")
        op = prop(cond, "ComparaisonNbUnits")
        self.assertEqual((prop(op, "OperatorType").v, prop(op, "Value").v), (2, mission.REAR_N))
        types = [prop(c, "TypeUnit").path for c in prop(prop(cond, "Contrainte"), "ContrainteList")]
        want = [r.descriptor for r in forces.force_rows("main_body") if r.transport is None]
        self.assertEqual(types, [unit_path(u) for u in dict.fromkeys(want)])
        self.assertNotIn(unit_path("MotRifles_SOV"), types)
        self.assertEqual(sets(list(walk([latch])), ctx.int_var("od_end")), [mission.END_REAR])
        self.assertEqual(mission.item("OD_RingRear").addon, "CircularZone")

    def test_p2(self):
        """P2 is fail-only (no Condition), starts after the battle is launched and Groupe_Joueur >= 1, fails on
        Or[Groupe_Joueur == 0, od_end >= END_ANVIL] and then set_end(END_LOST) (a no-op once od_end is set)."""
        ctx, seq = self.beat("p2")
        phase, guard, obj = subs(seq)
        self.assertEqual((prop(phase, "Condition").cls, prop(prop(phase, "Condition"), "Phase").v),
                         ("TGDConditionPhase", 2))
        self.assertEqual(cmp_of(prop(guard, "Condition")), ("Groupe_Joueur", 2, 1))
        self.assertEqual((obj.cls, prop(obj, "Condition")), ("TGDDescriptorGereObjectif", None))
        fail = prop(obj, "ConditionEchec")
        self.assertEqual(fail.cls, "TGDConditionOr")
        self.assertEqual([cmp_of(c) for c in prop(fail, "SousConditions")],
                         [("Groupe_Joueur", 0, 0), ("od_end", 2, mission.END_ANVIL)])
        self.assertEqual((token(prop(obj, "ObjectiveText")), token(prop(obj, "ObjectiveEtiquetteText")),
                          prop(obj, "ListVariables"), prop(obj, "Position")), ("od_p2", "od_p2l", None, None))
        (latch,) = subs(prop(obj, "ActionsEchec"))
        self.assertEqual(cmp_of(prop(latch, "Condition")), ("od_end", 0, 0))
        self.assertEqual(sets(list(walk([latch])), ctx.int_var("od_end")), [mission.END_LOST])
        self.assertEqual(gates.check_empty_group_guard(self.roots), 1)
        with self.assertRaisesRegex(CheckError, "Groupe_Joueur is empty"):
            gates.check_empty_group_guard([g_seq([obj])])  # the objective without its guard fails the gate
        self.assertEqual(gates.never_finishing_violations(self.roots)[1], [])

    def test_objective_rows(self):
        """At most 10 objectives in a run, at most 2 variables each (probe 2's limits): the nine rows, P1, B1, P2, P4,
        B6, P5 NECK MID, P5 NECK S, P6 and the CATCH, one GereObjectif each (the CATCH is one node for the surrender and
        the backstop)."""
        objs = of(self.nodes, "GereObjectif")
        self.assertLessEqual(len(objs), probe2.OBJECTIVE_ROWS_MAX)
        rows = ("od_p1", "od_b1", "od_p2", "od_p4", "od_b6", "od_p5m", "od_p5s", "od_p6", "od_catch")
        self.assertEqual(sorted(objs, key=id), sorted((objective_named(self.nodes, t) for t in rows), key=id))
        self.assertEqual(len(objs), 9)
        for o in objs:
            self.assertLessEqual(len(prop(o, "ListVariables") or []), probe2.OBJECTIVE_VARIABLES_MAX)

    def test_strings(self):
        """The dialogs (the funnel's six, P1's od_dheld and its "fixed" twin, the spring's two, the codeword and the
        backstop's)
        and P2's texts in both languages, no placeholder in a dialog (a dialog takes no variables)."""
        dialogs = {"od_dtotal", "od_dmajor", "od_dminor", "od_danvil", "od_drear", "od_dlost", "od_dheld",
                   "od_dheld_f", "od_dspring", "od_dauto", "od_dcode", "od_dback"}
        self.assertEqual(mission.STRINGS["Scripting/Dialog"].keys(), dialogs)
        for tok in dialogs:
            texts = mission.STRINGS["Scripting/Dialog"][tok]
            en, zh = texts.US, texts.SC
            self.assertTrue(en and zh)
            self.assertNotRegex(en + zh, r"%\d")
        for tok in ("od_p2", "od_p2l"):
            self.assertTrue(all(mission.STRINGS["Scripting/Localization"][tok].values()))



@SCRIPT_DATA
class Tiers(unittest.TestCase):
    """Gate 3 tiers on the op: "fixed" passes with no tiered entry; "tiered" (the default) names the five, whose
    zones are forced to NATO at load and handed to PACT later (phase 1: the towns; phase 2: the necks), and fails
    tiers.4 for any zone whose hand-over is taken away."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))

    def check(self, mode: str) -> tuple[Content, list[Node], dict[str, bytes]]:
        content = mission.content(mode)
        roots = content.script(self.tpl)[0]
        return content, roots, details_files(content.items, profile.SCENARIO)

    def test_fixed_passes(self):
        content, roots, details = self.check("fixed")
        self.assertEqual(content.tiered_arrivals, ())
        self.assertEqual(check_tiers(content, roots, details), 0)
        self.assertEqual(gates.check_arrivals(content.items, details), (7, 2))

    def test_tiered_op_passes(self):
        """The op as built passes gate 3 tiers in "tiered" mode, its own hand-overs only: the three towns' (pl_blue)
        and the necks' (pl_green), five zones in all; the default content is the tiered one."""
        self.assertEqual(mission.content().tiered_arrivals, tuple(t.name for t in mission.TIERS))
        content, roots, details = self.check("tiered")
        self.assertEqual(content.tiered_arrivals, tuple(t.name for t in mission.TIERS))
        counts, bad = tier_violations(content.tiered_arrivals, roots, details)
        self.assertEqual((counts, bad), ({"tiered": 5, "permanent": 2, "forced to the player at load": 8,
                                          "handed to the enemy": 5}, []))
        self.assertEqual(check_tiers(content, roots, details), 5)
        self.assertEqual(gates.check_arrivals(content.items, details, content.tiered_arrivals), (7, 2))
        with self.assertRaisesRegex(CheckError, "5 player arrivals end in a command zone only"):
            gates.check_arrivals(content.items, details)
        (necks,) = [n for n in walk(roots) if n.cls == gates.ZONE_OWNER
                    and [last(t) for t in prop(n, "Positions")] == list(mission.NECK_CZ)]
        self.assertEqual(prop(necks, "Camp").export, PACT)

    def test_tiered_fails_without_the_necks_hand_over(self):
        """The same op with the necks' hand-over made NATO's fails tiers.4 on the two neck tiers: the
        hand-over is what closes them."""
        content, roots, details = self.check("tiered")
        (necks,) = [n for n in walk(roots) if n.cls == gates.ZONE_OWNER
                    and [last(t) for t in prop(n, "Positions")] == list(mission.NECK_CZ)]
        nato = mission.Ctx().camp("NATO")
        necks.props = [(k, nato if k == "Camp" else v) for k, v in necks.props]
        counts, bad = tier_violations(content.tiered_arrivals, roots, details)
        self.assertEqual(counts["handed to the enemy"], 3)
        self.assertEqual(bad, [f"[tiers.4] {t.name}: its command zone {t.cz} is never handed to ordinateur_SOV (no "
                               f"SetCommandZoneOwnerAndForceConvergence(ordinateur_SOV) holds a tag in it), so the "
                               f"tier never closes" for t in sorted(mission.TIERS) if t.tier == "neck"])



if __name__ == "__main__":
    unittest.main()
