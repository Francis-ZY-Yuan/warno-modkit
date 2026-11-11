"""The component checks: shape, names, dependencies, closure, cycles, path escapes, outside-the-repo components."""
import importlib
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

import repofixture as fx
from modkit.core import components
from modkit.core.knowledge import corpus as kcorpus

OPS = "modkit." + "ops"


class Fixture(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name) / "repo"

    def texts(self):
        return [str(p) for p in components.check(self.root)]

    def assertProblem(self, fragment):
        found = self.texts()
        self.assertTrue(any(fragment in t for t in found), f"no problem mentioning {fragment!r} in {found}")


class Checks(Fixture):
    def test_clean_repo_passes(self):
        fx.make_repo(self.root, {"core": {}, "ops": {"deps": ["core"], "imports": ["core"]}})
        self.assertEqual(components.check(self.root), [])

    def test_shape_missing_folder_fails(self):
        fx.make_repo(self.root, {"core": {}})
        (self.root / "components/core/knowledge/trials/.gitkeep").unlink()
        (self.root / "components/core/knowledge/trials").rmdir()
        self.assertProblem("knowledge/trials")
        (self.root / "components/core/skills/.gitkeep").unlink()
        self.assertProblem("skills")

    def test_shape_needs_a_lessons_folder_and_topics(self):
        fx.make_repo(self.root, {"core": {}})
        self.assertEqual(components.check(self.root), [])
        (self.root / "components/core/knowledge/lessons/.gitkeep").unlink()
        self.assertProblem("empty folder knowledge/lessons")
        (self.root / "components/core/knowledge/lessons").rmdir()
        (self.root / "components/core/knowledge/topics.md").unlink()
        self.assertProblem("missing folder knowledge/lessons")
        self.assertProblem("missing file knowledge/topics.md")

    def test_generated_footer_links_on_record_pages_are_not_escapes(self):
        fx.make_repo(self.root, {"core": {}})
        link = "[t](" + fx.DOTS + "/" + fx.DOTS + "/" + fx.DOTS + "/ops/knowledge/trials/t.md)"
        page = f"---\nid: x\n---\nBody.\n\n{components.FOOTER_START}\n- Trials: {link}\n{components.FOOTER_END}\n"
        for sub in ("mechanisms", "lessons"):
            fx.write(self.root / f"components/core/knowledge/{sub}/x.md", page)
        self.assertEqual(components.check(self.root), [])
        fx.write(self.root / "components/core/knowledge/lessons/x.md", f"Body {link}\n")  # outside the footer
        self.assertProblem("knowledge/lessons/x.md:1 reaches outside its component folder")

    def test_shape_missing_file_fails(self):
        fx.make_repo(self.root, {"core": {}})
        (self.root / "components/core/knowledge/INDEX.md").unlink()
        (self.root / "components/core/pyproject.toml").unlink()
        self.assertProblem("INDEX.md")
        self.assertProblem("pyproject.toml")

    def test_namespace_init_is_refused(self):
        fx.make_repo(self.root, {"core": {}})
        fx.write(self.root / "components/core/src/modkit/__init__.py")
        self.assertProblem("namespace")

    def test_import_outside_closure_fails(self):
        fx.make_repo(self.root, {"core": {}, "ops": {"deps": ["core"]}, "extra": {"imports": ["ops"]}})
        self.assertProblem("extra")
        self.assertProblem(OPS)

    def test_import_in_tests_examples_and_skills_is_checked(self):
        fx.make_repo(self.root, {"core": {}, "ops": {}})
        for sub in ("tests/test_a.py", "examples/e/build.py", "skills/s/scripts/run.py"):
            fx.write(self.root / "components/core" / sub, "from modkit.ops import thing\n")
        found = self.texts()
        self.assertEqual(sum(OPS in t for t in found), 3, found)

    def test_from_modkit_import_name_is_checked(self):
        fx.make_repo(self.root, {"core": {}, "ops": {}})
        fx.write(self.root / "components/core/tests/test_a.py", "from modkit import ops\n")
        self.assertProblem(OPS)

    def test_import_inside_transitive_closure_passes(self):
        fx.make_repo(self.root, {"core": {}, "ops": {"deps": ["core"]},
                                 "extra": {"deps": ["ops"], "imports": ["core"]}})
        self.assertEqual(components.check(self.root), [])

    def test_cycle_fails(self):
        fx.make_repo(self.root, {"core": {"deps": ["ops"]}, "ops": {"deps": ["core"]}})
        self.assertProblem("cycle")

    def test_plugin_pyproject_mismatch_fails(self):
        fx.make_repo(self.root, {"core": {}, "ops": {"deps": ["core"], "pyproject_deps": []}})
        self.assertProblem("ops")
        self.assertProblem("core")
        self.assertProblem("pyproject")

    def test_plugin_name_must_follow_directory(self):
        fx.make_repo(self.root, {"core": {"plugin_name": "warno-other"}})
        self.assertProblem("warno-core")

    def test_path_escape_fails(self):
        fx.make_repo(self.root, {"core": {}})
        fx.write(self.root / "components/core/skills/s/SKILL.md", "run " + fx.DOTS + "/ops/thing.py\n")
        self.assertProblem("skills")
        fx.write(self.root / "components/core/skills/s/SKILL.md", "ok\n")
        self.assertEqual(components.check(self.root), [])
        root_var = "${" + "CLAUDE_PLUGIN_ROOT" + "}"
        fx.write(self.root / "components/core/skills/s/run.py", f'p = "{root_var}/{fx.DOTS}/ops"\n')
        self.assertProblem("run.py")

    def test_missing_visibility_fails(self):
        fx.make_repo(self.root, {"core": {}})
        (self.root / "modkit.repo.toml").unlink()
        self.assertProblem("modkit.repo.toml")


class Outside(Fixture):
    """Components of another repo are found through the installed package (importlib.util.find_spec)."""

    def install_fake(self, name, deps=()):
        other = Path(self._tmp.name) / "ext_repo"
        fx.make_component(other, name, deps=deps)
        src = other / "components" / name / "src"
        sys.path.insert(0, str(src))
        self.addCleanup(sys.path.remove, str(src))
        self.addCleanup(importlib.invalidate_caches)
        self.addCleanup(lambda: sys.modules.pop("modkit." + name, None))
        importlib.invalidate_caches()

    def test_private_repo_may_depend_on_installed_component(self):
        self.install_fake("pluggable")
        fx.make_repo(self.root, {"core": {"deps": ["pluggable"], "imports": ["pluggable"]}}, visibility="private")
        self.assertEqual(components.check(self.root), [])

    def test_closure_includes_the_installed_components_own_dependencies(self):
        self.install_fake("pluggable", deps=["leaf"])
        self.install_fake("leaf")
        fx.make_repo(self.root, {"core": {"deps": ["pluggable"], "imports": ["leaf"]}}, visibility="private")
        self.assertEqual(components.check(self.root), [])

    def test_public_repo_with_outside_dependency_fails(self):
        self.install_fake("pluggable")
        fx.make_repo(self.root, {"core": {"deps": ["pluggable"]}}, visibility="public")
        self.assertProblem("outside the repo")

    def test_unresolvable_dependency_fails(self):
        fx.make_repo(self.root, {"core": {"deps": ["nowhere"]}}, visibility="private")
        self.assertProblem("nowhere")


class PlainInstall(Fixture):
    """A plain (non-editable) install, as warno-setup prescribes for installed plugins, puts ``modkit/<name>`` in
    site-packages, away from its component folder. pip records the folder it installed from in the dist-info's
    ``direct_url.json``; that is how the component, and so its knowledge, is found."""

    def plain_install(self, name: str) -> Path:
        """`name` laid out like a plugin in Claude Code's cache, installed (not editable) into a site folder."""
        tmp = Path(self._tmp.name)
        built = fx.make_component(tmp / "staging", name)
        folder = tmp / "cache" / "warno-modkit" / f"warno-{name}" / "0.1.0"
        folder.parent.mkdir(parents=True)
        shutil.move(built, folder)
        site = tmp / "site"
        fx.write(site / "modkit" / name / "__init__.py")
        info = site / f"modkit_{name}-0.1.0.dist-info"
        fx.write(info / "METADATA", f"Metadata-Version: 2.1\nName: modkit-{name}\nVersion: 0.1.0\n")
        fx.write(info / "direct_url.json", json.dumps({"url": folder.as_uri(), "dir_info": {}}))
        if str(site) not in sys.path:
            sys.path.insert(0, str(site))
            self.addCleanup(sys.path.remove, str(site))
        self.addCleanup(importlib.invalidate_caches)
        self.addCleanup(lambda: sys.modules.pop("modkit." + name, None))
        importlib.invalidate_caches()
        return folder

    def test_found_through_direct_url(self):
        folder = self.plain_install("pluggable")
        found = components.installed_components()
        self.assertEqual(found["pluggable"].resolve(), folder.resolve())
        roots = {r.name: r for r in kcorpus.installed_roots()}
        self.assertEqual(roots["pluggable"].knowledge.resolve(), (folder / "knowledge").resolve())
        # a modder's project folder sees it, as `python -m modkit.core.knowledge check .` does
        project = Path(self._tmp.name) / "project"
        fx.write(project / "knowledge" / "topics.md", "# Topics\n")
        self.assertIn("pluggable", {r.name for r in kcorpus.discover(None, project)})

    def test_a_folder_gone_since_the_install_is_left_out(self):
        folder = self.plain_install("pluggable")
        shutil.rmtree(folder)
        self.assertNotIn("pluggable", components.installed_components())


if __name__ == "__main__":
    unittest.main()
