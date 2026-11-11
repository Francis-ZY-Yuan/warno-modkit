"""The repository check: ``python -m modkit.core.repocheck [--history] [ROOT]``.

Runs the component checks, the knowledge consistency check (``modkit.core.knowledge``), and in a public repository
(``modkit.repo.toml``) the hygiene gates over the tree and, with ``--history``, over every commit. Prints one line
per problem and exits 1 if there is any; knowledge warnings (a mechanism not verified on the current game build)
are printed as ``warning:`` lines and do not count.
"""
from __future__ import annotations

import sys
from pathlib import Path

from modkit.core import components, hygiene
from modkit.core.knowledge import check as knowledge_check
from modkit.core.knowledge import corpus as knowledge_corpus
from modkit.core.knowledge import render as knowledge_render


def knowledge(root: Path) -> tuple[list[str], list[str]]:
    """``(errors, warnings)`` of the records in this repository (see ``modkit.core.knowledge.check``)."""
    corpus = knowledge_corpus.load_repo(Path(root))
    return knowledge_check.check(corpus, repo=root)


def run(root: Path, history: bool = False) -> list:
    """Every problem found, as objects whose str() is the printed line."""
    root = Path(root)
    problems: list = list(components.check(root))
    problems += [components.Problem("knowledge", e) for e in knowledge(root)[0]]
    # generated pages are never edited by hand: a stale, edited or no longer written map page, INDEX.md or footer
    # is a problem
    problems += [components.Problem("knowledge", e) for e in knowledge_render.problems(root)]
    if components.visibility(root) == "public":
        problems += hygiene.scan_tree(root)
        if history:
            problems += hygiene.scan_history(root)
        problems += [components.Problem("allowlist", f"stale entry {e.path} / {e.text}") for e in hygiene.stale_allowlist(root)]
    return problems


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    history = "--history" in args
    rest = [a for a in args if a != "--history"]
    if len(rest) > 1 or any(a.startswith("-") for a in rest):
        print("usage: python -m modkit.core.repocheck [--history] [ROOT]")
        return 2
    root = Path(rest[0] if rest else ".").resolve()
    problems = run(root, history)
    for p in problems:
        print(p)
    for w in knowledge(root)[1]:
        print(f"warning: knowledge: {w}")
    kind = components.visibility(root) or "unknown visibility"
    print(f"repocheck {root.name} ({kind}{', with history' if history else ''}): "
          + (f"{len(problems)} problem(s)" if problems else "ok"))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
