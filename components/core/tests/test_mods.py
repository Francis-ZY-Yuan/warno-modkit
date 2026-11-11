"""Tests for modkit.core.mods (installed and built mods, read back) and modkit.core.paths.workshop_dir, on synthetic
mods folders, Workshop folders and packs in a temporary folder. Nothing here needs the game."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modkit.core import edat, mods, paths


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "mod"
        self.workshop = self.tmp / "content" / "1611600"


class ConfigTest(Base):
    def test_activated_mods(self):
        """ActivatedMods entries in order: '|'-separated, a ';' comment cut off, blanks dropped; [] without the line,
        None without Config.ini."""
        self.assertIsNone(mods.activated_mods(self.root))
        write(self.root / "Config.ini", "[Config]\nActivatedMods = OpenDoor| 123456789 |TwinStrike|;every mod\n")
        self.assertEqual(mods.activated_mods(self.root), ["OpenDoor", "123456789", "TwinStrike"])
        write(self.root / "Config.ini", "[Config]\n")
        self.assertEqual(mods.activated_mods(self.root), [])

    def test_mod_id_and_name(self):
        """The share installer's ID rule: no leading zeros, '' for 0, none or no Config.ini; the Name, else the
        folder's."""
        a = self.root / "A"
        self.assertEqual((mods.mod_id(a), mods.mod_name(a)), ("", "A"))
        write(a / "Config.ini", "[Properties]\nName = Alpha ; the title\nID = 0042 ; Mod Steam ID\n")
        self.assertEqual((mods.mod_id(a), mods.mod_name(a)), ("42", "Alpha"))
        write(a / "Config.ini", "[Properties]\nID = 0\n")
        self.assertEqual((mods.mod_id(a), mods.mod_name(a)), ("", "A"))


class FindTest(Base):
    def setUp(self):
        super().setUp()
        write(self.root / "Local" / "Config.ini", "[Properties]\nName = Local\nID = 0\n")
        write(self.root / "Shared" / "Config.ini", "[Properties]\nName = Shared\nID = 777\n")
        write(self.workshop / "888" / "Config.ini", "[Properties]\nName = Far\nID = 888\n")

    def test_by_name_by_id_then_the_workshop(self):
        self.assertEqual(mods.find_mod("Local", self.root, self.workshop), self.root / "Local")
        self.assertEqual(mods.find_mod("777", self.root, self.workshop), self.root / "Shared")
        self.assertEqual(mods.find_mod("888", self.root, self.workshop), self.workshop / "888")
        self.assertIsNone(mods.find_mod("999", self.root, self.workshop))
        self.assertIsNone(mods.find_mod("888", self.root, None))
        self.assertIsNone(mods.find_mod("Gone", self.root, self.workshop))

    def test_listings(self):
        self.assertEqual([p.name for p in mods.installed_mods(self.root)], ["Local", "Shared"])
        self.assertEqual([p.name for p in mods.workshop_items(self.workshop)], ["888"])
        self.assertEqual(mods.workshop_items(None), [])
        self.assertEqual(mods.installed_mods(self.tmp / "none"), [])


class PackTest(Base):
    def test_scenario_packs_and_read_pack(self):
        pack = self.root / "M" / "Scenarios" / "challenge_X_Definition.dat"
        pack.parent.mkdir(parents=True)
        edat.write_edat(str(pack), [("NDF/Scenarios/MapConfiguration/challenge_X.ndfbin", b"mc"),
                                    ("Localisation/challenge_X/A-US.dic", b"dic")])
        self.assertEqual(mods.scenario_packs(self.root / "M"), [pack])
        self.assertEqual(mods.read_pack(pack, lambda p: p.endswith(".dic")),
                         [("Localisation/challenge_X/A-US.dic", b"dic")])
        self.assertEqual(mods.scenario_packs(self.root / "None"), [])


class WorkshopDirTest(Base):
    """The Workshop content folder is found from the game install, in the Steam library holding it."""

    def library(self, installdir: str = "WARNO", content: bool = True) -> Path:
        steamapps = self.tmp / "lib" / "steamapps"
        game = steamapps / "common" / "WARNO"
        game.mkdir(parents=True)
        write(steamapps / "appmanifest_1611600.acf", f'"AppState"\n{{\n\t"appid"\t\t"1611600"\n'
                                                     f'\t"installdir"\t\t"{installdir}"\n}}\n')
        write(steamapps / "appmanifest_10.acf", '"AppState"\n{\n\t"installdir"\t\t"Other"\n}\n')
        if content:
            (steamapps / "workshop" / "content" / "1611600").mkdir(parents=True)
        return game

    def test_found_beside_the_install(self):
        game = self.library()
        with mock.patch.dict(os.environ, {paths.ENV_GAME_DIR: str(game)}):
            self.assertEqual(paths.workshop_dir(), self.tmp / "lib" / "steamapps" / "workshop" / "content" / "1611600")

    def test_none_without_it(self):
        game = self.library(content=False)
        with mock.patch.dict(os.environ, {paths.ENV_GAME_DIR: str(game)}):
            self.assertIsNone(paths.workshop_dir())
        with mock.patch.object(paths, "game_dir", side_effect=paths.NotConfigured("warno-setup")):
            self.assertIsNone(paths.workshop_dir())
        with mock.patch.dict(os.environ, {paths.ENV_GAME_DIR: str(self.tmp / "loose" / "WARNO")}):
            self.assertIsNone(paths.workshop_dir())


if __name__ == "__main__":
    unittest.main()
