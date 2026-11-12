"""Tests for modkit.ops.rekey (re-keying tables and rows) and the dump gates in modkit.ops.gates."""
import glob
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError

from modkit.core import dbg, paths
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.gates import check_dump_diff, check_fixture, dump_kind, typed_dump
from modkit.ops.graph import Imp, Map, Node, Str, build_graph, decode, encode, i32, loc
from modkit.ops.rekey import (
    DBG, TAG, TAG_CLASS, TXN, DumpRow, Rekey, ScalarEdit, def_entry, def_path, dump_rows, generated_dbg, rekey_dbg,
    rekey_definition, rekey_tag, replace_text, repath, swap_exact,
)


class Entry:
    """A planned entry as the gates read it: path, chunks() and, for a re-keyed file, its stock bytes."""

    def __init__(self, path: str, raw: bytes, stock: bytes | None = None):
        self.path, self.raw, self.stock = path, raw, stock

    def chunks(self):
        return (self.raw,)


def info(name: str, order: int = 130) -> bytes:
    return encode(build_graph([Node("TChallengeMapInfo", [("Name", Str(name)), ("Path", Str(f"Scenarios/{name}")),
                                                            ("OrderToChainMission", i32(order))])], []), "info")


class TableTest(unittest.TestCase):
    def test_replace_text(self):
        table = [b"a/challenge_A/b", b"challenge_A", b"other"]
        self.assertEqual(replace_text(table, "challenge_A", "challenge_B"), 2)
        self.assertEqual(table, [b"a/challenge_B/b", b"challenge_B", b"other"])

    def test_swap_exact(self):
        table = [b"_2x2_MapA", b"x_2x2_MapA", b"MapA"]
        self.assertEqual(swap_exact(table, {"_2x2_MapA": "_2x2_MapB", "MapA": "MapB"}), 2)
        self.assertEqual(table, [b"_2x2_MapB", b"x_2x2_MapA", b"MapB"])

    def test_rows_are_frozen(self):
        row = DumpRow("id", None, "a", "b")
        edit = ScalarEdit("MapConfiguration", "TChallengeMapInfo", "Duration", Value(0x02, 3), Value(0x02, 1))
        with self.assertRaises(FrozenInstanceError):
            row.repl = "c"
        with self.assertRaises(FrozenInstanceError):
            edit.new = Value(0x02, 2)


class DumpDiffTest(unittest.TestCase):
    PATH = "NDF/Scenarios/challenge_B/MapConfiguration.txn"

    def test_rows_explain_every_change(self):
        item = Entry(self.PATH, info("challenge_B"), info("challenge_A"))
        report, fired = check_dump_diff(item, [DumpRow("id", None, "challenge_A", "challenge_B"),
                                               DumpRow("unused", None, "nothing_here", "x")])
        self.assertEqual(fired, {"id"})
        self.assertEqual(len(report), 2)  # Name and Path

    def test_unexplained_change_fails(self):
        item = Entry(self.PATH, info("challenge_B", 1000), info("challenge_A"))
        with self.assertRaisesRegex(CheckError, "unexplained dump change"):
            check_dump_diff(item, [DumpRow("id", None, "challenge_A", "challenge_B")])

    def test_rows_apply_only_to_their_kinds(self):
        item = Entry(self.PATH, info("challenge_B"), info("challenge_A"))
        with self.assertRaises(CheckError):
            check_dump_diff(item, [DumpRow("id", ("ScenarioInfo",), "challenge_A", "challenge_B")])
        tag = Entry("NDF/Scenarios/challenge_B/MapConfiguration.txn.tag", info("challenge_B"), info("challenge_A"))
        _, fired = check_dump_diff(tag, [DumpRow("id", ("MapConfiguration.txn.tag",), "challenge_A", "challenge_B")])
        self.assertEqual(fired, {"id"})

    def test_a_source_map_is_compared_by_its_text(self):
        old = dbg.write([dbg.Line("", "ScenariosData:/challenge_A/MapPack.ndf", 1, 1)])
        new = dbg.write([dbg.Line("", "ScenariosData:/challenge_B/MapPack.ndf", 1, 1)])
        item = Entry("NDF/Scenarios/challenge_B/MapConfiguration.dbg", new, old)
        report, fired = check_dump_diff(item, [DumpRow("id", None, "challenge_A", "challenge_B")])
        self.assertEqual((len(report), fired), (1, {"id"}))
        moved = Entry(item.path, dbg.write([dbg.Line("", "ScenariosData:/challenge_B/MapPack.ndf", 2, 1)]), old)
        with self.assertRaisesRegex(CheckError, "unexplained dump change"):
            check_dump_diff(moved, [DumpRow("id", None, "challenge_A", "challenge_B")])

    def test_dump_kind(self):
        self.assertEqual([dump_kind(def_path("GDScript", ext, "challenge_B")) for ext in (TXN, TAG, DBG)],
                         ["GDScript", "GDScript.txn.tag", "GDScript.dbg"])
        with self.assertRaisesRegex(CheckError, "not a Definition entry"):
            dump_kind("NDF/Scenarios/GDScript/challenge_B.ndfbin")


SOURCE, NEW = "challenge_A", "challenge_B"
G_OLD, G_NEW = bytes(range(16)), bytes(range(16, 32))
SOURCES = ("Scenario.ndf", "Scripting/GdItems.ndf")
EDITS = (ScalarEdit("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission", Value(0x03, 130), Value(0x03, 7)),)


def table(**kw) -> Rekey:
    """A clone of challenge_A as challenge_B; keyword arguments replace fields."""
    fields = dict(source=SOURCE, scenario=NEW, guid_source=G_OLD, guid=G_NEW, renames={"ta_name": "tb_name"},
                  token_prefix="ta_", scalar_edits=EDITS, map_strings={}, map_trans={}, deck_swap={},
                  kinds=("GDScript", "MapConfiguration", "ScenarioInfo"))
    return Rekey(**{**fields, **kw})


def map_configuration(deck: str = "DECK_A", token: str = "ta_name") -> bytes:
    return encode(build_graph([Node("TChallengeMapInfo", [
        ("Name", loc(token)), ("Path", Str(f"Scenarios/{SOURCE}")), ("GUID", Value(0x1A, G_OLD)),
        ("OrderToChainMission", Value(0x03, 130)), ("LocalPlayerDeck", Str(deck)),
        ("Environment", Imp("$/GraphicSettings/EnvironmentSettings/MapA"))])], []), "MapConfiguration")


def scenario_info() -> bytes:
    return encode(build_graph([Node("TScenarioDefinition", [
        ("Name", Str(SOURCE)), ("GUID", Value(0x1A, G_OLD)), ("RootDatapackName", Str("_2x2_MapA"))])], []),
        "ScenarioInfo")


def tag(kind: str, sources=SOURCES, cls: str = TAG_CLASS) -> bytes:
    """A .txn.tag as stock's: a TNDFTagFile with a ConfigHash and its sources by game path (to their hashes)."""
    pairs = tuple((Str(f"ScenariosData:/{SOURCE}/{f}", 0x1C), Value(0x13, 7 + k)) for k, f in enumerate(sources))
    return encode(build_graph([Node(cls, [("ConfigHash", Value(0x13, -5)),
                                          ("SourceFileHashes", Map(pairs))])], []), f"{kind}.{TAG}")


class PathTest(unittest.TestCase):
    def test_def_path_names_its_scenario(self):
        self.assertEqual(def_path("GDScript", TAG, "challenge_X"), "NDF/Scenarios/challenge_X/GDScript.txn.tag")
        self.assertEqual(def_path("ScenarioInfo", TXN, "challenge_X"), "NDF/Scenarios/challenge_X/ScenarioInfo.txn")
        self.assertEqual(def_path("ScenarioInfo", DBG, "challenge_X"), "NDF/Scenarios/challenge_X/ScenarioInfo.dbg")
        with self.assertRaisesRegex(CheckError, "a .txn, .txn.tag or .dbg"):
            def_path("GDScript", "ndfbin", "challenge_X")

    def test_def_entry(self):
        self.assertEqual(def_entry("NDF/Scenarios/challenge_X/GDScript.txn.tag"), ("challenge_X", "GDScript", TAG))
        self.assertEqual(def_entry("NDF/Scenarios/challenge_X/GDScript.dbg"), ("challenge_X", "GDScript", DBG))
        self.assertIsNone(def_entry("NDF/Scenarios/GDScript/challenge_X.ndfbin"))
        self.assertIsNone(def_entry("out/LevelDesign.ndfbin"))

    def test_repath(self):
        self.assertEqual(repath(f"PC/Texture/{SOURCE}/a.tgv", SOURCE, NEW), f"PC/Texture/{NEW}/a.tgv")
        with self.assertRaisesRegex(CheckError, "no challenge_A component"):
            repath(f"PC/Texture/{SOURCE}x/a.tgv", SOURCE, NEW)


class RekeyDefinitionTest(unittest.TestCase):
    """Both tables the two cloners use: no map, deck or token swap beyond the id, GUID and menu tokens, and the
    full one with the map and deck swaps. Each re-keyed file differs from stock only by dump_rows."""

    def gate(self, kind: str, stock: bytes, rk: Rekey) -> set[str]:
        new = rekey_definition(stock, kind, rk)
        _, fired = check_dump_diff(Entry(def_path(kind, TXN, rk.scenario), new, stock), dump_rows(rk))
        return fired

    def test_identity_only(self):
        fired = self.gate("MapConfiguration", map_configuration(), table())
        self.assertEqual(fired, {"id challenge_A -> S", "GUID -> G", "loc ta_name -> tb_name",
                                 "OrderToChainMission 130 -> 7"})
        nb, _, _ = decode(rekey_definition(map_configuration(), "MapConfiguration", table()))
        self.assertIn(b"DECK_A", nb.strings)
        self.assertIn(b"MapA", nb.trans)

    def test_map_and_deck_swaps(self):
        rk = table(map_strings={"_2x2_MapA": "_2x2_MapB"}, map_trans={"MapA": "MapB"}, deck_swap={"DECK_A": "DECK_B"})
        self.assertEqual(self.gate("MapConfiguration", map_configuration(), rk) - self.gate(
            "MapConfiguration", map_configuration(), table()),
            {"map EnvironmentSettings MapA -> MapB", "deck DECK_A -> DECK_B"})
        self.assertIn("map _2x2_MapA -> _2x2_MapB", self.gate("ScenarioInfo", scenario_info(), rk))

    def test_each_deck_swap_must_hit(self):
        with self.assertRaisesRegex(CheckError, "0 LocalPlayerDeck strings swapped, expected 1"):
            rekey_definition(map_configuration(deck="OTHER"), "MapConfiguration", table(deck_swap={"DECK_A": "X"}))

    def test_template_tokens_must_be_renamed(self):
        with self.assertRaisesRegex(CheckError, "unmapped token ta_other"):
            rekey_definition(map_configuration(token="ta_other"), "MapConfiguration", table())

    def test_guid_sites(self):
        with self.assertRaisesRegex(CheckError, "1 GUID sites, expected 0"):
            rekey_definition(scenario_info(), "GDScript", table())

    def test_scalar_edit_needs_one_site(self):
        with self.assertRaisesRegex(CheckError, "0 sites hold"):
            rekey_definition(scenario_info(), "ScenarioInfo",
                             table(scalar_edits=(ScalarEdit("ScenarioInfo", "TScenarioDefinition", "Duration",
                                                            Value(0x02, 3), Value(0x02, 1)),)))


class RekeyTagTest(unittest.TestCase):
    def test_source_paths_move_and_hashes_stay(self):
        stock = tag("ScenarioInfo")
        new = rekey_tag(stock, "ScenarioInfo", table(), -5)
        nb, _, _ = decode(new)
        self.assertEqual(sorted(nb.strings), sorted(f"ScenariosData:/{NEW}/{f}".encode() for f in SOURCES))
        self.assertEqual(decode(stock)[0].objects[0].props, nb.objects[0].props)  # this ConfigHash and the hashes
        _, fired = check_dump_diff(Entry(def_path("ScenarioInfo", TAG, NEW), new, stock), dump_rows(table()))
        self.assertEqual(fired, {"id challenge_A -> S"})
        nb, _, _ = decode(rekey_tag(stock, "ScenarioInfo", table(), 1234))
        self.assertEqual(nb.objects[0].props[0][1], Value(0x13, 1234))   # the ConfigHash given

    def test_a_tag_names_a_source_of_its_scenario(self):
        with self.assertRaisesRegex(CheckError, "names no challenge_A source file"):
            rekey_tag(encode(build_graph([Node(TAG_CLASS, [("ConfigHash", Value(0x13, 1))])], []), "t"),
                      "ScenarioInfo", table(), 1)

    def test_a_tag_is_one_tag_file(self):
        with self.assertRaisesRegex(CheckError, "not one TNDFTagFile"):
            rekey_tag(tag("ScenarioInfo", cls="TGladNDFBinHandler_FileList"), "ScenarioInfo", table(), 1)


class SourceMapTest(unittest.TestCase):
    MAP = [dbg.Line("", f"ScenariosData:/{SOURCE}/MapPack.ndf", 1, 1), dbg.Line("Load", "CommonData:/x.ndf", 3, 5)]

    def test_rekey_moves_the_id_and_keeps_the_lines(self):
        new = dbg.read(rekey_dbg(dbg.write(self.MAP), "MapConfiguration", table(), 2))
        self.assertEqual(new, [dbg.Line("", f"ScenariosData:/{NEW}/MapPack.ndf", 1, 1), self.MAP[1]])
        self.assertEqual(dbg.read(rekey_dbg(dbg.write(self.MAP[1:]), "ScenarioLoader", table(), 1)), self.MAP[1:])

    def test_rekey_needs_one_line_per_object(self):
        with self.assertRaisesRegex(CheckError, "2 lines for 3 objects"):
            rekey_dbg(dbg.write(self.MAP), "MapConfiguration", table(), 3)

    def test_generated_map_names_exports_and_numbers_objects(self):
        root = Node("TGDDescriptorLaunchEffetMap", [("CampList", [])], export="$/GDScript/RootDescriptor")
        raw = encode(build_graph([Node("TCutsceneDescriptorDatabase"), root], [root]), "GDScript")
        lines = dbg.read(generated_dbg(raw, NEW, f"ScenariosData:/{NEW}/Scripting/GDScript.ndf"))
        names = {i: n for i, n in enumerate(ln.name for ln in lines)}
        nb, _, _ = decode(raw)
        self.assertEqual(len(lines), len(nb.objects))
        self.assertEqual([ln.line for ln in lines], list(range(1, len(nb.objects) + 1)))
        self.assertEqual(sorted(n for n in names.values() if n), ["RootDescriptor"])
        with self.assertRaisesRegex(CheckError, "not under ScenariosData:/challenge_B/"):
            generated_dbg(raw, NEW, "ScenariosData:/challenge_A/x.ndf")


class DumpRowsTest(unittest.TestCase):
    def test_rows_follow_the_table(self):
        labels = [r.label for r in dump_rows(table())]
        self.assertEqual(labels, ["id challenge_A -> S", "GUID -> G", "loc ta_name -> tb_name",
                                  "OrderToChainMission 130 -> 7"])
        full = table(map_strings={"_2x2_MapA": "_2x2_MapB"}, map_trans={"MapA": "MapB"},
                     deck_swap={"DECK_A": "DECK_B"})
        self.assertEqual([r.label for r in dump_rows(full)][4:],
                         ["map _2x2_MapA -> _2x2_MapB", "map EnvironmentSettings MapA -> MapB",
                          "deck DECK_A -> DECK_B"])
        self.assertIsNone(dump_rows(full)[0].kinds)  # the id row reaches the tags and source maps too


class FixtureTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "expected", "Info.txt")
        self.item = Entry("out/Info.ndfbin", info("challenge_A"))

    def tearDown(self):
        self.tmp.cleanup()

    def test_typed_dump(self):
        lines = typed_dump(info("challenge_A"), "title")
        self.assertTrue(lines[0].endswith("title"), lines[0])
        self.assertTrue(any("challenge_A" in line for line in lines))

    def test_bless_then_match(self):
        with self.assertRaises(CheckError):
            check_fixture(self.item, self.path, bless=False, summary=False, root=self.tmp.name)
        self.assertEqual(check_fixture(self.item, self.path, bless=True, summary=False, root=self.tmp.name),
                         f"blessed {os.path.join('expected', 'Info.txt')}")
        self.assertEqual(check_fixture(self.item, self.path, bless=False, summary=False, root=self.tmp.name),
                         f"matches {os.path.join('expected', 'Info.txt')}")
        changed = Entry("out/Info.ndfbin", info("challenge_C"))
        with self.assertRaisesRegex(CheckError, "dump differs"):
            check_fixture(changed, self.path, bless=False, summary=False, root=self.tmp.name)

    def test_summary(self):
        check_fixture(self.item, self.path, bless=True, summary=True, root=self.tmp.name)
        with open(self.path, encoding="utf-8") as fh:
            text = fh.read()
        self.assertIn("// 1 objects: {'TChallengeMapInfo': 1}", text)
        self.assertIn("// SHA-256 of the full typed dump: ", text)


class StockTest(unittest.TestCase):
    @paths.skip_unless_extracted("scenarios", "challenge_Survivors", "NDF", "Scenarios", "challenge_Survivors")
    def test_every_stock_tag_is_one_tag_file_naming_its_scenario(self):
        """Every stock challenge's .txn.tag is one TNDFTagFile, and each kind re-keys (rekey_tag): it names at least
        one source of its own scenario by game path. Every .txn beside it has its tag and its source map."""
        tags = sorted(glob.glob(os.path.join(paths.extracted_root(), "scenarios", "challenge_*", "NDF", "Scenarios",
                                             "challenge_*", f"*.{TAG}")))
        self.assertGreaterEqual(len(tags), 16 * 5)
        for path in tags:
            scenario, kind, _ = def_entry("/".join(path.replace(os.sep, "/").split("/")[-4:]))
            with self.subTest(f"{scenario}/{kind}"), open(path, "rb") as fh:
                raw = fh.read()
                nb, _, _ = decode(raw)
                self.assertEqual([nb.cname(ob.cls) for ob in nb.objects], [TAG_CLASS])
                new = rekey_tag(raw, kind, table(source=scenario, scenario="challenge_ModkitTest"), 1)
                self.assertNotIn(scenario.encode(), b"".join(decode(new)[0].strings))
                for ext in (TXN, DBG):
                    self.assertTrue(os.path.isfile(path[:-len(TAG)] + ext), ext)


if __name__ == "__main__":
    unittest.main()
