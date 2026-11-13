"""The gate framework: one error for every gate in the toolkit, reviewed exceptions, and the fixture comparison
(``check_fixture_text``: a generated text against the expected one kept beside its generator).

A gate is a function that raises ``CheckError`` when a build breaks one of its rules. ``run_gate`` runs one and lets
a failure through only when it was reviewed: the build's pending map (``modkit.core.models.Pending``), ``{gate name:
(exact message, ...)}`` (several for a gate that runs once per file), holds the gate's exact message. Any other
failure, including the same gate with a different message, still stops the build.

A reviewed entry covers the first failure its gate call raised, word for word, and nothing after it. Most gates stop
at their first violation, so while an entry fires the rest of that gate call does not run: a later fault the same
call would have found goes unchecked until the reviewed failure is fixed. The log line says so.
"""
from __future__ import annotations

import difflib
import os
from typing import Callable, Iterable, TypeVar

from modkit.core.models import PENDING, Fired, Pending

T = TypeVar("T")

SUSPENDED = "(the rest of this gate did not run)"  # the tail of a REVIEW PENDING log line


class CheckError(RuntimeError):
    """A gate failed. Every gate in the toolkit raises this class."""


def check(cond: bool, msg: str) -> None:
    """Raise ``CheckError(msg)`` unless ``cond`` holds."""
    if not cond:
        raise CheckError(msg)


def run_gate(name: str, fn: Callable[..., T], *args, pending: Pending, fired: Fired | None = None) -> T | None:
    """``fn(*args)``. A ``CheckError`` whose message equals one of ``pending[name]`` is printed as
    ``REVIEW PENDING: <name>: <message> (the rest of this gate did not run)``, appended to `fired` as (name, message)
    when given, and gives ``None``; any other error is raised. The entry covers that first failure only: whatever
    `fn` would have checked after raising it was not checked."""
    try:
        return fn(*args)
    except CheckError as exc:
        if str(exc) in PENDING.validate_python(pending).get(name, ()):
            print(f"REVIEW PENDING: {name}: {exc} {SUSPENDED}")
            if fired is not None:
                fired.append((name, str(exc)))
            return None
        raise


def check_fixture_text(path: str, text: str, *, bless: bool, label: str, subject: str) -> str:
    """The fixture gate's body: `text` (a typed dump, say) must equal the expected text kept in the file `path`.

    With `bless`, `text` is written to `path` instead (UTF-8, LF; folders made) and 'blessed <label>' returned.
    Otherwise a missing file, or any difference, fails (CheckError) naming the file by `label` and the compared text
    by `subject`, with the first 60 lines of a unified diff (expected, generated); a match returns 'matches <label>'."""
    if bless:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(text)
        return f"blessed {label}"
    check(os.path.isfile(path), f"{label} is missing: run with --bless and review it")
    with open(path, encoding="utf-8") as fh:
        want = fh.read()
    if want != text:
        diff = difflib.unified_diff(want.splitlines(), text.splitlines(), "expected", "generated", lineterm="", n=1)
        check(False, f"{subject} differs from {label} (re-run with --bless if intended):\n"
                     + "\n".join(list(diff)[:60]))
    return f"matches {label}"


def unfired(pending: Pending, fired: Iterable[tuple[str, str]]) -> Fired:
    """The (name, message) entries of `pending` that never fired (the gate now passes, or fails otherwise), sorted:
    reviews that can be closed."""
    seen = set(fired)
    return sorted((name, msg) for name, messages in PENDING.validate_python(pending).items() for msg in messages
                  if (name, msg) not in seen)
