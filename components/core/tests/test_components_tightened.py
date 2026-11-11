"""Component checks: routes by which a bad dependency used to pass (review round 1)."""
import unittest

import repofixture as fx
from modkit.core import components
from test_components import OPS, Fixture


class Tightened(Fixture):
    def two(self):
        fx.make_repo(self.root, {"core": {}, "ops": {}})

    def test_every_python_file_is_checked(self):
        self.two()
        fx.write(self.root / "components/core/scripts/tool.py", "import modkit.ops\n")
        self.assertProblem("scripts/tool.py")

    def test_string_literal_reference_counts(self):
        self.two()
        fx.write(self.root / "components/core/src/modkit/core/late.py",
                 "import importlib\nm = importlib.import_module('modkit.ops')\n")
        self.assertProblem(OPS)

    def test_toml_names_are_not_references(self):
        self.two()
        fx.write(self.root / "components/core/src/modkit/core/late.py", "N = 'modkit.local.toml'\n")
        self.assertEqual(components.check(self.root), [])

    def test_dynamic_import_with_modkit_prefix_is_a_finding(self):
        self.two()
        bodies = ["import importlib\nimportlib.import_module('modkit.' + name)\n",
                  "import importlib\nimportlib.import_module(f'modkit.{name}')\n",
                  "from importlib import import_module\nimport_module('modkit.%s' % name)\n",
                  "import importlib\nimportlib.import_module('modkit.{}'.format(name))\n"]
        for i, body in enumerate(bodies):
            fx.write(self.root / f"components/core/src/modkit/core/d{i}.py", body)
        found = [str(p) for p in components.check(self.root) if "dynamic-import" in str(p)]
        self.assertEqual(len(found), 4, found)

    def test_dynamic_import_of_other_names_passes(self):
        self.two()
        fx.write(self.root / "components/core/src/modkit/core/d.py",
                 "import importlib\nimportlib.import_module(name)\n")
        self.assertEqual(components.check(self.root), [])

    def test_plugin_json_that_is_not_an_object_is_a_problem(self):
        self.two()
        fx.write(self.root / "components/core/.claude-plugin/plugin.json", "[1, 2]")
        self.assertProblem("plugin.json")


if __name__ == "__main__":
    unittest.main()
