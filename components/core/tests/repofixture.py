"""Builders for throwaway repositories used by the component and hygiene tests.

Every string that a repository check would flag (hex addresses, drive-letter paths, private component names,
path escapes) is assembled here at run time, so this file itself stays clean under the checks it supports.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

DOTS = "." * 2


def write(path: Path, text: str | bytes = "") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(text, bytes):
        path.write_bytes(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def make_component(root: Path, name: str, deps=(), imports=(), pyproject_deps=None, plugin_name=None) -> Path:
    """A component with the exact shape; ``imports`` become ``import modkit.<x>`` lines in its package."""
    comp = root / "components" / name
    pdeps = list(deps) if pyproject_deps is None else list(pyproject_deps)
    write(comp / ".claude-plugin" / "plugin.json", json.dumps({
        "name": plugin_name or f"warno-{name}", "version": "0.1.0",
        "dependencies": [f"warno-{d}" for d in deps]}))
    write(comp / "pyproject.toml",
          '[project]\nname = "modkit-%s"\nversion = "0.1.0"\ndependencies = [%s]\n'
          % (name, ", ".join(f'"modkit-{d}"' for d in pdeps)))
    body = "".join(f"import modkit.{x}\n" for x in imports)
    write(comp / "src" / "modkit" / name / "__init__.py", body)
    for sub in ("skills", "examples", "tests", "knowledge/mechanisms", "knowledge/trials", "knowledge/lessons"):
        write(comp / sub / ".gitkeep")
    write(comp / "knowledge" / "topics.md", "# Topics\n")
    write(comp / "knowledge" / "INDEX.md", "# Index\n")
    return comp


def make_repo(root: Path, comps: dict, visibility: str = "public") -> Path:
    """``comps`` maps a component name to a dict of make_component keyword arguments."""
    root.mkdir(parents=True, exist_ok=True)
    write(root / "modkit.repo.toml", f'visibility = "{visibility}"\n')
    for name, kw in comps.items():
        make_component(root, name, **kw)
    from modkit.core.knowledge import render  # the generated navigation is part of a clean repository
    render.render(root)
    return root


def git(root: Path, *args: str) -> str:
    out = subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid", "-c", "commit.gpgsign=false", *args],
        cwd=root, check=True, capture_output=True, text=True)
    return out.stdout


def git_init(root: Path) -> None:
    git(root, "init", "-q")


def commit_all(root: Path, message: str = "c") -> None:
    git(root, "add", "-A")
    git(root, "commit", "-q", "-m", message)


def hex_literal(digits: str = "DEADBEEF") -> str:
    return "0" + "x" + digits


def user_path() -> str:
    return "C" + ":/" + "Users/someone/stuff"
