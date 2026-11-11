"""What the probe tests share: the probes example on sys.path, its profile's bindings of the shared gates, and a
quiet build. Not a test module itself.

The example is found from this component's own folder (a clone's components/ops, or an installed plugin's folder),
and the test builds go to a temporary folder, the profile's build root while the tests run."""
from __future__ import annotations

import atexit
import dataclasses
import os
import shutil
import sys
import tempfile
from pathlib import Path

COMPONENT = Path(__file__).resolve().parents[1]   # the ops component: its tests/, examples/, src/, ...
PROBES = COMPONENT / "examples" / "probes"
sys.path.insert(0, str(PROBES))

from modkit.ops import INGAME_DIC  # noqa: E402
from modkit.ops import build as ops_build  # noqa: E402
from modkit.ops import gates, leveldesign, testing  # noqa: E402
from modkit.ops.profile import SURVIVORS, Content, extracted  # noqa: E402
from probes import CONTENTS, profile  # noqa: E402

OUT_ROOT = tempfile.mkdtemp(prefix="modkit-ops-probes-")   # test builds, removed after each test
atexit.register(shutil.rmtree, OUT_ROOT, True)
SURVIVORS_GDSCRIPT = os.path.join("kreide_op", "challenge_Survivors_Definition")  # what a script test reads


def template_gdscript() -> str:
    """Survivors' GDScript, every probe script's input."""
    return SURVIVORS.gdscript()


def build_profile():
    """The probes' profile with OUT_ROOT as its build root, so a rebuild may clear a test build there."""
    return dataclasses.replace(profile.profile(), build_root=OUT_ROOT)


def quiet_build(content: Content, out_dir: str):
    """The probes' build of `content` (every gate) with its report swallowed."""
    return testing.quiet_build(build_profile(), content, out_dir)


def probe_main(argv: list[str]) -> int:
    """The probes' build.py front end."""
    return ops_build.cli(build_profile, CONTENTS, argv)


def details_files(items, scenario: str = profile.SCENARIO) -> dict[str, bytes]:
    """The generated Details files of `items` under the probes' profile, keyed to `scenario`."""
    return ops_build.details_files(profile.profile(), items, scenario)


def check_canonical(raw: bytes, shared: frozenset[str], what: str) -> None:
    """gates.check_canonical with the probes' import rule (stock's trie)."""
    gates.check_canonical(raw, shared, what, import_rule="trie")


def check_end_funnel(roots) -> tuple[int, bool]:
    """gates.check_end_funnel for the probes' funnel and race."""
    return gates.check_end_funnel(roots, (profile.END_FUNNEL, profile.END_RACE))


def end_funnel_violations(roots):
    return gates.end_funnel_violations(roots, (profile.END_FUNNEL, profile.END_RACE))


def scenario_guid(scenario: str) -> bytes:
    return leveldesign.scenario_guid(scenario, profile.GUID_NAMESPACE)


def ld_guid(it, scenario: str) -> bytes:
    return leveldesign.ld_guid(it, scenario, profile.GUID_NAMESPACE)


def ingame_keys(lang: str) -> frozenset[int]:
    """The token hashes of the game's INTERFACE_INGAME dictionary in `lang`."""
    return gates.ingame_keys(extracted(INGAME_DIC.format(lang=lang)))
