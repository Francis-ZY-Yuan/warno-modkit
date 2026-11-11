"""The script gates of modkit.ops.gates on small synthetic scripts: never-finishing actions and objectives, the
empty-group guard, dialog text, zone tags, smart orders and script effects. Each case builds only toolkit nodes (the
script effects' GameFx file too); none reads stock data.
"""
import dataclasses
import os
import tempfile
import unittest
from typing import Callable
from unittest import mock

from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.ops.bricks import (
    c_type, g_and, g_cmp, g_compete, g_detect, g_dialog, g_fx, g_hint, g_if, g_or, g_seq, g_simul, g_until, g_vanish,
    g_wait,
)
from modkit.ops.build import details_files
from modkit.ops.gates import (
    END_GAME, GROUP_UNION, NEVER_FINISH, STOCK_BLOCKING_OBJECTIVES, check_dialog_text, check_empty_group_guard,
    check_never_finishing, check_script_effects, check_smart_orders, check_zone_tags, gamefx_declarations,
    never_finishing_violations, polygons_overlap, smart_order_violations, zone_tag_violations,
)
from modkit.ops.graph import TRUE, Imp, Node, Str, build_graph, encode, i32, loc
from modkit.ops.leveldesign import LdItem, gd_tags
from modkit.ops.script import FOREVER
from modkit.ops.zones import rect_polygon
from test_build import profile

S, NS = "challenge_ModkitTest", "test-a"
PROFILE = profile(NS)


def zone(name: str, addon: str, box: tuple[float, float, float, float], **kw) -> LdItem:
    """A zone item over a world box, the item at its centre."""
    x0, y0, x1, y1 = box
    return LdItem(addon, name, (x0 + x1) / 2, (y0 + y1) / 2, addon, polygon=tuple(rect_polygon(box)), **kw)


def seize(group: Node, zone_tag: Node) -> Node:
    """LaunchSmartOrder Seize (TheDieburgSalient #519: Position, SmartOrderType 1, UnitGroup)."""
    return Node("TGDDescriptorLaunchSmartOrder", [("Position", zone_tag), ("SmartOrderType", i32(1)),
                                                  ("UnitGroup", group)])


def objective(name: str = "od_o1", **props: object) -> Node:
    """A GereObjectif named `name` (ObjectiveText) with the given properties (ActionsReussi, ConditionEchec, ...)."""
    return Node("TGDDescriptorGereObjectif", [*sorted(props.items()), ("ObjectiveText", loc(name))])


class NeverFinishing(unittest.TestCase):
    """Gate 3: an action that never finishes by itself (NEVER_FINISH) must not hold up a Sequential or a loop, and
    no ModifyUnit* sits in a Sequential. Seen in play: every enemy beat applied SetEffect(UnitEffect_revealUnit) right
    after its first create, and stopped there."""

    group = Node("TGDVariableUnitGroup", export="$/GDScript/OD/Variables/od_g")

    def effect(self) -> Node:
        return Node("TGDDescriptorSetEffect", [("Effet", Imp("$/GFX/EffectCapacity/UnitEffect_revealUnit")),
                                                    ("UnitGroup", [self.group])])

    def act(self, cls: str) -> Node:
        return Node(f"TGDDescriptor{cls}", [("Group", self.group)])

    def test_node_after_it_fails(self):
        """The shape seen in play, and the same for every class of NEVER_FINISH but TriggerEndGame."""
        with self.assertRaisesRegex(CheckError, r"(?s)SetEffect\(UnitEffect_revealUnit, od_g\): what follows it "
                                                     r"in its Sequential never runs \(1: MoveUnitGroup\(od_g\)\).*"
                                                     r"Move each into a Simultaneous beside the rest of its beat"):
            check_never_finishing([g_seq([self.act("CreateUnitOnPosition"), self.effect(),
                                                    self.act("MoveUnitGroup")])])
        for cls in sorted(NEVER_FINISH - {END_GAME}):
            with self.subTest(cls=cls), self.assertRaisesRegex(CheckError, cls.removeprefix("TGDDescriptor")):
                check_never_finishing([g_seq([Node(cls), g_wait(1.0)])])

    def test_income_and_combat_group_locks(self):
        """LockIncome and LockCombatGroup never finish either ([[seteffect-never-finishes]] lists both): one followed in
        a Sequential fails, the freeze the flow research found the gate let through before; stock's shape passes,
        TheWingedHussars #165's Competition[LockIncome, WaitCondition] with the Sequential going on after it."""
        camp = Node("TGDVariableCamp", export="$/GDScript/RootDescriptor/joueur")
        for cls in ("LockIncome", "LockCombatGroup"):
            lock = lambda: Node(f"TGDDescriptor{cls}", [("Camp", camp)])  # noqa: E731
            with self.subTest(cls=cls):
                with self.assertRaisesRegex(CheckError, rf"\n  {cls}: what follows it in its Sequential never runs "
                                                        r"\(1: SetAmmo\(od_g\)\)"):
                    check_never_finishing([g_seq([lock(), self.act("SetAmmo")])])
                race = g_compete([lock(), g_until(g_cmp(self.group))])
                self.assertEqual(check_never_finishing([g_seq([race, self.act("SetAmmo")])]), 1)

    def test_in_a_loop_with_others_fails(self):
        """Last in its loop but not alone: the loop never comes round (a re-apply loop)."""
        with self.assertRaisesRegex(CheckError, rf"looping Sequential \(NbExecutions {FOREVER:#x}\) beside 1 other"):
            check_never_finishing([g_seq([g_wait(30.0), self.effect()], runs=FOREVER)])

    def test_modify_unit_in_a_sequential_fails(self):
        with self.assertRaisesRegex(CheckError, r"ModifyUnitSpeed\(od_g\) is in a Sequential"):
            check_never_finishing([g_seq([self.act("CreateUnitOnPosition"), self.act("ModifyUnitSpeed")])])

    def test_stock_placements_pass(self):
        """Stock's shapes pass, and the gate counts the never-finishing actions it checked."""
        roots = [
            # BlackHorsesLastStand Sequential#185, and a reveal (Simultaneous[SetEffect, ...]) after it
            g_seq([self.act("CreateUnitOnPosition"),
                        g_simul([self.act("ModifyUnitSpeed"), self.act("LaunchSmartOrder")])]),
            g_seq([self.act("CreateUnitOnPosition"), g_simul([self.effect(),
                                                                        g_seq([self.act("MoveUnitGroup")])])]),
            # the Army General race (CS_Airborne Competition#542), then the Sequential goes on
            g_seq([g_compete([g_until(g_cmp(self.group)), self.effect(),
                                        self.act("DrawLabelOnPosition")]), self.act("ChangePawnActionPoint")]),
            g_seq([self.act("CreateUnitOnPosition"), self.effect()]),  # last in its Sequential (tuto_2 #125)
            # alone in its loop, raced (the tutorials' pawn labels)
            g_compete([g_seq([self.act("DrawLabelOnPosition")], runs=FOREVER),
                            g_until(g_cmp(self.group))]),
            g_seq([self.act("SetAmmo"), g_wait(1.0)], runs=FOREVER),  # instantaneous: may go on
        ]
        self.assertEqual(check_never_finishing(roots), 5)

    def test_after_end_game_is_exempt(self):
        """The game ends at TriggerEndGame (GloryOrAttrition #154 is followed by an EncapsuleCutscene)."""
        roots = [g_seq([Node(END_GAME), Node("TGDDescriptorEncapsuleCutscene")])]
        self.assertEqual(check_never_finishing(roots), 1)

    def reveal(self) -> Node:
        """A reveal: Simultaneous[SetEffect, Sequential[the rest]]."""
        return g_simul([self.effect(), g_seq([self.act("MoveUnitGroup")])])

    def fails_after(self, container: Node, path: str) -> None:
        """`container`, followed by a node in a Sequential, fails as never finishing, through `path`."""
        with self.assertRaisesRegex(CheckError, rf"\n  {path}[^:\n]* \(never finishes\): what follows it in its "
                                                     r"Sequential never runs \(1: SetAmmo\(od_g\)\)"):
            check_never_finishing([g_seq([container, self.act("SetAmmo")])])

    def passes_after(self, container: Node) -> None:
        roots = [g_seq([container, self.act("SetAmmo")])]
        self.assertEqual(never_finishing_violations(roots)[1], [])

    def test_node_after_a_stalling_simultaneous_or_sequential_fails(self):
        """A node after a reveal's Simultaneous never runs, as one after its SetEffect does; so
        does one after a Sequential holding a never-finishing node, even last in it."""
        effect = r"SetEffect\(UnitEffect_revealUnit, od_g\)"
        self.fails_after(self.reveal(), rf"Simultaneous > {effect}")
        self.fails_after(g_seq([self.act("CreateUnitOnPosition"), self.reveal()]),
                         rf"Sequential > Simultaneous > {effect}")
        self.passes_after(g_simul([self.act("MoveUnitGroup"), g_seq([self.act("CreateUnitOnPosition")])]))

    def test_competition_stalls_only_if_every_child_does(self):
        """A Competition finishes with its first child: it never finishes only when none of them does."""
        self.fails_after(g_compete([self.reveal(), self.act("DrawLabelOnPosition")]),
                         r"Competition > Simultaneous > SetEffect")
        self.passes_after(g_compete([self.reveal(), g_wait(5.0)]))
        self.passes_after(g_compete([g_until(g_cmp(self.group)), self.effect()]))  # the lock race

    def test_if_then_else_stalls_only_if_every_branch_does(self):
        """Only one branch runs: an IfThenElse never finishes when every branch never does. An absent branch
        finishes at once."""
        cond = g_cmp(self.group)
        self.fails_after(g_if(cond, self.reveal(), g_simul([Node("TGDDescriptorWaitForEver")])),
                         r"IfThenElse > Simultaneous > SetEffect")
        self.passes_after(g_if(cond, self.reveal()))
        self.passes_after(g_if(cond, self.reveal(), g_seq([g_wait(1.0)])))

    def test_stalling_container_in_a_loop_fails_unless_alone(self):
        with self.assertRaisesRegex(CheckError, r"Simultaneous > SetEffect.*\(never finishes\): it sits in a "
                                                     r"looping Sequential"):
            check_never_finishing([g_seq([g_wait(30.0), self.reveal()], runs=FOREVER)])
        self.assertEqual(never_finishing_violations([g_seq([self.reveal()], runs=FOREVER)])[1], [])

    def test_container_that_ends_the_game_is_exempt(self):
        """A container that never finishes only because the game ends in it is TriggerEndGame's exemption (the hold
        skeleton's ending, Sequential[ForceDisplayUIElement, TriggerEndGame]); a stall beside the end is not."""
        end = g_seq([Node("TGDDescriptorForceDisplayUIElement"), Node(END_GAME)])
        self.passes_after(end)
        self.passes_after(g_compete([self.effect(), end]))
        self.fails_after(g_simul([self.effect(), end]), r"Simultaneous > SetEffect")


class ObjectivesWait(unittest.TestCase):
    """Gate 3: an objective finishes only once it resolves and its chosen action finishes, so one in a Sequential
    holds what follows it, as does a container that waits on one: a beat that stalls silently on an objective
    mid-Sequential."""

    group = Node("TGDVariableUnitGroup", export="$/GDScript/OD/Variables/od_g")

    def after(self) -> Node:
        return g_hint("od_h", 15.0, "shint")

    def end(self) -> Node:
        return g_seq([Node("TGDDescriptorForceDisplayUIElement"), Node(END_GAME)])

    def test_node_after_an_objective_fails(self):
        with self.assertRaisesRegex(CheckError, r"(?s)\n  GereObjectif\(od_o1\) \(waits on an objective\): what "
                                                     r"follows it in its Sequential waits until the objective resolves "
                                                     r"and its chosen action finishes \(1: LDHint\).*"
                                                     r"Content.blocking_objectives \(Sledgehammer #373\)"):
            check_never_finishing([g_seq([objective(), self.after()])])

    def test_container_that_waits_on_one_fails(self):
        """The beat shape (a Simultaneous of objectives) and a chain waiting through ActionsReussi, an IfThenElse
        branch, or a Sequential holding the objective last."""
        chained = objective("od_o2", ActionsReussi=g_simul([objective("od_o3")]))
        for container, path in (
                (g_simul([self.after(), objective()]), r"Simultaneous > GereObjectif\(od_o1\)"),
                (g_simul([chained]), r"Simultaneous > GereObjectif\(od_o2\)"),
                (g_if(g_cmp(self.group), g_simul([objective()])),
                 r"IfThenElse > Simultaneous > GereObjectif\(od_o1\)"),
                (g_seq([g_wait(1.0), objective()]), r"Sequential > GereObjectif\(od_o1\)")):
            with self.subTest(path=path), self.assertRaisesRegex(
                    CheckError, rf"\n  {path} \(waits on an objective\): what follows it in its Sequential "
                                     r"waits until the objective resolves"):
                check_never_finishing([g_seq([container, self.after()])])

    def test_in_a_loop_beside_others_fails(self):
        with self.assertRaisesRegex(CheckError, r"GereObjectif\(od_o1\) \(waits on an objective\): it sits in a "
                                                     rf"looping Sequential \(NbExecutions {FOREVER:#x}\) beside 1 other "
                                                     r"nodes, which repeat only once the objective resolves"):
            check_never_finishing([g_seq([g_wait(2.0), objective()], runs=FOREVER)])

    def test_reviewed_objective_passes(self):
        """Content.blocking_objectives names an objective that gates the next phase on purpose (Sledgehammer #373's
        shape); the content list adds to the stock table, and only the named objective is admitted."""
        roots = [g_seq([objective(), self.after()])]
        self.assertEqual(check_never_finishing(roots, ["od_o1"]), 0)
        with self.assertRaisesRegex(CheckError, r"GereObjectif\(od_o1\)"):
            check_never_finishing(roots, ["od_o9"])
        self.assertIn("odvaMtR9hm", STOCK_BLOCKING_OBJECTIVES)

    def test_placements_that_pass(self):
        roots = [
            g_seq([g_wait(1.0), objective()]),                                # last in its Sequential
            g_seq([g_wait(1.0), g_simul([self.after(), objective(),      # the beat shape, last
                                                        objective("od_o2", ActionsReussi=objective("od_o3"))])]),
            # a race the wait ends (the objective is retired, shown as Ended): the Sequential goes on
            g_seq([g_compete([g_until(g_cmp(self.group)), objective()]), self.after()]),
            # both actions end the game: nothing after it runs either way (Gotterdammerung Simultaneous#72, #138)
            g_seq([g_simul([objective(ActionsReussi=self.end(), ActionsEchec=self.end())]),
                        Node("TGDDescriptorEncapsuleCutscene")]),
        ]
        self.assertEqual(never_finishing_violations(roots, frozenset())[1], [])

    def test_objective_whose_actions_stall(self):
        """Resolved either way, it starts an action that never finishes: what follows never runs."""
        effect = Node("TGDDescriptorSetEffect", [("Effet", Imp("$/GFX/EffectCapacity/UnitEffect_revealUnit")),
                                                     ("UnitGroup", [self.group])])
        stalls = objective(ActionsReussi=g_simul([effect]), ActionsEchec=g_simul([effect]))
        with self.assertRaisesRegex(CheckError, r"GereObjectif\(od_o1\) > Simultaneous > SetEffect\(UnitEffect_"
                                                     r"revealUnit, od_g\) \(never finishes\): what follows it in its "
                                                     r"Sequential never runs"):
            check_never_finishing([g_seq([stalls, self.after()])])

class EmptyGroupGuard(unittest.TestCase):
    """Gate 3: an objective resolves at its Start if a condition already holds, so a ConditionEchec on an empty
    group (the player has bought nothing yet) fails it on the first frame: the defeat guard firing during
    deployment."""

    group = Node("TGDVariableUnitGroup", export="$/GDScript/OD/Variables/Groupe_Joueur")
    other = Node("TGDVariableUnitGroup", export="$/GDScript/OD/Variables/od_g")

    def guard(self, group: Node | None = None) -> Node:
        return g_until(g_cmp(group or self.group, 1, 2))   # WaitCondition(group >= 1)

    def defeat(self, echec: Node | None = None) -> Node:
        return objective("od_o7", ConditionEchec=echec or g_cmp(self.group))   # group == 0

    def fails(self, roots: list[Node]) -> None:
        with self.assertRaisesRegex(CheckError, r"(?s)1 objectives fail on the first frame.*\n  "
                                                     r"GereObjectif\(od_o7\): its ConditionEchec holds while "
                                                     r"Groupe_Joueur is empty, and no WaitCondition\(Groupe_Joueur "
                                                     r">= 1\) comes before it in an ancestor Sequential.*"
                                                     r"as hold_script does"):
            check_empty_group_guard(roots)

    def test_guarded_shapes_pass(self):
        later = g_seq([self.guard(), g_wait(1.0), g_simul([g_seq([g_wait(5.0),
                                                                                      self.defeat()])])])
        both = g_seq([g_until(g_and(g_cmp(self.other, 1, 2), g_cmp(self.group, 0, 4))),
                           self.defeat()])                                     # And[..., Groupe_Joueur > 0]
        for roots in ([g_seq([self.guard(), self.defeat()])], [later], [both]):
            with self.subTest(roots=roots):
                self.assertEqual(check_empty_group_guard(roots), 1)
        negated = self.defeat(Node("TGDConditionNone", [("SousConditions", [g_cmp(self.group)])]))
        self.assertEqual(check_empty_group_guard([negated]), 0)            # holds only while not empty
        self.assertEqual(check_empty_group_guard([self.defeat(g_cmp(self.group, 3, 2))]), 0)  # >= 3

    def test_unguarded_shapes_fail(self):
        ob = self.defeat()
        for roots in ([g_seq([g_wait(1.0), ob])],                    # no guard
                      [g_seq([self.guard(self.other), ob])],              # another group's
                      [g_seq([ob, self.guard()])],                        # after it
                      [g_simul([self.guard(), ob])],                      # beside it, not before
                      [g_seq([g_until(g_cmp(self.group, 0, 2)), ob])],   # >= 0 holds while empty
                      [g_simul([g_seq([self.guard(), ob]), g_seq([ob])])]):  # a second, bare path
            with self.subTest(roots=roots):
                self.fails(roots)
        for echec in (g_or(g_cmp(self.other, 5, 2), g_cmp(self.group, op=3)),   # Or[..., <= 0]
                      g_cmp(self.group, 1, 5)):                                          # < 1
            with self.subTest(echec=echec):
                self.fails([self.defeat(echec)])

class DialogText(unittest.TestCase):
    """Gate 3: a dialog's text takes no variables, so %1..%9 would show as is."""

    def test_placeholder_in_a_dialog_fails(self):
        roots = [g_dialog("od_ask")]
        for pair in (("Spring the trap? %1 in the sack", "现在？"), ("Spring the trap now?", "包围圈内%2")):
            with self.subTest(pair=pair), self.assertRaisesRegex(
                    CheckError, r"(?s)1 dialog texts hold a %1\.\.%9 placeholder.*\n  od_ask: .*%[12].*ListVariables"):
                check_dialog_text(roots, {"Scripting/Dialog": {"od_ask": pair}})

class ZoneTags(unittest.TestCase):
    """Gate 3: a zone tag outside its zone makes the condition false forever, with no error."""

    box_a, box_b = (500000, 500000, 600000, 600000), (600000, 500000, 700000, 600000)  # side by side, one edge shared
    zone = staticmethod(zone)

    def setUp(self):
        self.cz_a = self.zone("OD_CZ_A", "CommandPoints", self.box_a, points=1)
        self.cz_b = self.zone("OD_CZ_B", "CommandPoints", self.box_b, points=1)
        self.inside = LdItem("Tags", "OD_In", 550000, 550000, "Name")
        self.outside = LdItem("Tags", "OD_Out", 800000, 550000, "Name")
        self.ring = LdItem("CircularZones", "OD_Ring", 550000, 550000, "CircularZone", radius_gru=50.0)

    def violations(self, items: list[LdItem], build: Callable[[dict[str, Node]], list[Node]]
                   ) -> tuple[dict[str, int], list[str]]:
        tags = {k.split("/", 1)[1]: v for k, v in gd_tags(items, S, NS).items()}
        return zone_tag_violations(build(tags), details_files(PROFILE, items, S))

    @staticmethod
    def control(tag: Node, zone_type: int | None = 1) -> Node:
        props = [("Position", tag), ("AutoriseControleAllie", TRUE)]
        return Node("TGDConditionTeamControleZone", props + ([("ZoneType", i32(zone_type))]
                                                                  if zone_type else []))

    def test_tags_inside_pass(self):
        items = [self.cz_a, self.cz_b, self.inside, self.ring]
        counts, bad = self.violations(items, lambda t: [g_simul([
            g_until(self.control(t["OD_In"])),
            g_until(Node("TGDConditionUnitDansZone", [("Detecteurs", [t["OD_CZ_A"], t["OD_CZ_B"]]),
                                                                 ("ZoneType", i32(1))])),
            Node("TGDDescriptorSetCommandZoneOwnerAndForceConvergence", [("Positions", [t["OD_CZ_A"]])]),
            g_until(g_detect(t["OD_Ring"], c_type("BRDM_2_SOV"), 1, 2))])])
        self.assertEqual((counts, bad), ({"zone lookups": 4, "detectors": 1, "zone items": 2, "command zones": 2}, []))

    def test_misplaced_tags_fail(self):
        """A tag outside every zone, a deployment-zone lookup (ZoneType omitted = 0) with no deployment zone, a
        command-zone owner change on a point that is no zone, and a detector that is no circle."""
        items = [self.cz_a, self.inside, self.outside]
        _, bad = self.violations(items, lambda t: [g_simul([
            g_until(self.control(t["OD_Out"])), g_until(self.control(t["OD_In"], None)),
            Node("TGDDescriptorSetCommandZoneOwnerAndForceConvergence", [("Positions", [t["OD_Out"]])]),
            g_until(g_detect(t["OD_In"], c_type("BRDM_2_SOV"), 1, 2))])])
        self.assertEqual(bad, [
            "TeamControleZone.Position Tags/OD_Out at (800,000, 550,000) lies in 0 polygons of out/CommandZone.ndfbin, "
            "not exactly one",
            "TeamControleZone.Position Tags/OD_In at (550,000, 550,000) lies in 0 polygons of "
            "out/DeploymentZone.ndfbin, not exactly one",
            "SetCommandZoneOwnerAndForceConvergence.Positions Tags/OD_Out at (800,000, 550,000) lies in 0 polygons of "
            "out/CommandZone.ndfbin, not exactly one",
            "DetectUnitDansDetecteur.Detecteur Tags/OD_In is a Name item, not a CircularZone with a radius"])
        tags = {k.split("/", 1)[1]: v for k, v in gd_tags(items, S, NS).items()}
        with self.assertRaisesRegex(CheckError, r"(?s)1 zone tags or zones the game would look up wrong.*"
                                                     r"exactly one zone polygon"):
            check_zone_tags([self.control(tags["OD_Out"])], details_files(PROFILE, items, S))

    def test_zone_items_and_overlaps(self):
        """A zone item whose point lies outside its own polygon, and two command zones that share area (a tag in the
        overlap lies in both); zones that only share an edge pass."""
        astray = dataclasses.replace(self.cz_a, x=650000.0)                    # its point in box B, not its own box
        _, bad = self.violations([astray, self.cz_b], lambda t: [])
        self.assertEqual(bad, ["CommandPoints/OD_CZ_A: its point (650,000, 550,000) lies outside its own polygon"])
        wide = self.zone("OD_CZ_B", "CommandPoints", (580000, 500000, 700000, 600000), points=1)
        in_both = LdItem("Tags", "OD_Both", 590000, 550000, "Name")
        _, bad = self.violations([self.cz_a, wide, in_both], lambda t: [g_until(self.control(t["OD_Both"]))])
        self.assertEqual(bad, ["TeamControleZone.Position Tags/OD_Both at (590,000, 550,000) lies in 2 polygons of "
                               "out/CommandZone.ndfbin (OD_CZ_A, OD_CZ_B), not exactly one",
                               "command zones OD_CZ_A and OD_CZ_B overlap"])
        self.assertFalse(polygons_overlap(self.cz_a.polygon, self.cz_b.polygon))
        self.assertTrue(polygons_overlap(self.cz_a.polygon, self.cz_a.polygon))   # one on the other
        small = tuple(rect_polygon((520000, 520000, 540000, 540000)))
        self.assertTrue(polygons_overlap(self.cz_a.polygon, small))               # one inside the other

class SmartOrders(unittest.TestCase):
    """Gate 3, check_smart_orders: no GiveOrderStandard, MoveUnitGroup or LaunchSmartOrder orders a group again
    after a LaunchSmartOrder on it (or on a group sharing its units) in the same Sequential. No stock script does, so
    what the AI does with a smart-ordered group ordered again is unknown."""

    @staticmethod
    def group(name: str) -> Node:
        return Node("TGDVariableUnitGroup", export=f"$/GDScript/OD/Variables/{name}")

    def setUp(self):
        self.g, self.h, self.u = self.group("od_g"), self.group("od_h"), self.group("od_u")
        self.zone = Node("TGDTagPosition", export="$/GDScript/GdItems/CommandPoints/OD_CZ")

    def seize(self, group: Node) -> Node:
        return seize(group, self.zone)

    def move(self, group: Node) -> Node:
        return Node("TGDDescriptorMoveUnitGroup", [("Group", group), ("Positions", [self.zone])])

    def order(self, group: Node) -> Node:
        return Node("TGDDescriptorGiveOrderStandard", [("Group", group), ("OrderType", i32(12)),
                                                            ("Position", self.zone)])

    def union(self, into: Node, *groups: Node) -> Node:
        return Node(GROUP_UNION, [("GroupDestination", into), ("ListGroupSource", list(groups))])

    def test_reorders_fail(self):
        """Each order class after a Seize on the same group, also nested in a later child; and through a union, both
        ways (the union may sit anywhere in the script)."""
        wait = g_wait(5.0)
        cases = {
            "MoveUnitGroup(od_g) comes after LaunchSmartOrder(od_g) in one Sequential":
                [g_seq([self.seize(self.g), wait, self.move(self.g)])],
            "GiveOrderStandard(od_g) comes after LaunchSmartOrder(od_g) in one Sequential":
                [g_seq([g_simul([self.seize(self.g)]), g_simul([g_seq([self.order(self.g)])])])],
            "LaunchSmartOrder(od_g) comes after LaunchSmartOrder(od_g) in one Sequential":
                [g_seq([self.seize(self.g), g_if(g_cmp(self.h), self.seize(self.g))])],
            "GiveOrderStandard(od_u) comes after LaunchSmartOrder(od_g) in one Sequential (od_u and od_g share units)":
                [self.union(self.u, self.g, self.h), g_seq([self.seize(self.g), self.order(self.u)])],
            "MoveUnitGroup(od_g) comes after LaunchSmartOrder(od_u) in one Sequential (od_g and od_u share units)":
                [g_seq([self.union(self.u, self.h), self.seize(self.u), self.union(self.h, self.g),
                             self.move(self.g)])],
        }
        for line, roots in cases.items():
            with self.subTest(line=line):
                self.assertEqual(smart_order_violations(roots)[1], [line])
        with self.assertRaisesRegex(CheckError, r"(?s)1 orders re-order a group after its smart order.*44 "
                                                     r"groups\):\n  MoveUnitGroup\(od_g\) comes after "
                                                     r"LaunchSmartOrder\(od_g\).*Give the group its route first"):
            check_smart_orders(cases["MoveUnitGroup(od_g) comes after LaunchSmartOrder(od_g) in one Sequential"])

    def test_orders_that_pass(self):
        """The route before the smart order, an order on another group, orders beside the Seize in a Simultaneous
        or in another branch (Marauders' Event_Art_POL), and a removal after the Seize."""
        roots = [g_seq([self.order(self.g), self.move(self.g), self.seize(self.g), self.order(self.h)]),
                 g_simul([self.seize(self.h), self.move(self.h)]),
                 g_simul([g_seq([self.seize(self.u)]), g_seq([g_wait(1.0), self.order(self.u)])]),
                 g_seq([self.seize(self.g), g_vanish(self.g)])]
        self.assertEqual(smart_order_violations(roots), (3, []))
        self.assertEqual(check_smart_orders(roots), 3)


class ScriptEffects(unittest.TestCase):
    """Gate 3, script effects: every effect a script launches is a self-contained export of the game's GameFx file.
    The fixture is a small synthetic GameFx file: one effect that takes no parameters, and one whose declaration takes
    two (an NDF Params block, which compiles to InputParameters of TActionAlias), as the tactical-nuke impact effects
    do. Seen in play: a script launch of such an effect crashed the game."""

    FX = "$/GFX/GameFx/"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.gamefx = os.path.join(self.tmp.name, "GameFx.ndfbin")

        def alias(name: str) -> Node:
            return Node("TActionAlias", [("_ShortDatabaseName", Str(name)), ("ExpectedType", Str("float3"))])

        plain = Node("TSimultaneousAction", [("_ShortDatabaseName", Str("fx_Plain")), ("Actions", [])],
                     export=self.FX + "fx_Plain")
        param = Node("TSimultaneousActionForActionCallTemplate", [
            ("InputParameters", [alias("parPosition"), alias("parRadius")]), ("_ShortDatabaseName", Str("fx_Param")),
            ("Actions", [])], export=self.FX + "fx_Param")
        with open(self.gamefx, "wb") as fh:
            fh.write(encode(build_graph([plain, param], [plain, param]), "GameFx"))

    def script(self, *names: str) -> bytes:
        """A GDScript launching each of `names` on one position."""
        pos = Node("TGDTagPosition", export="$/GDScript/RootDescriptor/t_fx")
        return encode(build_graph([g_seq([g_fx(name, pos) for name in names])], [pos]), "GDScript")

    def test_the_fixture_reads_as_declared(self):
        """Each effect with its parameters' names (the toolkit's writer also exports a TBaseClass per folder)."""
        declared = gamefx_declarations(self.gamefx)
        self.assertEqual({name: p for name, p in declared.items() if name.startswith(self.FX + "fx_")},
                         {self.FX + "fx_Plain": (), self.FX + "fx_Param": ("parPosition", "parRadius")})

    def test_a_self_contained_effect_passes(self):
        self.assertEqual(check_script_effects(self.script(self.FX + "fx_Plain", self.FX + "fx_Plain"), self.gamefx), 2)

    def test_a_parameterised_effect_fails(self):
        with self.assertRaisesRegex(CheckError, r"^the script launches effects a script may not launch: "
                                                r"\$/GFX/GameFx/fx_Param declares 2 parameters \(parPosition, "
                                                r"parRadius\)\. A script launch carries only the effect's name and a "
                                                r"position, and binds no parameters"):
            check_script_effects(self.script(self.FX + "fx_Plain", self.FX + "fx_Param"), self.gamefx)

    def test_a_missing_name_fails(self):
        with self.assertRaisesRegex(CheckError, r"may not launch: \$/GFX/GameFx/fx_Nope is not a GameFx export\. "):
            check_script_effects(self.script(self.FX + "fx_Nope"), self.gamefx)

    def test_one_line_names_every_bad_effect_once(self):
        """One FAILED line: each bad effect once, however often it is launched; the fix names stock's three."""
        with self.assertRaises(CheckError) as cm:
            check_script_effects(self.script(self.FX + "fx_Param", self.FX + "fx_Nope", self.FX + "fx_Param"),
                                 self.gamefx)
        message = str(cm.exception)
        self.assertNotIn("\n", message)
        self.assertEqual((message.count("fx_Param declares"), message.count("fx_Nope is not")), (1, 1))
        self.assertTrue(message.endswith("(fx_FumeeBlanche_ForScript_RandomPosition, "
                                         "fx_HE_Artillery_203mm_ForScript_RandomPosition, "
                                         "fx_FumeeNoire_ForScript_RandomPosition)"), message)

    def test_a_script_without_launches_reads_nothing(self):
        """No launch, no lookup: the GameFx file is not read, and no extraction is needed."""
        with mock.patch.object(paths, "extracted_root", side_effect=paths.NotConfigured("warno-setup")):
            self.assertEqual(check_script_effects(self.script()), 0)

    def test_without_an_extraction_it_fails_naming_setup(self):
        """A launch needs the stock GameFx: without an extraction the gate raises NotConfigured (warno-setup), and an
        extraction that lacks the file gives the missing-stock-file error naming the setup commands; the build turns
        either into one FAILED line."""
        launch = self.script(self.FX + "fx_Plain")
        with mock.patch.object(paths, "extracted_root",
                               side_effect=paths.NotConfigured("not configured: run the warno-setup skill")):
            with self.assertRaisesRegex(paths.NotConfigured, "warno-setup"):
                check_script_effects(launch)
        with tempfile.TemporaryDirectory() as empty, mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": empty}):
            with self.assertRaisesRegex(FileNotFoundError, r"^missing stock file extracted/glad_201602/NDF/GFX/"
                                                           r"GameFx\.ndfbin: .*\(the warno-setup skill\)$"):
                check_script_effects(launch)


if __name__ == "__main__":
    unittest.main()
