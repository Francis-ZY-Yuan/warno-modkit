"""The Operation build driver and its profile: the extension points, reviewed-pending gates, one process building two
profiles, and the command line.

The extension-point tests write synthetic items and need no stock data. The whole-build tests clone the stock
Survivors template onto Geisa, as the Open Door example does, and skip without an extraction.
"""
import contextlib
import dataclasses
import io
import os
import tempfile
import unittest
from unittest import mock

from modkit.core import edat, gamebuild, paths, trad
from modkit.core.gates import CheckError
from modkit.core.models import Texts
from modkit.core.ndfbin import Value
from modkit.ops import build as ops_build
from modkit.ops.graph import Node, Str, build_graph, decode, encode, loc
from modkit.ops.items import mem_item
from modkit.ops.leveldesign import LdItem, derived_menu_order, gd_tags, scenario_guid
from modkit.ops.items import read_provenance
from modkit.ops.profile import PACKS, SURVIVORS, Content, ExtraGate, ExtraPack, OpProfile, Sources
from modkit.ops.rekey import DBG, TXN, def_path, dump_rows
from modkit.ops.rekey import ScalarEdit
from modkit.ops.script import BRICK_FORCE_HIDE, hold_script
from modkit.ops.zones import playable_zone_graph, rect_polygon

GEISA = "_4x3_geisa"
GEISA_DETAILS = "geisa_op/_4x3_geisa_10vs10_CONQ_Details"
ZONE_INNER = ("out/DeploymentZone.ndfbin", "out/CommandZone.ndfbin")


def profile(namespace: str = "test-a", **kw) -> OpProfile:
    """Survivors on Geisa, the Open Door example's sources, under the GUID namespace `namespace`."""
    src = SURVIVORS.source
    values = dict(
        template=SURVIVORS, guid_namespace=namespace,
        map_strings={"_3x3_Railway": GEISA}, map_trans={"Railway": "Geisa"}, map_details=GEISA_DETAILS,
        map_copies=("out/PlayableZone.ndfbin", "out/IAStratZone.ndfbin", "out/IAStrat_PathCache.ndfbin",
                    "CamPaths_LevelDesign.ndfbin"),
        ground_z=49428.48828125,
        scalar_edits=(ScalarEdit("MapConfiguration", "TChallengeMapInfo", "Duration", Value(0x02, 3), Value(0x02, 1)),),
        deck_swap={},
        dictionaries=("SCENARIO_DEFINITION", "Scripting/Dialog", "Scripting/Localization"),
        asset_rules=((f"PC/Texture/{src}/MapPackAssets/Textures/*.tgv", "copy", "menu pictures"),
                     ("*", "drop", "not shipped")),
        import_rule="trie",
        shape_sources={"GDScript": ("scenarios/challenge_*/NDF/Scenarios/challenge_*/GDScript.txn",),
                       "out/LevelDesign.ndfbin": ("scenarios/challenge_*/out/LevelDesign.ndfbin",
                                                  "kreide_op/*/out/LevelDesign.ndfbin"),
                       **{inner: (f"scenarios/*/{inner}", f"kreide_op/*/{inner}") for inner in ZONE_INNER}},
        player_camp="joueur", enemy_camp="ordinateur_SOV", end_exports=(),
        build_root=tempfile.gettempdir(), dumps=True,
    )
    values.update(kw)
    return OpProfile(**values)


# Survivors' four camps, in CampList order: (export name, TGDVariableCamp scalars before PlayerName, deck).
CAMPS = (("joueur", (("AllianceStyle", 0x02, 3),), "OP_NORTH_SURV_PLAYER"),
         ("Allie", (("AllianceStyle", 0x02, 3),), "OP_NORTH_SURV_BEL"),
         ("ordinateur_DDR", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)),
          "OP_NORTH_SURV_DDR"),
         ("ordinateur_SOV", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)),
          "OP_NORTH_SURV_SOV"))
MENU = ("name", "order", "headr", "cname", "recap", "vic", "def")


def content(namespace: str = "test-a", scenario: str = "challenge_ModkitTest", mod_name: str = "ModkitTest",
            rules: tuple[tuple[str, Value], ...] = (), sources: Sources = Sources()) -> Content:
    """A tiny hold-a-point op: one place, one player tank, the template's four camps. `rules` are extra game-rules
    fields, to break the rules gate on purpose. `namespace` must be the profile's (the tags carry item GUIDs)."""
    items = (LdItem("Tags", "T_Hold", 1000000.0, 1000000.0, "Name"),
             LdItem("Camp_0", "T_Tank", 1000000.0, 1000000.0, "Spawn", unit="M1A1HA_Abrams_US"))

    def script(tpl):
        camps = [Node("TGDVariableCamp", [*((p, Value(tag, v)) for p, tag, v in scalars),
                                          ("PlayerName", loc(f"t_c{k}"))], export=f"$/GDScript/RootDescriptor/{name}")
                 for k, (name, scalars, _) in enumerate(CAMPS)]
        setup = [Node("TGDDescriptorSetDeck", [("Camp", camp), ("DeckIdentifier", Str(deck))])
                 for camp, (_, _, deck) in zip(camps, CAMPS)]
        tags = gd_tags(items, scenario, namespace)
        roots, exports = hold_script(tpl, SURVIVORS.objects, folder="$/GDScript/T", camps=camps, setup=setup,
                                     tags=tags, player_tags=[tags["Camp_0/T_Tank"]], hold_at=tags["Tags/T_Hold"],
                                     hold_s=600, intro="t_intro", objective=("t_obj", "t_objl"), start_delay_s=1.0,
                                     parallel=[], variables=[], prod_menu_switch=BRICK_FORCE_HIDE)
        if rules:  # after Fow, before the rest: stock's order (HoldUntilRelieved's rules)
            root = next(nd for nd in exports if nd.export == "$/GDScript/RootDescriptor")
            props = dict(root.props)["GameRules"].props
            at = next(k for k, (name, _) in enumerate(props) if name == "Fow") + 1
            props[at:at] = list(rules)
        return roots, exports

    strings = {"SCENARIO_DEFINITION": {f"t_{m}": Texts(US="Modkit test", SC="Modkit test") for m in MENU},
               "Scripting/Dialog": {"t_intro": Texts(US="Hold the place.", SC="Hold the place.")},
               "Scripting/Localization": {"t_obj": Texts(US="HOLD", SC="HOLD"),
                                          "t_objl": Texts(US="Hold for %1", SC="Hold %1"),
                                          **{f"t_c{k}": Texts(US=f"Side {k}", SC=f"Side {k}") for k in range(4)}}}
    return Content("tiny", items, script, strings, tuple(f"t_{m}" for m in MENU), scenario=scenario,
                   mod_name=mod_name, menu_renames=tuple((f"op13_{m}", f"t_{m}") for m in MENU), sources=sources)


def quiet(fn, *args):
    """fn(*args) with its report captured; returns (result, report)."""
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        result = fn(*args)
    return result, out.getvalue()


def tree(root: str) -> dict[str, bytes]:
    out = {}
    for folder, _, files in os.walk(root):
        for name in files:
            path = os.path.join(folder, name)
            with open(path, "rb") as fh:
                out[os.path.relpath(path, root).replace(os.sep, "/")] = fh.read()
    return out


def synthetic(profile_: OpProfile, content_: Content) -> ops_build.Plan:
    """A plan of synthetic items in the core packs plus the profile's extra items."""
    items = [mem_item("Definition", def_path("MapConfiguration", TXN, content_.scenario), b"def", "generate", "test"),
             mem_item("Details", "out/LevelDesign.ndfbin", b"ld", "generate", "test"),
             mem_item("Assets", f"Localisation/{content_.scenario}/X-US.dic", b"dic", "generate", "test")]
    return ops_build.Plan(items + ops_build.extra_items(profile_, content_), [("TrophyDef.txn", "dropped")], [])


class ExtensionPointsTest(unittest.TestCase):
    """What a private mod adds to a build, through the profile: packs, loose files, Config.ini and manifest rows."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.addCleanup(self.tmp.cleanup)
        self.content = Content("x", (), lambda tpl: ([], []), {}, (), scenario="challenge_X", mod_name="ModX",
                               menu_renames=())

    def write(self, prof: OpProfile) -> dict[str, bytes]:
        quiet(ops_build.write, prof, self.content, synthetic(prof, self.content), self.tmp.name)
        return tree(self.tmp.name)

    def test_extension_points_add_pack_and_loose_file(self):
        extra = mem_item("Extra", "Data/x.bin", b"extra payload", "copy", "test extra")
        video = mem_item("Loose", "Video/intro.webm", b"video bytes", "copy", "test video")
        prof = profile(build_root=self.tmp.name, dumps=False,
                       extra_packs=(ExtraPack("Extra", lambda c: [extra]),),
                       extra_loose_files=(lambda c: [video],))
        files = self.write(prof)
        self.assertEqual(sorted(files), ["MANIFEST.tsv", "ModX/Config.ini", "ModX/Gen/Version.ndf",
                                         "ModX/Scenarios/challenge_X_Assets.dat",
                                         "ModX/Scenarios/challenge_X_Definition.dat",
                                         "ModX/Scenarios/challenge_X_Details.dat",
                                         "ModX/Scenarios/challenge_X_Extra.dat", "ModX/Video/intro.webm"])
        pack = os.path.join(self.tmp.name, "ModX", "Scenarios", "challenge_X_Extra.dat")
        self.assertEqual([(e.path, edat.read_entry(pack, e)) for e in edat.read_index(pack)],
                         [("Data/x.bin", b"extra payload")])
        self.assertEqual(files["ModX/Video/intro.webm"], b"video bytes")
        rows = [line.split("\t")[:2] for line in files["MANIFEST.tsv"].decode().splitlines()[1:]]
        self.assertEqual([r[0] for r in rows], ["Definition", "Details", "Assets", "Extra", "Loose", "-"])

    def test_extra_items_keep_to_their_pack(self):
        stray = mem_item("Assets", "Data/x.bin", b"x", "copy", "test")
        with self.assertRaisesRegex(CheckError, "extra pack Extra planned an item for pack Assets"):
            ops_build.extra_items(profile(extra_packs=(ExtraPack("Extra", lambda c: [stray]),)), self.content)
        with self.assertRaisesRegex(CheckError, "loose files planned an item for pack Assets"):
            ops_build.extra_items(profile(extra_loose_files=(lambda c: [stray],)), self.content)

    def test_extra_config_rows(self):
        prof = profile(build_root=self.tmp.name, dumps=False, mod_id=4242,
                       extra_config_rows=("Extra = 1",), extra_manifest_rows=(("OtherMod", "requires", "test"),))
        files = self.write(prof)
        config = files["ModX/Config.ini"].decode("ascii")
        self.assertIn("ID = 4242", config)
        self.assertIn("\nExtra = 1\n", config)
        manifest = files["MANIFEST.tsv"].decode().splitlines()
        self.assertIn("-\tOtherMod\t\trequires\ttest", manifest)
        self.assertEqual(manifest[-1], "-\tTrophyDef.txn\t\tdrop\tdropped")

    def test_the_profile_refuses_a_bad_workshop_id(self):
        for bad in (-1, 2 ** 64, "7"):
            with self.subTest(bad=bad), self.assertRaisesRegex(CheckError, "Workshop ID"):
                profile(mod_id=bad)

    def test_no_extension_points_write_the_template_config(self):
        files = self.write(profile(build_root=self.tmp.name, dumps=False))
        self.assertIn("ID = 0", files["ModX/Config.ini"].decode("ascii"))
        self.assertNotIn("requires", files["MANIFEST.tsv"].decode())

    def test_extra_items_go_into_a_core_pack(self):
        """A file the profile adds to one of its own packs (a video descriptor in Assets, say)."""
        vid = mem_item("Assets", "PC/Video/challenge_X/intro.vid", b"descriptor", "copy", "test video")
        files = self.write(profile(build_root=self.tmp.name, dumps=False, extra_items=(lambda c: [vid],)))
        pack = os.path.join(self.tmp.name, "ModX", "Scenarios", "challenge_X_Assets.dat")
        self.assertEqual(sorted(e.path for e in edat.read_index(pack)),
                         ["Localisation/challenge_X/X-US.dic", "PC/Video/challenge_X/intro.vid"])
        self.assertIn("Assets\tPC/Video/challenge_X/intro.vid\t10\tcopy\ttest video", files["MANIFEST.tsv"].decode())
        stray = mem_item("Extra", "Data/x.bin", b"x", "copy", "test")
        with self.assertRaisesRegex(CheckError, "extra items planned an item for pack Extra, not one of the profile's"):
            ops_build.extra_items(profile(extra_items=(lambda c: [stray],)), self.content)

    def test_an_extra_pack_names_a_new_pack(self):
        """An extra pack named after a core pack would write that .dat twice."""
        with self.assertRaisesRegex(CheckError, "pack names repeat: .*'Assets'.*an extra pack must name a new pack"):
            ops_build.extra_items(profile(extra_packs=(ExtraPack("Assets", lambda c: []),)), self.content)

    def test_a_pending_entry_that_does_not_fire_is_listed(self):
        """Several messages per gate (a gate run once per file), and the entries a run never met."""
        def gate(n):
            if n < 0:
                raise CheckError(f"file {n} fails")
            return n
        run = ops_build.GateRun(profile(reviewed_pending={"files": ("file -1 fails", "file -2 fails"), "x": ("y",)}))
        results = [quiet(run, "files", gate, n)[0] for n in (-1, 3)]
        self.assertEqual(results, [ops_build.PENDING, 3])
        self.assertEqual(run.unfired(), [("files", "file -2 fails"), ("x", "y")])

    def test_a_generated_file_needs_its_shape_sources(self):
        """An extra item with a fixture is a generated ndfbin, so gate 2 holds it to stock shapes: the profile must name
        the stock files of its kind, and says so when it does not."""
        raw = encode(build_graph(playable_zone_graph(list(rect_polygon((0, 0, 10, 10))), (5.0, 5.0, 0.0)), []), "PZ")
        zone = mem_item("Details", "out/PlayableZone.ndfbin", raw, "generate", "test", fixture="PlayableZone.txt")
        with self.assertRaisesRegex(CheckError, r"out/PlayableZone.ndfbin is generated \(it has a fixture\), but the "
                                                r"profile names no stock files for its shapes \(shape_sources\)"):
            quiet(ops_build.check_generated, profile(), content(), [zone])

    def test_extra_gate_reviewed_pending_reports_not_raises(self):
        def gate(items, content_):
            raise CheckError("known fault")
        prof = profile(extra_gates=(ExtraGate("custom", gate),), reviewed_pending={"custom": ("known fault",)})
        result, report = quiet(ops_build.run_extra_gates, prof, [], self.content)
        self.assertEqual(result, ["custom: review pending"])
        self.assertIn("REVIEW PENDING: custom: known fault", report)
        with self.assertRaisesRegex(CheckError, "known fault"):
            ops_build.run_extra_gates(profile(extra_gates=(ExtraGate("custom", gate),)), [], self.content)


@paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
class WholeBuildTest(unittest.TestCase):
    """Whole builds of the tiny op from the stock template."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.addCleanup(self.tmp.cleanup)

    def out(self, name: str) -> str:
        return os.path.join(self.tmp.name, name)

    def test_reviewed_pending_reports_not_raises(self):
        broken = content(rules=(("CheckEndGame", Value(0x00, 1)),))
        with self.assertRaises(CheckError) as cm:
            quiet(ops_build.build, profile(build_root=self.tmp.name), broken, self.out("a"))
        message = str(cm.exception)
        self.assertIn("CheckEndGame", message)
        prof = profile(build_root=self.tmp.name, reviewed_pending={"rules": (message,), "package": ("never seen",)})
        items, report = quiet(ops_build.build, prof, broken, self.out("b"))
        self.assertIn(f"REVIEW PENDING: rules: {message}", report)
        self.assertIn("REVIEW PENDING, did not fire: package: never seen", report)
        self.assertNotIn("did not fire: rules", report)
        self.assertTrue(items)
        self.assertTrue(os.path.isfile(os.path.join(self.out("b"), "ModkitTest", "Config.ini")))
        other = profile(build_root=self.tmp.name, reviewed_pending={"rules": (message + " (another)",)})
        with self.assertRaises(CheckError):
            quiet(ops_build.build, other, broken, self.out("c"))

    def test_a_gameplay_file_fails_gate_5(self):
        """A loose Gen/<scenario>/GFX/Unit.txn lies under the scenario, but the game tags the mod Gameplay by it:
        gate 5 fails before anything is written. The same build without it passes gate 5."""
        unit = mem_item("Loose", "Gen/challenge_ModkitTest/GFX/Unit.txn", b"unit", "copy", "test")
        bad = profile(build_root=self.tmp.name, extra_loose_files=(lambda c: [unit],))
        with self.assertRaisesRegex(CheckError, r"^Loose:Gen/challenge_ModkitTest/GFX/Unit.txn: a Gameplay file"):
            quiet(ops_build.build, bad, content(), self.out("bad"))
        self.assertFalse(os.path.exists(self.out("bad")))
        _, report = quiet(ops_build.build, profile(build_root=self.tmp.name), content(), self.out("ok"))
        self.assertRegex(report, r"gate 5 package: all \d+ entries lie under challenge_ModkitTest; no Gameplay file")
        # 4 kinds: GDScript (generated), MapConfiguration, ScenarioInfo and ScenarioLoader (re-keyed); TrophyDef dropped
        self.assertRegex(report, r"gate 5 definition: 4 kinds in NDF/Scenarios/challenge_ModkitTest/, each \.txn with "
                                 r"its \.txn\.tag and a \.dbg of one line per object; 4 tags with the ConfigHash the "
                                 r"game computes; every class and property of \d+ "
                                 r"files \(\d+ objects\) is in the \d+ stock files'\n")

    def test_a_pending_gate_5_does_not_claim_a_pass(self):
        """With the Gameplay failure reviewed-pending, the build goes on, but its gate 5 line says the gate is pending,
        not that the package holds no Gameplay file."""
        unit = mem_item("Loose", "Gen/challenge_ModkitTest/GFX/Unit.txn", b"unit", "copy", "test")
        bad = profile(build_root=self.tmp.name, extra_loose_files=(lambda c: [unit],))
        with self.assertRaises(CheckError) as cm:
            quiet(ops_build.build, bad, content(), self.out("bad"))
        pending = profile(build_root=self.tmp.name, extra_loose_files=(lambda c: [unit],),
                          reviewed_pending={"package": (str(cm.exception),)})
        _, report = quiet(ops_build.build, pending, content(), self.out("pending"))
        self.assertIn(f"REVIEW PENDING: package: {cm.exception}", report)
        self.assertIn("gate 5 package: review pending\n", report)
        self.assertNotIn("no Gameplay file", report)

    def test_profile_has_no_module_globals(self):
        """Two profiles in one process: each output depends on its own profile only, and the first builds the same
        after the second."""
        a1, _ = quiet(ops_build.build, profile("test-a", build_root=self.tmp.name), content("test-a"), self.out("a1"))
        quiet(ops_build.build, profile("test-b", build_root=self.tmp.name, mod_id=7), content("test-b"), self.out("b"))
        quiet(ops_build.build, profile("test-a", build_root=self.tmp.name), content("test-a"), self.out("a2"))
        first, second, again = tree(self.out("a1")), tree(self.out("b")), tree(self.out("a2"))
        self.assertEqual(first, again)
        self.assertEqual(sorted(first), sorted(second))
        differ = sorted(k for k in first if first[k] != second[k])  # the manifest: compressed sizes follow the GUIDs
        self.assertEqual(differ, ["MANIFEST.tsv", "ModkitTest/Config.ini",
                                  "ModkitTest/Scenarios/challenge_ModkitTest_Definition.dat",
                                  "ModkitTest/Scenarios/challenge_ModkitTest_Details.dat",
                                  "dumps/GDScript.txt", "dumps/LevelDesign.txt"])
        self.assertIn(b"ID = 7", second["ModkitTest/Config.ini"])
        guid_a, guid_b = (scenario_guid("challenge_ModkitTest", ns) for ns in ("test-a", "test-b"))
        image_a, image_b = (self.map_configuration(self.out(name)) for name in ("a1", "b"))
        self.assertEqual((guid_a in image_a, guid_b in image_b, guid_a in image_b), (True, True, False))
        self.assertTrue(a1)

    @staticmethod
    def map_configuration(out: str) -> bytes:
        """The decoded MapConfiguration of a build, which holds the scenario GUID."""
        pack = os.path.join(out, "ModkitTest", "Scenarios", "challenge_ModkitTest_Definition.dat")
        entry = next(e for e in edat.read_index(pack)
                     if e.path == def_path("MapConfiguration", TXN, "challenge_ModkitTest"))
        return decode(edat.read_entry(pack, entry))[2]


@paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
class SourcesAndTemplateTest(unittest.TestCase):
    """What the content and the profile decide about the generated files: their names, or whether there are any."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=tempfile.gettempdir())
        self.addCleanup(self.tmp.cleanup)

    def test_sources_name_the_generated_files(self):
        sources = Sources(labels={"GDScript": "generated (test script)", "out/LevelDesign.ndfbin": "generated (test)"},
                          fixtures={"GDScript": "Script_test.txt"}, dictionary="TABLE[{name!r}] {lang}")
        out = os.path.join(self.tmp.name, "a")
        quiet(ops_build.build, profile(build_root=self.tmp.name), content(sources=sources), out)
        with open(os.path.join(out, "MANIFEST.tsv"), encoding="utf-8") as fh:
            rows = {tuple(line.split("\t")[1:2] + line.split("\t")[4:5]) for line in fh.read().splitlines()[1:]}
        for row in ((def_path("GDScript", TXN, "challenge_ModkitTest"), "generated (test script)"),
                    (def_path("GDScript", DBG, "challenge_ModkitTest"), "generated (test script): its source map"),
                    ("out/LevelDesign.ndfbin", "generated (test)"),
                    ("Localisation/challenge_ModkitTest/Scripting/Dialog-SC.dic", "TABLE['Scripting/Dialog'] SC")):
            self.assertIn(row, rows)
        self.assertEqual(sorted(os.listdir(os.path.join(out, "dumps"))), ["LevelDesign.txt", "Script_test.txt"])

    def test_template_script_and_details(self):
        """Content.script None ships the template's GDScript re-keyed, and details_from_template its Details whole:
        nothing is generated, and the script gates read the shipped script decoded."""
        src = SURVIVORS.source
        prof = profile(build_root=self.tmp.name, details_from_template=True, map_strings={}, map_trans={},
                       dictionaries=("SCENARIO_DEFINITION",),
                       asset_rules=((f"Localisation/{src}/SCENARIO_DEFINITION-*.dic", "drop", "generated"),
                                    (f"Localisation/{src}/Scripting/*.dic", "copy", "the template's texts"),
                                    ("*", "drop", "not shipped")))
        tiny = content()
        bare = Content("bare", (), None, {"SCENARIO_DEFINITION": tiny.strings["SCENARIO_DEFINITION"]},
                       tiny.menu_tokens, scenario=tiny.scenario, mod_name=tiny.mod_name, menu_renames=tiny.menu_renames)
        p = ops_build.plan(prof, bare)
        self.assertEqual([it for it in p.items if it.fixture is not None], [])
        gd = next(it for it in p.items if it.path == def_path("GDScript", TXN, tiny.scenario))
        self.assertEqual((gd.action, gd.stock is not None), ("rekey", True))
        self.assertEqual(sorted(it.path for it in p.items if it.pack == "Details"),
                         sorted(dict(read_provenance(SURVIVORS.path("details")))))
        self.assertTrue(any(nd.export == "$/GDScript/RootDescriptor" for nd in p.roots))
        with self.assertRaisesRegex(CheckError, "1 LevelDesign items, but the profile ships the template's Details"):
            ops_build.plan(prof, Content("x", tiny.items[:1], None, bare.strings, (), scenario=tiny.scenario,
                                         mod_name=tiny.mod_name, menu_renames=tiny.menu_renames))


class CliTest(unittest.TestCase):
    """The shared front end: `--content NAME --out DIR`; a failure exits 1 with one line, never a traceback."""

    def run_cli(self, factory, contents, argv):
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = ops_build.cli(factory, contents, argv)
        return code, err.getvalue()

    def test_not_configured_exits_1_with_its_message(self):
        def factory():
            raise paths.NotConfigured("The stock extraction folder is not configured: run the warno-setup skill")
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self.run_cli(factory, {"x": lambda: None}, ["--content", "x", "--out", tmp])
        self.assertEqual(code, 1)
        self.assertIn("warno-setup", err)
        self.assertNotIn("Traceback", err)

    def test_not_configured_in_the_content_exits_1(self):
        def make():
            raise paths.NotConfigured("not configured: run the warno-setup skill")
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self.run_cli(profile, {"x": make}, ["--content", "x", "--out", tmp])
        self.assertEqual((code, "warno-setup" in err, "Traceback" in err), (1, True, False))

    def test_a_failed_gate_exits_1(self):
        def make():
            raise CheckError("a gate failed")
        with tempfile.TemporaryDirectory() as tmp:
            code, err = self.run_cli(profile, {"x": make}, ["--content", "x", "--out", tmp])
        self.assertEqual(code, 1)
        self.assertIn("FAILED: a gate failed", err)

    def test_run_turns_a_failure_into_exit_1(self):
        """run() is the driver under any front end (one with other flags than --content and --out)."""
        def make():
            raise paths.NotConfigured("not configured: run the warno-setup skill")
        err = io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, contextlib.redirect_stderr(err):
            self.assertEqual(ops_build.run(profile, make, tmp), 1)
        self.assertEqual(err.getvalue(), "FAILED: not configured: run the warno-setup skill\n")

    def test_a_missing_stock_file_exits_1_naming_setup(self):
        """An extraction without a declared stock file (made before a component declared it, say): one FAILED line
        naming the file and the setup commands that fetch it, never a raw OS error. (The game-build warning an
        unverified install adds is test_build_warning's: held off here, whatever build is installed.)"""
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": tmp}), \
                mock.patch.object(gamebuild, "build_warning", return_value=None):
            os.makedirs(os.path.join(tmp, "scenarios"))   # gate 1 finds both languages' sets; no template
            for lang in ("SC", "US"):
                with open(os.path.join(tmp, "scenarios", f"X-{lang}.dic"), "wb") as fh:
                    fh.write(trad.build_dic({"t_x": "x"}))
            code, err = self.run_cli(profile, {"tiny": content}, ["--content", "tiny", "--out",
                                                                  os.path.join(tmp, "out")])
            self.assertFalse(os.path.exists(os.path.join(tmp, "out")))
        self.assertEqual(code, 1)
        (line,) = err.splitlines()
        self.assertTrue(line.startswith("FAILED: missing stock file extracted/kreide_op/challenge_Survivors_Definition/"),
                        line)
        self.assertTrue(line.endswith("run python -m modkit.core.setup check, then python -m modkit.core.setup extract "
                                      "(the warno-setup skill)"), line)

    def test_packs_other_than_the_three_fail_before_planning(self):
        """OpProfile.packs is always the three packs, in order: anything else fails when the profile is made, so the
        build prints one FAILED line and writes nothing (a dropped pack left its items planned but unwritten)."""
        self.assertEqual(profile().packs, PACKS)
        self.assertEqual(PACKS, ("Definition", "Details", "Assets"))
        for packs in (("Definition", "Details"), ("Definition", "Assets", "Details"), (*PACKS, "Extra")):
            with self.subTest(packs=packs), self.assertRaisesRegex(
                    CheckError, r"OpProfile.packs is .*, but a build always plans and writes the packs "
                                r"\['Definition', 'Details', 'Assets'\], in that order"):
                profile(packs=packs)
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            code, err = self.run_cli(lambda: profile(packs=("Definition", "Details")), {"tiny": content},
                                     ["--content", "tiny", "--out", out])
            self.assertFalse(os.path.exists(out))
        self.assertEqual(code, 1)
        (line,) = err.splitlines()
        self.assertTrue(line.startswith("FAILED: OpProfile.packs is ['Definition', 'Details']"), line)

    def test_out_is_required_without_a_default(self):
        with self.assertRaises(SystemExit):
            self.run_cli(profile, {"x": lambda: None}, ["--content", "x"])

    def test_an_unresolvable_default_out_exits_1(self):
        """No --out and no build folder to default to: cli itself prints run's one FAILED line and gives 1, so a front
        end needs no catch of its own. Nothing else runs."""
        made = []

        def default_out(name):
            raise paths.NotConfigured("The build folder is not configured: run the warno-setup skill")
        err = io.StringIO()
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            code = ops_build.cli(lambda: made.append("profile"), {"x": lambda: made.append("content")},
                                 ["--content", "x"], default_out=default_out)
        self.assertEqual(code, 1)
        self.assertEqual(err.getvalue(), "FAILED: The build folder is not configured: run the warno-setup skill\n")
        self.assertEqual(made, [])


class SourcesTest(unittest.TestCase):
    def test_a_name_left_out_gets_the_drivers_wording(self):
        src = Sources()
        self.assertEqual((src.label("GDScript"), src.label("out/LevelDesign.ndfbin"), src.label("out/CommandZone.ndfbin")),
                         ("generated (content script)", "generated (content items)", "generated (content zone items)"))
        self.assertEqual(src.fixture("out/CommandZone.ndfbin"), "CommandZone.txt")

    def test_a_name_given_is_kept_even_empty(self):
        src = Sources(labels={"GDScript": ""}, fixtures={"GDScript": ""})
        self.assertEqual((src.label("GDScript"), src.fixture("GDScript")), ("", ""))


class DefaultMenuOrderTest(unittest.TestCase):
    """A content whose scalar edits move no menu order gets its derived order (ops_build.scalar_edits); one that moves
    it keeps its own, so the frozen examples' 1001 is untouched."""

    ORDER = ScalarEdit("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission", Value(0x03, 130),
                       Value(0x03, 1001))

    def test_none_set_takes_the_derived_order(self):
        edits = ops_build.scalar_edits(profile(), content())
        derived = derived_menu_order("challenge_ModkitTest", "test-a")
        self.assertEqual(edits, (*profile().scalar_edits, ScalarEdit("MapConfiguration", "TChallengeMapInfo",
                                                                     "OrderToChainMission", Value(0x03, 130),
                                                                     Value(0x03, derived))))
        self.assertEqual(ops_build.rekey_table(profile(), content()).scalar_edits, edits)
        self.assertIn(f"OrderToChainMission 130 -> {derived}",
                      [r.label for r in dump_rows(ops_build.rekey_table(profile(), content()))])

    def test_a_set_order_is_kept(self):
        """The profile's, or the content's own (which replace the profile's), each kept as it is."""
        own = profile(scalar_edits=(self.ORDER,))
        self.assertEqual(ops_build.scalar_edits(own, content()), (self.ORDER,))
        mine = dataclasses.replace(content(), scalar_edits=(self.ORDER,))
        self.assertEqual(ops_build.scalar_edits(profile(), mine), (self.ORDER,))

    def test_no_default_without_the_templates_order(self):
        bare = profile(template=dataclasses.replace(SURVIVORS, menu_order=None))
        self.assertEqual(ops_build.scalar_edits(bare, content()), bare.scalar_edits)
        self.assertEqual(SURVIVORS.menu_order, 130)


class ScenarioGuidTest(unittest.TestCase):
    def test_one_formula_under_a_namespace(self):
        import uuid
        self.assertEqual(scenario_guid("challenge_X", "ns"), uuid.uuid5(uuid.NAMESPACE_URL, "ns/challenge_X").bytes)
        self.assertNotEqual(scenario_guid("challenge_X", "ns"), scenario_guid("challenge_X", "other"))


if __name__ == "__main__":
    unittest.main()
