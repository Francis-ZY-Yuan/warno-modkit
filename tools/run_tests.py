"""Run the components' test suites as CI does: ``python tools/run_tests.py [SUITE ...]``.

A suite is a component with a ``tests`` folder (``core``, ``ops``); with no SUITE, all of them. Each runs with
``unittest discover`` from the repository root, ops one module per process: a one-process ops run hits a CPython 3.14
crash ("Executing a cache"). Prints each run's output, then the tests run and skipped per suite: the tests that need
the game's data skip without it, so a green run without data is not a full run. Exits 1 if any run fails, 2 on a
bad SUITE.

On GitHub Actions it also folds each run's output into a group, appends the table to ``GITHUB_STEP_SUMMARY`` when
that is set, and adds a notice with the skip counts. Dev tooling only: no plugin ships or imports this file.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ONE_PROCESS_PER_MODULE = {"ops"}
RAN = re.compile(r"^Ran (\d+) tests? in", re.M)
SKIPPED = re.compile(r"^(?:OK|FAILED) \(.*?\bskipped=(\d+)", re.M)
ON_ACTIONS = os.environ.get("GITHUB_ACTIONS") == "true"


def suites() -> list[str]:
    return sorted(p.parent.name for p in (ROOT / "components").glob("*/tests") if p.is_dir())


def run(suite: str, pattern: str) -> tuple[int, int, int]:
    """Run one discover; stream its output and return ``(exit code, tests run, tests skipped)``."""
    tests = f"components/{suite}/tests"
    print(f"::group::{suite} {pattern}" if ON_ACTIONS else f"== {suite} {pattern}", flush=True)
    proc = subprocess.Popen([sys.executable, "-m", "unittest", "discover", "-s", tests, "-t", tests, "-p", pattern],
                            cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, errors="replace")
    lines = []
    for line in proc.stdout:
        lines.append(line)
        print(line, end="", flush=True)
    code = proc.wait()
    out = "".join(lines)
    print(f"exit {code}", flush=True)
    if ON_ACTIONS:
        print("::endgroup::", flush=True)
    ran, skipped = RAN.findall(out), SKIPPED.findall(out)
    return code, int(ran[-1]) if ran else 0, int(skipped[-1]) if skipped else 0


def main(argv: list[str]) -> int:
    sys.stdout.reconfigure(errors="replace")
    known = suites()
    chosen = argv or known
    if any(s not in known for s in chosen):
        print(f"usage: python tools/run_tests.py [SUITE ...]   (suites: {', '.join(known)})")
        return 2
    rows, failed = [], []
    for suite in chosen:
        if suite in ONE_PROCESS_PER_MODULE:
            patterns = sorted(p.name for p in (ROOT / "components" / suite / "tests").glob("test*.py"))
        else:
            patterns = ["test*.py"]
        ran = skipped = 0
        for pattern in patterns:
            code, n, s = run(suite, pattern)
            ran, skipped = ran + n, skipped + s
            if code != 0:
                failed.append(f"{suite} {pattern} (exit {code})")
        rows.append((suite, len(patterns), ran, skipped))

    lines = ["| Suite | Processes | Tests run | Skipped |", "| --- | --- | --- | --- |"]
    lines += [f"| {suite} | {procs} | {ran} | {skipped} |" for suite, procs, ran, skipped in rows]
    lines += ["", "Skipped tests need the game's data: a green run without it is not a full run."]
    if failed:
        lines += ["", "Failed: " + ", ".join(failed)]
    print("\n" + "\n".join(lines))
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        with open(os.environ["GITHUB_STEP_SUMMARY"], "a", encoding="utf-8") as fh:
            fh.write("## Tests\n\n" + "\n".join(lines) + "\n")
    if ON_ACTIONS:
        print("::notice title=Tests skipped without game data::"
              + "; ".join(f"{suite}: {skipped} of {ran} skipped" for suite, _, ran, skipped in rows))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
