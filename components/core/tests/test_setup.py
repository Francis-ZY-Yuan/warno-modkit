"""Tests for modkit.core.setup: the scripted stock extraction and its check.

The synthetic install built here has two revisions (100, 200), each holding archives of the real shapes: a full
``_Definition`` copy per revision, delta ``_Details`` archives nested under the previous revision's folder.
"""
import contextlib
import io
import json
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from modkit.core import components, edat, ndfrules, paths, setup
from modkit.core.stock import Stock

HERE = Path(__file__).resolve().parents[1]  # this component's folder: components/core, or an installed plugin's
COMPONENTS = HERE.parent
IN_CLONE = COMPONENTS.name == "components"  # else an installed plugin, <cache>/warno-core/<version>


def component_folders() -> list[Path]:
    """The component folders the stock-reader scan covers: in a clone, every component of the repository; in an
    installed plugin, every installed component (components.installed_components), this one included."""
    if IN_CLONE:
        return sorted(p for p in COMPONENTS.iterdir() if (p / "src").is_dir())
    return sorted({*components.installed_components().values(), HERE})


def put(game: Path, rel: str, files: list[tuple[str, bytes]]) -> None:
    out = game / "Data" / "PC" / rel
    out.parent.mkdir(parents=True, exist_ok=True)
    edat.write_edat(str(out), files)


def make_install(root: Path) -> Path:
    game = root / "game"
    (game / "Data" / "PC" / "100").mkdir(parents=True)
    (game / "Data" / "PC" / "200").mkdir(parents=True)
    (game / "WARNO.exe").write_bytes(b"x" * 1234)
    put(game, "100/Scenarios/foo_Definition.dat", [("NDF/old.ndfbin", b"old"), ("NDF/keep.ndfbin", b"k100")])
    put(game, "200/Scenarios/foo_Definition.dat", [("NDF/keep.ndfbin", b"k200"), ("NDF/new.ndfbin", b"new")])
    put(game, "100/Scenarios/foo_Details.dat", [("a.sav", b"a100"), ("b.sav", b"b100")])
    put(game, "100/200/Scenarios/foo_Details.dat", [("a.sav", b"a200")])
    put(game, "100/Scenarios/bar_Details.dat", [("c.sav", b"c100")])
    put(game, "100/Scenarios/baz_Details.dat", [("d.sav", b"d100")])
    put(game, "100/Maps/m_Assets.dat", [("PC/Texture/m/Preview.tgv", b"p100"), ("PC/Texture/m/Big.tgv", b"big")])
    put(game, "200/Maps/m_Assets.dat", [("PC/Texture/m/Preview.tgv", b"p200")])
    put(game, "100/ZZ_1.dat", [("Localisation/Localisation/Core/X-US.dic", b"us100"),
                               ("Localisation/Localisation/Core/Y.txt", b"no")])
    (game / "Mods" / "ModData").mkdir(parents=True)
    with zipfile.ZipFile(game / "Mods" / "ModData" / "base.zip", "w") as zf:
        zf.writestr("GameData/Gameplay/A.ndf", "export A is 1")
        zf.writestr("GameData/Other/B.ndf", "export B is 2")
    return game


class SetupCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.game = make_install(self.tmp)
        self.into = self.tmp / "ex"
        env = {k: v for k, v in os.environ.items() if not k.startswith("MODKIT_")}
        env["MODKIT_GAME_DIR"] = str(self.game)
        env["MODKIT_EXTRACTED"] = str(self.into)
        env["MODKIT_DATA"] = str(self.tmp / "data")
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def read(self, rel: str) -> bytes:
        return (self.into / rel).read_bytes()

    def extract(self, *stock: Stock):
        with contextlib.redirect_stdout(io.StringIO()):
            return setup.extract(self.into, list(stock))


class ExtractTest(SetupCase):
    def test_overlay_newest_revision_wins_per_path(self):
        self.extract(Stock("s/foo", packs=("foo_Details",)))
        self.assertEqual(self.read("s/foo/a.sav"), b"a200")
        self.assertEqual(self.read("s/foo/b.sav"), b"b100")

    def test_latest_takes_only_the_newest_full_copy(self):
        self.extract(Stock("s/foo", packs=("foo_Definition",), latest=True))
        self.assertEqual(self.read("s/foo/NDF/keep.ndfbin"), b"k200")
        self.assertEqual(self.read("s/foo/NDF/new.ndfbin"), b"new")
        self.assertFalse((self.into / "s" / "foo" / "NDF" / "old.ndfbin").exists())

    def test_include_and_nested_revision_folders(self):
        self.extract(Stock("maps/m", packs=("m_Assets",), include=("PC/Texture/m/Preview.tgv",)))
        self.assertEqual(self.read("maps/m/PC/Texture/m/Preview.tgv"), b"p200")
        self.assertFalse((self.into / "maps" / "m" / "PC" / "Texture" / "m" / "Big.tgv").exists())

    def test_rename_places_files_and_skips_the_rest(self):
        self.extract(Stock("loc", packs=("ZZ_1",), rename=(r"Localisation/Localisation/Core/(X-[A-Z]+\.dic)", r"\1")))
        self.assertEqual(self.read("loc/X-US.dic"), b"us100")
        self.assertEqual(os.listdir(self.into / "loc"), ["X-US.dic"])

    def test_wildcard_dest_makes_one_folder_per_name(self):
        self.extract(Stock("s/*", packs=("{}_Details",)))
        self.assertEqual(sorted(os.listdir(self.into / "s")), ["bar", "baz", "foo"])
        self.assertEqual(self.read("s/bar/c.sav"), b"c100")

    def test_wildcard_with_a_pattern_in_the_last_component(self):
        self.extract(Stock("s/ba*", packs=("{}_Details",)))
        self.assertEqual(sorted(os.listdir(self.into / "s")), ["bar", "baz"])

    def test_provenance_lists_revision_and_archive(self):
        self.extract(Stock("s/foo", packs=("foo_Details",), provenance=True))
        rows = [line.split("\t") for line in self.read("s/foo/_provenance.tsv").decode().splitlines()]
        self.assertEqual(rows, [["a.sav", "200", "100/200/Scenarios/foo_Details.dat", "4", "True"],
                                ["b.sav", "100", "100/Scenarios/foo_Details.dat", "4", "True"]])

    def test_zip_extracts_whole_or_by_include(self):
        self.extract(Stock("mb", archive="Mods/ModData/base.zip", include=("GameData/Gameplay/*",)))
        self.assertEqual(self.read("mb/GameData/Gameplay/A.ndf"), b"export A is 1")
        self.assertFalse((self.into / "mb" / "GameData" / "Other").exists())

    def test_index_is_written(self):
        self.extract(Stock("index_all.tsv", index=True))
        lines = self.read("index_all.tsv").decode().splitlines()
        self.assertEqual(lines[0], "revision\tdat_relpath\tinner_path\tsize")
        self.assertIn("200\t100/200/Scenarios/foo_Details.dat\ta.sav\t4", lines)

    def test_missing_pack_is_an_error_naming_it(self):
        with self.assertRaisesRegex(setup.SetupError, "nope_Details"):
            self.extract(Stock("s/nope", packs=("nope_Details",)))

    def test_same_revision_in_two_archives_is_an_error(self):
        put(self.game, "100/Elsewhere/foo_Details.dat", [("b.sav", b"dup")])
        with self.assertRaisesRegex(setup.SetupError, "b.sav.*both"):
            self.extract(Stock("s/foo", packs=("foo_Details",)))

    def test_a_corrupt_archive_fails_its_checksum(self):
        path = self.game / "Data" / "PC" / "100" / "Scenarios" / "bar_Details.dat"
        raw = bytearray(path.read_bytes())
        raw[-edat.SECTOR] ^= 0xFF  # the first byte of the only payload
        path.write_bytes(bytes(raw))
        with self.assertRaisesRegex(setup.SetupError, "checksum"):
            self.extract(Stock("s/bar", packs=("bar_Details",)))

    def test_rerun_overwrites_and_keeps_other_files(self):
        self.extract(Stock("s/foo", packs=("foo_Details",)))
        (self.into / "s" / "foo" / "mine.txt").write_text("mine")
        (self.into / "s" / "foo" / "a.sav").write_bytes(b"stale")
        self.extract(Stock("s/foo", packs=("foo_Details",)))
        self.assertEqual(self.read("s/foo/a.sav"), b"a200")
        self.assertEqual(self.read("s/foo/mine.txt"), b"mine")

    def test_manifest_records_the_build_it_was_made_from(self):
        self.extract(Stock("s/foo", packs=("foo_Details",)))
        manifest = json.loads(self.read("_extraction.json"))
        self.assertEqual((manifest["game_build"], manifest["exe_size"]), ("200", 1234))


class DeclarationTest(unittest.TestCase):
    def test_stock_rejects_malformed_entries(self):
        with self.assertRaises(ValueError):
            Stock("x")  # no source
        with self.assertRaises(ValueError):
            Stock("/".join(["..", "x"]), packs=("p",))
        with self.assertRaises(ValueError):
            Stock("s/*", packs=("p",))  # '*' without '{}'

    def test_every_declared_entry_is_well_formed_and_unique(self):
        stock = setup.declared()
        self.assertTrue(stock)
        self.assertEqual(len({(s.dest, s.packs, s.archive) for s in stock}), len(stock))

    def test_declared_paths_cover_every_reader(self):
        """Every `extracted_root()` path join in the src, examples and tests of every component (a clone's, or the
        installed plugins') is covered by a STOCK_PATHS entry."""
        folders = component_folders()
        self.assertIn(HERE, folders, "the scan must cover this component: it is looking in the wrong place")
        reads = setup.scan_readers([p for comp in folders
                                    for p in (comp / "src", comp / "examples", comp / "tests") if p.is_dir()])
        if IN_CLONE:  # a clone holds every public component, the readers among them
            self.assertGreater(len(reads), 5, "the scan found (almost) no readers: it is looking in the wrong place")
        stock = setup.declared_from_tree(COMPONENTS) if IN_CLONE else setup.declared()
        uncovered = [f"{r.file}:{r.line}: {'/'.join(r.parts)}" for r in reads if not setup.covers(r.parts, stock)]
        self.assertEqual(uncovered, [], "declare these in the component's STOCK_PATHS (modkit.core.stock.Stock)")

    def scan_text(self, text: str):
        with tempfile.TemporaryDirectory() as tmp:
            Path(tmp, "m.py").write_text(text)
            return [r.parts for r in setup.scan_readers([Path(tmp)])]

    def test_scanner_reads_joins_slashes_aliases_and_skips(self):
        got = self.scan_text(
            "import os\nfrom modkit.core import paths\n"
            "ROOT = str(paths.extracted_root())\n"
            "a = os.path.join(paths.extracted_root(), 'scenarios', 'x')\n"
            "b = os.path.join(ROOT, 'kreide_op', 'p', *rel.split('/'))\n"
            "c = paths.extracted_root() / 'basemaps' / 'a/b'\n"
            "d = paths.extracted_root().joinpath('glad', 'NDF')\n"
            "e = os.path.join(ROOT, '**', 'NDF', 'ModManager.ndfbin')\n"
            "f = os.path.join(a, 'deeper')\n"          # a derived path is not a root join
            "@paths.skip_unless_extracted('scenarios', 'x', 'out')\ndef t(): pass\n"
            "g = os.path.join(ROOT)\n")                # the whole extraction: nothing to declare
        self.assertEqual(sorted(got), sorted([
            ("scenarios", "x"), ("kreide_op", "p"), ("basemaps", "a", "b"), ("glad", "NDF"),
            ("scenarios", "x", "out")]))

    def test_a_line_marked_not_stock_is_skipped(self):
        got = self.scan_text("from modkit.core import paths\n"
                             "x = paths.extracted_root() / 'older'  # not stock\n"
                             "y = paths.extracted_root() / 'glad'\n")
        self.assertEqual(got, [("glad",)])

    def test_covers_matches_prefixes_and_wildcards_both_ways(self):
        stock = [Stock("scenarios/challenge_*", packs=("{}_Details",)), Stock("index_all.tsv", index=True)]
        for parts in (("scenarios",), ("scenarios", "challenge_Survivors", "out", "x.ndfbin"),
                      ("scenarios", "challenge_*", "out"), ("index_all.tsv",)):
            self.assertTrue(setup.covers(parts, stock), parts)
        for parts in (("scenarios", "CampagneStrat_Baor"), ("glad_201602",), ("index_all.tsv", "x")):
            self.assertFalse(setup.covers(parts, stock), parts)

    def test_an_undeclared_read_is_caught(self):
        parts = self.scan_text("from modkit.core import paths\nx = paths.extracted_root() / 'mystery' / 'f'\n")[0]
        self.assertFalse(setup.covers(parts, setup.declared_from_tree(COMPONENTS)))


class CheckTest(SetupCase):
    def table(self, size: int) -> None:
        (self.tmp / "data").mkdir(exist_ok=True)
        (self.tmp / "data" / ndfrules.TABLE_NAME).write_text(
            f"# WARNO.exe {size} bytes; 0 helpers; written by modkit.core.ndfrules extract\n{ndfrules.COLUMNS}\n")

    def run_check(self, stock=()):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), mock.patch.object(setup, "declared", return_value=list(stock)):
            code = setup.check()
        return code, out.getvalue()

    def test_matching_extraction_and_table_pass(self):
        stock = [Stock("s/foo", packs=("foo_Details",))]
        self.extract(*stock)
        self.table(1234)
        code, text = self.run_check(stock)
        self.assertEqual(code, 0, text)
        self.assertIn("200", text)

    def test_a_game_update_makes_both_stale(self):
        stock = [Stock("s/foo", packs=("foo_Details",))]
        self.extract(*stock)
        self.table(1234)
        (self.game / "Data" / "PC" / "300").mkdir()
        (self.game / "WARNO.exe").write_bytes(b"y" * 2000)
        code, text = self.run_check(stock)
        self.assertEqual(code, 1)
        self.assertRegex(text, r"extraction.*STALE.*200.*300")
        self.assertRegex(text, r"ndfrules.*STALE")

    def test_missing_declared_paths_are_listed(self):
        self.extract(Stock("s/foo", packs=("foo_Details",)))
        code, text = self.run_check([Stock("s/foo", packs=("foo_Details",)), Stock("s/gone", packs=("foo_Details",))])
        self.assertEqual(code, 1)
        self.assertIn("s/gone", text)

    def test_no_table_is_reported_not_raised(self):
        stock = [Stock("s/foo", packs=("foo_Details",))]
        self.extract(*stock)
        code, text = self.run_check(stock)
        self.assertEqual(code, 1)
        self.assertRegex(text, r"ndfrules.*no table")

    def test_no_extraction_is_reported(self):
        code, text = self.run_check([Stock("s/foo", packs=("foo_Details",))])
        self.assertEqual(code, 1)
        self.assertRegex(text, r"extraction.*not extracted")


class CliTest(SetupCase):
    def run_main(self, *argv):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = setup.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def test_extract_into_runs_and_check_follows(self):
        with mock.patch.object(setup, "declared", return_value=[Stock("s/foo", packs=("foo_Details",))]):
            code, out, err = self.run_main("extract", "--into", str(self.into))
            self.assertEqual((code, err), (0, ""), out)
            self.assertEqual((self.into / "s" / "foo" / "a.sav").read_bytes(), b"a200")

    def test_unconfigured_game_exits_1_naming_the_skill(self):
        del os.environ["MODKIT_GAME_DIR"]
        with mock.patch.object(paths, "_find_config", return_value=None):
            code, out, err = self.run_main("extract", "--into", str(self.into))
        self.assertEqual(code, 1)
        self.assertIn("warno-setup", err)
        self.assertNotIn("Traceback", err)

    def test_missing_install_data_exits_1(self):
        os.environ["MODKIT_GAME_DIR"] = str(self.tmp / "nowhere")
        code, out, err = self.run_main("extract", "--into", str(self.into))
        self.assertEqual(code, 1)
        self.assertIn("Data", err)


if __name__ == "__main__":
    unittest.main()
