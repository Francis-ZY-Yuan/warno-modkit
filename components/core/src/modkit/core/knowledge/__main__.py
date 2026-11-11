"""``python -m modkit.core.knowledge render|check [--stale] [ROOT]``.

ROOT is a repository (a folder with ``modkit.repo.toml``) or a modder's project folder with a ``knowledge/`` folder;
the default is the working folder. ``render`` writes the map into ROOT's ``knowledge/`` folder, the components'
INDEX.md and the records' footers, and deletes the generated pages it no longer writes (``render --stale`` only lists
what is out of date and exits 1 if anything is). ``check`` prints the errors, a stale generated page included, and
the warnings, and exits 1 on any error.
"""
from __future__ import annotations

import sys
from pathlib import Path

from modkit.core.knowledge import check as kcheck
from modkit.core.knowledge import corpus as kcorpus
from modkit.core.knowledge import render

USAGE = "usage: python -m modkit.core.knowledge render|check [--stale] [ROOT]"


def main(argv=None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    only_stale = "--stale" in args
    args = [a for a in args if a != "--stale"]
    if not args or args[0] not in ("render", "check") or len(args) > 2 or any(a.startswith("-") for a in args):
        print(USAGE)
        return 2
    root = Path(args[1] if len(args) > 1 else ".").resolve()
    corpus = kcorpus.load_folder(root)
    repo = root if kcorpus.is_repo(root) else None
    if args[0] == "check":
        errors, warnings = kcheck.check(corpus, repo=repo)
        errors += render.orphan_problems(root, corpus)
        for line in errors:
            print(line)
        for line in warnings:
            print(f"warning: {line}")
        print(f"knowledge check {root.name}: " + (f"{len(errors)} problem(s)" if errors else "ok")
              + (f", {len(warnings)} warning(s)" if warnings else ""))
        return 1 if errors else 0
    if repo is None and not (root / "knowledge").is_dir():
        print(f"{root} is neither a repository (no modkit.repo.toml) nor a project folder (no knowledge/ folder)")
        return 2
    try:
        if only_stale:
            old = render.stale(root, corpus)
            for path in old:
                print(f"out of date: {path.relative_to(root).as_posix()}")
            return 1 if old else 0
        changed = render.render(root, corpus)
    except render.RenderError as exc:
        print(exc)
        return 1
    for path in changed:
        print(f"{'wrote' if path.exists() else 'deleted'} {path.relative_to(root).as_posix()}")
    print(f"knowledge render {root.name}: {len(changed)} file(s) changed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
