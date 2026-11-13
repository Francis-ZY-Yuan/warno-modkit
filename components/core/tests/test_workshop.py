"""Tests for modkit.core.workshop: an item.toml loaded and validated offline, its description rendered, a live item
compared field by field, and the CLI's exit codes. No network: every Steam call goes to a fake opener, and the
local config is a temporary modkit.local.toml (or none)."""
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest import mock

from modkit.core import paths, workshop

ITEM_ID = 2000000001
TEMPLATE = "[h1]Demo[/h1]\nSource: [url=https://{{repo}}]{{repo}}[/url]\n\n"
REPO = "example.org/owner/demo"
RENDERED = "[h1]Demo[/h1]\nSource: [url=https://example.org/owner/demo]example.org/owner/demo[/url]"
PREVIEW = b"\xff\xd8\xff\xe0 a preview"
PREVIEW_URL = "https://images.example.org/preview"


def _toml(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml(v) for v in value) + "]"
    return json.dumps(value)


def make_item(root: Path, template: str = TEMPLATE, preview_bytes: bytes = PREVIEW, **fields) -> Path:
    """An item folder with every file present; ``fields`` override or (with None) drop item.toml's fields."""
    values = {"id": ITEM_ID, "mod_name": "DemoMod", "title": "Operation Demo", "description": "description.bbcode",
              "preview": "preview.jpg", "gallery": ["gallery/01.jpg", "gallery/02.jpg"], "vars": ["repo"]}
    values.update(fields)
    root.mkdir(parents=True, exist_ok=True)
    (root / "gallery").mkdir(exist_ok=True)
    for g in ("01.jpg", "02.jpg"):
        (root / "gallery" / g).write_bytes(PREVIEW)
    (root / "description.bbcode").write_text(template, encoding="utf-8", newline="\n")
    (root / "preview.jpg").write_bytes(preview_bytes)
    toml = root / "item.toml"
    toml.write_text("".join(f"{k} = {_toml(v)}\n" for k, v in values.items() if v is not None), encoding="utf-8")
    return toml


def live_item(**fields) -> dict:
    """A found item as GetPublishedFileDetails returns it, matching make_item's defaults."""
    out = {"publishedfileid": str(ITEM_ID), "result": 1, "title": "Operation Demo",
           "description": RENDERED.replace("\n", "\r\n"), "preview_url": PREVIEW_URL, "visibility": 0,
           "time_created": 1762905600, "time_updated": 1762992000, "file_size": "12345", "subscriptions": 7,
           "lifetime_subscriptions": 9, "favorited": 2, "views": 40}
    out.update(fields)
    return {k: v for k, v in out.items() if v is not None}


class FakeOpener:
    """Stands in for urllib.request.urlopen: answers the API with ``details`` and any other URL with ``files``."""

    def __init__(self, details=None, files=None, body: bytes | None = None, error: Exception | None = None):
        self.details = [live_item()] if details is None else details
        self.files = {PREVIEW_URL: PREVIEW} if files is None else files
        self.body = body
        self.error = error
        self.requests = []

    def __call__(self, request, timeout=None):
        self.requests.append((request, timeout))
        if self.error is not None:
            raise self.error
        if request.full_url == workshop.API_URL:
            body = self.body
            if body is None:
                body = json.dumps({"response": {"result": 1, "resultcount": len(self.details),
                                                "publishedfiledetails": self.details}}).encode()
            return io.BytesIO(body)
        if request.full_url in self.files:
            return io.BytesIO(self.files[request.full_url])
        raise urllib.error.HTTPError(request.full_url, 404, "Not Found", None, None)


class Env(unittest.TestCase):
    """A temporary folder, and no modkit.local.toml unless a test writes one with ``set_vars``."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        self.config = None
        patcher = mock.patch.object(paths, "_find_config", side_effect=lambda: self.config)
        patcher.start()
        self.addCleanup(patcher.stop)

    def set_vars(self, text: str = f'[workshop.vars]\nrepo = "{REPO}"\n') -> None:
        self.config = self.root / paths.CONFIG_NAME
        self.config.write_text(text, encoding="utf-8")

    def item(self, **kw) -> workshop.Item:
        return workshop.load_item(make_item(self.root / "item", **kw))


class Load(Env):
    def test_fields_and_paths_relative_to_the_toml(self):
        item = self.item()
        folder = self.root / "item"
        self.assertEqual((item.id, item.mod_name, item.title), (ITEM_ID, "DemoMod", "Operation Demo"))
        self.assertEqual(item.template, TEMPLATE)
        self.assertEqual(item.preview, folder / "preview.jpg")
        self.assertEqual(item.gallery, (folder / "gallery/01.jpg", folder / "gallery/02.jpg"))
        self.assertEqual(item.vars, ("repo",))
        self.assertEqual(item.description, folder / "description.bbcode")

    def test_missing_field(self):
        for name in ("id", "mod_name", "title", "description", "preview", "gallery", "vars"):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, f"missing field '{name}'"):
                self.item(**{name: None})

    def test_mistyped_field(self):
        for name, value in (("id", "42"), ("id", True), ("title", 5), ("gallery", "a.jpg"), ("gallery", [1]),
                            ("vars", "repo")):
            with self.subTest(name=name, value=value), self.assertRaisesRegex(ValueError, f"'{name}' must be"):
                self.item(**{name: value})

    def test_unknown_field(self):
        with self.assertRaisesRegex(ValueError, "unknown field.*galery"):
            self.item(galery=["a.jpg"])

    def repo(self, name: str, marker: str) -> Path:
        """A repository root marked by ``marker`` (a .git folder or file, or modkit.repo.toml) with docs/p.jpg."""
        root = self.root / name
        (root / "docs").mkdir(parents=True)
        (root / "docs" / "p.jpg").write_bytes(PREVIEW)
        if marker == ".git/":
            (root / ".git").mkdir()
        else:
            (root / marker).write_text("", encoding="utf-8")
        return root

    def test_a_slash_path_is_from_the_repository_root(self):
        for n, marker in enumerate((".git/", ".git", "modkit.repo.toml")):
            with self.subTest(marker=marker):
                root = self.repo(f"r{n}", marker)
                toml = make_item(root / "components" / "x" / "item", preview="/docs/p.jpg",
                                 gallery=["/docs/p.jpg", "gallery/01.jpg"])
                item = workshop.load_item(toml)
                self.assertEqual(workshop.repo_root(toml), root)
                self.assertEqual(item.preview, root / "docs" / "p.jpg")
                self.assertEqual(item.gallery, (root / "docs" / "p.jpg", toml.parent / "gallery" / "01.jpg"))
                self.assertEqual(workshop.validate(item), [])
                item = workshop.load_item(make_item(toml.parent, preview="/docs/q.jpg"))
                self.assertEqual(workshop.validate(item), ["preview: /docs/q.jpg not found"])

    def test_the_nearest_root_wins(self):
        outer = self.repo("outer", "modkit.repo.toml")
        inner = self.repo("outer/inner", ".git")
        self.assertEqual(workshop.repo_root(make_item(inner / "item")), inner)
        self.assertEqual(workshop.repo_root(make_item(outer / "item")), outer)

    def test_a_slash_path_without_a_root(self):
        if workshop.repo_root(self.root / "item" / "item.toml") is not None:
            self.skipTest("the temporary folder is inside a repository")
        self.assertEqual(self.item().preview, self.root / "item" / "preview.jpg")  # no root needed
        with self.assertRaisesRegex(ValueError, "'/docs/p.jpg' is from the repository root, but no folder above"):
            self.item(preview="/docs/p.jpg")

    def test_absent_toml_is_an_os_error(self):
        with self.assertRaises(OSError):
            workshop.load_item(self.root / "nope.toml")


class Validate(Env):
    def test_a_good_item_has_no_problems(self):
        self.assertEqual(workshop.validate(self.item()), [])

    def test_id(self):
        self.assertEqual(workshop.validate(self.item(id=1)), [])
        self.assertIn("id: 0 is not a Workshop item ID", workshop.validate(self.item(id=0)))

    def test_title(self):
        self.assertEqual(workshop.validate(self.item(title="t" * workshop.MAX_TITLE)), [])
        self.assertIn("title: empty", workshop.validate(self.item(title="")))
        self.assertIn("title: 129 characters, over Steam's 128", workshop.validate(self.item(title="t" * 129)))

    def test_description_present_and_short_enough(self):
        self.assertEqual(workshop.validate(self.item(template="x" * workshop.MAX_DESCRIPTION, vars=[])), [])
        self.assertIn("description: 8001 characters, over Steam's 8000",
                      workshop.validate(self.item(template="x" * 8001, vars=[])))
        item = self.item(description="other.bbcode", vars=[])
        self.assertEqual(item.template, "")
        self.assertEqual(workshop.validate(item), ["description: other.bbcode not found"])

    def test_preview(self):
        self.assertEqual(workshop.validate(self.item(preview_bytes=b"x" * workshop.MAX_PREVIEW_BYTES)), [])
        self.assertIn("preview: 1048577 bytes, over Steam's 1048576",
                      workshop.validate(self.item(preview_bytes=b"x" * (workshop.MAX_PREVIEW_BYTES + 1))))
        self.assertIn("preview: missing.jpg not found", workshop.validate(self.item(preview="missing.jpg")))
        (self.root / "item").mkdir(exist_ok=True)
        (self.root / "item" / "preview.bmp").write_bytes(PREVIEW)
        self.assertEqual(workshop.validate(self.item(preview="preview.bmp")),
                         ["preview: preview.bmp is not one of .jpg, .jpeg, .png, .gif"])
        for suffix in (".JPG", ".jpeg", ".png", ".gif"):
            with self.subTest(suffix=suffix):
                (self.root / "item" / f"p{suffix}").write_bytes(PREVIEW)
                self.assertEqual(workshop.validate(self.item(preview=f"p{suffix}")), [])

    def test_gallery(self):
        self.assertEqual(workshop.validate(self.item(gallery=[])), [])
        self.assertEqual(workshop.validate(self.item(gallery=["gallery/01.jpg", "gallery/09.jpg"])),
                         ["gallery: gallery/09.jpg not found"])

    def test_placeholders_and_vars(self):
        self.assertEqual(workshop.validate(self.item(template="no placeholder", vars=[])), [])
        self.assertEqual(workshop.validate(self.item(template="{{repo}} {{owner}}")),
                         ["description: {{owner}} is not in vars"])
        self.assertEqual(workshop.validate(self.item(template="{{repo}}", vars=["repo", "spare"])),
                         ["vars: 'spare' is not used in the description"])
        self.assertEqual(workshop.validate(self.item(template="{{repo}} {{ repo }}")),
                         ["description: {{ repo }} is not a placeholder (write {{name}})"])


class LocalVars(Env):
    def test_absent(self):
        self.assertEqual(workshop.local_vars(), {})
        self.set_vars('extracted = "x"\n')
        self.assertEqual(workshop.local_vars(), {})

    def test_read_from_the_config_paths_finds(self):
        self.set_vars()
        self.assertEqual(workshop.local_vars(), {"repo": REPO})

    def test_mistyped(self):
        self.set_vars("[workshop.vars]\nrepo = 5\n")
        with self.assertRaisesRegex(ValueError, r"\[workshop.vars\] must hold strings"):
            workshop.local_vars()


class Render(Env):
    def test_fills_every_placeholder_and_strips_trailing_newlines(self):
        self.assertEqual(workshop.render(self.item(), {"repo": REPO, "unused": "x"}), RENDERED)
        self.assertEqual(workshop.render(self.item(template="a\n\nb\r\n\n", vars=[]), {}), "a\n\nb")

    def test_missing_value_is_named(self):
        with self.assertRaisesRegex(ValueError, r"no value for \{\{owner\}\}, \{\{repo\}\}"):
            workshop.render(self.item(template="{{repo}} {{owner}}", vars=["repo", "owner"]), {})


class Fetch(unittest.TestCase):
    def test_posts_the_ids_and_returns_the_details(self):
        opener = FakeOpener(details=[live_item(), {"publishedfileid": "7", "result": 9}])
        details = workshop.fetch([ITEM_ID, 7], opener=opener, timeout=5)
        self.assertEqual([d["result"] for d in details], [1, 9])
        (request, timeout), = opener.requests
        self.assertEqual((request.full_url, request.get_method(), timeout), (workshop.API_URL, "POST", 5))
        form = urllib.parse.parse_qs(request.data.decode())
        self.assertEqual(form, {"itemcount": ["2"], "publishedfileids[0]": [str(ITEM_ID)],
                                "publishedfileids[1]": ["7"]})

    def test_an_unexpected_answer(self):
        for body in (b"<html>", b'{"response": {}}', b'{"response": {"publishedfiledetails": [1]}}'):
            with self.subTest(body=body), self.assertRaises(workshop.FetchError):
                workshop.fetch([ITEM_ID], opener=FakeOpener(body=body))

    def test_a_network_error_is_an_os_error(self):
        with self.assertRaises(OSError):
            workshop.fetch([ITEM_ID], opener=FakeOpener(error=urllib.error.URLError("offline")))


class Compare(Env):
    def diffs(self, live=None, description=RENDERED, preview=PREVIEW, **kw) -> dict[str, workshop.Diff]:
        out = workshop.compare(self.item(**kw), live_item() if live is None else live, description, preview)
        return {d.field: d for d in out}

    def test_everything_matches(self):
        diffs = self.diffs()
        self.assertEqual(list(diffs), ["item", "title", "description", "preview", "visibility", "gallery"])
        self.assertTrue(all(d.ok for d in diffs.values()), diffs)

    def test_item_not_found(self):
        self.assertEqual(list(self.diffs(live={"publishedfileid": str(ITEM_ID), "result": 9}).values()),
                         [workshop.Diff("item", False, f"{ITEM_ID} not found (result 9)")])
        self.assertFalse(self.diffs(live=live_item(publishedfileid="7"))["item"].ok)

    def test_title(self):
        diff = self.diffs(live=live_item(title="Operation Demo "))["title"]
        self.assertFalse(diff.ok)
        self.assertNotIn("reset", diff.detail)
        diff = self.diffs(live=live_item(title="DemoMod"))["title"]
        self.assertFalse(diff.ok)
        self.assertIn("an upload reset it to mod_name", diff.detail)

    def test_description(self):
        self.assertTrue(self.diffs(live=live_item(description=RENDERED))["description"].ok)  # LF as well as CRLF
        diff = self.diffs(live=live_item(description=RENDERED.replace("Demo[", "Demo![")))["description"]
        self.assertFalse(diff.ok)
        self.assertIn("line 1 differs", diff.detail)
        diff = self.diffs(live=live_item(description=RENDERED + "\r\n"))["description"]
        self.assertFalse(diff.ok)
        self.assertIn("live has 3 lines, local 2", diff.detail)
        diff = self.diffs(description=None)["description"]
        self.assertFalse(diff.ok)
        self.assertIn("not compared", diff.detail)

    def test_preview(self):
        self.assertIn(hashlib.sha256(PREVIEW).hexdigest()[:12], self.diffs()["preview"].detail)
        self.assertFalse(self.diffs(preview=PREVIEW + b"!")["preview"].ok)
        self.assertFalse(self.diffs(preview=None)["preview"].ok)
        diff = self.diffs(live=live_item(preview_url=None))["preview"]
        self.assertEqual((diff.ok, diff.detail), (False, "the live item has no preview_url"))

    def test_visibility_is_reported_only(self):
        for value, name in ((0, "public"), (1, "friends-only"), (2, "private"), (3, "unlisted"), (8, "unknown (8)")):
            with self.subTest(value=value):
                self.assertEqual(self.diffs(live=live_item(visibility=value))["visibility"],
                                 workshop.Diff("visibility", True, name))

    def test_gallery_is_never_checked(self):
        diff = self.diffs()["gallery"]
        self.assertTrue(diff.ok)
        self.assertTrue(diff.detail.startswith("not checked"))
        self.assertIn("2 local ones", diff.detail)


class Cli(Env):
    def run_main(self, *argv, opener=None) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = workshop.main(list(argv), opener=opener or FakeOpener(error=AssertionError("no network")))
        return code, out.getvalue(), err.getvalue()

    def toml(self, **kw) -> str:
        return str(make_item(self.root / "item", **kw))

    def test_check_offline(self):
        code, out, _ = self.run_main("check", self.toml(), "--offline")
        self.assertEqual(code, 0, out)
        self.assertIn("info  vars: no value for {{repo}}: add it under [workshop.vars] in modkit.local.toml", out)
        self.set_vars()
        code, out, _ = self.run_main("check", self.toml(), "--offline")
        self.assertEqual(code, 0, out)
        self.assertNotIn("vars:", out)
        code, out, _ = self.run_main("check", self.toml(title="t" * 129), "--offline")
        self.assertEqual(code, 1)
        self.assertIn("FAIL  title: 129 characters", out)
        code, out, _ = self.run_main("check", self.toml(id="42"), "--offline")
        self.assertEqual(code, 1)
        code, _, err = self.run_main("check", str(self.root / "nope.toml"), "--offline")
        self.assertEqual(code, 2)
        self.assertIn("error:", err)

    def test_check_online_all_match(self):
        self.set_vars()
        opener = FakeOpener()
        code, out, _ = self.run_main("check", self.toml(), opener=opener)
        self.assertEqual(code, 0, out)
        for field in ("item", "title", "description", "preview"):
            self.assertIn(f"ok    {field}: ", out)
        self.assertIn("info  visibility: public", out)
        self.assertIn("info  gallery: not checked", out)
        self.assertEqual([r.full_url for r, _ in opener.requests], [workshop.API_URL, PREVIEW_URL])

    def test_check_online_mismatches_say_what_to_do(self):
        self.set_vars()
        opener = FakeOpener(details=[live_item(title="DemoMod")], files={PREVIEW_URL: b"another image"})
        code, out, _ = self.run_main("check", self.toml(), opener=opener)
        self.assertEqual(code, 1)
        self.assertRegex(out, r"FAIL  title: .*-> re-apply it on the item's \"Edit title & description\" page "
                              r"\(every upload resets the title to mod_name, 'DemoMod'\)")
        self.assertRegex(out, r"FAIL  preview: .*-> point PreviewImagePath in the installed mod's Config.ini at a "
                              r"copy of preview.jpg outside the mod folder, at a path without your user name, and "
                              r"upload again")
        self.assertIn("ok    description: ", out)

    def test_check_online_missing_var(self):
        code, out, _ = self.run_main("check", self.toml(), opener=FakeOpener())
        self.assertEqual(code, 1)
        self.assertIn("FAIL  description: not compared: the description could not be rendered -> no value for "
                      "{{repo}}: add it under [workshop.vars] in modkit.local.toml", out)

    def test_check_online_not_found(self):
        self.set_vars()
        opener = FakeOpener(details=[{"publishedfileid": str(ITEM_ID), "result": 9}])
        code, out, _ = self.run_main("check", self.toml(), opener=opener)
        self.assertEqual(code, 1)
        self.assertIn(f"FAIL  item: {ITEM_ID} not found (result 9)", out)
        self.assertEqual(len(opener.requests), 1)

    def test_check_network_errors(self):
        self.set_vars()
        for opener in (FakeOpener(error=urllib.error.URLError("offline")), FakeOpener(body=b"<html>"),
                       FakeOpener(files={})):
            with self.subTest(opener=opener):
                code, _, err = self.run_main("check", self.toml(), opener=opener)
                self.assertEqual(code, 2)
                self.assertIn("error:", err)

    def test_render(self):
        self.set_vars()
        code, out, _ = self.run_main("render", self.toml())
        self.assertEqual((code, out), (0, RENDERED))

    def test_render_missing_var(self):
        code, out, err = self.run_main("render", self.toml())
        self.assertEqual((code, out), (1, ""))
        self.assertIn("no value for {{repo}}: add it under [workshop.vars] in modkit.local.toml", err)

    def test_status(self):
        opener = FakeOpener(details=[live_item(), {"publishedfileid": "7", "result": 9}])
        code, out, _ = self.run_main("status", str(ITEM_ID), opener=opener)
        self.assertEqual(code, 0, out)
        self.assertEqual(out.splitlines(), [
            f"{ITEM_ID}: Operation Demo", "  visibility: public", "  created: 2025-11-12T00:00:00Z",
            "  updated: 2025-11-13T00:00:00Z", "  file_size: 12345", "  subscriptions: 7",
            "  lifetime_subscriptions: 9", "  favorited: 2", "  views: 40"])
        code, out, _ = self.run_main("status", str(ITEM_ID), "7", opener=opener)
        self.assertEqual(code, 1)
        self.assertIn("7: not found (result 9)", out)

    def test_status_network_error(self):
        code, _, err = self.run_main("status", "7", opener=FakeOpener(error=TimeoutError("timed out")))
        self.assertEqual(code, 2)
        self.assertIn("timed out", err)

    def test_usage_errors_exit_2(self):
        for argv in ((), ("check",), ("status",), ("status", "abc"), ("nope",)):
            with self.subTest(argv=argv), contextlib.redirect_stderr(io.StringIO()), \
                    self.assertRaises(SystemExit) as cm:
                workshop.main(list(argv))
            self.assertEqual(cm.exception.code, 2)


CHANGELOG = workshop.CHANGELOG_URL.format(id=ITEM_ID)
DEFAULT = "Game Version = 210942<br>Mod Version = 0"


def page(*notes: tuple[int, str]) -> bytes:
    """A Change Notes page as Steam serves it, newest first."""
    return "".join(f'<div class="changelog headline">Update: Nov 12 @ 2:17pm</div>\n\t<p id="{u}">{t}</p>\n'
                   for u, t in notes).encode()


class Changes(Env):
    """The item's change notes: a changes file, one table per upload, against the Change Notes page."""

    GOOD = '[next]\nnote = "Next"\n[20]\nnote = "[b]Two[/b]\\nlines"\n[10]\nnote = "One"\n'

    def changes(self, text: str) -> workshop.Item:
        root = self.root / "item"
        make_item(root, changes="changes.toml")
        (root / "changes.toml").write_text(text, encoding="utf-8")
        return workshop.load_item(root / "item.toml")

    def test_load(self):
        item = self.changes(self.GOOD)
        self.assertEqual(item.releases, (workshop.Release("Next"), workshop.Release("[b]Two[/b]\nlines", 20),
                                         workshop.Release("One", 10)))

    def test_bad_files(self):
        for text, want in (("[next", "not TOML"),
                           ('note = "x"', r"\[note\]: write each release as a table holding only note"),
                           ('[9]\nnote = "x"\ndate = 1', r"\[9\]: write each release as a table"),
                           ('[next]\nnote = " "', r"\[next\]: note must be a non-empty string"),
                           ('[0]\nnote = "x"', r"\[0\]: name a release by its note's id"),
                           ('[v2]\nnote = "x"', r"\[v2\]: name a release by its note's id"),
                           ('[9]\nnote = "x"\n[next]\nnote = "y"', r"\[next\]: only the first release"),
                           ('[9]\nnote = "x"\n[10]\nnote = "y"', r"\[10\]: not older than the release above it")):
            with self.subTest(text=text), self.assertRaisesRegex(ValueError, "changes.toml: " + want):
                self.changes(text)

    def test_a_missing_file_is_a_problem(self):
        item = workshop.load_item(make_item(self.root / "item", changes="nope.toml"))
        self.assertEqual(item.releases, ())
        self.assertIn("changes: nope.toml not found", workshop.validate(item))

    def test_change_notes(self):
        self.assertEqual(workshop.change_notes(page((20, "A &amp; B<br>\n<b>bold</b>"), (10, DEFAULT)).decode()),
                         [(20, "A & B\n\nbold"), (10, "Game Version = 210942\nMod Version = 0")])

    def diffs(self, text: str, *notes) -> list[tuple[str, bool, str]]:
        found = workshop.compare_changes(self.changes(text), workshop.change_notes(page(*notes).decode()))
        return [(d.field, d.ok, d.detail) for d in found]

    def test_every_release_matches(self):
        """BBCode tags, line ends and blank lines aside; the pending release and older notes are reported only."""
        out = self.diffs(self.GOOD, (20, "<b>Two</b><br>lines"), (10, "One"), (5, DEFAULT))
        self.assertEqual(out, [("changes", True, "2 release(s) match their notes"),
                               ("pending", True, "[next] is not uploaded yet"),
                               ("older notes", True, "1 note(s) older than the newest release have none, not checked")])

    def test_a_new_upload_with_the_default_note(self):
        out = self.diffs(self.GOOD, (30, DEFAULT), (20, "Two<br>lines"), (10, "One"))
        self.assertEqual(out[0][:2], ("changes", False))
        self.assertIn("(update 30) is the game's default note, newer than every release in changes.toml", out[0][2])

    def test_a_note_that_differs_or_is_gone(self):
        out = self.diffs(self.GOOD, (20, DEFAULT))
        self.assertEqual(out, [
            ("changes", False, "[20] (still the game's default): line 1 differs: live "
                               "'Game Version = 210942', local 'Two'"),
            ("changes", False, "[10] is not on the Change Notes page's first page"),
            ("pending", True, "[next] is not uploaded yet")])

    def test_check_and_note_on_the_command_line(self):
        self.set_vars()
        toml = str(self.changes(self.GOOD).path)
        notes = page((30, DEFAULT), (20, "Two<br>lines"), (10, "One"))
        opener = FakeOpener(files={PREVIEW_URL: PREVIEW, CHANGELOG: notes})
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = workshop.main(["check", toml], opener=opener)
        self.assertEqual(code, 1, out.getvalue())
        self.assertRegex(out.getvalue(), r"FAIL  changes: the note of .* \(update 30\) is the game's default note, "
                                         r".*-> paste the \[next\] note \(python -m modkit.core.workshop note .*\) "
                                         r"over it on the item's Change Notes page, then rename \[next\] to \[30\]")
        self.assertEqual([r.full_url for r, _ in opener.requests], [workshop.API_URL, PREVIEW_URL, CHANGELOG])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(workshop.main(["note", toml]), 0)
        self.assertEqual(out.getvalue(), "Next")

    def test_without_changes_the_page_is_not_read(self):
        self.set_vars()
        opener = FakeOpener()
        with contextlib.redirect_stdout(io.StringIO()):
            workshop.main(["check", str(make_item(self.root / "item"))], opener=opener)
        self.assertNotIn(CHANGELOG, [r.full_url for r, _ in opener.requests])


if __name__ == "__main__":
    unittest.main()
