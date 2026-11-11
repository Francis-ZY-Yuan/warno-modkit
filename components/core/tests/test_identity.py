"""The history scan's identity rule, on synthetic repositories."""
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

import repofixture as fx
from modkit.core import hygiene, repocheck

NAME, EMAIL = "neutral person", "neutral@example.invalid"
UTC_DATE = "2026-01-02T03:04:05+0000"


def commit(root, *, an=NAME, ae=EMAIL, cn=None, ce=None, ad=UTC_DATE, cd=None, message="c"):
    env = {**os.environ, "GIT_AUTHOR_NAME": an, "GIT_AUTHOR_EMAIL": ae, "GIT_AUTHOR_DATE": ad,
           "GIT_COMMITTER_NAME": cn or an, "GIT_COMMITTER_EMAIL": ce or ae, "GIT_COMMITTER_DATE": cd or ad}
    fx.write(root / "stamp.txt", message)
    for args in (["add", "stamp.txt"], ["-c", "commit.gpgsign=false", "commit", "-q", "-m", message]):
        subprocess.run(["git", *args], cwd=root, env=env, check=True, capture_output=True)


class Identity(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = fx.make_repo(Path(self._tmp.name) / "repo", {"core": {}})
        self.config(allow="[]")
        fx.git_init(self.root)

    def config(self, allow):
        fx.write(self.root / "modkit.repo.toml",
                 'visibility = "public"\n[identity]\nname = "%s"\nemail = "%s"\noffset = "+0000"\nallow = %s\n'
                 % (NAME, EMAIL, allow))

    def found(self):
        return [str(f) for f in hygiene.scan_identity(self.root)]

    def test_neutral_utc_commit_passes(self):
        commit(self.root)
        self.assertEqual(self.found(), [])
        self.assertEqual([f for f in hygiene.scan_history(self.root) if f.rule == "identity"], [])

    def test_other_author_name_fails(self):
        commit(self.root, an="someone else")
        out = self.found()
        self.assertTrue(any("author is someone else" in line for line in out), out)
        self.assertIn("commit:", out[0])

    def test_other_email_fails(self):
        commit(self.root, ae="me@example.invalid")
        self.assertTrue(any("author is" in line and "me@example.invalid" in line for line in self.found()))

    def test_committer_differing_from_author_fails(self):
        commit(self.root, cn="another", ce="another@example.invalid")
        self.assertTrue(any("committer is another" in line for line in self.found()))

    def test_offset_on_author_date_fails(self):
        commit(self.root, ad="2026-01-02T03:04:05-0500", cd=UTC_DATE)
        out = self.found()
        self.assertTrue(any("author date is offset -0500" in line for line in out), out)

    def test_offset_on_committer_date_fails(self):
        commit(self.root, cd="2026-01-02T03:04:05-0500")
        out = self.found()
        self.assertTrue(any("committer date is offset -0500" in line for line in out), out)

    def test_allowlisted_identity_passes(self):
        self.config(allow='[{ name = "guest", email = "guest@example.invalid" }]')
        commit(self.root, an="guest", ae="guest@example.invalid")
        self.assertEqual(self.found(), [])

    def test_unlisted_identity_still_fails_with_an_allowlist(self):
        self.config(allow='[{ name = "guest", email = "guest@example.invalid" }]')
        commit(self.root, an="stranger", ae="guest@example.invalid")
        self.assertTrue(self.found())

    def test_repocheck_history_reports_it(self):
        commit(self.root, ad="2026-01-02T03:04:05-0500")
        self.assertTrue(any(p.rule == "identity" for p in repocheck.run(self.root, history=True)
                            if hasattr(p, "rule")))

    def test_no_identity_table_means_no_rule(self):
        fx.write(self.root / "modkit.repo.toml", 'visibility = "public"\n')
        commit(self.root, an="anyone", ad="2026-01-02T03:04:05-0500")
        self.assertEqual(self.found(), [])


if __name__ == "__main__":
    unittest.main()
