"""Tests for the script and package gates in modkit.ops.gates, on tiny synthetic scripts: the parameters a profile
sets (the end funnel's exports, the tier camps), the never-finishing rule, the strings and scenario-only gates."""
import unittest

from modkit.core.gates import CheckError
from modkit.core.packaging import GAMEPLAY_FILES
from modkit.ops.bricks import g_seq, g_simul, g_wait
from modkit.ops.gates import (
    check_end_funnel, check_never_finishing, check_package, check_prod_menu_switch, check_rules, check_strings,
    zone_owner_actions,
)
from modkit.ops.profile import Content
from modkit.ops.script import BRICK_DEFAULT, BRICK_FORCE_HIDE, PROD_MENU_SWITCH
from modkit.ops.graph import TRUE, Node, i32
from modkit.ops.items import mem_item
from modkit.ops.strings import StringError

ZONE_OWNER = "TGDDescriptorSetCommandZoneOwnerAndForceConvergence"


def end_game() -> Node:
    return Node("TGDDescriptorTriggerEndGame", [("VictoryReason", i32(6)), ("VictoryType", i32(5))])


def camp(name: str) -> Node:
    return Node("TGDVariableCamp", export=f"$/GDScript/RootDescriptor/{name}")


def owner(side: Node) -> Node:
    return Node(ZONE_OWNER, [("Camp", side), ("Positions", [])])


class EndFunnelTest(unittest.TestCase):
    def test_no_funnel_exports_is_not_checked(self):
        self.assertEqual(check_end_funnel([g_simul([end_game(), end_game()])], ()), (2, False))

    def test_every_ending_goes_through_the_profiles_funnel(self):
        funnel = g_seq([g_wait(1.0), end_game()], export="$/GDScript/M/Funnel")
        self.assertEqual(check_end_funnel([g_simul([funnel])], ("$/GDScript/M/Funnel",)), (1, True))
        with self.assertRaisesRegex(CheckError, r"\) is under neither \$/GDScript/M/Funnel\n"):
            check_end_funnel([g_simul([funnel, end_game()])], ("$/GDScript/M/Funnel",))


class ZoneOwnerTest(unittest.TestCase):
    def test_the_profiles_camps_open_and_close(self):
        """The player's forcing before LoadingDone opens a tier; the enemy's after it closes one."""
        player, enemy = camp("p"), camp("e")
        roots = [g_seq([owner(player), Node("TGDDescriptorLoadingDone"), owner(enemy)])]
        load, later = zone_owner_actions(roots, "p", "e")
        self.assertEqual(([dict(n.props)["Camp"] for n in load], [dict(n.props)["Camp"] for n in later]),
                         ([player], [enemy]))
        self.assertEqual(zone_owner_actions(roots, "e", "p"), ([], []))


class NeverFinishingTest(unittest.TestCase):
    def test_a_node_after_a_set_effect_never_runs(self):
        effect = Node("TGDDescriptorSetEffect")
        self.assertEqual(check_never_finishing([g_simul([effect, g_wait(1.0)])]), 1)
        with self.assertRaisesRegex(CheckError, r"SetEffect: what follows it in its Sequential never runs"):
            check_never_finishing([g_seq([effect, g_wait(1.0)])])


class RulesTest(unittest.TestCase):
    def test_rules_that_end_the_battle_fail(self):
        self.assertEqual(check_rules([Node("TGDSpecificTacticalGameRules", [("Fow", TRUE)])]), 1)
        with self.assertRaisesRegex(CheckError, "sets CheckEndGame"):
            check_rules([Node("TGDSpecificTacticalGameRules", [("CheckEndGame", TRUE)])])


class ProdMenuSwitchTest(unittest.TestCase):
    """The buy-menu switch the content asks for is what its HUD restores ship."""

    def content(self, switch: int):
        return Content("x", (), None, {}, (), scenario="challenge_X", mod_name="X", menu_renames=(),
                       prod_menu_switch=switch)

    def test_no_restore(self):
        """A script with no HUD restore passes while the content keeps ForceHide; asking for another switch fails."""
        self.assertEqual(check_prod_menu_switch(self.content(BRICK_FORCE_HIDE), [g_wait(1.0)]), 0)
        with self.assertRaisesRegex(CheckError, "x: the content asks for ShowProdMenuSwitchMenuTypeButtons 0 "
                                                r"\(Content.prod_menu_switch\), but the script has no HUD restore"):
            check_prod_menu_switch(self.content(BRICK_DEFAULT), [g_wait(1.0)])

    def test_restores_ship_the_contents_switch(self):
        restore = Node("TGDDescriptorForceDisplayUIElement", [(PROD_MENU_SWITCH, i32(BRICK_FORCE_HIDE))])
        self.assertEqual(check_prod_menu_switch(self.content(BRICK_FORCE_HIDE), [restore]), 1)
        with self.assertRaisesRegex(CheckError, r"set ShowProdMenuSwitchMenuTypeButtons to \[1\], but the content "
                                                r"asks for 0"):
            check_prod_menu_switch(self.content(BRICK_DEFAULT), [restore])


class PackageTest(unittest.TestCase):
    def test_scenario_only(self):
        ok = [mem_item("Definition", "NDF/Scenarios/GDScript/challenge_X.ndfbin", b"x", "generate", "t"),
              mem_item("Details", "out/LevelDesign.ndfbin", b"x", "generate", "t")]
        check_package(ok, "challenge_X")
        with self.assertRaisesRegex(CheckError, "GameData/Gameplay/Decks.ndfbin: not under challenge_X"):
            check_package(ok + [mem_item("GameData", "GameData/Gameplay/Decks.ndfbin", b"x", "copy", "t")],
                          "challenge_X")

    def test_no_gameplay_file(self):
        """The game's own lookup (modkit.core.packaging.is_gameplay_file, the one rule): a file under Gen/ ending with
        one of the 16 GAMEPLAY_FILES makes the mod Gameplay, even when its path holds the scenario id; the same name
        outside Gen/ does not."""
        ok = [mem_item("Definition", "NDF/Scenarios/GDScript/challenge_X.ndfbin", b"x", "generate", "t"),
              mem_item("Loose", "challenge_X/GFX/Unit.ndfbin", b"x", "copy", "t")]   # not under Gen/
        self.assertEqual(check_package(ok, "challenge_X"), 2)
        self.assertEqual(len(GAMEPLAY_FILES), 16)
        bad = [("Loose", f"Gen/challenge_X/{f}") for f in GAMEPLAY_FILES] + [("Definition",
                                                                              "Gen/challenge_X/GFX/Deck.ndfbin")]
        for pack, path in bad:
            with self.subTest(path=path), self.assertRaisesRegex(CheckError, f"{pack}:{path}: a Gameplay file"):
                check_package(ok + [mem_item(pack, path, b"x", "copy", "t")], "challenge_X")


class StringsGateTest(unittest.TestCase):
    def test_the_table_holds_exactly_the_dictionaries(self):
        with self.assertRaisesRegex(StringError, r"x: the string table must hold exactly \['A', 'B'\]; unknown "
                                                 r"\['C'\], missing \['B'\]"):
            check_strings("x", {"A": {}, "C": {}}, ("A", "B"), (), [])
        self.assertTrue(issubclass(StringError, CheckError))  # so a profile can review it

    def test_no_stock_chinese_dictionaries_fails(self):
        with self.assertRaisesRegex(CheckError, "no stock"):
            check_strings("x", {"A": {}}, ("A",), (), [])


if __name__ == "__main__":
    unittest.main()
