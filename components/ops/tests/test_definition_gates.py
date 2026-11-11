"""Tests for the gates on a cloned scenario's files in modkit.ops.gates: canonical layout, references, loc tokens,
leftover template names, the unit database, the Operations menu order."""
import glob
import os
import tempfile
import types
import unittest
import zipfile
from unittest import mock

from modkit.core import ndfbin, ndfrules, paths, trad
from modkit.ops import INGAME_DIC, STOCK_PATHS
from modkit.core.gates import CheckError
from modkit.ops.graph import Imp, Node, Str, all_values, build_graph, decode, encode, loc, u32
from modkit.ops.gates import (
    INGAME_PROPS, MENU_PACK, UNIT_ARCHIVE, UNIT_DATABASE, check_canonical, check_menu_order, check_no_template_name,
    check_references, check_tokens, check_units, ingame_keys, ingame_misses, menu_order_gate, menu_orders, ref_targets,
    split_tokens, stock_menu_orders, template_name_gate, unit_database,
)
from modkit.ops.items import mem_item

S = "challenge_B"
LANGS = ("US", "SC")


def script(*imports: str) -> bytes:
    """A GDScript-like file whose root uses `imports` in this order (graph.build_graph numbers them by first use)."""
    root = Node("TRoot", [("Uses", [Imp(p) for p in imports])], export="$/GDScript/Root")
    return encode(build_graph([Node("TCutsceneDescriptorDatabase"), root], [root]), "GDScript")


class CanonicalTest(unittest.TestCase):
    """Both import rules: 'trie' (stock) admits first uses that interleave folders, 'preorder' does not."""

    def test_both_rules_pass_a_plain_file(self):
        raw = script("$/GFX/Unit/A", "$/GFX/Unit/B", "$/GFX/Fx/C")
        for rule in ("trie", "preorder"):
            with self.subTest(rule=rule):
                check_canonical(raw, frozenset(), "GD", import_rule=rule)

    def test_interleaved_folders(self):
        raw = script("$/GFX/Unit/A", "$/GFX/Fx/C", "$/GFX/Unit/B")
        check_canonical(raw, frozenset(), "GD", import_rule="trie")
        with self.assertRaisesRegex(CheckError, "IMPR tree is not in index order"):
            check_canonical(raw, frozenset(), "GD", import_rule="preorder")

    def test_split_folder(self):
        """A folder written twice keeps the preorder but is not the trie."""
        nb, _, _ = decode(script("$/GFX/Unit/A", "$/GFX/Unit/B", "$/GFX/Fx/C"))
        gfx = nb.imports.children[0]
        unit = gfx.children[0]
        b = unit.children.pop()                     # $/GFX/Unit/B moves to a second Unit node right after the first
        gfx.children.insert(1, ndfbin.Node(unit.tran, ndfbin.NONE_IDX, [b]))
        raw = encode(nb, "GD")
        check_canonical(raw, frozenset(), "GD", import_rule="preorder")
        with self.assertRaisesRegex(CheckError, "not the trie"):
            check_canonical(raw, frozenset(), "GD", import_rule="trie")

    def test_unknown_rule(self):
        with self.assertRaisesRegex(CheckError, "import_rule"):
            check_canonical(script(), frozenset(), "GD", import_rule="other")

    def test_layout_rules(self):
        nb, _, _ = decode(script("$/GFX/Unit/A"))
        nb.topo = nb.topo[1:]
        with self.assertRaisesRegex(CheckError, "TOPO"):
            check_canonical(encode(nb, "GD"), frozenset(), "GD", import_rule="trie")


class ReferencesTest(unittest.TestCase):
    def test_ref_targets(self):
        self.assertEqual(ref_targets(f"ScenariosData:/{S}/Dico.csv", S, LANGS),
                         [f"Assets:Localisation/{S}/Dico-US.dic", f"Assets:Localisation/{S}/Dico-SC.dic"])
        self.assertEqual(ref_targets(f"Scenarios/ScenarioInfo/{S}", S, LANGS),
                         [f"Definition:NDF/Scenarios/ScenarioInfo/{S}.ndfbin"])
        self.assertEqual(ref_targets(S, S, LANGS), [])
        self.assertIsNone(ref_targets(f"Elsewhere/{S}/x", S, LANGS))

    def info(self, *strings: str) -> bytes:
        return encode(build_graph([Node("TInfo", [(f"S{k}", Str(s)) for k, s in enumerate(strings)])], []), "info")

    def test_every_reference_resolves(self):
        items = [mem_item("Definition", f"NDF/Scenarios/ScenarioInfo/{S}.ndfbin",
                          self.info(f"Scenarios/ScenarioInfo/{S}", f"ScenariosData:/{S}/Menu.png"), "rekey", "t"),
                 mem_item("Assets", f"PC/Texture/{S}/Menu.tgv", b"", "copy", "t")]
        self.assertEqual(check_references(items, S, LANGS), 2)
        with self.assertRaisesRegex(CheckError, "which is not shipped"):
            check_references(items[:1], S, LANGS)

    def test_unknown_pattern(self):
        items = [mem_item("Definition", f"NDF/Scenarios/ScenarioInfo/{S}.ndfbin", self.info(f"Odd/{S}/x"), "rekey",
                          "t")]
        with self.assertRaisesRegex(CheckError, "no resolution rule"):
            check_references(items, S, LANGS)


def dialog(text: str, button: str) -> bytes:
    nd = Node("TGDDescriptorCutsceneDialog", [("LocalizedText", loc(text)), ("TokenBoutonChoix0", loc(button))])
    return encode(build_graph([nd], []), "GDScript")


class TokensTest(unittest.TestCase):
    """A dialog button's token resolves in the game's INGAME dictionary, every other token in the scenario's."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ingame = os.path.join(self.tmp.name, "INTERFACE_INGAME-{lang}.dic")
        for lang in LANGS:
            with open(self.ingame.format(lang=lang), "wb") as fh:
                fh.write(trad.build_dic({"BTN_OK": "OK"}))

    def tearDown(self):
        self.tmp.cleanup()

    def items(self, text: str, button: str, dialog_keys=("m_text",)) -> list:
        out = [mem_item("Definition", f"NDF/Scenarios/GDScript/{S}.ndfbin", dialog(text, button), "generate", "t")]
        for lang in LANGS:
            out.append(mem_item("Assets", f"Localisation/{S}/Scripting/Dialog-{lang}.dic",
                                trad.build_dic({k: k for k in dialog_keys}), "generate", "t"))
            out.append(mem_item("Assets", f"Localisation/{S}/Scripting/Localization-{lang}.dic",
                                trad.build_dic({"m_other": "x"}), "generate", "t"))
        return out

    def test_split(self):
        nb, _, _ = decode(dialog("m_text", "BTN_OK"))
        self.assertEqual(split_tokens(nb), ({ndfbin.token_hash("m_text")}, {ndfbin.token_hash("BTN_OK")}))
        self.assertIn(("TGDDescriptorCutsceneDialog", "TokenBoutonChoix0"), INGAME_PROPS)

    def test_passes(self):
        self.assertEqual(check_tokens(self.items("m_text", "BTN_OK"), S, LANGS, global_tokens=(),
                                      ingame_dic=self.ingame), (2, 1))

    def test_a_button_token_must_be_in_ingame(self):
        items = self.items("m_text", "m_btn", dialog_keys=("m_text", "m_btn"))
        with self.assertRaisesRegex(CheckError, r"missing from the game's US INGAME dictionary: \['m_btn'\]"):
            check_tokens(items, S, LANGS, global_tokens=(), ingame_dic=self.ingame)
        nb, _, _ = decode(dialog("m_text", "m_btn"))
        self.assertEqual(ingame_misses(nb, self.ingame.format(lang="SC")), ["m_btn"])

    def test_text_tokens_need_the_scenario_dictionaries_or_global_tokens(self):
        with self.assertRaisesRegex(CheckError, r"missing from US dictionaries: \['m_gone'\]"):
            check_tokens(self.items("m_gone", "BTN_OK"), S, LANGS, global_tokens=(), ingame_dic=self.ingame)
        self.assertEqual(check_tokens(self.items("m_gone", "BTN_OK"), S, LANGS, global_tokens=("m_gone",),
                                      ingame_dic=self.ingame), (2, 1))

    def test_missing_ingame_dictionary(self):
        """The message names the setup commands that fetch it."""
        with self.assertRaisesRegex(CheckError, r"missing .*INTERFACE_INGAME.*python -m modkit\.core\.setup check, "
                                                r"then python -m modkit\.core\.setup extract \(the warno-setup skill\)"):
            ingame_keys(os.path.join(self.tmp.name, "nowhere", "INTERFACE_INGAME-US.dic"))

    def test_ingame_dic_is_a_declared_stock_path(self):
        """INGAME_DIC lies in a folder STOCK_PATHS declares, so the scripted extraction writes it."""
        self.assertIn("{lang}", INGAME_DIC)
        self.assertTrue(any(INGAME_DIC.startswith(stock.dest + "/") for stock in STOCK_PATHS))


@paths.skip_unless_extracted(*INGAME_DIC.format(lang="US").split("/"))
class IngamePropsStockTest(unittest.TestCase):
    def test_ingame_props_match_stock(self):
        """INGAME_PROPS is exactly the stock script properties whose tokens all resolve in the game's INGAME
        dictionary, some of them in no scenario dictionary: the dialog button labels (974 stock uses)."""
        root = str(paths.extracted_root())
        older = os.sep + "older" + os.sep
        scripts = [p for p in glob.glob(os.path.join(root, "**", "GDScript", "*.ndfbin"), recursive=True)
                   if older not in p]
        self.assertTrue(scripts)
        scenario: set[int] = set()
        for p in glob.glob(os.path.join(root, "**", "*.dic"), recursive=True):
            if "INTERFACE_INGAME" not in p and older not in p:
                with open(p, "rb") as fh:
                    scenario |= {k for k, _ in trad.read_dic(fh.read())}
        ingame = ingame_keys(os.path.join(root, *INGAME_DIC.format(lang="US").split("/")))
        uses: dict[tuple[str, str], set[int]] = {}
        for nb in ndfrules.stock_files(scripts):
            for ob, pi, x in all_values(nb):
                if x.tag == 0x1D and int.from_bytes(x.v, "little"):
                    uses.setdefault((nb.cname(ob.cls), nb.pname(pi)), set()).add(int.from_bytes(x.v, "little"))
        found = {k for k, toks in uses.items() if toks <= ingame and toks - scenario}
        self.assertEqual(found, set(INGAME_PROPS))


class TemplateNameTest(unittest.TestCase):
    """No re-keyed or generated file still names the template, but the names a clone keeps on purpose."""

    @staticmethod
    def named(*names: str, stock: bytes | None = b"", fixture: str | None = None) -> object:
        raw = encode(build_graph([Node("TResourceVideo", [("VideoFile", Str(n))]) for n in names], []), "GDScript")
        return mem_item("Definition", f"NDF/Scenarios/GDScript/{S}.ndfbin", raw, "rekey", "t",
                        stock=stock or None, fixture=fixture)

    def test_a_clean_clone_passes(self):
        items = [self.named("challenge_B_Intro", stock=b"stock"), self.named("Intro", fixture="GDScript.txt")]
        self.assertEqual(check_no_template_name(items, "Survivors"), (2, 0))

    def test_a_leftover_name_fails_in_any_case(self):
        for text in ("ScenariosData:/challenge_Survivors/x.webm", "SURVIVORS"):
            with self.subTest(text=text), self.assertRaisesRegex(CheckError, rf"GDScript/{S}.ndfbin: leftover "
                                                                             rf"Survivors: .*{text}"):
                check_no_template_name([self.named(text, stock=b"stock")], "Survivors")

    def test_kept_names_are_counted_not_failed(self):
        item = self.named("Survivors_Intro", "Survivors_Title", stock=b"stock")
        self.assertEqual(check_no_template_name([item], "Survivors", ("Survivors_Intro", "Survivors_Title")), (1, 2))
        with self.assertRaisesRegex(CheckError, "leftover Survivors: .*Survivors_Title"):
            check_no_template_name([item], "Survivors", ("Survivors_Intro",))

    def test_copies_are_not_read(self):
        """A byte copy (no stock bytes, no fixture) is the template's file as it is: only re-keyed and generated
        files are a clone's to clean."""
        self.assertEqual(check_no_template_name([self.named("Survivors", stock=None)], "Survivors"), (0, 0))

    def test_as_an_extra_gate(self):
        """template_name_gate: the check as a profile's extra gate (ExtraGate's callable), with its log line."""
        gate = template_name_gate("Survivors")
        self.assertEqual(gate([self.named("challenge_B_Intro", stock=b"stock")], None),
                         "1 re-keyed or generated dumps without Survivors")
        with self.assertRaisesRegex(CheckError, "leftover Survivors"):
            gate([self.named("Survivors_Intro", stock=b"stock")], None)
        kept = template_name_gate("Survivors", ("Survivors_Intro",))
        self.assertEqual(kept([self.named("Survivors_Intro", stock=b"stock")], None),
                         "1 re-keyed or generated dumps without Survivors (1 allow-listed resource-name hits: "
                         "Survivors_Intro)")


class UnitsTest(unittest.TestCase):
    """Every unit a generated file names is in the unit database: the mod SDK's unit and building descriptors."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.archive = os.path.join(self.tmp.name, "base.zip")
        units, buildings = UNIT_DATABASE
        with zipfile.ZipFile(self.archive, "w") as z:
            z.writestr(units, "export Descriptor_Unit_A is TEntityDescriptor\n(\n)\n"
                              "export Descriptor_Unit_B is TEntityDescriptor\n(\n)\nexport Other is TThing\n")
            z.writestr(buildings, "export Descriptor_Unit_FOB_X is TEntityDescriptor\n(\n)\n")

    def generated(self, *units: str, fixture: str | None = "GD.txt") -> object:
        """A generated file naming `units`: the first as a script's import, the rest as LevelDesign-like strings."""
        props = [("TypeUnit", Imp(units[0]))] + [("ClassName", Str(u)) for u in units[1:]]
        raw = encode(build_graph([Node("TGDDescriptorCreateUnitOnPosition", props)], []), "GDScript")
        return mem_item("Definition", f"NDF/Scenarios/GDScript/{S}.ndfbin", raw, "generate", "t", fixture=fixture)

    def test_the_database_holds_units_and_buildings(self):
        self.assertEqual(unit_database(self.archive, minimum=3),
                         {"$/GFX/Unit/Descriptor_Unit_A", "$/GFX/Unit/Descriptor_Unit_B",
                          "$/GFX/Unit/Descriptor_Unit_FOB_X"})

    def test_a_database_too_small_was_not_read(self):
        with self.assertRaisesRegex(CheckError, r"base.zip: only 3 unit descriptors found, want at least 1001"):
            unit_database(self.archive)

    def test_every_named_unit_exists(self):
        known = unit_database(self.archive, minimum=3)
        item = self.generated("$/GFX/Unit/Descriptor_Unit_A", "$/GFX/Unit/Descriptor_Unit_FOB_X")
        self.assertEqual(check_units([item], known), 2)
        with self.assertRaisesRegex(CheckError, r"unit descriptors not in the unit database: "
                                                r"\['\$/GFX/Unit/Descriptor_Unit_Z'\]"):
            check_units([item, self.generated("$/GFX/Unit/Descriptor_Unit_B", "$/GFX/Unit/Descriptor_Unit_Z")], known)

    @paths.skip_unless_game_dir(*UNIT_ARCHIVE.split("/"))
    def test_the_installed_database(self):
        """The game's own base.zip, found through the game install: thousands of units, the buildings with them."""
        known = unit_database()
        self.assertGreaterEqual(len(known), 1001)
        self.assertLessEqual({"$/GFX/Unit/Descriptor_Unit_FOB_UK", "$/GFX/Unit/Descriptor_Unit_M1A1HA_Abrams_US",
                              "$/GFX/Unit/Descriptor_Unit_MotRifles_SOV"}, known)
        self.assertTrue(all(name.startswith("$/GFX/Unit/Descriptor_Unit_") for name in known))

    def test_only_generated_files_are_read(self):
        """A template file copied or re-keyed (no fixture) is stock's own; only what the build generates is held."""
        stock = self.generated("$/GFX/Unit/Descriptor_Unit_Z", fixture=None)
        self.assertEqual(check_units([stock], set()), 0)


def map_config(*orders: int | None, pack: str = MENU_PACK) -> bytes:
    """A MapConfiguration-like file: one TChallengeMapInfo per order in ChapterPack `pack`, holding OrderToChainMission
    `order` (None: none)."""
    infos = [Node("TChallengeMapInfo", [("ChapterPack", Imp(pack))]
                  + ([("OrderToChainMission", u32(order))] if order is not None else [])) for order in orders]
    return encode(build_graph(infos, []), "MapConfiguration")


class MenuOrderTest(unittest.TestCase):
    """The Operations menu order: the built MapConfiguration's OrderToChainMission is no stock Operation's, stock read
    from a synthetic extraction the way the game reads it (every MapConfiguration whose ChapterPack is the Operations
    menu's). The stock proofs are test_gates_stock's MenuOrders."""

    STOCK = {130: ("challenge_A",), 997: ("challenge_B",)}

    def extraction(self, files: dict[str, bytes]) -> str:
        """A temporary extraction holding `files` (relative path: bytes), set as MODKIT_EXTRACTED for the test."""
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for rel, raw in files.items():
            path = os.path.join(tmp.name, *rel.split("/"))
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(raw)
        env = mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": tmp.name})
        env.start()
        self.addCleanup(env.stop)
        return tmp.name

    @staticmethod
    def stock_file(folder: str, scenario: str) -> str:
        return f"{folder}/NDF/Scenarios/MapConfiguration/{scenario}.ndfbin"

    def test_menu_orders_read_only_the_operations_menu(self):
        self.assertEqual(menu_orders(decode(map_config(1002))[0]), [1002])
        self.assertEqual(menu_orders(decode(map_config(30, pack="$/MapPacks/Strategics"))[0]), [])
        self.assertEqual(menu_orders(decode(map_config(1002, None))[0]), [1002, None])

    def test_a_free_order_passes(self):
        self.assertEqual(check_menu_order(map_config(1002), "MC", self.STOCK), 1002)

    def test_a_stock_order_fails_in_the_games_words(self):
        with self.assertRaisesRegex(CheckError, r"^MC: OrderToChainMission 997 is the menu order of the stock "
                                                r"Operation challenge_B\. Two Operations with one menu order stop the "
                                                r'game at start with a map pack configuration error, "Duplicate '
                                                r'OrderToChainMission 997": give this Operation its derived menu order '
                                                r"\(modkit\.ops\.leveldesign\.derived_menu_order\(scenario, "
                                                r"namespace\)\), a hash of its scenario GUID"):
            check_menu_order(map_config(997), "MC", self.STOCK)

    def test_one_operation_with_a_menu_order(self):
        for raw, message in ((map_config(30, pack="$/MapPacks/Strategics"), r"MC: 0 objects list an Operation"),
                             (map_config(1002, 1003), r"MC: 2 objects list an Operation"),
                             (map_config(None), r"MC: the Operation has no OrderToChainMission: give it its derived "
                                                r"menu order \(modkit\.ops\.leveldesign\.derived_menu_order")):
            with self.subTest(message=message), self.assertRaisesRegex(CheckError, message):
                check_menu_order(raw, "MC", self.STOCK)

    def test_stock_is_every_operations_menu_entry_of_the_extraction(self):
        """Every MapConfiguration of the extraction counts, wherever it lies; a scenario's copies count once; a
        campaign (another ChapterPack) and the older/ builds do not."""
        self.extraction({
            self.stock_file("scenarios/challenge_A", "challenge_A"): map_config(130),
            self.stock_file("kreide_op/challenge_A_Definition", "challenge_A"): map_config(130),
            self.stock_file("scenarios/challenge_B", "challenge_B"): map_config(997),
            self.stock_file("scenarios/CampagneStrat_C", "CampagneStrat_C"):
                map_config(10, pack="$/MapPacks/Strategics"),
            self.stock_file("older/1/challenge_D", "challenge_D"): map_config(1002),
        })
        self.assertEqual(dict(stock_menu_orders(minimum=2)), self.STOCK)

    def test_two_stock_operations_on_one_order_are_both_named(self):
        self.extraction({self.stock_file("scenarios/challenge_A", "challenge_A"): map_config(130),
                         self.stock_file("scenarios/challenge_B", "challenge_B"): map_config(130)})
        self.assertEqual(dict(stock_menu_orders(minimum=2)), {130: ("challenge_A", "challenge_B")})

    def test_too_few_stock_operations_were_not_read(self):
        self.extraction({self.stock_file("scenarios/challenge_A", "challenge_A"): map_config(130)})
        with self.assertRaisesRegex(CheckError, r"menu-order gate: 1 stock Operations found under .*, expected 16\+: "
                                                r"re-run the extraction \(the warno-setup skill\)"):
            stock_menu_orders()

    def test_an_unreadable_stock_file_fails(self):
        self.extraction({self.stock_file("scenarios/challenge_A", "challenge_A"): map_config(130),
                         self.stock_file("scenarios/challenge_B", "challenge_B"): b"not an ndfbin"})
        with self.assertRaisesRegex(CheckError, r"stock MapConfigurations that do not read: .*challenge_B\.ndfbin"):
            stock_menu_orders(minimum=1)

    def test_without_an_extraction_it_fails_naming_setup(self):
        """The gate never passes unread: with no extraction it raises NotConfigured (warno-setup), which the build
        turns into one FAILED line."""
        with mock.patch.object(paths, "extracted_root",
                               side_effect=paths.NotConfigured("not configured: run the warno-setup skill")):
            with self.assertRaisesRegex(paths.NotConfigured, "warno-setup"):
                stock_menu_orders()

    def test_as_an_extra_gate(self):
        """menu_order_gate: the shipped MapConfiguration of the content's scenario, against the extraction's stock."""
        self.extraction({self.stock_file(f"scenarios/challenge_{c}", f"challenge_{c}"): map_config(order)
                         for c, order in zip("ABCDEFGHIJKLMNOP", (130, 997, *range(1, 15)))})
        content = types.SimpleNamespace(scenario=S)
        inner = f"NDF/Scenarios/MapConfiguration/{S}.ndfbin"

        def shipped(order: int) -> list:
            return [mem_item("Definition", inner, map_config(order), "rekey", "t", stock=b"stock")]

        self.assertEqual(menu_order_gate(shipped(1002), content),
                         "OrderToChainMission 1002, the menu order of none of the 16 stock Operations")
        with self.assertRaisesRegex(CheckError, rf"^{inner}: OrderToChainMission 997 is the menu order of the stock "
                                                rf"Operation challenge_B\."):
            menu_order_gate(shipped(997), content)
        with self.assertRaisesRegex(CheckError, rf"the mod ships 0 {inner}, expected 1"):
            menu_order_gate([], content)


if __name__ == "__main__":
    unittest.main()
