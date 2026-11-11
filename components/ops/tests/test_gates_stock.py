"""The gates of modkit.ops.gates against stock: every rule holds on the stock scenarios (or names the stock cases
it reviews), and the counts pin what the stock surveys found. Each test skips without an extraction.
"""
import functools
import glob
import math
import os
import re
import unittest
from collections import Counter

from modkit.core import ndfbin, ndfrules, paths, trad
from modkit.core.gates import CheckError
from modkit.ops.bricks import g_fx, g_seq
from modkit.ops.files import read_file
from modkit.ops.gates import (
    ARRIVALS, CENTROID_TOLERANCE, COMPETE, END_GAME, GRID_TOLERANCE, GROUP_UNION, HEADING_TOLERANCE,
    MIDPOINT_TOLERANCE, NEVER_FINISH, OBJECTIVES, RULES_OMITTED, SEQ, SIMUL, SMART_ORDER, STOCK_BLOCKING_OBJECTIVES,
    STOCK_SCRIPT_EFFECTS, arrival_violations, check_grid, check_grid_subset, check_menu_order, check_objective_pins,
    check_script_effects, check_zone_layout, dialog_text_violations, effect_launches, effect_violations,
    empty_group_violations, gamefx_declarations, gamefx_file, group_name, menu_orders, never_finishing_violations,
    objective_name, objective_pin_violations, smart_order_violations, stalling_containers, stock_menu_files,
    stock_menu_orders, zone_polygons, zone_tag_violations,
)
from modkit.ops.graph import Node, build_graph, decode, encode, nodes_of
from modkit.ops.leveldesign import LD_FILE, ZONE_FILES, read_ld_items
from modkit.ops.script import BRICK_DEFAULT, BRICK_FORCE_HIDE, BRICK_FORCE_SHOW
from modkit.ops.zones import area_bbox, heading, point_in_polygon, polygon_centroid, read_ia_grid, read_zone_areas


def root() -> str:
    return str(paths.extracted_root())


def stock_gdscripts() -> str:
    return os.path.join(root(), "**", "GDScript", "*.ndfbin")


def stock_challenges() -> str:
    return os.path.join(root(), "scenarios", "challenge_*")


@functools.cache
def stock_scripts() -> tuple[tuple[str, tuple[Node, ...]], ...]:
    """(file stem, nodes) of each stock GDScript, parsed once; Survivors' two copies count once."""
    files = [p for p in glob.glob(stock_gdscripts(), recursive=True) if os.sep + "older" + os.sep not in p]
    out = {}
    for nb in ndfrules.stock_files(files):
        out.setdefault(os.path.basename(nb.path).removesuffix(".ndfbin"), tuple(nodes_of(nb)))
    return tuple(sorted(out.items()))


def stock_details(out: str) -> dict[str, bytes]:
    """The LevelDesign and zone files of a stock `out` folder, keyed as the build's Details are."""
    names = (LD_FILE, *ZONE_FILES.values())
    return {inner: read_file(os.path.join(os.path.dirname(out), *inner.split("/"))) for inner in names
            if os.path.isfile(os.path.join(os.path.dirname(out), *inner.split("/")))}


class Arrivals(unittest.TestCase):
    """Gate 3, the arrivals rule, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_arrivals_pass(self):
        """The gate's rule is stock's: in the 16 challenges and the 6 multiplayer layouts (Geisa 10vs10 and Kreide's
        five), all 83 player entries (57 RL, 26 AC) end in a player DZ or a CZ (a stock survey). The CZ
        half is needed: without command zones, 11 fail (BlackHorsesLastStand, Marauders AutoName_2,
        TheWingedHussars, six Kreide RLs)."""
        outs = [*sorted(glob.glob(os.path.join(root(), "scenarios", "challenge_*", "out"))),
                *sorted(glob.glob(os.path.join(root(), "geisa_op", "*_Details", "out"))),
                *sorted(glob.glob(os.path.join(root(), "kreide_op", "_3x3_Kreide_*_Details", "out")))]
        self.assertEqual(len(outs), 22)

        def raw(out: str, name: str) -> bytes | None:
            path = os.path.join(out, name)
            return read_file(path) if os.path.isfile(path) else None

        total, bad, strict = {"ReinforcementLocation": 0, "AerialCorridor": 0}, [], []
        for out in outs:
            ld, dz, cz = (raw(out, name) for name in ("LevelDesign.ndfbin", "DeploymentZone.ndfbin",
                                                       "CommandZone.ndfbin"))
            counts, why = arrival_violations(ld, dz, cz)
            total = {k: total[k] + counts[k] for k in total}
            bad += [f"{out}: {w}" for w in why]
            strict += [f"{os.path.basename(os.path.dirname(out))}/{w.split(':')[0]}"
                       for w in arrival_violations(ld, dz, None)[1]]
        self.assertEqual(bad, [])
        self.assertEqual(total, {"ReinforcementLocation": 57, "AerialCorridor": 26})
        self.assertEqual(len(strict), 11)
        for op in ("challenge_BlackHorsesLastStand", "challenge_Marauders/AutoName_2", "challenge_TheWingedHussars"):
            self.assertTrue(any(s.startswith(op) for s in strict), (op, strict))


class Tiers(unittest.TestCase):
    """Gate 3 tiers's geometry, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_command_zone_entries(self):
        """Stock's precedent for tiers.2's geometry: each of the 11 player entries that end in a command zone only
        (Arrivals.test_stock_arrivals_pass) ends in exactly one command zone and in no deployment zone of any side.
        The rest of the rule is the toolkit's: 10 of them have NumAlliance -1 (Marauders AutoName_2 omits it), and
        BlackHorsesLastStand and TheWingedHussars bring aircraft in through a command zone (no permanent tier)."""
        outs = [*sorted(glob.glob(os.path.join(root(), "scenarios", "challenge_*", "out"))),
                *sorted(glob.glob(os.path.join(root(), "geisa_op", "*_Details", "out"))),
                *sorted(glob.glob(os.path.join(root(), "kreide_op", "_3x3_Kreide_*_Details", "out")))]
        found = []
        for out in outs:
            details = stock_details(out)
            names = [w.split(":")[0] for w in arrival_violations(
                details[LD_FILE], details.get(ZONE_FILES["DeploymentZone"]), None, command_zones=False)[1]]
            dz, cz = (zone_polygons(details.get(ZONE_FILES[k])) for k in ("DeploymentZone", "CommandPoints"))
            for it in read_ld_items(details[LD_FILE]):
                if it["Name"] in names:
                    x, y = it["EndPosition"][:2]
                    layout = os.path.basename(os.path.dirname(out))
                    found.append((layout, it["Name"], it["addon"], it.get("NumAlliance"),
                                  sum(point_in_polygon(x, y, p) for _, _, p in cz),
                                  sum(point_in_polygon(x, y, p) for _, _, p in dz)))
        self.assertEqual(len(found), 11)
        self.assertEqual({(f[4], f[5]) for f in found}, {(1, 0)})                       # one CZ, no DZ: tiers.2
        self.assertEqual([f[:2] for f in found if f[3] != -1], [("challenge_Marauders", "AutoName_2")])
        self.assertEqual(sorted({f[0] for f in found if f[2] == "AerialCorridor"}),
                         ["challenge_BlackHorsesLastStand", "challenge_TheWingedHussars"])


class ObjectivePins(unittest.TestCase):
    """Gate 3, objective map pins, against stock: a toolkit convention, stricter than stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_fails_on_exactly_five(self):
        """Of the 45 stock GereObjectifs that show their map label, exactly 5 have no Position or
        UnitGroupPositionList and fail the gate: 3 in DelayedRetribution and 2 in HoldUntilRelieved. The other 47
        positionless ones (52 in all) leave ShowEtiquette out. Every other stock GDScript passes."""
        pinned, failing, positionless = 0, [], 0
        for stem, nodes in stock_scripts():
            n, bad = objective_pin_violations(nodes)
            pinned += n
            positionless += sum(nd.cls == "TGDDescriptorGereObjectif" and dict(nd.props).get("Position") is None
                                and not dict(nd.props).get("UnitGroupPositionList") for nd in nodes)
            failing += [(stem, objective_name(nd)) for nd in bad]
            if bad:
                with self.assertRaisesRegex(CheckError, "objectives show a map pin with no Position"):
                    check_objective_pins(nodes)
            else:
                self.assertEqual(check_objective_pins(nodes), n, stem)
        self.assertEqual((pinned, positionless), (45, 52))
        self.assertEqual(sorted(failing), [
            ("challenge_DelayedRetribution", "2oSwkfWrfy"), ("challenge_DelayedRetribution", "BWHMCt8Mnd"),
            ("challenge_DelayedRetribution", "C8BC3MDv5y"),
            ("challenge_HoldUntilRelieved", "BhSfeJs4tL"), ("challenge_HoldUntilRelieved", "uKoTA9Jue6")])


class MenuTexts(unittest.TestCase):
    """Gate 1's 30-unit title limit, against stock: a toolkit convention that stock's titles keep and its briefings
    do not."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_title_and_briefing_lengths(self):
        """The menu texts (MapConfiguration's DescriptionTextElements) of the 8 stock challenges that ship their own
        SCENARIO_DEFINITION dictionary, in UTF-16 units, (English, Chinese) min..max per element. The titles stay
        within 30; the briefing (TextePresentationScenario) runs over 1,000 English units."""
        def units(text: str) -> int:
            return len(text.encode("utf-16-le", "surrogatepass")) // 2

        challenges = []   # (folder, scenario, (US, SC)) of each challenge with its own SCENARIO_DEFINITION dictionary
        for folder in sorted(glob.glob(stock_challenges())):
            scenario = os.path.basename(folder)
            dics = tuple(os.path.join(folder, "Localisation", scenario, f"SCENARIO_DEFINITION-{lang}.dic")
                         for lang in ("US", "SC"))
            if any(os.path.isfile(d) for d in dics):
                challenges.append((folder, scenario, dics))
        missing = [scenario for _, scenario, dics in challenges if not all(os.path.isfile(d) for d in dics)]
        if missing or not challenges:
            self.skipTest(f"the extraction lacks the stock challenges' SCENARIO_DEFINITION dictionaries (declared in "
                          f"modkit.ops.STOCK_PATHS after it was made: {missing or 'all'}): run the warno-setup skill "
                          f"(python -m modkit.core.setup extract)")
        spans: dict[str, list[tuple[int, int]]] = {}
        for folder, scenario, dics in challenges:
            en, zh = (dict(trad.read_dic(read_file(d))) for d in dics)
            nb, _, _ = decode(read_file(os.path.join(folder, "NDF", "Scenarios", "MapConfiguration",
                                                     f"{scenario}.ndfbin")))
            (info,) = [nd for nd in nodes_of(nb) if nd.cls == "TChallengeMapInfo"]
            for key, token in dict(info.props)["DescriptionTextElements"].v:
                h = int.from_bytes(token.v, "little")
                if h in en:   # 0 (unset) and global tokens (MapTitle) are not the scenario's
                    spans.setdefault(nb.strings[key.v].decode(), []).append((units(en[h]), units(zh[h])))

        def span(element: str) -> tuple[tuple[int, int], tuple[int, int]]:
            got = spans[element]
            return (min(e for e, _ in got), max(e for e, _ in got)), (min(z for _, z in got), max(z for _, z in got))

        self.assertEqual(len(challenges), 8)
        self.assertEqual({element: span(element) for element in spans}, {
            "MissionName": ((9, 20), (3, 5)),
            "MissionNameInWarningOrder": ((9, 20), (3, 5)),
            "TitreObjectifs": ((9, 20), (3, 5)),
            "TexteForcesEnPresence": ((35, 71), (18, 47)),
            "TextePresentationScenario": ((1037, 1416), (359, 522)),
            "TexteObjectifs": ((548, 991), (148, 292)),
            "VictoryOperationOutcomeText": ((147, 295), (47, 79)),
            "DefeatOperationOutcomeText": ((164, 266), (56, 86)),
        })


class NeverFinishing(unittest.TestCase):
    """Gate 3, never-finishing actions, against stock."""


    @paths.skip_unless_extracted("scenarios")
    def test_stock_passes(self):
        """Every stock GDScript passes, and each exemption is one stock needs: a TriggerEndGame with a node after it,
        and a never-finishing action alone in a loop (the objectives' table: ObjectivesWait)."""
        paths = [p for p in glob.glob(stock_gdscripts(), recursive=True) if os.sep + "older" + os.sep not in p]
        files, found, bad, after_end, alone, stalling = 0, 0, [], 0, 0, 0
        for nb in ndfrules.stock_files(paths):
            nodes = nodes_of(nb)
            n, why = never_finishing_violations(nodes)
            files, found, bad = files + 1, found + n, bad + [f"{nb.path}: {w}" for w in why]
            stalling += stalling_containers(nodes)  # the containers rule runs on real cases: 124
            for nd in nodes:
                if nd.cls not in (SEQ, SIMUL, COMPETE):
                    continue
                props = dict(nd.props)
                kids, runs = props.get("SubActions") or [], props.get("NbExecutions")
                after_end += sum(1 for k in kids[:-1] if k.cls == END_GAME) if nd.cls == SEQ else 0
                alone += len(kids) == 1 and kids[0].cls in NEVER_FINISH and runs is not None and runs.v != 1
        self.assertEqual(bad, [])
        self.assertGreaterEqual(files, 29)
        self.assertGreater(found, 200)
        self.assertGreater(stalling, 100)
        self.assertEqual((after_end > 0, alone > 0), (True, True))


class ObjectivesWait(unittest.TestCase):
    """Gate 3, objectives that hold their Sequential, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_cases_are_the_table(self):
        """Without STOCK_BLOCKING_OBJECTIVES exactly two of the 168
        stock objectives hold up a Sequential, each named in the table; with it, all stock passes. Sledgehammer's waits
        until it resolves; TheKitzingenRuse's never finishes once it succeeds, because its success action (Partie3's
        sequence) holds a LockIncome, which never finishes either."""
        objectives, found = 0, []
        for stem, nodes in stock_scripts():
            objectives += sum(nd.cls in OBJECTIVES for nd in nodes)
            found += [f"{stem}: {re.search(r'GereObjectif\(\w+\)', line).group(0)}" for line in
                      never_finishing_violations(nodes, frozenset())[1] if "GereObjectif(" in line]
            self.assertEqual(never_finishing_violations(nodes)[1], [], stem)
        self.assertEqual(objectives, 162)  # 168 with Survivors' second copy
        self.assertEqual(found, ["challenge_Sledgehammer: GereObjectif(odvaMtR9hm)",
                                 "challenge_TheKitzingenRuse: GereObjectif(CVcFybf9To)"])
        self.assertEqual(len(STOCK_BLOCKING_OBJECTIVES), len(found))


class EmptyGroupGuard(unittest.TestCase):
    """Gate 3, the empty-group guard, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_tests_are_listed(self):
        """Stock never guards this way; its 16 tests count groups filled before the objective starts (a LevelDesign
        spawn's group, or one the script fills). Listed by name, reviewed: the gate is the toolkit's own (content with a
        deployment phase)."""
        found, line = [], re.compile(r"GereObjectif\((\w+)\): its ConditionEchec holds while (\w+) is empty")
        for stem, nodes in stock_scripts():
            found += [f"{stem}: {'/'.join(line.match(b).groups())}" for b in empty_group_violations(nodes)[1]]
        self.assertEqual(sorted(found), [
            "challenge_BlackHorsesLastStand: rTipsaGFpu/P0_C0_M577_US_1",
            "challenge_Marauders: 5uxOnWsweH/EventA2", "challenge_Marauders: gr0V2bOWmx/EventA1",
            "challenge_RedJuggernaut: 6vDLeFwkEj/IA_Supply_Units",
            "challenge_SigurdsStrike: CYockFfgYF/INF_Allies_ALL", "challenge_SigurdsStrike: CYockFfgYF/JOUEUR_Units",
            "challenge_SigurdsStrike: Ftg4oTVgwP/ALLIES_LEFT_FLANK",
            "challenge_SigurdsStrike: VI4gcJNQcE/ALLIES_RIGHT_FLANK",
            "challenge_SigurdsStrike: emD3Yf2vp8/ALLIES_RIGHT_FLANK",
            "challenge_SigurdsStrike: qm3hvJnW0P/ALLIES_LEFT_FLANK",
            "challenge_Sledgehammer: DYo4DVhmCU/All_Player_Units",
            "challenge_Sledgehammer: odvaMtR9hm/All_Player_Units",
            "challenge_Sledgehammer: u823KFrMyM/All_Player_Units",
            "challenge_Survivors: N4TvMgC9q1/Groupe_Joueur",
            "challenge_TheWingedHussars: wmBJluLSqC/All_Player_Units",
            "challenge_TheWingedHussars: wmBJluLSqC/AllyUnitsAlpha"])


class DialogText(unittest.TestCase):
    """Gate 3, dialog text placeholders, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_dialogs_have_none(self):
        """All 29 stock scenarios with dictionaries: 1,010 dialog text tokens, none holds a placeholder in any of
        its scenario's dictionaries (every language)."""
        total, bad = 0, []
        for scen in sorted(glob.glob(os.path.join(root(), "scenarios", "*"))):
            name = os.path.basename(scen)
            texts: dict[int, list[str]] = {}
            for p in glob.glob(os.path.join(scen, "Localisation", name, "**", "*.dic"), recursive=True):
                with open(p, "rb") as fh:
                    for key, text in trad.read_dic(fh.read()):
                        texts.setdefault(key, []).append(text)
            gd = os.path.join(scen, "NDF", "Scenarios", "GDScript", f"{name}.ndfbin")
            n, why = dialog_text_violations(nodes_of(next(ndfrules.stock_files([gd]))), texts)
            total, bad = total + n, bad + [f"{name}: {w}" for w in why]
        self.assertEqual((total, bad), (1010, []))


class Rules(unittest.TestCase):
    """Gate 3, game-rules fields, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_settings_are_listed(self):
        """Stock's own rules: HoldUntilRelieved lets a score end the battle, 7 challenges fix the random seed, none
        sets a time limit. Listed by name, reviewed: those are their designs."""
        found = sorted(f"{stem}: {k}" for stem, nodes in stock_scripts() for nd in nodes
                       if nd.cls == "TGDSpecificTacticalGameRules" for k, _ in nd.props if k in RULES_OMITTED)
        self.assertEqual(found, ["challenge_DelayedRetribution: ModeFixedRandomSeed",
                                 "challenge_GloryOrAttrition: ModeFixedRandomSeed",
                                 "challenge_HoldUntilRelieved: CheckEndGame",
                                 "challenge_RunningTheGauntlet: ModeFixedRandomSeed",
                                 "challenge_SigurdsStrike: ModeFixedRandomSeed",
                                 "challenge_Sledgehammer: ModeFixedRandomSeed",
                                 "challenge_TheHydra: ModeFixedRandomSeed",
                                 "challenge_TheWingedHussars: ModeFixedRandomSeed"])


class ZoneTags(unittest.TestCase):
    """Gate 3, zone tags and zones, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_passes(self):
        """The 16 challenges (script and Details): 169 zone lookups (130 TeamControleZone, 4 UnitDansZone, 35
        SetCommandZoneOwner positions) each in exactly one polygon of the right file, and 72 circle detectors. The 22
        layouts (challenges, Geisa 10vs10, Kreide's five): 166 zone items inside their own polygons, and no two of the
        111 command zones overlap (BlackHorsesLastStand's three share edges only). The strategic campaigns' one miss,
        listed: CampagneStrat_Airborne's tagzonepara lies in no command zone."""
        total, bad = {}, []
        for scen in sorted(glob.glob(stock_challenges())):
            name = os.path.basename(scen)
            gd = os.path.join(scen, "NDF", "Scenarios", "GDScript", f"{name}.ndfbin")
            counts, why = zone_tag_violations(nodes_of(next(ndfrules.stock_files([gd]))),
                                                   stock_details(os.path.join(scen, "out")))
            total, bad = {k: total.get(k, 0) + v for k, v in counts.items()}, bad + [f"{name}: {w}" for w in why]
        self.assertEqual((total, bad), ({"zone lookups": 169, "detectors": 72, "zone items": 94, "command zones": 51},
                                        []))
        outs = [*sorted(glob.glob(os.path.join(stock_challenges(), "out"))),
                *sorted(glob.glob(os.path.join(root(), "geisa_op", "*_Details", "out"))),
                *sorted(glob.glob(os.path.join(root(), "kreide_op", "_3x3_Kreide_*_Details", "out")))]
        layouts = [zone_tag_violations([], stock_details(out)) for out in outs]
        self.assertEqual(len(outs), 22)
        self.assertEqual(([sum(c["zone items"] for c, _ in layouts), sum(c["command zones"] for c, _ in layouts)],
                          [b for _, why in layouts for b in why]), ([166, 111], []))
        campaigns = []
        for scen in sorted(glob.glob(os.path.join(root(), "scenarios", "CampagneStrat_*"))):
            name = os.path.basename(scen)
            gd = os.path.join(scen, "NDF", "Scenarios", "GDScript", f"{name}.ndfbin")
            campaigns += [f"{name}: {w.split(' at ')[0]}" for w in zone_tag_violations(
                nodes_of(next(ndfrules.stock_files([gd]))), stock_details(os.path.join(scen, "out")))[1]]
        self.assertEqual(campaigns, ["CampagneStrat_Airborne: TeamControleZone.Position Tags/tagzonepara"])


class SmartOrders(unittest.TestCase):
    """Gate 3, smart orders, against stock."""

    @paths.skip_unless_extracted("scenarios")
    def test_stock_passes(self):
        """The 31 stock GDScripts: 44 smart orders on 44 groups (all in 9 challenges), none ordered again after its
        smart order in a Sequential, through 2,776 union edges. One stock group gets an order elsewhere: Marauders'
        artillery Event_Art_POL (Seize in Simultaneous #515; ShootOnPosition fire orders in another branch)."""
        smart, bad, unions, elsewhere = 0, [], 0, []
        for stem, nodes in stock_scripts():
            n, why = smart_order_violations(nodes)
            smart, bad = smart + n, bad + [f"{stem}: {w}" for w in why]
            unions += sum(len(dict(nd.props).get("ListGroupSource") or []) for nd in nodes
                          if nd.cls == GROUP_UNION)
            ordered = {id(dict(nd.props).get("UnitGroup")) for nd in nodes if nd.cls == SMART_ORDER}
            elsewhere += [(stem, group_name(dict(nd.props).get("Group")),
                           getattr(dict(nd.props).get("OrderType"), "v", None))
                          for nd in nodes if nd.cls in ("TGDDescriptorGiveOrderStandard", "TGDDescriptorMoveUnitGroup")
                          and id(dict(nd.props).get("Group")) in ordered]
        self.assertEqual((smart, bad, unions), (44, [], 2776))
        self.assertEqual(elsewhere, [("challenge_Marauders", "Event_Art_POL", 31)] * 3)


@functools.cache
def stock_script_files() -> tuple[tuple[str, bytes], ...]:
    """(file stem, bytes) of each stock GDScript, as the game reads it; Survivors' two copies count once."""
    out: dict[str, bytes] = {}
    for p in sorted(glob.glob(stock_gdscripts(), recursive=True)):
        if os.sep + "older" + os.sep not in p:
            out.setdefault(os.path.basename(p).removesuffix(".ndfbin"), read_file(p))
    return tuple(sorted(out.items()))


GAMEFX = paths.skip_unless_extracted("glad_201602", "NDF", "GFX", "GameFx.ndfbin")
NUKE_SOL, NUKE_PLAIN = "$/GFX/GameFx/fx_impact_sol_Tactical_Nuke", "$/GFX/GameFx/fx_impact_Tactical_Nuke"


@GAMEFX
class ScriptEffects(unittest.TestCase):
    """Gate 3, script effects, against stock: the game's lookup (the effect's name among the exports of its GameFx
    file), and every effect a stock script launches."""

    @paths.skip_unless_extracted("scenarios")
    def test_every_stock_launch_passes(self):
        """The 31 stock GDScripts (30 distinct): 75 launches in 7 of them, naming only STOCK_SCRIPT_EFFECTS, all
        from FX_script.ndf (the decompiled scenarios hold the same 75). Each script passes the gate."""
        names, per = Counter(), {}
        for stem, raw in stock_script_files():
            launched = effect_launches(ndfbin.decode(raw)[0])
            names.update(launched)
            per[stem] = len(launched)
            self.assertEqual(check_script_effects(raw), len(launched), stem)
        self.assertEqual(len(per), 30)
        self.assertEqual(dict(names), dict(zip(STOCK_SCRIPT_EFFECTS, (45, 27, 3))))
        self.assertEqual({k: v for k, v in per.items() if v},
                         {"challenge_BackhandBlow": 28, "challenge_RedJuggernaut": 16, "challenge_Gotterdammerung": 8,
                          "challenge_BlackHorsesLastStand": 7, "challenge_TheKitzingenRuse": 7,
                          "challenge_TheDieburgSalient": 5, "challenge_HoldUntilRelieved": 4})

    def test_both_nuke_names_fail(self):
        """Both names of the tactical-nuke impact effect are parameterised impact actions: the ground wrapper's four
        parameters (Template_Param_* in the NDF, no defaults) and the effect's own five (TActionAlias, with
        defaults) both compile to InputParameters. A script launching either fails, naming them."""
        declared = gamefx_declarations(gamefx_file())
        self.assertEqual(declared[NUKE_SOL], ("parPosition", "parDirection", "parRadiusPhysical", "parRadiusSuppress"))
        self.assertEqual(len(declared[NUKE_PLAIN]), 5)
        self.assertEqual(len(effect_violations([NUKE_SOL, NUKE_PLAIN], declared)), 2)
        pos = Node("TGDTagPosition", export="$/GDScript/RootDescriptor/t_fx")
        for name, n in ((NUKE_SOL, 4), (NUKE_PLAIN, 5)):
            raw = encode(build_graph([g_seq([g_fx(STOCK_SCRIPT_EFFECTS[1], pos), g_fx(name, pos)])], [pos]),
                         "GDScript")
            with self.subTest(effect=name), self.assertRaisesRegex(
                    CheckError, rf"may not launch: {re.escape(name)} declares {n} parameters \(par"):
                check_script_effects(raw)

    def test_the_script_only_effects_are_self_contained(self):
        """Every GameFx export named for scripts (14 named *ForScript*: smokes, barrages, bombs, mortars) takes no
        parameters (the mega bomb among them, though no stock script launches it); 1,437 of the 1,656 exports take
        some."""
        declared = gamefx_declarations(gamefx_file())
        script_only = {name: params for name, params in declared.items() if "ForScript" in name}
        self.assertEqual(len(script_only), 14)
        self.assertEqual({name: p for name, p in script_only.items() if p}, {})
        self.assertIn("$/GFX/GameFx/fx_HE_Mega_Bomb_ForScript", script_only)
        self.assertLessEqual(set(STOCK_SCRIPT_EFFECTS), set(script_only))
        self.assertEqual((sum(bool(p) for p in declared.values()), len(declared)), (1437, 1656))


class BrickStatus(unittest.TestCase):
    """The buy-menu switch values, as the mod SDK declares them."""

    @paths.skip_unless_extracted("moddata_base")
    def test_enum(self):
        """EGDBrickStatus as GDBrickStatus.ndf declares it."""
        path = os.path.join(root(), "moddata_base", "GameData", "Gameplay", "Constantes", "Enumerations",
                            "GDBrickStatus.ndf")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        self.assertEqual(dict(re.findall(r"(\w+) is (\d+)", text)),
                         {"Default": "0", "ForceHide": "1", "ForceShow": "2"})
        self.assertEqual((BRICK_DEFAULT, BRICK_FORCE_HIDE, BRICK_FORCE_SHOW), (0, 1, 2))


@functools.cache
def stock_layouts() -> tuple[tuple[str, str, tuple[float, float, float, float], float], ...]:
    """(name, out folder, playable zone bbox, playable zone Center z) of every stock challenge and Kreide layout whose
    out/PlayableZone holds a zone (Gotterdammerung, RedJuggernaut and Survivors ship an empty one)."""
    out = []
    for folder in [*sorted(glob.glob(os.path.join(root(), "scenarios", "challenge_*", "out"))),
                   *sorted(glob.glob(os.path.join(root(), "kreide_op", "_3x3_Kreide_*_Details", "out")))]:
        path = os.path.join(folder, "PlayableZone.ndfbin")
        if not os.path.isfile(path):
            continue
        nb, _, _ = decode(read_file(path))
        props = [{nb.pname(pi): v for pi, v in ob.props} for ob in nb.objects]
        zones = [d for ob, d in zip(nb.objects, props) if nb.cname(ob.cls) == "TMapArea"]
        if len(zones) != 1:
            continue
        ring = [p.v for p in zones[0]["BasePolygon2D"].v]
        box = (min(x for x, _ in ring), min(y for _, y in ring), max(x for x, _ in ring), max(y for _, y in ring))
        out.append((os.path.basename(os.path.dirname(folder)), folder, box, zones[0]["Center"].v[2]))
    return tuple(out)


def layout_files(folder: str) -> tuple[bytes, bytes | None, bytes | None]:
    """A stock layout's (LevelDesign, DeploymentZone, CommandZone) files (None: none shipped)."""
    def raw(name: str) -> bytes | None:
        path = os.path.join(folder, name)
        return read_file(path) if os.path.isfile(path) else None
    return raw("LevelDesign.ndfbin"), raw("DeploymentZone.ndfbin"), raw("CommandZone.ndfbin")


KREIDE_LAYOUTS = ["_3x3_Kreide_10vs10_CONQ_Details", "_3x3_Kreide_10vs10_DEST_Details",
                  "_3x3_Kreide_1vs1_CONQ_DUEL_Details", "_3x3_Kreide_3vs3_CONQ_Details", "_3x3_Kreide_3vs3_DEST_Details"]


@paths.skip_unless_extracted("kreide_op")
@paths.skip_unless_extracted("scenarios")
class ZoneLayoutStock(unittest.TestCase):
    """check_zone_layout against stock: its stock clauses hold on every layout, and the generator conventions break
    where the docstring says."""

    def rejects(self, **conventions) -> list[str]:
        """The stock layouts check_zone_layout rejects with `conventions` (ground_z=True: each layout's own playable
        zone's Center z)."""
        out = []
        for name, folder, box, z in stock_layouts():
            asked = {k: (z if k == "ground_z" else v) for k, v in conventions.items()}
            try:
                check_zone_layout(*layout_files(folder), box, **asked)
            except CheckError:
                out.append(name)
        return out

    def test_every_stock_layout_keeps_the_stock_clauses(self):
        layouts = stock_layouts()
        self.assertEqual(len(layouts), 18)  # 13 challenges and the 5 Kreide layouts
        self.assertEqual(self.rejects(), [])

    def test_the_tolerances_are_stocks(self):
        """CENTROID_TOLERANCE, HEADING_TOLERANCE and MIDPOINT_TOLERANCE bound stock's largest gaps, which are the
        numbers the docstring gives."""
        centre, turn, mid, unturned = [], [], [], 0
        for _, folder, _, _ in stock_layouts():
            ld, dz, cz = layout_files(folder)
            for raw in (dz, cz):
                for poly, center, *_ in read_zone_areas(raw) if raw else []:
                    centre.append(max(abs(c - k) for c, k in zip(center[:2], polygon_centroid(poly))))
            for it in read_ld_items(ld):
                if it["addon"] in ARRIVALS:
                    start, end = it["StartPosition"][:2], it["EndPosition"][:2]
                    mid.append(math.dist(it["pos"], ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2))
                               / math.dist(start, end))
                    if it["rot"] is None:
                        unturned += 1
                    else:
                        aim = heading(start, end)
                        turn.append(abs((it["rot"] - aim + math.pi) % (2 * math.pi) - math.pi))
        self.assertEqual((len(centre), len(turn), unturned, len(mid)), (132, 141, 4, 145))
        self.assertEqual((round(max(centre), 3), round(max(turn), 4), round(max(mid), 4)), (0.075, 0.0093, 0.0053))
        self.assertLess(max(centre), CENTROID_TOLERANCE)
        self.assertLess(max(turn), HEADING_TOLERANCE)
        self.assertLess(max(mid), MIDPOINT_TOLERANCE)
        self.assertEqual(sum(m > 1e-6 for m in mid), 3)

    def test_stock_breaks_the_generator_conventions(self):
        challenges = [name for name, *_ in stock_layouts() if name.startswith("challenge_")]
        self.assertEqual(self.rejects(exact=True), challenges + KREIDE_LAYOUTS)
        self.assertEqual(self.rejects(ground_z=True), [
            "challenge_BlackHorsesLastStand", "challenge_GloryOrAttrition", "challenge_Marauders",
            "challenge_RunningTheGauntlet", "challenge_Sledgehammer", "challenge_TheDieburgSalient",
            "challenge_TheHydra", "challenge_TheKitzingenRuse", "challenge_TheWingedHussars", *KREIDE_LAYOUTS])
        self.assertEqual(self.rejects(sides=(0, 1)), ["challenge_Sledgehammer"])
        self.assertEqual(self.rejects(dz_only=True), [
            "challenge_BlackHorsesLastStand", "challenge_Marauders", "challenge_SigurdsStrike",
            "challenge_TheWingedHussars", "_3x3_Kreide_10vs10_CONQ_Details", "_3x3_Kreide_10vs10_DEST_Details",
            "_3x3_Kreide_3vs3_DEST_Details"])
        margins = [min(check_zone_layout(*layout_files(folder), box).margins) for _, folder, box, _ in stock_layouts()]
        self.assertEqual(min(margins), (2199.0, "DeploymentZone/PlayerDeploymentZone"))  # HoldUntilRelieved


@paths.skip_unless_extracted("kreide_op")
@paths.skip_unless_extracted("scenarios")
class GridStock(unittest.TestCase):
    """check_grid against stock: every shipped grid keeps the rule; check_grid_subset's tile-aligned cut is a
    generator's convention that only some stock layouts happen to keep."""

    def grids(self):
        for name, folder, box, _ in stock_layouts():
            areas, entries = read_ia_grid(os.path.join(folder, "IAStratZone.ndfbin"),
                                          os.path.join(folder, "IAStrat_PathCache.ndfbin"))
            yield name, areas, entries, box

    def test_every_stock_grid_spans_its_playable_zone(self):
        tiles = {name: check_grid(areas, entries, box)[0] for name, areas, entries, box in self.grids()}
        self.assertEqual(len(tiles), 18)
        self.assertEqual(tiles["_3x3_Kreide_3vs3_CONQ_Details"], 256)

    def test_the_tolerance_is_stocks(self):
        """GRID_TOLERANCE bounds stock's largest gap, TheKitzingenRuse's 5,792 world."""
        rejected = []
        for name, areas, entries, box in self.grids():
            try:
                check_grid(areas, entries, box, tolerance=5791)
            except CheckError:
                rejected.append(name)
        self.assertEqual(rejected, ["challenge_TheKitzingenRuse"])
        self.assertGreater(GRID_TOLERANCE, 5792)

    def test_the_tile_sides_are_stocks(self):
        """Stock's AI tiles run from 30,960 world a side (DelayedRetribution) to 491,520 (RunningTheGauntlet), the
        range GRID_TOLERANCE's comment and the AI grid's knowledge page give."""
        sides = [(side, name) for name, areas, _, _ in self.grids() for b in map(area_bbox, areas)
                 for side in (b[2] - b[0], b[3] - b[1])]
        self.assertEqual((min(sides), max(sides)), ((30960.0, "challenge_DelayedRetribution"),
                                                    (491520.0, "challenge_RunningTheGauntlet")))

    def test_only_some_stock_grids_are_tile_aligned_cuts(self):
        aligned = []
        for name, areas, entries, box in self.grids():
            try:
                check_grid_subset(areas, entries, box)
                aligned.append(name)
            except CheckError:
                pass
        self.assertEqual(aligned, ["challenge_DelayedRetribution", "challenge_GloryOrAttrition", "challenge_TheHydra",
                                   *KREIDE_LAYOUTS])


@paths.skip_unless_extracted("scenarios")
class MenuOrders(unittest.TestCase):
    """The menu-order gate against stock: the game's lookup (every MapConfiguration whose ChapterPack is the Operations
    menu's), the 16 stock Operations' orders, and each stock Operation passing beside the others."""

    # Each stock Operation's OrderToChainMission at 201602, read off the extraction (not a list the gate uses).
    STOCK = {10: "BlackHorsesLastStand", 11: "Sledgehammer", 20: "RedJuggernaut", 30: "BackhandBlow",
             40: "TheKitzingenRuse", 50: "Gotterdammerung", 70: "TheDieburgSalient", 90: "HoldUntilRelieved",
             100: "RunningTheGauntlet", 110: "TheWingedHussars", 120: "Marauders", 130: "Survivors",
             996: "SigurdsStrike", 997: "DelayedRetribution", 998: "GloryOrAttrition", 999: "TheHydra"}

    @staticmethod
    def operations() -> list[tuple[str, bytes]]:
        """(path relative to the extraction, bytes) of every current stock MapConfiguration that lists an Operation."""
        out = []
        for path in stock_menu_files(root()):
            rel = os.path.relpath(path, root())
            if rel.split(os.sep)[0] == "older":
                continue
            raw = read_file(path)
            if menu_orders(ndfbin.decode(raw)[0]):
                out.append((rel, raw))
        return out

    def test_no_two_stock_operations_share_a_menu_order(self):
        """The 16 stock Operations hold 16 distinct menu orders, one each (Survivors' two copies count once)."""
        self.assertEqual(dict(stock_menu_orders()),
                         {order: (f"challenge_{name}",) for order, name in self.STOCK.items()})

    def test_every_stock_operation_passes_beside_the_others(self):
        """Each stock Operation's own MapConfiguration lists one Operation and passes the gate against the other 15:
        stock never trips it. The campaigns' MapConfigurations list none (another ChapterPack)."""
        stock, seen = stock_menu_orders(), set()
        order_of = {f"challenge_{name}": order for order, name in self.STOCK.items()}
        for rel, raw in self.operations():
            scenario = os.path.basename(rel).removesuffix(".ndfbin")
            others = {order: tuple(n for n in names if n != scenario) for order, names in stock.items()}
            with self.subTest(file=rel):
                self.assertEqual(check_menu_order(raw, rel, others), order_of[scenario])
            seen.add(scenario)
        self.assertEqual(len(seen), 16)
        campaigns = [p for p in stock_menu_files(root()) if os.path.basename(p).startswith("CampagneStrat_")]
        self.assertGreater(len(campaigns), 0)
        self.assertTrue(all(menu_orders(ndfbin.decode(read_file(p))[0]) == [] for p in campaigns))

    def test_the_template_order_fails(self):
        """A clone that keeps Survivors' order (no OrderToChainMission edit) fails, naming Survivors."""
        rel, raw = next((rel, raw) for rel, raw in self.operations() if rel.endswith("challenge_Survivors.ndfbin"))
        with self.assertRaisesRegex(CheckError, r"OrderToChainMission 130 is the menu order of the stock Operation "
                                                r'challenge_Survivors\. .*"Duplicate OrderToChainMission 130"'):
            check_menu_order(raw, rel, stock_menu_orders())



if __name__ == "__main__":
    unittest.main()
