"""Tests for the shared gates under Open Door's settings: its sides, its funnel and Geisa's west-edge arrivals,
on synthetic layouts and scripts (item GUIDs and spawns, the arrivals and tier gates, the in-game dictionary, objective
pins, the end funnel, dialog text, the game rules, the deployment-phase block and the buy-menu switch).

Classes that read the stock extraction skip without it.
"""
from __future__ import annotations

import dataclasses
import unittest
import uuid

from modkit.core import ndfbin, paths
from modkit.core.gates import CheckError
from modkit.ops import INGAME_DIC, gates
from modkit.ops.bricks import (
    g_cmp, g_dialog, g_hint, g_if, g_seq, g_set, g_simul, g_until, g_wait, g_zone_owner,
)
from modkit.ops.files import read_file
from modkit.ops.gates import check_canonical, check_shapes, survey_shapes
from modkit.ops.graph import TRUE, Node, Str, build_graph, decode, encode, i32, loc, walk
from modkit.ops.leveldesign import LD_FILE, LdItem, leveldesign_graph
from modkit.ops.maps import GEISA
from modkit.ops.profile import SURVIVORS, Content, extracted
from modkit.ops.script import BRICK_DEFAULT, BRICK_FORCE_HIDE, BRICK_FORCE_SHOW, PROD_MENU_SWITCH, silent_cutscenes
from modkit.ops.strings import LANGS
from modkit.ops.shapes import camp_nodes, setdeck_block
from modkit.ops.zones import rect_polygon
from open_door_support import (
    SCRIPT_DATA, check_end_funnel, check_tiers, details_files, gd_tags, ld_guid, tier_violations, zone_owner_actions,
)
from opendoor import CONTENTS, profile
from opendoor.map import MAP, POINTS
from probes import spike2 as probe2

INGAME_DATA = paths.skip_unless_extracted("glad_201602", "Localisation", "Core")

def spawn_props(it: LdItem) -> list[str]:
    """Property names of the Spawn add-on, read back from the encoded LevelDesign."""
    raw = encode(build_graph(leveldesign_graph([it], profile.SCENARIO, profile.GUID_NAMESPACE), [],
                             frozenset({"Name", "Ranking", "GUID"})), "LD")
    nb, _, _ = decode(raw)
    ob = next(ob for ob in nb.objects if nb.cname(ob.cls) == "TGameDesignAddOn_Spawn")
    return [nb.pname(pi) for pi, _ in ob.props]


class Items(unittest.TestCase):
    def test_od_guid_namespace(self):
        it = MAP.item("Tags", "OD_NeckMid", "NECK_MID", "Name")
        want = uuid.uuid5(uuid.NAMESPACE_URL, "warno-opendoor/challenge_OperationOpenDoor/Tags/OD_NeckMid").bytes
        self.assertEqual(ld_guid(it, profile.SCENARIO), want)

    def test_od_item_position(self):
        it = MAP.item("Tags", "A", "NECK_MID", "Name")
        self.assertEqual((it.x, it.y), GEISA.px_to_world(POINTS["NECK_MID"]))
        it = MAP.item("Tags", "B", (10, 20), "Name")
        self.assertEqual((it.x, it.y), GEISA.px_to_world((10, 20)))
        with self.assertRaisesRegex(CheckError, "NO_SUCH_POINT"):
            MAP.item("Tags", "C", "NO_SUCH_POINT", "Name")

    def test_hidden_spawn_item(self):
        hidden = MAP.item("Camp_0", "OD_Hidden", "HIDE_S", "Spawn", unit="M1A1HA_Abrams_US", camp=0,
                              disable_auto_spawn=True)
        names = spawn_props(hidden)
        self.assertEqual(names[-1], "DisableAutoSpawn")
        self.assertNotIn("Camp", names)
        names = spawn_props(MAP.item("Camp_2", "OD_Other", "HIDE_S", "Spawn", unit="M1A1HA_Abrams_US", camp=2))
        self.assertLess(names.index("Camp"), names.index("ClassName"))
        self.assertEqual(names[:6], ["Name", "Ranking", "GUID", "AutoNameBase", "Camp", "ClassName"])


class Arrivals(unittest.TestCase):
    DZ = MAP.item("DeploymentZone", "OD_DZ_T", "NECK_MID", "DeploymentZone")

    def test_geisa_west_entries(self):
        """Geisa 10vs10 CONQ's own west-edge entries, verbatim but for NumAlliance (omitted: the player's side)."""
        got = GEISA.player_arrivals("OD")
        self.assertEqual([(it.ranking, it.addon) for it in got],
                         [("ReinforcementLocations", "ReinforcementLocation")] * 2 + [("AerialCorridors", "AerialCorridor")] * 2)
        self.assertEqual({it.num_alliance for it in got}, {None})
        rl7 = next(it for it in got if it.name == "OD_RL_W2")  # Geisa P0_AutoName_7, the road at EDGE W
        self.assertEqual((rl7.start, rl7.end, (rl7.x, rl7.y)),
                         ((11677.0, 1514376.0), (64050.0, 1515041.0), (37863.496, 1514708.5)))

    def test_deploy_phase_needs_player_arrivals(self):
        """Probe 1's third launch: a player deployment zone, but nowhere for units bought after the launch to arrive
        [[deployment-phase-recipe]]."""
        arrivals = GEISA.player_arrivals("OD")
        self.assertEqual(gates.check_arrivals([self.DZ, *arrivals]), (2, 2))
        self.assertEqual(gates.check_arrivals(arrivals[:1]), (0, 0))  # no deployment phase: nothing to check
        with self.assertRaisesRegex(CheckError, "no player reinforcement location"):
            gates.check_arrivals([self.DZ, *arrivals[2:]])
        with self.assertRaisesRegex(CheckError, "no player aerial corridor"):
            gates.check_arrivals([self.DZ, *arrivals[:2]])
        enemy = [dataclasses.replace(it, num_alliance=1) for it in arrivals]
        with self.assertRaisesRegex(CheckError, "no player reinforcement location"):
            gates.check_arrivals([self.DZ, *enemy])

    @staticmethod
    def zone(name: str, addon: str, box: tuple[float, float, float, float], **kw) -> LdItem:
        """A zone item over a world box, the item at its centre."""
        x0, y0, x1, y1 = box
        return LdItem(addon, name, (x0 + x1) / 2, (y0 + y1) / 2, addon, polygon=tuple(rect_polygon(box)),
                           **kw)

    def ends(self, items: list[LdItem]) -> tuple[dict[str, int], list[str]]:
        files = details_files(items)
        return gates.arrival_violations(files[LD_FILE], files.get("out/DeploymentZone.ndfbin"),
                                       files.get("out/CommandZone.ndfbin"))

    def test_end_in_a_player_zone(self):
        """Gate 3 reads where the game reads: each player arrival's End lies in a player DZ or any CZ, from the shipped
        Details bytes. An End in the enemy's DZ only fails for a player entry; a -1 entry ending there is the enemy's
        (stock multiplayer), and is not counted."""
        arrivals = GEISA.player_arrivals("OD")                                # Ends at x 61,618..66,868
        dz = self.zone("OD_DZ_T", "DeploymentZone", (33280, 640000, 1382400, 1996800))
        cz = self.zone("OD_CZ_T", "CommandPoints", (20000, 900000, 100000, 1000000), points=1)  # holds RL_W1, AC_W1
        far = self.zone("OD_DZ_T", "DeploymentZone", (230400, 640000, 1382400, 1996800))
        both = {"ReinforcementLocation": 2, "AerialCorridor": 2}
        self.assertEqual(self.ends([dz, *arrivals]), (both, []))
        self.assertEqual(gates.check_arrivals([dz, *arrivals], details_files([dz, *arrivals])), (2, 2))
        counts, bad = self.ends([far, cz, *arrivals])
        self.assertEqual((counts, [b.split(":")[0] for b in bad]), (both, ["OD_AC_W2", "OD_RL_W2"]))
        self.assertIn("166,350 W of OD_DZ_T", bad[1])
        enemy = dataclasses.replace(dz, alliance=1)
        _, bad = self.ends([far, enemy, *arrivals])
        self.assertEqual(len(bad), 4)
        self.assertTrue(all("(only in a DZ of alliance 1)" in b for b in bad), bad)
        multi = [dataclasses.replace(it, num_alliance=-1) for it in arrivals]
        self.assertEqual(self.ends([far, enemy, *multi]), (dict.fromkeys(both, 0), []))
        with self.assertRaisesRegex(CheckError, r"(?s)4 player arrivals end outside every player deployment zone"
                                                     r".*OD_RL_W1: End \(66,701, 969,031\) lies in no player deployment "
                                                     r"zone and no command zone, 163,699 W of OD_DZ_T.*83/83.*nothing "
                                                     r"bought arrive"):
            gates.check_arrivals([far, *arrivals], details_files([far, *arrivals]))

    def test_end_in_a_command_zone_only_fails(self):
        """Ours, stricter than stock [[arrival-end-in-zone]]: an End held only by a command zone passes stock's rule,
        but the corridor follows the zone's owner, so a zone the Soviets take or contest gives it away."""
        arrivals = GEISA.player_arrivals("OD")                                # Ends at x 61,618..66,868
        far = self.zone("OD_DZ_T", "DeploymentZone", (230400, 640000, 1382400, 1996800))
        cz = self.zone("OD_CZ_T", "CommandPoints", (10000, 900000, 100000, 1600000), points=1)  # holds all four Ends
        items = [far, cz, *arrivals]
        self.assertEqual(self.ends(items), ({"ReinforcementLocation": 2, "AerialCorridor": 2}, []))  # stock's rule
        with self.assertRaisesRegex(CheckError, r"(?s)4 player arrivals end in a command zone only.*\n  OD_RL_W1: "
                                                     r"End \(66,701, 969,031\) lies in no player deployment zone, "
                                                     r"163,699 W of OD_DZ_T\n.*Cover each End with a player deployment "
                                                     r"zone too"):
            gates.check_arrivals(items, details_files(items))


class Tiers(unittest.TestCase):
    """Gate 3 tiers, the tier rule, proven on synthetic contents: one passing tiered content and one failing case per
    clause. The synthetic layout: a player deployment zone holding Geisa's west-edge entries
    (the permanent tier), and one command zone holding the End of OD_RL_T, forced to NATO before LoadingDone and handed
    to PACT later."""

    zone = staticmethod(Arrivals.zone)
    DZ_BOX = (33280, 640000, 300000, 1996800)          # holds the west arrivals' Ends (x 61,618..66,868)
    CZ_BOX = (900000, 900000, 1000000, 1000000)

    def setUp(self):
        self.dz = self.zone("OD_DZ_T", "DeploymentZone", self.DZ_BOX)
        self.cz = self.zone("OD_CZ_T", "CommandPoints", self.CZ_BOX, points=1)
        self.tier = LdItem("ReinforcementLocations", "OD_RL_T", 900000.0, 950000.0, "ReinforcementLocation",
                                rotation=0.0, start=(850000.0, 950000.0), end=(950000.0, 950000.0))
        self.camps = camp_nodes(profile.CAMP_ROWS, profile.CAMP_TOKENS)

    def layout(self, *extra: LdItem, tier: LdItem | None = None,
               arrivals: list[LdItem] | None = None) -> list[LdItem]:
        return [self.dz, self.cz, *(GEISA.player_arrivals("OD") if arrivals is None else arrivals), tier or self.tier,
                *extra]

    def roots(self, items: list[LdItem], load: str = "before", pact: bool = True) -> list[Node]:
        """Main = Sequential[owner(joueur) if load == "before", LoadingDone, owner(joueur) if load == "after",
        Simultaneous[owner(PACT) if pact]] over OD_CZ_T's tag."""
        tag = gd_tags(items)["CommandPoints/OD_CZ_T"]
        nato = [g_zone_owner(self.camps[profile.CAMPS["NATO"]], [tag])]
        return [g_seq([*(nato if load == "before" else []), Node("TGDDescriptorLoadingDone"),
                            *(nato if load == "after" else []),
                            g_simul([g_zone_owner(self.camps[profile.CAMPS["PACT"]], [tag])] if pact else [])])]

    def bad(self, items: list[LdItem], tiered: tuple[str, ...] = ("OD_RL_T",), **kw: object) -> list[str]:
        return tier_violations(tiered, self.roots(items, **kw), details_files(items))[1]

    def content(self, items: list[LdItem], tiered: tuple[str, ...] = ("OD_RL_T",)) -> Content:
        return Content("t", tuple(items), lambda tpl: ([], []), {}, (), tiered_arrivals=tiered,
                       scenario=profile.SCENARIO, mod_name=profile.MOD_NAME, menu_renames=profile.MENU_RENAMES)

    def test_tiered_content_passes(self):
        """The passing tiered content: gate 3 tiers counts it, and check_arrivals' command-zone-only rule skips it only
        when it is named tiered."""
        items = self.layout()
        details = details_files(items)
        counts, bad = tier_violations(("OD_RL_T",), self.roots(items), details)
        self.assertEqual((counts, bad), ({"tiered": 1, "permanent": 2, "forced to the player at load": 1,
                                          "handed to the enemy": 1}, []))
        self.assertEqual(check_tiers(self.content(items), self.roots(items), details), 1)
        self.assertEqual(gates.check_arrivals(items, details, ("OD_RL_T",)), (3, 2))
        with self.assertRaisesRegex(CheckError, r"(?s)1 player arrivals end in a command zone only.*OD_RL_T.*"
                                                     r"Content.tiered_arrivals \(gate 3 tiers\)"):
            gates.check_arrivals(items, details)

    def test_untiered_command_zone_end_fails_clause_1(self):
        self.assertEqual(self.bad(self.layout(), tiered=()),
                         ["[tiers.1] OD_RL_T: its End (950,000, 950,000) lies in no player deployment zone, and the "
                          "entry is not tiered (Content.tiered_arrivals)"])

    def test_tiered_entry_shape_fails_clause_2(self):
        """A tiered aerial corridor, a tiered entry with NumAlliance -1, an End in no command zone, an End in a
        deployment zone of any side as well, and a tiered name that names no entry."""
        corridor = dataclasses.replace(self.tier, ranking="AerialCorridors", name="OD_AC_T", addon="AerialCorridor")
        self.assertIn("[tiers.2] OD_AC_T: tiered, but it is an AerialCorridor: aircraft arrive only in the permanent "
                      "tier", self.bad(self.layout(corridor), tiered=("OD_RL_T", "OD_AC_T")))
        self.assertEqual(self.bad(self.layout(tier=dataclasses.replace(self.tier, num_alliance=-1))),
                         ["[tiers.2] OD_RL_T: tiered, but its NumAlliance is -1: omit it or write 0, so a zone the "
                          "enemy holds closes it for both sides"])
        self.assertEqual(self.bad(self.layout(tier=dataclasses.replace(self.tier, end=(1100000.0, 950000.0)))),
                         ["[tiers.2] OD_RL_T: tiered, but its End (1,100,000, 950,000) lies in 0 command zones, not "
                          "exactly one"])
        enemy_dz = self.zone("OD_DZ_E", "DeploymentZone", (940000, 940000, 960000, 960000), alliance=1)
        self.assertEqual(self.bad(self.layout(enemy_dz)),
                         ["[tiers.2] OD_RL_T: tiered, but its End (950,000, 950,000) lies in deployment zone OD_DZ_E, "
                          "whose owner never changes: the tier would never close"])
        self.assertEqual(self.bad(self.layout(), tiered=("OD_RL_T", "OD_RL_X")),
                         ["[tiers.2] OD_RL_X: tiered, but 0 reinforcement locations or aerial corridors carry the "
                          "name, not one"])

    def test_tiered_name_on_two_entries_fails_clause_2(self):
        """A tiered name carried by two entries (here a reinforcement location and an aerial
        corridor, one name in two rankings)."""
        twin = dataclasses.replace(self.tier, ranking="AerialCorridors", addon="AerialCorridor")
        self.assertEqual(self.bad(self.layout(twin)),
                         ["[tiers.2] OD_RL_T: tiered, but 2 reinforcement locations or aerial corridors carry the "
                          "name, not one"])

    def test_tiered_end_in_a_player_zone_fails_clause_2(self):
        """A tiered End inside a player deployment zone (the DZ is checked first and its owner never
        changes, so the tier would never close)."""
        own_dz = self.zone("OD_DZ_P", "DeploymentZone", (940000, 940000, 960000, 960000))
        self.assertEqual(self.bad(self.layout(own_dz)),
                         ["[tiers.2] OD_RL_T: tiered, but its End (950,000, 950,000) lies in deployment zone OD_DZ_P, "
                          "whose owner never changes: the tier would never close"])

    def test_zone_not_forced_at_load_fails_clause_3(self):
        """The joueur hand-over after LoadingDone, or none: the tier starts closed."""
        want = ["[tiers.3] OD_RL_T: its command zone OD_CZ_T is not forced to joueur at load (no "
                "SetCommandZoneOwnerAndForceConvergence(joueur) before LoadingDone holds a tag in it), so the tier "
                "starts closed"]
        for load in ("after", "none"):
            with self.subTest(load=load):
                self.assertEqual(self.bad(self.layout(), load=load), want)

    def test_zone_never_handed_to_pact_fails_clause_4(self):
        self.assertEqual(self.bad(self.layout(), pact=False),
                         ["[tiers.4] OD_RL_T: its command zone OD_CZ_T is never handed to ordinateur_SOV (no "
                          "SetCommandZoneOwnerAndForceConvergence(ordinateur_SOV) holds a tag in it), so the tier "
                          "never closes"])

    def test_pact_forcing_at_load_is_no_hand_over(self):
        """A PACT forcing before LoadingDone (a direct child, or nested in a container before it)
        would start the tier closed; it is no hand-over, so with no later one tiers.4 fails. One after LoadingDone
        passes."""
        items = self.layout()
        details = details_files(items)
        tag = gd_tags(items)["CommandPoints/OD_CZ_T"]
        nato, pact = (lambda side=side: g_zone_owner(self.camps[profile.CAMPS[side]], [tag])
                      for side in ("NATO", "PACT"))
        done = Node("TGDDescriptorLoadingDone")
        early = {"direct": g_seq([nato(), pact(), done]),
                 "nested": g_seq([nato(), g_simul([pact()]), done])}
        for case, roots in early.items():
            with self.subTest(case=case):
                load, handed = zone_owner_actions([roots])
                self.assertEqual((len(load), handed), (1, []))
                self.assertEqual(tier_violations(("OD_RL_T",), [roots], details)[1],
                                 ["[tiers.4] OD_RL_T: its command zone OD_CZ_T is never handed to ordinateur_SOV (no "
                                  "SetCommandZoneOwnerAndForceConvergence(ordinateur_SOV) holds a tag in it), so the "
                                  "tier never closes"])
        later = g_seq([nato(), pact(), done, g_simul([pact()])])
        self.assertEqual(len(zone_owner_actions([later])[1]), 1)
        self.assertEqual(tier_violations(("OD_RL_T",), [later], details)[1], [])

    def test_no_permanent_tier_fails_clause_5(self):
        """No reinforcement location ends in a player deployment zone (only aircraft would), or an aerial corridor
        ends in a command zone."""
        corridors = [it for it in GEISA.player_arrivals("OD") if it.addon == "AerialCorridor"]
        self.assertEqual(self.bad(self.layout(arrivals=corridors)),
                         ["[tiers.5] no player reinforcement location ends in a player deployment zone: once every "
                          "tier closes, nothing bought arrives (the permanent tier)"])
        corridor = dataclasses.replace(self.tier, ranking="AerialCorridors", name="OD_AC_T", addon="AerialCorridor")
        self.assertEqual(self.bad(self.layout(corridor)),
                         ["[tiers.5] OD_AC_T: an aerial corridor whose End (950,000, 950,000) lies in no player "
                          "deployment zone: aircraft arrive only in the permanent tier"])

    def test_check_tiers(self):
        """check_tiers fails with every line and the rule; without a deployment phase it checks nothing, and a
        content may name no tiered entry then."""
        items = self.layout()
        with self.assertRaisesRegex(CheckError, r"(?s)1 arrivals break the tier rule \(gate 3 tiers\):"
                                                     r"\n  \[tiers\.4\] OD_RL_T.*\nA tiered entry is a "
                                                     r"ReinforcementLocation"):
            check_tiers(self.content(items), self.roots(items, pact=False), details_files(items))
        bare = [it for it in items if it.addon != "DeploymentZone"]
        self.assertEqual(check_tiers(self.content(bare, ()), [], details_files(bare)), 0)
        with self.assertRaisesRegex(CheckError, "tiered arrivals .'OD_RL_T'. but no deployment phase"):
            check_tiers(self.content(bare), [], details_files(bare))

def dialog_nb(button0: str, button1: str) -> ndfbin.NdfBin:
    """A multiple-choice dialog and its text component, as probe 1's start_dialog writes them."""
    nb = ndfbin.NdfBin()
    text = nb.intern_class("TGDDescriptorCutsceneTextComponent")
    nb.objects.append(ndfbin.Obj(text, [(nb.intern_prop("LocalizedText", text), ndfbin.loc_value("od_start"))]))
    c = nb.intern_class("TGDDescriptorCutsceneDialogWithMultipleChoice")
    nb.objects.append(ndfbin.Obj(c, [(nb.intern_prop("TokenBoutonChoix0", c), ndfbin.loc_value(button0)),
                                     (nb.intern_prop("TokenBoutonChoix1", c), ndfbin.loc_value(button1))]))
    return nb


def names(tokens: set[int]) -> list[str]:
    return sorted(ndfbin.token_unhash(t) for t in tokens)


@INGAME_DATA
class Dictionaries(unittest.TestCase):
    def test_button_tokens_go_to_ingame(self):
        """Dialog button labels resolve in the game's INGAME list; every other token in the scenario's dictionaries."""
        ours, ingame = gates.split_tokens(dialog_nb("od_c1x", "CMP_HARD"))
        self.assertEqual((names(ours), names(ingame)), (["od_start"], ["CMP_HARD", "od_c1x"]))

    def test_scenario_button_token_fails(self):
        """Probe 1's second launch [[dialog-button-ingame-dictionary]]: a scenario token on a dialog button is missing
        from the game's INGAME dictionary; stock buttons are in it in every language."""
        def misses(nb: ndfbin.NdfBin, lang: str) -> list[str]:
            return gates.ingame_misses(nb, extracted(INGAME_DIC.format(lang=lang)))

        self.assertEqual(misses(dialog_nb("od_c1x", "CMP_HARD"), "US"), ["od_c1x"])
        for lang in LANGS:
            with self.subTest(lang=lang):
                self.assertEqual(misses(dialog_nb("CMP_EASY", "CMP_HARD"), lang), [])


class Objectives(unittest.TestCase):
    """Gate 3: an objective that shows its map label (ShowEtiquette) needs a place for it. Probe 1's two positionless
    counters set ShowEtiquette and their pins sat in the map corner in its first play
    [[objective-label-needs-position]]."""

    @staticmethod
    def objective(*extra: tuple[str, object]) -> Node:
        return Node("TGDDescriptorGereObjectif", [("LabelComponent", Str("Primary")), *extra])

    def test_positionless_label_fails(self):
        with self.assertRaisesRegex(CheckError, "map corner"):
            gates.check_objective_pins([g_seq([self.objective(("ShowEtiquette", TRUE))])])

    def test_placed_or_unlabelled_pass(self):
        tag = Node("TGDTagPosition", export="$/GDScript/GdItems/Tags/OD_X")
        unit = Node("TGDVariableUnitGroup", export="$/GDScript/OD/Variables/G")
        roots = [g_seq([self.objective(("Position", tag), ("ShowEtiquette", TRUE)),
                             self.objective(("ShowEtiquette", TRUE), ("UnitGroupPositionList", [unit])),
                             self.objective()])]
        self.assertEqual(gates.check_objective_pins(roots), 2)

    def test_empty_unit_list_is_no_place(self):
        with self.assertRaisesRegex(CheckError, "map corner"):
            gates.check_objective_pins([self.objective(("ShowEtiquette", TRUE), ("UnitGroupPositionList", []))])


def objective(name: str = "od_o1", **props: object) -> Node:
    """A GereObjectif named `name` (ObjectiveText) with the given properties (ActionsReussi, ConditionEchec, ...)."""
    return Node("TGDDescriptorGereObjectif", [*sorted(props.items()), ("ObjectiveText", loc(name))])


def end_game(victory_type: int = 6, winner: int | None = None) -> Node:
    """TriggerEndGame in the stock encoding [[mission-ends-only-by-script]]: ScriptDecided, the grade, the loser's
    WinningAlliance 1 (the player's win omits it)."""
    props = [("VictoryReason", i32(6)), ("VictoryType", i32(victory_type))]
    return Node(gates.END_GAME, props + ([("WinningAlliance", i32(winner))] if winner else []))


class EndFunnel(unittest.TestCase):
    """Gate 3: the first TriggerEndGame wins [[mission-ends-only-by-script]], so every ending goes through the one
    funnel node or the ending race; two endings in one tick outside the race fail."""

    od_end = Node("TGDVariableInteger", export="$/GDScript/OD/Variables/od_end")

    def funnel(self) -> Node:
        return g_seq([g_until(g_cmp(self.od_end, 1, 2)),
                           g_if(g_cmp(self.od_end, 1), end_game(), end_game(winner=1))],
                          export=profile.END_FUNNEL)

    def race(self) -> Node:
        return g_simul([end_game(4), end_game(winner=1)], export=profile.END_RACE)

    def test_funnel_and_race_pass(self):
        guard = objective("od_guard", ActionsEchec=g_set(self.od_end, 2))   # P2's kind: sets od_end, no ending
        roots = [g_simul([self.funnel(), g_seq([g_wait(30.0), self.race()]), guard])]
        self.assertEqual(check_end_funnel(roots), (4, True))

    def test_ending_outside_fails(self):
        guard = objective("od_guard", ActionsEchec=end_game(5, winner=1))           # ends the game itself
        with self.assertRaisesRegex(CheckError, r"(?s)the end funnel does not hold every ending.*\n  "
                                                     r"TriggerEndGame\(VictoryReason 6, VictoryType 5, "
                                                     r"WinningAlliance 1\) is under neither "
                                                     r"\$/GDScript/OD/EndFunnel nor \$/GDScript/OD/EndRace.*"
                                                     r"let the one funnel node call TriggerEndGame"):
            check_end_funnel([g_simul([self.funnel(), guard])])
        shared = end_game(winner=1)  # one node both inside the race and reachable outside it
        race = g_simul([end_game(4), shared], export=profile.END_RACE)
        with self.assertRaisesRegex(CheckError, r"WinningAlliance 1\) is under neither"):
            check_end_funnel([g_simul([race, g_seq([g_wait(5.0), shared])])])

    def test_one_funnel_and_one_race(self):
        with self.assertRaisesRegex(CheckError, r"2 nodes are exported as \$/GDScript/OD/EndFunnel; a funnel has one"):
            check_end_funnel([g_simul([self.funnel(), self.funnel()])])


class DialogText(unittest.TestCase):
    def test_hint_passes(self):
        """A hint takes ListVariables, so its %1 is no dialog text (the probes' dialogs: test_probes.py)."""
        table = {"Scripting/Localization": {"od_h": ("%1 asks", "%1")},
                 "Scripting/Dialog": {"od_ask": ("Now?", "现在？")}}
        roots = [g_hint("od_h", 15.0, "shint"), g_dialog("od_ask")]
        self.assertEqual(gates.check_dialog_text(roots, table), 1)


class Rules(unittest.TestCase):
    """Gate 3: our rules leave the engine's endings off [[mission-ends-only-by-script]]."""

    def test_engine_ending_fields_fail(self):
        for name in gates.RULES_OMITTED:
            rules = Node("TGDSpecificTacticalGameRules", [("Fow", TRUE), (name, TRUE)])
            with self.subTest(name=name), self.assertRaisesRegex(CheckError, rf"sets {name}.*Survivors #114"):
                gates.check_rules([g_seq([]), rules])


class Script(unittest.TestCase):
    def test_walk_each_once(self):
        leaf = Node("Leaf")
        mid = Node("Mid", [("A", leaf), ("B", [leaf, [leaf]])])
        root = Node("Root", [("X", mid), ("Y", [mid, leaf]), ("Z", i32(1))])
        self.assertEqual([nd.cls for nd in walk([root, mid])], ["Root", "Mid", "Leaf"])

    @SCRIPT_DATA
    def test_deploy_phase_shapes(self):
        """The copied deploy-phase block, put in a script, lays out canonically and uses only stock shapes."""
        tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        camps = camp_nodes(profile.CAMP_ROWS, profile.CAMP_TOKENS)
        joueur = camps[profile.CAMPS["NATO"]]
        group = Node("TGDVariableUnitGroup", export="$/GDScript/OD/Variables/Groupe_Joueur")
        zone = Node("TGDTagPosition", [(f"GUID{k}", i32(k)) for k in range(1, 5)],
                         export="$/GDScript/GdItems/CommandPoints/OD_CZ")
        dp = profile.deploy_phase(tpl, joueur, group, [zone], 3000, hint="od_h2")
        rules = dict(dp.game_rules.props)
        self.assertEqual(rules["InitialGamePhase"].v, 1)
        off = {k: v.v for k, v in profile.hud_restore(tpl, deploy=False)}
        on = {k: v.v for k, v in profile.hud_restore(tpl, deploy=True)}
        self.assertEqual({k: v for k, v in on.items() if off.get(k) != v},
                         {"ShowLaunchBattleButton": 2, "ShowProdMenu": 2, "ShowTopBar": 2})
        points = [nd for nd in walk(dp.setup) if nd.cls == "TGDDescriptorSetRessourceForTeam"]
        self.assertEqual([dict(nd.props)["Quantite"].v for nd in points], [3000])
        main = g_seq([*setdeck_block(camps, profile.CAMP_ROWS), *dp.setup, Node("TGDDescriptorLoadingDone"),
                           Node("TGDDescriptorForceDisplayUIElement", profile.hud_restore(tpl, deploy=True)),
                           dp.launched, g_simul([dp.refresh])], export="$/GDScript/OD/Main")
        root = Node("TGDDescriptorLaunchEffetStandard", [
            ("CampList", list(camps.values())), ("EffetMap", g_seq([g_wait(1.0), main])),
            ("GameRules", dp.game_rules)], export="$/GDScript/RootDescriptor")
        roots = [silent_cutscenes(["od_h2"]), root]  # #0 is the one unexported root, as in stock
        raw = encode(build_graph(roots, [root, *camps.values(), zone, main, dp.refresh, group]), "GD")
        check_canonical(raw, frozenset(), "GD", import_rule="preorder")
        stock, _ = survey_shapes(tuple(extracted(g) for g in profile.SHAPE_SOURCES["GDScript"]), 16)
        self.assertGreater(check_shapes(raw, stock, "GD"), 0)


@SCRIPT_DATA
class ProdMenuSwitch(unittest.TestCase):
    """The buy menu's Groups/factory-tabs switch (ShowProdMenuSwitchMenuTypeButtons) is a
    per-content setting, Content.prod_menu_switch, ForceHide by default (S#296's, as every stock HUD node that shows the
    buy menu); op alone ships Default, written by omission as stock writes it; never ForceShow."""

    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))

    def test_contents(self):
        """op ships Default (the switch left out of its HUD restore), as its Content field says (the probes ship
        ForceHide: test_probes.py); check_prod_menu_switch passes it."""
        want = {"op": 0}
        self.assertEqual(sorted(CONTENTS), sorted(want))
        for name, make in CONTENTS.items():
            with self.subTest(content=name):
                content = make()
                roots, _ = content.script(self.tpl)
                restores = [nd for nd in walk(roots) if nd.cls == "TGDDescriptorForceDisplayUIElement"
                            and not getattr(dict(nd.props).get("ForceHideAll"), "v", 0)]
                self.assertEqual(len(restores), 1)
                (restore,) = restores
                shipped = dict(restore.props).get(PROD_MENU_SWITCH)
                self.assertEqual((content.prod_menu_switch, None if shipped is None else (shipped.tag, shipped.v)),
                                 (want[name], None if want[name] == BRICK_DEFAULT else (0x02, 1)))
                self.assertEqual(gates.prod_menu_switches(roots), [want[name]])
                self.assertEqual(gates.check_prod_menu_switch(content, roots), 1)

    def test_hud_restore(self):
        """hud_restore keeps S#296's ForceHide by default, leaves the switch out for Default (every other property
        unchanged, in order), and refuses ForceShow; a content whose field and script disagree fails the check."""
        for deploy in (False, True):
            with self.subTest(deploy=deploy):
                hide = profile.hud_restore(self.tpl, deploy)
                self.assertEqual(hide, profile.hud_restore(self.tpl, deploy, prod_menu_switch=BRICK_FORCE_HIDE))
                self.assertEqual(dict(hide)[PROD_MENU_SWITCH].v, BRICK_FORCE_HIDE)
                default = profile.hud_restore(self.tpl, deploy, prod_menu_switch=BRICK_DEFAULT)
                self.assertEqual(default, [(k, v) for k, v in hide if k != PROD_MENU_SWITCH])
        with self.assertRaisesRegex(CheckError, "no stock HUD node force-shows it"):
            profile.hud_restore(self.tpl, True, prod_menu_switch=BRICK_FORCE_SHOW)
        op = CONTENTS["op"]()
        roots, _ = probe2.content().script(self.tpl)               # a ForceHide script under op's Default
        with self.assertRaisesRegex(CheckError, r"op: the HUD restores set ShowProdMenuSwitchMenuTypeButtons to "
                                                     r"\[1\], but the content asks for 0"):
            gates.check_prod_menu_switch(op, roots)
        with self.assertRaisesRegex(CheckError, "asks for 1"):
            gates.check_prod_menu_switch(dataclasses.replace(op, prod_menu_switch=BRICK_FORCE_HIDE),
                                        op.script(self.tpl)[0])



if __name__ == "__main__":
    unittest.main()
