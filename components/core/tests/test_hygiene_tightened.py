"""Hygiene gates: routes by which a leak used to pass (review round 1)."""
import json
import unittest
from pathlib import Path

import repofixture as fx
from modkit.core import hygiene
from test_hygiene import Fixture

PY = "components/core/src/modkit/core/a.py"
VT, RV, SL = "vt" + "able", "rv" + "a", "sl" + "ot"


def texts(findings, rule="address"):
    return sorted(f.text for f in findings if f.rule == rule)


class Addresses(Fixture):
    def test_numbered_slot_is_not_covered_by_a_bare_allowlist_entry(self):
        self.put(PY, f"# {SL}\n# {SL} 12\n# {SL} #12\n# {SL}_12\n")
        self.allow((PY, SL, "generic term: no exe-specific value"))
        found = texts(hygiene.scan_tree(self.root))
        self.assertEqual(found, sorted([f"{SL} 12", f"{SL} 12", f"{SL} 12"]))

    def test_hex_with_separators_and_suffixes_is_flagged(self):
        lits = [fx.hex_literal("DEAD_BEEF"), fx.hex_literal("1_0000_0000"), fx.hex_literal("140001234ull")]
        self.put(PY, "".join(f"A = {x}\n" for x in lits))
        self.assertEqual(len(texts(hygiene.scan_tree(self.root))), 3)

    def test_short_hex_with_separators_passes(self):
        self.put(PY, f"A = {fx.hex_literal('FF_FF')}\n")
        self.assertEqual(hygiene.scan_tree(self.root), [])

    def test_identifier_forms_of_the_words_are_flagged(self):
        for i, ident in enumerate([f"{RV}_1f", f"{VT}_ptr", f"{VT}{SL.capitalize()}", f"{SL}_table"]):
            self.put(f"components/core/src/modkit/core/i{i}.py", f"{ident} = 1\n")
        found = hygiene.scan_tree(self.root)
        self.assertEqual({Path(f.path).name for f in found if f.rule == "address"},
                         {"i0.py", "i1.py", "i2.py", "i3.py"})

    def test_words_inside_other_words_pass(self):
        self.put(PY, "# conservative, observation, slotted, Slotted\nconservative_view = 1\n")
        self.assertEqual(hygiene.scan_tree(self.root), [])


class AllowFile(Fixture):
    def test_text_value_is_scanned_for_personal_strings(self):
        self.allow(("x/y.py", fx.user_path(), "r"))
        found = hygiene.scan_tree(self.root)
        self.assertEqual([(f.rule, f.path) for f in found], [("local-path", hygiene.ALLOW_FILE)])

    def test_text_value_is_scanned_for_deny_hashes(self):
        self.deny("plugh")
        self.allow(("x/y.py", "plugh", "r"))
        self.assertEqual([f.rule for f in hygiene.scan_tree(self.root)], ["deny"])

    def test_text_value_stays_exempt_from_the_rule_it_allows(self):
        self.allow((PY, fx.hex_literal("ABABABAB"), "format tag: x"))
        self.assertEqual([f for f in hygiene.scan_tree(self.root) if f.path == hygiene.ALLOW_FILE], [])


class LocalConfig(Fixture):
    def test_tracked_local_config_is_a_finding(self):
        fx.git_init(self.root)
        fx.write(self.root / "modkit.local.toml", "x = 1\n")
        self.assertEqual(hygiene.scan_tree(self.root), [])  # untracked: skipped
        fx.git(self.root, "add", "-f", "modkit.local.toml")
        self.assertEqual(texts(hygiene.scan_tree(self.root), "local-config-committed"), ["modkit.local.toml"])
        fx.commit_all(self.root)
        fx.git(self.root, "rm", "-q", "--cached", "modkit.local.toml")
        fx.git(self.root, "commit", "-q", "-m", "drop")
        self.assertEqual(hygiene.scan_tree(self.root), [])
        self.assertEqual(texts(hygiene.scan_history(self.root), "local-config-committed"), ["modkit.local.toml"])


class Manifests(Fixture):
    def manifest(self, data):
        fx.write(self.root / ".claude-plugin/marketplace.json", json.dumps(data))
        return [f for f in hygiene.scan_tree(self.root) if f.rule == "manifest-personal"]

    def test_nested_authors_and_maintainers_are_flagged(self):
        self.assertTrue(self.manifest({"name": "warno-modkit", "plugins": [{"name": "warno-core", "maintainers": [{"name": "A"}]}]}))
        self.assertTrue(self.manifest({"plugins": [{"author": "A"}]}))
        self.assertTrue(self.manifest({"plugins": [{"owner": {"name": "A"}}]}))
        self.assertTrue(self.manifest({"plugins": [{"authors": ["A"]}]}))

    def test_urls_emails_and_paths_are_flagged_at_any_depth(self):
        self.assertTrue(self.manifest({"plugins": [{"homepage": "https://example.invalid/u"}]}))
        self.assertTrue(self.manifest({"a": {"b": {"c": "mail a@b.invalid"}}}))
        self.assertTrue(self.manifest({"a": [fx.user_path()]}))

    def test_generic_nested_owner_passes(self):
        self.assertEqual(self.manifest({"plugins": [{"owner": {"name": hygiene.GENERIC_OWNER}}]}), [])


class PrivateRefs(Fixture):
    def test_case_and_underscore_forms(self):
        name = "Un" + "its"
        self.put("components/core/a.txt", f"MODKIT.{name} modkit_{name.lower()} Modkit-{name}\n")
        self.assertEqual(len(texts(hygiene.scan_tree(self.root), "private-ref")), 3)

    def test_component_names_in_any_case_pass(self):
        self.put("components/core/a.txt", "MODKIT.CORE modkit_ops modkit_data modkit.local.toml\n")
        self.assertEqual(hygiene.scan_tree(self.root), [])


if __name__ == "__main__":
    unittest.main()
