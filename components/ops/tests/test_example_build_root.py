"""Every example takes its default --out and the folder a rebuild may delete in from modkit.core.paths.build_root,
read when a build runs, never at import. The build folder needs no setting: unconfigured it is build/ in the working
folder, so a profile can always be made, and a setup of only MODKIT_EXTRACTED and MODKIT_GAME_DIR builds with --out."""
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

from modkit.core import paths

EXAMPLES = Path(__file__).resolve().parents[1] / "examples"
FRONT_ENDS = (("probes", "probes", "spike2"), ("open-door", "opendoor", "op"),  # (folder, package, a content)
              ("twin-strike", "twinstrike", "op"))
SMALLEST = {"probes": "empty", "open-door": "op", "twin-strike": "op"}  # the content each env-only build makes


def run_python(code: str, cwd: str, env: dict) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-c", textwrap.dedent(code)], cwd=cwd, env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")


def clean_env(**extra: str) -> dict:
    env = {k: v for k, v in os.environ.items() if not k.startswith("MODKIT_")}
    return {**env, **extra}


ONLY_CWD = "paths._code_dirs = lambda: []          # only the working folder (empty) is searched for a toml"


class ExampleBuildRoot(unittest.TestCase):
    def profiles(self, cwd: str, env: dict) -> dict[str, list[str]]:
        """Each example's default_out(<content>), profile().build_root and working folder, made in a fresh process."""
        out = {}
        for folder, package, content in FRONT_ENDS:
            r = run_python(f"""
                import os, sys
                from modkit.core import paths
                {ONLY_CWD}
                sys.path.insert(0, {str(EXAMPLES / folder)!r})
                from {package} import profile
                print(profile.default_out({content!r}))
                print(profile.profile().build_root)
                print(os.getcwd())
            """, cwd, env)
            self.assertEqual(r.returncode, 0, r.stderr)
            out[folder] = r.stdout.splitlines()
        return out

    def test_default_out_and_build_root_follow_paths_build_root(self):
        with tempfile.TemporaryDirectory() as tmp:
            build = os.path.join(tmp, "my builds")
            for (folder, _, content), (default, root, _) in zip(FRONT_ENDS, self.profiles(
                    tmp, clean_env(MODKIT_BUILD=build)).values()):
                self.assertEqual((default, root), (os.path.join(build, folder, content), build))

    def test_unconfigured_profiles_use_the_working_folders_build(self):
        """No setting and no toml (a fresh clone before warno-setup): profiles are still made, over build/ in the
        working folder, so the tests that need no stock data run."""
        with tempfile.TemporaryDirectory() as tmp:
            for (folder, _, content), (default, root, cwd) in zip(FRONT_ENDS, self.profiles(tmp, clean_env()).values()):
                build = os.path.join(cwd, "build")
                self.assertEqual((default, root), (os.path.join(build, folder, content), build))
            self.assertEqual(os.listdir(tmp), [])

    def test_unconfigured_build_fails_in_one_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            for folder, package, content in FRONT_ENDS:
                for out in ([], ["--out", os.path.join(tmp, "out")]):
                    with self.subTest(example=folder, out=bool(out)):
                        r = run_python(f"""
                            import runpy, sys
                            from modkit.core import paths
                            {ONLY_CWD}
                            sys.argv = ["build.py", "--content", {content!r}, *{out!r}]
                            runpy.run_path({str(EXAMPLES / folder / "build.py")!r}, run_name="__main__")
                        """, tmp, clean_env())
                        self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
                        self.assertNotIn("Traceback", r.stderr)
                        (line,) = r.stderr.strip().splitlines()
                        self.assertTrue(line.startswith("FAILED: ") and "warno-setup" in line, line)
                        self.assertEqual(os.listdir(tmp), [])

    @paths.skip_unless_extracted()
    @paths.skip_unless_game_dir("WARNO.exe")
    def test_env_only_setup_builds_with_out(self):
        """MODKIT_EXTRACTED and MODKIT_GAME_DIR only, no toml: every build CLI builds with --out, and nothing is
        written outside it."""
        extracted, game = paths.extracted_root(), paths.game_dir()
        if not (extracted.parent / paths.DATA_NAME / "ndfrules.tsv").is_file():
            self.skipTest("the rules table is not in its default place beside the extraction (see warno-setup)")
        env = clean_env(MODKIT_EXTRACTED=str(extracted), MODKIT_GAME_DIR=str(game))
        with tempfile.TemporaryDirectory() as tmp:
            for folder, _, _ in FRONT_ENDS:
                with self.subTest(example=folder):
                    out = os.path.join(tmp, "out", folder)
                    r = run_python(f"""
                        import runpy, sys
                        from modkit.core import paths
                        {ONLY_CWD}
                        sys.argv = ["build.py", "--content", {SMALLEST[folder]!r}, "--out", {out!r}]
                        runpy.run_path({str(EXAMPLES / folder / "build.py")!r}, run_name="__main__")
                    """, tmp, env)
                    self.assertEqual(r.returncode, 0, r.stdout[-2000:] + r.stderr[-2000:])
                    self.assertTrue(any(Path(out).glob("*/Config.ini")), os.listdir(out))
            self.assertEqual(os.listdir(tmp), ["out"])


if __name__ == "__main__":
    unittest.main()
