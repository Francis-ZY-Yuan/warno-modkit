"""Tests for modkit.core.ndfrules, WARNO's load-time property checks as a build gate.

`Violations` feeds hand-made NdfBins to `violations`, and `Slot` the validate-slot choice; neither needs the game.
`Location` checks where the table lives. `Table` reads the table `extract` wrote to the data folder, `Stock` applies
it to the extracted stock files (the game loads all of them, so a violation means a rule was read wrong), and `Exe`
reads the installed WARNO.exe; each skips when its data is absent (see the warno-setup skill).

Rule.validate values below are placeholders: where a validate routine sits is read from your own exe at run time.
"""
from __future__ import annotations

import collections
import contextlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modkit.core import ndfbin, ndfrules, paths
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.core.ndfrules import Rule

STRESS_V, WAIT_V, CUT_V, PROD_V = 1, 2, 3, 4  # placeholder validate ids
BIG = 3 << 24                                  # a grouping key as large as a real one: it must never be printed
HEX5 = r"0x[0-9a-fA-F]{5,}"


def nb_of(cls: str, props: dict[str, Value]) -> ndfbin.NdfBin:
    nb = ndfbin.NdfBin()
    c = nb.intern_class(cls)
    nb.objects.append(ndfbin.Obj(c, [(nb.intern_prop(n, c), v) for n, v in props.items()]))
    return nb


def rules(*rs: Rule) -> dict[str, list[Rule]]:
    out: dict[str, list[Rule]] = {}
    for r in rs:
        out.setdefault(r.cls, []).append(r)
    return out


STRESS = rules(Rule("TGDDescriptorChangeStress", "defined", "DamageType", "", "", STRESS_V, 0, 0),
               Rule("TGDDescriptorChangeStress", "defined", "Group", "", "", STRESS_V, 0, 0))
GROUP = Value(0x09, ndfbin.Ref(1, 0, 0))


class Violations(unittest.TestCase):
    def test_zero_enum_fails(self):
        """A ChangeStress with DamageType <int32> 0: the game's fatal 'must be defined' load error."""
        bad = ndfrules.violations(nb_of("TGDDescriptorChangeStress", {
            "DamageType": Value(0x02, 0), "Group": GROUP, "Value": Value(0x02, 400)}), STRESS)
        self.assertEqual(len(bad), 1)
        self.assertIn("'DamageType' must be defined: the game rejects a zero value", bad[0])

    def test_nonzero_passes(self):
        self.assertEqual(ndfrules.violations(nb_of("TGDDescriptorChangeStress", {
            "DamageType": Value(0x02, 2), "Group": GROUP}), STRESS), [])

    def test_missing_fails_unless_stock_omits_it(self):
        nb = nb_of("TGDDescriptorChangeStress", {"DamageType": Value(0x02, 2)})
        self.assertIn("'Group' must be defined: it is left out", ndfrules.violations(nb, STRESS)[0])
        omitted = rules(Rule("TGDDescriptorChangeStress", "defined", "Group", "", "", STRESS_V, 9, 3))
        self.assertEqual(ndfrules.violations(nb, omitted), [])  # stock leaves it out: the C++ default passes

    def test_zero_values_of_each_kind(self):
        nb = ndfbin.NdfBin(strings=[b"", b"x"])
        zero = [Value(0x11, []), Value(0x07, 0), Value(0x05, 0.0), Value(0x00, False), Value(0x1D, bytes(8))]
        some = [Value(0x11, [GROUP]), Value(0x07, 1), Value(0x05, 0.5), Value(0x00, True), GROUP,
                ndfbin.loc_value("od_start")]
        self.assertEqual([ndfrules.is_zero(nb, v) for v in zero], [True] * len(zero))
        self.assertEqual([ndfrules.is_zero(nb, v) for v in some], [False] * len(some))

    def test_constant_comparison(self):
        wait = rules(Rule("TGDDescriptorWaitDuration", "ge", "Duration", "0.0", "", WAIT_V, 0, 0))
        self.assertEqual(ndfrules.violations(nb_of("TGDDescriptorWaitDuration", {"Duration": Value(0x05, 15.0)}),
                                             wait), [])
        self.assertIn("fails 'ge 0.0'", ndfrules.violations(
            nb_of("TGDDescriptorWaitDuration", {"Duration": Value(0x05, -1.0)}), wait)[0])

    def test_unreviewed_check_fails_and_review_evaluates_it(self):
        cut = rules(Rule("TCutsceneDescriptor", "cond", "Key", "", "FKey.IsValid()", CUT_V, 9, 0))
        nb = nb_of("TCutsceneDescriptor", {"Key": ndfbin.loc_value("od_start")})
        self.assertIn("unreviewed game check", ndfrules.violations(nb, cut, reviewed={})[0])
        self.assertEqual(ndfrules.violations(nb, cut), [])  # REVIEWED: nonzero
        zero_key = nb_of("TCutsceneDescriptor", {"Key": Value(0x1D, bytes(8))})
        self.assertIn("fails 'FKey.IsValid()'", ndfrules.violations(zero_key, cut)[0])

    def test_unknown_property_fails_until_reviewed(self):
        """A ProductionUnites with Group and Transporter, which no rule names and no stock object sets. Each fails
        until ndfrules.PROPERTIES reviews it; reviewed, they pass, and an unreviewed one still fails."""
        made = rules(*(Rule("TGDDescriptorProductionUnites", "defined", p, "", "", PROD_V, 6, 0)
                       for p in ("Camp", "Position", "TypeUnit")),
                     Rule("TGDDescriptorProductionUnites", "ge", "NbUnit", "1", "", PROD_V, 6, 0))
        props = {"Camp": GROUP, "Group": GROUP, "NbUnit": Value(0x02, 1), "Position": GROUP, "Transporter": GROUP,
                 "TypeUnit": GROUP}
        bad = ndfrules.violations(nb_of("TGDDescriptorProductionUnites", props), made, properties={
            "TGDDescriptorProductionUnites": {}})
        self.assertEqual([b.split("'")[1] for b in bad], ["Group", "Transporter"])
        self.assertIn("unknown to the gate: no rule names it and it is not reviewed", bad[0])
        self.assertEqual(ndfrules.violations(nb_of("TGDDescriptorProductionUnites", props), made), [])
        extra = nb_of("TGDDescriptorProductionUnites", {**props, "CompanyFillingRatio": Value(0x02, 100)})
        self.assertEqual([b.split("'")[1] for b in ndfrules.violations(extra, made)], ["CompanyFillingRatio"])
        self.assertEqual(ndfrules.violations(extra, made, properties=None), [])

    def test_unknown_property_message_says_what_the_validation_tests(self):
        made = rules(*(Rule("TGDDescriptorProductionUnites", "defined", p, "", "", BIG, 6, 0)
                       for p in ("TypeUnit", "Camp", "Position")),
                     Rule("TGDDescriptorProductionUnites", "ge", "NbUnit", "1", "", BIG, 6, 0))
        bad = ndfrules.violations(nb_of("TGDDescriptorProductionUnites", {"Group": GROUP}), made,
                                  properties={"TGDDescriptorProductionUnites": {}})
        self.assertIn("the game's validation of TGDDescriptorProductionUnites tests only Camp, NbUnit, Position, "
                      "TypeUnit; " + ndfrules.REVIEW_REMEDY, bad[0])
        none = ndfrules.violations(nb_of("TGDDescriptorProductionUnites", {"Group": GROUP}), {},
                                   properties={"TGDDescriptorProductionUnites": {}})
        self.assertIn("the table holds no check of TGDDescriptorProductionUnites", none[0])

    def test_unreviewed_check_remedy(self):
        cut = rules(Rule("TCutsceneDescriptor", "cond", "Key", "", "FKey.IsValid()", BIG, 9, 0))
        bad = ndfrules.violations(nb_of("TCutsceneDescriptor", {"Key": GROUP}), cut, reviewed={})
        self.assertEqual(bad, ["#0 TCutsceneDescriptor: unreviewed game check cond 'Key': " + ndfrules.REVIEW_REMEDY])

    def test_the_remedy_never_says_to_edit_the_installed_core(self):
        """A failure sends the modder to their own build's reviewed_pending, or upstream; an installed core is
        replaced on update, so its tables are never edited in place."""
        self.assertEqual(ndfrules.REVIEW_REMEDY,
                         "if you have checked it against the game and stock, put this gate's message in your build's "
                         "reviewed_pending (warno-gates), and send the review upstream so a toolkit release adds it")
        cut = rules(Rule("TCutsceneDescriptor", "cond", "Key", "", "FKey.IsValid()", BIG, 9, 0))
        made = rules(Rule("TGDDescriptorProductionUnites", "defined", "Camp", "", "", BIG, 6, 0))
        bad = ndfrules.violations(nb_of("TCutsceneDescriptor", {"Key": GROUP}), cut, reviewed={})
        bad += ndfrules.violations(nb_of("TGDDescriptorProductionUnites", {"Camp": GROUP, "Group": GROUP}), made,
                                   properties={"TGDDescriptorProductionUnites": {}})
        self.assertEqual(len(bad), 2)
        for text in bad:
            self.assertNotRegex(text, r"add it to ndfrules\.|\badd it to\b")
            self.assertTrue(text.endswith(ndfrules.REVIEW_REMEDY), text)

    def test_messages_name_no_place_in_the_exe(self):
        """Every kind of violation message, from rules whose grouping key is a large number: none prints it."""
        cls = "TGDDescriptorProductionUnites"
        made = rules(Rule(cls, "defined", "Camp", "", "", BIG, 6, 0), Rule(cls, "ge", "NbUnit", "1", "", BIG, 6, 0),
                     Rule(cls, "cond", "TypeUnit", "", "FKey.IsValid()", BIG, 6, 0),
                     Rule(cls, "custom", "", "", "failed condition 'X > 0'", BIG, 6, 0))
        nb = nb_of(cls, {"Camp": Value(0x02, 0), "NbUnit": Value(0x02, 0), "TypeUnit": Value(0x1D, bytes(8)),
                         "Group": GROUP})
        bad = ndfrules.violations(nb, made, reviewed={(cls, "cond", "TypeUnit"): ("nonzero", "test")},
                                  properties={cls: {}})
        bad += ndfrules.violations(nb, made, reviewed={}, properties=None)
        self.assertGreaterEqual(len(bad), 6)
        for text in bad:
            with self.subTest(text=text[:60]):
                self.assertNotRegex(text, HEX5)
                self.assertNotIn(f"{BIG:x}", text.lower())
                self.assertNotIn("validate ", text)

    def test_reviews_carry_no_exe_detail(self):
        """Review reasons are functional facts plus stock evidence: no address, offset or decompiled code."""
        texts = [why for _, why in ndfrules.REVIEWED.values()]
        texts += [ev for props in ndfrules.PROPERTIES.values() for ev in props.values()]
        for text in texts:
            with self.subTest(text=text[:40]):
                self.assertNotRegex(text, r"0x[0-9a-fA-F]+|\[r[a-z0-9]+[+-]|\.py:\d|\bcmp\b|\bmov\b|vtable|slot")


class Slot(unittest.TestCase):
    def test_slot_is_the_one_index_that_holds_checkers(self):
        self.assertEqual(ndfrules.pick_slot(collections.Counter({5: 900, 9: 3, 2: 1})), 5)

    def test_ambiguous_or_empty_slot_fails(self):
        with self.assertRaisesRegex(CheckError, "no vtable"):
            ndfrules.pick_slot(collections.Counter())
        with self.assertRaisesRegex(CheckError, "ambiguous"):
            ndfrules.pick_slot(collections.Counter({5: 100, 9: 60}))

    def test_checking_routines_at_the_slot_must_chain_to_the_root(self):
        at_slot = set(range(100))
        self.assertEqual(ndfrules.check_chain(at_slot, set(range(95)) | {500}), (95, 100))
        with self.assertRaisesRegex(CheckError, "only 40 of the 100 checking routines .* the index is wrong"):
            ndfrules.check_chain(at_slot, set(range(40)))
        with self.assertRaisesRegex(CheckError, "only 0 of the 0"):
            ndfrules.check_chain(set(), {1})


class Output(unittest.TestCase):
    """What the CLI prints names no place in the exe: the table keeps its grouping key, `show` and `extract` never
    print it, and the stamp holds counts only."""

    def run_main(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = ndfrules.main(list(args))
        return code, out.getvalue()

    def test_stamp_holds_counts_only(self):
        stamp = ndfrules.stamp_line(55000000, 759, 821, 827, 888)
        self.assertNotRegex(stamp, HEX5)
        self.assertRegex(stamp, r"^WARNO\.exe 55000000 bytes; ")  # load_table reads the size from here

    def test_show_and_extract_print_no_address(self):
        cls = "TGDDescriptorChangeStress"
        old = [Rule(cls, "defined", "DamageType", "", "", BIG, 0, 0), Rule(cls, "defined", "Gone", "", "", BIG, 0, 0)]
        new = [Rule(cls, "defined", "DamageType", "", "", BIG + 16, 0, 0),  # moved routine: not a change
               Rule(cls, "defined", "Group", "", "", BIG + 16, 0, 0)]
        stamp = ndfrules.stamp_line(16, 759, 821, 827, 888)
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"MODKIT_DATA": d}):
            ndfrules.write_table(old, ndfrules.stamp_line(16, 1, 1, 1, 1))
            with open(ndfrules.table_path(), encoding="utf-8") as fh:
                self.assertIn(f"{BIG:#x}", fh.read())  # the file keeps the grouping key
            code, shown = self.run_main("show", cls)
            self.assertEqual(code, 0, shown)
            self.assertIn("DamageType", shown)
            with mock.patch.object(ndfrules, "extract", return_value=(new, stamp)):
                code, extracted = self.run_main("extract")
            self.assertEqual(code, 0, extracted)
            self.assertIn("1 rows removed, 1 added", extracted)
            self.assertIn("- TGDDescriptorChangeStress\tdefined\tGone", extracted)
            self.assertIn("+ TGDDescriptorChangeStress\tdefined\tGroup", extracted)
            code, shown_after = self.run_main("show", cls)
        for text in (shown, extracted, shown_after):
            self.assertNotRegex(text, HEX5)
            self.assertNotIn(f"{BIG:x}", text.lower())
            self.assertNotIn(f"{BIG + 16:x}", text.lower())


class Location(unittest.TestCase):
    def test_table_lives_in_the_data_dir(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"MODKIT_DATA": d}):
            self.assertEqual(ndfrules.table_path(), Path(d) / "ndfrules.tsv")
            r = Rule("TGDDescriptorChangeStress", "defined", "Group", "", "", STRESS_V, 0, 0)
            ndfrules.write_table([r], "WARNO.exe 16 bytes; test")
            got, size = ndfrules.load_table()
            self.assertEqual((got, size), ({"TGDDescriptorChangeStress": [r]}, 16))
        package = Path(ndfrules.__file__).resolve().parent
        self.assertFalse(list(package.glob("*.tsv")))

    def test_cli_reports_a_missing_table(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"MODKIT_DATA": d}):
            out = io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                self.assertEqual(ndfrules.main(["show", "TCutsceneDescriptor"]), 1)
            self.assertIn("extract", out.getvalue())
            self.assertNotIn("Traceback", out.getvalue())


SELF = Value(0x09, ndfbin.Ref(ndfbin.REF_OBJECT, 0, 0))  # a reference small_file can write: its own object


def small_file(cls: str = "TThing", mode: int = ndfbin.MODE_ZSTD, **props: Value) -> bytes:
    """A whole .ndfbin file of one exported object of class `cls`."""
    sections = ["OBJE", "TOPO", "CHNK", "CLAS", "PROP", "STRG", "TRAN", "IMPR", "EXPR"]
    nb = ndfbin.NdfBin(sections=list(sections), section_layout=list(sections))
    c = nb.intern_class(cls)
    nb.objects.append(ndfbin.Obj(c, [(nb.intern_prop(n, c), v) for n, v in props.items()]))
    nb.topo, nb.chnk, nb.exports = [0], [(0, 1)], ndfbin.Node(nb.intern_tran("Thing"), 0)
    return ndfbin.encode_file(nb, mode)


class Local(unittest.TestCase):
    """A table, an extraction and a game folder of our own, in a temporary folder."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.extracted, self.data, game = (self.root / n for n in ("extracted", "data", "game"))
        for folder in (self.extracted, self.data, game):
            folder.mkdir()
        env = mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": str(self.extracted), "MODKIT_DATA": str(self.data),
                                           "MODKIT_GAME_DIR": str(game)})  # no WARNO.exe: nothing to compare
        env.start()
        self.addCleanup(env.stop)
        ndfrules.write_table(list(STRESS.values())[0], "WARNO.exe 16 bytes; test")

    def run_main(self, *args) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            code = ndfrules.main(list(args))
        return code, out.getvalue()


class CheckFile(Local):
    def test_reads_every_compression_mode(self):
        """The gate reads a generated file through ndfbin.decode, whatever its compression."""
        for mode in (ndfbin.MODE_NONE, ndfbin.MODE_LZ4, ndfbin.MODE_ZSTD, ndfbin.MODE_ZLIB):
            with self.subTest(mode=mode):
                self.assertEqual(ndfrules.check_file(small_file(mode=mode), "x"), 1)
                bad = small_file("TGDDescriptorChangeStress", mode, DamageType=Value(0x02, 0), Group=SELF)
                with self.assertRaisesRegex(CheckError, "'DamageType' must be defined"):
                    ndfrules.check_file(bad, "x")

    def test_one_reader(self):
        """ndfrules has no decompress-and-parse of its own: ndfbin.decode is the one reader of a whole file."""
        self.assertFalse(hasattr(ndfrules, "_image"))


class Verify(Local):
    def test_no_stock_file_read_fails(self):
        code, out = self.run_main("verify")
        self.assertEqual(code, 1, out)
        self.assertIn("no stock NDF file was read", out)
        self.assertIn("setup extract", out)
        self.assertNotIn("Traceback", out)

    def test_only_unparseable_files_fails(self):
        (self.extracted / "junk.ndfbin").write_bytes(b"not an ndfbin")
        code, out = self.run_main("verify")
        self.assertEqual(code, 1, out)
        self.assertIn("no stock NDF file was read (1 skipped as unparseable)", out)

    def test_counts_the_files_it_skipped(self):
        (self.extracted / "a").mkdir()
        (self.extracted / "a" / "good.ndfbin").write_bytes(small_file())
        (self.extracted / "a" / "junk.ndfbin").write_bytes(b"not an ndfbin")
        (self.extracted / "older").mkdir()  # earlier game builds: neither read nor skipped
        (self.extracted / "older" / "old.ndfbin").write_bytes(b"not an ndfbin")
        code, out = self.run_main("verify")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines()[-1], "1 stock files (1 objects), 1 skipped as unparseable, 0 violations")

    def test_reads_txn_and_leaves_out_what_the_game_no_longer_loads(self):
        """Build 210942 ships compiled NDF as .txn; an entry declared corpus=False (an earlier build's copy kept for
        a reader) is neither read nor counted as skipped."""
        from modkit.core import setup
        from modkit.core.stock import Stock
        (self.extracted / "new").mkdir()
        (self.extracted / "new" / "Thing.txn").write_bytes(small_file())
        (self.extracted / "new" / "Thing.txn.tag").write_bytes(b"not an ndfbin")  # not compiled NDF: not read
        (self.extracted / "copy" / "NDF").mkdir(parents=True)
        (self.extracted / "copy" / "NDF" / "Thing.ndfbin").write_bytes(b"not an ndfbin")
        declared = [Stock("copy", packs=("Old",), corpus=False), Stock("new", packs=("New",))]
        with mock.patch.object(setup, "declared", return_value=declared):
            code, out = self.run_main("verify")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines()[-1], "1 stock files (1 objects), 0 skipped as unparseable, 0 violations")

    def test_violations_still_fail(self):
        (self.extracted / "bad.ndfbin").write_bytes(
            small_file("TGDDescriptorChangeStress", DamageType=Value(0x02, 0), Group=SELF))
        code, out = self.run_main("verify")
        self.assertEqual(code, 1, out)
        self.assertTrue(out.splitlines()[-1].endswith(", 0 skipped as unparseable, 1 violations"), out)


@paths.skip_unless_data("ndfrules.tsv")
class Table(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rules, cls.size = ndfrules.load_table()

    def test_change_stress_rows(self):
        """The rows behind the fatal 'DamageType must be defined' load error, both in one validate."""
        rows = self.rules["TGDDescriptorChangeStress"]
        self.assertEqual({(r.kind, r.prop) for r in rows}, {("defined", "DamageType"), ("defined", "Group")})
        self.assertEqual(len({r.validate for r in rows}), 1)

    def test_reviewed_rows_exist(self):
        """Every REVIEWED entry still names a row: a re-extract that drops or renames it must not leave it stale."""
        keys = {(r.cls, r.kind, r.prop or r.detail) for rs in self.rules.values() for r in rs}
        self.assertEqual(set(ndfrules.REVIEWED) - keys, set())

    def test_reviewed_properties(self):
        """Every PROPERTIES class has rules; no reviewed property is one a rule names (that one the gate evaluates
        itself); and the class's evidence names every property its validate tests, so a re-extract that finds a new
        check makes the review stale here. ProductionUnites' rows are the ones its review was read against."""
        for cls, reviewed in ndfrules.PROPERTIES.items():
            with self.subTest(cls=cls):
                rows = self.rules.get(cls, [])
                self.assertTrue(rows)
                named = {r.prop for r in rows}
                for prop in reviewed:
                    self.assertNotIn(prop, named)
                self.assertTrue(any(all(p in evidence for p in named) for evidence in reviewed.values()),
                                (cls, sorted(named)))
        self.assertEqual({(r.kind, r.prop) for r in self.rules["TGDDescriptorProductionUnites"]},
                         {("defined", "Camp"), ("defined", "Position"), ("defined", "TypeUnit"),
                          ("ge", "ExperienceLevel"), ("ge", "NbUnit")})
        self.assertEqual(set(ndfrules.PROPERTIES["TGDDescriptorProductionUnites"]),
                         {"Group", "Transporter", "ProduceOutMap"})

    def test_exe_stamp(self):
        with tempfile.TemporaryDirectory() as d:
            exe = os.path.join(d, "WARNO.exe")
            with open(exe, "wb") as fh:
                fh.write(b"MZ" * 8)
            ndfrules.check_exe(16, exe)
            with self.assertRaisesRegex(CheckError, "re-run"):
                ndfrules.check_exe(self.size, exe)


@paths.skip_unless_extracted()
@paths.skip_unless_data("ndfrules.tsv")
class Stock(unittest.TestCase):
    def test_stock_passes(self):
        rules, _ = ndfrules.load_table()
        bad = []
        for nb in ndfrules.stock_files():
            bad += [f"{nb.path}: {v}" for v in ndfrules.violations(nb, rules, reviewed=None)][:3]
        self.assertEqual(bad, [])


@paths.skip_unless_game_dir("WARNO.exe")
class Exe(unittest.TestCase):
    def test_validate_slot_found_at_run_time(self):
        """The slot is read from the exe, not assumed: the routine it gives for ChangeStress holds the check behind
        the game's 'DamageType must be defined' load error."""
        x = ndfrules._Exe(str(ndfrules.exe_path()))
        helpers, _, _ = ndfrules.find_helpers(x)
        tabs = ndfrules.vtables(x)
        slot = ndfrules.validate_slot(x, helpers, tabs)
        fns = {(x.q(vt + 8 * slot) or 0) - x.pe.base for name, vt in tabs if name == "TGDDescriptorChangeStress"}
        found = {(kind, prop) for fn in fns for kind, prop, _, _ in ndfrules.checks_in(x, fn, helpers)}
        self.assertIn(("defined", "DamageType"), found)


if __name__ == "__main__":
    unittest.main()
