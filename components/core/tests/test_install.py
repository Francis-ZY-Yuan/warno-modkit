"""Tests for modkit.core.install, the one-click share installer.

`Package` checks the zip and the refusals. `Hooks` checks the extension point. `Install` runs the real .cmd end to
end (Windows only, skipped while WARNO.exe runs) from a lone copy in a folder whose path has a space and an
apostrophe, always against a fake Saved Games folder through install.ENV_SAVED_GAMES, never the real one.
"""
from __future__ import annotations

import base64
import contextlib
import hashlib
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest import mock

from modkit.core import install, paths

NAME = "FixtureMod"
TITLE = "Fixture Mod's menu title"
CONFIG = ("[Properties]\nName = FixtureMod\nID = 0 ; Mod Steam ID, do not modify\n"
          "ModGenVersion = 201602 ; ModGen revision, do not modify\n\n"
          "[Config] ; Used for mod compatibility check, do not modify\n")
ORIGINAL = "[Config]\nActivatedMods = Other ;Set every mod...\n"
WORKSHOP_ID = "2000000001"  # a mod uploaded to the Workshop has a non-zero ID; the game lists it by that ID
CONFIG_ID = CONFIG.replace("ID = 0 ;", f"ID = {WORKSHOP_ID} ;")


def warno_running() -> bool:
    if sys.platform != "win32":
        return False
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq WARNO.exe", "/NH"], capture_output=True, text=True).stdout
    return "warno.exe" in out.lower()


def make_mod(root: Path, config: str = CONFIG) -> Path:
    mod = root / NAME
    (mod / "Gen").mkdir(parents=True)
    (mod / "Scenarios").mkdir()
    (mod / "Config.ini").write_text(config, encoding="ascii", newline="")
    (mod / "Gen" / "Version.ndf").write_bytes(b"version\r\n")
    (mod / "Scenarios" / "a.dat").write_bytes(bytes(range(256)) * 300)
    (mod / "Scenarios" / "it's.dat").write_bytes(b"\x00\xff" * 50)
    (mod / install.MARKER).write_text("marker", encoding="ascii")
    return mod


def tree(root: Path) -> dict[str, bytes]:
    return {p.relative_to(root).as_posix(): p.read_bytes() for p in root.rglob("*") if p.is_file()}


class Package(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="install_test_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mod = make_mod(self.tmp / "built")
        self.zip = install.package(self.mod, TITLE, self.tmp / "out")

    def cmd_bytes(self) -> bytes:
        return zipfile.ZipFile(self.zip).read(f"Install {NAME}.cmd")

    def test_zip_layout_and_default_name(self):
        self.assertEqual(self.zip.name, f"{NAME}-share.zip")
        names = set(zipfile.ZipFile(self.zip).namelist())
        want = {f"Install {NAME}.cmd", "README.txt"} | {f"{NAME}/{r}" for r, _ in install.mod_files(self.mod)}
        self.assertEqual(names, want)

    def test_lone_installer_matches_zipped_one(self):
        self.assertEqual((self.tmp / "out" / f"Install {NAME}.cmd").read_bytes(), self.cmd_bytes())

    def test_same_mod_packs_to_same_bytes(self):
        again = install.package(self.mod, TITLE, self.tmp / "again")
        self.assertEqual(again.read_bytes(), self.zip.read_bytes())

    def test_mod_files_byte_identical_and_marker_skipped(self):
        z = zipfile.ZipFile(self.zip)
        got = {n[len(NAME) + 1:]: z.read(n) for n in z.namelist() if n.startswith(NAME + "/")}
        want = tree(self.mod)
        want.pop(install.MARKER)
        self.assertEqual(got, want)
        self.assertNotIn(f"{NAME}/{install.MARKER}", z.namelist())

    def test_cmd_is_ascii_crlf(self):
        data = self.cmd_bytes()
        data.decode("ascii")
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.assertEqual(data.count(b"\r"), data.count(b"\r\n"))

    def test_cmd_header_and_markers(self):
        text = self.cmd_bytes().decode("ascii")
        header = text.split("::PS-BEGIN")[0]
        self.assertIn('set "OD_SELF=%~f0"', header)
        self.assertIn("'::PS-'+'BEGIN'", header)
        self.assertNotIn("-ExecutionPolicy", text)
        self.assertNotIn("-EncodedCommand", text)
        ps_line = next(ln for ln in header.splitlines() if ln.startswith("powershell.exe"))
        self.assertNotIn("%", ps_line)
        self.assertEqual(text.count("\n::PS-BEGIN\r"), 1)
        self.assertEqual(text.count("\n::PS-END\r"), 1)

    def test_payload_matches_source(self):
        text = self.cmd_bytes().decode("ascii")
        body = text.split("::PAYLOAD-BEGIN\r\n")[1].split("::PAYLOAD-END")[0]
        self.assertTrue(all(len(ln) <= 76 for ln in body.split("\r\n")))
        z = zipfile.ZipFile(io.BytesIO(base64.b64decode(re.sub(r"\s", "", body))))
        want = tree(self.mod)
        want.pop(install.MARKER)
        self.assertEqual({n[len(NAME) + 1:]: z.read(n) for n in z.namelist()}, want)

    def test_readme(self):
        data = zipfile.ZipFile(self.zip).read("README.txt")
        text = data.decode("ascii")
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        for need in (TITLE, "Operations", "More info", "Run anyway", "Saved Games\\EugenSystems\\WARNO\\mod\\",
                     "Mod Center", "Built for WARNO data version 201602"):
            self.assertIn(need, text)

    def test_refuses_missing_config(self):
        (self.mod / "Config.ini").unlink()
        with self.assertRaisesRegex(install.ShareError, "Config.ini"):
            install.package(self.mod, TITLE, self.tmp / "o2")
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(install.main([str(self.mod), "--title", TITLE, "--out", str(self.tmp / "o2")]), 1)

    def test_refuses_gameplay_mod(self):
        (self.mod / "Config.ini").write_text(CONFIG + "GFX/Unit=0123456789abcdef\n", newline="")
        with self.assertRaisesRegex(install.ShareError, "Gameplay"):
            install.package(self.mod, TITLE, self.tmp / "o2")

    def test_refuses_a_mod_that_ships_a_gameplay_file(self):
        """The game tags a mod Gameplay when it ships, under Gen, a file whose path ends with one of the Gameplay
        tag's FilesForTag (packaging.GAMEPLAY_FILES), whatever its [Config] says."""
        for rel in ("Gen/NDF/GFX/Unit.ndfbin", "Gen/challenge_X/GFX/Unit.ndfbin",
                    "Gen/a/InitialisationGameDistanceUnits.ndfbin"):
            with self.subTest(rel=rel):
                fx = self.tmp / "gp" / rel.replace("/", "_") / NAME
                shutil.copytree(self.mod, fx)
                (fx / rel).parent.mkdir(parents=True, exist_ok=True)
                (fx / rel).write_bytes(b"x")
                self.assertTrue(install.is_gameplay(fx))
                with self.assertRaisesRegex(install.ShareError, f"Gameplay.*{re.escape(rel)}"):
                    install.package(fx, TITLE, self.tmp / "o2")

    def test_a_gameplay_name_outside_gen_or_another_suffix_is_fine(self):
        for rel in ("Scenarios/GFX/Unit.ndfbin", "Gen/NDF/GFX/MyUnit.ndfbin", "Gen/Unit.ndfbin"):
            (self.mod / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.mod / rel).write_bytes(b"x")
        self.assertFalse(install.is_gameplay(self.mod))
        install.package(self.mod, TITLE, self.tmp / "o2")

    def test_comment_only_config_is_fine(self):
        (self.mod / "Config.ini").write_text(CONFIG + "; just a comment = here\n", newline="")
        install.package(self.mod, TITLE, self.tmp / "o2")

    def test_refuses_requires_rows(self):
        (self.tmp / "built" / "MANIFEST.tsv").write_text(
            "name\tmod\tdir\trole\nx\tOtherMod\td\trequires\n", encoding="utf-8")
        with self.assertRaisesRegex(install.ShareError, "OtherMod"):
            install.package(self.mod, TITLE, self.tmp / "o2")

    def test_manifest_without_requires_is_fine(self):
        (self.tmp / "built" / "MANIFEST.tsv").write_text(
            "name\tmod\tdir\trole\nx\tFixtureMod\td\tbuilds\n", encoding="utf-8")
        install.package(self.mod, TITLE, self.tmp / "o2")

    def test_default_out_is_share_in_the_build_folder(self):
        cwd = os.getcwd()
        self.addCleanup(os.chdir, cwd)
        os.chdir(self.tmp)
        env = {k: v for k, v in os.environ.items() if k != paths.ENV_BUILD}
        # a set build folder: share/ in it
        with mock.patch.dict(os.environ, {**env, paths.ENV_BUILD: str(self.tmp / "my builds")}, clear=True), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(install.main([str(self.mod), "--title", TITLE]), 0)
        share = self.tmp / "my builds" / "share"
        self.assertTrue((share / f"{NAME}-share.zip").is_file())
        self.assertTrue((share / f"Install {NAME}.cmd").is_file())
        # nothing set and no modkit.local.toml: build/share in the working folder
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(paths, "_code_dirs", return_value=[]), \
                contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(install.main([str(self.mod), "--title", TITLE]), 0)
        self.assertTrue((self.tmp / "build" / "share" / f"{NAME}-share.zip").is_file())
        self.assertTrue((self.tmp / "build" / "share" / f"Install {NAME}.cmd").is_file())


CMD_SHA256 = "cab2321523cf66f4343e9b1c31379669865a89ef4fdb8ea3e16a215769a0ec51"  # build_cmd's bytes for fixed_cmd()


def fixed_cmd(root: Path) -> bytes:
    """build_cmd on fixed inputs (a fixed payload, so no zlib version can change the bytes)."""
    (root / "a.dat").write_bytes(bytes(range(256)))
    (root / "v.ndf").write_bytes(b"version\r\n")
    return install.build_cmd("Fixture Mod's", "A title", [("Gen/Version.ndf", root / "v.ndf"),
                                                          ("Scenarios/a.dat", root / "a.dat")], b"payload bytes" * 20)


class WhereItGoes(unittest.TestCase):
    """Where the installer puts a mod is defined once, in install's constants: the .cmd is formatted from them, and
    saved_games()/mod_root() are the same lookup in Python."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="install_where_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def test_cmd_bytes_are_unchanged(self):
        """The bytes of the .cmd before its template was formatted from the constants."""
        self.assertEqual(hashlib.sha256(fixed_cmd(self.tmp)).hexdigest(), CMD_SHA256)

    def test_the_cmd_is_formatted_from_the_constants(self):
        with mock.patch.multiple(install, ENV_SELF="X_SELF", ENV_SAVED_GAMES="X_SAVED", ENV_NO_PAUSE="X_NOPAUSE",
                                 SHELL_FOLDERS=r"Software\Elsewhere", SAVED_GAMES_ID="{0000-ID}",
                                 WARNO_FOLDER=("Studio", "Game"), MOD_FOLDER="mods"):
            text = fixed_cmd(self.tmp).decode("ascii")
        self.assertNotIn("OD_", text)
        for need in ('set "X_SELF=%~f0"', "ReadAllText($env:X_SELF)", "if not defined X_NOPAUSE pause",
                     "if ($env:X_SAVED) { return $env:X_SAVED }", r"'HKCU:\Software\Elsewhere'", "'{0000-ID}'",
                     r"Join-Path (Get-SavedGames) 'Studio\Game'", "Join-Path $warnoDir 'mods'",
                     "if ($env:X_NOPAUSE) { throw"):
            self.assertIn(need, text)

    def test_saved_games_and_mod_root(self):
        with mock.patch.dict(os.environ, {install.ENV_SAVED_GAMES: str(self.tmp / "SG")}):
            self.assertEqual(install.saved_games(), self.tmp / "SG")
            self.assertEqual(install.mod_root(), self.tmp / "SG" / "EugenSystems" / "WARNO" / "mod")
        env = {k: v for k, v in os.environ.items() if k != install.ENV_SAVED_GAMES}
        with mock.patch.dict(os.environ, {**env, "USERPROFILE": str(self.tmp / "me")}, clear=True), \
                mock.patch.object(install, "SAVED_GAMES_ID", "{not-a-known-folder}"):
            self.assertEqual(install.saved_games(), self.tmp / "me" / "Saved Games")  # no known folder: the fallback


class Hooks(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="install_hook_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mod = make_mod(self.tmp / "built")

    def add(self, hook):
        install.register_hook(hook)
        self.addCleanup(install.HOOKS.remove, hook)

    def test_hook_gets_mod_dir_and_targets(self):
        calls = []
        self.add(lambda mod_dir, targets: calls.append((mod_dir, tuple(targets))))
        dest = install.package(self.mod, TITLE, self.tmp / "out")
        out = self.tmp / "out"
        self.assertEqual(calls, [(self.mod.resolve(), (out / f"Install {NAME}.cmd", out / f"{NAME}-share.zip"))])
        self.assertEqual(dest, out / f"{NAME}-share.zip")

    def test_hook_runs_after_the_checks_and_before_any_write(self):
        seen = []
        self.add(lambda mod_dir, targets: seen.append([t.exists() for t in targets]))
        (self.mod / "Config.ini").unlink()
        with self.assertRaises(install.ShareError):
            install.package(self.mod, TITLE, self.tmp / "o1")
        self.assertEqual(seen, [])                       # a refused mod never reaches a hook
        make_mod(self.tmp / "again")
        install.package(self.tmp / "again" / NAME, TITLE, self.tmp / "o2")
        self.assertEqual(seen, [[False, False]])         # nothing written yet when the hook runs

    def test_hook_can_refuse(self):
        def refuse(mod_dir, targets):
            raise install.ShareError(f"{mod_dir.name}: refused by a hook")
        self.add(refuse)
        with self.assertRaisesRegex(install.ShareError, "refused by a hook"):
            install.package(self.mod, TITLE, self.tmp / "o1")
        self.assertFalse((self.tmp / "o1").exists())
        with contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(install.main([str(self.mod), "--title", TITLE, "--out", str(self.tmp / "o2")]), 1)
        self.assertIn("refused by a hook", err.getvalue())


@unittest.skipUnless(sys.platform == "win32", "the installer is a Windows .cmd")
@unittest.skipIf(warno_running(), "WARNO.exe is running")
class Install(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp(prefix="install_e2e_"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.mod = make_mod(self.tmp / "built")
        z = install.package(self.mod, TITLE, self.tmp / "out")
        # the .cmd alone, in a folder whose path has a space and an apostrophe (what Explorer does with a zip)
        self.run_dir = self.tmp / "Bob's Downloads"
        self.run_dir.mkdir()
        self.cmd = self.run_dir / f"Install {NAME}.cmd"
        self.cmd.write_bytes(zipfile.ZipFile(z).read(self.cmd.name))
        self.sg = self.tmp / "Saved Games"
        self.warno = self.sg / "EugenSystems" / "WARNO"
        self.modroot = self.warno / "mod"
        self.warno.mkdir(parents=True)
        self.want = tree(self.mod)
        self.want.pop(install.MARKER)

    def run_cmd(self) -> subprocess.CompletedProcess:
        # the variables by install's own names, so a rename can never send a test install to the real Saved Games
        env = dict(os.environ, **{install.ENV_SAVED_GAMES: str(self.sg), install.ENV_NO_PAUSE: "1"})
        return subprocess.run(["cmd", "/c", str(self.cmd)], env=env, capture_output=True, text=True, timeout=300,
                              stdin=subprocess.DEVNULL)

    def test_it_installs_into_mod_root(self):
        """The .cmd puts the mod where install.mod_root() says, under the same override."""
        with mock.patch.dict(os.environ, {install.ENV_SAVED_GAMES: str(self.sg)}):
            self.assertEqual(install.mod_root(), self.modroot)
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertInstalled()

    def ini(self) -> bytes:
        return (self.modroot / "Config.ini").read_bytes()

    def backup(self) -> Path:
        return self.modroot / f"Config.ini.before-{NAME}.bak"

    def put_ini(self, text: str):
        self.modroot.mkdir(exist_ok=True)
        (self.modroot / "Config.ini").write_bytes(text.encode("ascii"))

    def assertInstalled(self):
        self.assertEqual(tree(self.modroot / NAME), self.want)

    def use_config(self, config: str) -> None:
        """Rebuild the fixture mod with `config` as its Config.ini, and put its lone .cmd where setUp put the first."""
        shutil.rmtree(self.tmp / "built")
        self.mod = make_mod(self.tmp / "built", config)
        z = install.package(self.mod, TITLE, self.tmp / "out_config")
        self.cmd.write_bytes(zipfile.ZipFile(z).read(self.cmd.name))
        self.want = tree(self.mod)
        self.want.pop(install.MARKER)

    def test_lf_file_then_second_run(self):
        self.put_ini(ORIGINAL)
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertIn("Installed " + TITLE + " and switched it on.", r.stdout)
        self.assertInstalled()
        self.assertEqual(self.ini(), f"[Config]\nActivatedMods = Other|{NAME} ;Set every mod...\n".encode())
        self.assertFalse(self.ini().startswith(b"\xef\xbb\xbf"))
        self.assertEqual(self.backup().read_bytes(), ORIGINAL.encode())
        after = self.ini()
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini(), after)
        self.assertEqual(self.ini().count(NAME.encode()), 1)
        self.assertEqual(self.backup().read_bytes(), ORIGINAL.encode())
        self.assertInstalled()

    def test_crlf_file_keeps_crlf(self):
        self.put_ini(ORIGINAL.replace("\n", "\r\n"))
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini(), f"[Config]\r\nActivatedMods = Other|{NAME} ;Set every mod...\r\n".encode())
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini().count(NAME.encode()), 1)

    def test_config_without_activatedmods_line(self):
        self.put_ini("[Config] ; hi\nOther = 1\n")
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini(), f"[Config] ; hi\nActivatedMods = {NAME}\nOther = 1\n".encode())

    def test_no_config_ini(self):
        self.modroot.mkdir()
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini(), f"[Config]\nActivatedMods = {NAME}\n".encode())
        self.assertFalse(self.backup().exists())
        self.assertInstalled()

    def test_no_mod_folder(self):
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini(), f"[Config]\nActivatedMods = {NAME}\n".encode())
        self.assertInstalled()

    def test_no_warno_folder(self):
        shutil.rmtree(self.sg)
        self.sg.mkdir()
        r = self.run_cmd()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("Install failed", r.stdout)
        self.assertEqual(list(self.sg.iterdir()), [])

    def test_replaces_older_install(self):
        old = self.modroot / NAME
        (old / "Scenarios").mkdir(parents=True)
        (old / "Scenarios" / "stale.dat").write_bytes(b"old")
        (old / "Config.ini").write_text("[Properties]\nName = old\n")
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertFalse((old / "Scenarios" / "stale.dat").exists())
        self.assertInstalled()

    def test_a_mod_with_an_id_is_listed_by_its_id(self):
        """The game's own form: a mod with a non-zero ID is listed by that ID, and a second run changes nothing."""
        self.use_config(CONFIG_ID)
        self.put_ini(ORIGINAL)
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertInstalled()
        self.assertEqual(self.ini(), f"[Config]\nActivatedMods = Other|{WORKSHOP_ID} ;Set every mod...\n".encode())
        after = self.ini()
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini(), after)

    def test_reinstall_after_the_game_listed_it_by_id(self):
        """The game rewrites ActivatedMods at startup, naming a mod with a non-zero ID by its ID. A reinstall finds
        that entry and lists the mod once, in its place: the file is left alone."""
        self.use_config(CONFIG_ID)
        listed = f"[Config]\nActivatedMods = Other|{WORKSHOP_ID}|Third ;Set every mod...\n"
        self.put_ini(listed)
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertInstalled()
        self.assertEqual(self.ini(), listed.encode())
        self.assertFalse(self.backup().exists())

    def test_either_form_counts_as_the_mod(self):
        """The folder name and the ID both name the mod: they become one entry, in the game's form, at the first
        one's place."""
        self.use_config(CONFIG_ID)
        self.put_ini(f"[Config]\r\nActivatedMods = {NAME}|Other|{WORKSHOP_ID}\r\n")
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertEqual(self.ini(), f"[Config]\r\nActivatedMods = {WORKSHOP_ID}|Other\r\n".encode())

    def test_the_replaced_copys_id_counts_as_the_mod(self):
        """An installed copy may have another ID than the new build (here a Workshop ID, the new build 0): the entry
        for the old ID is the mod's, and takes the new form in its place."""
        old = self.modroot / NAME
        old.mkdir(parents=True)
        (old / "Config.ini").write_text(CONFIG_ID, encoding="ascii", newline="")
        self.put_ini(f"[Config]\nActivatedMods = Other|{WORKSHOP_ID}|Third\n")
        r = self.run_cmd()
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        self.assertInstalled()
        self.assertEqual(self.ini(), f"[Config]\nActivatedMods = Other|{NAME}|Third\n".encode())

    def test_damaged_installer_is_refused(self):
        # a payload that no longer matches the baked hashes (here: the first hash is wrong) must install nothing
        data = self.cmd.read_bytes()
        i = data.index(b"'Config.ini' = '") + len(b"'Config.ini' = '")
        self.cmd.write_bytes(data[:i] + (b"0" if data[i:i + 1] != b"0" else b"1") + data[i + 1:])
        r = self.run_cmd()
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("looks damaged", r.stdout)
        self.assertFalse((self.modroot / NAME).exists())


if __name__ == "__main__":
    unittest.main()
