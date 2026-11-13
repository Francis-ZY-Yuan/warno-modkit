"""Tests for Open Door's phases 1 to 4, by shape and through `Model`, a 1 s step model of the script runtime driven
by a `World` of zone and circle counts, captures, group sizes and dialog answers; `grade` is the catch's arithmetic
in plain Python."""
from __future__ import annotations

import re
import unittest
from collections import Counter

from modkit.core import ndfbin
from modkit.core.gates import CheckError
from modkit.ops import gates, shapes
from modkit.ops.bricks import g_cmp, g_modify, g_seq, g_set, g_simul, g_wait, unit_path
from modkit.ops.files import read_file
from modkit.ops.graph import TRUE, Node, decode, i32, walk
from modkit.ops.maps import GEISA
from modkit.ops.models import ForceRow, Knobs
from modkit.ops.profile import SURVIVORS
from modkit.ops.testing import (
    cmp_of, last, of, parent_of, prop, sets, subs, token,
)
from modkit.ops.zones import point_in_polygon
from open_door_support import (
    JOUEUR, PACT, SCRIPT_DATA, cmp_count, cmp_vars,
)
from opendoor import forces, profile
from opendoor import op as mission
from opendoor.map import MAP

px_of, radius_px, box_px = MAP.px_of, MAP.radius_px, MAP.box_px


class World:
    """What the model below reads of the battle, by second: per zone tag name, (Soviet, NATO) units inside from a
    second on; the same per circle tag name (`rings`: the Soviets there are vehicles, for the sack count); zone owners
    the battle changes (a capture); a unit group's count from a second on; the answer to each multiple-choice dialog in
    turn (HOLD FIRE once none is left), and how long one stays open (0: it pauses the game, so no time passes);
    how long a blocking order or a boarding takes (None: it never completes)."""

    def __init__(self, units: dict[str, list[tuple[int, int, int]]] | None = None,
                 captures: dict[int, dict[str, str]] | None = None,
                 groups: dict[str, list[tuple[int, int]]] | None = None,
                 kills: list[tuple[int, int]] | None = None,
                 rings: dict[str, list[tuple[int, int, int]]] | None = None,
                 answers: list[int] | None = None, dialog_s: int = 0,
                 arrive_s: int | None = None, board_s: int | None = None) -> None:
        self.zones, self.captures, self.groups = units or {}, captures or {}, groups or {}
        self.kill_steps = kills or []                 # the player's kills of the listed types, from a second on
        self.rings, self.answers, self.dialog_s = rings or {}, list(answers or []), dialog_s
        self.arrive_s, self.board_s = arrive_s, board_s

    def kills(self, t: int) -> int:
        return next((n for t0, n in reversed(self.kill_steps) if t0 <= t), 0)

    @staticmethod
    def _at(steps: list[tuple[int, int, int]], t: int) -> dict[str, int]:
        pact, nato = next(((p, n) for t0, p, n in reversed(steps) if t0 <= t), (0, 0))
        return {profile.CAMPS["PACT"]: pact, profile.CAMPS["NATO"]: nato}

    def units(self, zone: str, t: int) -> dict[str, int]:
        return self._at(self.zones.get(zone, []), t)

    def detected(self, ring: str, t: int) -> dict[str, int]:
        return self._at(self.rings.get(ring, []), t)

    def group(self, name: str, t: int) -> int:
        return next((n for t0, n in reversed(self.groups.get(name, [])) if t0 <= t), 0)


class Model:
    """A 1 s step model of the script runtime for the nodes phases 1 and 2 use, to check what their beats do in time
    ([[script-container-semantics]]: a Sequential runs its children in turn, a Simultaneous all of them until all
    finish, a Competition until its first finishes). One tick is one second; a node that finishes at once takes no tick.
    Owners start NATO's; a forcing or a World capture changes them. Objectives resolve on the first tick their Condition
    (first) or ConditionEchec holds, then run that action. Instant actions (creates, hints, dialogs, group counts,
    removals) are logged; ModifieVariableInteger does Set, Add, Substract and Divide (integer, truncated), the forms
    stock uses. GetNbKillsCamp reads World.kills, whatever its type list (test_b1 pins the list). A group the script
    fills (ClearUnitGroup, AddDetectedUnitsToUnitGroup: the circle's Soviets, whatever the constraint; test_sack pins
    it) counts what it was given; any other group reads World.group. A multiple-choice dialog takes World.dialog_s, then
    writes World's next answer to its SelectedButton; a blocking order or boarding takes World.arrive_s or board_s."""

    def __init__(self, world: World, values: dict[str, int] | None = None) -> None:
        self.world, self.t, self.vars, self.owner, self.log = world, 0, dict(values or {}), {}, []
        self.groups: dict[str, int] = {}

    def value(self, v: Node) -> int:
        if v.cls in gates.UNIT_GROUPS:
            return self.groups[last(v)] if last(v) in self.groups else self.world.group(last(v), self.t)
        return self.vars.get(last(v), 0)

    @staticmethod
    def camp_of(contrainte: Node) -> str:
        (team,) = [k for k in walk([contrainte]) if k.cls == "TGDContrainteOnUnitTeam"]
        return last(prop(team, "Camp"))

    def wait(self, seconds: int | None):
        """A blocking action that takes `seconds` (None: forever, until its race or the run ends)."""
        k = 0
        while seconds is None or k < seconds:
            k += 1
            yield

    def compare(self, left: int, op: Node) -> bool:
        other, value, kind = prop(op, "Variable"), prop(op, "Value"), prop(op, "OperatorType")
        right = self.value(other) if other is not None else value.v if value is not None else 0
        return gates.INT_OPERATORS[kind.v if kind is not None else 0](left, right)

    def cond(self, c: Node) -> bool:
        if c.cls == "TGDConditionAnd":
            return all(self.cond(k) for k in prop(c, "SousConditions"))
        if c.cls == "TGDConditionOr":
            return any(self.cond(k) for k in prop(c, "SousConditions"))
        if c.cls == "TGDConditionVariable":
            return self.compare(self.value(prop(c, "Variable")), prop(c, "Operator"))
        if c.cls == "TGDConditionTeamControleZone":
            return self.owner.get(last(prop(c, "Position")), profile.CAMPS["NATO"]) == last(prop(c, "Camp"))
        if c.cls == "TGDConditionUnitDansZone":
            camp = last(prop(prop(c, "Contrainte"), "Camp"))
            inside = sum(self.world.units(last(z), self.t)[camp] for z in prop(c, "Detecteurs"))
            return self.compare(inside, prop(c, "ComparaisonNbUnits"))
        if c.cls == "TGDConditionDetectUnitDansDetecteur":
            inside = self.world.detected(last(prop(c, "Detecteur")), self.t)[self.camp_of(prop(c, "Contrainte"))]
            return self.compare(inside, prop(c, "ComparaisonNbUnits"))
        raise AssertionError(f"the model has no {c.cls}")

    def note(self, *what: object) -> None:
        self.log.append((self.t, *what))

    @staticmethod
    def step(g) -> bool:
        try:
            next(g)
            return True
        except StopIteration:
            return False

    def run(self, n: Node):
        cls = n.cls.removeprefix("TGDDescriptor")
        if cls == "Sequential":
            for _ in range(prop(n, "NbExecutions").v):
                for kid in subs(n):
                    yield from self.run(kid)
        elif cls in ("Simultaneous", "Competition"):
            gens = [self.run(k) for k in subs(n)]
            while gens:
                left = [g for g in gens if self.step(g)]
                if cls == "Competition" and len(left) < len(gens):
                    for g in left:
                        g.close()
                    return
                gens = left
                if gens:
                    yield
        elif cls == "WaitDuration":
            for _ in range(round(prop(n, "Duree").v)):
                yield
        elif cls == "WaitCondition":
            while not self.cond(prop(n, "Condition")):
                yield
        elif cls == "IfThenElse":
            branch = prop(n, "EffetIfTrue" if self.cond(prop(n, "Condition")) else "EffetIfFalse")
            if branch is not None:
                yield from self.run(branch)
        elif cls == "ModifieVariableInteger":
            name, other, value, kind = (prop(n, k) for k in ("Variable1", "Variable2", "Value", "ModificationType"))
            v = self.value(other) if other is not None else value.v if value is not None else 0
            old = self.vars.get(last(name), 0)
            ops = {None: lambda: v, 1: lambda: old + v, 2: lambda: old - v,
                   4: lambda: int(old / v)}                    # Divide: C++ integer division (truncation)
            self.vars[last(name)] = ops[kind.v if kind is not None else None]()
        elif cls == "SetVariableIntegerFromUnitGroup":
            self.vars[last(prop(n, "Variable"))] = self.value(prop(n, "Group"))
            self.note("count", last(prop(n, "Variable")), self.vars[last(prop(n, "Variable"))])
        elif cls == "KillAllUnit":
            self.note("vanish", [last(g) for g in prop(n, "GroupList")])
        elif cls == "ClearUnitGroup":
            self.groups[last(prop(n, "Group"))] = 0
        elif cls == "AddDetectedUnitsToUnitGroup":
            detector, name = prop(n, "Detector"), last(prop(n, "Group"))
            found = self.world.detected(last(prop(detector, "Detecteur")), self.t)
            self.groups[name] = self.groups.get(name, 0) + found[self.camp_of(prop(detector, "Contrainte"))]
        elif cls == "EncapsuleCutsceneDialogListWithMultipleChoice":
            (text,) = [k for k in walk([n]) if k.cls == "TGDDescriptorCutsceneTextComponent"]
            (dialog,) = prop(n, "DialogList")
            self.note("ask", token(prop(text, "LocalizedText")))
            yield from self.wait(self.world.dialog_s)
            answer = self.world.answers.pop(0) if self.world.answers else mission.SPRING_WAIT
            self.vars[last(prop(dialog, "SelectedButton"))] = answer
            self.note("answer", answer)
        elif cls == "GiveOrderStandard":
            blocking = prop(n, "Blocking") is not None
            self.note("order", last(prop(n, "Group")), last(prop(n, "Position")), blocking)
            if blocking:
                yield from self.wait(self.world.arrive_s)
        elif cls == "LoadIntoTransporter":
            self.note("board", last(prop(n, "Group")), last(prop(n, "Targets")))
            yield from self.wait(self.world.board_s)
        elif cls == "CreateUnitOnPosition":
            self.note("create", last(prop(n, "Group")), prop(n, "NbUnit").v)
        elif cls == "GetNbKillsCamp":
            self.vars[last(prop(n, "Variable"))] = self.world.kills(self.t)
        elif cls == "SetCommandZoneOwnerAndForceConvergence":
            zones = [last(z) for z in prop(n, "Positions")]
            self.owner |= dict.fromkeys(zones, last(prop(n, "Camp")))
            self.note("owner", last(prop(n, "Camp")), zones)
        elif cls == "LDHint":
            self.note("hint", token(prop(n, "Info")))
        elif cls == "EncapsuleCutscene":
            (text,) = [k for k in walk([n]) if k.cls == "TGDDescriptorCutsceneTextComponent"]
            self.note("dialog", token(prop(text, "LocalizedText")))
        elif cls == "GereObjectif":
            name, counters = token(prop(n, "ObjectiveText")), prop(n, "ListVariables") or []
            while True:
                for key, then, how in (("Condition", "ActionsReussi", "done"), ("ConditionEchec", "ActionsEchec",
                                                                                "failed")):
                    if prop(n, key) is not None and self.cond(prop(n, key)):
                        self.note(how, name, [self.value(v) for v in counters])
                        if prop(n, then) is not None:
                            yield from self.run(prop(n, then))
                        return
                yield
        else:
            self.note(cls)

    def play(self, root: Node, until: int) -> "Model":
        g = self.run(root)
        while self.t <= until:
            self.owner |= self.world.captures.get(self.t, {})
            if not self.step(g):
                break
            self.t += 1
        return self

    def when(self, *what: object) -> list[int]:
        return [e[0] for e in self.log if e[1:1 + len(what)] == what]


@SCRIPT_DATA
class Phase1(unittest.TestCase):
    """Phase 1: the first echelon, the captured T-80U, PL BLUE's fall, P1 and B1 (design 4.1)."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        cls.roots, cls.exports = mission.script(cls.tpl)
        cls.nodes = list(walk(cls.roots))

    def beat(self, check: str, ctx: mission.Ctx | None = None) -> tuple[mission.Ctx, Node]:
        (b,) = [b for b in mission.BEATS if b.check == check]
        ctx = ctx or mission.Ctx()
        return ctx, b.build(ctx)

    def var(self, name: str) -> Node:
        (v,) = [n for n in self.exports if n.export == f"{profile.VARIABLES}/{name}"]
        return v

    def test_companies(self):
        """Design 6.3's first echelon: FE_COMPANIES sum to the first_echelon rows (36 at FORCE_SCALE), N 11, C 14
        with the BMP-1 command vehicle, S 11; B1's thresholds are 28/42/55 % of them (forces.threshold)."""
        companies, rows = mission.fe_tallies()
        self.assertEqual(companies, rows)
        self.assertEqual(rows, Counter({(r.unit, r.transport): r.count for r in
                                        forces.force_rows("first_echelon")}))
        self.assertEqual(mission.tally([ForceRow("A", 1), ForceRow("A", 2), ForceRow("A", 1, "B")]),
                         Counter({("A", None): 3, ("A", "B"): 1}))
        self.assertEqual(mission.FE_TOTAL, 36)
        self.assertEqual(mission.FE_TYPES, ("T80B_SOV", "BMP_2_SOV", "MotRifles_SOV", "BMP_1_CMD_SOV", "BRDM_2_SOV",
                                         "BRDM_2_Konkurs_SOV", "Scout_SOV", "ZSU_23_Shilka_SOV", "BRDM_Strela_1_SOV"))
        self.assertEqual([(c.key, sum(r.count for r in c.rows)) for c in mission.FE_COMPANIES],
                         [("n", 11), ("c", 14), ("s", 11)])
        self.assertEqual([c.key for c in mission.FE_COMPANIES if any(r.unit == "BMP_1_CMD_SOV" for r in c.rows)],
                         ["c"])
        for c in mission.FE_COMPANIES:  # every company's riflemen have their carriers beside them
            with self.subTest(company=c.key):
                rows = {r.unit: r.count for r in c.rows}
                for r in c.rows:
                    if r.transport:
                        self.assertEqual(rows[r.transport], r.count)
        self.assertEqual(mission.KNOBS["od_b1_n"],
                         Knobs(*(forces.threshold("B1", d, forces.force_rows("first_echelon"))
                                 for d in ("easy", "medium", "hard"))))
        self.assertEqual(mission.KNOBS["od_b1_n"], Knobs(10, 15, 20))

    def test_first_echelon(self):
        """H+1:00: each row created (PACT) at its company's entry, riflemen and carriers in groups of their own that
        join the company; then per company, side by side, the boarding raced against 30 s and the Seize of its town,
        last. No union of the companies (B1 counts kills by type)."""
        self.assertEqual((mission.FE_T, mission.BOARD_S), (60.0, 30.0))
        ctx, seq = self.beat("first_echelon")
        *made, attacks = subs(seq)
        creates = [n for n in made if n.cls == "TGDDescriptorCreateUnitOnPosition"]
        want = [(f"od_fe_{c.key}" + ("_inf" if r.transport else "_ifv" if r.unit == "BMP_2_SOV" else ""), r.count,
                 c.entry, unit_path(r.unit), PACT) for c in mission.FE_COMPANIES for r in c.rows]
        self.assertEqual([(last(prop(c, "Group")), prop(c, "NbUnit").v, last(prop(c, "Position")),
                           prop(c, "TypeUnit").path, prop(c, "Camp").export) for c in creates], want)
        joins = [n for n in made if n.cls == "TGDDescriptorAddUnitGroupListToUnitGroup"]
        self.assertEqual([(last(prop(j, "GroupDestination")), [last(g) for g in prop(j, "ListGroupSource")])
                          for j in joins],
                         [(f"od_fe_{c.key}", [f"od_fe_{c.key}_inf", f"od_fe_{c.key}_ifv"])
                          for c in mission.FE_COMPANIES])
        self.assertEqual(len(made), len(creates) + len(joins))
        self.assertEqual(attacks.cls, "TGDDescriptorSimultaneous")
        for c, attack in zip(mission.FE_COMPANIES, subs(attacks)):
            with self.subTest(company=c.key):
                race, seize = subs(attack)
                boarding, timeout = subs(race)
                (load,) = subs(boarding)
                self.assertEqual((race.cls, timeout.cls, prop(timeout, "Duree").v), ("TGDDescriptorCompetition",
                                                                                     "TGDDescriptorWaitDuration", 30.0))
                self.assertEqual([(k, v.v if isinstance(v, ndfbin.Value) else last(v)) for k, v in load.props],
                                 [("Blocking", True), ("Group", f"od_fe_{c.key}_inf"),
                                  ("Targets", f"od_fe_{c.key}_ifv")])
                self.assertEqual([(k, v.v if isinstance(v, ndfbin.Value) else last(v)) for k, v in seize.props],
                                 [("Position", c.town), ("SmartOrderType", 1), ("UnitGroup", f"od_fe_{c.key}")])

    def test_first_echelon_gets_no_later_order(self):
        """In the whole script, the only orders naming a first-echelon group are the three Seizes; nothing routes them
        west (the rear exit counts BMP-2s), and no group holds theirs. The new gate passes the
        op; a route west after the beat, on a company or on a union of it, fails."""
        groups = {f"od_fe{s}" for c in mission.FE_COMPANIES for s in (f"_{c.key}", f"_{c.key}_inf", f"_{c.key}_ifv")}
        named = [(n.cls.removeprefix("TGDDescriptor"), last(prop(n, gates.ORDER_GROUPS[n.cls]))) for n in self.nodes
                 if n.cls in gates.ORDER_GROUPS and last(prop(n, gates.ORDER_GROUPS[n.cls])) in groups]
        self.assertEqual(named, [("LaunchSmartOrder", f"od_fe_{c.key}") for c in mission.FE_COMPANIES])
        self.assertEqual(sorted({last(prop(n, "GroupDestination")) for n in of(self.nodes, "AddUnitGroupList")}),
                         sorted(["Groupe_Joueur", *(f"od_fe_{c.key}" for c in mission.FE_COMPANIES),
                                 "od_mb", "od_mb_inf", "od_mb3"]))                 # phase 2's main body
        holders = {(last(prop(n, "GroupDestination")), last(g)) for n in of(self.nodes, "AddUnitGroupList")
                   for g in prop(n, "ListGroupSource") if last(g) in groups}
        self.assertEqual(holders, {(f"od_fe_{c.key}", f"od_fe_{c.key}{s}") for c in mission.FE_COMPANIES
                                   for s in ("_inf", "_ifv")})                       # only their own company's
        self.assertEqual(gates.check_smart_orders(self.roots), 3)
        ctx, seq = self.beat("first_echelon")

        def west(group: Node) -> Node:
            return Node("TGDDescriptorGiveOrderStandard", [("Group", group), ("OrderType", i32(12)),
                                                                ("Position", ctx.tag("OD_RearExit"))])

        with self.assertRaisesRegex(CheckError, r"GiveOrderStandard\(od_fe_n\) comes after "
                                                     r"LaunchSmartOrder\(od_fe_n\)"):
            gates.check_smart_orders([g_seq([seq, west(ctx.group("od_fe_n"))])])
        union = ctx.group("od_x")
        with self.assertRaisesRegex(CheckError, r"GiveOrderStandard\(od_x\) comes after LaunchSmartOrder"):
            gates.check_smart_orders([g_seq([seq, mission.g_union(union, [ctx.group("od_fe_c")]), west(union)])])

    def test_captured(self):
        """H+0:30: SpawnUnits(OD_Captured), then it joins Groupe_Joueur (Survivors #1330-#1331), then the hint
        od_hcapt; no SetAmmo or SetFuel."""
        self.assertEqual(mission.CAPTURED_T, 30.0)
        ctx, seq = self.beat("captured")
        spawn, join, hint = subs(seq)
        self.assertEqual([last(u) for u in prop(spawn, "Units")], ["OD_Captured"])
        self.assertEqual((last(prop(join, "GroupDestination")), [last(g) for g in prop(join, "ListGroupSource")]),
                         ("Groupe_Joueur", ["OD_Captured"]))
        self.assertEqual(token(prop(subs(hint)[0], "Info")), "od_hcapt")
        self.assertEqual(of(self.nodes, "SetAmmo") + of(self.nodes, "SetFuel"), [])

    def test_p1(self):
        """P1 at H+0:00 beside the phase hint: od_p1_min = 12, one a minute off it; pinned on Village E's zone, shows
        the minutes left; done on od_plblue; failed on od_released without it once the counter reads 0 (the row
        freezes on 0 whichever H+12 clock ticks first), with the dialog od_dheld_f (od_dheld when tiered)."""
        self.assertEqual((mission.P1_DEADLINE_S, mission.P1_MINUTES), (720.0, 12))
        ctx, root = self.beat("p1")
        hint, seq = subs(root)
        self.assertEqual(token(prop(hint, "Info")), "od_hph1")
        start, both = subs(seq)
        self.assertEqual(sets([start], ctx.int_var("od_p1_min")), [12])
        countdown, obj = subs(both)
        self.assertEqual(prop(countdown, "NbExecutions").v, 12)
        wait, tick = subs(countdown)
        self.assertEqual((prop(wait, "Duree").v, last(prop(tick, "Variable1")), prop(tick, "ModificationType").v,
                          prop(tick, "Value").v), (60.0, "od_p1_min", 2, 1))
        self.assertEqual((token(prop(obj, "ObjectiveText")), last(prop(obj, "Position")), prop(obj, "ShowEtiquette"),
                          [last(v) for v in prop(obj, "ListVariables")]), ("od_p1", "OD_CZ_VillageE", TRUE,
                                                                           ["od_p1_min"]))
        self.assertEqual(cmp_of(prop(obj, "Condition")), ("od_plblue", 0, 1))
        fail = prop(obj, "ConditionEchec")
        self.assertEqual((fail.cls, [cmp_of(c) for c in prop(fail, "SousConditions")]),
                         ("TGDConditionAnd", [("od_released", 0, 1), ("od_plblue", 0, 0), ("od_p1_min", 0, 0)]))
        for mode, want in (("fixed", "od_dheld_f"), ("tiered", "od_dheld")):
            with self.subTest(mode=mode):
                _, root = self.beat("p1", mission.Ctx(mode))
                (dialog,) = [n for n in walk([root]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
                self.assertEqual(token(prop(dialog, "LocalizedText")), want)
        (dialog,) = subs(prop(obj, "ActionsEchec"))
        self.assertEqual(dialog.cls, "TGDDescriptorEncapsuleCutscene")

    def test_b1(self):
        """B1 at H+0:00: bonus, "%1 / %2" = kills and od_b1_n; Condition kills >= od_b1_n (HoldUntilRelieved #267's
        variable-against-variable shape); its window, od_released = 1, is its ConditionEchec. Kills are the player's
        kills of the first-echelon types (GetNbKillsCamp(joueur, FE_TYPES), probe 2's counter: Dieburg
        #332's Camp, TypeUnitList, Variable), polled every second from H+0:00 until the release, the poll's one write;
        no group count, so riflemen riding in their BMP-2s cannot read as kills."""
        ctx, root = self.beat("b1")
        feed, bonus = subs(root)
        self.assertEqual((prop(bonus, "LabelComponent").text, [last(v) for v in prop(bonus, "ListVariables")],
                          prop(bonus, "Position")), ("Bonus", ["od_b1_k", "od_b1_n"], None))
        cond = prop(bonus, "Condition")
        self.assertEqual((last(prop(cond, "Variable")), prop(prop(cond, "Operator"), "OperatorType").v,
                          last(prop(prop(cond, "Operator"), "Variable"))), ("od_b1_k", 2, "od_b1_n"))
        self.assertEqual(cmp_of(prop(bonus, "ConditionEchec")), ("od_released", 0, 1))
        (race,) = subs(feed)
        poll, stop = subs(race)
        self.assertEqual((race.cls, prop(poll, "NbExecutions").v, cmp_of(prop(stop, "Condition"))),
                         ("TGDDescriptorCompetition", shapes.FOREVER, ("od_released", 0, 1)))
        kills, wait = subs(poll)
        self.assertEqual([k for k, _ in kills.props], ["Camp", "TypeUnitList", "Variable"])
        self.assertEqual((kills.cls, prop(kills, "Camp").export, [i.path for i in prop(kills, "TypeUnitList")],
                          last(prop(kills, "Variable")), prop(wait, "Duree").v),
                         ("TGDDescriptorGetNbKillsCamp", JOUEUR, [unit_path(u) for u in mission.FE_TYPES], "od_b1_k",
                          1.0))
        self.assertEqual(set(mission.FE_TYPES), {r.unit for r in forces.force_rows("first_echelon")})
        writers = [n for n in self.nodes if any(v is self.var("od_b1_k") for k, v in n.props
                                                if k in ("Variable", "Variable1"))
                   and n.cls.startswith("TGDDescriptor")]
        self.assertEqual([n.cls for n in writers], ["TGDDescriptorGetNbKillsCamp"])
        self.assertEqual(sorted((last(prop(n, "Group")), last(prop(n, "Variable"))) for n in self.nodes
                                if n.cls == "TGDDescriptorSetVariableIntegerFromUnitGroup"),
                         sorted([("od_sackg", "od_sack"),                         # phase 2's sack; the pocket:
                                 ("od_pocketg", "od_sealed_n"), ("od_pocketg", "od_pocket"),
                                 ("od_mb", "od_alive"), ("od_pocketg", "od_captured")]))

    def test_pl_blue(self):
        """Per town, Competition[PACT controls it, Sequential[its race: PACT >= 3, NATO none, 20 s], od_released];
        then, unless released, its flag and tier_handover(PACT, the town) with no hint (the hints take turns in
        town_hints, beside them). The release: Competition[the three flags then od_plblue = 1, H+12],
        od_released = 1, then the door hint once all three towns are said and HINT_S more, or H+12's forcing of all
        three with no hint (P1's dialog announces it)."""
        self.assertEqual((mission.TOWN_PACT_N, mission.TOWN_HOLD_S), (3, 20.0))
        ctx, root = self.beat("pl_blue")
        *towns, hints, release = subs(root)
        self.assertEqual(len(towns), 3)
        self.assertEqual([n.cls for n in walk([hints]) if n.cls == "TGDDescriptorLDHint"],
                         ["TGDDescriptorLDHint"] * 3)                       # town_hints (test_town_hints)
        self.assertEqual([n for n in walk(towns) if n.cls == "TGDDescriptorLDHint"], [])
        for (cz, key), town in zip(mission.TOWN_KEYS.items(), towns):
            with self.subTest(town=cz):
                falls, then = subs(town)
                control, wrapped, done = subs(falls)
                self.assertEqual((last(prop(prop(control, "Condition"), "Position")),
                                  prop(prop(control, "Condition"), "Camp").export), (cz, PACT))
                (race,) = subs(wrapped)
                loop, held = subs(race)
                self.assertEqual(cmp_of(prop(held, "Condition")), (f"od_town_{key}_held", 2, 20))
                start = prop(subs(loop)[0], "Condition")
                self.assertEqual([([last(z) for z in prop(c, "Detecteurs")], prop(prop(c, "Contrainte"), "Camp").export,
                                   cmp_count(prop(c, "ComparaisonNbUnits"))) for c in prop(start, "SousConditions")],
                                 [([cz], PACT, (2, 3)), ([cz], JOUEUR, (3, 0))])   # PACT >= 3, NATO <= 0
                self.assertEqual(cmp_of(prop(done, "Condition")), ("od_released", 0, 1))
                self.assertEqual(cmp_of(prop(then, "Condition")), ("od_released", 0, 0))
                flag, handover = subs(prop(then, "EffetIfTrue"))
                self.assertEqual(sets([flag], ctx.int_var(f"od_town_{key}")), [1])
                (owner,) = subs(handover)
                self.assertEqual((owner.cls, prop(owner, "Camp").export, [last(z) for z in prop(owner, "Positions")]),
                                 (gates.ZONE_OWNER, PACT, [cz]))
        race, released, door = subs(release)
        fell, deadline = subs(race)
        wait, plblue = subs(fell)
        self.assertEqual([cmp_of(c) for c in prop(prop(wait, "Condition"), "SousConditions")],
                         [(f"od_town_{k}", 0, 1) for k in ("ne", "ve", "se")])
        self.assertEqual((sets([plblue], ctx.int_var("od_plblue")), prop(deadline, "Duree").v,
                          sets([released], ctx.int_var("od_released"))), ([1], 720.0, [1]))
        self.assertEqual(cmp_of(prop(door, "Condition")), ("od_plblue", 0, 1))
        said, gap, hint = subs(prop(door, "EffetIfTrue"))                # HINT_S after the last town's hint
        self.assertEqual([cmp_of(c) for c in prop(prop(said, "Condition"), "SousConditions")],
                         [(f"od_said_{k}", 0, 1) for k in ("ne", "ve", "se")])
        self.assertEqual((prop(gap, "Duree").v, token(prop(subs(hint)[0], "Info"))), (mission.HINT_S, "od_hopen"))
        (owner,) = subs(prop(door, "EffetIfFalse"))
        self.assertEqual((owner.cls, prop(owner, "Camp").export, [last(z) for z in prop(owner, "Positions")]),
                         ("TGDDescriptorSetCommandZoneOwnerAndForceConvergence", PACT, list(mission.TOWN_CZ)))
        _, fixed = self.beat("pl_blue", mission.Ctx("fixed"))  # "fixed" mode's hints say only the zone turned red
        tokens = [token(prop(n, "Info")) for n in walk([fixed]) if n.cls == "TGDDescriptorLDHint"]
        self.assertEqual(sorted(tokens), ["od_hfne_f", "od_hfse_f", "od_hfve_f", "od_hopen"])

    def test_town_hints(self):
        """town_hints: Sequential[Competition[Sequential(NbExecutions = 3)[WaitCondition(Or over
        NE, VE, SE of And[od_town_<key> = 1, od_said_<key> = 0]), the IfThenElse chain taking the first such town (SE
        the last else): od_said_<key> = 1, then its hint beside a HINT_S wait], WaitCondition(od_released = 1 and
        od_plblue = 0: H+12)]]. Each od_said_<key> is written there once; "fixed" mode says the _f twins."""
        ctx, root = self.beat("pl_blue")
        hints = subs(root)[3]
        (race,) = subs(hints)
        rounds, cut = subs(race)
        self.assertEqual((hints.cls, race.cls, rounds.cls, prop(rounds, "NbExecutions").v),
                         ("TGDDescriptorSequential", "TGDDescriptorCompetition", "TGDDescriptorSequential", 3))
        self.assertEqual([cmp_of(c) for c in prop(prop(cut, "Condition"), "SousConditions")],
                         [("od_released", 0, 1), ("od_plblue", 0, 0)])
        keys = ["ne", "ve", "se"]

        def pending(key: str) -> list[tuple[str, int, int]]:
            return [(f"od_town_{key}", 0, 1), (f"od_said_{key}", 0, 0)]

        wait, pick = subs(rounds)
        self.assertEqual([[cmp_of(c) for c in prop(a, "SousConditions")]
                          for a in prop(prop(wait, "Condition"), "SousConditions")], [pending(k) for k in keys])
        chain, node = [], pick
        while node.cls == "TGDDescriptorIfThenElse":
            chain.append(([cmp_of(c) for c in prop(prop(node, "Condition"), "SousConditions")],
                          prop(node, "EffetIfTrue")))
            node = prop(node, "EffetIfFalse")
        chain.append((None, node))
        self.assertEqual([c for c, _ in chain], [pending("ne"), pending("ve"), None])
        for key, (_, say) in zip(keys, chain):
            with self.subTest(town=key):
                flag, both = subs(say)
                hint, gap = subs(both)
                self.assertEqual((sets([flag], ctx.int_var(f"od_said_{key}")), both.cls, token(prop(hint, "Info")),
                                  prop(hint, "Time").v, prop(gap, "Duree").v),
                                 ([1], "TGDDescriptorSimultaneous", f"od_hf{key}", mission.HINT_S, mission.HINT_S))
        writes = [last(prop(n, "Variable1")) for n in self.nodes if n.cls == "TGDDescriptorModifieVariableInteger"
                  and last(prop(n, "Variable1")).startswith("od_said_")]
        self.assertEqual(sorted(writes), ["od_said_ne", "od_said_se", "od_said_ve"])
        _, fixed = self.beat("pl_blue", mission.Ctx("fixed"))
        said = [token(prop(n, "Info")) for n in walk([subs(fixed)[3]]) if n.cls == "TGDDescriptorLDHint"]
        self.assertEqual(said, ["od_hfne_f", "od_hfve_f", "od_hfse_f"])

    def phase1(self, world: World, until: int = 800, values: dict[str, int] | None = None,
               release_first: bool = False, green: bool = False) -> Model:
        """The model run of P1, B1 and PL BLUE from H+0:00, side by side as in the battle Simultaneous, with od_b1_n
        at Medium (15). `release_first` steps PL BLUE before P1 and P1's objective before its countdown in each tick:
        the release lands, and the objective looks, before the countdown's 12th step (the order that would freeze the
        row on "1 min left" if the failure read od_released alone). `green` adds phase 2's PL GREEN beat (od_b6_s at
        Medium), whose phase hint follows the release."""
        ctx = mission.Ctx()
        beats = [mission.p1(ctx), mission.b1(ctx), mission.pl_blue(ctx), *([mission.pl_green(ctx)] if green else [])]
        if release_first:
            inner = subs(subs(subs(beats[0])[1])[1])   # beat_hint > Sequential > Simultaneous[countdown, P1]
            inner.reverse()
        root = g_simul(beats[::-1] if release_first else beats)
        knobs = {"od_b1_n": 15, **({"od_b6_s": 120} if green else {})}
        return Model(world, {**knobs, **(values or {})}).play(root, until)

    def assert_one_at_a_time(self, m: Model) -> None:
        hints = [(e[0], e[2]) for e in m.log if e[1] == "hint"]
        for (t0, a), (t1, b) in zip(hints, hints[1:]):
            self.assertGreaterEqual(t1 - t0, mission.HINT_S, (a, b, hints))

    def test_model_towns_fall_together(self):
        """Towns that fall in one second show their hints one at a time, HINT_S apart in TOWN_CZ
        order, each town once, and each town's zone goes to PACT once, at its fall; od_hopen comes HINT_S after the last
        town's hint, and PL GREEN's phase hint (B6_HINT_T after the release) after od_hopen's 15 s. Two at once: Village
        E taken at 2:30 (its hint then), Town NE and Town SE held by their races from 6:40; three at once: all three
        taken at 5:00. Either way PL BLUE is released once, in that second."""
        pact = profile.CAMPS["PACT"]
        cases = {
            "two": World(units={"OD_CZ_TownNE": [(400, 4, 0)], "OD_CZ_TownSE": [(400, 3, 0)]},
                         captures={150: {"OD_CZ_VillageE": pact}}),
            "three": World(captures={300: dict.fromkeys(mission.TOWN_CZ, pact)}),
        }
        for name, world in cases.items():
            with self.subTest(case=name):
                m = self.phase1(world, until=700, green=True)                  # before PL GREEN's window closes
                owners = [(e[0], e[3]) for e in m.log if e[1] == "owner"]
                self.assertEqual(sorted(z for _, (z,) in owners), sorted(mission.TOWN_CZ))       # each once, no forcing
                t = max(t for t, _ in owners)                                                  # the last fall
                together = [z for t0, (z,) in owners if t0 == t]
                self.assertEqual(len(together), {"two": 2, "three": 3}[name])
                if name == "two":
                    self.assertLessEqual(abs(t - 420), 2)
                hints = [(e[0], e[2]) for e in m.log if e[1] == "hint"]
                late = [(t + k * int(mission.HINT_S), f"od_hf{mission.TOWN_KEYS[z]}") for k, z in enumerate(together)]
                early = [(150, "od_hfve")] if name == "two" else []
                n = len(together)
                self.assertEqual(hints, [(0, "od_hph1"), *early, *late,
                                         (t + n * int(mission.HINT_S), "od_hopen"),
                                         (t + int(mission.B6_HINT_T), "od_hph2")])
                self.assert_one_at_a_time(m)
                self.assertEqual([m.vars[f"od_said_{k}"] for k in mission.TOWN_KEYS.values()], [1, 1, 1])
                self.assertEqual((m.vars["od_plblue"], m.vars["od_released"]), (1, 1))
                self.assertEqual([e[1:3] for e in m.log if e[1] in ("done", "failed")][:1], [("done", "od_p1")])

    def test_model_town_falls_just_before_h12(self):
        """Town NE falls at 11:40 and Village E at 11:50, Town SE held: NE's hint at 11:40, VE's waits its turn to
        11:55; at H+12 the forcing shows no hint, and the sequencer stops. Falls at 11:50 and 11:55 instead: VE's
        hint at 11:50, NE's would wait to 12:05, after H+12, and is dropped: H+12 shows P1's dialog and at most the
        one hint already showing."""
        pact = profile.CAMPS["PACT"]
        held = {"OD_CZ_TownSE": [(0, 0, 1)]}
        m = self.phase1(World(units=held, captures={700: {"OD_CZ_TownNE": pact}, 710: {"OD_CZ_VillageE": pact}}))
        self.assertEqual([(e[0], e[2]) for e in m.log if e[1] == "hint"],
                         [(0, "od_hph1"), (700, "od_hfne"), (715, "od_hfve")])
        self.assertEqual([e[2] for e in m.log if e[1] == "dialog"], ["od_dheld"])
        m = self.phase1(World(units=held, captures={710: {"OD_CZ_VillageE": pact}, 715: {"OD_CZ_TownNE": pact}}))
        self.assertEqual([(e[0], e[2]) for e in m.log if e[1] == "hint"], [(0, "od_hph1"), (710, "od_hfve")])
        self.assertEqual((m.vars["od_said_ve"], m.vars.get("od_said_ne", 0), m.vars["od_town_ne"]), (1, 0, 1))
        self.assertEqual([e[2] for e in m.log if e[1] == "dialog"], ["od_dheld"])
        self.assertEqual([e[3] for e in m.log if e[1] == "owner"],
                         [["OD_CZ_VillageE"], ["OD_CZ_TownNE"], list(mission.TOWN_CZ)])

    def test_model_all_held_stalls_nothing(self):
        """A NATO unit parked in each town: none falls, no town hint shows, and at H+12 the forcing hands all three to
        PACT; the sequencer stops with the release, and the whole run (P1, B1, PL BLUE) ends at H+12 instead of
        waiting for a fall."""
        world = World(units=dict.fromkeys(mission.TOWN_CZ, [(0, 0, 1)]))
        m = self.phase1(world, until=900)
        self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph1"])
        self.assertEqual([(e[0], e[3]) for e in m.log if e[1] == "owner"], [(720, list(mission.TOWN_CZ))])
        self.assertLessEqual(m.t, 722)                    # the run's root finished: nothing waits on a town
        self.assertEqual(sum(m.vars.get(f"od_said_{k}", 0) for k in mission.TOWN_KEYS.values()), 0)

    def test_model_towns_fall_one_by_one(self):
        """Town NE by its race (4 Soviets, no NATO, from 3:20: held at 3:40), Village E by capture at 5:00, Town SE by
        its race from 6:40 (7:00): each town is forced to PACT, with its hint, as it falls; then PL BLUE is released
        once (od_plblue, then od_released), with the door hint 15 s after the last town's; P1 is done and B1, short of
        15 kills, fails; nothing is forced at H+12."""
        world = World(units={"OD_CZ_TownNE": [(200, 4, 0)], "OD_CZ_TownSE": [(400, 3, 0)]},
                      captures={300: {"OD_CZ_VillageE": profile.CAMPS["PACT"]}}, kills=[(200, 6)])
        m = self.phase1(world)
        owners = [(t, zones) for t, what, camp, zones in (e for e in m.log if e[1] == "owner")]
        self.assertEqual([z for _, z in owners], [["OD_CZ_TownNE"], ["OD_CZ_VillageE"], ["OD_CZ_TownSE"]])
        for (t, _), want in zip(owners, (220, 300, 420)):
            self.assertLessEqual(abs(t - want), 2, owners)
        self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph1", "od_hfne", "od_hfve", "od_hfse",
                                                                   "od_hopen"])
        self.assertEqual(m.when("hint", "od_hopen")[0] - m.when("hint", "od_hfse")[0], mission.HINT_S)  # one at a time
        self.assertEqual(m.vars["od_plblue"], 1)
        self.assertEqual(m.vars["od_released"], 1)
        self.assertEqual([e[1:3] for e in m.log if e[1] in ("done", "failed")], [("done", "od_p1"),
                                                                                 ("failed", "od_b1")])
        (b1,) = [e for e in m.log if e[1:3] == ("failed", "od_b1")]
        self.assertEqual(b1[3], [6, 15])                    # frozen where the window closed
        self.assertEqual(m.when("dialog"), [])

    def test_model_h12_forces_the_rest(self):
        """A NATO unit parked in Town SE holds its race false: Town NE and Village E fall, then at H+12 PL BLUE is
        released anyway: the three towns are forced to PACT at once, with no hint, P1 fails with "0 min left" and the
        dialog od_dheld, H+12's one announcement, whichever of the two H+12 clocks (P1's countdown, the release) ticks
        first in the second; od_plblue stays 0, and Town SE's own
        branch ends quietly (no hint, no flag)."""
        for release_first in (False, True):
            with self.subTest(release_first=release_first):
                world = World(units={"OD_CZ_TownNE": [(200, 4, 0)], "OD_CZ_TownSE": [(0, 0, 1), (400, 5, 1)]},
                              captures={300: {"OD_CZ_VillageE": profile.CAMPS["PACT"]}})
                m = self.phase1(world, release_first=release_first)
                (forced,) = [e for e in m.log if e[1] == "owner" and len(e[3]) == 3]
                self.assertEqual((forced[0], forced[3]), (720, list(mission.TOWN_CZ)))
                self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph1", "od_hfne", "od_hfve"])
                self.assertEqual((m.vars.get("od_plblue", 0), m.vars["od_released"], m.vars.get("od_town_se", 0)),
                                 (0, 1, 0))
                (p1,) = [e for e in m.log if e[1:3] == ("failed", "od_p1")]
                self.assertEqual((p1[0] - 720 in (0, 1), p1[3]), (True, [0]))  # 0 min left
                self.assertEqual([e[2] for e in m.log if e[1] == "dialog"], ["od_dheld"])
                self.assertEqual(m.owner["OD_CZ_TownSE"], profile.CAMPS["PACT"])

    def test_model_race_breaks_and_restarts(self):
        """A streak that a NATO unit breaks starts again: 4 Soviets in Town NE from 1:40, a NATO unit inside from 1:55
        to 2:05, then gone: the town falls 20 s after 2:05, not at 2:00."""
        world = World(units={"OD_CZ_TownNE": [(100, 4, 0), (115, 4, 1), (125, 4, 0)]})
        m = self.phase1(world, until=200)
        (t,) = [e[0] for e in m.log if e[1] == "owner"]
        self.assertLessEqual(abs(t - 145), 2)

    def test_model_b1_completes_and_freezes(self):
        """B1 completes on the poll round that reads the 15th first-echelon kill (8:00), before the release, and its
        row keeps that round's numbers; kills before the first echelon arrives read 0; the countdown ends at 0."""
        world = World(units={"OD_CZ_TownSE": [(0, 0, 1)]}, kills=[(300, 11), (480, 15), (500, 17)])
        m = self.phase1(world)
        (b1,) = [e for e in m.log if e[1:3] == ("done", "od_b1")]
        self.assertLessEqual(abs(b1[0] - 480), 2)
        self.assertEqual(b1[3], [15, 15])
        self.assertEqual(m.when("failed", "od_b1"), [])
        (p1,) = [e for e in m.log if e[1:3] == ("failed", "od_p1")]
        self.assertEqual(p1[3], [0])

    def test_strings(self):
        """Phase 1's texts in both languages; P1 and B1 hold at most 2 numbers; every hint token has its "fixed"
        twin, and so has P1's dialog, which holds none."""
        loc, dialogs = mission.STRINGS["Scripting/Localization"], mission.STRINGS["Scripting/Dialog"]
        for tok in ("od_hph1", "od_p1", "od_p1l", "od_b1", "od_b1l", "od_hcapt", "od_hopen",
                    *(f"od_hf{k}{s}" for k in ("ne", "ve", "se") for s in ("", "_f"))):
            with self.subTest(token=tok):
                self.assertTrue(all(loc[tok].values()))
                self.assertLessEqual(len(set(re.findall(r"%\d", loc[tok].US))), 2)
        self.assertEqual(re.findall(r"%\d", loc["od_p1"].US), ["%1"])
        self.assertEqual(re.findall(r"%\d", loc["od_b1"].US), ["%1", "%2"])
        self.assertFalse({"od_h12", "od_h12_f"} & set(loc))
        for tok in ("od_dheld", "od_dheld_f"):
            self.assertTrue(all(dialogs[tok].values()))
            self.assertNotRegex("".join(dialogs[tok].values()), r"%\d")
        self.assertIn("reinforcements no longer arrive", dialogs["od_dheld"].US)
        self.assertNotIn("reinforcements", dialogs["od_dheld_f"].US)


@SCRIPT_DATA
class Phase2(unittest.TestCase):
    """Phase 2: the main body, the sack count, P4 and the spring (design 5.2), B6 and the PL GREEN window."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        cls.roots, cls.exports = mission.script(cls.tpl)
        cls.nodes = list(walk(cls.roots))

    def beat(self, check: str, ctx: mission.Ctx | None = None) -> tuple[mission.Ctx, Node]:
        (b,) = [b for b in mission.BEATS if b.check == check]
        ctx = ctx or mission.Ctx()
        return ctx, b.build(ctx)

    @staticmethod
    def released(ctx: mission.Ctx, at: int, sprung: int | None = None) -> Node:
        """A stand-in for PL BLUE (od_released = 1 at `at`) and, given `sprung`, for the spring (od_sprung = 1)."""
        out = [g_seq([g_wait(at), g_set(ctx.int_var("od_released"), 1)])]
        if sprung is not None:
            out.append(g_seq([g_wait(sprung), g_set(ctx.int_var("od_sprung"), 1)]))
        return g_simul(out)

    @staticmethod
    def kv(node: Node) -> list[tuple[str, object]]:
        """A node's properties, scalars by value and references by name."""
        return [(k, v.v if isinstance(v, ndfbin.Value) else last(v)) for k, v in node.props]

    # ----------------------------------------------------------------------- the main body

    def test_waves(self):
        """Six waves one a minute from the release, alternating MID and BOTTOM, with design 6.3's main body and
        Pocket_AD (the force table at FORCE_SCALE): 60 vehicles (MB_TOTAL) and 9 riflemen, who ride the BMP-2s
        of wave 3; every main-body vehicle type the rear exit counts is in a wave."""
        waves, rows = mission.mb_tallies()
        self.assertEqual(waves, rows)
        self.assertEqual(rows, Counter({(r.unit, r.transport): r.count for r in
                                        [*forces.force_rows("main_body"), *forces.force_rows("pocket_ad")]}))
        self.assertEqual((mission.MB_TOTAL, mission.MB_DISMOUNTS), (60, 9))
        self.assertEqual([(w.key, w.offset, w.lane) for w in mission.WAVES],
                         [(1, 0.0, "MID"), (2, 60.0, "BOTTOM"), (3, 120.0, "MID"), (4, 180.0, "BOTTOM"),
                          (5, 240.0, "MID"), (6, 300.0, "BOTTOM")])
        self.assertEqual([w.rows for w in mission.WAVES], [
            (ForceRow("T80BV_SOV", 10),),
            (ForceRow("T80BV_SOV", 10),),
            (ForceRow("BMP_2_SOV", 10), ForceRow("MotRifles_SOV", 9, "BMP_2_SOV"), ForceRow("BRDM_2_Konkurs_SOV", 3)),
            (ForceRow("T80BV_SOV", 10), ForceRow("T80BV_CMD_SOV", 1)),
            (ForceRow("Tunguska_2K22_SOV", 2), ForceRow("Osa_9K33M3_SOV", 2), ForceRow("MTLB_Strela10_SOV", 2),
             ForceRow("BMP_1_CMD_SOV", 1)),
            (ForceRow("2S3M_Akatsiya_SOV", 6), ForceRow("MTLB_supply_SOV", 3)),
        ])
        self.assertEqual(sum(r.count for w in mission.WAVES for r in w.rows if r.transport is None), mission.MB_TOTAL)
        main_vehicles = {r.unit for r in forces.force_rows("main_body") if r.transport is None}
        self.assertLessEqual(main_vehicles, {r.unit for w in mission.WAVES for r in w.rows if r.transport is None})

    def test_main_body(self):
        """Each wave, once released (od_released = 1) and from its offset: its rows created (PACT) at its lane's entry,
        riflemen and carriers in groups of their own; the vehicles join od_mb before the riflemen join the wave (so
        od_mb holds the 60 vehicles), the riflemen join od_mb_inf; the boarding raced against BOARD_S (wave 3 only);
        then the wave drives its lane, last."""
        self.assertEqual(mission.BOARD_S, 30.0)
        ctx, seq = self.beat("main_body")
        wait, waves = subs(seq)
        self.assertEqual(cmp_of(prop(wait, "Condition")), ("od_released", 0, 1))
        self.assertEqual(len(subs(waves)), 6)
        for w, node in zip(mission.WAVES, subs(waves)):
            with self.subTest(wave=w.key):
                kids = subs(node)
                if w.offset:
                    self.assertEqual((kids[0].cls, prop(kids[0], "Duree").v), ("TGDDescriptorWaitDuration", w.offset))
                    kids = kids[1:]
                *steps, route = kids
                self.assertEqual([last(prop(o, "Position")) for o in walk([route])
                                  if o.cls == "TGDDescriptorGiveOrderStandard"],
                                 [leg.to for leg in mission.LANES[w.lane].legs])
                self.assertTrue(all(last(prop(o, "Group")) == f"od_mb{w.key}" for o in walk([route])
                                    if o.cls == "TGDDescriptorGiveOrderStandard"))
                creates = [n for n in steps if n.cls == "TGDDescriptorCreateUnitOnPosition"]
                carriers = {r.transport for r in w.rows if r.transport}
                want = [(f"od_mb{w.key}" + ("_inf" if r.transport else "_ifv" if r.unit in carriers else ""), r.count,
                         mission.LANES[w.lane].entry, unit_path(r.unit), PACT) for r in w.rows]
                self.assertEqual([(last(prop(c, "Group")), prop(c, "NbUnit").v, last(prop(c, "Position")),
                                   prop(c, "TypeUnit").path, prop(c, "Camp").export) for c in creates], want)
                rest = steps[len(creates):]
                joins = [(last(prop(j, "GroupDestination")), [last(g) for g in prop(j, "ListGroupSource")])
                         for j in rest if j.cls == "TGDDescriptorAddUnitGroupListToUnitGroup"]
                if carriers:
                    self.assertEqual(joins, [("od_mb", [f"od_mb{w.key}", f"od_mb{w.key}_ifv"]),
                                             ("od_mb_inf", [f"od_mb{w.key}_inf"]),
                                             (f"od_mb{w.key}", [f"od_mb{w.key}_inf", f"od_mb{w.key}_ifv"])])
                    self.assertEqual(len(rest), 4)
                    race = rest[-1]
                    boarding, timeout = subs(race)
                    (load,) = subs(boarding)
                    self.assertEqual((race.cls, timeout.cls, prop(timeout, "Duree").v),
                                     ("TGDDescriptorCompetition", "TGDDescriptorWaitDuration", mission.BOARD_S))
                    self.assertEqual(self.kv(load), [("Blocking", True), ("Group", f"od_mb{w.key}_inf"),
                                                     ("Targets", f"od_mb{w.key}_ifv")])
                else:
                    self.assertEqual(joins, [("od_mb", [f"od_mb{w.key}"])])
                    self.assertEqual(len(rest), 1)

    def test_lane_route(self):
        """Probe 2's traffic beat: each leg but the last is Competition[WaitDuration its timeout,
        Sequential[GiveOrderStandard Blocking, FastMoveAndAttack (12), the waypoint's tag]]; the last, to the rear
        exit, a plain FastMoveAndAttack order. The only ordered groups are the first echelon's companies (their
        Seizes) and the six waves (their routes); no smart order names a wave (gate check_smart_orders: 3 groups)."""
        ctx = mission.Ctx()
        for lane, l in mission.LANES.items():
            with self.subTest(lane=lane):
                route = mission.lane_route(ctx, ctx.group("od_x"), lane)
                *legs, final = subs(route)
                self.assertEqual(len(legs), len(l.legs) - 1)
                for leg, race in zip(l.legs, legs):
                    timeout, wrapped = subs(race)
                    (order,) = subs(wrapped)
                    self.assertEqual((race.cls, prop(timeout, "Duree").v, wrapped.cls),
                                     ("TGDDescriptorCompetition", leg.timeout, "TGDDescriptorSequential"))
                    self.assertEqual(self.kv(order), [("Blocking", True), ("Group", "od_x"), ("OrderType", 12),
                                                      ("Position", leg.to)])
                    self.assertGreaterEqual(leg.timeout, mission.LEG_MIN_S)
                self.assertEqual(self.kv(final), [("Group", "od_x"), ("OrderType", 12), ("Position", "OD_RearExit")])
        self.assertEqual(gates.check_smart_orders(self.roots), 3)
        ordered = {last(prop(n, gates.ORDER_GROUPS[n.cls])) for n in self.nodes if n.cls in gates.ORDER_GROUPS}
        self.assertEqual(ordered, {*(f"od_fe_{c.key}" for c in mission.FE_COMPANIES),
                                   *(f"od_mb{w.key}" for w in mission.WAVES)})
        smart = {last(prop(n, "UnitGroup")) for n in self.nodes if n.cls == gates.SMART_ORDER}
        self.assertEqual(smart, {f"od_fe_{c.key}" for c in mission.FE_COMPANIES})

    def test_model_main_body(self):
        """The model: released at 1:40, each wave is created at its offset; when nothing ever arrives, each leg gives
        up at its timeout and the wave drives on (wave 1, MID: NECK MID at 1:40, SACK MID at 5:40, the anvil at 6:40,
        the rear exit at 9:10); wave 3's riflemen board until BOARD_S runs out, then it drives."""
        ctx = mission.Ctx()
        root = g_simul([self.released(ctx, 100), mission.main_body(ctx)])
        m = Model(World()).play(root, 1500)
        creates = [(e[0], e[2]) for e in m.log if e[1] == "create"]
        for w in mission.WAVES:
            with self.subTest(wave=w.key):
                self.assertEqual({t for t, g in creates if g.startswith(f"od_mb{w.key}")}, {100 + int(w.offset)})
                start = 100 + int(w.offset) + (int(mission.BOARD_S) if w.key == 3 else 0)
                times = [e[0] for e in m.log if e[1] == "order" and e[2] == f"od_mb{w.key}"]
                legs = mission.LANES[w.lane].legs
                self.assertEqual(times, [start + sum(int(leg.timeout) for leg in legs[:k]) for k in range(len(legs))])
        self.assertEqual([e[0] for e in m.log if e[1] == "board"], [220])
        self.assertEqual(sum(e[3] for e in m.log if e[1] == "create"), mission.MB_TOTAL + mission.MB_DISMOUNTS)

    # ----------------------------------------------------------------------- the sack, P4 and the spring

    def test_sack(self):
        """The sack count: forever, ClearUnitGroup(od_sackg), AddDetectedUnitsToUnitGroup on each SACK_RINGS circle
        with AllContrainte[Team PACT, NoContrainte[MotRifles_SOV, Scout_SOV]] (the Soviet rows' infantry types so far),
        od_sack = its count (the round's one write), WaitDuration 2."""
        loop = mission.sack(mission.Ctx())
        clear, *collects, count, wait = subs(loop)
        self.assertEqual((prop(loop, "NbExecutions").v, clear.cls, last(prop(clear, "Group"))),
                         (shapes.FOREVER, "TGDDescriptorClearUnitGroup", "od_sackg"))
        self.assertEqual([last(prop(prop(c, "Detector"), "Detecteur")) for c in collects], list(mission.SACK_RINGS))
        for c in collects:
            detector = prop(c, "Detector")
            self.assertEqual((last(prop(c, "Group")), prop(detector, "ComparaisonNbUnits")), ("od_sackg", None))
            team, none = prop(prop(detector, "Contrainte"), "ContrainteList")
            self.assertEqual((prop(detector, "Contrainte").cls, team.cls, prop(team, "Camp").export, none.cls),
                             ("TGDContrainteOnUnitAllContrainte", "TGDContrainteOnUnitTeam", PACT,
                              "TGDContrainteOnUnitNoContrainte"))
            self.assertEqual([prop(k, "TypeUnit").path for k in prop(none, "ContrainteList")],
                             [unit_path("MotRifles_SOV"), unit_path("Scout_SOV")])
        self.assertEqual((count.cls, last(prop(count, "Group")), last(prop(count, "Variable")), prop(wait, "Duree").v),
                         ("TGDDescriptorSetVariableIntegerFromUnitGroup", "od_sackg", "od_sack", 2.0))
        infantry = {r.unit for r in forces.ROWS
                    if r.camp == "PACT" and (r.transport or "Scout" in r.unit)}
        self.assertEqual(infantry, set(mission.SACK_INFANTRY))

    def test_p4(self):
        """P4: "%1 / %2" = od_sack and od_smin (15/20/24: 0.25/0.33/0.40 of MB_TOTAL), Condition od_sack >= od_smin
        (variable against variable), ActionsReussi od_p4 = 1, ConditionEchec od_sprung = 1 (sprung by Corps before
        S_min); a primary, no pin."""
        obj = mission.p4(mission.Ctx())
        self.assertEqual((token(prop(obj, "ObjectiveText")), prop(obj, "LabelComponent").text,
                          [last(v) for v in prop(obj, "ListVariables")], prop(obj, "Position")),
                         ("od_p4", "Primary", ["od_sack", "od_smin"], None))
        self.assertEqual(cmp_vars(prop(obj, "Condition")), ("od_sack", 2, "od_smin"))
        self.assertEqual(cmp_of(prop(obj, "ConditionEchec")), ("od_sprung", 0, 1))
        done = prop(obj, "ActionsReussi")
        self.assertEqual((done.cls, last(prop(done, "Variable1")), prop(done, "Value").v),
                         ("TGDDescriptorModifieVariableInteger", "od_p4", 1))
        self.assertEqual(mission.KNOBS["od_smin"],
                         Knobs(*(forces.share_count(s, mission.MB_TOTAL) for s in (0.25, 0.33, 0.40))))

    def test_spring(self):
        """Design 5.2's spring, probe 2's ask loop: pick = ans = CHOICE_NONE (the sentinel) before the race and before
        each ask; the dialog (FIRE AT WILL / HOLD FIRE: stock INGAME tokens) writes pick; ans = pick only after it
        closes; od_spr_open = 1 around the dialog; re-asked SPRING_GAP_S after each answer, once P4 is done; the exits
        Now (ans == 0), H+30 (1800 s from the launch) and the anvil contested (PACT >= 1 in the union of the three anvil
        command zones), the two automatic ones only with no dialog open; then od_dauto unless the answer was FIRE AT
        WILL; then od_sprung = 1, its one write (IfThenElse on 0)."""
        self.assertEqual((mission.SPRING_GAP_S, mission.SPRING_DEADLINE_S), (120.0, 1800.0))
        self.assertEqual((mission.SPRING_NOW, mission.SPRING_WAIT, mission.CHOICE_NONE), (0, 1, 2))
        ctx, root = self.beat("spring")
        count, decide = subs(root)
        wait, both = subs(count)
        self.assertEqual(cmp_of(prop(wait, "Condition")), ("od_released", 0, 1))
        self.assertEqual([k.cls for k in subs(both)], ["TGDDescriptorSequential", "TGDDescriptorGereObjectif"])
        pick0, ans0, race, auto, latch = subs(decide)
        self.assertEqual((sets([pick0], ctx.int_var("od_spr_pick")), sets([ans0], ctx.int_var("od_spr_ans"))),
                         ([2], [2]))
        self.assertEqual(race.cls, "TGDDescriptorCompetition")
        asks, now, deadline, anvil = subs(race)
        p4_done, loop = subs(asks)
        self.assertEqual((cmp_of(prop(p4_done, "Condition")), prop(loop, "NbExecutions").v),
                         (("od_p4", 0, 1), shapes.FOREVER))
        pick, ans, opened, dialog, copy, closed, gap = subs(loop)
        self.assertEqual((sets([pick], ctx.int_var("od_spr_pick")), sets([ans], ctx.int_var("od_spr_ans")),
                          sets([opened], ctx.int_var("od_spr_open"))), ([2], [2], [1]))
        self.assertEqual(dialog.cls, "TGDDescriptorEncapsuleCutsceneDialogListWithMultipleChoice")
        (choice,) = prop(dialog, "DialogList")
        self.assertEqual((last(prop(choice, "SelectedButton")), token(prop(choice, "TokenBoutonChoix0")),
                          token(prop(choice, "TokenBoutonChoix1"))), ("od_spr_pick", "ORD_AIARA", "ORD_HOLDF"))
        self.assertEqual(self.kv(copy), [("Variable1", "od_spr_ans"), ("Variable2", "od_spr_pick")])
        self.assertEqual(self.kv(closed), [("Variable1", "od_spr_open")])               # = 0
        self.assertEqual(prop(gap, "Duree").v, 120.0)
        self.assertEqual(cmp_of(prop(now, "Condition")), ("od_spr_ans", 0, 0))
        timer, idle = subs(deadline)
        self.assertEqual((prop(timer, "Duree").v, cmp_of(prop(idle, "Condition"))), (1800.0, ("od_spr_open", 0, 0)))
        armed, contested = subs(anvil)
        self.assertEqual(cmp_of(prop(armed, "Condition")), ("od_released", 0, 1))
        zone, idle = prop(prop(contested, "Condition"), "SousConditions")
        self.assertEqual(([last(z) for z in prop(zone, "Detecteurs")], prop(prop(zone, "Contrainte"), "Camp").export,
                          cmp_count(prop(zone, "ComparaisonNbUnits")), prop(zone, "ZoneType").v),
                         (list(mission.ANVIL_CZ), PACT, (2, 1), 1))
        self.assertEqual(cmp_of(idle), ("od_spr_open", 0, 0))
        self.assertEqual(cmp_of(prop(auto, "Condition")), ("od_spr_ans", 2, 1))
        self.assertIsNone(prop(auto, "EffetIfFalse"))
        (text,) = [n for n in walk([prop(auto, "EffetIfTrue")]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
        self.assertEqual(token(prop(text, "LocalizedText")), "od_dauto")
        self.assertEqual(cmp_of(prop(latch, "Condition")), ("od_sprung", 0, 0))
        self.assertEqual(sets(list(walk([latch])), ctx.int_var("od_sprung")), [1])
        self.assertEqual(len([n for n in self.nodes if n.cls == "TGDDescriptorModifieVariableInteger"
                              and last(prop(n, "Variable1")) == "od_sprung"]), 1)
        self.assertEqual(gates.never_finishing_violations(self.roots)[1], [])

    def spring_run(self, world: World, until: int = 2000, values: dict[str, int] | None = None) -> Model:
        """The model run of the spring beat from H+0:00 beside a stand-in release at 1:40, od_smin at Medium (20)."""
        ctx = mission.Ctx()
        root = g_simul([self.released(ctx, 100), mission.spring(ctx)])
        return Model(world, {"od_smin": 20, **(values or {})}).play(root, until)

    def test_model_spring_wait_then_now(self):
        """The sack fills to 25 at 6:40: P4 is done on the next 2 s round with [25, 20]; Corps asks at once; HOLD FIRE;
        it asks again 2:00 later; FIRE AT WILL springs it there and then: od_sprung = 1, no od_dauto."""
        world = World(rings={"OD_RingPlainC": [(200, 5, 0), (300, 12, 0), (400, 25, 0)]},
                      answers=[mission.SPRING_WAIT, mission.SPRING_NOW])
        m = self.spring_run(world, until=900)
        (p4,) = [e for e in m.log if e[1:3] == ("done", "od_p4")]
        self.assertLessEqual(p4[0] - 400, 2)
        self.assertEqual(p4[3], [25, 20])
        asks = m.when("ask", "od_dspring")
        self.assertEqual((len(asks), asks[0], asks[1] - asks[0]), (2, p4[0], 120))
        self.assertEqual((m.vars["od_sprung"], m.vars["od_spr_open"], m.when("dialog")), (1, 0, []))

    def test_model_spring_deadline(self):
        """Every ask answered HOLD FIRE: Corps asks every 2:00 from P4 until H+30, then springs it itself with
        od_dauto at H+30 sharp (1800 s after the launch, not after the release)."""
        m = self.spring_run(World(rings={"OD_RingSackMid": [(400, 21, 0)]}))
        asks = m.when("ask", "od_dspring")
        self.assertEqual([b - a for a, b in zip(asks, asks[1:])], [120] * (len(asks) - 1))
        self.assertEqual((asks[0] - 400 <= 2, len(asks), asks[-1] < 1800), (True, 12, True))
        self.assertEqual(m.when("dialog", "od_dauto"), [1800])
        self.assertEqual(m.vars["od_sprung"], 1)

    def test_model_spring_anvil_before_p4(self):
        """A Soviet unit inside an anvil zone (OD_CZ_SW) at 10:00, the sack still short of S_min: no ask; Corps springs
        it at once with od_dauto; P4 then fails on od_sprung, frozen on its count. A Soviet unit in the anvil before
        the release springs nothing (the exit arms at the release)."""
        world = World(rings={"OD_RingPlainS": [(300, 8, 0)]},
                      units={"OD_CZ_SW": [(50, 1, 0), (60, 0, 0), (600, 1, 3)]})
        m = self.spring_run(world, until=700)
        self.assertEqual(m.when("ask"), [])
        self.assertEqual(m.when("dialog", "od_dauto"), [600])
        self.assertEqual(m.vars["od_sprung"], 1)
        (p4,) = [e for e in m.log if e[1:3] == ("failed", "od_p4")]
        self.assertEqual((p4[0] - 600 in (0, 1), p4[3]), (True, [8, 20]))

    def test_model_spring_waits_for_the_dialog(self):
        """Review focus 4: a dialog that stays open (30 s here; in play the game pauses) while the anvil is contested:
        the race does not end until it closes, and its HOLD FIRE answer, copied after the close, leads to od_dauto; a
        stale FIRE AT WILL (0) left in pick and ans before the beat starts springs nothing."""
        world = World(rings={"OD_RingSackS": [(400, 22, 0)]}, units={"OD_CZ_AnvilC": [(410, 2, 0)]},
                      answers=[mission.SPRING_WAIT], dialog_s=30)
        m = self.spring_run(world, until=700, values={"od_spr_pick": 0, "od_spr_ans": 0})
        (ask,) = m.when("ask", "od_dspring")
        (answer,) = [e for e in m.log if e[1] == "answer"]
        self.assertGreaterEqual(ask, 400)
        self.assertEqual((answer[0] - ask, answer[2]), (30, mission.SPRING_WAIT))
        self.assertEqual(m.when("dialog", "od_dauto"), [answer[0]])

    # ----------------------------------------------------------------------- B6 and the PL GREEN window

    def test_b6(self):
        """B6: a bonus, "%1 / %2" = od_b6_t and od_b6_s (1:30/2:00/2:30), Condition od_b6_t >= od_b6_s, ActionsReussi
        od_b6 = 1, ConditionEchec od_window = WINDOW_CLOSED; its timer is one seconds_while, contact = Or over
        both necks of And[NATO >= 1 in the neck's command zone, PACT >= 1 in its approach circle], broken = And over
        both of Or[And[NATO <= 0 in the neck], PACT <= 0 in the approach], summing (no reset)."""
        ctx = mission.Ctx()
        obj = mission.b6(ctx)
        self.assertEqual((token(prop(obj, "ObjectiveText")), prop(obj, "LabelComponent").text,
                          [last(v) for v in prop(obj, "ListVariables")], prop(obj, "Position")),
                         ("od_b6", "Bonus", ["od_b6_t", "od_b6_s"], None))
        self.assertEqual(cmp_vars(prop(obj, "Condition")), ("od_b6_t", 2, "od_b6_s"))
        self.assertEqual(cmp_of(prop(obj, "ConditionEchec")), ("od_window", 0, mission.WINDOW_CLOSED))
        self.assertEqual(self.kv(prop(obj, "ActionsReussi")), [("Variable1", "od_b6"), ("Value", 1)])
        self.assertEqual(mission.KNOBS["od_b6_s"], Knobs(90, 120, 150))
        start, comp = subs(mission.b6_contact(ctx))                     # no reset: both necks' stays add up
        _, stop = subs(comp)
        holds, broken = prop(start, "Condition"), prop(stop, "Condition")
        self.assertEqual((holds.cls, broken.cls), ("TGDConditionOr", "TGDConditionAnd"))
        for (neck, ring), contact, gone in zip(mission.B6_PAIRS, prop(holds, "SousConditions"),
                                               prop(broken, "SousConditions")):
            zone, seen = prop(contact, "SousConditions")
            self.assertEqual(([last(z) for z in prop(zone, "Detecteurs")],
                              prop(prop(zone, "Contrainte"), "Camp").export,
                              cmp_count(prop(zone, "ComparaisonNbUnits"))), ([neck], JOUEUR, (2, 1)))
            self.assertEqual((last(prop(seen, "Detecteur")), prop(prop(seen, "Contrainte"), "Camp").export,
                              cmp_count(prop(seen, "ComparaisonNbUnits"))), (ring, PACT, (2, 1)))
            wrapped, seen = prop(gone, "SousConditions")
            (zone,) = prop(wrapped, "SousConditions")
            self.assertEqual((gone.cls, wrapped.cls, [last(z) for z in prop(zone, "Detecteurs")],
                              cmp_count(prop(zone, "ComparaisonNbUnits")), last(prop(seen, "Detecteur")),
                              cmp_count(prop(seen, "ComparaisonNbUnits"))),
                             ("TGDConditionOr", "TGDConditionAnd", [neck], (3, 0), ring, (3, 0)))

    def test_pl_green(self):
        """Once released, side by side: the phase hint od_hph2 4 x HINT_S later (after the town hints, which take
        turns, and od_hopen; test_model_towns_fall_together); the contact timer until the
        window closes; the window's close (B6 done, the necks emptied after the first contact, release + 8:00, or the
        spring), od_window = WINDOW_CLOSED, then tier_handover(PACT, both necks) whatever closed it, its
        hint picked then: od_hgrs once sprung, else od_hgrn (od_hgrs_f, od_hgrn_f in "fixed" mode); B6, last. That
        hand-over is the script's one PACT forcing of a neck, and it sits right after the close's race, one of whose
        children waits for od_sprung = 1: no path hands a neck to PACT after the spring but the close the spring
        itself makes."""
        self.assertEqual((mission.WINDOW_S, mission.WINDOW_CLOSED, mission.B6_HINT_T), (480.0, 1, 60.0))
        ctx, root = self.beat("pl_green")
        wait, both = subs(root)
        self.assertEqual(cmp_of(prop(wait, "Condition")), ("od_released", 0, 1))
        hint, timer, shut, b6 = subs(both)
        gap, ld = subs(hint)
        self.assertEqual((prop(gap, "Duree").v, token(prop(subs(ld)[0], "Info"))), (60.0, "od_hph2"))
        (race,) = subs(timer)
        self.assertEqual(cmp_of(prop(subs(race)[1], "Condition")), ("od_window", 0, 1))
        close, flag, handover = subs(shut)
        done, emptied, timeout, spring = subs(close)
        self.assertEqual(cmp_of(prop(done, "Condition")), ("od_b6", 0, 1))
        contact, empty = subs(emptied)
        self.assertEqual(cmp_of(prop(contact, "Condition")), ("od_b6_t", 2, 1))
        (zone,) = prop(prop(empty, "Condition"), "SousConditions")
        self.assertEqual(([last(z) for z in prop(zone, "Detecteurs")], prop(prop(zone, "Contrainte"), "Camp").export,
                          cmp_count(prop(zone, "ComparaisonNbUnits"))), (list(mission.NECK_CZ), JOUEUR, (3, 0)))
        self.assertEqual(prop(timeout, "Duree").v, 480.0)
        self.assertEqual(cmp_of(prop(spring, "Condition")), ("od_sprung", 0, 1))
        self.assertEqual(sets([flag], ctx.int_var("od_window")), [1])
        owner, said = subs(handover)
        self.assertEqual((handover.cls, prop(owner, "Camp").export, [last(z) for z in prop(owner, "Positions")]),
                         ("TGDDescriptorSequential", PACT, list(mission.NECK_CZ)))
        self.assertEqual((said.cls, cmp_of(prop(said, "Condition"))), ("TGDDescriptorIfThenElse", ("od_sprung", 0, 1)))
        picked = [token(prop(subs(prop(said, k))[0], "Info")) for k in ("EffetIfTrue", "EffetIfFalse")]
        self.assertEqual(picked, ["od_hgrs", "od_hgrn"])
        self.assertEqual(b6.cls, "TGDDescriptorGereObjectif")
        _, fixed = self.beat("pl_green", mission.Ctx("fixed"))
        self.assertLessEqual({"od_hgrs_f", "od_hgrn_f"},
                             {token(prop(n, "Info")) for n in walk([fixed]) if n.cls == "TGDDescriptorLDHint"})
        necks = [n for n in self.nodes if n.cls == gates.ZONE_OWNER
                 and {last(t) for t in prop(n, "Positions")} & set(mission.NECK_CZ)]
        self.assertEqual(sorted(prop(n, "Camp").export for n in necks),
                         sorted([JOUEUR, PACT, JOUEUR, JOUEUR]))           # load's, this one, the two seals
        (to_pact,) = [n for n in necks if prop(n, "Camp").export == PACT]   # in the script: the close's hand-over
        closing = parent_of(self.nodes, parent_of(self.nodes, to_pact))     # Sequential[race, od_window, hand-over]
        race = subs(closing)[0]
        self.assertEqual((race.cls, [cmp_of(prop(k, "Condition")) for k in subs(race)
                                     if k.cls == "TGDDescriptorWaitCondition"]),
                         ("TGDDescriptorCompetition", [("od_b6", 0, 1), ("od_sprung", 0, 1)]))

    def green_run(self, world: World, until: int = 700, sprung: int | None = None) -> Model:
        """The model run of the PL GREEN beat beside a stand-in release at 1:40, od_b6_s at Medium (120)."""
        ctx = mission.Ctx()
        root = g_simul([self.released(ctx, 100, sprung), mission.pl_green(ctx)])
        return Model(world, {"od_b6_s": 120}).play(root, until)

    @staticmethod
    def handovers(m: Model) -> list[tuple[int, str, list[str]]]:
        return [(e[0], e[2], e[3]) for e in m.log if e[1] == "owner"]

    def test_model_window_b6_done(self):
        """NATO holds NECK MID throughout and Soviets reach its approach at 5:00: 120 s of contact complete B6 at 7:00
        with [120, 120]; the window closes on it: od_window = 1, both necks to PACT once, with od_hgrn; the phase hint
        came at 2:40."""
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 2)]}, rings={"OD_RingApprMid": [(300, 3, 0)]})
        m = self.green_run(world)
        (b6,) = [e for e in m.log if e[1:3] == ("done", "od_b6")]
        self.assertLessEqual(abs(b6[0] - 420), 2)
        self.assertEqual(b6[3], [120, 120])
        (handover,) = self.handovers(m)
        self.assertEqual((handover[1], handover[2]), (profile.CAMPS["PACT"], list(mission.NECK_CZ)))
        self.assertLessEqual(handover[0] - b6[0], 1)
        self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph2", "od_hgrn"])
        self.assertEqual(m.when("hint", "od_hph2"), [160])
        self.assertEqual(m.vars["od_window"], mission.WINDOW_CLOSED)

    def test_model_window_necks_emptied(self):
        """NATO in NECK S until 6:40, Soviets at its approach from 5:40: 60 s of contact, then the neck is left: the
        window closes at 6:40, B6 fails frozen on [60, 120], and the necks go to PACT once. NECK MID, empty from the
        start, closed nothing before any contact."""
        world = World(units={"OD_CZ_NeckS": [(0, 0, 1), (400, 0, 0)]}, rings={"OD_RingApprS": [(340, 2, 0)]})
        m = self.green_run(world)
        (b6,) = [e for e in m.log if e[1:3] == ("failed", "od_b6")]
        self.assertLessEqual(abs(b6[0] - 400), 2)
        self.assertEqual(b6[3], [60, 120])
        (handover,) = self.handovers(m)
        self.assertLessEqual(abs(handover[0] - 400), 2)
        self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph2", "od_hgrn"])

    def test_model_window_timeout(self):
        """No stand at all: the window closes 8:00 after the release, B6 fails on [0, 120], the necks go to PACT
        once, with od_hgrn."""
        m = self.green_run(World(), until=900)
        (handover,) = self.handovers(m)
        self.assertEqual(handover[0], 100 + 480)
        self.assertEqual([e[3] for e in m.log if e[1:3] == ("failed", "od_b6")], [[0, 120]])
        self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph2", "od_hgrn"])

    def test_model_window_both_necks_count_once(self):
        """Both necks in contact at once count one second a second (one timer): contact at both from 5:00 to
        6:00 adds 60; then NECK S alone from 7:00 completes B6 at 8:00."""
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 1)], "OD_CZ_NeckS": [(0, 0, 1)]},
                      rings={"OD_RingApprMid": [(300, 2, 0), (360, 0, 0)],
                             "OD_RingApprS": [(300, 2, 0), (360, 0, 0), (420, 2, 0)]})
        m = self.green_run(world)
        (b6,) = [e for e in m.log if e[1:3] == ("done", "od_b6")]
        self.assertLessEqual(abs(b6[0] - 480), 2)

    def test_model_window_spring_first(self):
        """The trap sprung at 4:10, the window still open: the spring closes it (B6 fails) and hands both necks to PACT
        in that same close, once, at the spring's tick (at most 1 s later), with od_hgrs; so before P5 can seal a neck,
        which starts at the spring and needs 30 s held. Nothing more after it."""
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 1)]}, rings={"OD_RingApprMid": [(200, 1, 0)]})
        m = self.green_run(world, until=900, sprung=250)
        (handover,) = self.handovers(m)
        self.assertEqual((handover[1], handover[2]), (profile.CAMPS["PACT"], list(mission.NECK_CZ)))
        self.assertLessEqual(handover[0] - 250, 1)
        self.assertLess(handover[0] - 250, 30)       # P5 seals a neck after 30 s held from the spring
        (b6,) = [e for e in m.log if e[1:3] == ("failed", "od_b6")]
        self.assertLessEqual(abs(b6[0] - 250), 1)
        self.assertEqual(m.vars["od_window"], mission.WINDOW_CLOSED)
        self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph2", "od_hgrs"])

    def test_model_window_spring_after_close(self):
        """A window that closed before the spring (8:00 after the release, at 9:40) handed the necks over then, with
        od_hgrn; the spring at 11:40 hands nothing over and shows nothing: no PACT hand-over after od_sprung = 1."""
        m = self.green_run(World(), until=900, sprung=700)
        self.assertEqual([(t, camp) for t, camp, _ in self.handovers(m)], [(580, profile.CAMPS["PACT"])])
        self.assertEqual([e[2] for e in m.log if e[1] == "hint"], ["od_hph2", "od_hgrn"])
        self.assertEqual([e for e in m.log if e[0] >= 700], [])

    def test_model_window_each_close_hands_over_once(self):
        """Every way the window closes (B6 done, the necks emptied after contact, release + 8:00, the spring) hands both
        necks to PACT exactly once, never after the spring, across a long run."""
        contact = dict(units={"OD_CZ_NeckMid": [(0, 0, 1)]}, rings={"OD_RingApprMid": [(300, 2, 0)]})
        cases = {"b6 done": (World(**contact), None),
                 "emptied": (World(units={"OD_CZ_NeckMid": [(0, 0, 1), (360, 0, 0)]},
                                   rings={"OD_RingApprMid": [(300, 2, 0)]}), None),
                 "timeout": (World(), None),
                 "spring": (World(**contact), 330)}
        for name, (world, sprung) in cases.items():
            with self.subTest(close=name):
                m = self.green_run(world, until=1500, sprung=sprung)
                (handover,) = self.handovers(m)
                self.assertEqual((handover[1], handover[2]), (profile.CAMPS["PACT"], list(mission.NECK_CZ)))
                if sprung is not None:
                    self.assertLessEqual(handover[0] - sprung, 1)

    def test_strings(self):
        """Phase 2's texts in both languages: P4 and B6 hold two numbers each; the hand-over hint has its "fixed"
        twin, which promises nothing about reinforcements; the spring's dialogs hold none and name the buttons' stock
        texts."""
        loc, dialogs = mission.STRINGS["Scripting/Localization"], mission.STRINGS["Scripting/Dialog"]
        for tok in ("od_hph2", "od_p4", "od_p4l", "od_b6", "od_b6l", "od_hgrn", "od_hgrn_f", "od_hgrs",
                    "od_hgrs_f"):
            with self.subTest(token=tok):
                self.assertTrue(all(loc[tok].values()))
        for tok in ("od_p4", "od_p4l", "od_b6", "od_b6l"):
            self.assertEqual([re.findall(r"%\d", text) for text in loc[tok].values()], [["%1", "%2"]] * 2)
        self.assertIn("reinforcements arrive only at the ANVIL", loc["od_hgrn"].US)
        self.assertNotIn("reinforcements", loc["od_hgrn_f"].US)
        self.assertIn("reinforcements arrive only at the anvil", loc["od_hgrs"].US.lower())
        self.assertNotIn("reinforcements", loc["od_hgrs_f"].US)
        for tok in ("od_dspring", "od_dauto"):
            self.assertNotRegex("".join(dialogs[tok].values()), r"%\d")
        self.assertTrue(all(word in dialogs["od_dspring"].US for word in ("FIRE AT WILL", "HOLD FIRE")))
        self.assertTrue(all(word in dialogs["od_dspring"].SC for word in ("自由射击", "不射击")))


# Count reads: what reads a unit group's count, the pocket's circles or the battle's tallies.
COUNT_READS = ("TGDDescriptorSetVariableIntegerFromUnitGroup", "TGDDescriptorAddDetectedUnitsToUnitGroup",
               "TGDDescriptorClearUnitGroup", "TGDDescriptorGetNbKillsCamp", "TGDDescriptorGetNbLossCamp")


def surrender_point(sealed_n: int, pct: int) -> int:
    """Design 5.4's surrender point in plain Python: floor(sealed_n x pct / 100) for the difficulty's shares; a pct
    that is none of them reads as Medium's (the fallback)."""
    shares = mission.KNOBS["od_surr_pct"]
    return sealed_n * (pct if pct in (shares.easy, shares.medium, shares.hard) else shares.medium) // 100


def grade(alive: int, captured_seen: int, sealed: bool) -> tuple[int, int]:
    """The grade arithmetic in plain Python (design 5.5): (catch, od_end) for `alive` main-body vehicles
    still alive, `captured_seen` Soviet vehicles in the pocket at the surrender (counted only if the pocket surrendered,
    which needs it `sealed`, and never more than `alive`)."""
    captured = min(captured_seen, alive) if sealed else 0
    catch = mission.MB_TOTAL - alive + captured
    if catch >= round(0.70 * mission.MB_TOTAL) and sealed:
        return catch, mission.END_TOTAL
    return catch, mission.END_MAJOR if catch >= round(0.40 * mission.MB_TOTAL) else mission.END_MINOR


@SCRIPT_DATA
class Phase34(unittest.TestCase):
    """Phases 3 and 4: the spring's effects (design 5.3), P5 per neck and the hints in turn (design 5.4), the seal, P6,
    the surrender, the backstop and the catch (design 5.4-5.5), by shape and through `Model`."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        cls.roots, cls.exports = mission.script(cls.tpl)
        cls.nodes = list(walk(cls.roots))
        cls.jaws = [it.name for it in mission.ITEMS if it.group in mission.JAWS]

    def beat(self, check: str, ctx: mission.Ctx | None = None) -> tuple[mission.Ctx, Node]:
        (b,) = [b for b in mission.BEATS if b.check == check]
        ctx = ctx or mission.Ctx()
        return ctx, b.build(ctx)

    @staticmethod
    def at(ctx: mission.Ctx, **flags: int | None) -> list[Node]:
        """Stand-ins for other beats' phase flags: each named flag = 1 at its second (None: never)."""
        return [g_seq([g_wait(t), g_set(ctx.int_var(name), 1)]) for name, t in flags.items()
                if t is not None]

    @staticmethod
    def zone_counts(cond: Node) -> list[tuple[list[str], str, tuple[int, int]]]:
        return [([last(z) for z in prop(c, "Detecteurs")], prop(prop(c, "Contrainte"), "Camp").export,
                 cmp_count(prop(c, "ComparaisonNbUnits"))) for c in prop(cond, "SousConditions")]

    def test_constants(self):
        """The values: design 6.1's spring row, the seal at 30 s, design 5.4's surrender at 45/35/25 % and T_hold
        15:00, the backstop at spring + 25:00, design 5.5's bands at 70 % and 40 % of the main body's 60 vehicles."""
        self.assertEqual(mission.SPRING_CARDS, (ForceRow("M1A1HA_Abrams_US", 4), ForceRow("Leopard_2A4_RFA", 4),
                                             ForceRow("OH58D_Kiowa_Warrior_US", 2)))
        self.assertEqual((mission.SEAL_NATO_N, mission.SEAL_HOLD_S, mission.T_HOLD_S, mission.BACKSTOP_S),
                         (1, 30.0, 900.0, 1500.0))
        self.assertEqual(mission.KNOBS["od_surr_pct"], Knobs(45, 35, 25))
        self.assertEqual((mission.CATCH_TOTAL_N, mission.CATCH_MAJOR_N), (42, 24))
        self.assertEqual((mission.CATCH_TOTAL_N, mission.CATCH_MAJOR_N),
                         tuple(forces.share_count(s, mission.MB_TOTAL) for s in (0.70, 0.40)))
        self.assertEqual((mission.ADD, mission.DIVIDE, mission.STRICTLY_LESS, mission.SURR_PCT_BASE),
                         (1, 4, 5, 100))                         # EVariableIntegerModification, EGDOperator
        self.assertFalse(hasattr(mission, "MULTIPLY"))
        self.assertEqual([(s.cz, s.key) for s in mission.SEALS], [("OD_CZ_NeckMid", "mid"), ("OD_CZ_NeckS", "s")])
        self.assertTrue({f"od_sealed_{s.key}" for s in mission.SEALS} <= set(mission.FLAGS))

    # ----------------------------------------------------------------------- phase 3

    def test_spring_effects(self):
        """Once od_sprung = 1: the codeword dialog od_dcode, SpawnUnits of every jaw item, which join Groupe_Joueur
        (Survivors #1330-#1331), and the spring cards in SigurdsStrike #1042's shape (Camp, NbUnitsToAdd, TypeUnit);
        then the hints and P5 side by side. No F-4G, EF-111 or AH-64 card anywhere (not built yet); the A-10A unlocks on
        od_sprung (load_deck's lock)."""
        _, root = self.beat("phase3")
        wait, effects, both = subs(root)
        self.assertEqual(cmp_of(prop(wait, "Condition")), ("od_sprung", 0, 1))
        dialog, spawn, join, *cards = subs(effects)
        (text,) = [n for n in walk([dialog]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
        self.assertEqual((dialog.cls, token(prop(text, "LocalizedText"))), ("TGDDescriptorEncapsuleCutscene",
                                                                              "od_dcode"))
        self.assertEqual(len(self.jaws), sum(forces.group_total(forces.ROWS, g) for g in mission.JAWS))
        self.assertEqual([last(u) for u in prop(spawn, "Units")], self.jaws)
        self.assertEqual((last(prop(join, "GroupDestination")), [last(g) for g in prop(join, "ListGroupSource")]),
                         ("Groupe_Joueur", self.jaws))
        self.assertEqual([(prop(c, "TypeUnit").path, prop(c, "NbUnitsToAdd").v) for c in cards],
                         [(unit_path(c.unit), c.count) for c in mission.SPRING_CARDS])
        for c in cards:
            self.assertEqual(([k for k, _ in c.props], prop(c, "Camp").export), (["Camp", "NbUnitsToAdd", "TypeUnit"],
                                                                                 JOUEUR))
        self.assertEqual(both.cls, "TGDDescriptorSimultaneous")
        decked = {prop(n, "TypeUnit").path for n in of(self.nodes, "AddUnitToDeck")}
        for unit in ("F4_Wild_Weasel_US", "EF111_Raven_US", "AH64_Apache_US", "AH64_Apache_emp1_US"):
            self.assertNotIn(unit_path(unit), decked)
        (lock,) = of(self.nodes, "LockDeckUnit")
        until = subs(parent_of(self.nodes, lock))[0]
        self.assertEqual(cmp_of(prop(until, "Condition")), ("od_sprung", 0, 1))

    def test_jaws_hidden_inside_and_revealed_once(self):
        """The jaws (design 6.2): hidden camp 0 spawns (DisableAutoSpawn), each inside the playable zone in both tier
        modes; the script reveals each exactly once, in the one SpawnUnits that names them, after od_sprung = 1."""
        ring = GEISA.playable_polygon()
        for mode in mission.TIER_MODES:
            jaw = [it for it in mission.items(mode) if it.group in mission.JAWS]
            self.assertEqual([it.name for it in jaw], self.jaws)
            for it in jaw:
                with self.subTest(mode=mode, item=it.name):
                    self.assertEqual((it.ranking, it.camp, it.disable_auto_spawn), ("Camp_0", 0, True))
                    self.assertTrue(point_in_polygon(it.x, it.y, ring))
        spawns = of(self.nodes, "SpawnUnits")
        named = Counter(last(u) for s in spawns for u in prop(s, "Units"))
        self.assertEqual({name: named[name] for name in self.jaws}, dict.fromkeys(self.jaws, 1))
        (reveal,) = [s for s in spawns if any(last(u) in self.jaws for u in prop(s, "Units"))]
        effects = parent_of(self.nodes, reveal)
        beat = parent_of(self.nodes, effects)
        self.assertEqual(cmp_of(prop(subs(beat)[0], "Condition")), ("od_sprung", 0, 1))

    def test_p5(self):
        """P5 per neck: the seal race (zone_race: NATO >= 1 and PACT none in the neck's command zone, 30 s held), its
        flag, then tier_handover(NATO, that neck) whose hint waits for its turn (od_hturn its own or HTURN_ANY);
        the objective pinned on the neck shows the held seconds, done on the flag, failed if the battle ends first.
        "Fixed" mode's seal hints say only that the neck is ours."""
        ctx, root = self.beat("phase3")
        lane, *necks = subs(subs(root)[2])
        self.assertEqual(len(necks), 2)
        for seal, node in zip(mission.SEALS, necks):
            with self.subTest(neck=seal.cz):
                chain, obj = subs(node)
                race, flag, handover = subs(chain)
                loop, held = subs(race)
                self.assertEqual(cmp_of(prop(held, "Condition")), (f"od_p5_{seal.key}_held", 2, 30))
                self.assertEqual(self.zone_counts(prop(subs(loop)[0], "Condition")),
                                 [([seal.cz], JOUEUR, (2, 1)), ([seal.cz], PACT, (3, 0))])   # NATO >= 1, PACT <= 0
                self.assertEqual(sets([flag], ctx.int_var(f"od_sealed_{seal.key}")), [1])
                owner, said = subs(handover)
                self.assertEqual((prop(owner, "Camp").export, [last(z) for z in prop(owner, "Positions")]),
                                 (JOUEUR, [seal.cz]))
                turn, hint = subs(said)
                self.assertEqual([cmp_of(c) for c in prop(prop(turn, "Condition"), "SousConditions")],
                                 [("od_hturn", 0, seal.turn), ("od_hturn", 0, mission.HTURN_ANY)])
                self.assertEqual(token(prop(subs(hint)[0], "Info")), seal.hint)
                self.assertEqual((token(prop(obj, "ObjectiveText")), token(prop(obj, "ObjectiveEtiquetteText")),
                                  prop(obj, "LabelComponent").text, last(prop(obj, "Position")),
                                  prop(obj, "ShowEtiquette"), [last(v) for v in prop(obj, "ListVariables")]),
                                 (seal.text, seal.text + "l", "Primary", seal.cz, TRUE,
                                  [f"od_p5_{seal.key}_held"]))
                self.assertEqual(cmp_of(prop(obj, "Condition")), (f"od_sealed_{seal.key}", 0, 1))
                self.assertEqual(cmp_of(prop(obj, "ConditionEchec")), ("od_end", 2, mission.END_TOTAL))
        _, fixed = self.beat("phase3", mission.Ctx("fixed"))
        self.assertEqual(sorted(token(prop(n, "Info")) for n in walk([fixed]) if n.cls == "TGDDescriptorLDHint"),
                         ["od_hjaw", "od_hsm_f", "od_hss_f"])

    def test_seal_hints(self):
        """The hints' lane: HINT_S, the jaw hint beside a HINT_S wait, then on the first seal od_hturn = NECK MID's
        turn if it is sealed (both at once: NECK MID first), else NECK S's, then HINT_S later HTURN_ANY."""
        ctx, root = self.beat("phase3")
        lane = subs(subs(root)[2])[0]
        gap, jaw, first, pick, gap2, anyone = subs(lane)
        hint, wait = subs(jaw)
        self.assertEqual((prop(gap, "Duree").v, token(prop(hint, "Info")), prop(hint, "Time").v, prop(wait, "Duree").v,
                          prop(gap2, "Duree").v), (mission.HINT_S,) + ("od_hjaw",) + (mission.HINT_S,) * 3)
        self.assertEqual([cmp_of(c) for c in prop(prop(first, "Condition"), "SousConditions")],
                         [("od_sealed_mid", 0, 1), ("od_sealed_s", 0, 1)])
        self.assertEqual(cmp_of(prop(pick, "Condition")), ("od_sealed_mid", 0, 1))
        self.assertEqual([sets(subs(prop(pick, k)), ctx.int_var("od_hturn")) for k in ("EffetIfTrue", "EffetIfFalse")],
                         [[mission.HTURN_MID], [mission.HTURN_S]])
        self.assertEqual(sets([anyone], ctx.int_var("od_hturn")), [mission.HTURN_ANY])

    def phase3_run(self, world: World, sprung: int = 100, until: int = 400, green: bool = False) -> Model:
        """The model run of the phase-3 beat beside a stand-in spring (od_sprung = 1 at `sprung`), and with `green`
        phase 2's PL GREEN beat beside a stand-in release at 1:40 (od_b6_s at Medium)."""
        ctx = mission.Ctx()
        beats = [*self.at(ctx, od_sprung=sprung), mission.phase3(ctx)]
        if green:
            beats += [*self.at(ctx, od_released=100), mission.pl_green(ctx)]
        return Model(world, {"od_b6_s": 120}).play(g_simul(beats), until)

    @staticmethod
    def hints(m: Model) -> list[tuple[int, str]]:
        return [(e[0], e[2]) for e in m.log if e[1] == "hint"]

    def assert_one_at_a_time(self, hints: list[tuple[int, str]]) -> None:
        for (t0, a), (t1, b) in zip(hints, hints[1:]):
            self.assertGreaterEqual(t1 - t0, mission.HINT_S, (a, b, hints))

    def test_model_both_necks_at_once(self):
        """Player units in both necks and no Soviets from the spring at 1:40: the codeword dialog, the reveal and the
        cards at once; the jaw hint at 1:55; both seals 30 s held at 2:10, each neck handed back to NATO then; their
        hints one at a time, NECK MID's first; both P5 rows done on 30 s."""
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 2)], "OD_CZ_NeckS": [(0, 0, 3)]})
        m = self.phase3_run(world)
        self.assertEqual(m.when("dialog", "od_dcode"), [100])
        kinds = [e[1] for e in m.log if e[0] == 100]
        self.assertEqual(kinds[:4], ["dialog", "SpawnUnits", "AddUnitGroupListToUnitGroup", "AddUnitToDeck"])
        self.assertEqual([(t, camp, zones) for t, camp, zones in Phase2.handovers(m)],
                         [(130, profile.CAMPS["NATO"], ["OD_CZ_NeckMid"]),
                          (130, profile.CAMPS["NATO"], ["OD_CZ_NeckS"])])
        self.assertEqual(self.hints(m), [(115, "od_hjaw"), (131, "od_hsm"), (146, "od_hss")])
        self.assert_one_at_a_time(self.hints(m))
        self.assertEqual([e[1:] for e in m.log if e[1] in ("done", "failed")],
                         [("done", "od_p5m", [30]), ("done", "od_p5s", [30])])
        self.assertEqual((m.vars["od_sealed_mid"], m.vars["od_sealed_s"]), (1, 1))

    def test_model_second_seal_waits_its_turn(self):
        """NECK S sealed first (2:10), NECK MID 5 s later: NECK S's hint at once, NECK MID's waits its 15 s. Later, a
        neck sealed long after the other shows its hint at once (no turn to wait for)."""
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 0), (105, 0, 1)], "OD_CZ_NeckS": [(0, 0, 1)]})
        m = self.phase3_run(world)
        self.assertEqual([(t, zones) for t, _, zones in Phase2.handovers(m)],
                         [(130, ["OD_CZ_NeckS"]), (135, ["OD_CZ_NeckMid"])])
        self.assertEqual(self.hints(m), [(115, "od_hjaw"), (131, "od_hss"), (146, "od_hsm")])
        late = World(units={"OD_CZ_NeckMid": [(0, 0, 0), (300, 0, 1)], "OD_CZ_NeckS": [(0, 0, 1)]})
        m = self.phase3_run(late, until=500)
        self.assertEqual(self.hints(m), [(115, "od_hjaw"), (131, "od_hss"), (330, "od_hsm")])

    def test_model_seal_race_breaks(self):
        """A Soviet unit in NECK MID from 2:00 to 2:05 breaks its streak (zone_race resets): the seal comes 30 s after
        2:05; a neck with no player unit is never sealed and its P5 row stays open."""
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 1), (120, 1, 1), (125, 0, 1)]})
        m = self.phase3_run(world)
        (handover,) = Phase2.handovers(m)
        self.assertEqual((handover[0], handover[2]), (155, ["OD_CZ_NeckMid"]))
        self.assertEqual([e[1:3] for e in m.log if e[1] in ("done", "failed")], [("done", "od_p5m")])
        self.assertEqual(m.vars.get("od_sealed_s", 0), 0)

    def test_model_spring_closes_window_then_seal(self):
        """With phase 2's PL GREEN: the trap sprung at 4:10, the window still open: the spring's close hands both necks
        to PACT at once (od_hgrs), the codeword dialog shows, the jaw hint 15 s later, and NECK MID, held by the player
        all along, is sealed 30 s after the spring and handed back to NATO: PACT first, then NATO, never the other way
        round; every hint one at a time."""
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 2)]})
        m = self.phase3_run(world, sprung=250, until=600, green=True)
        self.assertEqual([(t, camp, zones) for t, camp, zones in Phase2.handovers(m)],
                         [(250, profile.CAMPS["PACT"], list(mission.NECK_CZ)),
                          (280, profile.CAMPS["NATO"], ["OD_CZ_NeckMid"])])
        self.assertEqual(m.when("dialog", "od_dcode"), [250])
        self.assertEqual(self.hints(m), [(160, "od_hph2"), (250, "od_hgrs"), (265, "od_hjaw"), (281, "od_hsm")])
        self.assert_one_at_a_time(self.hints(m))
        self.assertEqual((m.owner["OD_CZ_NeckMid"], m.owner["OD_CZ_NeckS"]),
                         (profile.CAMPS["NATO"], profile.CAMPS["PACT"]))

    # ----------------------------------------------------------------------- phase 4 and the catch

    def parts(self) -> dict[str, Node]:
        """The pocket beat's parts, by name."""
        ctx, root = self.beat("pocket")
        wait, both = subs(root)
        main, p6 = subs(both)
        race, *catch = subs(main)
        surrender, backstop = subs(race)
        return dict(ctx=ctx, wait=wait, main=main, p6=p6, race=race, surrender=surrender, backstop=backstop,
                    catch=catch)

    def test_seal_and_surrender(self):
        """Once both necks are sealed: the pocket's vehicles counted into od_sealed_n (a round over the sack's circles,
        the sack's vehicle constraint), od_pocket = od_sealed_n, od_surr_x = od_sealed_n x od_surr_pct / 100
        (share_of: od_surr_x = 0, IfThenElse on od_surr_pct's value with one counted loop of Adds per difficulty share,
        Medium's the last else, then the Divide by the constant), od_surr_n = od_surr_x, then od_sealed = 1, last; then
        the pocket loop raced against the surrender's wait (od_surr_n >= od_pocket, or T_hold), od_surr = 1, and the
        wait for P6's od_p6."""
        p = self.parts()
        ctx = p["ctx"]
        self.assertEqual(cmp_of(prop(p["wait"], "Condition")), ("od_sprung", 0, 1))
        both, clear, *rest = subs(p["surrender"])
        collects, rest = rest[:5], rest[5:]
        count, left, zero, shares, per, surr_n, sealed, race, surr, p6_done = rest
        self.assertEqual([cmp_of(c) for c in prop(prop(both, "Condition"), "SousConditions")],
                         [("od_sealed_mid", 0, 1), ("od_sealed_s", 0, 1)])
        self.assertEqual((clear.cls, last(prop(clear, "Group"))), ("TGDDescriptorClearUnitGroup", "od_pocketg"))
        self.assertEqual([last(prop(prop(c, "Detector"), "Detecteur")) for c in collects], list(mission.SACK_RINGS))
        for c in collects:
            self.assertEqual(prop(prop(c, "Detector"), "Contrainte").cls, "TGDContrainteOnUnitAllContrainte")
        self.assertEqual(Phase2.kv(count), [("Group", "od_pocketg"), ("Variable", "od_sealed_n")])
        self.assertEqual([Phase2.kv(n) for n in (left, zero, per, surr_n)],
                         [[("Variable1", "od_pocket"), ("Variable2", "od_sealed_n")], [("Variable1", "od_surr_x")],
                          [("Variable1", "od_surr_x"), ("Value", 100), ("ModificationType", 4)],
                          [("Variable1", "od_surr_n"), ("Variable2", "od_surr_x")]])
        knob = mission.KNOBS["od_surr_pct"]
        easy, medium, hard = knob.easy, knob.medium, knob.hard
        branches, node = [], shares                                         # IfThenElse(easy, IfThenElse(hard, ...))
        while node.cls == "TGDDescriptorIfThenElse":
            branches.append((cmp_of(prop(node, "Condition")), prop(node, "EffetIfTrue")))
            node = prop(node, "EffetIfFalse")
        branches.append((None, node))                                       # the fallback: Medium
        self.assertEqual([c for c, _ in branches], [("od_surr_pct", 0, easy), ("od_surr_pct", 0, hard), None])
        for (_, loop), n in zip(branches, (easy, hard, medium)):
            (add,) = subs(loop)
            self.assertEqual((loop.cls, prop(loop, "NbExecutions").v, Phase2.kv(add)),
                             ("TGDDescriptorSequential", n, [("Variable1", "od_surr_x"), ("Variable2", "od_sealed_n"),
                                                             ("ModificationType", 1)]))
        self.assertEqual(sets([sealed], ctx.int_var("od_sealed")), [1])
        loop, gives_up = subs(race)
        self.assertEqual((race.cls, prop(loop, "NbExecutions").v), ("TGDDescriptorCompetition", shapes.FOREVER))
        self.assertEqual(Phase2.kv(subs(loop)[6]), [("Group", "od_pocketg"), ("Variable", "od_pocket")])
        self.assertEqual(prop(subs(loop)[7], "Duree").v, mission.SACK_POLL_S)
        (inner,) = subs(gives_up)
        threshold, hold = subs(inner)
        self.assertEqual(cmp_vars(prop(threshold, "Condition")), ("od_surr_n", 2, "od_pocket"))   # stock's form
        self.assertEqual(prop(hold, "Duree").v, 900.0)
        self.assertEqual(sets([surr], ctx.int_var("od_surr")), [1])
        self.assertEqual(cmp_of(prop(p6_done, "Condition")), ("od_p6", 0, 1))
        wait, unsealed = subs(p["backstop"])                                     # the backstop, guarded
        self.assertEqual((prop(wait, "Duree").v, prop(unsealed, "Condition").cls,
                          [cmp_of(c) for c in prop(prop(unsealed, "Condition"), "SousConditions")]),
                         (1500.0, "TGDConditionAnd", [("od_sealed", 0, 0), ("od_end", 0, 0)]))
        writes = [n for n in self.nodes if n.cls == "TGDDescriptorModifieVariableInteger"
                  and last(prop(n, "Variable1")) == "od_sealed"]
        self.assertEqual(len(writes), 1)

    def test_p6(self):
        """P6 from od_sealed = 1: "%1 ... %2" = od_pocket and od_surr_n; done on od_surr_n >= od_pocket or od_surr = 1
        (T_hold), then od_p6 = 1; failed if the battle ends first; last in its Sequential, no pin."""
        wait, obj = subs(self.parts()["p6"])
        self.assertEqual(cmp_of(prop(wait, "Condition")), ("od_sealed", 0, 1))
        self.assertEqual((token(prop(obj, "ObjectiveText")), prop(obj, "LabelComponent").text,
                          [last(v) for v in prop(obj, "ListVariables")], prop(obj, "Position")),
                         ("od_p6", "Primary", ["od_pocket", "od_surr_n"], None))
        either = prop(obj, "Condition")
        threshold, held = prop(either, "SousConditions")
        self.assertEqual((either.cls, cmp_vars(threshold), cmp_of(held)),
                         ("TGDConditionOr", ("od_surr_n", 2, "od_pocket"), ("od_surr", 0, 1)))
        self.assertEqual(cmp_of(prop(obj, "ConditionEchec")), ("od_end", 2, mission.END_TOTAL))
        self.assertEqual(Phase2.kv(prop(obj, "ActionsReussi")), [("Variable1", "od_p6"), ("Value", 1)])

    def test_catch(self):
        """After the race: od_alive = od_mb's count; surrendered: od_captured = the pocket's vehicles, at most od_alive,
        then the pocket's every Soviet unit (Team PACT) removed, KillAllUnit Vanished (DeathCause omitted), last; else
        (the backstop) od_captured = 0 and the dialog od_dback; then od_mb_n = 60, od_catch = 60 - od_alive +
        od_captured; then the CATCH: done on od_catch >= 24 (Total if >= 42 and sealed, else Major), failed below
        (Minor)."""
        p = self.parts()
        ctx = p["ctx"]
        alive, pick, total, base, minus, plus, obj = p["catch"]
        self.assertEqual(Phase2.kv(alive), [("Group", "od_mb"), ("Variable", "od_alive")])
        self.assertEqual(cmp_of(prop(pick, "Condition")), ("od_surr", 0, 1))
        kids = subs(prop(pick, "EffetIfTrue"))
        self.assertEqual([k.cls.removeprefix("TGDDescriptor") for k in kids],
                         ["ClearUnitGroup", *["AddDetectedUnitsToUnitGroup"] * 5, "SetVariableIntegerFromUnitGroup",
                          "IfThenElse", "ClearUnitGroup", *["AddDetectedUnitsToUnitGroup"] * 5, "KillAllUnit"])
        self.assertEqual(Phase2.kv(kids[6]), [("Group", "od_pocketg"), ("Variable", "od_captured")])
        clamp = kids[7]
        self.assertEqual(cmp_vars(prop(clamp, "Condition")), ("od_alive", 5, "od_captured"))
        self.assertEqual(Phase2.kv(subs(prop(clamp, "EffetIfTrue"))[0]),
                         [("Variable1", "od_captured"), ("Variable2", "od_alive")])
        for c in kids[9:14]:
            self.assertEqual((last(prop(c, "Group")), prop(prop(prop(c, "Detector"), "Contrainte"), "Camp").export),
                             ("od_pocket_all", PACT))
        self.assertEqual([(k, [last(g) for g in v]) for k, v in kids[-1].props],
                         [("GroupList", ["od_pocket_all"])])                    # Vanished: no DeathCause
        zero, dialog = subs(prop(pick, "EffetIfFalse"))
        (text,) = [n for n in walk([dialog]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
        self.assertEqual((Phase2.kv(zero), token(prop(text, "LocalizedText"))),
                         ([("Variable1", "od_captured")], "od_dback"))
        self.assertEqual([Phase2.kv(n) for n in (total, base, minus, plus)],
                         [[("Variable1", "od_mb_n"), ("Value", 60)], [("Variable1", "od_catch"), ("Value", 60)],
                          [("Variable1", "od_catch"), ("Variable2", "od_alive"), ("ModificationType", 2)],
                          [("Variable1", "od_catch"), ("Variable2", "od_captured"), ("ModificationType", 1)]])
        self.assertEqual((token(prop(obj, "ObjectiveText")), prop(obj, "LabelComponent").text,
                          [last(v) for v in prop(obj, "ListVariables")], prop(obj, "Position")),
                         ("od_catch", "Primary", ["od_catch", "od_mb_n"], None))
        self.assertEqual((cmp_of(prop(obj, "Condition")), cmp_of(prop(obj, "ConditionEchec"))),
                         (("od_catch", 2, 24), ("od_catch", 3, 23)))
        (split,) = subs(prop(obj, "ActionsReussi"))
        self.assertEqual([cmp_of(c) for c in prop(prop(split, "Condition"), "SousConditions")],
                         [("od_catch", 2, 42), ("od_sealed", 0, 1)])
        end = ctx.int_var("od_end")
        self.assertEqual([sets(list(walk([prop(split, k)])), end) for k in ("EffetIfTrue", "EffetIfFalse")],
                         [[mission.END_TOTAL], [mission.END_MAJOR]])
        self.assertEqual(sets(list(walk([prop(obj, "ActionsEchec")])), end), [mission.END_MINOR])
        self.assertIs(obj, subs(p["main"])[-1])                              # last in its Sequential (gate 3)

    def test_count_reads_before_the_vanish(self):
        """Review focus 3: the script's one KillAllUnit is last in its Sequential, after the pocket's vehicles are
        counted, and od_mb's count comes before the IfThenElse holding it; going up from it, nothing that follows in
        any enclosing Sequential reads a count (a group count, a circle, a tally, or a condition on a group's size), up
        to the beat. The pocket loop that runs beside is stopped by the surrender's wait before."""
        (vanish,) = of(self.nodes, "KillAllUnit")
        node, ups = vanish, 0
        while True:                                   # up to the pocket beat: Sequential[WaitCondition(od_sprung), ...]
            up = parent_of(self.nodes, node)
            if up.cls == "TGDDescriptorSequential":
                kids = subs(up)
                after = list(walk(kids[kids.index(node) + 1:]))
                self.assertEqual([n.cls for n in after if n.cls in COUNT_READS], [])
                self.assertEqual([n for n in after if gates.group_count_test(n) is not None], [])
                if node is vanish:
                    self.assertTrue(any(last(prop(n, "Variable")) == "od_captured" for n in kids[:kids.index(node)]
                                        if n.cls == "TGDDescriptorSetVariableIntegerFromUnitGroup"))
                if kids[0].cls == "TGDDescriptorWaitCondition":
                    self.assertEqual(cmp_of(prop(kids[0], "Condition")), ("od_sprung", 0, 1))
                    break
            node, ups = up, ups + 1
        self.assertEqual(ups, 4)                      # its Sequential, the IfThenElse, the catch's, the Simultaneous
        pocket = up
        catch = subs(subs(subs(pocket)[1])[0])
        reads = [k for k, n in enumerate(catch) if n.cls == "TGDDescriptorSetVariableIntegerFromUnitGroup"]
        holder = next(k for k, n in enumerate(catch) if any(x is vanish for x in walk([n])))
        self.assertEqual(([last(prop(catch[k], "Variable")) for k in reads], reads[0] < holder),
                         (["od_alive"], True))

    def pocket_run(self, world: World, sealed: tuple[int | None, int | None] = (200, 200), pct: int = 35,
                   until: int = 2600) -> Model:
        """The model run of the pocket beat beside stand-ins: the spring at 1:40 and each neck's seal at its second."""
        ctx = mission.Ctx()
        root = g_simul([*self.at(ctx, od_sprung=100, od_sealed_mid=sealed[0], od_sealed_s=sealed[1]),
                             mission.pocket(ctx)])
        return Model(world, {"od_surr_pct": pct}).play(root, until)

    def test_model_surr_n(self):
        """od_surr_n = floor(od_sealed_n x od_surr_pct / 100) for the difficulty's three shares, through the loop of
        Adds, as `surrender_point`; an unset share (0) falls back to Medium's 35 %."""
        for sealed_n, pct in ((20, 35), (20, 45), (20, 25), (0, 35), (3, 25), (59, 45), (60, 35), (7, 45), (99, 25),
                              (30, 0)):
            with self.subTest(sealed_n=sealed_n, pct=pct):
                world = World(rings={"OD_RingPlainC": [(0, sealed_n, 0)]}, groups={"od_mb": [(0, 60)]})
                m = self.pocket_run(world, sealed=(150, 150), pct=pct, until=160)
                self.assertEqual((m.vars["od_sealed_n"], m.vars["od_surr_n"], m.vars["od_sealed"]),
                                 (sealed_n, surrender_point(sealed_n, pct), 1))
                if pct:
                    self.assertEqual(m.vars["od_surr_n"], sealed_n * pct // 100)
        self.assertEqual(surrender_point(30, 0), 10)

    def test_modifications_are_stock_forms(self):
        """Every ModifieVariableInteger and every integer comparison in the script is a form the 29 stock Operation
        scripts use: Set, Add and Substract by a constant or a
        variable, Divide by a constant (no Multiply); against a constant any EGDOperator, against a variable only
        Equal, MoreOrEqual, StrictlyMore and StrictlyLess (stock compares a variable with LessOrEqual or Different
        only against a constant). A variable-against-variable LessOrEqual, Different or Multiply fails."""
        def forms(nodes: list[Node]) -> tuple[set, set]:
            mods, cmps = set(), set()
            for n in nodes:
                if n.cls == "TGDDescriptorModifieVariableInteger":
                    kind = prop(n, "ModificationType")
                    mods.add((kind.v if kind is not None else 0, prop(n, "Variable2") is not None))
                elif n.cls == "TGDOperatorIntegerCompare":
                    kind = prop(n, "OperatorType")
                    cmps.add((kind.v if kind is not None else 0, prop(n, "Variable") is not None))
            return mods, cmps

        stock_mods = {(0, False), (0, True), (1, False), (1, True), (2, False), (2, True), (4, False)}
        stock_cmps = {*((op, False) for op in range(6)), *((op, True) for op in (0, 2, 4, 5))}
        mods, cmps = forms(self.nodes)
        self.assertLessEqual(mods, stock_mods)
        self.assertLessEqual(cmps, stock_cmps)
        self.assertIn((4, False), mods)                                             # Divide by a constant
        self.assertLessEqual({(2, True), (5, True)}, cmps)                          # the GE and < against a variable
        ctx = mission.Ctx()
        a, b = ctx.int_var("od_test_a"), ctx.int_var("od_test_b")
        for bad in (g_cmp(a, op=3, other=b), g_cmp(a, op=1, other=b), g_modify(a, 3, other=b)):
            with self.subTest(bad=bad.cls):
                mods, cmps = forms(list(walk([bad])))
                self.assertFalse(mods <= stock_mods and cmps <= stock_cmps)

    def test_model_surrender_at_the_threshold(self):
        """Sealed at 3:20 with 30 Soviet vehicles in the pocket (Medium: it gives up at 10); the main body down to 20
        alive; the pocket falls to 10 at 6:40: P6 is done on that round with [10, 10], then the counts (od_alive,
        od_captured) and only then the removal of the pocket's units; no count after it; the CATCH done on [50, 60]:
        Total."""
        world = World(rings={"OD_RingPlainC": [(0, 30, 0), (400, 10, 0)]}, groups={"od_mb": [(0, 20)]})
        m = self.pocket_run(world)
        self.assertEqual((m.vars["od_sealed_n"], m.vars["od_surr_n"]), (30, 10))
        (p6,) = [e for e in m.log if e[1:3] == ("done", "od_p6")]
        self.assertLessEqual(p6[0] - 400, 2)
        self.assertEqual(p6[3], [10, 10])
        vanish = next(k for k, e in enumerate(m.log) if e[1] == "vanish")
        self.assertEqual(m.log[vanish][2], ["od_pocket_all"])
        self.assertEqual([e[2:] for e in m.log[:vanish] if e[1] == "count"][-2:],
                         [("od_alive", 20), ("od_captured", 10)])
        self.assertEqual([e for e in m.log[vanish:] if e[1] == "count"], [])
        self.assertLess(m.log.index(p6), vanish)
        (catch,) = [e for e in m.log if e[2:3] == ("od_catch",)]
        self.assertEqual((catch[1], catch[3], m.vars["od_end"]), ("done", [50, 60], mission.END_TOTAL))
        self.assertEqual(m.when("dialog"), [])

    def test_model_surrender_at_t_hold(self):
        """The pocket never falls to its surrender point: it surrenders 15:00 after the seal (T_hold), P6 done then
        with the count it shows; the catch counts what is in it."""
        world = World(rings={"OD_RingPlainC": [(0, 30, 0), (400, 25, 0)]}, groups={"od_mb": [(0, 40)]})
        m = self.pocket_run(world)
        (p6,) = [e for e in m.log if e[1:3] == ("done", "od_p6")]
        self.assertEqual((p6[0], p6[3]), (200 + 900, [25, 10]))
        self.assertIn(m.when("vanish")[0] - p6[0], (0, 1))
        self.assertEqual((m.vars["od_catch"], m.vars["od_end"]), (45, mission.END_TOTAL))

    def test_model_backstop(self):
        """The backstop: no neck sealed 25:00 after the spring (at 26:40): Corps's dialog od_dback, no removal, the
        catch counts the destroyed only (captured 0): Major with 36 destroyed; P6 never shows; od_sealed stays 0. A
        neck sealed after that changes nothing."""
        world = World(rings={"OD_RingPlainC": [(0, 30, 0)]}, groups={"od_mb": [(0, 24)]})
        m = self.pocket_run(world, sealed=(300, None), until=2000)
        self.assertEqual(m.when("dialog", "od_dback"), [1600])
        self.assertEqual((m.when("vanish"), m.vars.get("od_sealed", 0), m.vars["od_captured"]), ([], 0, 0))
        (catch,) = [e for e in m.log if e[2:3] == ("od_catch",)]
        self.assertEqual((catch[0], catch[1], catch[3], m.vars["od_end"]), (1600, "done", [36, 60], mission.END_MAJOR))
        self.assertEqual([e for e in m.log if e[2:3] == ("od_p6",)], [])
        late = self.pocket_run(world, sealed=(300, 1700), until=2000)
        self.assertEqual((late.vars["od_end"], late.when("vanish"), late.vars.get("od_sealed", 0)),
                         (mission.END_MAJOR, [], 0))

    def test_model_defeat_before_the_backstop(self):
        """A defeat written before the backstop (od_end = END_ANVIL at 16:40, a stand-in for the
        anvil's set_end; one neck sealed, never both) holds it for good: at 26:40 and after, no od_dback, no CATCH row,
        no removal, and od_end stays the defeat's. Without the defeat the same run shows od_dback at 26:40
        (test_model_backstop)."""
        ctx = mission.Ctx()
        world = World(rings={"OD_RingPlainC": [(0, 30, 0)]}, groups={"od_mb": [(0, 24)]})
        defeat = g_seq([g_wait(1000), g_set(ctx.int_var("od_end"), mission.END_ANVIL)])
        root = g_simul([*self.at(ctx, od_sprung=100, od_sealed_mid=300), defeat, mission.pocket(ctx)])
        m = Model(world, {"od_surr_pct": 35}).play(root, 2600)
        self.assertEqual((m.when("dialog"), m.when("vanish"), [e for e in m.log if e[1] in ("done", "failed")]),
                         ([], [], []))
        self.assertEqual((m.vars["od_end"], m.vars.get("od_catch", 0), m.vars.get("od_sealed", 0)),
                         (mission.END_ANVIL, 0, 0))
        self.assertEqual(m.t, 2601)                       # still waiting at the run's end: the backstop never fired

    def test_model_sealed_just_before_the_backstop(self):
        """Both necks sealed 10 s before the backstop: the backstop never fires (no od_dback, even long after), and the
        pocket surrenders at T_hold, 15:00 after the seal."""
        world = World(rings={"OD_RingPlainC": [(0, 30, 0)]}, groups={"od_mb": [(0, 30)]})
        m = self.pocket_run(world, sealed=(1590, 1500), until=2600)
        self.assertEqual(m.when("dialog"), [])
        self.assertIn(m.when("vanish")[0] - (1590 + 900), (0, 1))
        self.assertEqual((m.vars["od_catch"], m.vars["od_end"]), (60, mission.END_TOTAL))

    def test_model_phases_3_and_4_together(self):
        """The phase-3 and pocket beats side by side, the seals from P5 itself: the spring at 1:40, player units holding
        both necks; both sealed at 2:10 (P5 done x2), the pocket's 30 Soviet vehicles counted then (Medium: it gives up
        at 10); the pocket falls to 8 at 6:40: P6 done [8, 10], the pocket removed, the CATCH done [43, 60] (25 alive):
        Total. Every count before the removal; the P5 rows done before the ending."""
        ctx = mission.Ctx()
        world = World(units={"OD_CZ_NeckMid": [(0, 0, 2)], "OD_CZ_NeckS": [(0, 0, 2)]},
                      rings={"OD_RingPlainC": [(0, 30, 0), (400, 8, 0)]}, groups={"od_mb": [(0, 25)]})
        root = g_simul([*self.at(ctx, od_sprung=100), mission.phase3(ctx), mission.pocket(ctx)])
        m = Model(world, {"od_surr_pct": 35}).play(root, 700)
        self.assertEqual([e[1:3] for e in m.log if e[1] in ("done", "failed")],
                         [("done", "od_p5m"), ("done", "od_p5s"), ("done", "od_p6"), ("done", "od_catch")])
        self.assertEqual((m.vars["od_sealed_n"], m.vars["od_surr_n"], m.vars["od_sealed"]), (30, 10, 1))
        (p6,) = [e for e in m.log if e[1:3] == ("done", "od_p6")]
        self.assertEqual(p6[3], [8, 10])
        vanish = next(k for k, e in enumerate(m.log) if e[1] == "vanish")
        self.assertEqual([e for e in m.log[vanish:] if e[1] == "count"], [])
        (catch,) = [e for e in m.log if e[2:3] == ("od_catch",)]
        self.assertEqual((catch[3], m.vars["od_end"]), ([43, 60], mission.END_TOTAL))
        self.assert_one_at_a_time(self.hints(m))

    def test_model_grade_table(self):
        """The grade, through the script's own arithmetic, against `grade` (plain Python) over a table of cases: the
        Total, Major and Minor bands at their edges (42 and 24 of 60), the clamp of a pocket count above the main body
        still alive, an empty pocket at the seal, and the backstop (Total out of reach)."""
        cases = {                     # (alive, sealed_n, pocket at the surrender, sealed, pct)
            "total": (20, 30, 10, True, 35),
            "major, one short of total": (30, 30, 11, True, 35),
            "total at its edge": (30, 30, 12, True, 35),
            "major at its edge": (50, 40, 14, True, 35),
            "minor, one short of major": (50, 40, 13, True, 35),
            "pocket above alive (clamped)": (5, 20, 8, True, 35),
            "empty pocket at the seal": (40, 0, 0, True, 35),
            "easy share": (30, 30, 13, True, 45),
            "hard share": (30, 30, 7, True, 25),
            "backstop major": (10, 30, 30, False, 35),
            "backstop at major's edge": (36, 30, 30, False, 35),
            "backstop minor": (37, 30, 30, False, 35),
        }
        for name, (alive, sealed_n, left, sealed, pct) in cases.items():
            with self.subTest(case=name):
                world = World(rings={"OD_RingPlainC": [(0, sealed_n, 0), (400, left, 0)]},
                              groups={"od_mb": [(0, alive)]})
                m = self.pocket_run(world, sealed=(200, 200) if sealed else (None, 200), pct=pct, until=2600)
                catch, end = grade(alive, left, sealed)
                if sealed:                     # at the surrender point (the round at 6:40), else at T_hold
                    self.assertEqual(m.vars["od_surr_n"], surrender_point(sealed_n, pct))
                    want = 400 if left <= surrender_point(sealed_n, pct) else 200 + int(mission.T_HOLD_S)
                    want = 200 if sealed_n <= surrender_point(sealed_n, pct) else want
                    self.assertIn(m.when("vanish")[0] - want, (0, 1, 2, 3))
                self.assertEqual((m.vars["od_catch"], m.vars["od_end"]), (catch, end))
                (row,) = [e for e in m.log if e[2:3] == ("od_catch",)]
                self.assertEqual((row[1], row[3]), ("done" if catch >= 24 else "failed", [catch, 60]))
                self.assertEqual(len(m.when("vanish")), 1 if sealed else 0)

    def test_strings(self):
        """Phase 3 and 4's texts in both languages: P5 shows the held seconds out of SEAL_HOLD_S, P6 and the CATCH two
        numbers, the dialogs none; the backstop's dialog and P6 name their times; each seal hint has its "fixed" twin,
        which promises nothing about reinforcements; Major and Minor's dialogs claim no shut door (the backstop ends
        with it open)."""
        loc, dialogs = mission.STRINGS["Scripting/Localization"], mission.STRINGS["Scripting/Dialog"]
        for tok in ("od_hjaw", "od_p5m", "od_p5ml", "od_p5s", "od_p5sl", "od_hsm", "od_hsm_f", "od_hss", "od_hss_f",
                    "od_p6", "od_p6l", "od_catch", "od_catchl"):
            with self.subTest(token=tok):
                self.assertTrue(all(loc[tok].values()))
        for tok in ("od_p5m", "od_p5ml", "od_p5s", "od_p5sl"):
            self.assertEqual([re.findall(r"%\d", text) for text in loc[tok].values()], [["%1"]] * 2)
            self.assertTrue(all(f"%1 / {int(mission.SEAL_HOLD_S)} " in text for text in loc[tok].values()))
        for tok in ("od_p6", "od_p6l", "od_catch", "od_catchl"):
            self.assertEqual([sorted(re.findall(r"%\d", text)) for text in loc[tok].values()], [["%1", "%2"]] * 2)
        self.assertIn(f"{int(mission.T_HOLD_S // 60)} min", loc["od_p6"].US)
        self.assertIn(f"{int(mission.SEAL_HOLD_S)} s", loc["od_hjaw"].US)
        self.assertIn(f"{int(mission.BACKSTOP_S // 60)} minutes", dialogs["od_dback"].US)
        for tok in ("od_dcode", "od_dback", "od_dmajor", "od_dminor"):
            self.assertNotRegex("".join(dialogs[tok].values()), r"%\d")
        for tok in ("od_hsm", "od_hss"):
            self.assertIn("reinforcements arrive there again", loc[tok].US)
            self.assertNotIn("reinforcements", loc[f"{tok}_f"].US)
        for tok in ("od_dmajor", "od_dminor"):
            self.assertNotIn("door", dialogs[tok].US.lower())
        self.assertTrue(all(word in dialogs["od_dcode"].US for word in ("M1A1HA", "Leopard 2A4", "OH-58D", "A-10")))




if __name__ == "__main__":
    unittest.main()
