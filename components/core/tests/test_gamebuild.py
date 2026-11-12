"""modkit.core.gamebuild: the verified builds, the installed build read from an install's layout, the warning, the CLI."""
import contextlib
import io
import os
import re
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modkit.core import gamebuild, packaging, paths


def fake_install(root: Path, *revisions: str) -> Path:
    for rev in revisions:
        folder = root / "Data" / "PC" / rev
        folder.mkdir(parents=True)
        (folder / "Glad.dat").write_bytes(b"")
    return root


class Env(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for patcher in (mock.patch.dict(os.environ, {}, clear=True),
                        mock.patch.object(paths, "_code_dirs", return_value=[]),
                        mock.patch.object(paths, "_find_config", return_value=None)):
            patcher.start()
            self.addCleanup(patcher.stop)

    def install(self, *revisions: str) -> None:
        game = fake_install(self.root / "game", *revisions)
        os.environ[paths.ENV_GAME_DIR] = str(game)


class InstalledBuild(Env):
    def test_newest_revision_of_a_fake_install(self):
        self.install("169425", "197351", "201602")
        self.assertEqual(gamebuild.installed_build(), "201602")

    def test_numeric_order_not_text_order(self):
        self.install("99999", "201602")
        self.assertEqual(gamebuild.installed_build(), "201602")

    def test_none_when_unconfigured(self):
        self.assertIsNone(gamebuild.installed_build())

    def test_none_when_nothing_found(self):
        os.environ[paths.ENV_GAME_DIR] = str(self.root / "empty")
        self.assertIsNone(gamebuild.installed_build())


class Verified(unittest.TestCase):
    def test_the_verified_builds_newest_last(self):
        """201602, then 210942 once Twin Strike played on it (2026-11-12-twin-strike-210942-play1)."""
        self.assertEqual(gamebuild.VERIFIED_BUILDS, ("201602", "210942"))
        self.assertEqual(list(gamebuild.VERIFIED_BUILDS), sorted(gamebuild.VERIFIED_BUILDS, key=int))


class Warning(Env):
    def test_verified_build_has_no_warning(self):
        self.install(gamebuild.VERIFIED_BUILDS[-1])
        self.assertIsNone(gamebuild.build_warning())

    def test_every_verified_build_has_no_warning(self):
        for build in gamebuild.VERIFIED_BUILDS:
            with self.subTest(build=build):
                game = fake_install(self.root / build, build)
                os.environ[paths.ENV_GAME_DIR] = str(game)
                self.assertIsNone(gamebuild.build_warning())

    def test_unknown_build_has_no_warning(self):
        self.assertIsNone(gamebuild.build_warning())

    def test_other_build_warns_in_one_line(self):
        self.install("999999")
        line = gamebuild.build_warning()
        self.assertTrue(line.startswith("GAME BUILD: installed 999999; this toolkit was verified on 201602, 210942."))
        self.assertIn("knowledge/builds.md", line)
        self.assertIn("knowledge/topics/game-updates.md", line)
        self.assertNotIn("\n", line)


class Pin(unittest.TestCase):
    def test_packaging_build_number_is_never_older_than_the_newest_verified_build(self):
        """Packaging names one build in both files, and a port moves it first: the new build joins VERIFIED_BUILDS
        only after the probes play clean on it (CLAUDE.md), so packaging names the newest verified build or a newer
        one."""
        m = re.fullmatch(rb"version is '(\d+)'\n", packaging.VERSION_NDF)
        self.assertIsNotNone(m, packaging.VERSION_NDF)
        build = m.group(1).decode()
        self.assertIn(f"ModGenVersion = {build} ", packaging.CONFIG_INI)
        self.assertGreaterEqual(int(build), int(gamebuild.VERIFIED_BUILDS[-1]))


class Cli(Env):
    def run_main(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = gamebuild.main()
        return code, out.getvalue()

    def test_unconfigured_exits_1_naming_setup(self):
        code, text = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("warno-setup", text)

    def test_verified_exits_0_without_warning(self):
        self.install("201602", "210942")
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("installed build: 210942", text)
        self.assertIn("verified builds: 201602, 210942\n", text)
        self.assertNotIn("GAME BUILD", text)

    def test_other_build_exits_0_with_warning(self):
        self.install("999999")
        code, text = self.run_main()
        self.assertEqual(code, 0)
        self.assertIn("GAME BUILD: installed 999999", text)


if __name__ == "__main__":
    unittest.main()
