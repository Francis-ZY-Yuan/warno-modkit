"""Tests for modkit.ops.mission, the composed mission pieces, and the bricks lifted with them (g_union, g_spawn,
g_kill, a blocking shapes.order): each builds the node shape it built inside Open Door or a probe for one input, and
its parameters reach the node (synthetic: no stock data needed)."""
from __future__ import annotations

import unittest

from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.bricks import g_hint, g_kill, g_seq, g_spawn, g_union, unit_path
from modkit.ops.forces import formation
from modkit.ops.graph import Imp, Node, walk
from modkit.ops.maps import GEISA
from modkit.ops.mission import (
    CHOICE_NONE, Lane, Leg, Wave, after_launch, board, create_rows, difficulty, end_funnel, hidden_units, lane_route,
    placed_units, reask_loop, ring_round, script_frame, wave, zone_handover, zone_race,
)
from modkit.ops.script import BRICK_FORCE_HIDE, FOREVER, deploy_phase
from modkit.ops.shapes import (
    AIRPLANE_EVACUATE, AIRPLANE_MOVE_AND_ENGAGE, BATTLE_PHASE, DIFF_NONE, EASY, FAST_MOVE_AND_ATTACK, GE, HARD, HINT_S,
    LE, MAJOR_VICTORY, MEDIUM, PENETRATION, POLL_S, SHOOT_ON_POSITION, TOTAL_VICTORY, Beat, Ctx, Minimap, camp_nodes,
    order,
)
from modkit.ops.testing import cmp_of, end_game, last, prop, set_values, subs, token
from test_script import TEMPLATES, template   # the three-object template script of the script tests

CAMPS = (("blue", (("AllianceStyle", 0x02, 3),), "DECK_BLUE"), ("red", (("Alliance", 0x03, 1),), "DECK_RED"))
TOKENS = {"blue": "t_blue", "red": "t_red"}
MAP = Minimap(GEISA, {"HILL": (100.0, 200.0), "ROAD": (150.0, 200.0), "TOWN": (200.0, 260.0)})
ITEMS = [
    MAP.item("Tags", "T_Entry", "HILL", "Name"),
    MAP.item("Tags", "T_Road", "ROAD", "Name"),
    MAP.item("Tags", "T_Town", "TOWN", "Name"),
    MAP.zone_item("CommandPoints", "T_CZ_A", (90, 190, 110, 210), "CommandPoints", points=2),
    MAP.zone_item("CommandPoints", "T_CZ_B", (190, 250, 210, 270), "CommandPoints", points=2),
    MAP.zone_item("DeploymentZone", "T_DZ", (10, 10, 50, 50), "DeploymentZone"),
    MAP.ring_item("T_RingA", "HILL", 20.0),
    MAP.ring_item("T_RingB", "TOWN", 30.0),
]


def ctx() -> Ctx:
    return Ctx(camp_nodes(CAMPS, TOKENS), {"P": "blue", "E": "red"}, "P", ITEMS, "challenge_T", "ns", "$/GDScript/T")


def kv(node: Node) -> list[tuple[str, object]]:
    """A node's properties: scalars by value, imports by path, references by export name."""
    def one(v: object) -> object:
        if isinstance(v, Value):
            return v.v
        if isinstance(v, Imp):
            return v.path
        if isinstance(v, list):
            return [one(x) for x in v]
        return last(v) if isinstance(v, Node) and v.export else v
    return [(k, one(v)) for k, v in node.props]


class Bricks(unittest.TestCase):
    def test_union(self):
        c = ctx()
        node = g_union(c.group("all"), [c.group("a"), c.tag("T_Entry")])
        self.assertEqual((node.cls, kv(node)), ("TGDDescriptorAddUnitGroupListToUnitGroup",
                                                [("GroupDestination", "all"), ("ListGroupSource", ["a", "T_Entry"])]))

    def test_spawn(self):
        c = ctx()
        node = g_spawn([c.tag("T_Entry"), c.tag("T_Town")])
        self.assertEqual((node.cls, kv(node)), ("TGDDescriptorSpawnUnits", [("Units", ["T_Entry", "T_Town"])]))

    def test_kill_with_a_cause_or_vanished(self):
        c = ctx()
        node = g_kill(c.group("a"), cause=PENETRATION)
        self.assertEqual((node.cls, kv(node)), ("TGDDescriptorKillAllUnit",
                                                [("DeathCause", PENETRATION), ("GroupList", ["a"])]))
        self.assertEqual(kv(g_kill(c.group("a"), c.group("b"), cause=None)), [("GroupList", ["a", "b"])])

    def test_order_blocking(self):
        c = ctx()
        self.assertEqual(kv(order(c.group("a"), SHOOT_ON_POSITION, c.tag("T_Town"))),
                         [("Group", "a"), ("OrderType", SHOOT_ON_POSITION), ("Position", "T_Town")])
        self.assertEqual(kv(order(c.group("a"), FAST_MOVE_AND_ATTACK, c.tag("T_Town"), blocking=True)),
                         [("Blocking", 1), ("Group", "a"), ("OrderType", FAST_MOVE_AND_ATTACK), ("Position", "T_Town")])

    def test_aircraft_orders(self):
        """AirplaneMoveAndEngage cancelable onto a place (Survivors #1496: Group, OrderCancelable, OrderType,
        Position); AirplaneEvacuate blocking with no place (#1648: Blocking, Group, OrderType)."""
        c = ctx()
        self.assertEqual(kv(order(c.group("a"), AIRPLANE_MOVE_AND_ENGAGE, c.tag("T_Town"), cancelable=True)),
                         [("Group", "a"), ("OrderCancelable", 1), ("OrderType", 3), ("Position", "T_Town")])
        self.assertEqual(kv(order(c.group("a"), AIRPLANE_EVACUATE, None, blocking=True)),
                         [("Blocking", 1), ("Group", "a"), ("OrderType", 2)])


class HiddenUnits(unittest.TestCase):
    def test_hidden_spawns_in_formation(self):
        units = [("H_1", "M1A1HA_Abrams_US"), ("H_2", "M1A1HA_Abrams_US"), ("H_3", "Leopard_2A4_RFA")]
        items = hidden_units(MAP, (100.0, 200.0), units, 8.0, 2, "reserves")
        self.assertEqual([(it.ranking, it.name, it.addon, it.unit, it.camp, it.disable_auto_spawn, it.group)
                          for it in items],
                         [("Camp_0", name, "Spawn", unit, 0, True, "reserves") for name, unit in units])
        self.assertEqual([MAP.px_of(it) for it in items],
                         [GEISA.world_to_px(GEISA.px_to_world(p)) for p in formation((100.0, 200.0), 3, 8.0, 2)])
        wide = hidden_units(MAP, (100.0, 200.0), units, 12.0, 3, "row")
        self.assertEqual({round(MAP.px_of(it)[1], 6) for it in wide}, {200.0})   # cols 3: one row
        self.assertNotEqual([MAP.px_of(it) for it in wide], [MAP.px_of(it) for it in items])
        self.assertEqual({it.group for it in wide}, {"row"})

    def test_hidden_is_placed_hidden(self):
        units = [("H_1", "M1A1HA_Abrams_US"), ("H_2", "Leopard_2A4_RFA")]
        self.assertEqual(hidden_units(MAP, (100.0, 200.0), units, 8.0, 2, "g"),
                         placed_units(MAP, (100.0, 200.0), units, 8.0, 2, "g", hidden=True))

    def test_placed_spawns_stand_from_the_start_in_their_camp(self):
        """placed_units: ranked Camp_<camp>, Camp written, auto-spawned (no DisableAutoSpawn), each facing `rotation`,
        laid out by forces.formation as hidden_units are."""
        units = [("G_1", "Leopard_1A5_RFA"), ("G_2", "Leopard_1A5_RFA"), ("G_3", "Marder_1A3_RFA")]
        items = placed_units(MAP, (100.0, 200.0), units, 8.0, 2, "garrison", camp=3, rotation=-1.5)
        self.assertEqual([(it.ranking, it.name, it.addon, it.unit, it.camp, it.disable_auto_spawn, it.group,
                           it.rotation) for it in items],
                         [("Camp_3", name, "Spawn", unit, 3, False, "garrison", -1.5) for name, unit in units])
        self.assertEqual([MAP.px_of(it) for it in items],
                         [GEISA.world_to_px(GEISA.px_to_world(p)) for p in formation((100.0, 200.0), 3, 8.0, 2)])
        self.assertIsNone(placed_units(MAP, (100.0, 200.0), units, 8.0, 2, "g")[0].rotation)

    def test_placed_spawns_take_an_experience(self):
        """`experience` reaches each item's ExperienceLevel (Survivors' hidden strike aircraft: 2); left out, None."""
        units = [("A_1", "F15C_Eagle_AA_US"), ("A_2", "F15C_Eagle_AA_US")]
        items = placed_units(MAP, (100.0, 200.0), units, 6.0, 2, "air", camp=3, hidden=True, experience=2)
        self.assertEqual([(it.experience, it.disable_auto_spawn) for it in items], [(2, True), (2, True)])
        self.assertIsNone(placed_units(MAP, (100.0, 200.0), units, 6.0, 2, "air")[0].experience)


class Lanes(unittest.TestCase):
    def test_lane_route(self):
        """Each leg but the last: Competition[WaitDuration timeout, Sequential[GiveOrderStandard Blocking]]; the last
        a plain GiveOrderStandard. A leg's order type and timeout reach its node."""
        c = ctx()
        route = lane_route(c, c.group("w"), (Leg("T_Road", 90.0), Leg("T_Town", 60.0, 7), Leg("T_Entry", None)))
        *legs, final = subs(route)
        self.assertEqual(route.cls, "TGDDescriptorSequential")
        self.assertEqual(len(legs), 2)
        for race, (to, timeout, kind) in zip(legs, (("T_Road", 90.0, FAST_MOVE_AND_ATTACK), ("T_Town", 60.0, 7))):
            wait, wrapped = subs(race)
            (step,) = subs(wrapped)
            self.assertEqual((race.cls, wait.cls, prop(wait, "Duree").v, wrapped.cls),
                             ("TGDDescriptorCompetition", "TGDDescriptorWaitDuration", timeout,
                              "TGDDescriptorSequential"))
            self.assertEqual(kv(step), [("Blocking", 1), ("Group", "w"), ("OrderType", kind), ("Position", to)])
        self.assertEqual(kv(final), [("Group", "w"), ("OrderType", FAST_MOVE_AND_ATTACK), ("Position", "T_Entry")])

    def test_lane_route_needs_timeouts_but_the_last(self):
        c = ctx()
        for legs in ((Leg("T_Road", None), Leg("T_Town", None)), (Leg("T_Road", 60.0), Leg("T_Town", 60.0)), ()):
            with self.subTest(legs=legs), self.assertRaisesRegex(CheckError, "every leg but the last"):
                lane_route(c, c.group("w"), legs)

    def test_lane_route_with_a_final_node(self):
        """With a final node, every leg is raced against its timeout, the last too, and the final node follows, last
        in the route's Sequential; a leg with no timeout fails. Without one the route is as before."""
        c = ctx()
        final = Node("TGDDescriptorAttack")
        route = lane_route(c, c.group("w"), (Leg("T_Road", 90.0), Leg("T_Town", 120.0, 24)), final)
        *legs, last_node = subs(route)
        self.assertIs(last_node, final)
        self.assertEqual([(prop(subs(r)[0], "Duree").v, kv(subs(subs(r)[1])[0])) for r in legs],
                         [(90.0, [("Blocking", 1), ("Group", "w"), ("OrderType", FAST_MOVE_AND_ATTACK),
                                  ("Position", "T_Road")]),
                          (120.0, [("Blocking", 1), ("Group", "w"), ("OrderType", 24), ("Position", "T_Town")])])
        with self.assertRaisesRegex(CheckError, "with a final node every leg needs a timeout"):
            lane_route(c, c.group("w"), (Leg("T_Road", 90.0), Leg("T_Town", None)), final)
        plain = (Leg("T_Road", 90.0), Leg("T_Town", None))
        self.assertEqual([n.cls for n in walk([lane_route(c, c.group("w"), plain)])],
                         [n.cls for n in walk([lane_route(ctx(), ctx().group("w"), plain, None)])])


class Waves(unittest.TestCase):
    ROWS = (("T80BV_SOV", 3, None), ("BMP_2_SOV", 2, None), ("MotRifles_SOV", 2, "BMP_2_SOV"))
    LANES = {"N": Lane("T_Entry", (Leg("T_Road", 60.0), Leg("T_Town", None)))}

    def test_create_rows(self):
        """Riflemen into inf, their carriers into ifv, the rest into the group, in the side's camp at the tag."""
        c = ctx()
        group, inf, ifv = c.group("g"), c.group("g_inf"), c.group("g_ifv")
        nodes = create_rows(c, "E", self.ROWS, c.tag("T_Entry"), group, inf, ifv)
        self.assertEqual([kv(n) for n in nodes],
                         [[("Camp", "red"), ("Group", into), ("NbUnit", n), ("Position", "T_Entry"),
                           ("TypeUnit", unit_path(unit))]
                          for (unit, n, _), into in zip(self.ROWS, ("g", "g_ifv", "g_inf"))])
        self.assertEqual([last(prop(n, "Group")) for n in create_rows(c, "E", self.ROWS[:2], c.tag("T_Entry"), group)],
                         ["g", "g"])
        with self.assertRaisesRegex(CheckError, "need the inf and ifv groups"):
            create_rows(c, "E", self.ROWS, c.tag("T_Entry"), group)

    def test_board(self):
        c = ctx()
        node = board(c.group("r"), c.group("v"), 45.0)
        load, wait = subs(node)
        self.assertEqual((node.cls, load.cls, wait.cls, prop(wait, "Duree").v),
                         ("TGDDescriptorCompetition", "TGDDescriptorSequential", "TGDDescriptorWaitDuration", 45.0))
        (step,) = subs(load)
        self.assertEqual((step.cls, kv(step)), ("TGDDescriptorLoadIntoTransporter",
                                                [("Blocking", 1), ("Group", "r"), ("Targets", "v")]))

    def test_wave_with_riflemen(self):
        """Wait offset, the creates, the vehicles into <prefix>, the riflemen into <prefix>_inf, then into the wave,
        the boarding (board_s), then the lane."""
        c = ctx()
        node = wave(c, Wave(3, 120.0, "N", self.ROWS), self.LANES, side="E", prefix="x_w", board_s=25.0)
        wait, *creates, every, all_inf, joined, boarding, route = subs(node)
        self.assertEqual(prop(wait, "Duree").v, 120.0)
        self.assertEqual([last(prop(n, "Group")) for n in creates], ["x_w3", "x_w3_ifv", "x_w3_inf"])
        self.assertEqual({last(prop(n, "Camp")) for n in creates} | {last(prop(n, "Position")) for n in creates},
                         {"red", "T_Entry"})
        self.assertEqual([kv(n) for n in (every, all_inf, joined)],
                         [[("GroupDestination", "x_w"), ("ListGroupSource", ["x_w3", "x_w3_ifv"])],
                          [("GroupDestination", "x_w_inf"), ("ListGroupSource", ["x_w3_inf"])],
                          [("GroupDestination", "x_w3"), ("ListGroupSource", ["x_w3_inf", "x_w3_ifv"])]])
        self.assertEqual(prop(subs(boarding)[1], "Duree").v, 25.0)
        self.assertEqual(kv(subs(route)[-1]), [("Group", "x_w3"), ("OrderType", FAST_MOVE_AND_ATTACK),
                                              ("Position", "T_Town")])
        self.assertEqual(list(c.variables), ["x_w3", "x_w", "x_w3_inf", "x_w3_ifv", "x_w_inf"])

    def test_wave_with_orders_before_its_route_and_a_final_node(self):
        """`before_route` puts its nodes for the wave's group right before the route; `final` ends the route (every
        leg timed). Neither given: the same nodes as before."""
        lanes = {"N": Lane("T_Entry", (Leg("T_Road", 60.0), Leg("T_Town", 90.0)))}
        c = ctx()
        roe = lambda g: [Node("TGDDescriptorSetIdleROEBehavior", [("Group", g)])]  # noqa: E731
        end = lambda g: Node("TGDDescriptorAttack", [("Group", g)])  # noqa: E731
        node = wave(c, Wave(1, 0.0, "N", self.ROWS[:1]), lanes, side="E", prefix="x_w", board_s=25.0,
                    before_route=roe, final=end)
        create, every, idle, route = subs(node)
        self.assertEqual((idle.cls, last(prop(idle, "Group"))), ("TGDDescriptorSetIdleROEBehavior", "x_w1"))
        self.assertEqual((subs(route)[-1].cls, last(prop(subs(route)[-1], "Group"))), ("TGDDescriptorAttack", "x_w1"))
        self.assertEqual([n.cls for n in subs(route)[:-1]], ["TGDDescriptorCompetition"] * 2)
        bare = wave(ctx(), Wave(1, 0.0, "N", self.ROWS[:1]), self.LANES, side="E", prefix="x_w", board_s=25.0)
        hooked = wave(ctx(), Wave(1, 0.0, "N", self.ROWS[:1]), self.LANES, side="E", prefix="x_w", board_s=25.0,
                      before_route=None, final=None)
        self.assertEqual([n.cls for n in walk([bare])], [n.cls for n in walk([hooked])])

    def test_wave_without_riflemen_or_offset(self):
        c = ctx()
        node = wave(c, Wave(1, 0.0, "N", self.ROWS[:1]), self.LANES, side="E", prefix="x_w", board_s=25.0)
        create, every, route = subs(node)
        self.assertEqual((create.cls, kv(every)), ("TGDDescriptorCreateUnitOnPosition",
                                                   [("GroupDestination", "x_w"), ("ListGroupSource", ["x_w1"])]))
        self.assertEqual(route.cls, "TGDDescriptorSequential")
        self.assertEqual(list(c.variables), ["x_w1", "x_w"])

    def test_wave_tracks_types(self):
        """With `track`, the tracked types' rows go into <prefix><key>_<name>, which joins the wave and
        <prefix>_<name> before the wave joins <prefix>; a wave with none of them makes no tracked group; a tracked
        type may be neither riflemen nor carriers."""
        c = ctx()
        node = wave(c, Wave(3, 0.0, "N", self.ROWS), self.LANES, side="E", prefix="x_w", board_s=25.0,
                    track=("tanks", ("T80BV_SOV",)))
        *creates, to_wave, to_all, every, all_inf, joined, boarding, route = subs(node)
        self.assertEqual([last(prop(n, "Group")) for n in creates], ["x_w3_tanks", "x_w3_ifv", "x_w3_inf"])
        self.assertEqual([kv(n) for n in (to_wave, to_all, every)],
                         [[("GroupDestination", "x_w3"), ("ListGroupSource", ["x_w3_tanks"])],
                          [("GroupDestination", "x_w_tanks"), ("ListGroupSource", ["x_w3_tanks"])],
                          [("GroupDestination", "x_w"), ("ListGroupSource", ["x_w3", "x_w3_ifv"])]])
        none = wave(ctx(), Wave(1, 0.0, "N", self.ROWS[1:]), self.LANES, side="E", prefix="x_w", board_s=25.0,
                    track=("tanks", ("T80BV_SOV",)))
        self.assertFalse(any("tanks" in (n.export or "") for n in walk([none])))
        with self.assertRaisesRegex(CheckError, "neither riflemen nor carriers"):
            wave(ctx(), Wave(2, 0.0, "N", self.ROWS), self.LANES, side="E", prefix="x_w", board_s=25.0,
                 track=("bmp", ("BMP_2_SOV",)))


class Reask(unittest.TestCase):
    def test_reask_loop(self):
        """Forever: pick = ans = CHOICE_NONE, asking = 1, the dialog (SelectedButton = pick), ans = pick, asking = 0,
        the gap."""
        c = ctx()
        pick, ans, asking = c.int_var("p"), c.int_var("a"), c.int_var("o")
        loop = reask_loop("t_ask", ("ORD_AIARA", "ORD_HOLDF"), c.camp("P"), pick, ans, asking, 90.0)
        reset_pick, reset_ans, opened, dialog, copy, closed, gap = subs(loop)
        self.assertEqual(prop(loop, "NbExecutions").v, FOREVER)
        self.assertEqual([kv(n) for n in (reset_pick, reset_ans, opened, copy, closed)],
                         [[("Variable1", "p"), ("Value", CHOICE_NONE)], [("Variable1", "a"), ("Value", CHOICE_NONE)],
                          [("Variable1", "o"), ("Value", 1)], [("Variable1", "a"), ("Variable2", "p")],
                          [("Variable1", "o")]])
        (choice,) = prop(dialog, "DialogList")
        self.assertEqual((token(prop(choice, "TokenBoutonChoix0")), token(prop(choice, "TokenBoutonChoix1"))),
                         ("ORD_AIARA", "ORD_HOLDF"))
        self.assertIs(prop(choice, "SelectedButton"), pick)
        self.assertIs(prop(choice, "VisibleByCamp"), c.camp("P"))
        (text,) = [n for n in walk([dialog]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
        self.assertEqual(token(prop(text, "LocalizedText")), "t_ask")
        self.assertEqual(prop(gap, "Duree").v, 90.0)


class Zones(unittest.TestCase):
    def in_zones(self, cond: Node) -> tuple[str, int, int]:
        """(camp, operator, value) of a ConditionUnitDansZone, or of the one inside an And."""
        if cond.cls == "TGDConditionAnd":
            (cond,) = prop(cond, "SousConditions")
        cmp = prop(cond, "ComparaisonNbUnits")
        op, value = prop(cmp, "OperatorType"), prop(cmp, "Value")
        return last(prop(prop(cond, "Contrainte"), "Camp")), op.v if op else 0, value.v if value else 0

    def test_zone_race(self):
        """Competition[seconds_while (reset on a break), WaitCondition(held >= hold_s)]; side >= at_least and other
        none starts the streak, side < at_least or other >= 1 breaks it."""
        c = ctx()
        held = c.int_var("held")
        race = zone_race(c, ["T_CZ_A", "T_CZ_B"], "E", "P", 3, 20.0, held)
        loop, done = subs(race)
        self.assertEqual((race.cls, cmp_of(prop(done, "Condition"))), ("TGDDescriptorCompetition", ("held", GE, 20)))
        start, timer, reset = subs(loop)
        self.assertEqual(prop(subs(subs(timer)[0])[0], "Duree").v, POLL_S)
        self.assertEqual(kv(reset), [("Variable1", "held")])
        holds = prop(prop(start, "Condition"), "SousConditions")
        self.assertEqual([self.in_zones(x) for x in holds], [("red", GE, 3), ("blue", LE, 0)])
        self.assertEqual([last(t) for t in prop(holds[0], "Detecteurs")], ["T_CZ_A", "T_CZ_B"])
        broken = prop(subs(timer)[1], "Condition")
        self.assertEqual([self.in_zones(x) for x in prop(broken, "SousConditions")], [("red", LE, 2), ("blue", GE, 1)])
        flipped = zone_race(c, ["T_CZ_A"], "P", "E", 1, 5.0, held)
        self.assertEqual(cmp_of(prop(subs(flipped)[1], "Condition")), ("held", GE, 5))
        self.assertEqual([self.in_zones(x) for x in prop(prop(subs(subs(flipped)[0])[0], "Condition"),
                                                         "SousConditions")], [("blue", GE, 1), ("red", LE, 0)])

    def test_zone_handover(self):
        """Sequential[SetCommandZoneOwnerAndForceConvergence(side, the tags), Simultaneous[the hint]]; an action
        instead of a token goes in as given; None leaves the hint out; only command zones."""
        c = ctx()
        node = zone_handover(c, "E", ["T_CZ_A", "T_CZ_B"], "t_hint")
        owner, hint = subs(node)
        self.assertEqual((owner.cls, kv(owner)), ("TGDDescriptorSetCommandZoneOwnerAndForceConvergence",
                                                  [("Camp", "red"), ("Positions", ["T_CZ_A", "T_CZ_B"])]))
        (ld,) = subs(hint)
        self.assertEqual((hint.cls, token(prop(ld, "Info")), prop(ld, "Time").v),
                         ("TGDDescriptorSimultaneous", "t_hint", HINT_S))
        action = g_seq([g_hint("t_other", HINT_S, "shint")])
        self.assertIs(subs(zone_handover(c, "P", ["T_CZ_A"], action))[1], action)
        self.assertEqual(kv(subs(zone_handover(c, "P", ["T_CZ_A"], None))[0])[0], ("Camp", "blue"))
        self.assertEqual(len(subs(zone_handover(c, "P", ["T_CZ_A"], None))), 1)
        with self.assertRaisesRegex(CheckError, "T_DZ is not a command zone"):
            zone_handover(c, "P", ["T_DZ"], "t_hint")
        with self.assertRaisesRegex(CheckError, "0 items are named T_None"):
            zone_handover(c, "P", ["T_None"], "t_hint")

    def test_ring_round(self):
        """ClearUnitGroup, one AddDetectedUnitsToUnitGroup per circle with a fresh constraint, then the count."""
        c = ctx()
        made: list[Node] = []

        def team() -> Node:
            made.append(Node("TGDContrainteOnUnitTeam", [("Camp", c.camp("E"))]))
            return made[-1]

        clear, *collects, count = ring_round(c, c.group("g"), ["T_RingA", "T_RingB"], team, c.int_var("n"))
        self.assertEqual(kv(clear), [("Group", "g")])
        self.assertEqual([(n.cls, last(prop(prop(n, "Detector"), "Detecteur"))) for n in collects],
                         [("TGDDescriptorAddDetectedUnitsToUnitGroup", "T_RingA"),
                          ("TGDDescriptorAddDetectedUnitsToUnitGroup", "T_RingB")])
        self.assertEqual([prop(prop(n, "Detector"), "Contrainte") for n in collects], made)
        self.assertIsNone(prop(prop(collects[0], "Detector"), "ComparaisonNbUnits"))
        self.assertEqual(kv(count), [("Group", "g"), ("Variable", "n")])
        self.assertEqual(len(ring_round(c, c.group("g"), ["T_RingA"], team)), 2)


class Endings(unittest.TestCase):
    ENDINGS = {1: ("t_win", TOTAL_VICTORY, False), 2: ("t_major", MAJOR_VICTORY, False),
               3: ("t_lost", TOTAL_VICTORY, True)}

    def test_end_funnel(self):
        """Wait for end >= 1, then IfThenElse(end == v) per row in order, the last row the last else; each branch the
        dialog, then its TriggerEndGame (a loss names alliance 1); exported where the caller says."""
        c = ctx()
        end = c.int_var("end")
        funnel = end_funnel(end, self.ENDINGS, "$/GDScript/T/EndFunnel")
        wait, pick = subs(funnel)
        self.assertEqual((funnel.export, cmp_of(prop(wait, "Condition"))), ("$/GDScript/T/EndFunnel", ("end", GE, 1)))
        rows = []
        while pick.cls == "TGDDescriptorIfThenElse":
            rows.append((cmp_of(prop(pick, "Condition")), prop(pick, "EffetIfTrue")))
            pick = prop(pick, "EffetIfFalse")
        rows.append((None, pick))
        self.assertEqual([cond for cond, _ in rows], [("end", 0, 1), ("end", 0, 2), None])
        for (_, branch), (dialog_token, kind, loses) in zip(rows, self.ENDINGS.values()):
            dialog, trigger = subs(branch)
            (text,) = [n for n in walk([dialog]) if n.cls == "TGDDescriptorCutsceneTextComponent"]
            self.assertEqual(token(prop(text, "LocalizedText")), dialog_token)
            self.assertEqual(end_game(trigger), (6, kind, 1 if loses else None))
        with self.assertRaisesRegex(CheckError, "must be 1 or more"):
            end_funnel(end, {0: ("t_win", TOTAL_VICTORY, False)}, "$/GDScript/T/EndFunnel")


class Difficulty(unittest.TestCase):
    KNOBS = {"k_a": (1, 2, 3), "k_b": (40, 50, 60)}

    def test_after_launch(self):
        phase, wait, hint = subs(after_launch("t_h", 12.0))
        self.assertEqual(kv(prop(phase, "Condition")), [("Phase", BATTLE_PHASE)])
        self.assertEqual(prop(wait, "Duree").v, 12.0)
        self.assertEqual(token(prop(subs(hint)[0], "Info")), "t_h")

    def test_difficulty(self):
        """diff = DIFF_NONE, the knobs at Medium, three branches (Easy and Hard overwrite the knobs), then the
        fallback to Medium; each case's hint is the prefix and its number, hint_t after the launch."""
        c = ctx()
        diff = c.int_var("diff")
        node = difficulty(c, diff, self.KNOBS, "t_dif", 7.0)
        none, knob_a, knob_b, branches, fallback = subs(node)
        self.assertEqual([kv(n) for n in (none, knob_a, knob_b)],
                         [[("Variable1", "diff"), ("Value", DIFF_NONE)], [("Variable1", "k_a"), ("Value", 2)],
                          [("Variable1", "k_b"), ("Value", 50)]])
        self.assertEqual(list(c.variables), ["diff", "k_a", "k_b"])
        for level, branch in zip((EASY, MEDIUM, HARD), subs(branches)):
            with self.subTest(level=level):
                cond, body = prop(branch, "Condition"), prop(branch, "EffetIfTrue")
                self.assertEqual(kv(cond), [("Difficulty", level)] if level else [])
                *sets, launch = subs(body)
                self.assertEqual(set_values(sets, diff), [level])
                knobs = {last(prop(s, "Variable1")): prop(s, "Value").v for s in sets[1:]}
                self.assertEqual(knobs, {} if level == MEDIUM else {k: v[level] for k, v in self.KNOBS.items()})
                _, wait, hint = subs(launch)
                self.assertEqual((prop(wait, "Duree").v, token(prop(subs(hint)[0], "Info"))), (7.0, f"t_dif{level}"))
        self.assertEqual(cmp_of(prop(fallback, "Condition")), ("diff", 0, DIFF_NONE))
        to_medium, launch = subs(prop(fallback, "EffetIfTrue"))
        self.assertEqual(kv(to_medium), [("Variable1", "diff"), ("Value", MEDIUM)])
        self.assertEqual(token(prop(subs(subs(launch)[2])[0], "Info")), f"t_dif{DIFF_NONE}")


class Frame(unittest.TestCase):
    def frame(self, beats: list[Beat], flags=()):
        c = ctx()
        tpl = template()
        deploy = deploy_phase(tpl, TEMPLATES, c.camp("P"), c.group("Groupe_Joueur"), [c.tag("T_CZ_A")], points=900,
                              income=10, hint="t_dep", refresh_export="$/GDScript/T/Refresh", refresh_s=2.0)
        return c, deploy, script_frame(tpl, TEMPLATES, c, deploy, beats, camp_rows=CAMPS, folder="$/GDScript/T",
                                       start_delay_s=1.5, prod_menu_switch=BRICK_FORCE_HIDE, flags=flags)

    def test_script_frame(self):
        """The root, Main (SetDecks, HUD hide, deployment setup, LoadingDone, HUD restore, then the load beats beside
        the refresh loop and Sequential[launched, Simultaneous[Sequential[wait t, beat]]]), the exports in order with
        an unlisted exported node after the refresh loop, and the flags declared after the beats."""
        funnel = Node("TGDDescriptorWaitDuration", export="$/GDScript/T/Funnel")
        beats = [Beat(None, "load", lambda c: g_seq([funnel, c.int_var("seen")])),
                 Beat(30.0, "timed", lambda c: g_hint("t_hint", HINT_S, "shint"))]
        c, deploy, (roots, exports) = self.frame(beats, flags=("flag",))
        voices, root = roots
        self.assertEqual((root.export, voices.cls), ("$/GDScript/RootDescriptor", "TCutsceneDescriptorDatabase"))
        delay, main = subs(prop(root, "EffetMap"))
        self.assertEqual((prop(delay, "Duree").v, main.export, prop(root, "GameRules")),
                         (1.5, "$/GDScript/T/Main", deploy.game_rules))
        kids = subs(main)
        self.assertEqual([k.cls for k in kids[:2]], ["TGDDescriptorSetDeck"] * 2)
        self.assertEqual(kids[2].cls, "TGDDescriptorForceDisplayUIElement")
        self.assertEqual(kids[3:3 + len(deploy.setup)], list(deploy.setup))
        self.assertEqual([k.cls for k in kids[3 + len(deploy.setup):-1]],
                         ["TGDDescriptorLoadingDone", "TGDDescriptorForceDisplayUIElement"])
        load, refresh, battle = subs(kids[-1])
        self.assertEqual((subs(load)[0], refresh), (funnel, deploy.refresh))
        launched, timed = subs(battle)
        self.assertIs(launched, deploy.launched)
        (one,) = subs(timed)
        self.assertEqual(prop(subs(one)[0], "Duree").v, 30.0)
        self.assertEqual(exports, [root, *c.camps.values(), *c.tags.values(), main, deploy.refresh, funnel,
                                   *c.variables.values()])
        self.assertEqual(list(c.variables), ["Groupe_Joueur", "seen", "flag"])

    def test_without_timed_beats_launched_stands_alone(self):
        c, deploy, (roots, _) = self.frame([Beat(None, "load", lambda c: g_hint("t_hint", HINT_S, "shint"))])
        main = subs(prop(roots[1], "EffetMap"))[1]
        self.assertEqual(subs(subs(main)[-1])[1:], [deploy.refresh, deploy.launched])


if __name__ == "__main__":
    unittest.main()
