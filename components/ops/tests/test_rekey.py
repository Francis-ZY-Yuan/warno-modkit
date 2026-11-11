"""Tests for modkit.ops.rekey (re-keying tables and rows) and the dump gates in modkit.ops.gates."""
import hashlib
import os
import tempfile
import unittest
from dataclasses import FrozenInstanceError

from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.gates import check_dump_diff, check_fixture, typed_dump
from modkit.ops.graph import Imp, Node, Str, all_values, build_graph, decode, encode, i32, loc
from modkit.ops.rekey import (
    DumpRow, Rekey, ScalarEdit, def_path, dump_rows, rekey_definition, rekey_tag, replace_text, repath, swap_exact,
    tag_name_hashes,
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

    def test_tag_name_hashes_take_the_sources(self):
        got = tag_name_hashes("challenge_X", ("Scenario.ndf", "Scripting/GdItems.ndf"))
        self.assertEqual(got["Scenario.ndf"], hashlib.md5(b"ScenariosData:/challenge_X/Scenario.ndf").digest())
        self.assertEqual(list(got), ["Scenario.ndf", "Scripting/GdItems.ndf"])
        self.assertEqual(tag_name_hashes("challenge_X", ()), {})

    def test_rows_are_frozen(self):
        row = DumpRow("id", None, "a", "b")
        edit = ScalarEdit("MapConfiguration", "TChallengeMapInfo", "Duration", Value(0x02, 3), Value(0x02, 1))
        with self.assertRaises(FrozenInstanceError):
            row.repl = "c"
        with self.assertRaises(FrozenInstanceError):
            edit.new = Value(0x02, 2)


class DumpDiffTest(unittest.TestCase):
    PATH = "NDF/Scenarios/MapConfiguration/challenge_B.ndfbin"

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
        tag = Entry("NDF/Scenarios/MapConfiguration/challenge_B.tag", info("challenge_B"), info("challenge_A"))
        _, fired = check_dump_diff(tag, [DumpRow("id", ("MapConfiguration.tag",), "challenge_A", "challenge_B")])
        self.assertEqual(fired, {"id"})


SOURCE, NEW = "challenge_A", "challenge_B"
G_OLD, G_NEW = bytes(range(16)), bytes(range(16, 32))
SOURCES = ("Scenario.ndf", "Scripting/GdItems.ndf")
EDITS = (ScalarEdit("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission", Value(0x03, 130), Value(0x03, 7)),)


def table(**kw) -> Rekey:
    """A clone of challenge_A as challenge_B; keyword arguments replace fields."""
    fields = dict(source=SOURCE, scenario=NEW, guid_source=G_OLD, guid=G_NEW, renames={"ta_name": "tb_name"},
                  token_prefix="ta_", scalar_edits=EDITS, map_strings={}, map_trans={}, deck_swap={},
                  kinds=("GDScript", "MapConfiguration", "ScenarioInfo"), tag_sources=SOURCES, tag_dropped=())
    return Rekey(**{**fields, **kw})


def map_configuration(deck: str = "DECK_A", token: str = "ta_name") -> bytes:
    return encode(build_graph([Node("TChallengeMapInfo", [
        ("Name", loc(token)), ("Path", Str(f"Scenarios/{SOURCE}")), ("GUID", Value(0x1A, G_OLD)),
        ("OrderToChainMission", Value(0x03, 130)), ("LocalPlayerDeck", Str(deck)),
        ("Environment", Imp("$/GraphicSettings/EnvironmentSettings/MapA"))])], []), "MapConfiguration")


def scenario_info() -> bytes:
    return encode(build_graph([Node("TScenarioLoadInfo", [
        ("Name", Str(SOURCE)), ("GUID", Value(0x1A, G_OLD)), ("RootDatapackName", Str("_2x2_MapA"))])], []),
        "ScenarioInfo")


def tag(kind: str, sources=SOURCES) -> bytes:
    pairs = [Value(0x22, (Value(0x25, h), Value(0x25, bytes(16)))) for h in tag_name_hashes(SOURCE, sources).values()]
    return encode(build_graph([Node("TTagFile", [("BaseName", Str(f"Scenarios/{kind}/{SOURCE}")),
                                                 ("Hashes", pairs)])], []), f"{kind}.tag")


class PathTest(unittest.TestCase):
    def test_def_path_names_its_scenario(self):
        self.assertEqual(def_path("GDScript", "tag", "challenge_X"), "NDF/Scenarios/GDScript/challenge_X.tag")

    def test_repath(self):
        self.assertEqual(repath(f"PC/Texture/{SOURCE}/a.tgv", SOURCE, NEW), f"PC/Texture/{NEW}/a.tgv")
        with self.assertRaisesRegex(CheckError, "no challenge_A component"):
            repath(f"PC/Texture/{SOURCE}x/a.tgv", SOURCE, NEW)


class RekeyDefinitionTest(unittest.TestCase):
    """Both tables the two cloners use: no map, deck or token swap beyond the id, GUID and menu tokens, and the
    full one with the map and deck swaps. Each re-keyed file differs from stock only by dump_rows."""

    def gate(self, kind: str, stock: bytes, rk: Rekey) -> set[str]:
        new = rekey_definition(stock, kind, rk)
        _, fired = check_dump_diff(Entry(def_path(kind, "ndfbin", rk.scenario), new, stock), dump_rows(rk))
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
                             table(scalar_edits=(ScalarEdit("ScenarioInfo", "TScenarioLoadInfo", "Duration",
                                                            Value(0x02, 3), Value(0x02, 1)),)))


class RekeyTagTest(unittest.TestCase):
    def test_base_name_and_source_hashes(self):
        stock = tag("ScenarioInfo")
        new = rekey_tag(stock, "ScenarioInfo", table())
        nb, _, _ = decode(new)
        self.assertEqual(nb.strings, [f"Scenarios/ScenarioInfo/{NEW}".encode()])
        firsts = {x.v[0].v for _, _, x in all_values(nb) if x.tag == 0x22}
        self.assertEqual(firsts, set(tag_name_hashes(NEW, SOURCES).values()))
        _, fired = check_dump_diff(Entry(def_path("ScenarioInfo", "tag", NEW), new, stock), dump_rows(table()))
        self.assertEqual(fired, {"id challenge_A -> S", "tag name hash Scenario.ndf",
                                 "tag name hash Scripting/GdItems.ndf"})

    def test_every_listed_hash_is_swapped(self):
        with self.assertRaisesRegex(CheckError, "no scenario source-name hash"):
            rekey_tag(tag("ScenarioInfo", ("Other.ndf",)), "ScenarioInfo", table())


class DumpRowsTest(unittest.TestCase):
    def test_rows_follow_the_table(self):
        labels = [r.label for r in dump_rows(table())]
        self.assertEqual(labels, ["id challenge_A -> S", "GUID -> G", "loc ta_name -> tb_name",
                                  "OrderToChainMission 130 -> 7", "tag name hash Scenario.ndf",
                                  "tag name hash Scripting/GdItems.ndf"])
        full = table(map_strings={"_2x2_MapA": "_2x2_MapB"}, map_trans={"MapA": "MapB"},
                     deck_swap={"DECK_A": "DECK_B"}, tag_dropped=("Scenario.ndf",))
        self.assertEqual([r.label for r in dump_rows(full)][4:],
                         ["map _2x2_MapA -> _2x2_MapB", "map EnvironmentSettings MapA -> MapB",
                          "deck DECK_A -> DECK_B", "tag name hash Scripting/GdItems.ndf"])
        tag_row = dump_rows(full)[-1]
        self.assertEqual(tag_row.kinds, ("GDScript.tag", "MapConfiguration.tag", "ScenarioInfo.tag"))


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
    @paths.skip_unless_extracted("scenarios", "challenge_Survivors", "NDF", "Scenarios", "ScenarioInfo")
    def test_tag_sidecar_holds_the_source_name_hashes(self):
        """A stock .tag sidecar holds MD5('ScenariosData:/<scenario>/<source>') for its scenario's sources."""
        folder = os.path.join(paths.extracted_root(), "scenarios", "challenge_Survivors", "NDF", "Scenarios")
        with open(os.path.join(folder, "ScenarioInfo", "challenge_Survivors.tag"), "rb") as fh:
            image = decode(fh.read())[2]
        hashes = tag_name_hashes("challenge_Survivors", ("Scenario.ndf", "MapPack.ndf"))
        self.assertTrue(any(h in image for h in hashes.values()))
        self.assertFalse(any(h in image for h in tag_name_hashes("challenge_Other", ("Scenario.ndf",)).values()))


if __name__ == "__main__":
    unittest.main()
