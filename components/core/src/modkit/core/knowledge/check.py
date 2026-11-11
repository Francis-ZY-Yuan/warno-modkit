"""The consistency check of the knowledge schema. ``check(corpus)`` returns ``(errors, warnings)`` as printable lines.

Errors:

* a record that does not parse or break the schema (a mechanism with no ``topics`` included), a file whose name is
  not its ID, a duplicate ID, a duplicate topic ID, a leftover one-file ``lessons.md``;
* an unknown ID in a ``trials`` / ``mechanisms`` field (a lesson's included) or a ``[[id]]`` citation (in a record,
  a skill or an example), or an ID of the wrong kind in those fields;
* a mechanism topic that no ``topics.md`` declares, or that is declared outside the mechanism's component and its
  dependencies (a project may use any topic it sees);
* a ``PLAYED`` mechanism with no passing play trial;
* a gate or shape that is not a dotted path ``modkit.<component>.<module>.<name>`` naming something defined in
  the record's component or one of its dependencies (resolved by AST, the code is never imported);
* a public record, skill or example that references the ID of a private record;
* a public ``exe-analysis`` mechanism with neither a probe-run or play trial that did not fail nor a gate
  proven both ways (it lists a gate, and has a passing and a failing trial).

Warning: a mechanism whose ``last_verified`` names another game build than the current one. The current build
comes from ``paths.game_build()`` and the warning is skipped when it is unknown.
"""
from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path

from modkit.core import paths
from modkit.core.knowledge import schema
from modkit.core.knowledge.corpus import Corpus, Root

_UNSET = object()


@dataclass(frozen=True)
class Finding:
    repo_root: str
    where: str
    text: str
    warning: bool = False

    def __str__(self) -> str:
        rel = self.where
        try:
            rel = Path(self.where).relative_to(self.repo_root).as_posix()
        except ValueError:
            pass
        return f"{rel}: {self.text}" if rel else self.text


def _same(a: str, b) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(str(b)))


def _top_names(body: list[ast.stmt]) -> dict[str, ast.AST]:
    names: dict[str, ast.AST] = {}
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names[node.name] = node
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                for sub in ast.walk(target):
                    if isinstance(sub, ast.Name):
                        names[sub.id] = node
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names[node.target.id] = node
    return names


class Resolver:
    """Finds the definition a dotted gate or shape name points at, parsing each source file once."""

    def __init__(self, corpus: Corpus):
        self.corpus = corpus
        self._trees: dict[Path, ast.Module | None] = {}

    def _tree(self, path: Path) -> ast.Module | None:
        if path not in self._trees:
            try:
                self._trees[path] = ast.parse(path.read_text(encoding="utf-8"))
            except (OSError, SyntaxError, UnicodeDecodeError, ValueError):
                self._trees[path] = None
        return self._trees[path]

    def _locate(self, root: Root, parts: list[str]) -> tuple[Path, int] | None:
        for i in range(len(parts) - 1, 1, -1):
            base = root.src.joinpath(*parts[2:i])
            for candidate in ((base / "__init__.py",) if i == 2 else (base.with_suffix(".py"), base / "__init__.py")):
                if not candidate.is_file():
                    continue
                tree = self._tree(candidate)
                if tree is None:
                    continue
                body = tree.body
                for number, attr in enumerate(parts[i:]):
                    node = _top_names(body).get(attr)
                    if node is None:
                        break
                    if number == len(parts) - i - 1:
                        return candidate, node.lineno
                    if not isinstance(node, ast.ClassDef):
                        break
                    body = node.body
        return None

    def locate(self, dotted: str) -> tuple[Path, int] | None:
        """The file and line where ``dotted`` is defined, or None."""
        parts = dotted.split(".")
        root = self.corpus.roots.get(parts[1]) if schema.DOTTED_RE.fullmatch(dotted) else None
        return self._locate(root, parts) if root else None

    def problem(self, dotted: str, owner: Root, what: str) -> str | None:
        """Why ``dotted`` is not a valid ``what`` (gate or shape) of a record in ``owner``, or None."""
        if not schema.DOTTED_RE.fullmatch(dotted):
            return f"{what} {dotted!r} is not a dotted path modkit.<component>.<module>.<name>"
        parts = dotted.split(".")
        comp = parts[1]
        if not owner.is_project and comp != owner.name and comp not in self.corpus.closure(owner.name):
            return f"{what} {dotted} is in component {comp}, outside the dependencies of {owner.name}"
        root = self.corpus.roots.get(comp)
        if root is None or self._locate(root, parts) is None:
            return f"{what} {dotted} does not exist"
        return None


def _current(current_build) -> str | None:
    return paths.game_build() if current_build is _UNSET else current_build


def check(corpus: Corpus, current_build=_UNSET, repo=None) -> tuple[list[str], list[str]]:
    """``(errors, warnings)``. ``current_build`` defaults to ``paths.game_build()``; None skips the version
    warning. With ``repo``, only the findings in that repository's own records are returned."""
    findings = _findings(corpus, _current(current_build))
    if repo is not None:
        findings = [f for f in findings if _same(f.repo_root, repo)]
    errors = sorted({str(f) for f in findings if not f.warning})
    warnings = sorted({str(f) for f in findings if f.warning})
    return errors, warnings


def _findings(corpus: Corpus, current: str | None) -> list[Finding]:
    out: list[Finding] = []
    resolver = Resolver(corpus)

    def add(where: schema.Where, text: str, warning: bool = False) -> None:
        out.append(Finding(where.repo_root, where.path, text, warning))

    for issue in corpus.issues:
        out.append(Finding(issue.repo_root, issue.path, issue.text))

    def reference(where: schema.Where, subject: str, verb: str, id_: str, expected: str | None) -> None:
        """One use of an ID: it must exist, be of the expected kind, and not be private from a public place."""
        record = corpus.record(id_)
        if record is None:
            add(where, f"{subject} {verb} unknown {expected + ' ' if expected else ''}ID {id_}")
            return
        if expected and record.record_kind != expected:
            add(where, f"{subject} {id_} is not a {expected}")
        if where.visibility == "public" and record.where.visibility == "private":
            add(where, f"{subject} {verb} private ID {id_}; a public record never links a private one")

    roots = corpus.roots
    for m in corpus.mechanisms.values():
        label = f"mechanism {m.id}:"
        for t in m.trials:
            reference(m.where, label, "lists", t, "trial")
        owner = roots[m.where.component]
        for tid in m.topics:
            topic = corpus.topics.get(tid)
            if topic is None:
                add(m.where, f"{label} topic {tid} is not declared in any topics.md")
            elif (not owner.is_project and topic.where.component != owner.name
                  and topic.where.component not in corpus.closure(owner.name)):
                add(m.where, f"{label} topic {tid} is declared in component {topic.where.component}, outside the "
                             f"dependencies of {owner.name}")
        for what, names in (("gate", m.gates), ("shape", m.shapes)):
            for name in names:
                problem = resolver.problem(name, roots[m.where.component], what)
                if problem:
                    add(m.where, f"{label} {problem}")
        linked = linked_trials(corpus, m)
        if m.status == "PLAYED" and not any(t.kind == "play" and t.outcome == "pass" for t in linked):
            add(m.where, f"{label} is PLAYED but has no passing play trial")
        if m.source == "exe-analysis" and m.where.visibility == "public":
            probed = any(t.kind in ("probe-run", "play") and t.outcome != "fail" for t in linked)
            both = bool(m.gates) and {"pass", "fail"} <= {t.outcome for t in linked}
            if not (probed or both):
                add(m.where, f"{label} a public exe-analysis record needs a probe-run or play trial that did not "
                             "fail, or a gate proven both ways (a passing and a failing trial)")
        build = m.verified_build
        if current and build and build != current:
            add(m.where, f"{label} last verified on game build {build}, not the current {current}", warning=True)
    for t in corpus.trials.values():
        for mid in t.mechanisms:
            reference(t.where, f"trial {t.id}:", "lists", mid, "mechanism")
    for lesson in corpus.lessons.values():
        for tid in lesson.trials:
            reference(lesson.where, f"lesson {lesson.id}:", "lists", tid, "trial")
    for c in corpus.citations:
        subject = f"record {c.source_id}:" if c.kind == "record" else c.kind
        if not schema.ID_RE.fullmatch(c.id):
            add(c.where, f"{subject} malformed-citation: [[{c.id}]] is not a record ID")
            continue
        reference(c.where, subject, "cites", c.id, None)
    return out


def linked_trials(corpus: Corpus, m: schema.Mechanism) -> list[schema.Trial]:
    """The trials of a mechanism: the ones it lists and the ones that list it."""
    ids = {t for t in m.trials if t in corpus.trials}
    ids |= {t.id for t in corpus.trials.values() if m.id in t.mechanisms}
    return [corpus.trials[i] for i in sorted(ids)]

