"""Tests for modkit.ops.script: the HUD restore, the deployment phase, silent dialog voices, the hold skeleton."""
import unittest

from modkit.core.gates import CheckError
from modkit.ops.bricks import g_seq, g_wait
from modkit.ops.graph import Node, build_graph, decode, encode, i32, loc
from modkit.ops.script import (
    BRICK_DEFAULT, BRICK_FORCE_HIDE, BRICK_FORCE_SHOW, DEPLOY_INITIAL_PHASE, FOREVER, PROD_MENU_SWITCH, PRODUCTION_DECK,
    PRODUCTION_TYPE, SILENCE, Templates, deploy_phase, hold_script, hud_restore, silent_cutscenes,
)

RULES = "TGDSpecificTacticalGameRules"
HUD = "TGDDescriptorForceDisplayUIElement"
HIDE_ORDER = ["ShowLaunchBattleButton", "ShowMinimap", "ShowProdMenu", PROD_MENU_SWITCH, "ShowTopBar"]


def template(restore_switch: int = BRICK_FORCE_HIDE):
    """A three-object template script: #0 game rules, #1 the HUD hide node (stock order), #2 the HUD restore."""
    rules = Node(RULES, [("InitialGamePhase", i32(2)), ("CheckEndGame", i32(1))])
    hide = Node(HUD, [(name, i32(1)) for name in HIDE_ORDER])
    restore = Node(HUD, [("ShowMinimap", i32(2)), (PROD_MENU_SWITCH, i32(restore_switch)), ("ShowTopBar", i32(1))])
    nb, _, _ = decode(encode(build_graph([rules, hide, restore], []), "tpl"))
    return nb


TEMPLATES = Templates((0, RULES, ()), (1, HUD, ()), (2, HUD, ("ShowMinimap",)))


def values(props) -> list[tuple[str, int]]:
    return [(name, v.v) for name, v in props]


class HudRestoreTest(unittest.TestCase):
    """Both values of the buy-menu switch: ForceHide keeps the template's node as it is, Default leaves the switch
    out."""

    def test_force_hide_keeps_the_template(self):
        self.assertEqual(values(hud_restore(template(), TEMPLATES, False, BRICK_FORCE_HIDE)),
                         [(PROD_MENU_SWITCH, 1), ("ShowTopBar", 1)])

    def test_default_leaves_the_switch_out(self):
        self.assertEqual(values(hud_restore(template(), TEMPLATES, False, BRICK_DEFAULT)), [("ShowTopBar", 1)])

    def test_deploy_shows_launch_button_buy_menu_and_top_bar_in_stock_order(self):
        self.assertEqual(values(hud_restore(template(), TEMPLATES, True, BRICK_FORCE_HIDE)),
                         [("ShowLaunchBattleButton", 2), ("ShowProdMenu", 2), (PROD_MENU_SWITCH, 1),
                          ("ShowTopBar", 2)])
        self.assertEqual(values(hud_restore(template(), TEMPLATES, True, BRICK_DEFAULT)),
                         [("ShowLaunchBattleButton", 2), ("ShowProdMenu", 2), ("ShowTopBar", 2)])

    def test_never_force_show(self):
        with self.assertRaisesRegex(CheckError, "only Default"):
            hud_restore(template(), TEMPLATES, False, BRICK_FORCE_SHOW)

    def test_template_must_force_hide_the_switch(self):
        with self.assertRaisesRegex(CheckError, "no longer force-hides"):
            hud_restore(template(BRICK_DEFAULT), TEMPLATES, False, BRICK_FORCE_HIDE)


class DeployPhaseTest(unittest.TestCase):
    def phase(self, zones, hint):
        joueur, group = Node("TGDVariableCamp"), Node("TGDVariableUnitGroup")
        return joueur, group, deploy_phase(template(), TEMPLATES, joueur, group, zones, points=1500, income=150,
                                           hint=hint, refresh_export="$/GDScript/M/JoueurRefresh", refresh_s=2.0)

    def test_setup_points_income_and_zone_owner(self):
        zone = Node("TGDTagPosition")
        joueur, _, dp = self.phase([zone], None)
        self.assertEqual([nd.cls for nd in dp.setup],
                         ["TGDDescriptorChangeProductionType", "TGDDescriptorSetRessourceForTeam",
                          "TGDDescriptorSetIncomeToTeam", "TGDDescriptorSetCommandZoneOwnerAndForceConvergence"])
        self.assertEqual(dict(dp.setup[1].props)["Quantite"].v, 1500)
        self.assertEqual(dict(dp.setup[2].props)["Quantite"].v, 150)
        self.assertEqual(dict(dp.setup[3].props), {"Camp": joueur, "Positions": [zone]})
        _, _, dp = self.phase([], None)
        self.assertEqual(len(dp.setup), 3)

    def test_production_type_and_a_zero_income(self):
        """The buy menu opens on stock's Groups (PRODUCTION_TYPE, 1) unless a content asks for its Deck view
        (PRODUCTION_DECK, 0, written as asked); an income of 0 is written with no amount, as stock writes it
        (RunningTheGauntlet #275); any other income as before."""
        joueur, group = Node("TGDVariableCamp"), Node("TGDVariableUnitGroup")
        kw = dict(points=2000, hint=None, refresh_export="$/GDScript/M/JoueurRefresh", refresh_s=2.0)
        plain = deploy_phase(template(), TEMPLATES, joueur, group, [], income=150, **kw)
        deck = deploy_phase(template(), TEMPLATES, joueur, group, [], income=0, production_type=PRODUCTION_DECK, **kw)
        self.assertEqual((PRODUCTION_TYPE, PRODUCTION_DECK), (1, 0))
        self.assertEqual(plain.setup[0].props, [("ProductionType", i32(PRODUCTION_TYPE))])
        self.assertEqual(deck.setup[0].props, [("ProductionType", i32(0))])
        self.assertEqual(plain.setup[2].props, [("Camp", joueur), ("Quantite", i32(150))])
        self.assertEqual(deck.setup[2].props, [("Camp", joueur)])

    def test_refresh_loop(self):
        joueur, group, dp = self.phase([], None)
        self.assertEqual(dp.refresh.export, "$/GDScript/M/JoueurRefresh")
        props = dict(dp.refresh.props)
        self.assertEqual(props["NbExecutions"].v, FOREVER)
        add, wait = props["SubActions"]
        self.assertEqual((add.cls, dict(add.props)["Group"], dict(wait.props)["Duree"].v),
                         ("TGDDescriptorAddAllCampUnitsToUnitGroup", group, 2.0))

    def test_launch_waits_for_the_battle_phase_with_and_without_a_hint(self):
        _, _, bare = self.phase([], None)
        self.assertEqual(bare.launched.cls, "TGDDescriptorWaitCondition")
        _, _, hinted = self.phase([], "m_hint")
        self.assertEqual(hinted.launched.cls, "TGDDescriptorCompetition")
        hint, wait = dict(hinted.launched.props)["SubActions"]
        self.assertEqual((hint.cls, dict(hint.props)["Info"], wait.cls),
                         ("TGDDescriptorLDHint", loc("m_hint"), "TGDDescriptorWaitCondition"))

    def test_game_rules_start_in_the_deployment_phase(self):
        _, _, dp = self.phase([], None)
        self.assertEqual(values(dp.game_rules.props), [("InitialGamePhase", DEPLOY_INITIAL_PHASE), ("CheckEndGame", 1)])


class SilentCutscenesTest(unittest.TestCase):
    def test_one_silent_descriptor_per_token(self):
        db = silent_cutscenes(["m_a", "m_b"])
        descs = dict(db.props)["CutsceneDescriptorList"]
        self.assertEqual([dict(d.props)["Key"] for d in descs], [loc("m_a"), loc("m_b")])
        stream = dict(dict(dict(descs[0].props)["DefaultSoundDescriptor"].props)["TheSoundStream"].props)
        self.assertEqual((stream["FileName"].text, stream["FileName"].tag), (SILENCE, 0x1C))


class HoldScriptTest(unittest.TestCase):
    """The two forms the skeleton's two callers build: two camps with a loop beside the objective and an extra
    variable, and four camps with nothing beside it."""

    def build(self, n_camps: int, with_loop: bool, switch: int = BRICK_FORCE_HIDE):
        gd = "$/GDScript"
        camps = [Node("TGDVariableCamp", export=f"{gd}/RootDescriptor/c{k}") for k in range(n_camps)]
        tags = {"Tags/A": Node("TGDTagPosition", export=f"{gd}/GdItems/Tags/A"),
                "Camp_0/P": Node("TGDTagUnitGroup", export=f"{gd}/GdItems/Camp_0/P")}
        wave = Node("TGDVariableUnitGroup", export=f"{gd}/M/Variables/Wave")
        loop = g_seq([g_wait(60.0)], runs=FOREVER, export=f"{gd}/M/WaveLoop")
        setup = [Node("TGDDescriptorSetDeck", [("Camp", c)]) for c in camps]
        roots, exports = hold_script(template(), TEMPLATES, folder=f"{gd}/M", camps=camps, setup=setup, tags=tags,
                                     player_tags=[tags["Camp_0/P"]], hold_at=tags["Tags/A"], hold_s=600,
                                     intro="m_intro", objective=("m_obj", "m_objl"), start_delay_s=1.0,
                                     parallel=[loop] if with_loop else [], variables=[wave] if with_loop else [],
                                     prod_menu_switch=switch)
        return roots, exports, camps, loop, wave

    def test_with_a_loop_and_a_variable(self):
        roots, exports, camps, loop, wave = self.build(2, True)
        self.assertEqual([nd.export.rsplit("/", 1)[-1] for nd in exports],
                         ["RootDescriptor", "c0", "c1", "A", "P", "Main", "Objective", "WaveLoop", "Mission_Success",
                          "Mission_Fail", "Groupe_Joueur", "Wave", "HoldTimer"])
        main = next(nd for nd in exports if nd.export.endswith("/Main"))
        steps = dict(main.props)["SubActions"]
        self.assertEqual([nd.cls for nd in steps],
                         ["TGDDescriptorSetDeck", "TGDDescriptorSetDeck", HUD, "TGDDescriptorLoadingDone",
                          "TGDDescriptorAddUnitGroupListToUnitGroup", "TGDDescriptorEncapsuleCutscene", HUD,
                          "TGDDescriptorWaitCondition", "TGDDescriptorStartTimer", "TGDDescriptorSimultaneous"])
        self.assertEqual([nd.export for nd in dict(steps[-1].props)["SubActions"]],
                         ["$/GDScript/M/Objective", "$/GDScript/M/WaveLoop"])
        self.assertEqual(values(steps[6].props), [(PROD_MENU_SWITCH, 1), ("ShowTopBar", 1)])
        self.assertEqual(dict(roots[1].props)["CampList"], camps)
        encode(build_graph(roots, exports), "GDScript")  # a valid graph

    def test_without_a_loop(self):
        roots, exports, camps, _, _ = self.build(4, False)
        self.assertEqual([nd.export.rsplit("/", 1)[-1] for nd in exports],
                         ["RootDescriptor", "c0", "c1", "c2", "c3", "A", "P", "Main", "Objective", "Mission_Success",
                          "Mission_Fail", "Groupe_Joueur", "HoldTimer"])
        objective = next(nd for nd in exports if nd.export.endswith("/Objective"))
        props = dict(objective.props)
        self.assertEqual((props["ObjectiveText"], props["ObjectiveEtiquetteText"]), (loc("m_obj"), loc("m_objl")))
        timer = next(nd for nd in exports if nd.export.endswith("/HoldTimer"))
        self.assertEqual(dict(timer.props)["Duree"].v, 600)
        self.assertEqual(dict(dict(roots[0].props)["CutsceneDescriptorList"][0].props)["Key"], loc("m_intro"))
        encode(build_graph(roots, exports), "GDScript")

    def test_prod_menu_switch_is_the_callers(self):
        """The HUD restore carries the caller's buy-menu switch: Default leaves the property out (stock's form)."""
        for switch, want in ((BRICK_FORCE_HIDE, [(PROD_MENU_SWITCH, 1), ("ShowTopBar", 1)]),
                             (BRICK_DEFAULT, [("ShowTopBar", 1)])):
            with self.subTest(switch=switch):
                _, exports, _, _, _ = self.build(2, False, switch)
                main = next(nd for nd in exports if nd.export.endswith("/Main"))
                restore = [nd for nd in dict(main.props)["SubActions"] if nd.cls == HUD][1]
                self.assertEqual(values(restore.props), want)


if __name__ == "__main__":
    unittest.main()
