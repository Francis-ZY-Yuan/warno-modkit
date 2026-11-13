"""Tests for probe 2 (examples/probes/probes/spike2.py, the `spike2` content).

`Script` builds `spike2.script(tpl)` once and checks each beat's shape and placement in it (the battle Simultaneous
holds one Sequential[WaitDuration t, beat] per timed beat, in BEATS order). `Items` checks the geometry against
Geisa's own layout and Minimap, and the zone lookups the beats make, read from the shipped Details bytes. `Bricks`
checks the mission bricks (modkit.ops.bricks) against their stock shapes. `Build` runs the probes' build.py front end
(every gate) into a temporary folder and removes it afterwards. Classes that read the stock extraction or the
game install skip without them.
"""
from __future__ import annotations

import contextlib
import glob
import io
import math
import os
import re
import unittest

from probe_support import (
    OUT_ROOT, check_end_funnel, details_files, ingame_keys, ld_guid, probe_main, scenario_guid, template_gdscript,
)
from modkit.core import edat, ndfbin, paths, tgv
from modkit.core.gates import CheckError
from modkit.core.models import LANGS
from modkit.ops import bricks, gates, graph, leveldesign, shapes
from modkit.ops.bricks import unit_path
from modkit.ops.files import read_file
from modkit.ops.graph import Node, all_values, decode
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA
from modkit.ops.profile import extracted
from modkit.ops.rekey import TXN, def_path
from modkit.ops.shapes import camp_nodes
from modkit.ops.testing import (  # noqa: F401
    cmp_of, end_game, hints, last, objective_named, of, parent_of, prop, remove_out, set_values, sets, start_s, subs,
    token, within,
)
from modkit.ops.zones import point_in_polygon
from probes import profile, spike, spike2
from probes.geisa import MAP, POINTS

OUT = os.path.join(OUT_ROOT, "spike2")
GD_ITEMS = "$/GDScript/GdItems"
SEQ, SIM, ITE = "TGDDescriptorSequential", "TGDDescriptorSimultaneous", "TGDDescriptorIfThenElse"
COMP, WAIT, UNTIL = "TGDDescriptorCompetition", "TGDDescriptorWaitDuration", "TGDDescriptorWaitCondition"
MODIFY, TEG = "TGDDescriptorModifieVariableInteger", "TGDDescriptorTriggerEndGame"
PACT = f"$/GDScript/RootDescriptor/{profile.CAMPS['PACT']}"
JOUEUR = f"$/GDScript/RootDescriptor/{profile.CAMPS['NATO']}"
FOREVER = spike2.FOREVER
# The zones the PACT spawns, the traffic and the tanks' routes must keep out of: the capture zones (CAP A, CAP B) and
# the count race's (TOWN NE, SHOULDER). The CAP circles are gone (the zones are tested by polygon).
GUARDED_ZONES = ("OD_CZ_CapA", "OD_CZ_CapB", "OD_CZ_TownNE", "OD_CZ_Shoulder")
ROAD_LUMINANCE = 55   # Minimap: road pixels 55-69, built-up 70+; fields and forest below 50 (spike2.TRAFFIC_ROAD_PX)


SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
STOCK_DATA = paths.skip_unless_extracted("scenarios")
GEISA_DATA = paths.skip_unless_extracted(*GEISA.details.split("/"))
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
px_of, radius_px, box_px = MAP.px_of, MAP.radius_px, MAP.box_px


def minimap() -> str:
    """Geisa's Minimap picture (the road pixels the traffic tests read)."""
    return extracted(GEISA.picture("Minimap"))


def to_box(p: tuple[float, float], box: tuple[float, float, float, float]) -> float:
    """Distance in px from point `p` to the rectangle `box` (0 inside)."""
    x0, y0, x1, y1 = box
    return math.hypot(max(x0 - p[0], 0.0, p[0] - x1), max(y0 - p[1], 0.0, p[1] - y1))


def along(a: tuple[float, float], b: tuple[float, float], step: float = 0.5) -> list[tuple[float, float]]:
    """Points every `step` px along the segment a-b, both ends included."""
    n = max(1, math.ceil(math.dist(a, b) / step))
    return [(a[0] + (b[0] - a[0]) * k / n, a[1] + (b[1] - a[1]) * k / n) for k in range(n + 1)]


def clearance(points: list[tuple[float, float]]) -> dict[str, float]:
    """The least distance in px from `points` to each guarded zone's square (0 inside)."""
    return {name: min(to_box(p, box_px(spike2.item(name))) for p in points) for name in GUARDED_ZONES}


def adds(node: Node) -> tuple[str, int, int]:
    """(variable, ModificationType, Value) of a g_modify."""
    return last(prop(node, "Variable1")), prop(node, "ModificationType").v, prop(node, "Value").v


def ladder_run(steps: list[tuple[int, int]], counts: list[int]) -> list[int]:
    """The value spike2.count_ladder's loops keep, driven through `counts`: each loop (up, down) adds 1 once the
    count is >= up and takes it back once the count is <= down, then waits again."""
    armed, var, out = [True] * len(steps), 0, []
    for c in counts:
        for i, (up, down) in enumerate(steps):
            if armed[i] and c >= up:
                armed[i], var = False, var + 1
            elif not armed[i] and c <= down:
                armed[i], var = True, var - 1
        out.append(var)
    return out


def item_of(tag: Node) -> LdItem:
    """The spike2.ITEMS entry a GdItems tag binds to, by its export path."""
    ranking, name = tag.export.removeprefix(GD_ITEMS + "/").split("/")
    it = spike2.item(name)
    assert it.ranking == ranking, tag.export
    return it


@SCRIPT_DATA
class Script(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(template_gdscript()))
        cls.roots, cls.exports = spike2.script(cls.tpl)
        cls.nodes = list(graph.walk(cls.roots))
        (cls.main,) = [n for n in cls.exports if n.export == "$/GDScript/OD/Main"]
        cls.top = subs(cls.main)[-1]                         # Simultaneous[load..., refresh, funnel, Sequential[...]]
        cls.launched, cls.battle = subs(subs(cls.top)[-1])
        timed = [b for b in spike2.BEATS if b.t is not None]
        cls.beats = {}                                       # beat name -> (its WaitDuration, its root node)
        for b, seq in zip(timed, subs(cls.battle), strict=True):
            wait, beat = subs(seq)
            cls.beats[b.check] = (prop(wait, "Duree").v, beat)

    def beat(self, name: str) -> tuple[Node, list[Node]]:
        root = self.beats[name][1]
        return root, list(graph.walk([root]))

    def var(self, name: str) -> Node:
        (v,) = [n for n in self.exports if n.export == f"{spike.VARIABLES}/{name}"]
        return v

    def test_layout(self):
        """The load beats, the refresh loop and the funnel run from load beside the battle; each timed beat is the last
        node of Sequential[WaitDuration t, beat] in the battle Simultaneous, at its time (the race at 0:00:
        it waits for the start dialog's answer)."""
        self.assertEqual([(b.t, b.check) for b in spike2.BEATS],
                         [(None, "deck"), (None, "guard"), (0.0, "dialog"), (0.0, "race"), (5.0, "difficulty"),
                          (10.0, "objectives"), (15.0, "counters"), (60.0, "capture"), (120.0, "count"),
                          (180.0, "vanish"), (300.0, "spring"), (480.0, "traffic"), (900.0, "end")])
        self.assertEqual({name: t for name, (t, _) in self.beats.items()},
                         {b.check: b.t for b in spike2.BEATS if b.t is not None})
        kids = subs(self.top)
        self.assertEqual([k.export for k in kids[2:4]], ["$/GDScript/OD/JoueurRefresh", profile.END_FUNNEL])
        self.assertEqual([n.cls for n in subs(kids[0])], ["TGDDescriptorAddUnitToDeck"] * 2)  # the deck
        self.assertEqual(subs(kids[1])[-1].cls, "TGDDescriptorGereObjectif")               # the defeat guard
        self.assertEqual(token(prop(subs(self.launched)[0], "Info")), "od_hdep")
        self.assertEqual(gates.never_finishing_violations(self.roots)[1], [])  # no objective or reveal holds a beat

    def test_load_deck(self):
        """Load: Rifles_US with Transporter M113A3_US, and M1_Abrams_US with Experience 0 written."""
        cards = {prop(n, "TypeUnit").path: n for n in of(self.nodes, "AddUnitToDeck")}
        self.assertEqual(sorted(cards), sorted(unit_path(u) for u in ("Rifles_US", "M1_Abrams_US")))
        rifles, m1 = cards[unit_path("Rifles_US")], cards[unit_path("M1_Abrams_US")]
        self.assertEqual(prop(rifles, "Transporter").path, unit_path("M113A3_US"))
        self.assertIsNone(prop(rifles, "Experience"))
        self.assertEqual([k for k, _ in m1.props], ["Camp", "Experience", "NbUnitsToAdd", "TypeUnit"])  # HUR #383
        self.assertEqual((prop(m1, "Experience").v, prop(m1, "NbUnitsToAdd").v), (0, 2))
        self.assertTrue(all(prop(n, "Camp").export == JOUEUR for n in cards.values()))

    def test_forced_ownership(self):
        """Load: NATO owns OD_CZ_SW, CAP A, CAP B and TOWN NE (one SetCommandZoneOwnerAndForceConvergence in Main's
        setup, before LoadingDone; HoldUntilRelieved #107). The only other one is the count race's (PACT, TOWN NE)."""
        owner, race = of(self.nodes, "SetCommandZoneOwner")
        self.assertEqual((prop(race, "Camp").export, [last(t) for t in prop(race, "Positions")]),
                         (PACT, ["OD_CZ_TownNE"]))
        self.assertIn(race, list(graph.walk([self.beats["count"][1]])))
        self.assertEqual(prop(owner, "Camp").export, JOUEUR)
        self.assertEqual([last(t) for t in prop(owner, "Positions")],
                         ["OD_CZ_SW", "OD_CZ_CapA", "OD_CZ_CapB", "OD_CZ_TownNE"])
        main = [n.cls for n in subs(self.main)]
        self.assertLess(subs(self.main).index(owner), main.index("TGDDescriptorLoadingDone"))

    def test_defeat_guard(self):
        """The defeat guard: the fail-only objective (no Condition) fails on Groupe_Joueur == 0 and then sets od_end = 2 while it is
        still 0; it starts after the battle is launched and Groupe_Joueur holds a unit (gate 3 counts it). It shows the
        difficulty readout (od_diff, 9 at load) as its one number."""
        obj = objective_named(self.nodes, "od_guard")
        self.assertIsNone(prop(obj, "Condition"))
        self.assertEqual(cmp_of(prop(obj, "ConditionEchec")), ("Groupe_Joueur", 0, 0))
        self.assertEqual([prop(obj, k) for k in ("ListVariables", "ListVariablesForEtiquetteText", "Position")],
                         [[self.var("od_diff")], [self.var("od_diff")], None])
        seq = parent_of(self.nodes, obj)
        nine, phase, guard, _ = subs(seq)
        self.assertEqual(sets([nine], self.var("od_diff")), [spike2.DIFF_NONE])
        self.assertEqual((prop(phase, "Condition").cls, prop(prop(phase, "Condition"), "Phase").v),
                         ("TGDConditionPhase", 2))
        self.assertEqual(cmp_of(prop(guard, "Condition")), ("Groupe_Joueur", 2, 1))
        (latch,) = subs(prop(obj, "ActionsEchec"))
        self.assertEqual(cmp_of(prop(latch, "Condition")), ("od_end", 0, 0))
        self.assertEqual(sets(list(graph.walk([latch])), self.var("od_end")), [spike2.END_LOSS])
        self.assertEqual(gates.check_empty_group_guard(self.roots), 1)
        bare = bricks.g_seq([obj])  # the same objective without its guard fails the gate
        with self.assertRaisesRegex(CheckError, "Groupe_Joueur is empty"):
            gates.check_empty_group_guard([bare])

    def test_start_dialog(self):
        """0:00: [ALL] sets od_run 0 (full) with od_hfull, [FAST] sets it 1 (quick) with od_hquick; the buttons
        are stock INGAME tokens in every language. od_answered = 1 right after the dialog, before the routing (whose
        branches last their hints' 15 s), and nowhere else."""
        root, nodes = self.beat("dialog")
        dialog, answered, route = subs(root)
        self.assertEqual(sets([answered], self.var("od_answered")), [1])
        self.assertEqual([n for n in of(self.nodes, "ModifieVariableInteger")
                          if prop(n, "Variable1") is self.var("od_answered")], [answered])
        self.assertEqual(dialog.cls, "TGDDescriptorEncapsuleCutsceneDialogListWithMultipleChoice")
        (box,) = prop(dialog, "DialogList")
        buttons = (token(prop(box, "TokenBoutonChoix0")), token(prop(box, "TokenBoutonChoix1")))
        self.assertEqual(buttons, ("C_ALL", "HTP_SPDFAT"))
        for lang in LANGS:
            self.assertLessEqual({ndfbin.token_hash(b) for b in buttons}, ingame_keys(lang))
        self.assertEqual(token(prop(prop(box, "TextComponentsToFill")[0], "LocalizedText")), "od_start")
        self.assertEqual(cmp_of(prop(route, "Condition")), ("od_choice", 0, 0))
        self.assertIs(prop(prop(route, "Condition"), "Variable"), prop(box, "SelectedButton"))
        for branch, run, hint in (("EffetIfTrue", 0, "od_hfull"), ("EffetIfFalse", 1, "od_hquick")):
            with self.subTest(branch=branch):
                kids = list(graph.walk([prop(route, branch)]))
                writes = [n for n in of(kids, "ModifieVariableInteger") if prop(n, "Variable1") is self.var("od_run")]
                self.assertEqual([prop(n, "Value").v if prop(n, "Value") else 0 for n in writes], [run])
                self.assertEqual(hints(kids), [hint])

    def test_difficulty(self):
        """0:05: od_diff = 9, then three IfThenElse on ConditionOnGameDifficulty, no else, in a Simultaneous
        (Easy is an empty condition object), each setting od_diff and showing its hint. The readout is the defeat guard's
        (test_defeat_guard)."""
        root, nodes = self.beat("difficulty")
        reset, both = subs(root)
        self.assertEqual(sets([reset], self.var("od_diff")), [spike2.DIFF_NONE])
        branches = subs(both)
        self.assertEqual(of(nodes, "GereObjectif"), [])
        self.assertEqual([b.cls for b in branches], [ITE] * 3)
        for level, branch in enumerate(branches):
            with self.subTest(level=level):
                cond = prop(branch, "Condition")
                self.assertEqual(cond.cls, "TGDConditionOnGameDifficulty")
                self.assertEqual(cond.props, [("Difficulty", graph.i32(level))] if level else [])
                self.assertIsNone(prop(branch, "EffetIfFalse"))
                kids = list(graph.walk([prop(branch, "EffetIfTrue")]))
                writes = [n for n in of(kids, "ModifieVariableInteger") if prop(n, "Variable1") is self.var("od_diff")]
                self.assertEqual([prop(n, "Value").v if prop(n, "Value") else 0 for n in writes], [level])
                self.assertEqual(hints(kids), [f"od_hdif{level}"])

    def test_objectives(self):
        """0:10: O1 completes at 1:00 and chains O3 (ActionsReussi Simultaneous[O3]), which completes at 2:00; O2 fails
        at 1:30; B1 (Bonus, pinned on group X) completes once 2 of X's 3 are dead, and starts only once X holds 3. B1
        shows the 0:15 beat's counters, X alive and the player's BRDM-2 kills."""
        root, nodes = self.beat("objectives")
        self.assertEqual(token(prop(subs(root)[0], "Info")), "od_hobj")
        o1, o2, o3, b1 = (objective_named(nodes, t) for t in ("od_o1", "od_o2", "od_o3", "od_b1"))
        self.assertEqual(cmp_of(prop(o1, "Condition")), ("od_o1", 0, 1))
        self.assertEqual([n is o3 for n in subs(prop(o1, "ActionsReussi"))], [True])
        self.assertEqual(prop(o1, "ActionsReussi").cls, SIM)
        self.assertEqual(cmp_of(prop(o3, "Condition")), ("od_o3", 0, 1))
        self.assertIsNone(prop(o2, "Condition"))
        self.assertEqual(cmp_of(prop(o2, "ConditionEchec")), ("od_o2", 0, 1))
        for name, at in (("od_o1", 60.0), ("od_o2", 90.0), ("od_o3", 120.0)):  # each flag set once, by its timer
            with self.subTest(flag=name):
                writes = [n for n in of(self.nodes, "ModifieVariableInteger") if prop(n, "Variable1") is self.var(name)]
                self.assertEqual(len(writes), 1)
                self.assertEqual(start_s(self.battle, writes[0]), at)
        self.assertEqual(prop(b1, "LabelComponent").text, "Bonus")
        self.assertEqual(last(prop(b1, "Position")), "OD_ParkX")
        self.assertIs(prop(b1, "ShowEtiquette"), graph.TRUE)
        self.assertEqual(cmp_of(prop(b1, "Condition")), ("od_xdone", 3, 1))     # X alive <= 1: 2 of 3 dead
        self.assertEqual([last(v) for v in prop(b1, "ListVariables")], ["od_xalive", "od_kills"])
        guard, _ = subs(parent_of(nodes, b1))
        self.assertEqual(cmp_of(prop(guard, "Condition")), ("od_xdone", 2, 3))  # after X >= 3 (the
        #                                                                         poll's copy, not the group)
        self.assertEqual(gates.check_objective_pins(self.roots), 1)              # B1 only

    def test_counters(self):
        """0:15: 3 + 3 BRDM-2 (PACT) at OD_ParkX and OD_ParkY into od_x and od_y, revealed; a forever loop reads
        the player's BRDM-2 kills, then group X's count, then copies it into od_xdone (B1's input) as its last write,
        every 2 s, until 1:54; at 1:55 KillAllUnit (Vanished) removes X and Y."""
        root, nodes = self.beat("counters")
        hint, seq = subs(root)
        self.assertEqual(token(prop(hint, "Info")), "od_hcnt")
        *creates, end = subs(seq)
        self.assertEqual([(last(prop(c, "Group")), prop(c, "NbUnit").v, last(prop(c, "Position")),
                           prop(c, "TypeUnit").path, prop(c, "Camp").export) for c in creates],
                         [("od_x", 3, "OD_ParkX", unit_path("BRDM_2_SOV"), PACT),
                          ("od_y", 3, "OD_ParkY", unit_path("BRDM_2_SOV"), PACT)])
        effect, rest = subs(end)
        self.assertEqual((end.cls, prop(effect, "Effet").path), (SIM, f"$/GFX/EffectCapacity/{spike.REVEAL_EFFECT}"))
        self.assertEqual([last(g) for g in prop(effect, "UnitGroup")], ["od_x", "od_y"])
        race, gap, removal = subs(rest)
        poll, stop = subs(race)
        self.assertEqual((race.cls, poll.cls, prop(poll, "NbExecutions").v, stop.cls), (COMP, SEQ, FOREVER, WAIT))
        kills, count_x, copy, wait = subs(poll)  # the order: kills, then alive, then B1's copy last
        self.assertEqual((last(prop(count_x, "Variable")), last(prop(count_x, "Group"))), ("od_xalive", "od_x"))
        self.assertEqual((last(prop(copy, "Variable1")), last(prop(copy, "Variable2")), prop(copy, "ModificationType")),
                         ("od_xdone", "od_xalive", None))
        t0 = self.beats["counters"][0]
        self.assertEqual((t0 + prop(stop, "Duree").v, t0 + prop(stop, "Duree").v + prop(gap, "Duree").v),
                         (spike2.COUNTERS_STOP_T, spike2.GROUPS_GONE_T))  # 1:54, 1:55
        self.assertEqual((spike2.COUNTERS_STOP_T, spike2.GROUPS_GONE_T), (114.0, 115.0))
        self.assertEqual((removal.cls, removal.props[0][0], [last(g) for g in prop(removal, "GroupList")]),
                         ("TGDDescriptorKillAllUnit", "GroupList", ["od_x", "od_y"]))  # Vanished: no DeathCause
        self.assertEqual(of(nodes, "GereObjectif"), [])
        self.assertEqual([k for k, _ in kills.props], ["Camp", "TypeUnitList", "Variable"])  # Dieburg #332
        self.assertEqual((prop(kills, "Camp").export, [i.path for i in prop(kills, "TypeUnitList")],
                          last(prop(kills, "Variable"))), (JOUEUR, [unit_path("BRDM_2_SOV")], "od_kills"))
        self.assertEqual(prop(wait, "Duree").v, 2.0)

    def test_race_waits_for_the_answer(self):
        """The race beat starts at 0:00 and waits for od_answered (set by the start
        dialog, test_start_dialog), then 30 s, before it reads od_run; nothing reads od_run before that wait."""
        root, nodes = self.beat("race")
        self.assertEqual(self.beats["race"][0], 0.0)
        answered, wait, pick = subs(root)
        self.assertEqual((answered.cls, cmp_of(prop(answered, "Condition"))), (UNTIL, ("od_answered", 0, 1)))
        self.assertEqual((wait.cls, prop(wait, "Duree").v), (WAIT, 30.0))
        self.assertEqual((pick.cls, cmp_of(prop(pick, "Condition"))), (ITE, ("od_run", 0, spike2.RUN_QUICK)))
        reads = [n for n in of(nodes, "ConditionVariable") if prop(n, "Variable") is self.var("od_run")]
        self.assertEqual(reads, [prop(pick, "Condition")])
        self.assertEqual(of([answered, wait], "WaitDuration"), [wait])  # no fixed wait before the answer
        # A slow answer can't skip the race: whatever the dialog takes, the race starts its 30 s after od_answered.
        self.assertEqual(start_s(root, pick), 30.0)

    def test_race_and_its_flip(self):
        """Quick runs only: the race under EndRace, win (Minor) then loss (Major, alliance 1), flipped on Hard."""
        root, nodes = self.beat("race")
        pick = subs(root)[-1]
        self.assertEqual(pick.cls, ITE)
        self.assertEqual(cmp_of(prop(pick, "Condition")), ("od_run", 0, spike2.RUN_QUICK))
        race = prop(pick, "EffetIfTrue")
        self.assertEqual(race.export, profile.END_RACE)
        self.assertIn(race, self.exports)
        (flip,) = subs(race)
        self.assertEqual(prop(flip, "Condition").props, [("Difficulty", graph.i32(2))])  # Hard
        win, loss = (6, 4, None), (6, 5, 1)
        for branch, order in (("EffetIfTrue", [loss, win]), ("EffetIfFalse", [win, loss])):
            with self.subTest(branch=branch):
                pair = prop(flip, branch)
                self.assertEqual(pair.cls, SIM)
                self.assertEqual([[n.cls for n in subs(s)] for s in subs(pair)], [[TEG], [TEG]])
                self.assertEqual([end_game(subs(s)[0]) for s in subs(pair)], order)

    def test_end_dialog(self):
        """15:00, full runs only: [VICTORY!] sets od_end 1, [DEFEAT!] 2, each only
        while od_end is 0."""
        root, nodes = self.beat("end")
        self.assertEqual(cmp_of(prop(root, "Condition")), ("od_run", 0, spike2.RUN_FULL))
        dialog, route = subs(prop(root, "EffetIfTrue"))
        (box,) = prop(dialog, "DialogList")
        self.assertEqual((token(prop(box, "TokenBoutonChoix0")), token(prop(box, "TokenBoutonChoix1"))),
                         ("win", "lose"))
        self.assertEqual(token(prop(prop(box, "TextComponentsToFill")[0], "LocalizedText")), "od_endq")
        self.assertIs(prop(prop(route, "Condition"), "Variable"), prop(box, "SelectedButton"))
        for branch, value in (("EffetIfTrue", spike2.END_WIN), ("EffetIfFalse", spike2.END_LOSS)):
            with self.subTest(branch=branch):
                latch = prop(route, branch)
                self.assertEqual(cmp_of(prop(latch, "Condition")), ("od_end", 0, 0))
                self.assertEqual(sets(list(graph.walk([latch])), self.var("od_end")), [value])

    # ---- 2b's beats

    def opened(self, name: str, hint: str) -> tuple[list[tuple], list[str], list[Node], list[Node]]:
        """A PACT beat, beat_hint(hint, Sequential[creates..., reveal(groups, rest)]): (each create as (group, count,
        position tag, unit path, camp), the revealed groups, the reveal's rest, every node of the beat). It also checks
        that nothing follows the reveal and that the beat breaks no gate 3 rule on its own."""
        root, nodes = self.beat(name)
        tip, seq = subs(root)
        self.assertEqual((root.cls, token(prop(tip, "Info")), seq.cls), (SIM, hint, SEQ))
        *creates, end = subs(seq)
        effect, rest = subs(end)
        self.assertEqual((end.cls, prop(effect, "Effet").path), (SIM, f"$/GFX/EffectCapacity/{spike.REVEAL_EFFECT}"))
        self.assertEqual(gates.never_finishing_violations([root])[1], [])
        made = [(last(prop(c, "Group")), prop(c, "NbUnit").v, last(prop(c, "Position")), prop(c, "TypeUnit").path,
                 prop(c, "Camp").export) for c in creates]
        return made, [last(g) for g in prop(effect, "UnitGroup")], subs(rest), nodes

    def seconds_loop(self, loop: Node, var: str, reset: bool) -> tuple[Node, Node]:
        """An spike2.seconds_while loop adding 1 to `var` each second: (its start condition, its break condition)."""
        self.assertEqual((loop.cls, prop(loop, "NbExecutions").v), (SEQ, FOREVER))
        start, race, *tail = subs(loop)
        self.assertEqual((start.cls, race.cls), (UNTIL, COMP))
        tick, stop = subs(race)
        self.assertEqual((tick.cls, prop(tick, "NbExecutions").v, stop.cls), (SEQ, FOREVER, UNTIL))
        wait, add = subs(tick)
        self.assertEqual((prop(wait, "Duree").v, adds(add)), (1.0, (var, 1, 1)))
        self.assertEqual(set_values(tail, self.var(var)) if tail else None, [0] if reset else None)
        return prop(start, "Condition"), prop(stop, "Condition")

    def owner_reading(self, reading: Node, zone: str, var: Node) -> None:
        """spike2.owner_reading: IfThenElse(joueur owns `zone`, var = 1, IfThenElse(PACT owns it, var = 2, var = 0)),
        each test a ConditionTeamControleZone with ZoneType 1 and AutoriseControleAllie (TheDieburgSalient #262)."""
        inner = prop(reading, "EffetIfFalse")
        for cond, camp in ((prop(reading, "Condition"), JOUEUR), (prop(inner, "Condition"), PACT)):
            self.assertEqual([k for k, _ in cond.props], ["Position", "Camp", "AutoriseControleAllie", "ZoneType"])
            self.assertEqual((cond.cls, last(prop(cond, "Position")), prop(cond, "Camp").export,
                              prop(cond, "AutoriseControleAllie"), prop(cond, "ZoneType").v),
                             ("TGDConditionTeamControleZone", zone, camp, graph.TRUE, 1))
        branches = (prop(reading, "EffetIfTrue"), prop(inner, "EffetIfTrue"), prop(inner, "EffetIfFalse"))
        self.assertEqual([b.cls for b in branches], [SIM] * 3)
        self.assertEqual([set_values(subs(b), var) for b in branches], [[1], [2], [0]])

    def in_zones(self, cond: Node, zones: tuple[str, ...] = ("OD_CZ_TownNE", "OD_CZ_Shoulder")
                 ) -> tuple[str, int, int]:
        """(camp, operator, value) of a ConditionUnitDansZone over the union of the command zones `zones`, ZoneType 1,
        held in an And of its own (stock: And holds UnitDansZone, Or and WaitCondition do not)."""
        if cond.cls == "TGDConditionAnd":
            (cond,) = prop(cond, "SousConditions")
        self.assertEqual(cond.cls, "TGDConditionUnitDansZone")
        self.assertEqual([last(t) for t in prop(cond, "Detecteurs")], list(zones))
        self.assertEqual([k for k, _ in cond.props], ["ComparaisonNbUnits", "Detecteurs", "Contrainte", "ZoneType"])
        self.assertEqual(prop(cond, "ZoneType").v, 1)
        op = prop(cond, "ComparaisonNbUnits")
        kind, value = prop(op, "OperatorType"), prop(op, "Value")
        return prop(prop(cond, "Contrainte"), "Camp").export, kind.v if kind else 0, value.v if value else 0

    def test_capture(self):
        """1:00 capture. Tank A (T80BV_CMD_SOV) from ENTRY E seizes CAP A; once PACT owns it (ConditionTeamControleZone)
        or after 180 s it drives out to CORNER PACT and the NATO CMD tank is revealed with its hint. Tank B from ENTRY SE
        seizes CAP B and is killed (KillAllUnit, Penetration) 3 s after a Soviet unit is inside CAP B's command zone
        (UnitDansZone on its polygon, not a circle). One readout: CAP A's owner every second (0 none,
        1 NATO, 2 PACT) and the seconds a Soviet unit has been inside CAP A's zone (polygon too)."""
        made, revealed, rest, nodes = self.opened("capture", "od_hcap")
        cmd = unit_path("T80BV_CMD_SOV")
        self.assertEqual(made, [("od_capa", 1, "OD_EntryE", cmd, PACT), ("od_capb", 1, "OD_EntrySE", cmd, PACT)])
        self.assertEqual(revealed, ["od_capa", "od_capb"])
        (both,) = rest
        poll, timer, run_a, run_b, readout = subs(both)
        self.assertEqual(of(nodes, "DetectUnitDansDetecteur"), [])           # no circle left in the beat
        # CAP A's owner, every second, forever
        self.assertEqual((poll.cls, prop(poll, "NbExecutions").v), (SEQ, FOREVER))
        reading_a, wait = subs(poll)
        self.assertEqual(prop(wait, "Duree").v, 1.0)
        self.owner_reading(reading_a, "OD_CZ_CapA", self.var("od_owna"))
        # the Soviet seconds inside CAP A's zone, summed over every stay (no reset)
        start, stop = self.seconds_loop(timer, "od_capa_in", reset=False)
        self.assertEqual(self.in_zones(start, ("OD_CZ_CapA",)), (PACT, 2, 1))
        self.assertEqual(self.in_zones(stop, ("OD_CZ_CapA",)), (PACT, 3, 0))
        # tank A: seize, PACT owns it or 180 s, drive out, then the NATO CMD tank
        seize, until, gone, spawn, tip = subs(run_a)
        self.assertEqual([(k, last(v) if isinstance(v, Node) else v.v) for k, v in seize.props],
                         [("Position", "OD_CZ_CapA"), ("SmartOrderType", 1), ("UnitGroup", "od_capa")])  # Dieburg #519
        owned, timeout = subs(until)
        self.assertEqual((until.cls, owned.cls, timeout.cls, prop(timeout, "Duree").v), (COMP, UNTIL, WAIT, 180.0))
        control = prop(owned, "Condition")
        self.assertEqual((control.cls, last(prop(control, "Position")), prop(control, "Camp").export,
                          prop(control, "ZoneType").v), ("TGDConditionTeamControleZone", "OD_CZ_CapA", PACT, 1))
        self.assertEqual((gone.cls, [(k, [last(g) for g in v]) for k, v in gone.props]),
                         ("TGDDescriptorKillAllUnit", [("GroupList", ["od_capa"])]))  # Vanished
        self.assertEqual(of(nodes, "MoveUnitGroup"), [])  # no order after the Seize smart order
        self.assertEqual((spawn.cls, [last(t) for t in prop(spawn, "Units")]),
                         ("TGDDescriptorSpawnUnits", ["OD_NatoCmd"]))
        self.assertEqual((tip.cls, hints(subs(tip))), (SIM, ["od_hnato"]))
        # tank B: seize CAP B, killed 3 s after a Soviet unit is inside CAP B's zone (its polygon)
        seize_b, entered, delay, kill, tip_b = subs(run_b)
        self.assertEqual((last(prop(seize_b, "Position")), last(prop(seize_b, "UnitGroup"))), ("OD_CZ_CapB", "od_capb"))
        self.assertEqual(entered.cls, UNTIL)
        self.assertEqual(self.in_zones(prop(entered, "Condition"), ("OD_CZ_CapB",)), (PACT, 2, 1))
        self.assertEqual((delay.cls, prop(delay, "Duree").v), (WAIT, 3.0))
        self.assertEqual(kill.cls, "TGDDescriptorKillAllUnit")
        self.assertEqual([(k, v.v if isinstance(v, ndfbin.Value) else [last(g) for g in v]) for k, v in kill.props],
                         [("DeathCause", spike.PENETRATION), ("GroupList", ["od_capb"])])
        self.assertEqual(hints(subs(tip_b)), ["od_hkillb"])
        # the one readout: positionless, stays up, last in the beat's Simultaneous
        self.assertEqual((token(prop(readout, "ObjectiveText")), [last(v) for v in prop(readout, "ListVariables")],
                          prop(readout, "Position"), cmp_of(prop(readout, "Condition"))),
                         ("od_capa", ["od_owna", "od_capa_in"], None, ("od_stay", 0, 1)))
        # B's trigger and A's seconds resolve in exactly one shipped polygon (gate 6)
        details = details_files(spike2.ITEMS, spike2.SCENARIO)
        counts, bad = gates.zone_tag_violations([self.beats["capture"][1]], details)
        self.assertEqual((bad, counts["zone lookups"], counts["detectors"]), ([], 6, 0))

    def test_count_race(self):
        """2:00 count race: 4 BMP-2 from north of TOWN NE seize it. A streak starts on UnitDansZone([TOWN NE,
        SHOULDER]) PACT >= 3 and NATO <= 0, and breaks on PACT <= 2 or NATO >= 1; od_cr_held counts the streak's
        seconds (back to 0 on a break); at 20, SetCommandZoneOwnerAndForceConvergence(PACT, [TOWN NE]) and its hint.
        Readout (2 numbers): Soviet in (an event-driven ladder up to 4) and held."""
        made, revealed, rest, nodes = self.opened("count", "od_hcr")
        self.assertEqual(made, [("od_cr", 4, "OD_TownNENorth", unit_path("BMP_2_SOV"), PACT)])
        self.assertEqual(revealed, ["od_cr"])
        (both,) = rest
        seize, *ladders, held, force, readout = subs(both)
        self.assertEqual((seize.cls, last(prop(seize, "Position")), prop(seize, "SmartOrderType").v,
                          last(prop(seize, "UnitGroup"))), ("TGDDescriptorLaunchSmartOrder", "OD_CZ_TownNE", 1, "od_cr"))
        self.assertEqual(len(ladders), spike2.RACE_LADDER)
        steps = []
        for loop in ladders:
            self.assertEqual(prop(loop, "NbExecutions").v, FOREVER)
            up, inc, down, dec = subs(loop)
            self.assertEqual((up.cls, down.cls, adds(inc), adds(dec)),
                             (UNTIL, UNTIL, ("od_cr_pact", 1, 1), ("od_cr_pact", 2, 1)))
            (c1, op1, k1), (c2, op2, k2) = self.in_zones(prop(up, "Condition")), self.in_zones(prop(down, "Condition"))
            self.assertEqual((c1, op1, c2, op2), (PACT, 2, PACT, 3))
            steps.append((k1, k2))
        self.assertEqual(steps, [(k, k - 1) for k in range(1, 5)])
        counts = [0, 1, 4, 2, 6, 3, 0, 2]  # driven through a count, the ladder keeps the variable at it, up to 4
        self.assertEqual(ladder_run(steps, counts), [min(c, 4) for c in counts])
        start, stop = self.seconds_loop(held, "od_cr_held", reset=True)
        self.assertEqual((start.cls, [self.in_zones(c) for c in prop(start, "SousConditions")]),
                         ("TGDConditionAnd", [(PACT, 2, 3), (JOUEUR, 3, 0)]))  # Marauders #1343/#1344
        self.assertEqual((stop.cls, [(c.cls, self.in_zones(c)) for c in prop(stop, "SousConditions")]),
                         ("TGDConditionOr", [("TGDConditionAnd", (PACT, 3, 2)), ("TGDConditionAnd", (JOUEUR, 2, 1))]))
        wait, owner, tip = subs(force)
        self.assertEqual((wait.cls, cmp_of(prop(wait, "Condition"))), (UNTIL, ("od_cr_held", 2, 20)))
        self.assertEqual((owner.cls, prop(owner, "Camp").export, [last(t) for t in prop(owner, "Positions")]),
                         ("TGDDescriptorSetCommandZoneOwnerAndForceConvergence", PACT, ["OD_CZ_TownNE"]))
        self.assertEqual(hints(subs(tip)), ["od_hcrown"])
        self.assertEqual((token(prop(readout, "ObjectiveText")), [last(v) for v in prop(readout, "ListVariables")]),
                         ("od_cr", ["od_cr_pact", "od_cr_held"]))

    def test_vanish(self):
        """3:00 vanish: 4 BRDM-2 into V at CORNER PACT; once V holds 4 (or 5 s), the PACT losses and the player's kills
        are read, KillAllUnit with no DeathCause (Vanished) removes V, and 2 s later both are read again and the first
        reads subtracted; then one readout of the two changes; 15 s on, a RandomLauncher shows one of two hints."""
        made, revealed, rest, nodes = self.opened("vanish", "od_hvan")
        self.assertEqual(made, [("od_v", 4, "OD_CornerPact", unit_path("BRDM_2_SOV"), PACT)])
        fill, loss0, kill0, kill, wait, loss2, kill2, sub_loss, sub_kill, shown = rest
        full, timeout = subs(fill)
        self.assertEqual((fill.cls, cmp_of(prop(full, "Condition")), prop(timeout, "Duree").v),
                         (COMP, ("od_v", 2, 4), 5.0))
        self.assertEqual([(k, [last(g) for g in v]) for k, v in kill.props], [("GroupList", ["od_v"])])  # Vanished
        self.assertEqual((wait.cls, prop(wait, "Duree").v), (WAIT, 2.0))
        for read, cls, camp, var in ((loss0, "GetNbLossCamp", PACT, "od_vl0"),
                                     (kill0, "GetNbKillsCamp", JOUEUR, "od_vk0"),
                                     (loss2, "GetNbLossCamp", PACT, "od_vl"),
                                     (kill2, "GetNbKillsCamp", JOUEUR, "od_vk")):
            self.assertEqual((read.cls, [k for k, _ in read.props if k != "TypeUnitList"], prop(read, "Camp").export,
                              last(prop(read, "Variable"))), (f"TGDDescriptor{cls}", ["Camp", "Variable"], camp, var))
        for read in (kill0, kill2):  # both stock GetNbKillsCamp carry a type list
            self.assertEqual(([k for k, _ in read.props], [i.path for i in prop(read, "TypeUnitList")]),
                             (["Camp", "TypeUnitList", "Variable"], [unit_path("BRDM_2_SOV")]))
        for sub, var, first in ((sub_loss, "od_vl", "od_vl0"), (sub_kill, "od_vk", "od_vk0")):
            self.assertEqual((last(prop(sub, "Variable1")), last(prop(sub, "Variable2")),
                              prop(sub, "ModificationType").v), (var, first, 2))  # Substract
        picks, readout = subs(shown)
        self.assertEqual((token(prop(readout, "ObjectiveText")), [last(v) for v in prop(readout, "ListVariables")]),
                         ("od_vn", ["od_vl", "od_vk"]))
        delay, pick = subs(picks)
        self.assertEqual((delay.cls, prop(delay, "Duree").v), (WAIT, 15.0))
        self.assertEqual((pick.cls, prop(pick, "NbExecutions").v), ("TGDDescriptorRandomLauncher", 1))
        self.assertEqual([[c.cls for c in subs(s)] for s in subs(pick)], [[SIM], [SIM]])  # Sequential[Simultaneous]
        self.assertEqual([hints(list(graph.walk([s]))) for s in subs(pick)], [["od_hvana"], ["od_hvanb"]])

    def test_traffic(self):
        """8:00 traffic: 10 T-80BV + 10 BMP-2 at ENTRY E into od_tr,
        FastMoveAndAttack (12) by waypoints: a blocking order to NECK MID raced against 240 s (Marauders
        Competition#325's shape: [WaitDuration, Sequential[...]]), then an order to SACK MID (never VILLAGE E);
        every second, the seconds since the spawn and how many reached the SACK MID circle (AddDetectedUnitsToUnitGroup,
        then its count)."""
        self.assertEqual(self.beats["traffic"][0], 480.0)
        made, revealed, rest, nodes = self.opened("traffic", "od_htr")
        self.assertEqual(made, [("od_tr", 10, "OD_EntryE", unit_path("T80BV_SOV"), PACT),
                                ("od_tr", 10, "OD_EntryE", unit_path("BMP_2_SOV"), PACT)])
        self.assertEqual(revealed, ["od_tr"])
        (both,) = rest
        route, poll, readout = subs(both)
        race, second = subs(route)
        timeout, leg = subs(race)
        self.assertEqual((race.cls, timeout.cls, prop(timeout, "Duree").v, leg.cls), (COMP, WAIT, 240.0, SEQ))
        (first,) = subs(leg)
        self.assertEqual([(k, v.v if isinstance(v, ndfbin.Value) else last(v)) for k, v in first.props],
                         [("Blocking", True), ("Group", "od_tr"), ("OrderType", 12), ("Position", "OD_NeckMid")])
        self.assertEqual([(k, v.v if isinstance(v, ndfbin.Value) else last(v)) for k, v in second.props],
                         [("Group", "od_tr"), ("OrderType", 12), ("Position", "OD_SackMid")])
        self.assertEqual([last(prop(o, "Position")) for o in (first, second)], list(spike2.TRAFFIC_WAYPOINTS))
        # The second leg starts at most 240 s after the beat, whatever the first leg does.
        self.assertEqual(gates.finish_status(race, {}), gates.FINISHES)
        named = {last(v) for n in nodes for _, v in n.props if isinstance(v, Node) and v.export
                 and v.export.startswith(GD_ITEMS)}
        self.assertFalse(named & {"OD_CZ_CapA", "OD_CZ_CapB", "OD_CZ_TownNE", "OD_CZ_Shoulder"})
        self.assertEqual((prop(poll, "NbExecutions").v, [n.cls.removeprefix("TGDDescriptor") for n in subs(poll)]),
                         (FOREVER, ["WaitDuration", "ModifieVariableInteger", "AddDetectedUnitsToUnitGroup",
                                    "SetVariableIntegerFromUnitGroup"]))
        wait, tick, collect, count = subs(poll)
        self.assertEqual((prop(wait, "Duree").v, adds(tick)), (1.0, ("od_tr_s", 1, 1)))
        detector = prop(collect, "Detector")
        self.assertEqual((last(prop(collect, "Group")), prop(detector, "ComparaisonNbUnits"),
                          last(prop(detector, "Detecteur")), prop(prop(detector, "Contrainte"), "Camp").export),
                         ("od_through", None, "OD_RingSackExit", PACT))  # HUR #112: no count on the detector
        self.assertEqual((last(prop(count, "Variable")), last(prop(count, "Group"))), ("od_tr_n", "od_through"))
        self.assertEqual([last(v) for v in prop(readout, "ListVariables")], ["od_tr_s", "od_tr_n"])

    def test_spring(self):
        """5:00 spring dialog: the choice and its copy = 2, then the readout (asks, the live choice) beside
        Sequential[Competition[up to 4 x (choice = copy = 2, asks += 1, dialog FIRE AT WILL / HOLD FIRE, copy = choice,
        30 s), WaitCondition(copy == 0)], IfThenElse(copy == 0, hint od_hnow, hint od_hwait)] (BackhandBlow
        Competition#194's exit). The exit and the verdict read the copy made after the dialog closed, never
        the live SelectedButton."""
        root, nodes = self.beat("spring")
        pick, asks, ans = self.var("od_spr_pick"), self.var("od_spr_asks"), self.var("od_spr_ans")
        tip, seq = subs(root)
        self.assertEqual(token(prop(tip, "Info")), "od_hspr")
        reset, reset_ans, both = subs(seq)
        self.assertEqual((set_values([reset], pick), set_values([reset_ans], ans)), ([2], [2]))
        readout, then = subs(both)
        self.assertEqual(prop(readout, "ListVariables"), [asks, pick])
        race, verdict = subs(then)
        loop, exit_ = subs(race)
        self.assertEqual((race.cls, loop.cls, prop(loop, "NbExecutions").v, exit_.cls), (COMP, SEQ, 4, UNTIL))
        again, again_ans, count, dialog, copy, gap = subs(loop)
        self.assertEqual((set_values([again], pick), set_values([again_ans], ans), adds(count), prop(gap, "Duree").v),
                         ([2], [2], ("od_spr_asks", 1, 1), 30.0))
        self.assertEqual((prop(copy, "Variable1"), prop(copy, "Variable2"), prop(copy, "ModificationType")),
                         (ans, pick, None))
        # nothing reads the live choice but the readout: the exit and the verdict read the copy
        readers = [n for n in nodes if n.cls == "TGDConditionVariable" and prop(n, "Variable") is pick]
        self.assertEqual(readers, [])
        (box,) = prop(dialog, "DialogList")
        buttons = (token(prop(box, "TokenBoutonChoix0")), token(prop(box, "TokenBoutonChoix1")))
        self.assertEqual(buttons, ("ORD_AIARA", "ORD_HOLDF"))  # FIRE AT WILL, HOLD FIRE
        for lang in LANGS:
            self.assertLessEqual({ndfbin.token_hash(b) for b in buttons}, ingame_keys(lang))
        self.assertIs(prop(box, "SelectedButton"), pick)
        self.assertEqual(token(prop(prop(box, "TextComponentsToFill")[0], "LocalizedText")), "od_springq")
        self.assertEqual(cmp_of(prop(exit_, "Condition")), ("od_spr_ans", 0, 0))
        self.assertEqual(cmp_of(prop(verdict, "Condition")), ("od_spr_ans", 0, 0))
        self.assertEqual([hints(subs(prop(verdict, b))) for b in ("EffetIfTrue", "EffetIfFalse")],
                         [["od_hnow"], ["od_hwait"]])
        # The script sets the choice and its copy to 2 before the exit WaitCondition starts and before each ask, and
        # copies the choice only after the dialog: neither a stale 0 nor a default written at the dialog's start can end
        # the loop.
        self.assertEqual((set_values(self.nodes, pick), set_values(self.nodes, ans)), ([2, 2], [2, 2]))
        self.assertEqual(within(seq, reset, reset_ans, both), [0, 1, 2])
        self.assertEqual(within(loop, dialog, copy), [3, 4])

    def test_spawns_and_routes_keep_out_of_the_zones(self):
        """The traffic and the capture's routes: every PACT spawn lies 25 px (300 m) or more from every capture and count-race
        zone; the traffic's waypoints and the road it takes (spike2.TRAFFIC_ROAD_PX), 40 px or more;
        tank B's way from ENTRY SE to CAP B never comes within 50 px of CAP A (straight lines; the roads were read off
        the Minimap). Tank A has no way out: it is removed."""
        spawns = {last(prop(c, "Position")) for c in of(self.nodes, "CreateUnitOnPosition")
                  if prop(c, "Camp").export == PACT}
        self.assertEqual(spawns, {"OD_ParkX", "OD_ParkY", "OD_EntryE", "OD_EntrySE", "OD_TownNENorth", "OD_CornerPact"})
        for name in sorted(spawns):
            with self.subTest(spawn=name):
                self.assertGreater(min(clearance([px_of(spike2.item(name))]).values()), 25.0)
        orders = [o for o in of(self.nodes, "GiveOrderStandard") if last(prop(o, "Group")) == "od_tr"]
        for o in orders:
            with self.subTest(waypoint=last(prop(o, "Position"))):
                self.assertGreater(min(clearance([px_of(item_of(prop(o, "Position")))]).values()), 40.0)
        for line in spike2.TRAFFIC_ROAD_PX:
            points = [p for a, b in zip(line, line[1:]) for p in along(a, b)]
            self.assertGreater(min(clearance(points).values()), 40.0, clearance(points))
        b_way = along(spike2.ENTRY_SE, POINTS["TOWN_SE"])
        self.assertGreater(clearance(b_way)["OD_CZ_CapA"], 50.0)

    def test_b1_counts_only_kills(self):
        """B1 resolves on od_xdone, written only as the last step of the counters poll
        round, which ends at 1:54; X and Y are removed at 1:55, after the last write, so a removal can't complete B1 (a
        group count can't tell dead from removed, so B1's input is frozen at 1:54 instead). The vanish beat's first read
        (3:00) comes after the removal."""
        done = self.var("od_xdone")
        writes = [n for n in of(self.nodes, "ModifieVariableInteger") if prop(n, "Variable1") is done]
        counters, nodes = self.beat("counters")
        (poll,) = [n for n in nodes if n.cls == SEQ and prop(n, "NbExecutions").v == FOREVER]
        self.assertEqual(writes, [subs(poll)[2]])
        (race,) = [n for n in nodes if n.cls == COMP]
        self.assertIn(poll, subs(race))
        (removal,) = [n for n in nodes if n.cls == "TGDDescriptorKillAllUnit"]
        reveal_seq = parent_of(nodes, race)
        self.assertLess(within(reveal_seq, race)[0], within(reveal_seq, removal)[0])
        readers = [n for n in self.nodes if n.cls == "TGDConditionVariable" and prop(n, "Variable") is done]
        b1 = objective_named(self.nodes, "od_b1")
        self.assertEqual(len(readers), 2)
        self.assertIn(prop(b1, "Condition"), readers)
        self.assertFalse([n for n in self.nodes if n.cls == "TGDConditionVariable"
                          and prop(n, "Variable") is self.var("od_x")])  # nothing reads group X's own count
        vanish, vnodes = self.beat("vanish")
        self.assertGreater(self.beats["vanish"][0], spike2.GROUPS_GONE_T)
        fill, first_read = subs(subs(subs(subs(vanish)[1])[-1])[1])[:2]  # beat_hint > Sequential > reveal > its rest
        self.assertEqual((fill.cls, first_read), (COMP, of(vnodes, "GetNbLossCamp")[0]))  # the baseline, after the fill

    def test_funnel(self):
        """The funnel waits for od_end >= 1, then ends the game, a total victory on 1 and a loss otherwise. It runs
        from load, and gate 3 finds every TriggerEndGame under it or the race: the funnel is used."""
        (funnel,) = [n for n in self.exports if n.export == profile.END_FUNNEL]
        self.assertIn(funnel, subs(self.top))
        wait, pick = subs(funnel)
        self.assertEqual(cmp_of(prop(wait, "Condition")), ("od_end", 2, 1))
        self.assertEqual(cmp_of(prop(pick, "Condition")), ("od_end", 0, 1))
        self.assertEqual([end_game(subs(prop(pick, b))[0]) for b in ("EffetIfTrue", "EffetIfFalse")],
                         [(6, 6, None), (6, 6, 1)])  # Gotterdammerung #258 / #254
        self.assertEqual(check_end_funnel(self.roots), (6, True))
        stray = bricks.g_seq([bricks.g_end_game(shapes.TOTAL_VICTORY)])  # an ending outside both fails
        with self.assertRaisesRegex(CheckError, "end funnel"):
            check_end_funnel([*self.roots, stray])

    def test_od_end_only_while_zero(self):
        """Every write to od_end is the only node of an IfThenElse(od_end == 0) branch (set_end)."""
        end = self.var("od_end")
        writes = [n for n in of(self.nodes, "ModifieVariableInteger") if prop(n, "Variable1") is end]
        self.assertEqual(len(writes), 3)  # the defeat guard, VICTORY!, DEFEAT!
        for w in writes:
            latch = parent_of(self.nodes, parent_of(self.nodes, w))
            self.assertEqual(latch.cls, ITE)
            self.assertEqual(cmp_of(prop(latch, "Condition")), ("od_end", 0, 0))

    def test_objective_rows(self):
        """The whole run holds at most 10 objectives (a resolved objective stays on the panel), each
        showing at most 2 numbers, the stock maximum (Stock.test_objective_numbers); each text and label uses exactly
        the placeholders %1..%n its list fills, in English and Chinese."""
        objectives = of(self.nodes, "GereObjectif")
        self.assertEqual(len(objectives), spike2.OBJECTIVE_ROWS_MAX)
        self.assertEqual(sorted(token(prop(o, "ObjectiveText")) for o in objectives),
                         sorted(["od_guard", "od_o1", "od_o2", "od_o3", "od_b1", "od_capa", "od_cr", "od_vn", "od_spr",
                                 "od_tr"]))
        table = {t: texts for d in spike2.STRINGS.values() for t, texts in d.items()}
        for o in objectives:
            with self.subTest(objective=token(prop(o, "ObjectiveText"))):
                for text, numbers in (("ObjectiveText", "ListVariables"),
                                      ("ObjectiveEtiquetteText", "ListVariablesForEtiquetteText")):
                    n = len(prop(o, numbers) or [])
                    self.assertLessEqual(n, spike2.OBJECTIVE_VARIABLES_MAX)
                    for words in table[token(prop(o, text))].values():
                        self.assertLessEqual(set(re.findall(r"%(\d)", words)), {str(k) for k in range(1, n + 1)})
                    if text == "ObjectiveText":
                        self.assertEqual(set(re.findall(r"%(\d)", table[token(prop(o, text))].US)),
                                         {str(k) for k in range(1, n + 1)})

    def test_pact_beats_end_with_reveal(self):
        """Every Sequential that creates PACT units ends with spike.reveal() on exactly the groups it fills."""
        found = 0
        for seq in of(self.nodes, "Sequential"):
            made = [n for n in subs(seq)
                    if n.cls == "TGDDescriptorCreateUnitOnPosition" and prop(n, "Camp").export == PACT]
            if not made:
                continue
            found += 1
            end = subs(seq)[-1]
            self.assertEqual(end.cls, SIM)
            self.assertEqual(prop(subs(end)[0], "UnitGroup"), list(dict.fromkeys(prop(c, "Group") for c in made)))
        self.assertEqual(found, 5)  # counters, capture, count race, vanish, traffic

    def test_tokens_are_in_the_table(self):
        """Every loc token the script uses is in STRINGS, but the dialog buttons (INGAME)."""
        table = {t for d in spike2.STRINGS.values() for t in d}
        used = set()
        for nd in self.nodes:
            for key, v in nd.props:
                if isinstance(v, ndfbin.Value) and v.tag == 0x1D and (nd.cls, key) not in gates.INGAME_PROPS:
                    used.add(token(v))
        self.assertEqual(sorted(used - table), [])
        self.assertEqual(sorted(table - used - set(spike2.MENU_TOKENS)), [])  # no stray tokens


@GEISA_DATA
class Items(unittest.TestCase):
    """Spike 2's geometry (one place: spike2.ITEMS), 2b's included."""

    @classmethod
    def setUpClass(cls):
        cls.details = details_files(spike2.ITEMS, spike2.SCENARIO)
        hdr, rgba = tgv.read_tgv(minimap())
        cls.minimap_w, cls.minimap = hdr.width, tgv.drop_alpha(rgba)

    def luminance(self, p: tuple[float, float], reach: int = 0) -> int:
        """The brightest Minimap pixel within `reach` px of `p` (grey mean)."""
        x, y = round(p[0]), round(p[1])
        return max(sum(self.minimap[((y + dy) * self.minimap_w + x + dx) * 3:][:3]) // 3
                   for dx in range(-reach, reach + 1) for dy in range(-reach, reach + 1))

    def test_player_side(self):
        """Spike 1's OD_CZ_SW and arrivals; spike 2's own deployment zone (test_own_deployment_zone)."""
        mine = {it.name: it for it in spike2.ITEMS}
        for it in spike.ITEMS:
            if it.name == "OD_CZ_SW" or it.addon in gates.ARRIVALS:
                self.assertEqual(mine[it.name], it)
        self.assertNotIn("OD_DZ_W", mine)
        self.assertEqual(gates.check_arrivals(spike2.ITEMS, self.details), (2, 2))

    def test_own_deployment_zone(self):
        """OD_DZ_W2 is probe 1's DZ ending at x 480, 10 px west of SHOULDER's command
        zone, so no unit can deploy in SHOULDER (nor TOWN NE, CAP A, CAP B); the player's arrival Ends lie inside it
        (gates 3 and 7: check_arrivals on the shipped bytes, command zones not counted); the script's zone lookups
        resolve (gate 6); spike 1's own zone is unchanged."""
        (dz,) = [it for it in spike2.ITEMS if it.addon == "DeploymentZone"]
        self.assertEqual((dz.ranking, dz.name, dz.alliance, box_px(dz)), ("DeploymentZone", "OD_DZ_W2", None,
                                                                          spike2.DZ_W2))
        self.assertEqual(spike2.DZ_W2, (13, 250, 480, 780))
        shoulder = box_px(spike2.item("OD_CZ_Shoulder"))
        self.assertEqual(shoulder[0] - spike2.DZ_W2[2], 10)
        for name in GUARDED_ZONES:
            with self.subTest(zone=name):
                self.assertFalse(gates.polygons_overlap(dz.polygon, spike2.item(name).polygon))
        self.assertEqual(to_box(POINTS["SHOULDER"], spike2.DZ_W2), 40.0)  # spike 1's DZ held it
        _, bad = gates.arrival_violations(self.details[leveldesign.LD_FILE],
                                         self.details[leveldesign.ZONE_FILES["DeploymentZone"]], None, command_zones=False)
        self.assertEqual(bad, [])
        tpl, _, _ = decode(read_file(template_gdscript()))
        roots, _ = spike2.script(tpl)
        counts, bad = gates.zone_tag_violations(roots, self.details)
        self.assertEqual((bad, counts["zone items"], counts["command zones"]), ([], 6, 5))
        # spike 1 keeps its zone (its builds are byte-identical: the baseline hashes)
        self.assertEqual(spike.DZ_W, (13, 250, 540, 780))
        (dz1,) = [it for it in spike.ITEMS if it.addon == "DeploymentZone"]
        self.assertEqual((dz1.name, box_px(dz1)), ("OD_DZ_W", spike.DZ_W))

    def test_traffic_road_on_the_minimap(self):
        """The traffic's waypoints (NECK MID in its hamlet, SACK MID) and every vertex of the road it takes
        (spike2.TRAFFIC_ROAD_PX) sit on a road or built-up pixel of Geisa's Minimap (luminance 55 or more; fields and
        forest are darker); the spawns of tank B and the count race sit on a road, ENTRY E within 3 px of one."""
        for name in spike2.TRAFFIC_WAYPOINTS:
            with self.subTest(waypoint=name):
                self.assertGreaterEqual(self.luminance(px_of(spike2.item(name))), ROAD_LUMINANCE)
        self.assertEqual([px_of(spike2.item(n)) for n in spike2.TRAFFIC_WAYPOINTS],
                         [spike2.TRAFFIC_ROAD_PX[0][-3], spike2.TRAFFIC_ROAD_PX[0][-1]])
        for line in spike2.TRAFFIC_ROAD_PX:
            for p in line:
                with self.subTest(road=p):
                    self.assertGreaterEqual(self.luminance(p), ROAD_LUMINANCE)
        self.assertEqual(spike2.TRAFFIC_ROAD_PX[0][0], (756, 397))  # ENTRY E's road
        for name, reach in (("OD_EntrySE", 0), ("OD_TownNENorth", 0), ("OD_EntryE", 3)):
            with self.subTest(spawn=name):
                self.assertGreaterEqual(self.luminance(px_of(spike2.item(name)), reach), ROAD_LUMINANCE)

    def test_no_geisa_zone_covers_the_towns(self):
        """Why the town zones are squares: no polygon of Geisa's own command zones (its out/CommandZone.ndfbin, read as
        the zone readers read it) holds any of the four points."""
        raw = read_file(os.path.join(extracted(GEISA.details), "out", "CommandZone.ndfbin"))
        zones = gates.zone_polygons(raw)
        self.assertEqual(len(zones), 17)
        for point in spike2.TOWN_ZONES.values():
            x, y = GEISA.px_to_world(POINTS[point])
            self.assertEqual([n for n, _, poly in zones if point_in_polygon(x, y, poly)], [], point)

    def test_town_zones(self):
        """Each town zone is the 60 px square around its point, item at the centre, 2 points, apart from the others."""
        for name, point in spike2.TOWN_ZONES.items():
            with self.subTest(zone=name):
                it = spike2.item(name)
                self.assertEqual((it.ranking, it.addon, it.points), ("CommandPoints", "CommandPoints", 2))
                self.assertEqual(px_of(it), POINTS[point])
                xs, ys = zip(*(GEISA.world_to_px(p) for p in it.polygon))
                px, py = POINTS[point]
                self.assertEqual((min(xs), min(ys), max(xs), max(ys)), (px - 30, py - 30, px + 30, py + 30))
        zones = [it for it in spike2.ITEMS if it.addon == "CommandPoints"]
        self.assertEqual(len(zones), 5)
        for k, a in enumerate(zones):
            for b in zones[k + 1:]:
                self.assertFalse(gates.polygons_overlap(a.polygon, b.polygon), (a.name, b.name))

    def test_circles(self):
        """The one circle, the passage exit on SACK MID; the CAP circles are gone (the capture beat tests
        the CAP zones by polygon)."""
        (it,) = [it for it in spike2.ITEMS if it.addon == "CircularZone"]
        self.assertEqual((it.ranking, it.name, it.addon, px_of(it)),
                         ("CircularZones", "OD_RingSackExit", "CircularZone", POINTS["SACK_MID"]))
        self.assertAlmostEqual(radius_px(it), 20.0, places=6)

    def test_parking(self):
        """Groups X and Y park about 1 km east of spike 1's DZ east edge (1.5-2 km from OD_DZ_W2's), apart, outside
        every zone and circle, and well away from the traffic's road (y >= 400 px) and the NATO CMD tank's drive (y
        475)."""
        x, y = px_of(spike2.item("OD_ParkX")), px_of(spike2.item("OD_ParkY"))
        for at in (x, y):
            with self.subTest(at=at):
                self.assertTrue(0.7 <= (at[0] - spike.DZ_W[2]) / spike2.KM_PX <= 1.3)
                self.assertTrue(1.5 <= (at[0] - spike2.DZ_W2[2]) / spike2.KM_PX <= 2.0)
                self.assertLess(at[1], 400 - 80)
                world = GEISA.px_to_world(at)
                for it in spike2.ITEMS:
                    if it.polygon and it.addon == "CommandPoints":
                        self.assertFalse(point_in_polygon(*world, list(it.polygon)), it.name)
                    if it.addon == "CircularZone":
                        self.assertGreater(math.dist(at, px_of(it)), radius_px(it), it.name)
        self.assertGreater(math.dist(x, y), 25.0)

    def test_nato_cmd(self):
        """The NATO M1A1HA CMD: a hidden player spawn about 1 km west of CAP A, on the road
        south of a farmstead, outside every zone, 50 px or more from CAP A's and CAP B's squares and 90 px from the
        traffic's road."""
        it = spike2.item("OD_NatoCmd")
        self.assertEqual((it.ranking, it.addon, it.unit, it.camp, it.disable_auto_spawn),
                         ("Camp_0", "Spawn", "M1A1HA_Abrams_CMD_US", 0, True))
        at = px_of(it)
        self.assertEqual(at, (616.0, 488.0))
        self.assertAlmostEqual(math.dist(at, POINTS["VILLAGE_E"]) / spike2.KM_PX, 1.0, delta=0.05)
        self.assertLess(at[0], POINTS["VILLAGE_E"][0])
        near = clearance([at])
        self.assertEqual((near["OD_CZ_CapA"], near["OD_CZ_CapB"]), (54.0, 72.0))
        road = [p for line in spike2.TRAFFIC_ROAD_PX for a, b in zip(line, line[1:]) for p in along(a, b)]
        self.assertGreater(min(math.dist(at, p) for p in road), 90.0)
        self.assertGreaterEqual(self.luminance(at), ROAD_LUMINANCE)

    def test_waypoint_tags(self):
        """The spawn and waypoint tags; VILLAGE E is none (the traffic skips it)."""
        for name, at in (("OD_EntryE", "ENTRY_E"), ("OD_EntrySE", spike2.ENTRY_SE),
                         ("OD_TownNENorth", spike2.RACE_SPAWN), ("OD_NeckMid", "NECK_MID"),
                         ("OD_SackMid", "SACK_MID"), ("OD_CornerPact", "CORNER_PACT")):
            with self.subTest(tag=name):
                it = spike2.item(name)
                self.assertEqual((it.ranking, it.addon, px_of(it)),
                                 ("Tags", "Name", POINTS[at] if isinstance(at, str) else at))
        self.assertNotIn("OD_VillageE", {it.name for it in spike2.ITEMS})
        self.assertEqual(spike2.ENTRY_SE, (756.0, 585.0))
        self.assertEqual(spike2.RACE_SPAWN, (655.0, 158.0))

    def test_inside_the_playable_zone(self):
        ring = GEISA.playable_polygon()
        for it in spike2.ITEMS:
            if it.addon in gates.ARRIVALS:
                continue  # Geisa's own entries start at the map edge
            with self.subTest(item=it.name):
                for p in it.polygon or ((it.x, it.y),):
                    self.assertTrue(point_in_polygon(*p, ring), (it.name, GEISA.world_to_px(p)))

    def test_2b_lookups_pass_gate_6(self):
        """The kinds of lookup the beats make, built with the bricks against the shipped Details: TeamControleZone on
        CAP A and CAP B for both sides, UnitDansZone on CAP A, on CAP B and over [TOWN NE, SHOULDER],
        SetCommandZoneOwner(PACT, TOWN NE) and the SACK MID circle as a detector. Each resolves in exactly one polygon;
        with ZoneType 0 the same lookups fail."""
        ctx = spike2.Ctx()
        nato, pact = ctx.camp("NATO"), ctx.camp("PACT")
        tag = ctx.tag
        conds = [bricks.g_zone_control(camp, tag(z)) for camp in (nato, pact) for z in ("OD_CZ_CapA", "OD_CZ_CapB")]
        conds += [bricks.g_units_in_zones([tag(z)], bricks.c_team(pact), 1, 2) for z in ("OD_CZ_CapA", "OD_CZ_CapB")]
        conds.append(bricks.g_units_in_zones([tag("OD_CZ_TownNE"), tag("OD_CZ_Shoulder")], bricks.c_team(pact), 3, 2))
        conds.append(bricks.g_detect(tag("OD_RingSackExit"), bricks.c_team(pact), 1, 2))
        root = bricks.g_seq([*(bricks.g_until(c) for c in conds), bricks.g_zone_owner(pact, [tag("OD_CZ_TownNE")])])
        self.assertEqual(gates.check_zone_tags([root], self.details),
                         {"zone lookups": 9, "detectors": 1, "zone items": 6, "command zones": 5})
        for c in conds[:7]:  # ZoneType 0 looks in the deployment zones, which hold none of these (OD_DZ_W2 stops
            #                  west of SHOULDER; spike 1's held it)
            c.props = [(k, graph.i32(0) if k == "ZoneType" else v) for k, v in c.props]
        _, bad = gates.zone_tag_violations([root], self.details)
        self.assertEqual(len(bad), 8, bad)
        self.assertTrue(all("0 polygons of out/DeploymentZone.ndfbin" in b for b in bad), bad)


@STOCK_DATA
class Stock(unittest.TestCase):
    def test_objective_numbers(self):
        """OBJECTIVE_VARIABLES_MAX is stock's: no objective of the stock GDScripts (challenges and strategic campaigns)
        fills ListVariables or ListVariablesForEtiquetteText with more than 2 variables, and some fill 2."""
        paths = sorted(glob.glob(os.path.join(extracted("scenarios"), "*", "NDF", "Scenarios", "*", "GDScript.txn")))
        self.assertGreaterEqual(len(paths), 16)
        most = 0
        for path in paths:
            nb, _, _ = decode(read_file(path))
            for ob in nb.objects:
                if nb.cname(ob.cls).startswith("TGDDescriptorGereObjectif"):
                    for pi, v in ob.props:
                        if nb.pname(pi) in ("ListVariables", "ListVariablesForEtiquetteText"):
                            most = max(most, sum(1 for x in ndfbin.iter_values(v) if x.tag == 0x09))
        self.assertEqual(most, spike2.OBJECTIVE_VARIABLES_MAX)


class Bricks(unittest.TestCase):
    """The mission bricks probe 2 uses, each in its stock object's property order."""

    def test_choice_is_spike_1s_dialog(self):
        """g_choice builds probe 1's start dialog node for node (probe 1 builds byte-identical with it)."""
        ctx = spike.Ctx()
        (dialog,) = of(list(graph.walk([spike.start_dialog(ctx)])), "EncapsuleCutsceneDialogListWithMultipleChoice")
        (box,) = prop(dialog, "DialogList")
        self.assertEqual([k for k, _ in box.props], ["AfficherBoutonPause", "ComponentName", "DureePause", "Pause",
                                                     "TextComponentsToFill", "TokenBoutonChoix0",
                                                     "VisibleByAlliedOfSpecifiedCamp", "VisibleByCamp",
                                                     "SelectedButton", "TokenBoutonChoix1"])  # Sledgehammer #621

    def test_difficulty(self):
        self.assertEqual(bricks.g_difficulty(shapes.EASY).props, [])  # HoldUntilRelieved #199
        self.assertEqual(bricks.g_difficulty(shapes.HARD).props, [("Difficulty", graph.i32(2))])

    def test_end_game(self):
        self.assertEqual(end_game(bricks.g_end_game(shapes.TOTAL_VICTORY)), (6, 6, None))
        self.assertEqual([k for k, _ in bricks.g_end_game(5, shapes.PACT_ALLIANCE).props],
                         ["VictoryReason", "VictoryType", "WinningAlliance"])

    def test_zone_bricks_write_zone_type_1(self):
        camp, zone = camp_nodes(profile.CAMP_ROWS, profile.CAMP_TOKENS)["joueur"], Node("TGDTagPosition")
        control = bricks.g_zone_control(camp, zone)
        self.assertEqual([k for k, _ in control.props], ["Position", "Camp", "AutoriseControleAllie", "ZoneType"])
        inside = bricks.g_units_in_zones([zone], bricks.c_team(camp), 5, 2)
        self.assertEqual([k for k, _ in inside.props], ["ComparaisonNbUnits", "Detecteurs", "Contrainte", "ZoneType"])
        for nd in (control, inside):
            self.assertEqual(prop(nd, "ZoneType").v, 1)
        owner = bricks.g_zone_owner(camp, [zone])
        self.assertEqual([k for k, _ in owner.props], ["Camp", "Positions"])

    def test_kills_and_losses(self):
        camp, var = camp_nodes(profile.CAMP_ROWS, profile.CAMP_TOKENS)["joueur"], Node("TGDVariableInteger")
        self.assertEqual([k for k, _ in bricks.g_kills(var, camp, ["BRDM_2_SOV"]).props],
                         ["Camp", "TypeUnitList", "Variable"])  # HoldUntilRelieved #237
        self.assertEqual([k for k, _ in bricks.g_kills(var, camp).props], ["Camp", "Variable"])
        self.assertEqual([k for k, _ in bricks.g_losses(var, camp).props], ["Camp", "Variable"])  # Glory #161

    def test_seize_and_random(self):
        group, zone = Node("TGDVariableUnitGroup"), Node("TGDTagPosition")
        seize = bricks.g_seize(group, zone)
        self.assertEqual((seize.cls, seize.props), ("TGDDescriptorLaunchSmartOrder",  # TheDieburgSalient #519
                                                    [("Position", zone), ("SmartOrderType", graph.i32(1)),
                                                     ("UnitGroup", group)]))
        kids = [bricks.g_seq([]), bricks.g_seq([])]
        pick = bricks.g_random(kids)
        self.assertEqual((pick.cls, pick.props), ("TGDDescriptorRandomLauncher",  # BlackHorsesLastStand #100
                                                  [("SubActions", kids), ("NbExecutions", graph.u32(1))]))


class Identity(unittest.TestCase):
    def test_identity(self):
        """Its own scenario, mod folder, GUID and menu tokens; the tags carry the scenario's item GUIDs."""
        c = spike2.content()
        self.assertEqual((c.name, c.scenario, c.mod_name), ("spike2", "challenge_OpenDoorTest", "OpenDoorTest"))
        self.assertEqual(scenario_guid(c.scenario), scenario_guid("challenge_OpenDoorTest"))
        self.assertNotEqual(scenario_guid(c.scenario), scenario_guid(profile.SCENARIO))
        self.assertEqual(c.menu_renames["op13_name"], "o2_name")
        self.assertEqual(c.menu_tokens, tuple(c.menu_renames.values()))
        self.assertFalse(set(c.menu_tokens) & set(profile.MENU_TOKENS))  # spike 1 keeps its od_* menu tokens
        self.assertEqual(sorted(spike2.STRINGS["SCENARIO_DEFINITION"]), sorted(c.menu_tokens))
        self.assertEqual(spike2.STRINGS["SCENARIO_DEFINITION"]["o2_name"].US, "Open Door test 2")
        ctx = spike2.Ctx()
        it = spike2.item("OD_CZ_CapA")
        self.assertEqual(prop(ctx.tag("OD_CZ_CapA"), leveldesign.TAG_ID).v, ld_guid(it, "challenge_OpenDoorTest"))
        self.assertEqual(spike.content().menu_renames, profile.LOC_RENAMES)  # spike 1 unchanged


@SCRIPT_DATA
@GAME
class Build(unittest.TestCase):
    def test_spike2_builds(self):
        """`--content spike2` passes every gate and writes OpenDoorTest with challenge_OpenDoorTest packs, whose
        MapConfiguration carries the o2_* menu tokens and the scenario's GUID."""
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(probe_main(["--content", "spike2", "--out", OUT]), 0)
            log = out.getvalue()
            self.assertIn("gate 3 mission: 6 TriggerEndGame, each under", log)
            self.assertIn("1 objective failure tests on an empty unit group", log)
            self.assertIn("3 dialog texts without %1..%9", log)                    # start, spring, end
            self.assertIn("35 zone lookups each in exactly one shipped polygon, 1 detectors on circles, 6 zone items "
                          "inside their own polygon, 5 command zones apart", log)
            self.assertIn("and 10 objectives (0 reviewed", log)                   # OBJECTIVE_ROWS_MAX
            self.assertIn("(6 dialog-button tokens in the game's INGAME dictionary)", log)
            self.assertIn("+ 2 admitted", log)                                     # Transporter, DeathCause
            packs = sorted(os.listdir(os.path.join(OUT, "OpenDoorTest", "Scenarios")))
            self.assertEqual(packs, [f"challenge_OpenDoorTest_{p}.dat" for p in ("Assets", "Definition", "Details")])
            with open(os.path.join(OUT, "OpenDoorTest", "Config.ini"), encoding="ascii") as fh:
                self.assertIn("OpenDoorTest", fh.read())
            dat = os.path.join(OUT, "OpenDoorTest", "Scenarios", "challenge_OpenDoorTest_Definition.dat")
            (entry,) = [e for e in edat.read_index(dat)
                        if e.path == def_path("MapConfiguration", TXN, "challenge_OpenDoorTest")]
            nb, _, _ = decode(edat.read_entry(dat, entry))
            tokens = {ndfbin.token_unhash(int.from_bytes(x.v, "little")) for _, _, x in all_values(nb)
                      if x.tag == 0x1D}
            self.assertLessEqual(set(spike2.MENU_TOKENS), tokens)
            self.assertFalse(tokens & set(profile.MENU_TOKENS))
            guids = [x.v for _, _, x in all_values(nb) if x.tag == 0x1A]
            self.assertEqual(guids, [scenario_guid(spike2.SCENARIO)])
        finally:
            remove_out(OUT)
        self.assertFalse(os.path.exists(OUT))


if __name__ == "__main__":
    unittest.main()
