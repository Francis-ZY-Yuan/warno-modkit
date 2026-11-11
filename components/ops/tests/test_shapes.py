"""Tests for modkit.ops.shapes, the mission building blocks (synthetic: no stock data needed)."""
from __future__ import annotations

import unittest

from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.bricks import g_choice, g_cmp, g_hint, g_seq
from modkit.ops.graph import Node, walk
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA
from modkit.ops.script import FOREVER
from modkit.ops.shapes import (
    GRU_WORLD, POLL_S, REVEAL_EFFECT, TRANSPORTER_SHAPE, Ctx, Minimap, add_card, beat_hint, camp_nodes, count_ladder,
    dialog_tokens, lock_card, objective, reveal, seconds_while, set_end, setdeck_block,
)
from modkit.ops.testing import last, of, prop, subs, token

CAMPS = (("blue", (("AllianceStyle", 0x02, 3),), "DECK_BLUE"), ("red", (("Alliance", 0x03, 1),), "DECK_RED"))
TOKENS = {"blue": "t_blue", "red": "t_red"}
MAP = Minimap(GEISA, {"HILL": (100.0, 200.0)})


def ctx(items=()) -> Ctx:
    return Ctx(camp_nodes(CAMPS, TOKENS), {"P": "blue", "E": "red"}, "P", items, "challenge_T", "ns", "$/GDScript/T")


class Camps(unittest.TestCase):
    def test_camp_nodes_and_setdeck(self):
        camps = camp_nodes(CAMPS, TOKENS)
        self.assertEqual(list(camps), ["blue", "red"])
        self.assertEqual(camps["red"].export, "$/GDScript/RootDescriptor/red")
        self.assertEqual([p for p, _ in camps["blue"].props], ["AllianceStyle", "PlayerName"])
        self.assertEqual(prop(camps["red"], "Alliance"), Value(0x03, 1))
        decks = setdeck_block(camps, CAMPS)
        self.assertEqual([(prop(n, "Camp"), prop(n, "DeckIdentifier").text) for n in decks],
                         [(camps["blue"], "DECK_BLUE"), (camps["red"], "DECK_RED")])


class Context(unittest.TestCase):
    def test_variables_once_per_name(self):
        c = ctx()
        self.assertIs(c.int_var("x"), c.int_var("x"))
        self.assertEqual(c.group("g").export, "$/GDScript/T/Variables/g")
        with self.assertRaisesRegex(CheckError, "variable x is a TGDVariableInteger, not a TGDVariableUnitGroup"):
            c.group("x")
        self.assertEqual(list(c.variables), ["x", "g"])

    def test_sides_and_tags(self):
        c = ctx([MAP.item("Tags", "T_Hill", "HILL", "Name")])
        self.assertIs(c.camp("E"), c.camps["red"])
        self.assertEqual(last(c.tag("T_Hill")), "T_Hill")
        with self.assertRaisesRegex(CheckError, "T_None is not an ITEMS entry"):
            c.tag("T_None")
        with self.assertRaisesRegex(CheckError, "two ITEMS entries are named T_Hill"):
            ctx([MAP.item("Tags", "T_Hill", "HILL", "Name"), MAP.item("CommandPoints", "T_Hill", "HILL", "Name")])


class Places(unittest.TestCase):
    def test_item_by_point_or_px(self):
        it = MAP.item("Tags", "A", "HILL", "Name")
        self.assertEqual((it.x, it.y), (100.0 * GEISA.world_per_px, 200.0 * GEISA.world_per_px))
        self.assertEqual(MAP.px_of(MAP.item("Tags", "B", (3, 4), "Name")), (3.0, 4.0))
        with self.assertRaisesRegex(CheckError, "Tags/C: NOWHERE is not a named point"):
            MAP.item("Tags", "C", "NOWHERE", "Name")

    def test_zone_and_ring(self):
        zone = MAP.zone_item("CommandPoints", "Z", (10, 20, 30, 60), "CommandPoints", points=2)
        self.assertEqual(MAP.px_of(zone), (20.0, 40.0))
        self.assertEqual(MAP.box_px(zone), (10.0, 20.0, 30.0, 60.0))
        self.assertEqual(zone.polygon[0], zone.polygon[-1])
        self.assertEqual(zone.points, 2)
        ring = MAP.ring_item("R", "HILL", 25.0)
        self.assertEqual((ring.ranking, ring.addon), ("CircularZones", "CircularZone"))
        self.assertAlmostEqual(ring.radius_gru, 25.0 * GEISA.world_per_px / GRU_WORLD)
        self.assertAlmostEqual(MAP.radius_px(ring), 25.0)


class Blocks(unittest.TestCase):
    def test_add_card_order(self):
        c = ctx()
        plain = add_card(c, "Tank_A", 2)
        self.assertEqual([p for p, _ in plain.props], ["Camp", "NbUnitsToAdd", "TypeUnit"])
        self.assertIs(prop(plain, "Camp"), c.camp("P"))
        full = add_card(c, "Rifles_A", 1, transport="Truck_A", experience=0)
        self.assertEqual([p for p, _ in full.props], ["Camp", "Experience", "NbUnitsToAdd", "Transporter", "TypeUnit"])
        self.assertEqual(prop(full, "Transporter").path, "$/GFX/Unit/Descriptor_Unit_Truck_A")
        self.assertEqual(TRANSPORTER_SHAPE[:2], ("TGDDescriptorAddUnitToDeck", "Transporter"))

    def test_lock_card_races_its_condition(self):
        c = ctx()
        node = lock_card(c, "Plane_A", g_cmp(c.int_var("open"), 1))
        self.assertEqual(node.cls, "TGDDescriptorCompetition")
        until, lock = subs(node)
        self.assertEqual((until.cls, lock.cls), ("TGDDescriptorWaitCondition", "TGDDescriptorLockDeckUnit"))
        self.assertIs(prop(lock, "Camp"), c.camp("P"))

    def test_set_end_writes_only_while_zero(self):
        end = ctx().int_var("end")
        node = set_end(end, 2)
        self.assertEqual(node.cls, "TGDDescriptorIfThenElse")
        self.assertIs(prop(prop(node, "Condition"), "Variable"), end)
        (write,) = subs(prop(node, "EffetIfTrue"))
        self.assertEqual((prop(write, "Variable1"), prop(write, "Value").v), (end, 2))
        self.assertIsNone(prop(node, "EffetIfFalse"))

    def test_seconds_while_and_count_ladder(self):
        c = ctx()
        var = c.int_var("held")
        streak = seconds_while(lambda: g_cmp(var, 1), lambda: g_cmp(var), var, reset=True)
        self.assertEqual(prop(streak, "NbExecutions").v, FOREVER)
        self.assertEqual([k.cls for k in subs(streak)], ["TGDDescriptorWaitCondition", "TGDDescriptorCompetition",
                                                         "TGDDescriptorModifieVariableInteger"])
        tick = subs(subs(streak)[1])[0]
        self.assertEqual(prop(subs(tick)[0], "Duree").v, POLL_S)
        summed = seconds_while(lambda: g_cmp(var, 1), lambda: g_cmp(var), var, reset=False)
        self.assertEqual(len(subs(summed)), 2)
        loops = count_ladder(lambda v, op: g_cmp(var, v, op), c.int_var("n"), 3)
        self.assertEqual(len(loops), 3)
        ups = [prop(prop(prop(subs(loop)[0], "Condition"), "Operator"), "Value") for loop in loops]
        self.assertEqual([u.v for u in ups], [1, 2, 3])

    def test_reveal_runs_beside_the_rest(self):
        g = ctx().group("enemy")
        node = reveal([g], [g_seq([])])
        effect, rest = subs(node)
        self.assertEqual(prop(effect, "Effet").path, f"$/GFX/EffectCapacity/{REVEAL_EFFECT}")
        self.assertEqual(rest.cls, "TGDDescriptorSequential")
        self.assertEqual(len(subs(reveal([g], []))), 1)

    def test_objective_label_needs_a_position(self):
        c = ctx([MAP.item("Tags", "T_Hill", "HILL", "Name")])
        placed = objective("o", "l", g_cmp(c.int_var("x"), 1), c.tag("T_Hill"))
        loose = objective("o", "l", None, fail=g_cmp(c.int_var("x"), 1), kind="Bonus")
        self.assertEqual([p for p, _ in placed.props][-1], "ShowEtiquette")
        self.assertNotIn("ShowEtiquette", [p for p, _ in loose.props])
        self.assertNotIn("Condition", [p for p, _ in loose.props])
        self.assertEqual(prop(loose, "LabelComponent").text, "Bonus")

    def test_objective_counters(self):
        """`counters` fill both texts' lists (the default form, unchanged); `label_counters` fill the label's only;
        both at once is refused."""
        c = ctx([MAP.item("Tags", "T_Hill", "HILL", "Name")])
        n, cond, at = c.int_var("n"), g_cmp(c.int_var("x"), 1), c.tag("T_Hill")
        tail = ["ObjectiveEtiquetteText", "ObjectiveText", "Position", "ShowAddAnimation", "ShowBaseAnimation",
                "ShowEtiquette"]
        head = ["BonusScoreMission", "Condition", "LabelComponent"]
        both = objective("o", "l", cond, at, [n])
        self.assertEqual([p for p, _ in both.props], [*head, "ListVariables", "ListVariablesForEtiquetteText", *tail])
        self.assertEqual((prop(both, "ListVariables"), prop(both, "ListVariablesForEtiquetteText")), ([n], [n]))
        label = objective("o", "l", cond, at, label_counters=[n])
        self.assertEqual([p for p, _ in label.props], [*head, "ListVariablesForEtiquetteText", *tail])
        self.assertEqual(prop(label, "ListVariablesForEtiquetteText"), [n])
        self.assertEqual([p for p, _ in objective("o", "l", cond, at).props], [*head, *tail])
        with self.assertRaisesRegex(CheckError, "not both"):
            objective("o", "l", cond, at, [n], label_counters=[n])

    def test_beat_hint_and_dialog_tokens(self):
        c = ctx()
        beat = beat_hint("h1", g_choice("ask", "B0", "B1", c.camp("P"), c.int_var("pick")),
                         g_choice("ask", "B0", "B1", c.camp("P"), c.int_var("pick")), g_hint("h2", 15.0, "shint"))
        self.assertEqual([token(prop(n, "Info")) for n in of(list(walk([beat])), "LDHint")], ["h1", "h2"])
        self.assertEqual(dialog_tokens([beat]), ["ask"])


if __name__ == "__main__":
    unittest.main()
