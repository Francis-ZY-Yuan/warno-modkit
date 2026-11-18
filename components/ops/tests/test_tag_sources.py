"""Tests for the gate that a mod's compiled scenario transactions are current for the installed game
(modkit.ops.gates.check_tag_sources, gate 5's tag-sources) [[txn-tag-config-hash]].

Everything but `InstalledStock` runs on synthetic tags and stock folders (no game data). `InstalledStock` holds every
stock scenario pack of the configured game install to its own build's tags, and skips without one.
"""
from __future__ import annotations

import glob
import os
import tempfile
import unittest
from pathlib import Path
from typing import Mapping, Sequence
from unittest import mock

from modkit.core import edat, mods, paths
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops import gates
from modkit.ops.gates import OWN_FOLDER, StockTags, check_tag_sources, read_stock_tags, stock_tags, tag_sources
from modkit.ops.graph import Map, Node, Str, build_graph, encode
from modkit.ops.rekey import TAG, TAG_CLASS, TXN, def_path

LOADER, CONSTANTS, ENUM = "CommonData:/T/Loader.ndf", "CommonData:/T/Constants.ndf", "CommonData:/T/Enum.ndf"
# One build's stock sources per kind, in order, with their hashes; a scenario's own sources are written OWN_FOLDER and
# hold a hash of their own in each scenario (tag_file).
SOURCES = {
    "ScenarioLoader": ((OWN_FOLDER + "Scenario.ndf", 0), (LOADER, 11), (CONSTANTS, 12)),
    "GDScript": ((ENUM, 13), (OWN_FOLDER + "Scripts/One.ndf", 0)),
}
STALE = "the game finds each \\.txn stale and recompiles the scenario from sources the mod does not ship, stopping " \
        "with \"NDF parsing error\\. Retry\\?\"; rebuild the mod against this game build:\n  "


def tag_file(scenario: str, sources: Sequence[tuple[str, int]], config_hash: int = 0) -> bytes:
    """A .txn.tag: one TNDFTagFile holding `config_hash` and the SourceFileHashes `sources`, OWN_FOLDER written as
    `scenario`'s own folder, whose sources hold a hash that differs per scenario."""
    own = f"ScenariosData:/{scenario}/"
    pairs = tuple((Str(p.replace(OWN_FOLDER, own)), Value(0x13, h if not p.startswith(OWN_FOLDER) else len(scenario)))
                  for p, h in sources)
    props = [("ConfigHash", Value(0x13, config_hash)), ("SourceFileHashes", Map(pairs))]
    return encode(build_graph([Node(TAG_CLASS, props)], []), "tag")


def tags(scenario: str, sources: Mapping[str, Sequence[tuple[str, int]]] = SOURCES) -> dict[str, bytes]:
    """A Definition pack's tags: one per kind of `sources`, plus a .txn the gate does not read."""
    out = {def_path(kind, TAG, scenario): tag_file(scenario, s) for kind, s in sources.items()}
    out[def_path("GDScript", TXN, scenario)] = b"not a tag"
    return out


def write_stock(folder: Path, scenarios: Sequence[str] = ("challenge_S1", "challenge_S2"),
                sources: Mapping[str, Sequence[tuple[str, int]]] = SOURCES) -> Path:
    """A build's Scenarios folder: one <scenario>_Definition.dat per scenario holding its tags (a second GDScript
    script for the second, as stock's scenarios ship scripts of their own), and a Details pack the reader skips."""
    folder.mkdir(parents=True, exist_ok=True)
    for i, scenario in enumerate(scenarios):
        own = dict(sources)
        if i and "GDScript" in own:
            own["GDScript"] = (*own["GDScript"], (OWN_FOLDER + "Scripts/Two.ndf", 0))
        edat.write_edat(str(folder / f"{scenario}_Definition.dat"), sorted(tags(scenario, own).items()))
        edat.write_edat(str(folder / f"{scenario}_Details.dat"), [("x.ndfbin", b"x")])
    return folder


class TagSourcesTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.stock = read_stock_tags(write_stock(self.tmp / "Data" / "PC" / "300" / "Scenarios"))

    def test_a_tags_sources_as_stocks_are_compared(self):
        """The own folder is written OWN_FOLDER; GDScript's own scripts are left out of its list; the hashes are the
        sources' outside the own folder."""
        raw = tag_file("challenge_M", SOURCES["ScenarioLoader"])
        self.assertEqual(tag_sources(raw, "challenge_M", "ScenarioLoader"),
                         ((OWN_FOLDER + "Scenario.ndf", LOADER, CONSTANTS), {LOADER: 11, CONSTANTS: 12}))
        raw = tag_file("challenge_M", SOURCES["GDScript"])
        self.assertEqual(tag_sources(raw, "challenge_M", "GDScript"), ((ENUM,), {ENUM: 13}))

    def test_one_builds_stock_holds_one_list_per_kind_and_one_hash_per_source(self):
        self.assertEqual(self.stock, StockTags("build 300's stock",
                                               {"ScenarioLoader": (OWN_FOLDER + "Scenario.ndf", LOADER, CONSTANTS),
                                                "GDScript": (ENUM,)},
                                               {LOADER: 11, CONSTANTS: 12, ENUM: 13}, 4))
        self.assertEqual(read_stock_tags(write_stock(self.tmp / "given")).name, "the given stock")

    def test_a_folder_not_one_builds_stock_fails(self):
        moved = dict(SOURCES, ScenarioLoader=((OWN_FOLDER + "Scenario.ndf", 0), (LOADER, 99), (CONSTANTS, 12)))
        mixed = self.tmp / "mixed"
        write_stock(mixed, ("challenge_S1",))
        write_stock(mixed, ("challenge_S2",), moved)
        with self.assertRaisesRegex(CheckError, r"stock's tags hold more than one hash of CommonData:/T/Loader\.ndf: "
                                                r"not one build's stock$"):
            read_stock_tags(mixed)
        listed = dict(SOURCES, GDScript=((CONSTANTS, 12), (ENUM, 13)))
        write_stock(mixed, ("challenge_S2",), listed)
        with self.assertRaisesRegex(CheckError, r"stock's GDScript tags hold more than one source list: not one "
                                                r"build's stock$"):
            read_stock_tags(mixed)
        (self.tmp / "empty").mkdir()
        with self.assertRaisesRegex(CheckError, r"no stock scenario tag \(NDF/Scenarios/<scenario>/<Kind>\.txn\.tag "
                                                r"in a \*_Definition\.dat\)$"):
            read_stock_tags(self.tmp / "empty")

    def test_tags_current_for_stock_pass(self):
        """Another scenario's tags, built from the same stock: its own folder and own scripts aside, they are
        stock's."""
        entries = tags("challenge_M", dict(SOURCES, GDScript=(*SOURCES["GDScript"], (OWN_FOLDER + "Scripts/M.ndf", 0))))
        self.assertEqual(check_tag_sources(entries, self.stock), 2)

    def test_a_template_hash_of_another_build_fails_naming_the_tag_the_source_and_both_values(self):
        old = dict(SOURCES, ScenarioLoader=((OWN_FOLDER + "Scenario.ndf", 0), (LOADER, 99), (CONSTANTS, 12)))
        with self.assertRaises(CheckError) as cm:
            check_tag_sources(tags("challenge_M", old), self.stock)
        self.assertRegex(str(cm.exception),
                         r"^1 of 2 tags are not current for build 300's stock: " + STALE
                         + r"Definition:NDF/Scenarios/challenge_M/ScenarioLoader\.txn\.tag: SourceFileHashes holds 99 "
                           r"for 'CommonData:/T/Loader\.ndf', but build 300's stock tags hold 11 \(the game would stop "
                           r"on \"File not found : 'ScenariosData:/challenge_M/Scenario\.ndf'\"\)$")

    def test_a_list_of_another_build_fails_naming_each_entry(self):
        """A source stock lists and the tag lacks, one the tag lists and stock does not (a template's or the scenario's
        own), and the same sources in another order."""
        old = dict(SOURCES, ScenarioLoader=((OWN_FOLDER + "Scenario.ndf", 0), (OWN_FOLDER + "Extra.ndf", 0),
                                            (LOADER, 11), ("CommonData:/T/Globals.ndf", 5)))
        with self.assertRaises(CheckError) as cm:
            check_tag_sources(tags("challenge_M", old), self.stock)
        self.assertIn("Definition:NDF/Scenarios/challenge_M/ScenarioLoader.txn.tag: SourceFileHashes lacks "
                      "'CommonData:/T/Constants.ndf', which build 300's stock ScenarioLoader tags list; "
                      "SourceFileHashes lists 'ScenariosData:/challenge_M/Extra.ndf', which build 300's stock "
                      "ScenarioLoader tags do not; SourceFileHashes lists 'CommonData:/T/Globals.ndf', which build "
                      "300's stock ScenarioLoader tags do not (the game would stop", str(cm.exception))
        swapped = dict(SOURCES, GDScript=((OWN_FOLDER + "Scripts/One.ndf", 0), (ENUM, 13)),
                       ScenarioLoader=((LOADER, 11), (OWN_FOLDER + "Scenario.ndf", 0), (CONSTANTS, 12)))
        with self.assertRaises(CheckError) as cm:
            check_tag_sources(tags("challenge_M", swapped), self.stock)
        self.assertRegex(str(cm.exception), r"^1 of 2 tags are not current for build 300's stock: .*\n  Definition:NDF/"
                                            r"Scenarios/challenge_M/ScenarioLoader\.txn\.tag: SourceFileHashes lists "
                                            r"the ScenarioLoader sources of build 300's stock tags in another order ")

    def test_a_kind_stock_does_not_hold_fails(self):
        entries = dict(tags("challenge_M"), **tags("challenge_M", {"TrophyDef": ((LOADER, 11),)}))
        with self.assertRaisesRegex(CheckError, r"^1 of 3 tags .*\n  Definition:NDF/Scenarios/challenge_M/"
                                                r"TrophyDef\.txn\.tag: build 300's stock scenario packs hold no "
                                                r"TrophyDef\.txn\.tag to compare it with$"):
            check_tag_sources(entries, self.stock)

    def test_the_installs_stock_is_its_newest_build_holding_scenario_packs(self):
        """stock_tags reads Data/PC/<build>/Scenarios of the newest build folder holding the scenario packs (a newer
        one without them is skipped), and is None when the game folder holds none."""
        self.addCleanup(gates._stock_tags.cache_clear)
        game = self.tmp / "game"
        write_stock(game / "Data" / "PC" / "290" / "Scenarios", sources=dict(SOURCES, GDScript=((ENUM, 1),)))
        write_stock(game / "Data" / "PC" / "301" / "Scenarios")
        (game / "Data" / "PC" / "310" / "Scenarios").mkdir(parents=True)
        with mock.patch.dict(os.environ, {paths.ENV_GAME_DIR: str(game)}):
            self.assertEqual(stock_tags(), StockTags("build 301's stock", self.stock.lists, self.stock.hashes, 4))
        with mock.patch.dict(os.environ, {paths.ENV_GAME_DIR: str(self.tmp / "nothing")}):
            self.assertIsNone(stock_tags())


_STOCK_DIR = paths.stock_scenarios_dir()


@unittest.skipIf(_STOCK_DIR is None, "the game folder holds no Data/PC/<build>/Scenarios (see the warno-setup skill)")
class InstalledStock(unittest.TestCase):
    def test_every_stock_scenario_pack_is_current_for_its_own_build(self):
        """The gate's ground truth: every stock scenario's tags pass against the install's own stock tags."""
        current = stock_tags()
        packs = sorted(glob.glob(os.path.join(_STOCK_DIR, "*_Definition.dat")))
        checked = sum(check_tag_sources(dict(mods.read_pack(pack, lambda p: p.endswith(f".{TAG}"))), current)
                      for pack in packs)
        self.assertEqual(checked, current.tags)


if __name__ == "__main__":
    unittest.main()
