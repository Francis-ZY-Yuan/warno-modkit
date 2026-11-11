"""The hygiene gates, on throwaway repositories (and on this one)."""
import contextlib
import hashlib
import io
import tempfile
import unittest
from pathlib import Path

import repofixture as fx
from modkit.core import hygiene, repocheck


def sha(phrase):
    return hashlib.sha256(phrase.encode()).hexdigest()


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = fx.make_repo(Path(self._tmp.name) / "repo", {"core": {}, "ops": {"deps": ["core"]}})
        self.core = self.root / "components/core"

    def rules(self, findings=None):
        findings = hygiene.scan_tree(self.root) if findings is None else findings
        return sorted({f.rule for f in findings})

    def put(self, rel, text):
        return fx.write(self.root / rel, text)

    def allow(self, *entries):
        body = "".join(f'[[allow]]\npath = "{p}"\ntext = "{t}"\nreason = "{r}"\n' for p, t, r in entries)
        fx.write(self.core / "hygiene-allow.toml", body)

    def deny(self, *phrases):
        fx.write(self.core / "hygiene-deny.toml", "hashes = [%s]\n" % ", ".join(f'"{sha(p)}"' for p in phrases))


class Tree(Fixture):
    def test_clean_tree_passes(self):
        self.put("components/core/src/modkit/core/ok.py", "X = 12345\nTEXT = 'a plain module'\n")
        self.assertEqual(hygiene.scan_tree(self.root), [])

    def test_stock_extension_fails(self):
        for name in ("a.ndfbin", "b.DAT", "c.dds", "ndfrules.tsv"):
            self.put("components/core/examples/" + name, b"\0\1")
        found = hygiene.scan_tree(self.root)
        self.assertEqual({Path(f.path).name for f in found if f.rule == "stock-extension"},
                         {"a.ndfbin", "b.DAT", "c.dds", "ndfrules.tsv"})

    def test_the_formats_setup_extracts_fail(self):
        """Every kind of file `setup extract` writes into an extraction: the mod SDK's NDF text, Definition .tag
        sidecars, Details .sav files, compiled scenario Python (.xyz), and setup's own index and provenance files."""
        names = ("GDOperator.ndf", "x.TAG", "Items.sav", "scenario.xyz", "_provenance.tsv", "index_all.tsv",
                 "_extraction.json")
        for name in names:
            self.put("components/core/tests/fixtures/" + name, "small text\n")
        found = hygiene.scan_tree(self.root)
        self.assertEqual({Path(f.path).name for f in found if f.rule == "stock-extension"}, set(names))
        self.put("components/core/tests/fixtures/notes.tsv", "a\tb\n")  # an ordinary .tsv or .json is not stock
        self.put("components/core/tests/fixtures/x.json", "{}\n")
        self.assertEqual({Path(f.path).name for f in hygiene.scan_tree(self.root) if f.rule == "stock-extension"},
                         set(names))

    def test_size_fails_over_512_kib(self):
        self.put("components/core/examples/big.txt", "a" * (512 * 1024 + 1))
        self.put("components/core/examples/ok.txt", "a" * (512 * 1024))
        found = [f for f in hygiene.scan_tree(self.root) if f.rule == "size"]
        self.assertEqual([f.path for f in found], ["components/core/examples/big.txt"])

    def test_local_path_fails(self):
        self.put("components/core/src/modkit/core/a.py", f'P = "{fx.user_path()}"\n')
        self.put("components/core/src/modkit/core/b.py", "P = 'x/" + "Steam" + "Library/y'\n")
        self.put("components/core/src/modkit/core/c.py", "U = 'http://example.invalid/x'\nK = 'HKCU:\\Software'\n")
        found = [f for f in hygiene.scan_tree(self.root) if f.rule == "local-path"]
        self.assertEqual(sorted(Path(f.path).name for f in found), ["a.py", "b.py"])

    def test_deny_hash_matches_without_plain_text(self):
        self.deny("plugh", "xyzzy frobnicate", "alpha beta gamma", "one two three four")
        self.put("components/core/src/modkit/core/a.py", "# a Plugh here\n")
        self.put("components/core/src/modkit/core/b.py", "# xyzzy\n# frobnicate\n")
        self.put("components/core/src/modkit/core/c.py", "# Alpha-beta, gamma!\n")
        self.put("components/core/src/modkit/core/d.py", "# alpha beta delta\n")
        self.put("components/core/src/modkit/core/e.py", "# One two\n# three four\n")
        found = [f for f in hygiene.scan_tree(self.root) if f.rule == "deny"]
        self.assertEqual(sorted(Path(f.path).name for f in found), ["a.py", "b.py", "c.py", "e.py"])
        self.assertTrue(all(f.text.startswith("sha256:") for f in found))
        stored = (self.core / "hygiene-deny.toml").read_text()
        for plain in ("plugh", "xyzzy", "frobnicate", "alpha"):
            self.assertNotIn(plain, stored)
            self.assertFalse(any(plain in f.text for f in found))

    def test_deny_in_a_file_name(self):
        self.deny("plugh")
        self.put("components/core/examples/plugh.txt", "x")
        self.assertIn("deny", self.rules())

    def test_local_deny_list_is_read_from_the_local_toml_and_never_scanned(self):
        fx.write(self.root / "modkit.local.toml", 'deny = ["someone-private"]\n')
        self.put("components/core/src/modkit/core/a.py", "# Someone Private\n")
        found = hygiene.scan_tree(self.root)
        self.assertEqual([(f.rule, f.path) for f in found], [("deny", "components/core/src/modkit/core/a.py")])

    def test_address_literal_fails_and_allowlisted_guid_passes(self):
        lit, guid = fx.hex_literal("1A2B3C4D"), fx.hex_literal("ABABABAB")
        path = "components/core/src/modkit/core/a.py"
        self.put(path, f"A = {lit}\nB = {guid}\nC = {fx.hex_literal('FFF')}\n")
        found = hygiene.scan_tree(self.root)
        self.assertEqual({(f.rule, f.text, f.line) for f in found}, {("address", lit, 1), ("address", guid, 2)})
        self.allow((path, guid, "file magic: format tag"))
        found = hygiene.scan_tree(self.root)
        self.assertEqual([(f.rule, f.text) for f in found], [("address", lit)])

    def test_allowlist_is_exact(self):
        path = "components/core/src/modkit/core/a.py"
        self.put(path, f"A = {fx.hex_literal('ABABABAB')}\n")
        self.allow((path, fx.hex_literal("ABABABAC"), "r"))
        self.assertEqual(self.rules(), ["address"])
        self.allow(("components/core/src/modkit/core/other.py", fx.hex_literal("ABABABAB"), "r"))
        self.assertEqual(self.rules(), ["address"])

    def test_allowlist_entry_needs_a_reason(self):
        self.allow(("a/b.py", "x", ""))
        with self.assertRaises(ValueError):
            hygiene.scan_tree(self.root)

    def test_stale_allowlist_entries_are_reported(self):
        path = "components/core/src/modkit/core/a.py"
        self.put(path, "A = 1\n")
        self.allow((path, fx.hex_literal("ABABABAB"), "r"), ("components/core/gone.py", "x", "r"))
        self.assertEqual(len(hygiene.stale_allowlist(self.root)), 2)

    def test_address_words(self):
        words = ["vt" + "able", "rv" + "a", "sl" + "ot", "sl" + "ot 12"]
        for i, w in enumerate(words):
            self.put(f"components/core/src/modkit/core/w{i}.py", f"# the {w} of it\n")
        # (identifier parts count: rva2off and vtables_x used to pass and are now flagged; whole other words pass)
        self.put("components/core/src/modkit/core/ok.py", "# conservative, observation, slotted are other words\n")
        found = hygiene.scan_tree(self.root)
        self.assertEqual({f.path for f in found if f.rule == "address"},
                         {f"components/core/src/modkit/core/w{i}.py" for i in range(4)})

    def test_private_ref_fails(self):
        name = "un" + "its"
        self.put("components/core/src/modkit/core/a.py", f"import modkit.{name}\nimport modkit.core.paths\n")
        self.put("components/core/notes.txt", f"dep modkit-{name} and modkit.local.toml and modkit-data\n")
        found = [f for f in hygiene.scan_tree(self.root) if f.rule == "private-ref"]
        self.assertEqual(sorted(Path(f.path).name for f in found), ["a.py", "notes.txt"])

    def test_private_ref_in_manifests(self):
        fx.write(self.root / "components/core/.claude-plugin/plugin.json",
                 '{"name": "warno-core", "dependencies": ["warno-%s"]}' % ("vid" + "eo"))
        found = [f for f in hygiene.scan_tree(self.root) if f.rule == "private-ref"]
        self.assertEqual([f.path for f in found], ["components/core/.claude-plugin/plugin.json"])

    def test_manifest_personal(self):
        fx.write(self.root / ".claude-plugin/marketplace.json",
                 '{"name": "warno-modkit", "owner": {"name": "Some Person", "email": "a@b.invalid"}, "plugins": []}')
        fx.write(self.core / ".claude-plugin/plugin.json",
                 '{"name": "warno-core", "author": {"name": "warno-modkit contributors"}}')
        found = [f for f in hygiene.scan_tree(self.root) if f.rule == "manifest-personal"]
        self.assertTrue(found)
        self.assertTrue(all(f.path == ".claude-plugin/marketplace.json" for f in found))

    def test_generic_manifest_owner_passes(self):
        fx.write(self.root / ".claude-plugin/marketplace.json",
                 '{"name": "warno-modkit", "owner": {"name": "warno-modkit contributors"}, "plugins": []}')
        self.assertEqual(hygiene.scan_tree(self.root), [])

    def test_dot_claude_is_scanned_and_build_is_skipped(self):
        self.put(".claude/notes.md", f"see {fx.user_path()}\n")
        self.put("build/out.txt", f"see {fx.user_path()}\n")
        self.put("modkit-data/x.txt", f"see {fx.user_path()}\n")
        found = hygiene.scan_tree(self.root)
        self.assertEqual([f.path for f in found], [".claude/notes.md"])

    def test_binary_file_is_scanned(self):
        self.put("components/core/examples/blob.bin", b"\x00\x01junk " + fx.user_path().encode() + b"\x00\x02")
        self.assertEqual(self.rules(), ["local-path"])


class History(Fixture):
    def test_history_scan_finds_deleted_leak(self):
        fx.git_init(self.root)
        fx.commit_all(self.root, "base")
        leak = self.put("components/core/src/modkit/core/leak.py", f'P = "{fx.user_path()}"\n')
        self.put("components/core/examples/stock.ndfbin", b"\0")
        fx.commit_all(self.root, "add leak")
        leak.unlink()
        (self.root / "components/core/examples/stock.ndfbin").unlink()
        fx.commit_all(self.root, "remove leak")
        self.assertEqual(hygiene.scan_tree(self.root), [])
        found = hygiene.scan_history(self.root)
        self.assertEqual({(f.rule, Path(f.path).name) for f in found},
                         {("local-path", "leak.py"), ("stock-extension", "stock.ndfbin")})
        self.assertTrue(all(f.commit for f in found))

    def test_history_respects_the_allowlist(self):
        fx.git_init(self.root)
        path = "components/core/src/modkit/core/a.py"
        self.put(path, f"A = {fx.hex_literal('ABABABAB')}\n")
        fx.commit_all(self.root)
        self.assertEqual(self.rules(hygiene.scan_history(self.root)), ["address"])
        self.allow((path, fx.hex_literal("ABABABAB"), "file magic: tag"))
        self.assertEqual(hygiene.scan_history(self.root), [])

    def test_history_scans_commit_authors_and_messages_for_personal_strings(self):
        fx.git_init(self.root)
        self.put("components/core/a.txt", "x")
        fx.commit_all(self.root, "by Someone Private")
        fx.write(self.root / "modkit.local.toml", 'deny = ["someone-private"]\n')
        found = hygiene.scan_history(self.root)
        self.assertEqual([f.rule for f in found], ["deny"])


def segment(marker, payload=b""):
    return b"\xff" + bytes([marker]) + (len(payload) + 2).to_bytes(2, "big") + payload


def make_jpeg(*extra, scan=b"\x12\x34\x56"):
    """A minimal JPEG assembled from a few bytes: SOI, APP0 JFIF, DQT, SOF0, DHT, SOS, scan data, EOI."""
    jfif = segment(0xE0, b"JFIF\0\1\1\0\0\1\0\1\0\0")
    body = segment(0xDB, b"\0" + bytes(range(1, 65))) + segment(0xC0, b"\x08\0\1\0\1\1\1\x11\0")
    body += segment(0xC4, b"\0" + bytes(16) + b"\0") + segment(0xDA, b"\1\1\0\0\x3f\0")
    return b"\xff\xd8" + jfif + b"".join(extra) + body + scan + b"\xff\xd9"


SHOT = "docs/screenshots/scene-one.jpg"
LISTED = "# Screenshots\n\n## Screenshots\n\n- `scene-one.jpg`: the intro scene of the first mission\n"


class Screenshots(Fixture):
    def shot(self, data, readme=LISTED, rel=SHOT):
        self.put(rel, data)
        if readme is not None:
            self.put(hygiene.SCREENSHOT_README, readme)
        return [(f.rule, f.text) for f in hygiene.scan_tree(self.root) if f.path == rel]

    def test_listed_clean_jpeg_passes(self):
        self.assertEqual(self.shot(make_jpeg()), [])

    def test_exif_segment_fails(self):
        found = self.shot(make_jpeg(segment(0xE1, b"Exif\0\0")))
        self.assertEqual([r for r, _ in found], ["screenshot"])
        self.assertIn("APP1", found[0][1])

    def test_xmp_iptc_and_comment_fail(self):
        for marker in (0xE1, 0xED, 0xFE):
            self.assertEqual([r for r, _ in self.shot(make_jpeg(segment(marker, b"x")))], ["screenshot"], marker)

    def test_jfif_and_icc_are_allowed(self):
        self.assertEqual(self.shot(make_jpeg(segment(0xE2, b"ICC_PROFILE\0\1\1"))), [])

    def test_not_listed_fails(self):
        for readme in (None, "# Screenshots\n", "- `other.jpg`: another\n", "- `scene-one.jpg`\n",
                       "- `old-scene-one.jpg`: a different file\n"):
            (self.root / hygiene.SCREENSHOT_README).unlink(missing_ok=True)
            found = self.shot(make_jpeg(), readme)
            self.assertEqual([r for r, _ in found], ["screenshot"], readme)
            self.assertIn("not listed", found[0][1])

    def test_non_jpeg_bytes_fail(self):
        for data in (b"\x89PNG\r\n\x1a\n" + bytes(20), b"plain text, not a picture\n", b""):
            self.assertEqual([r for r, _ in self.shot(data)], ["screenshot"], data)

    def test_truncated_jpeg_fails(self):
        self.assertEqual([r for r, _ in self.shot(make_jpeg()[:12])], ["screenshot"])

    def test_scan_bytes_do_not_trigger_the_text_rules(self):
        scan = bytes([0x12]) + b"C:" + bytes([92]) + fx.user_path().encode() + fx.hex_literal("12345").encode()
        self.assertEqual(self.shot(make_jpeg(scan=scan)), [])

    def test_png_in_the_folder_is_still_stock(self):
        found = self.shot(b"\x89PNG\r\n\x1a\n", rel="docs/screenshots/a.png")
        self.assertEqual(found, [("stock-extension", "a.png")])

    def test_jpeg_outside_the_folder_is_still_stock(self):
        for rel in ("docs/a.jpg", "docs/screenshots/sub/a.jpg", "screenshots/a.jpg", "docs/screenshots/a.JPG"):
            found = self.shot(make_jpeg(), rel=rel)
            self.assertIn("stock-extension", [r for r, _ in found], rel)

    def test_oversize_jpeg_is_still_size(self):
        big = make_jpeg(scan=bytes(hygiene.MAX_BYTES))
        self.assertEqual([r for r, _ in self.shot(big)], ["size"])

    def test_deny_on_the_path_still_runs(self):
        self.deny("scene one")
        self.assertEqual([r for r, _ in self.shot(make_jpeg())], ["deny"])

    def test_other_app_segments_fail_and_name_the_marker(self):
        for marker in range(0xE1, 0xF0):
            if marker == 0xE2 or marker == 0xEE:
                continue
            found = self.shot(make_jpeg(segment(marker, b"Ducky")))
            self.assertEqual([r for r, _ in found], ["screenshot"], marker)
            self.assertIn(f"APP{marker - 0xE0}", found[0][1])
        self.assertIn("APP12", self.shot(make_jpeg(segment(0xEC, b"Ducky")))[0][1])

    def test_adobe_app14_and_icc_app2_pass(self):
        adobe = segment(0xEE, b"Adobe\0\x64\0\0\0\0\1")
        self.assertEqual(self.shot(make_jpeg(adobe, segment(0xE2, b"ICC_PROFILE\0\1\1"))), [])

    def test_a_segment_between_two_scans_is_checked(self):
        second_scan = segment(0xDA, b"\1\1\0\0\x3f\0") + b"\x01\xff\x00\x02\xff\xd0\x03"
        for extra, expect in ((b"", []), (segment(0xE1, b"Exif\0\0"), ["screenshot"])):
            data = make_jpeg()[:-2] + extra + second_scan + b"\xff\xd9"
            self.assertEqual([r for r, _ in self.shot(data)], expect, extra)

    def test_bytes_after_eoi_fail(self):
        found = self.shot(make_jpeg() + b"\0")
        self.assertEqual(found, [("screenshot", "data after EOI")])
        self.assertEqual(self.shot(make_jpeg() + segment(0xE1, b"Exif\0\0"))[0][0], "screenshot")

    def test_a_file_with_no_eoi_fails(self):
        found = self.shot(make_jpeg()[:-2])
        self.assertEqual(found, [("screenshot", "malformed JPEG segments")])

    def test_history_applies_the_same_rule(self):
        fx.git_init(self.root)
        self.put(hygiene.SCREENSHOT_README, LISTED)
        self.put(SHOT, make_jpeg())
        fx.commit_all(self.root, "clean")
        self.assertEqual(hygiene.scan_history(self.root), [])
        self.put("docs/screenshots/scene-exif.jpg", make_jpeg(segment(0xE1, b"Exif\0\0")))
        self.put("docs/screenshots/scene-bare.jpg", make_jpeg())
        self.put(SHOT, make_jpeg(scan=fx.user_path().encode() + fx.hex_literal("12345").encode()))
        fx.commit_all(self.root, "unlisted and tagged")
        (self.root / "docs/screenshots/scene-exif.jpg").unlink()
        (self.root / "docs/screenshots/scene-bare.jpg").unlink()
        fx.commit_all(self.root, "removed again")
        found = {(Path(f.path).name, f.rule) for f in hygiene.scan_history(self.root)}
        self.assertEqual(found, {("scene-exif.jpg", "screenshot"), ("scene-bare.jpg", "screenshot")})


class Repocheck(Fixture):
    def run_check(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = repocheck.main([*argv, str(self.root)])
        return code, out.getvalue()

    def test_clean_repo_exits_zero(self):
        fx.git_init(self.root)
        fx.commit_all(self.root)
        code, out = self.run_check("--history")
        self.assertEqual(code, 0, out)

    def test_findings_exit_nonzero_and_print(self):
        self.put("components/core/a.py", f'P = "{fx.user_path()}"\n')
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("local-path", out)

    def test_component_problems_exit_nonzero(self):
        (self.core / "pyproject.toml").unlink()
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("pyproject.toml", out)

    def test_private_repo_skips_the_hygiene_gates(self):
        fx.write(self.root / "modkit.repo.toml", 'visibility = "private"\n')
        self.put("components/core/a.py", f'P = "{fx.user_path()}"\n')
        code, _ = self.run_check()
        self.assertEqual(code, 0)


class ThisRepo(unittest.TestCase):
    def test_this_repository_passes_every_check(self):
        root = next((p for p in Path(__file__).resolve().parents if (p / "modkit.repo.toml").is_file()), None)
        if root is None:
            self.skipTest("not running inside the warno-modkit clone")
        self.assertEqual(repocheck.run(root, history=True), [])


if __name__ == "__main__":
    unittest.main()
