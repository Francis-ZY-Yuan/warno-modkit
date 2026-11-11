"""Tests for modkit.core.paths: where the extraction and the game install live."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modkit.core import paths


class PathsTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.cwd = os.getcwd()
        self.addCleanup(os.chdir, self.cwd)
        env = {k: v for k, v in os.environ.items()
               if k not in ("MODKIT_EXTRACTED", "MODKIT_GAME_DIR", "MODKIT_DATA", "MODKIT_BUILD")}
        patcher = mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        # only the working folder is searched; the code's own location must not find a real config
        patcher = mock.patch.object(paths, "_code_dirs", return_value=[])
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_env_var_wins(self):
        (self.tmp / "modkit.local.toml").write_text('extracted = "from_toml"\ngame_dir = "g_toml"\n')
        os.chdir(self.tmp)
        os.environ["MODKIT_EXTRACTED"] = str(self.tmp / "from_env")
        os.environ["MODKIT_GAME_DIR"] = str(self.tmp / "game_env")
        self.assertEqual(paths.extracted_root(), self.tmp / "from_env")
        self.assertEqual(paths.game_dir(), self.tmp / "game_env")

    def test_finds_config_from_subfolder(self):
        (self.tmp / "modkit.local.toml").write_text('extracted = "ex"\ngame_dir = "' + ".." + '/game"\n')
        sub = self.tmp / "a" / "b"
        sub.mkdir(parents=True)
        os.chdir(sub)
        self.assertEqual(paths.extracted_root(), self.tmp / "ex")
        self.assertEqual(paths.game_dir(), self.tmp.parent / "game")

    def test_unconfigured_skips_cleanly(self):
        os.chdir(self.tmp)
        with self.assertRaises(paths.NotConfigured) as cm:
            paths.extracted_root()
        self.assertIn("warno-setup", str(cm.exception))
        with self.assertRaises(paths.NotConfigured):
            paths.game_dir()

        class Probe(unittest.TestCase):
            @paths.skip_unless_extracted("a", "b.ndfbin")  # not stock
            def test_it(self):
                raise AssertionError("must not run")

        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(Probe).run(result)
        self.assertEqual(len(result.skipped), 1)
        self.assertIn("warno-setup", result.skipped[0][1])
        self.assertTrue(result.wasSuccessful())

    def test_skip_runs_when_file_present(self):
        (self.tmp / "ex" / "a").mkdir(parents=True)
        (self.tmp / "ex" / "a" / "b.ndfbin").write_bytes(b"x")
        os.chdir(self.tmp)
        os.environ["MODKIT_EXTRACTED"] = str(self.tmp / "ex")

        class Probe(unittest.TestCase):
            @paths.skip_unless_extracted("a", "b.ndfbin")  # not stock
            def test_it(self):
                pass

        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(Probe).run(result)
        self.assertEqual((result.testsRun, len(result.skipped)), (1, 0))

    def test_data_dir_env_then_toml_then_beside_the_extraction(self):
        (self.tmp / "modkit.local.toml").write_text('extracted = "work/extracted"\n')
        os.chdir(self.tmp)
        self.assertEqual(paths.data_dir(), self.tmp / "work" / "modkit-data")
        (self.tmp / "modkit.local.toml").write_text('extracted = "work/extracted"\ndata_dir = "mine"\n')
        self.assertEqual(paths.data_dir(), self.tmp / "mine")
        os.environ["MODKIT_DATA"] = str(self.tmp / "from_env")
        self.assertEqual(paths.data_dir(), self.tmp / "from_env")

    def test_data_dir_unconfigured(self):
        os.chdir(self.tmp)
        with self.assertRaises(paths.NotConfigured) as cm:
            paths.data_dir()
        self.assertIn("warno-setup", str(cm.exception))
        self.assertIn("MODKIT_DATA", str(cm.exception))

        class Probe(unittest.TestCase):
            @paths.skip_unless_data("ndfrules.tsv")
            def test_it(self):
                raise AssertionError("must not run")

        result = unittest.TestResult()
        unittest.defaultTestLoader.loadTestsFromTestCase(Probe).run(result)
        self.assertEqual(len(result.skipped), 1)
        self.assertTrue(result.wasSuccessful())

    def test_build_root_env_then_toml_then_beside_the_toml(self):
        (self.tmp / "modkit.local.toml").write_text('extracted = "ex"\n')
        sub = self.tmp / "a" / "b"
        sub.mkdir(parents=True)
        os.chdir(sub)
        self.assertEqual(paths.build_root(), self.tmp / "build")  # beside the toml found, not the working folder
        (self.tmp / "modkit.local.toml").write_text('extracted = "ex"\nbuild_dir = "out/builds"\n')
        self.assertEqual(paths.build_root(), self.tmp / "out" / "builds")
        os.environ["MODKIT_BUILD"] = str(self.tmp / "from_env")
        self.assertEqual(paths.build_root(), self.tmp / "from_env")

    def test_build_root_unconfigured_is_build_in_the_working_folder(self):
        """With no setting and no toml it never raises: a build given --out needs no build folder setting."""
        sub = self.tmp / "a"
        sub.mkdir()
        os.chdir(sub)
        self.assertEqual(paths.build_root(), sub / "build")
        os.environ["MODKIT_EXTRACTED"] = str(self.tmp / "ex")  # env-only setup: still the working folder's build/
        os.environ["MODKIT_GAME_DIR"] = str(self.tmp / "game")
        self.assertEqual(paths.build_root(), sub / "build")

    def test_rel_source_keeps_extracted_prefix(self):
        root = self.tmp / "ex"
        os.environ["MODKIT_EXTRACTED"] = str(root)
        self.assertEqual(paths.rel_source(str(root / "a" / "b.ndfbin")), "extracted/a/b.ndfbin")
        self.assertEqual(paths.rel_source(root / "a" / "b.ndfbin"), "extracted/a/b.ndfbin")


if __name__ == "__main__":
    unittest.main()
