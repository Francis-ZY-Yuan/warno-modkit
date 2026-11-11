"""Tests for modkit.core.packaging: the files every mod ships, the Gameplay file list, writing a mod folder."""
import glob
import os
import tempfile
import unittest
from unittest import mock

from modkit.core import ndfbin, packaging, paths
from modkit.core.gates import CheckError


class ConstantsTest(unittest.TestCase):
    def test_config_ini(self):
        text = packaging.CONFIG_INI.format(name="MyOp")
        self.assertTrue(text.startswith("[Properties]\nName = MyOp\n"))
        self.assertTrue(text.endswith("[Config] ; Used for mod compatibility check, do not modify\n"))
        self.assertNotIn("\r", text)
        self.assertIn("\nDescription = \n", text)  # empty values keep the space after '='
        self.assertIn("\nModGenVersion = 201602 ;", text)

    def test_version_ndf(self):
        self.assertEqual(packaging.VERSION_NDF, b"version is '201602'\n")

    def test_gameplay_files(self):
        self.assertEqual(len(packaging.GAMEPLAY_FILES), 16)
        self.assertEqual(len(set(packaging.GAMEPLAY_FILES)), 16)
        self.assertIn("GFX/Unit.ndfbin", packaging.GAMEPLAY_FILES)
        self.assertTrue(all(f.endswith(".ndfbin") for f in packaging.GAMEPLAY_FILES))

    def test_is_gameplay_file(self):
        """Under Gen/ and ending with one of the 16, as the game's lookup tests a mod's files."""
        for rel in ("Gen/NDF/GFX/Unit.ndfbin", "Gen/challenge_X/GFX/Unit.ndfbin",
                    "Gen/InitialisationGameDistanceUnits.ndfbin"):
            self.assertTrue(packaging.is_gameplay_file(rel), rel)
        for rel in ("GFX/Unit.ndfbin", "Scenarios/Gen/GFX/Unit.ndfbin", "Gen/NDF/GFX/MyUnit.ndfbin", "Gen/Version.ndf"):
            self.assertFalse(packaging.is_gameplay_file(rel), rel)

    def test_is_gameplay_file_ignores_case(self):
        """The game reads a mod's files through Windows paths, where case names no other file: any spelling counts."""
        for rel in ("gen/NDF/GFX/Unit.ndfbin", "GEN/ndf/gfx/unit.NDFBIN", "Gen/x/initialisationgamedistanceunits.ndfbin"):
            self.assertTrue(packaging.is_gameplay_file(rel), rel)
        for rel in ("gfx/unit.ndfbin", "Gen/NDF/GFX/myunit.ndfbin", "GEN/Version.ndf"):
            self.assertFalse(packaging.is_gameplay_file(rel), rel)


class Entry:
    def __init__(self, pack: str, path: str, size: int, action: str = "copy", source: str = "src"):
        self.pack, self.path, self.size, self.action, self.source = pack, path, size, action, source


class WriteTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, *rel: str) -> bytes:
        with open(os.path.join(self.root, *rel), "rb") as fh:
            return fh.read()

    def test_config_ini_defaults_to_the_template(self):
        self.assertEqual(packaging.config_ini("MyOp", mod_id=0, extra_config_rows=()),
                         packaging.CONFIG_INI.format(name="MyOp"))

    def test_config_ini_id_and_rows(self):
        text = packaging.config_ini("MyOp", mod_id=900000001, extra_config_rows=["GFX/Unit=abc"])
        self.assertIn("\nID = 900000001 ; Mod Steam ID", text)
        self.assertNotIn("\nID = 0 ;", text)
        self.assertTrue(text.endswith("do not modify\nGFX/Unit=abc\n"), text[-60:])

    def test_config_ini_checks_the_template(self):
        for template in (packaging.CONFIG_INI.replace("ID = 0 ;", "ID = 1 ;"),
                         packaging.CONFIG_INI.replace(packaging.CONFIG_HEADER, "[Other]")):
            with self.subTest(template=template[-40:]), \
                    mock.patch.object(packaging, "CONFIG_INI", template), \
                    self.assertRaisesRegex(CheckError, "template changed"):
                packaging.config_ini("MyOp", mod_id=0, extra_config_rows=())

    def test_write_mod_files(self):
        mod = os.path.join(self.root, "MyOp")
        os.makedirs(mod)
        packaging.write_mod_files(mod, "MyOp", mod_id=0, extra_config_rows=())
        self.assertEqual(self.read("MyOp", "Config.ini"), packaging.CONFIG_INI.format(name="MyOp").encode("ascii"))
        self.assertEqual(self.read("MyOp", "Gen", "Version.ndf"), packaging.VERSION_NDF)

    def test_write_manifest(self):
        entries = [Entry("Loose", "v.webm", 3), Entry("Assets", "b", 2), Entry("Definition", "z", 1),
                   Entry("Definition", "a", 4, "rekey", "extracted/x")]
        path = packaging.write_manifest(entries, [("old.ogg", "not referenced")], self.root,
                                        packs=("Definition", "Assets"),
                                        extra_manifest_rows=[("OtherMod", "requires", "its builder")])
        self.assertEqual(path, os.path.join(self.root, "MANIFEST.tsv"))
        self.assertEqual(self.read("MANIFEST.tsv").decode("utf-8").split("\n"), [
            "pack\tinner_path\tbytes\taction\tsource", "Definition\ta\t4\trekey\textracted/x",
            "Definition\tz\t1\tcopy\tsrc", "Assets\tb\t2\tcopy\tsrc", "Loose\tv.webm\t3\tcopy\tsrc",
            "-\tOtherMod\t\trequires\tits builder", "-\told.ogg\t\tdrop\tnot referenced", ""])

    def test_clean_out(self):
        build = os.path.join(self.root, "build")
        for name in ("MyOp", "dumps", "keep"):
            os.makedirs(os.path.join(build, "out", name))
        packaging.clean_out(os.path.join(build, "out"), ("MyOp", "dumps", "absent"), build)
        self.assertEqual(os.listdir(os.path.join(build, "out")), ["keep"])
        os.makedirs(os.path.join(self.root, "elsewhere", "MyOp"))
        with self.assertRaisesRegex(CheckError, "refusing to delete"):
            packaging.clean_out(os.path.join(self.root, "elsewhere"), ("MyOp",), build)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "elsewhere", "MyOp")))

    def test_clean_out_normalises_before_the_containment_test(self):
        build = os.path.join(self.root, "build")
        os.makedirs(os.path.join(build, "out", "MyOp"))
        # the root and the out folder spelled with '..' (as a caller's relative or joined paths may be): inside
        packaging.clean_out(os.path.join(build, "x", "..", "out"), ("MyOp",), os.path.join(self.root, "y", "..", "build"))
        self.assertEqual(os.listdir(os.path.join(build, "out")), [])
        # a sibling whose name starts like the root's, the root itself, and a '..' that climbs out: all refused
        os.makedirs(os.path.join(self.root, "build2", "MyOp"))
        for out_dir, name in ((os.path.join(self.root, "build2"), "MyOp"), (self.root, "build"),
                              (os.path.join(build, "out", "..", ".."), "build2")):
            with self.subTest(out_dir=out_dir, name=name), self.assertRaisesRegex(CheckError, "refusing to delete"):
                packaging.clean_out(out_dir, (name,), build)
        self.assertTrue(os.path.isdir(os.path.join(self.root, "build2", "MyOp")))
        self.assertTrue(os.path.isdir(build))

    def test_clean_out_defaults_to_the_build_root(self):
        build = os.path.join(self.root, "build")
        os.makedirs(os.path.join(build, "out", "MyOp"))
        os.makedirs(os.path.join(self.root, "elsewhere", "MyOp"))
        with mock.patch.dict(os.environ, {"MODKIT_BUILD": build}):
            packaging.clean_out(os.path.join(build, "out"), ("MyOp",))
            with self.assertRaisesRegex(CheckError, "refusing to delete"):
                packaging.clean_out(os.path.join(self.root, "elsewhere"), ("MyOp",))
        self.assertEqual(os.listdir(os.path.join(build, "out")), [])


class StockTest(unittest.TestCase):
    @paths.skip_unless_extracted()
    def test_gameplay_files_match_stock_mod_manager(self):
        """The list is the Gameplay tag's FilesForTag in the game's own ModManager descriptor."""
        root = str(paths.extracted_root())
        found = [p for p in glob.glob(os.path.join(root, "**", "NDF", "ModManager.ndfbin"), recursive=True)
                 if "older" not in os.path.relpath(p, root).replace(os.sep, "/").split("/")]
        if not found:
            self.skipTest("NDF/ModManager.ndfbin is not in the extraction (see the warno-setup skill)")
        nb, _, _ = ndfbin.load(found[0])
        tags = {}
        for ob in nb.objects:
            if nb.cname(ob.cls) == "TModTagDescriptor":
                props = {nb.pname(p): v for p, v in ob.props}
                files = [nb.strings[v.v].decode() for v in props["FilesForTag"].v]
                tags[nb.strings[props["ModTag"].v].decode()] = files
        self.assertEqual(tuple(tags["Gameplay"]), packaging.GAMEPLAY_FILES)


if __name__ == "__main__":
    unittest.main()
