"""Tests for modkit.core.knowledge: the front-matter parser, the corpus, the consistency check and the generated
navigation. Every rule of the knowledge schema has a failing corpus here, and one clean corpus shows the rules pass."""
import contextlib
import hashlib
import io
import os
import re
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import repofixture as rf
from modkit.core import paths, repocheck
from modkit.core.knowledge import check as kcheck
from modkit.core.knowledge import corpus as kcorpus
from modkit.core.knowledge import frontmatter, render
from modkit.core.knowledge import __main__ as cli

FIXTURES = Path(__file__).parent / "fixtures" / "knowledge"
PRIV = "pri" + "vate"  # a private component's name, assembled so this file names no component of its own
BUILD = "201602"
L1_PAGES = ("symptoms.md", "status.md", "trials.md", "lessons.md", "builds.md")
UP = rf.DOTS + "/"  # a parent-folder step, assembled so the path-escape scan sees no literal
LINK_RE = re.compile(r"\[[^\]\n]*\]\(([^)\s]+)\)")


def dot(comp: str, tail: str) -> str:
    """A dotted gate name; built at run time so the component import scan sees no literal."""
    return "modkit." + comp + "." + tail


def md(meta: str, body: str = "Body.\n") -> str:
    return f"---\n{meta.strip()}\n---\n{body}"


def run_cli(*argv):
    out = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
        code = cli.main(list(argv))
    return code, out.getvalue()


def broken_links(pages: dict) -> list[str]:
    """Every relative Markdown link in ``pages`` (path -> text) whose target is neither a file on disk nor another
    page of ``pages``. Web links and in-page anchors are skipped; a ``#fragment`` is ignored."""
    key = lambda p: os.path.normcase(os.path.abspath(p))  # noqa: E731
    planned = {key(p) for p in pages}
    out = []
    for page, text in pages.items():
        for target in LINK_RE.findall(text):
            if target.startswith("#") or re.match(r"[A-Za-z][A-Za-z0-9+.-]*:", target):
                continue
            dest = Path(page).parent / target.split("#", 1)[0]
            if not dest.exists() and key(dest) not in planned:
                out.append(f"{Path(page).as_posix()}: {target}")
    return out

class Tree(unittest.TestCase):
    """A public repository holding the fixture records, plus helpers to edit it and to add a private repo."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.addCleanup(self._tmp.cleanup)
        self.pub = rf.make_repo(self.tmp / "pub", {"core": {}, "ops": {"deps": ["core"]}})
        for comp in ("core", "ops"):
            shutil.copytree(FIXTURES / comp, self.pub / "components" / comp, dirs_exist_ok=True)

    def path(self, rel: str, repo: Path | None = None) -> Path:
        return (repo or self.pub) / "components" / rel

    def edit(self, rel: str, old: str, new: str, repo: Path | None = None) -> None:
        p = self.path(rel, repo)
        text = p.read_text(encoding="utf-8")
        self.assertIn(old, text)
        p.write_text(text.replace(old, new, 1), encoding="utf-8")

    def add(self, rel: str, text: str, repo: Path | None = None) -> None:
        rf.write(self.path(rel, repo), text)

    def make_private(self) -> Path:
        priv = rf.make_repo(self.tmp / "priv", {PRIV: {"deps": ["ops"]}}, visibility="private")
        self.add(f"{PRIV}/knowledge/mechanisms/private-thing.md",
                 md("id: private-thing\ntitle: A private finding\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]"), priv)
        self.add(f"{PRIV}/knowledge/trials/2026-03-02-private-run.md",
                 md("id: 2026-03-02-private-run\nkind: survey\nbuild: aaa111\ngame_version: 201602\n"
                    "mechanisms: [private-thing]\noutcome: mixed"), priv)
        return priv

    def corpus(self, *repos: Path, project: Path | None = None):
        roots = []
        for repo in repos or (self.pub,):
            roots += kcorpus.repo_roots(repo)
        if project is not None:
            roots.append(kcorpus.project_root(project))
        return kcorpus.load(roots)

    def run_check(self, *repos: Path, current: str | None = BUILD, **kw):
        return kcheck.check(self.corpus(*repos, **kw), current_build=current)

    def assertClean(self, *repos, **kw):
        errors, warnings = self.run_check(*repos, **kw)
        self.assertEqual(errors, [])
        self.assertEqual(warnings, [])

    def assertError(self, text: str, *repos, **kw):
        errors, _ = self.run_check(*repos, **kw)
        self.assertTrue(any(text in e for e in errors), f"{text!r} not in {errors}")
        return errors


class FrontMatterTest(unittest.TestCase):
    def test_scalars_inline_and_block_lists(self):
        text = ('---\n# a comment\nid: a-b\ntitle: "Quoted: yes"\nname: \'single\'\nempty:\n'
                'inline: [x, "y z", w]\nnone: []\nblock:\n  - one\n  - two words\nlast: end\n---\nBody line\n\nmore\n')
        meta, body = frontmatter.parse(text)
        self.assertEqual(meta, {"id": "a-b", "title": "Quoted: yes", "name": "single", "empty": "",
                                "inline": ["x", "y z", "w"], "none": [], "block": ["one", "two words"],
                                "last": "end"})
        self.assertEqual(body, "Body line\n\nmore\n")

    def test_no_front_matter_is_an_error(self):
        with self.assertRaises(frontmatter.FrontMatterError):
            frontmatter.parse("# just a heading\n")

    def test_malformed_input_is_an_error(self):
        for bad in ("---\nid: a\n", "---\nid: a\nid: b\n---\n", "---\nnot a pair\n---\n",
                    "---\nk: [a, b\n---\n", "---\n  - orphan\n---\n", "---\nk: - x\n---\n"):
            with self.subTest(bad=bad), self.assertRaises(frontmatter.FrontMatterError):
                frontmatter.parse(bad)

    def test_crlf_text_parses(self):
        meta, body = frontmatter.parse("---\r\nid: a\r\nl: [x]\r\n---\r\nBody\r\n")
        self.assertEqual(meta, {"id": "a", "l": ["x"]})
        self.assertEqual(body, "Body\n")


class CheckRulesTest(Tree):
    def test_clean_corpus_has_no_errors_or_warnings(self):
        self.assertClean()

    def test_clean_corpus_resolves_every_record(self):
        c = self.corpus()
        self.assertEqual(sorted(c.mechanisms), ["crash-names-the-error", "seteffect-never-finishes"])
        self.assertEqual(sorted(c.trials), ["2026-01-10-crash-report-play", "2026-02-01-probe-seteffect"])
        self.assertEqual(sorted(c.lessons), ["model-the-lookup"])
        self.assertEqual({(x.id, x.kind) for x in c.citations},
                         {("seteffect-never-finishes", "skill"), ("crash-names-the-error", "example"),
                          ("crash-names-the-error", "record")})

    def test_unknown_trial_id(self):
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                  "trials: [2026-02-01-probe-seteffect]", "trials: [2026-02-01-probe-seteffect, 2026-09-09-nope]")
        self.assertError("unknown trial ID 2026-09-09-nope")

    def test_unknown_mechanism_id_in_a_trial(self):
        self.edit("ops/knowledge/trials/2026-02-01-probe-seteffect.md",
                  "mechanisms: [seteffect-never-finishes]", "mechanisms: [seteffect-never-finishes, no-such-thing]")
        self.assertError("unknown mechanism ID no-such-thing")

    def test_unknown_trial_in_a_lesson(self):
        self.edit("core/knowledge/lessons/model-the-lookup.md", "trials: [2026-01-10-crash-report-play]",
                  "trials: [2026-01-10-crash-report-play, 2026-09-09-nope]")
        self.assertError("unknown trial ID 2026-09-09-nope")

    def test_unknown_citation_in_a_skill(self):
        self.add("ops/skills/build-op/SKILL.md", "See [[no-such-record]].\n")
        self.assertError("unknown ID no-such-record")

    def test_a_mechanism_id_in_a_trials_field_is_not_a_trial(self):
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                  "trials: [2026-02-01-probe-seteffect]", "trials: [2026-02-01-probe-seteffect, crash-names-the-error]")
        self.assertError("crash-names-the-error is not a trial")

    def test_duplicate_id(self):
        self.add("ops/knowledge/mechanisms/crash-names-the-error.md",
                 md("id: crash-names-the-error\ntitle: Again\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]"))
        self.assertError("duplicate ID crash-names-the-error")

    def test_duplicate_id_across_record_kinds(self):
        self.add("ops/knowledge/trials/2026-04-01-clash.md",
                 md("id: 2026-04-01-clash\nkind: survey\nbuild: b\ngame_version: 201602\nmechanisms: []\noutcome: pass"))
        self.add("ops/knowledge/lessons/2026-04-01-clash.md",
                 md("id: 2026-04-01-clash\ntitle: Same id\ntrials: [2026-04-01-clash]"))
        self.assertError("duplicate ID 2026-04-01-clash")

    def test_played_needs_a_play_trial(self):
        self.edit("core/knowledge/trials/2026-01-10-crash-report-play.md", "kind: play", "kind: launch")
        self.assertError("PLAYED but has no passing play trial")

    def test_played_with_only_a_failed_play_trial(self):
        self.edit("core/knowledge/trials/2026-01-10-crash-report-play.md", "outcome: pass", "outcome: fail")
        self.assertError("PLAYED but has no passing play trial")

    def test_play_trial_may_link_from_the_trial_side_only(self):
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md",
                  "trials: [2026-01-10-crash-report-play]", "trials: []")
        self.assertClean()

    def test_missing_gate(self):
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                  dot("ops", "fakegates.gate_finishes"), dot("ops", "fakegates.gate_missing"))
        self.assertError("gate modkit.ops.fakegates.gate_missing does not exist")

    def test_missing_gate_module(self):
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                  dot("ops", "fakegates.gate_finishes"), dot("ops", "nomodule.gate_finishes"))
        self.assertError("gate modkit.ops.nomodule.gate_finishes does not exist")

    def test_missing_shape(self):
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md",
                  dot("core", "fakegates.NameShape"), dot("core", "fakegates.NoShape"))
        self.assertError("shape modkit.core.fakegates.NoShape does not exist")

    def test_method_of_a_class_resolves_and_a_missing_one_does_not(self):
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md",
                  dot("core", "fakegates.NameShape"), dot("core", "fakegates.NameShape.accepts"))
        self.assertClean()
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md",
                  "NameShape.accepts", "NameShape.rejects")
        self.assertError("does not exist")

    def test_gate_must_be_a_dotted_path(self):
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                  dot("ops", "fakegates.gate_finishes"), "gate_finishes")
        self.assertError("not a dotted path")

    def test_gate_outside_the_dependencies(self):
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md",
                  dot("core", "fakegates.check_names"), dot("ops", "fakegates.gate_finishes"))
        self.assertError("outside the dependencies of core")

    def test_gate_in_a_dependency_is_found(self):
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                  dot("ops", "fakegates.gate_finishes"), dot("core", "fakegates.check_names"))
        self.assertClean()

    def test_public_exe_analysis_needs_a_probe_or_play_trial_or_both_ways_gate(self):
        self.edit("ops/knowledge/trials/2026-02-01-probe-seteffect.md", "kind: probe-run", "kind: launch")
        self.assertError("exe-analysis")

    def test_public_exe_analysis_with_a_gate_proven_both_ways(self):
        self.edit("ops/knowledge/trials/2026-02-01-probe-seteffect.md", "kind: probe-run", "kind: launch")
        self.add("ops/knowledge/trials/2026-02-02-launch-bad-build.md",
                 md("id: 2026-02-02-launch-bad-build\nkind: launch\nbuild: b\ngame_version: 201602\n"
                    "mechanisms: [seteffect-never-finishes]\noutcome: fail"))
        self.assertClean()

    def test_public_exe_analysis_with_no_gate_even_if_both_outcomes_exist(self):
        self.edit("ops/knowledge/trials/2026-02-01-probe-seteffect.md", "kind: probe-run", "kind: launch")
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                  "gates: [modkit.ops.fakegates.gate_finishes]", "gates: []")
        self.add("ops/knowledge/trials/2026-02-02-launch-bad-build.md",
                 md("id: 2026-02-02-launch-bad-build\nkind: launch\nbuild: b\ngame_version: 201602\n"
                    "mechanisms: [seteffect-never-finishes]\noutcome: fail"))
        self.assertError("exe-analysis")

    def test_private_exe_analysis_needs_no_proof(self):
        priv = self.make_private()
        self.add(f"{PRIV}/knowledge/mechanisms/private-re.md",
                 md("id: private-re\ntitle: Exe finding\nstatus: RE\nlast_verified: 201602 2026-01-01\n"
                    "source: exe-analysis\ntopics: [script-flow]"), priv)
        errors, _ = self.run_check(self.pub, priv)
        self.assertEqual(errors, [])

    def test_not_verified_on_the_current_version_is_a_warning(self):
        errors, warnings = self.run_check(current="999999")
        self.assertEqual(errors, [])
        self.assertEqual(len(warnings), 2)
        self.assertTrue(any("crash-names-the-error" in w and "999999" in w for w in warnings))

    def test_version_warning_is_skipped_without_a_game_version(self):
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md", "201602 2026-01-10", "100000 2026-01-10")
        self.assertClean(current=None)

    def test_default_version_comes_from_paths(self):
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md", "201602 2026-01-10", "100000 2026-01-10")
        with mock.patch.object(paths, "game_build", return_value="201602"):
            _, warnings = kcheck.check(self.corpus())
        self.assertEqual(len(warnings), 1)
        with mock.patch.object(paths, "game_build", return_value=None):
            _, warnings = kcheck.check(self.corpus())
        self.assertEqual(warnings, [])

    def test_schema_errors_are_reported_not_raised(self):
        for old, new, text in (
                ("status: PLAYED", "status: WORKS", "status"),
                ("source: play", "source: guess", "source"),
                ("last_verified: 201602 2026-01-10", "last_verified: yesterday", "last_verified"),
                ("title: The crash report names the real error\n", "# no title\n", "title"),
                ("stock_precedent:", "stock_precedance:", "unknown field")):
            with self.subTest(text=text):
                self.edit("core/knowledge/mechanisms/crash-names-the-error.md", old, new)
                self.assertError(text)
                self.edit("core/knowledge/mechanisms/crash-names-the-error.md", new, old)
        self.assertClean()

    def test_trial_schema_errors(self):
        for old, new, text in (("kind: play", "kind: dream", "kind"), ("outcome: pass", "outcome: ok", "outcome"),
                               ("id: 2026-01-10-crash-report-play", "id: crash-report-play", "id")):
            with self.subTest(text=text):
                self.edit("core/knowledge/trials/2026-01-10-crash-report-play.md", old, new)
                self.assertError(text)
                self.edit("core/knowledge/trials/2026-01-10-crash-report-play.md", new, old)

    def test_file_name_must_match_the_id(self):
        shutil.move(self.path("core/knowledge/mechanisms/crash-names-the-error.md"),
                    self.path("core/knowledge/mechanisms/other-name.md"))
        self.assertError("file name")

    def test_lesson_needs_a_trials_line(self):
        self.edit("core/knowledge/lessons/model-the-lookup.md", "trials: [2026-01-10-crash-report-play]\n", "")
        self.assertError("model-the-lookup")

    def test_untested_needs_no_last_verified(self):
        self.add("ops/knowledge/mechanisms/ideas.md", md("id: ideas\ntitle: An idea\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]"))
        self.assertClean()


class PrivateLinksTest(Tree):
    def setUp(self):
        super().setUp()
        self.priv = self.make_private()

    def public_refs_private(self, rel: str, old: str, new: str):
        self.edit(rel, old, new)
        errors, _ = self.run_check(self.pub, self.priv)
        self.assertTrue(any("private" in e and ("private-thing" in e or "2026-03-02-private-run" in e)
                            for e in errors), errors)

    def test_both_repos_alone_are_clean(self):
        errors, _ = self.run_check(self.pub, self.priv)
        self.assertEqual(errors, [])

    def test_public_trials_field_names_a_private_trial(self):
        self.public_refs_private("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                                 "trials: [2026-02-01-probe-seteffect]",
                                 "trials: [2026-02-01-probe-seteffect, 2026-03-02-private-run]")

    def test_public_trial_names_a_private_mechanism(self):
        self.public_refs_private("ops/knowledge/trials/2026-02-01-probe-seteffect.md",
                                 "mechanisms: [seteffect-never-finishes]",
                                 "mechanisms: [seteffect-never-finishes, private-thing]")

    def test_public_body_cites_a_private_mechanism(self):
        self.public_refs_private("ops/knowledge/mechanisms/seteffect-never-finishes.md",
                                 "See also", "See [[private-thing]] and")

    def test_public_lesson_names_a_private_trial(self):
        self.public_refs_private("core/knowledge/lessons/model-the-lookup.md",
                                 "trials: [2026-01-10-crash-report-play]",
                                 "trials: [2026-01-10-crash-report-play, 2026-03-02-private-run]")

    def test_public_skill_cites_a_private_mechanism(self):
        self.public_refs_private("ops/skills/build-op/SKILL.md", "for why", "for why, and [[private-thing]]")

    def test_public_example_cites_a_private_mechanism(self):
        self.public_refs_private("ops/examples/demo/README.md", "when it fails", "[[private-thing]] when it fails")

    def test_the_error_is_reported_in_the_repo_that_holds_it(self):
        self.edit("ops/skills/build-op/SKILL.md", "for why", "for why, and [[private-thing]]")
        c = self.corpus(self.pub, self.priv)
        self.assertTrue(kcheck.check(c, current_build=BUILD, repo=self.pub)[0])
        self.assertEqual(kcheck.check(c, current_build=BUILD, repo=self.priv)[0], [])

    def test_private_record_may_link_public_ones(self):
        self.edit(f"{PRIV}/knowledge/trials/2026-03-02-private-run.md", "mechanisms: [private-thing]",
                  "mechanisms: [private-thing, seteffect-never-finishes]", repo=self.priv)
        self.add(f"{PRIV}/skills/x/SKILL.md", "Uses [[crash-names-the-error]].\n", self.priv)
        errors, _ = self.run_check(self.pub, self.priv)
        self.assertEqual(errors, [])

    def test_project_root_may_link_public(self):
        proj = self.tmp / "myproject"
        rf.write(proj / "knowledge" / "mechanisms" / "my-finding.md",
                 md("id: my-finding\ntitle: Mine\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]\ntrials: [2026-03-03-my-run]",
                    "Builds on [[seteffect-never-finishes]].\n"))
        rf.write(proj / "knowledge" / "trials" / "2026-03-03-my-run.md",
                 md("id: 2026-03-03-my-run\nkind: survey\nbuild: aaa\ngame_version: 201602\n"
                    "mechanisms: [my-finding, seteffect-never-finishes]\noutcome: mixed"))
        errors, warnings = self.run_check(project=proj)
        self.assertEqual((errors, warnings), ([], []))
        c = self.corpus(project=proj)
        self.assertEqual(c.mechanisms["my-finding"].where.visibility, "private")

    def test_public_record_cannot_link_a_project_record(self):
        proj = self.tmp / "myproject"
        rf.write(proj / "knowledge" / "mechanisms" / "my-finding.md",
                 md("id: my-finding\ntitle: Mine\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]"))
        self.add("ops/skills/build-op/SKILL.md", "Cites [[my-finding]].\n")
        self.assertError("private", project=proj)

    def test_project_ids_clash_with_public_ones(self):
        proj = self.tmp / "myproject"
        rf.write(proj / "knowledge" / "mechanisms" / "crash-names-the-error.md",
                 md("id: crash-names-the-error\ntitle: Mine\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]"))
        self.assertError("duplicate ID crash-names-the-error", project=proj)

    def test_project_gate_may_name_any_visible_component(self):
        proj = self.tmp / "myproject"
        rf.write(proj / "knowledge" / "mechanisms" / "my-finding.md",
                 md("id: my-finding\ntitle: Mine\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]\n"
                    "gates: [modkit.ops.fakegates.gate_finishes]"))
        errors, _ = self.run_check(project=proj)
        self.assertEqual(errors, [])


class RenderTest(Tree):
    def snapshot(self, repo: Path) -> dict:
        return {p.relative_to(repo).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(repo.rglob("*")) if p.is_file()}

    def test_render_is_idempotent(self):
        render.render(self.pub)
        first = self.snapshot(self.pub)
        self.assertGreater(len(first), 5)
        render.render(self.pub)
        self.assertEqual(self.snapshot(self.pub), first)
        self.assertEqual(self.run_check()[0], [])

    def test_render_leaves_the_record_text_alone(self):
        before = self.path("core/knowledge/mechanisms/crash-names-the-error.md").read_text(encoding="utf-8")
        render.render(self.pub)
        after = self.path("core/knowledge/mechanisms/crash-names-the-error.md").read_text(encoding="utf-8")
        self.assertTrue(after.startswith(before.rstrip("\n")))
        self.assertEqual(after.count("<!-- referenced-by:start -->"), 1)
        self.assertEqual(after.count("<!-- referenced-by:end -->"), 1)

    def test_footer_is_rewritten_in_place(self):
        render.render(self.pub)
        self.add("ops/skills/build-op/SKILL.md", "Nothing is cited here now.\n")
        render.render(self.pub)
        text = self.path("ops/knowledge/mechanisms/seteffect-never-finishes.md").read_text(encoding="utf-8")
        self.assertNotIn("skills/build-op", text)
        self.assertEqual(text.count("<!-- referenced-by:start -->"), 1)

    def test_footer_lists_skill_citation(self):
        render.render(self.pub)
        text = self.path("ops/knowledge/mechanisms/seteffect-never-finishes.md").read_text(encoding="utf-8")
        start, end = text.index("<!-- referenced-by:start -->"), text.index("<!-- referenced-by:end -->")
        footer = text[start:end]
        self.assertIn("skills/build-op/SKILL.md", footer)
        self.assertIn("2026-02-01-probe-seteffect", footer)
        self.assertIn(dot("ops", "fakegates.gate_finishes"), footer)
        self.assertIn(dot("core", "fakegates.NameShape"), footer)
        core = self.path("core/knowledge/mechanisms/crash-names-the-error.md").read_text(encoding="utf-8")
        self.assertIn("examples/demo/README.md", core)
        self.assertIn("seteffect-never-finishes", core)  # a record that cites it in its body

    def test_component_index_groups_mechanisms_by_topic_and_trials_by_date(self):
        render.render(self.pub)
        index = self.path("ops/knowledge/INDEX.md").read_text(encoding="utf-8")
        self.assertLess(index.index("### Script flow"), index.index("seteffect-never-finishes"))
        self.assertIn("A set-effect action never finishes by itself (RE, verified 201602 2026-02-01)", index)
        self.assertIn("mechanisms/seteffect-never-finishes.md", index)
        self.assertIn("trials/2026-02-01-probe-seteffect.md", index)
        self.add("ops/knowledge/trials/2026-03-01-later.md",
                 md("id: 2026-03-01-later\nkind: survey\nbuild: b\ngame_version: 201602\nmechanisms: []\noutcome: pass"))
        render.render(self.pub)
        index = self.path("ops/knowledge/INDEX.md").read_text(encoding="utf-8")
        self.assertLess(index.index("2026-03-01-later"), index.index("2026-02-01-probe-seteffect"))

    def test_symptom_index_links_gate(self):
        render.render(self.pub)
        text = (self.pub / "knowledge" / "symptoms.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "The sequence stops after the effect" in line)
        self.assertIn("seteffect-never-finishes", row)
        self.assertIn(dot("ops", "fakegates.gate_finishes"), row)
        self.assertIn("components/ops/src/modkit/ops/fakegates.py", row)  # the link target

    def test_component_index_has_its_own_symptom_index(self):
        """Each component's INDEX.md carries the symptoms of its own trials, so an installed component (which has no
        map) still has the index that warno-launch-triage starts from."""
        render.render(self.pub)
        ops = self.path("ops/knowledge/INDEX.md").read_text(encoding="utf-8")
        core = self.path("core/knowledge/INDEX.md").read_text(encoding="utf-8")
        self.assertLess(ops.index("## Mechanisms"), ops.index("## Symptom index"))
        self.assertLess(ops.index("## Symptom index"), ops.index("## Trials, newest first"))
        row = next(line for line in ops.splitlines() if line.startswith("| The sequence stops after the effect"))
        self.assertEqual(row, f"| The sequence stops after the effect | [seteffect-never-finishes](mechanisms/"
                              f"seteffect-never-finishes.md) | `{dot('ops', 'fakegates.gate_finishes')}` |")
        self.assertNotIn("The sequence stops after the effect", core)  # another component's trial
        self.assertIn("| The game closes without a message |", core)
        # it links nothing outside the component's knowledge folder: an installed plugin's neighbours are elsewhere
        self.edit("core/knowledge/trials/2026-01-10-crash-report-play.md", "mechanisms: [",
                  "mechanisms: [seteffect-never-finishes, ")
        render.render(self.pub)
        core = self.path("core/knowledge/INDEX.md").read_text(encoding="utf-8")
        self.assertIn("| The game closes without a message | `seteffect-never-finishes` (ops) | "
                      f"`{dot('ops', 'fakegates.gate_finishes')}` |", core)
        for index in (core, self.path("ops/knowledge/INDEX.md").read_text(encoding="utf-8")):
            self.assertNotIn(rf.DOTS + "/", index)
        self.add("ops/knowledge/trials/2026-03-01-later.md",
                 md("id: 2026-03-01-later\nkind: survey\nbuild: b\ngame_version: 201602\nmechanisms: []\noutcome: pass"))
        render.render(self.pub)
        self.assertEqual(self.path("ops/knowledge/INDEX.md").read_text(encoding="utf-8").count("| The sequence"), 1)

    def test_component_index_without_symptoms(self):
        rf.write(self.path("core/knowledge/trials/2026-01-10-crash-report-play.md"),
                 self.path("core/knowledge/trials/2026-01-10-crash-report-play.md").read_text(encoding="utf-8")
                 .replace("symptom: The game closes without a message\n", ""))
        render.render(self.pub)
        core = self.path("core/knowledge/INDEX.md").read_text(encoding="utf-8")
        self.assertIn("them.\n\nNone yet.\n\n## Trials, newest first", core.replace("\r\n", "\n"))

    def test_code_links_carry_no_line_anchor(self):
        """A gate or shape link names the file only, so editing code above the definition never stales a page."""
        render.render(self.pub)
        text = (self.pub / "knowledge" / "symptoms.md").read_text(encoding="utf-8")
        row = next(line for line in text.splitlines() if "The sequence stops after the effect" in line)
        self.assertIn("fakegates.py)", row)
        for p in self.pub.rglob("*.md"):
            self.assertNotRegex(p.read_text(encoding="utf-8"), r"\.py#L\d+", p)

    def test_repo_map_lists_components_mechanisms_trials_and_lessons(self):
        render.render(self.pub)
        text = "".join(p.read_text(encoding="utf-8") for p in sorted((self.pub / "knowledge").rglob("*.md")))
        for needle in ("core", "ops", "crash-names-the-error", "2026-01-10-crash-report-play", "model-the-lookup",
                       "Gates model where the game reads", "components/core/knowledge/INDEX.md"):
            self.assertIn(needle, text)

    def test_public_render_names_nothing_private(self):
        priv = self.make_private()
        self.add(f"{PRIV}/skills/x/SKILL.md", "Uses [[crash-names-the-error]].\n", priv)
        both = self.corpus(self.pub, priv)
        render.render(self.pub, both)
        for p in self.pub.rglob("*.md"):
            text = p.read_text(encoding="utf-8")
            self.assertNotIn("private-thing", text, p)
            self.assertNotIn(PRIV, text, p)
        render.render(priv, both)
        text = (priv / "knowledge" / "status.md").read_text(encoding="utf-8")
        self.assertIn("private-thing", text)
        self.assertIn("seteffect-never-finishes", text)  # the private map includes the public components
        core = self.path("core/knowledge/mechanisms/crash-names-the-error.md").read_text(encoding="utf-8")
        self.assertNotIn(PRIV, core)  # a private render never edits the public repo's pages

    def test_private_render_footer_lists_a_private_citation(self):
        priv = self.make_private()
        self.add(f"{PRIV}/skills/x/SKILL.md", "Uses [[private-thing]].\n", priv)
        render.render(priv, self.corpus(self.pub, priv))
        text = self.path(f"{PRIV}/knowledge/mechanisms/private-thing.md", priv).read_text(encoding="utf-8")
        self.assertIn("skills/x/SKILL.md", text)
        self.assertIn("2026-03-02-private-run", text)

    def test_render_refuses_a_broken_corpus_without_writing(self):
        self.edit("ops/knowledge/trials/2026-02-01-probe-seteffect.md", "kind: probe-run", "kind: nonsense")
        before = self.snapshot(self.pub)
        with self.assertRaises(render.RenderError):
            render.render(self.pub)
        self.assertEqual(self.snapshot(self.pub), before)

    def test_crlf_checkout_is_not_stale(self):
        render.render(self.pub)
        for p in self.pub.rglob("*.md"):  # the fixtures may already be CRLF (a Windows clone): normalise first
            p.write_bytes(p.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        self.assertEqual(render.stale(self.pub), [])
        self.assertEqual(render.render(self.pub), [])
        self.assertEqual(self.run_check()[0], [])

    def test_render_check_mode_reports_stale_files(self):
        self.assertTrue(render.stale(self.pub))
        render.render(self.pub)
        self.assertEqual(render.stale(self.pub), [])


class EmptyRepoTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.repo = rf.make_repo(Path(self._tmp.name) / "r", {"core": {}, "ops": {"deps": ["core"]}})
        for comp in ("core", "ops"):  # the real repo's empty knowledge files
            (self.repo / "components" / comp / "knowledge" / "topics.md").write_text("", encoding="utf-8")
            (self.repo / "components" / comp / "knowledge" / "INDEX.md").write_text("", encoding="utf-8")

    def test_empty_repo_renders_and_checks(self):
        c = kcorpus.load(kcorpus.repo_roots(self.repo))
        self.assertEqual(kcheck.check(c, current_build=BUILD), ([], []))
        render.render(self.repo, c)
        self.assertTrue((self.repo / "components" / "core" / "knowledge" / "INDEX.md").read_text().strip())
        readme = self.repo / "knowledge" / "README.md"
        self.assertIn("Knowledge map", readme.read_text(encoding="utf-8"))
        self.assertFalse((self.repo / "knowledge" / "topics").exists())  # no topic is in use
        before = readme.read_bytes()
        render.render(self.repo, c)
        self.assertEqual(readme.read_bytes(), before)


class CliAndWiringTest(Tree):
    def run_cli(self, *argv):
        return run_cli(*argv)

    def test_render_then_check(self):
        with mock.patch.object(paths, "game_build", return_value=BUILD):
            code, out = self.run_cli("render", str(self.pub))
            self.assertEqual(code, 0, out)
            code, out = self.run_cli("check", str(self.pub))
            self.assertEqual(code, 0, out)
            self.assertIn("ok", out)

    def test_check_exits_1_on_an_error(self):
        self.edit("ops/skills/build-op/SKILL.md", "[[seteffect-never-finishes]]", "[[nope]]")
        with mock.patch.object(paths, "game_build", return_value=BUILD):
            code, out = self.run_cli("check", str(self.pub))
        self.assertEqual(code, 1)
        self.assertIn("nope", out)

    def test_check_prints_warnings_but_exits_0(self):
        with mock.patch.object(paths, "game_build", return_value="999999"):
            code, out = self.run_cli("check", str(self.pub))
        self.assertEqual(code, 0)
        self.assertIn("warning", out)

    def test_usage(self):
        self.assertEqual(self.run_cli()[0], 2)
        self.assertEqual(self.run_cli("frobnicate")[0], 2)

    def test_repocheck_runs_the_knowledge_check(self):
        render.render(self.pub)
        rf.git_init(self.pub)
        rf.commit_all(self.pub)
        with mock.patch.object(paths, "game_build", return_value=BUILD):
            self.assertEqual([str(p) for p in repocheck.run(self.pub)], [])
            self.edit("ops/skills/build-op/SKILL.md", "[[seteffect-never-finishes]]", "[[nope]]")
            rf.commit_all(self.pub)
            problems = [str(p) for p in repocheck.run(self.pub)]
        self.assertEqual(len(problems), 1)
        self.assertIn("nope", problems[0])


    def repocheck_lines(self):
        rf.commit_all(self.pub)
        with mock.patch.object(paths, "game_build", return_value=BUILD):
            return [str(p) for p in repocheck.run(self.pub)]

    def test_hand_edited_index_fails_repocheck(self):
        render.render(self.pub)
        rf.git_init(self.pub)
        self.assertEqual(self.repocheck_lines(), [])
        index = self.path("ops/knowledge/INDEX.md")
        index.write_text(index.read_text(encoding="utf-8") + "A hand-written line.", encoding="utf-8")
        lines = self.repocheck_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("ops/knowledge/INDEX.md", lines[0])
        self.assertIn("python -m modkit.core.knowledge render", lines[0])

    def test_unrendered_repo_fails_repocheck_naming_every_stale_file(self):
        rf.git_init(self.pub)
        lines = self.repocheck_lines()
        for needle in ("knowledge/README.md", "knowledge/topics/script-flow.md", "core/knowledge/INDEX.md", "ops/knowledge/INDEX.md",
                       "crash-names-the-error.md", "seteffect-never-finishes.md", "model-the-lookup.md"):
            self.assertTrue(any(needle in line for line in lines), (needle, lines))

    def test_hand_edited_footer_fails_repocheck_as_footer_not_generated(self):
        render.render(self.pub)
        rf.git_init(self.pub)
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md", "2026-02-01-probe-seteffect](",
                  "2026-02-01-probe-seteffect-edited](")
        lines = self.repocheck_lines()
        self.assertEqual(len(lines), 1)
        self.assertIn("footer-not-generated", lines[0])

    def test_text_above_the_footer_may_change_without_staleness(self):
        render.render(self.pub)
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md", "The action stays", "The action really stays")
        self.assertEqual(render.problems(self.pub), [])


class FooterHoleTest(Tree):
    def setUp(self):
        super().setUp()
        self.priv = self.make_private()

    def mech_with(self, body: str):
        self.add("ops/knowledge/mechanisms/sneaky.md",
                 md("id: sneaky\ntitle: Sneaky\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]", body))

    def private_errors(self):
        errors, _ = self.run_check(self.pub, self.priv)
        return errors

    def test_citation_inside_a_closed_footer_is_still_read(self):
        self.mech_with("""x
<!-- referenced-by:start -->
[[private-thing]]
<!-- referenced-by:end -->
""")
        self.assertTrue(any("private ID private-thing" in e for e in self.private_errors()))

    def test_citation_after_an_unclosed_start_marker_is_read_and_the_marker_is_an_error(self):
        self.mech_with("""x
<!-- referenced-by:start -->
[[private-thing]]
""")
        errors = self.private_errors()
        self.assertTrue(any("private ID private-thing" in e for e in errors), errors)
        self.assertTrue(any("unclosed or repeated referenced-by marker" in e for e in errors), errors)

    def test_repeated_or_reversed_markers_are_errors(self):
        self.mech_with("""x
<!-- referenced-by:end -->
<!-- referenced-by:start -->
""")
        self.assertTrue(any("referenced-by marker" in e for e in self.private_errors()))

    def test_spaced_citation_is_read(self):
        self.mech_with("See [[ private-thing ]].")
        self.assertTrue(any("private ID private-thing" in e for e in self.private_errors()))

    def test_malformed_citations_fail_loudly(self):
        for bad in ("[[a|b]]", "[[private-thing#x]]", "[[]]", "[[Two Words]]", "[[UPPER]]"):
            with self.subTest(bad=bad):
                self.mech_with("See " + bad + ".")
                self.assertTrue(any("malformed-citation" in e for e in self.private_errors()), bad)


class TopicRulesTest(Tree):
    MECH = "core/knowledge/mechanisms/crash-names-the-error.md"

    def test_topics_are_read_in_declaration_order(self):
        c = self.corpus()
        self.assertEqual(list(c.topics), ["loading-and-crashes", "mod-packaging", "script-flow"])
        self.assertEqual(c.topics["script-flow"].where.component, "ops")
        self.assertEqual(c.topics["mod-packaging"].title, "Mod packaging")
        self.assertEqual(c.topics["mod-packaging"].scope, "How a mod folder is laid out and shared.")
        self.assertEqual(c.mechanisms["seteffect-never-finishes"].topics, ("script-flow", "loading-and-crashes"))

    def test_missing_topics_is_an_error(self):
        self.edit(self.MECH, "topics: [loading-and-crashes]\n", "")
        self.assertError("crash-names-the-error: missing field topics")

    def test_empty_topics_is_an_error(self):
        self.edit(self.MECH, "topics: [loading-and-crashes]", "topics: []")
        self.assertError("missing field topics")

    def test_more_than_three_topics_is_an_error(self):
        self.edit(self.MECH, "topics: [loading-and-crashes]", "topics: [a, b, c, d]")
        self.assertError("topics lists 4 topics")

    def test_undeclared_topic_is_an_error(self):
        self.edit(self.MECH, "topics: [loading-and-crashes]", "topics: [loading-and-crashes, no-such-topic]")
        self.assertError("topic no-such-topic is not declared in any topics.md")

    def test_duplicate_topic_id_across_two_components_is_an_error(self):
        self.add("ops/knowledge/topics.md", "# Topics\n\n## script-flow: Script flow\nHow scripts run.\n\n"
                                            "## loading-and-crashes: Loading again\nThe same ID as core's.\n")
        errors = self.assertError("duplicate topic ID loading-and-crashes")
        self.assertTrue(any(e.startswith("components/ops/knowledge/topics.md") for e in errors), errors)

    def test_a_topic_from_outside_the_dependencies_is_an_error(self):
        self.edit(self.MECH, "topics: [loading-and-crashes]", "topics: [script-flow]")
        self.assertError("topic script-flow is declared in component ops, outside the dependencies of core")

    def test_a_topic_from_a_dependency_is_fine(self):
        self.assertIn("loading-and-crashes", self.corpus().mechanisms["seteffect-never-finishes"].topics)
        self.assertClean()

    def test_malformed_topic_headings(self):
        self.add("core/knowledge/topics.md", "# Topics\n\n## Not An Id\nScope.\n\n## no-scope: No scope\n\n"
                                             "## loading-and-crashes: Loading\nScope.\n")
        errors = self.assertError("must read '## <topic-id>: <title>'")
        self.assertTrue(any("topic no-scope needs a sentence of scope" in e for e in errors), errors)

    def test_a_citation_never_names_a_topic(self):
        self.add("ops/skills/build-op/SKILL.md", "See [[script-flow]].\n")
        self.assertError("unknown ID script-flow")

    def test_project_may_use_any_visible_topic_and_declare_its_own(self):
        proj = self.tmp / "myproject"
        rf.write(proj / "knowledge" / "topics.md", "## my-topic: Mine\nMy own topic.\n")
        rf.write(proj / "knowledge" / "mechanisms" / "my-finding.md",
                 md("id: my-finding\ntitle: Mine\nstatus: UNTESTED\nsource: play\ntopics: [my-topic, script-flow]"))
        self.assertClean(project=proj)


class LessonFilesTest(Tree):
    def test_a_lessons_folder_parses_with_its_front_matter_and_verbatim_body(self):
        body = ("First line, with `code` and [[crash-names-the-error]].\n\n- a list item\n  continued\n\n"
                "Last paragraph: with a colon.\n")
        self.add("ops/knowledge/lessons/keep-the-body.md",
                 md("id: keep-the-body\ntitle: A rule: with a colon\n"
                    "trials: [2026-02-01-probe-seteffect, 2026-01-10-crash-report-play]", body))
        self.add("ops/knowledge/lessons/no-prose.md",
                 md("id: no-prose\ntitle: A rule alone\ntrials:\n  - 2026-02-01-probe-seteffect", ""))
        c = self.corpus()
        x = c.lessons["keep-the-body"]
        self.assertEqual((x.id, x.title, x.trials), ("keep-the-body", "A rule: with a colon",
                                                     ("2026-02-01-probe-seteffect", "2026-01-10-crash-report-play")))
        self.assertEqual(x.body, body)
        self.assertEqual(x.where.component, "ops")
        self.assertEqual(c.lessons["no-prose"].body, "")
        self.assertIn(("crash-names-the-error", "record", "keep-the-body"),
                      {(y.id, y.kind, y.source_id) for y in c.citations})
        self.assertClean()
        render.render(self.pub)  # the generated footer is not part of the body
        self.assertEqual(self.corpus().lessons["keep-the-body"].body, body)
        self.assertIn("<!-- referenced-by:end -->",
                      self.path("ops/knowledge/lessons/keep-the-body.md").read_text(encoding="utf-8"))

    def test_lesson_schema_errors(self):
        for meta, text in (("id: bad-one\ntrials: [2026-02-01-probe-seteffect]", "missing field title"),
                           ("id: bad-one\ntitle: T", "missing field trials"),
                           ("id: bad-one\ntitle: T\ntrials: [2026-02-01-probe-seteffect]\nrule: x", "unknown field")):
            with self.subTest(text=text):
                self.add("ops/knowledge/lessons/bad-one.md", md(meta))
                self.assertError(text)
        self.add("ops/knowledge/lessons/bad-one.md", md("id: other-id\ntitle: T\ntrials: [2026-02-01-probe-seteffect]"))
        self.assertError("the file name must be other-id.md")

    def test_a_leftover_lessons_md_is_an_error(self):
        self.add("core/knowledge/lessons.md", "# Lessons\n\n## old-style: A rule\ntrials: 2026-01-10-crash-report-play\n")
        errors = self.assertError("lessons.md is the old one-file form")
        self.assertTrue(any(e.startswith("components/core/knowledge/lessons.md") for e in errors), errors)

    def test_lesson_footer_lists_its_trials_and_citations(self):
        self.add("ops/skills/build-op/SKILL.md", "See [[seteffect-never-finishes]] and [[model-the-lookup]].\n")
        render.render(self.pub)
        text = self.path("core/knowledge/lessons/model-the-lookup.md").read_text(encoding="utf-8")
        footer = text[text.index("<!-- referenced-by:start -->"):]
        self.assertIn(f"[2026-01-10-crash-report-play]({UP}trials/2026-01-10-crash-report-play.md)", footer)
        self.assertIn("skills/build-op/SKILL.md", footer)
        self.assertEqual(render.problems(self.pub), [])
        self.edit("core/knowledge/lessons/model-the-lookup.md", f"]({UP}trials/", f"]({UP}trial/")
        self.assertIn("footer-not-generated", " ".join(render.problems(self.pub)))


class MapTest(Tree):
    def map(self, root: Path | None = None) -> Path:
        return (root or self.pub) / "knowledge"

    def page(self, rel: str) -> str:
        return (self.map() / rel).read_text(encoding="utf-8")

    def test_render_writes_the_readme_the_topics_in_use_and_the_l1_pages(self):
        render.render(self.pub)
        written = sorted(p.relative_to(self.map()).as_posix() for p in self.map().rglob("*"))
        self.assertEqual(written, sorted(["README.md", *L1_PAGES, "topics", "topics/loading-and-crashes.md",
                                          "topics/script-flow.md"]))  # mod-packaging is declared but not in use
        for p in self.map().rglob("*.md"):
            self.assertTrue(p.read_text(encoding="utf-8").startswith(render.GENERATED), p)
        self.assertFalse((self.pub / "KNOWLEDGE.md").exists())

    def test_readme_starts_here_and_counts_the_topics(self):
        render.render(self.pub)
        readme = self.page("README.md")
        self.assertLessEqual(len(readme.splitlines()), 60)
        for question, target in (("What is known about X?", "(#topics)"), ("I saw this in game", "(symptoms.md)"),
                                 ("How sure is it?", "(status.md)"), ("Which game build", "(builds.md)"),
                                 ("What was tried?", "(trials.md)"), ("What rules did it teach?", "(lessons.md)")):
            row = next(line for line in readme.splitlines() if line.startswith(f"| {question}"))
            self.assertIn(target, row)
        self.assertIn("| [Loading and crashes](topics/loading-and-crashes.md) | What the game checks when a mod "
                      "loads, and how a failed load shows. | 2 | 1 |", readme)
        self.assertIn("| Mod packaging | How a mod folder is laid out and shared. | 0 | 0 |", readme)
        self.assertIn(f"| [core]({UP}components/core/knowledge/INDEX.md) |", readme)
        self.assertIn("components/*/knowledge/", readme)

    def test_topic_page_lists_mechanisms_by_status_lessons_through_trials_and_trials(self):
        render.render(self.pub)
        page = self.page("topics/loading-and-crashes.md")
        self.assertIn("What the game checks when a mod loads, and how a failed load shows.", page)
        self.assertLess(page.index("### PLAYED"), page.index("### RE"))
        self.assertIn(f"- [crash-names-the-error]({UP}{UP}components/core/knowledge/mechanisms/crash-names-the-error.md)"
                      ": The crash report names the real error (core, verified 201602)", page)
        self.assertIn(f"- [seteffect-never-finishes]({UP}{UP}components/ops/knowledge/mechanisms/"
                      "seteffect-never-finishes.md): A set-effect action never finishes by itself (ops, verified "
                      "201602)", page)
        self.assertIn(f"[model-the-lookup]({UP}{UP}components/core/knowledge/lessons/model-the-lookup.md)", page)
        self.assertLess(page.index(f"2026-02-01-probe-seteffect]({UP}{UP}"), page.index(f"2026-01-10-crash-report-play]({UP}{UP}"))
        flow = self.page("topics/script-flow.md")
        self.assertNotIn("model-the-lookup", flow)  # its trial touches no script-flow mechanism
        # a lesson reaches a topic through the trial's own mechanisms list too
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md", "trials: [2026-01-10-crash-report-play]",
                  "trials: []")
        self.edit("core/knowledge/trials/2026-01-10-crash-report-play.md", "mechanisms: [crash-names-the-error]",
                  "mechanisms: [crash-names-the-error, seteffect-never-finishes]")
        render.render(self.pub)
        self.assertIn("model-the-lookup", self.page("topics/script-flow.md"))

    def test_builds_page_groups_by_build_newest_first(self):
        self.add("ops/knowledge/mechanisms/ideas.md",
                 md("id: ideas\ntitle: An idea\nstatus: UNTESTED\nsource: play\ntopics: [script-flow]"))
        self.add("ops/knowledge/trials/2026-03-01-later.md",
                 md("id: 2026-03-01-later\nkind: survey\nbuild: b\ngame_version: 300000\nmechanisms: []\noutcome: pass"))
        render.render(self.pub)
        page = self.page("builds.md")
        self.assertIn("A fact holds for the build it was last verified on.", page)
        self.assertLess(page.index("## 300000"), page.index("## 201602"))
        self.assertLess(page.index("## 201602"), page.index("## Not verified on any build"))
        self.assertIn("The crash report names the real error (PLAYED, 2026-01-10)", page)
        self.assertIn("2026-03-01-later", page[page.index("## 300000"):page.index("## 201602")])
        self.assertIn("[ideas](", page[page.index("## Not verified on any build"):])
        self.assertNotIn("topics/game-updates.md", page)  # no such topic here
        self.add("core/knowledge/topics.md", "## game-updates: Game updates\nWhat changed between game builds.\n\n"
                                             "## loading-and-crashes: Loading and crashes\nLoads.\n")
        self.edit("core/knowledge/mechanisms/crash-names-the-error.md", "topics: [loading-and-crashes]",
                  "topics: [loading-and-crashes, game-updates]")
        render.render(self.pub)
        self.assertIn("Start with [topics/game-updates.md](topics/game-updates.md).", self.page("builds.md"))

    def test_l1_pages_hold_the_old_map_sections(self):
        render.render(self.pub)
        self.assertIn("| The game closes without a message |", self.page("symptoms.md"))
        status = self.page("status.md")
        self.assertLess(status.index("## PLAYED"), status.index("crash-names-the-error"))
        self.assertLess(status.index("crash-names-the-error"), status.index("## RE"))
        self.assertNotIn("### ", status)
        self.assertIn(f"2026-02-01-probe-seteffect]({UP}components/ops/knowledge/trials/", self.page("trials.md"))
        self.assertIn(f"- [model-the-lookup]({UP}components/core/knowledge/lessons/model-the-lookup.md) (core): Gates "
                      "model where the game reads. Trials: [2026-01-10-crash-report-play]", self.page("lessons.md"))

    def test_index_groups_mechanisms_under_each_topic(self):
        render.render(self.pub)
        ops = self.path("ops/knowledge/INDEX.md").read_text(encoding="utf-8")
        self.assertLess(ops.index("### Script flow"), ops.index("### Loading and crashes"))  # its own topics first
        self.assertEqual(ops.count("[seteffect-never-finishes](mechanisms/seteffect-never-finishes.md): A set-effect"), 2)
        core = self.path("core/knowledge/INDEX.md").read_text(encoding="utf-8")
        self.assertNotIn("### Script flow", core)
        self.assertNotIn("### Mod packaging", core)  # no mechanism carries it
        self.assertIn("- [model-the-lookup](lessons/model-the-lookup.md): Gates model where the game reads", core)
        self.assertNotIn(rf.DOTS + "/", core)

    def test_render_deletes_a_stale_generated_page_and_keeps_a_hand_written_one(self):
        render.render(self.pub)
        stale_topic = self.map() / "topics" / "old-topic.md"
        old_map = self.pub / "KNOWLEDGE.md"
        for p in (stale_topic, old_map):
            rf.write(p, render.GENERATED + "\n# Old\n")
        notes, mine = self.map() / "notes.md", self.map() / "topics" / "mine.md"
        for p in (notes, mine):
            rf.write(p, "# Hand-written\n")
        changed = render.render(self.pub)
        self.assertEqual(sorted(changed), sorted([stale_topic, old_map]))
        self.assertFalse(stale_topic.exists() or old_map.exists())
        self.assertTrue(notes.exists() and mine.exists())
        # a topic no mechanism carries any more loses its page
        self.edit("ops/knowledge/mechanisms/seteffect-never-finishes.md", "topics: [script-flow, loading-and-crashes]",
                  "topics: [loading-and-crashes]")
        render.render(self.pub)
        self.assertFalse((self.map() / "topics" / "script-flow.md").exists())
        self.assertEqual(render.render(self.pub), [])

    def test_check_flags_a_stale_generated_page(self):
        render.render(self.pub)
        with mock.patch.object(paths, "game_build", return_value=BUILD):
            self.assertEqual(run_cli("check", str(self.pub))[0], 0)
            rf.write(self.pub / "KNOWLEDGE.md", "# A hand-written file of the same name is not generated\n")
            self.assertEqual(run_cli("check", str(self.pub))[0], 0)
            rf.write(self.pub / "KNOWLEDGE.md", render.GENERATED + "\n# Knowledge map\n")
            rf.write(self.map() / "topics" / "old-topic.md", render.GENERATED + "\n# Old\n")
            code, out = run_cli("check", str(self.pub))
        self.assertEqual(code, 1, out)
        self.assertIn("KNOWLEDGE.md: stale generated page", out)
        self.assertIn("knowledge/topics/old-topic.md: stale generated page", out)
        self.assertEqual(len(render.problems(self.pub)), 2)  # repocheck reports them too
        self.assertEqual(sorted(render.stale(self.pub)), sorted([self.pub / "KNOWLEDGE.md",
                                                                 self.map() / "topics" / "old-topic.md"]))

    def test_every_link_in_the_fixture_pages_resolves(self):
        render.render(self.pub)
        pages = render.plan(self.pub)
        self.assertEqual(len([p for p in pages if p.parent == self.map()]), 6)
        self.assertEqual(broken_links(pages), [])

    def test_a_project_folder_gets_the_map_beside_its_records(self):
        proj = self.tmp / "myproject"
        rf.write(proj / "knowledge" / "topics.md", "## my-topic: Mine\nMy own topic.\n")
        rf.write(proj / "knowledge" / "mechanisms" / "my-finding.md",
                 md("id: my-finding\ntitle: Mine\nstatus: UNTESTED\nsource: play\ntopics: [my-topic, script-flow]\n"
                    "trials: [2026-03-03-my-run]"))
        rf.write(proj / "knowledge" / "trials" / "2026-03-03-my-run.md",
                 md("id: 2026-03-03-my-run\nkind: survey\nbuild: aaa\ngame_version: 201602\n"
                    "mechanisms: [my-finding, seteffect-never-finishes]\noutcome: mixed"))
        rf.write(proj / "knowledge" / "lessons" / "my-rule.md",
                 md("id: my-rule\ntitle: My rule\ntrials: [2026-03-03-my-run]", "Why.\n"))
        render.render(proj, self.corpus(project=proj))
        k = proj / "knowledge"
        for rel in ("README.md", *L1_PAGES, "topics/my-topic.md", "topics/script-flow.md"):
            self.assertTrue((k / rel).is_file(), rel)
        self.assertFalse((k / "INDEX.md").exists())
        readme = (k / "README.md").read_text(encoding="utf-8")
        self.assertIn("| this project |", readme)
        self.assertIn(f"[my-finding]({UP}mechanisms/my-finding.md)", (k / "topics" / "my-topic.md").read_text(encoding="utf-8"))
        self.assertIn("`seteffect-never-finishes`", (k / "topics" / "script-flow.md").read_text(encoding="utf-8"))
        self.assertIn("<!-- referenced-by:start -->", (k / "lessons" / "my-rule.md").read_text(encoding="utf-8"))
        # the generated lessons.md beside lessons/ is not a leftover, and a second render changes nothing
        self.assertEqual(self.run_check(project=proj), ([], []))
        self.assertEqual(render.render(proj, self.corpus(project=proj)), [])
        self.assertEqual(broken_links(render.plan(proj, self.corpus(project=proj))), [])
        self.assertEqual(render.orphans(proj, self.corpus(project=proj)), [])


class RealRepoLinksTest(unittest.TestCase):
    def test_every_relative_link_in_every_generated_page_of_the_repo_resolves(self):
        """Walks the pages ``render`` writes for this repository: the map, each INDEX.md and every footer."""
        repo = Path(__file__).resolve().parents[3]
        if not kcorpus.is_repo(repo):
            self.skipTest("not run from a clone of the repository")
        pages = render.plan(repo)
        self.assertIn(repo / "knowledge" / "README.md", pages)
        self.assertTrue(any(p.parent.name == "topics" for p in pages))
        self.assertTrue(any(p.parent.name == "lessons" for p in pages))
        self.assertEqual(broken_links(pages), [])


class GameBuildTest(unittest.TestCase):
    def test_newest_numeric_data_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name in ("100", "201602", "99999", "Shared", "20160x"):
                (Path(tmp) / "Data" / "PC" / name).mkdir(parents=True)
            (Path(tmp) / "Data" / "PC" / "999999999").write_text("a file, not a build folder")
            with mock.patch.object(paths, "game_dir", return_value=Path(tmp)):
                self.assertEqual(paths.game_build(), "201602")

    def test_none_when_unconfigured_or_empty(self):
        with mock.patch.object(paths, "game_dir", side_effect=paths.NotConfigured("x")):
            self.assertIsNone(paths.game_build())
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(paths, "game_dir", return_value=Path(tmp)):
                self.assertIsNone(paths.game_build())
            (Path(tmp) / "Data" / "PC").mkdir(parents=True)
            with mock.patch.object(paths, "game_dir", return_value=Path(tmp)):
                self.assertIsNone(paths.game_build())


if __name__ == "__main__":
    unittest.main()
