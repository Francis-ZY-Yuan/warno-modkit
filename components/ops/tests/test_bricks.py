"""Tests for modkit.ops.bricks: each brick's class, property order and value tags."""
import unittest

from modkit.core import ndfbin
from modkit.ops import bricks
from modkit.ops.bricks import (
    c_all, c_any, c_none, c_team, c_type, g_and, g_attack, g_cmp, g_collect, g_compete, g_count, g_create, g_detect,
    g_dialog, g_end_sequence, g_fx, g_grant, g_hint, g_hold, g_idle_roe, g_if, g_ignored, g_income, g_int_compare,
    g_modify, g_or, g_planes_spent, g_roe, g_seize, g_seq, g_set, g_simul, g_smart_hold, g_until, g_vanish, g_wait,
    g_zone_owner, unit_path,
)
from modkit.ops.graph import TRUE, Imp, Node, Str, build_graph, decode, encode, f32, i32, loc, u32


def shape(nd: Node) -> tuple[str, list[str]]:
    return nd.cls, [name for name, _ in nd.props]


class FlowTest(unittest.TestCase):
    def test_containers(self):
        a, b = g_wait(1), g_wait(2)
        self.assertEqual(g_seq([a, b]).props, [("SubActions", [a, b]), ("NbExecutions", u32(1))])
        self.assertEqual(g_seq([a], runs=3, export="$/GDScript/X").export, "$/GDScript/X")
        self.assertEqual(shape(g_simul([a])), ("TGDDescriptorSimultaneous", ["SubActions", "NbExecutions"]))
        self.assertEqual(shape(g_compete([a])), ("TGDDescriptorCompetition", ["SubActions", "NbExecutions"]))
        self.assertEqual(g_wait(2).props, [("Duree", f32(2.0))])

    def test_if(self):
        c, t, e = g_and(), g_wait(1), g_wait(2)
        self.assertEqual(shape(g_if(c, t)), ("TGDDescriptorIfThenElse", ["Condition", "EffetIfTrue"]))
        self.assertEqual(shape(g_if(c, t, e)), ("TGDDescriptorIfThenElse", ["Condition", "EffetIfTrue", "EffetIfFalse"]))

    def test_hold(self):
        flag = Node("TGDVariableInteger")
        hold = g_hold(lambda: g_and(), lambda: g_or(), 10.0, flag, export="$/GDScript/Hold")
        self.assertEqual(shape(hold), ("TGDDescriptorCompetition", ["SubActions", "NbExecutions"]))
        loop, done = hold.props[0][1]
        self.assertEqual(loop.props[1], ("NbExecutions", u32(0xFFFFFFFF)))  # repeats until the flag ends it
        self.assertEqual(done.cls, "TGDDescriptorWaitCondition")
        self.assertIs(done.props[0][1].props[1][1], flag)
        self.assertEqual(hold.export, "$/GDScript/Hold")


class ConditionTest(unittest.TestCase):
    def test_int_compare_omits_zero_and_equal(self):
        self.assertEqual(g_int_compare().props, [])
        self.assertEqual(g_int_compare(0, 0).props, [])
        self.assertEqual(g_int_compare(1, 2).props, [("Value", i32(1)), ("OperatorType", i32(2))])
        var = Node("TGDVariableInteger")
        self.assertEqual(g_int_compare(other=var).props, [("Variable", var)])

    def test_cmp(self):
        var = Node("TGDVariableUnitGroup")
        cond = g_cmp(var, 1, 2)
        self.assertEqual(shape(cond), ("TGDConditionVariable", ["Operator", "Variable"]))
        self.assertIs(cond.props[1][1], var)

    def test_detect(self):
        zone, team = Node("TGDTagDetecteur"), c_team(Node("TGDVariableCamp"))
        self.assertEqual(shape(g_detect(zone, team, 1, 2)),
                         ("TGDConditionDetectUnitDansDetecteur", ["ComparaisonNbUnits", "Detecteur", "Contrainte"]))
        self.assertEqual(shape(g_detect(zone, team, compare=False)),
                         ("TGDConditionDetectUnitDansDetecteur", ["Detecteur", "Contrainte"]))

    def test_and_or(self):
        a, b = g_until(g_and()), g_until(g_or())
        self.assertEqual(g_and(a, b).props, [("SousConditions", [a, b])])
        self.assertEqual(g_or(a).cls, "TGDConditionOr")

    def test_constraints(self):
        self.assertEqual(unit_path("A_B"), "$/GFX/Unit/Descriptor_Unit_A_B")
        self.assertEqual(c_type("A_B").props, [("TypeUnit", Imp("$/GFX/Unit/Descriptor_Unit_A_B"))])
        x = c_type("A")
        self.assertEqual(c_all(x).cls, "TGDContrainteOnUnitAllContrainte")
        self.assertEqual(c_none(x).cls, "TGDContrainteOnUnitNoContrainte")
        self.assertEqual(c_any(x).props, [("ContrainteList", [x])])


class ActionTest(unittest.TestCase):
    def setUp(self):
        self.var, self.other, self.group = Node("TGDVariableInteger"), Node("TGDVariableInteger"), Node("TGDVariableUnitGroup")

    def test_set_and_modify(self):
        self.assertEqual(g_set(self.var).props, [("Variable1", self.var)])
        self.assertEqual(g_set(self.var, 3).props, [("Variable1", self.var), ("Value", i32(3))])
        self.assertEqual(g_set(self.var, other=self.other).props, [("Variable1", self.var), ("Variable2", self.other)])
        self.assertEqual(g_modify(self.var, 1).props, [("Variable1", self.var), ("Value", i32(0)),
                                                       ("ModificationType", i32(1))])

    def test_groups(self):
        zone = Node("TGDTagDetecteur")
        self.assertEqual(g_count(self.var, self.group).props, [("Group", self.group), ("Variable", self.var)])
        self.assertEqual(g_collect(self.group, zone).props, [("Detector", zone), ("Group", self.group)])
        self.assertEqual(g_vanish(self.group).props, [("GroupList", [self.group])])

    def test_create_and_roe(self):
        camp, pos = Node("TGDVariableCamp"), Node("TGDTagPosition")
        self.assertEqual(shape(g_create(camp, self.group, 2, pos, unit_path("A"))),
                         ("TGDDescriptorCreateUnitOnPosition", ["Camp", "Group", "NbUnit", "Position", "TypeUnit"]))
        self.assertEqual(g_roe(self.group, 2).props, [("Group", self.group), ("ShotReactionBehavior", i32(2))])
        self.assertEqual(g_roe(self.group, 1).props[1], ("ShotReactionBehavior", i32(1)))

    def test_zone_owner(self):
        camp, a, b = Node("TGDVariableCamp"), Node("TGDTagPosition"), Node("TGDTagPosition")
        nd = g_zone_owner(camp, (a, b))
        self.assertEqual(shape(nd), ("TGDDescriptorSetCommandZoneOwnerAndForceConvergence", ["Camp", "Positions"]))
        self.assertEqual(dict(nd.props)["Positions"], [a, b])

    def test_fx(self):
        pos = Node("TGDTagPosition")
        self.assertEqual(g_fx("$/GFX/GameFx/fx_A", pos).props, [("DatabaseName", Str("$/GFX/GameFx/fx_A")),
                                                                ("Position", pos)])


class DialogTest(unittest.TestCase):
    def test_dialog(self):
        d = g_dialog("op_hi")
        self.assertEqual(d.cls, "TGDDescriptorEncapsuleCutscene")
        play = d.props[0][1][0]
        dialog = play.props[0][1][0]
        self.assertEqual([n for n, _ in dialog.props], [
            "CanBeSkippedWithEscape", "ComponentName", "DureePause", "TextComponentsToFill", "TokenBoutonChoix0",
            "VisibleByAlliedOfSpecifiedCamp"])
        text = dialog.props[3][1][0]
        self.assertEqual(text.props[1], ("LocalizedText", loc("op_hi")))
        self.assertEqual(dialog.props[4], ("TokenBoutonChoix0", loc("SI_NEXT")))

    def test_camera(self):
        """EncapsuleCutscene[CutsceneStartCameraPath] in DelayedRetribution #65/#79's order, player actions blocked."""
        cam = bricks.g_camera("TS_Start")
        self.assertEqual(shape(cam), ("TGDDescriptorEncapsuleCutscene", ["SubActions", "BlockPlayerActions"]))
        self.assertEqual(cam.props[1], ("BlockPlayerActions", TRUE))
        (start,) = cam.props[0][1]
        self.assertEqual(start.props, [("CameraPathName", Str("TS_Start")), ("AccelerationActivated", TRUE),
                                       ("DecelerationActivated", TRUE), ("CanBeSkippedWithEscape", TRUE),
                                       ("VisibleByAlliedOfSpecifiedCamp", TRUE)])
        self.assertEqual(start.cls, "TGDDescriptorCutsceneStartCameraPath")

    def test_ammo(self):
        """SetAmmo in stock's two forms: refilled, MaxAmmoRatio 100 then Units (HoldUntilRelieved #281); emptied, Units
        only (Survivors #1332)."""
        group = Node("TGDVariableUnitGroup", export="$/GDScript/X/Variables/g")
        self.assertEqual(bricks.g_ammo([group], refill=True).props, [("MaxAmmoRatio", i32(100)), ("Units", [group])])
        empty = bricks.g_ammo([group])
        self.assertEqual((empty.cls, empty.props), ("TGDDescriptorSetAmmo", [("Units", [group])]))

    def test_hint(self):
        self.assertEqual(g_hint("op_h", 15.0, "shint").props, [
            ("Info", loc("op_h")), ("Time", f32(15.0)), ("ComponentName", Str("shint")),
            ("VisibleByAlliedOfSpecifiedCamp", TRUE)])

    def test_end_sequence(self):
        end = g_end_sequence("op_win", 5, None, "$/GDScript/Win")
        hide, dialog, trigger = end.props[0][1]
        self.assertEqual(hide.props, [("ForceHideAll", TRUE)])
        self.assertEqual(dialog.cls, "TGDDescriptorEncapsuleCutscene")
        self.assertEqual(trigger.props, [("VictoryReason", i32(6)), ("VictoryType", i32(5))])
        lose = g_end_sequence("op_lose", 1, 1, "$/GDScript/Lose").props[0][1][2]
        self.assertEqual(lose.props[-1], ("WinningAlliance", i32(1)))


class OrdersAndEconomyTest(unittest.TestCase):
    """The bricks the first play of Twin Strike asked for, each in its stock object's order and value forms."""

    camp, group, other = Node("TGDVariableCamp"), Node("TGDVariableUnitGroup"), Node("TGDVariableUnitGroup")
    pos = Node("TGDTagPosition")

    def test_idle_roe_and_ignored(self):
        """SetIdleROEBehavior (Survivors #188: Group, IdleBehavior int32) and AddIgnoredUnitByScript (TheDieburgSalient
        #143: UnitGroup only)."""
        self.assertEqual(g_idle_roe(self.group, 2).props, [("Group", self.group), ("IdleBehavior", i32(2))])
        self.assertEqual(g_idle_roe(self.group, 2).cls, "TGDDescriptorSetIdleROEBehavior")
        self.assertEqual(g_ignored(self.group).props, [("UnitGroup", self.group)])
        self.assertEqual(g_ignored(self.group).cls, "TGDDescriptorAddIgnoredUnitByScript")

    def test_smart_hold(self):
        """LaunchSmartOrder Hold (RedJuggernaut #249: Position, SmartOrderType 2, UnitGroup), beside Seize's 1."""
        self.assertEqual(g_smart_hold(self.group, self.pos).props,
                         [("Position", self.pos), ("SmartOrderType", i32(2)), ("UnitGroup", self.group)])
        self.assertEqual(g_seize(self.group, self.pos).props[1], ("SmartOrderType", i32(1)))

    def test_attack(self):
        """Attack (Survivors #1099): Blocking, Group, AttackEnPrioriteUniteNotUbserstress, Targets."""
        self.assertEqual(g_attack(self.group, self.other).props,
                         [("Blocking", TRUE), ("Group", self.group), ("AttackEnPrioriteUniteNotUbserstress", TRUE),
                          ("Targets", self.other)])
        self.assertEqual(g_attack(self.group, self.other).cls, "TGDDescriptorAttack")

    def test_income_leaves_a_zero_out(self):
        """SetIncomeToTeam: an amount as DelayedRetribution #109 writes it; a zero with no Quantite at all, as
        RunningTheGauntlet #275 writes it."""
        self.assertEqual(g_income(self.camp, 250).props, [("Camp", self.camp), ("Quantite", i32(250))])
        self.assertEqual(g_income(self.camp, 0).props, [("Camp", self.camp)])

    def test_grant(self):
        """GiveRessourceToTeam (BlackHorsesLastStand #312: Camp, Quantite, ResourceType 1)."""
        self.assertEqual(g_grant(self.camp, 4000).props,
                         [("Camp", self.camp), ("Quantite", i32(4000)), ("ResourceType", i32(1))])

    def test_planes_spent(self):
        """Survivors #1682: at least `count` of the group out of fuel or ammunition (MoreOrEqual), over its three
        logistic constraints: two OperatorType 2 at or below 0, one (OperatorType 0, left out) at or below 50."""
        cond = g_planes_spent(self.group, 2)
        self.assertEqual(shape(cond), ("TGDConditionUnitGroupWithFilter", ["Operator", "Variable", "Contrainte"]))
        self.assertEqual(dict(cond.props)["Operator"].props, [("Value", i32(2)), ("OperatorType", i32(2))])
        any_ = dict(cond.props)["Contrainte"]
        self.assertEqual(any_.cls, "TGDContrainteOnUnitAnyContrainte")
        got = [([(k, v.v) for k, v in c.props if k == "OperatorType"],
                dict(c.props)["CompareInteger"].props) for c in dict(any_.props)["ContrainteList"]]
        self.assertEqual(got, [([("OperatorType", 2)], [("OperatorType", i32(3))]),
                               ([("OperatorType", 2)], [("OperatorType", i32(3))]),
                               ([], [("Value", i32(50)), ("OperatorType", i32(3))])])


class EncodeTest(unittest.TestCase):
    def test_every_brick_encodes(self):
        """A script using every brick builds, encodes and decodes back to the same image."""
        camp, group, var = Node("TGDVariableCamp"), Node("TGDVariableUnitGroup"), Node("TGDVariableInteger")
        zone, pos = Node("TGDTagDetecteur"), Node("TGDTagPosition")
        flag = Node("TGDVariableInteger", export="$/GDScript/Vars/Flag")
        body = g_seq([
            g_create(camp, group, 1, pos, unit_path("A")), g_roe(group, 2), g_fx("$/GFX/GameFx/fx_A", pos),
            g_zone_owner(camp, [pos]), g_idle_roe(group, 2), g_ignored(group), g_smart_hold(group, pos),
            g_attack(group, group), g_income(camp, 0), g_income(camp, 250), g_grant(camp, 4000),
            g_until(g_planes_spent(group, 2)),
            g_count(var, group), g_collect(group, zone), g_set(var, 1), g_modify(var, 2, 1), g_vanish(group),
            g_until(g_and(g_cmp(var, 1, 2), g_or(g_detect(zone, c_all(c_team(camp), c_any(c_type("A"))), 1, 2),
                                                 g_detect(zone, c_none(c_type("B")), compare=False)))),
            g_simul([g_hint("op_h", 15.0, "shint"), g_dialog("op_d")]),
            g_hold(lambda: g_cmp(var, 1), lambda: g_cmp(var, 0), 5.0, flag),
            g_if(g_cmp(var, 1), g_wait(1), g_wait(2)),
            g_end_sequence("op_end", 5, None, "$/GDScript/End"),
        ], export="$/GDScript/Main")
        raw = encode(build_graph([body], [body, flag]), "bricks")
        nb, _, image = decode(raw)
        self.assertEqual(ndfbin.encode_image(nb), image)
        self.assertIn(b"TGDDescriptorSetShotReactionROEBehavior", nb.classes)

    def test_no_brick_reads_a_module_setting(self):
        """Bricks take every mod-specific value as an argument: the module holds functions only."""
        settings = [k for k, v in vars(bricks).items() if k.isupper() and not k.startswith("_")]
        self.assertEqual(settings, ["TRUE"])  # the imported bool constant, not a setting


if __name__ == "__main__":
    unittest.main()
