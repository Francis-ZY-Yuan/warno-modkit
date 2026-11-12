"""Tests for the probes example as a whole: the empty probe's build through the probes' profile, the default identity
(every probe's identity against the other examples' contents is test_example_contents'), and the shared gates passing
on every probe's script.

`Build` builds the empty probe once into a temporary folder (every gate runs) and checks the tree and the packs;
it removes the folder afterwards. `Identity` builds it again under probe 2's identity. Classes that read the stock
extraction or the game install skip without them.
"""
from __future__ import annotations

import contextlib
import dataclasses
import functools
import inspect
import os
import shutil
import unittest
import uuid

from probe_support import OUT_ROOT, details_files, ld_guid, quiet_build, scenario_guid, template_gdscript
from modkit.core import edat, paths, trad
from modkit.core.gates import CheckError
from modkit.ops import gates
from modkit.ops.files import read_file
from modkit.ops.graph import decode, walk
from modkit.ops.items import mem_item
from modkit.ops.leveldesign import read_ld_items
from modkit.ops.maps import GEISA
from modkit.ops.profile import SURVIVORS, Content
from modkit.ops.rekey import def_path
from modkit.ops.script import BRICK_DEFAULT, PROD_MENU_SWITCH
from modkit.ops.strings import LANGS, StringError
from probes import CONTENTS, empty, profile, spike, spike2

OUT = os.path.join(OUT_ROOT, "empty")
OUT_ID = os.path.join(OUT_ROOT, "identity")
TEST_ID = ("challenge_OpenDoorTest", "OpenDoorTest")  # probe 2's identity
SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")


def remove(out: str) -> None:
    shutil.rmtree(out, ignore_errors=True)
    with contextlib.suppress(OSError):
        os.rmdir(os.path.dirname(out))  # the test builds' folder, if nothing else is in it


def pack_files(root: str, scenario: str) -> dict[str, dict[str, bytes]]:
    """{pack: {inner path: bytes}} of the three packs under the mod folder `root`."""
    out = {}
    for pack in ("Definition", "Details", "Assets"):
        path = os.path.join(root, "Scenarios", f"{scenario}_{pack}.dat")
        out[pack] = {e.path: edat.read_entry(path, e) for e in edat.read_index(path)}
    return out


@functools.cache
def roots_of(name: str) -> tuple:
    """The script roots of the probe `name`, made once."""
    tpl, _, _ = decode(read_file(template_gdscript()))
    return tuple(CONTENTS[name]().script(tpl)[0])


@SCRIPT_DATA
@GAME
class Build(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.items = quiet_build(empty.content(), OUT)
        cls.packs = pack_files(os.path.join(OUT, profile.MOD_NAME), profile.SCENARIO)

    @classmethod
    def tearDownClass(cls):
        remove(OUT)

    def test_empty_builds(self):
        root = os.path.join(OUT, profile.MOD_NAME)
        for rel in ("Config.ini", "Gen/Version.ndf", *(f"Scenarios/{profile.SCENARIO}_{p}.dat"
                                                      for p in ("Definition", "Details", "Assets"))):
            with self.subTest(file=rel):
                self.assertTrue(os.path.isfile(os.path.join(root, *rel.split("/"))))
        self.assertTrue(os.path.isfile(os.path.join(OUT, "MANIFEST.tsv")))
        self.assertTrue(os.path.isfile(os.path.join(OUT, "od_overlay.png")))
        found = [os.path.join(d, f) for d, dirs, files in os.walk(OUT) for f in files + dirs if f == ".modinstall"]
        self.assertEqual(found, [])

    def test_package_has_no_gameplay_files(self):
        self.assertEqual(gates.check_package(self.items, profile.SCENARIO), len(self.items))
        bad = mem_item("Assets", "GameData/Gameplay/Gfx/Decks.ndfbin", b"", "generated", "test")
        with self.assertRaisesRegex(CheckError, "GameData/Gameplay/Gfx/Decks.ndfbin"):
            gates.check_package(self.items + [bad], profile.SCENARIO)
        unit = mem_item("Loose", f"Gen/{profile.SCENARIO}/GFX/Unit.txn", b"", "copy", "test")
        with self.assertRaisesRegex(CheckError, f"Loose:Gen/{profile.SCENARIO}/GFX/Unit.txn: a Gameplay file"):
            gates.check_package(self.items + [unit], profile.SCENARIO)

    def test_dictionaries_per_language(self):
        assets = self.packs["Assets"]
        dics = sorted(p for p in assets if p.endswith(".dic"))
        self.assertEqual(dics, sorted(f"Localisation/{profile.SCENARIO}/{name}-{lang}.dic"
                                      for name in profile.DICTIONARIES for lang in LANGS))

        def text(lang: str, token: str) -> str:
            return dict(trad.read_dic(assets[f"Localisation/{profile.SCENARIO}/SCENARIO_DEFINITION-{lang}.dic"]))[
                trad.token_key(token)]

        self.assertNotEqual(text("SC", "od_name"), text("US", "od_name"))
        for name in profile.DICTIONARIES:
            with self.subTest(dictionary=name):
                self.assertEqual(assets[f"Localisation/{profile.SCENARIO}/{name}-FR.dic"],
                                 assets[f"Localisation/{profile.SCENARIO}/{name}-US.dic"])

    def test_map_and_deck_swaps(self):
        definition = self.packs["Definition"]

        def strings(kind: str) -> list[str]:
            nb, _, _ = decode(definition[f"NDF/Scenarios/{kind}/{profile.SCENARIO}.ndfbin"])
            return [s.decode("latin-1") for s in nb.strings]

        info = strings("ScenarioInfo")
        self.assertIn(GEISA.name, info)
        self.assertNotIn("_3x3_Railway", info)
        config = strings("MapConfiguration")
        self.assertIn("OP_BASE_BB_Player", config)
        self.assertNotIn("OP_NORTH_SURV_PLAYER", config)
        nb, _, _ = decode(definition[f"NDF/Scenarios/MapConfiguration/{profile.SCENARIO}.ndfbin"])
        chain = [v for ob in nb.objects for pi, v in ob.props if nb.pname(pi) == "OrderToChainMission"]
        self.assertEqual([v.v for v in chain], [1001])


class Defaults(unittest.TestCase):
    def test_defaults_are_probe_ones(self):
        c = empty.content()
        self.assertEqual((c.scenario, c.mod_name, scenario_guid(c.scenario), c.blocking_objectives),
                         ("challenge_OpenDoor", "OpenDoorOps", scenario_guid(profile.SCENARIO), ()))
        self.assertEqual(scenario_guid(profile.SCENARIO),
                         uuid.uuid5(uuid.NAMESPACE_URL, "warno-opendoor/challenge_OpenDoor").bytes)
        # def_path names its scenario on every call: no default to freeze the old id
        self.assertIs(inspect.signature(def_path).parameters["scenario"].default, inspect.Parameter.empty)


@SCRIPT_DATA
@GAME
class Identity(unittest.TestCase):
    """A content's own scenario and mod name reach every path, name and GUID the build writes."""

    @classmethod
    def setUpClass(cls):
        cls.items = quiet_build(empty.content(*TEST_ID), OUT_ID)

    @classmethod
    def tearDownClass(cls):
        remove(OUT_ID)

    def test_override_reaches_paths_names_and_guids(self):
        scenario, mod = TEST_ID
        root = os.path.join(OUT_ID, mod)
        with open(os.path.join(root, "Config.ini"), encoding="ascii") as fh:
            self.assertIn(mod, fh.read())
        self.assertFalse(os.path.exists(os.path.join(OUT_ID, profile.MOD_NAME)))
        self.assertEqual(sorted(os.listdir(os.path.join(root, "Scenarios"))),
                         [f"{scenario}_{p}.dat" for p in ("Assets", "Definition", "Details")])
        packs = pack_files(root, scenario)
        self.assertEqual(sorted(packs["Definition"]), sorted(f"NDF/Scenarios/{k}/{scenario}.{ext}"
                                                             for k in SURVIVORS.kinds for ext in ("ndfbin", "tag")))
        self.assertTrue(all(p.startswith(f"Localisation/{scenario}/") or f"/{scenario}/" in p for p in packs["Assets"]),
                        sorted(packs["Assets"]))
        new_guid = scenario_guid(scenario)
        self.assertNotEqual(new_guid, scenario_guid(profile.SCENARIO))
        from modkit.ops.graph import all_values
        for kind in ("MapConfiguration", "ScenarioInfo"):
            nb, _, _ = decode(packs["Definition"][f"NDF/Scenarios/{kind}/{scenario}.ndfbin"])
            guids = {x.v for _, _, x in all_values(nb) if x.tag == 0x1A}
            with self.subTest(kind=kind):
                self.assertIn(new_guid, guids)
                self.assertFalse(guids & {scenario_guid(profile.SCENARIO), SURVIVORS.guid})
        stale = []  # every Definition string naming a probe id names the new one
        for inner, raw in packs["Definition"].items():
            nb, _, _ = decode(raw)
            stale += [f"{inner}: {t}" for t in (s.decode("latin-1") for s in nb.strings + nb.trans)
                      if "challenge_OpenDoor" in t and scenario not in t]
        self.assertEqual(stale, [])
        ld = read_ld_items(packs["Details"]["out/LevelDesign.ndfbin"])
        content = empty.content()
        self.assertEqual(sorted(it["GUID"] for it in ld), sorted(ld_guid(it, scenario) for it in content.items))
        self.assertFalse({it["GUID"] for it in ld} & {ld_guid(it, profile.SCENARIO) for it in content.items})
        gates.check_package(self.items, scenario)
        with self.assertRaisesRegex(CheckError, "not under challenge_OpenDoor;"):
            gates.check_package(self.items, profile.SCENARIO)

    def test_tags_must_match_the_scenario(self):
        """A script whose GdItems tags were made for another scenario than its content's fails the binding gate
        before anything is written."""
        stale = dataclasses.replace(empty.content(), scenario=TEST_ID[0], mod_name=TEST_ID[1])
        out = os.path.join(OUT_ROOT, "stale")
        with self.assertRaisesRegex(CheckError, "GUID words match no LevelDesign item"):
            quiet_build(stale, out)
        self.assertFalse(os.path.exists(out))

    def test_build_rejects_other_dictionaries(self):
        """A build ships exactly the profile's three dictionaries: another name, or a missing one, fails gate 1
        before writing."""
        base = empty.content()
        out = os.path.join(OUT_ROOT, "bad")
        extra = {**base.strings, "Scripting/Typo": {"od_x": ("x", "x")}}
        missing = {k: v for k, v in base.strings.items() if k != "Scripting/Dialog"}
        for table, name in ((extra, "Scripting/Typo"), (missing, "Scripting/Dialog")):
            with self.subTest(dictionary=name), self.assertRaisesRegex(StringError, name):
                quiet_build(profile.content("bad", base.items, base.script, table, base.menu_tokens), out)
        self.assertFalse(os.path.exists(out))


@SCRIPT_DATA
class Gates(unittest.TestCase):
    """The shared script gates pass on every probe (their synthetic and stock cases: the gate tests)."""

    def test_tiers(self):
        """The probes name no tier and pass (every arrival ends in their deployment zone); the empty probe has no
        deployment phase."""
        for name in CONTENTS:
            content = CONTENTS[name]()
            with self.subTest(content=name):
                details = details_files(content.items, content.scenario)
                roots = list(roots_of(name))
                self.assertEqual(content.tiered_arrivals, ())
                self.assertEqual(gates.check_tiers(content, roots, details, profile.CAMPS["NATO"],
                                                   profile.CAMPS["PACT"]), 0)
                if gates.has_deployment_phase(content.items):
                    self.assertEqual(gates.tier_violations((), roots, details, profile.CAMPS["NATO"],
                                                           profile.CAMPS["PACT"])[1], [])

    def test_objectives_wait(self):
        """Probe 1's four objectives each end their beat (a Simultaneous, or last in reveal()'s Sequential); the
        empty probe's objective is last in Main."""
        for name, n in (("spike", 4), ("empty", 1)):
            with self.subTest(content=name):
                roots = roots_of(name)
                self.assertEqual(gates.never_finishing_violations(roots, frozenset())[1], [])
                self.assertEqual(sum(nd.cls in gates.OBJECTIVES for nd in walk(roots)), n)

    def test_scripts_without_a_funnel_are_not_checked(self):
        """The empty probe's two endings are its one objective's two actions; probe 1 has none."""
        funnel = (profile.END_FUNNEL, profile.END_RACE)
        self.assertEqual(gates.check_end_funnel(roots_of("empty"), funnel), (2, False))
        self.assertEqual(gates.check_end_funnel(roots_of("spike"), funnel), (0, False))

    def test_empty_group_guard(self):
        """The empty probe guards its defeat test (Sequential[..., WaitCondition(Groupe_Joueur >= 1), StartTimer,
        Simultaneous[objective]]); probe 1 has no failure test."""
        self.assertEqual(gates.check_empty_group_guard(roots_of("empty")), 1)
        self.assertEqual(gates.check_empty_group_guard(roots_of("spike")), 0)

    def test_dialog_text(self):
        """Probe 1's and the empty probe's dialogs take no variables."""
        self.assertEqual(gates.check_dialog_text(roots_of("spike"), spike.STRINGS), 1)
        self.assertEqual(gates.check_dialog_text(roots_of("empty"), empty.content().strings), 1)

    def test_rules(self):
        self.assertEqual(gates.check_rules(roots_of("spike")), 1)
        self.assertEqual(gates.check_rules(roots_of("empty")), 1)

    def test_zone_tags(self):
        """Probe 1: the deployment phase's SetCommandZoneOwner on OD_CZ_SW, three circle detectors, OD_DZ_W and
        OD_CZ_SW each around its own point."""
        counts, bad = gates.zone_tag_violations(roots_of("spike"), details_files(spike.ITEMS))
        self.assertEqual((counts, bad), ({"zone lookups": 1, "detectors": 3, "zone items": 2, "command zones": 1}, []))

    def test_smart_orders(self):
        """Probe 1's t80_company (the route, then the Seize), probe 2's capture and count race (Seize, then removal
        or nothing), and the empty probe (none)."""
        self.assertEqual(gates.check_smart_orders(roots_of("spike")), 1)
        self.assertEqual(gates.check_smart_orders(roots_of("spike2")), 3)
        self.assertEqual(gates.check_smart_orders(roots_of("empty")), 0)

    def test_prod_menu_switch(self):
        """Every probe ships S#296's ForceHide (int32 1) in its one HUD restore, as its Content field says."""
        for name in CONTENTS:
            with self.subTest(content=name):
                content = CONTENTS[name]()
                roots = list(roots_of(name))
                restores = [nd for nd in walk(roots) if nd.cls == "TGDDescriptorForceDisplayUIElement"
                            and not getattr(dict(nd.props).get("ForceHideAll"), "v", 0)]
                self.assertEqual(len(restores), 1)
                shipped = dict(restores[0].props).get(PROD_MENU_SWITCH)
                self.assertEqual((content.prod_menu_switch, (shipped.tag, shipped.v)), (1, (0x02, 1)))
                self.assertNotEqual(content.prod_menu_switch, BRICK_DEFAULT)
                self.assertEqual(gates.prod_menu_switches(roots), [1])
                self.assertEqual(gates.check_prod_menu_switch(content, roots), 1)
