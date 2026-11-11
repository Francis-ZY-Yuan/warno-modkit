"""The component checks, run over a repository root.

Every component under ``components/<name>/`` must have the exact shape, declare the same dependencies in
``plugin.json`` (``warno-<x>``) and ``pyproject.toml`` (``modkit-<x>``), form no cycle, import only
``modkit.<x>`` packages inside its dependency closure, and reach no path outside its own folder. In a public
repository no component may depend on one outside the repository.

Components of another repository are found through the installed package (``importlib.util.find_spec``): the
folder holding ``.claude-plugin/plugin.json`` above ``src/modkit/<x>``, or else the installed distribution's
declared requirements.
"""
from __future__ import annotations

import ast
import importlib.metadata
import importlib.util
import json
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

REPO_FILE = "modkit.repo.toml"
FOOTER_START = "<!-- referenced-by:start -->"
FOOTER_END = "<!-- referenced-by:end -->"
SHAPE_DIRS = ("skills", "examples", "tests", "knowledge/mechanisms", "knowledge/trials", "knowledge/lessons")
SHAPE_FILES = (".claude-plugin/plugin.json", "pyproject.toml", "knowledge/topics.md", "knowledge/INDEX.md")
FOOTED = ("mechanisms", "lessons")  # the record folders whose pages carry a generated "referenced by" block
SKIP_DIRS = {"__pycache__", ".git", ".venv", "node_modules"}
LITERAL_REF = re.compile(r"modkit\.([A-Za-z_]\w*)(?:\.\w+)*")
ESCAPE = re.compile(r"(?<![\w.])\.\.[/\\]|\$\{CLAUDE_PLUGIN_ROOT\}[/\\]\.\.")


@dataclass(frozen=True)
class Problem:
    component: str
    text: str

    def __str__(self) -> str:
        return f"{self.component}: {self.text}" if self.component else self.text


def visibility(root: Path) -> str | None:
    """``public`` or ``private`` from the repository's ``modkit.repo.toml``; None when absent or invalid."""
    try:
        with open(Path(root) / REPO_FILE, "rb") as fh:
            value = tomllib.load(fh).get("visibility")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return value if value in ("public", "private") else None


def repo_components(root: Path) -> list[str]:
    folder = Path(root) / "components"
    return sorted(p.name for p in folder.iterdir() if p.is_dir()) if folder.is_dir() else []


def _plugin_deps(path: Path) -> tuple[str | None, set[str]]:
    """(plugin name, dependency component names) from a plugin.json."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("the top level is not an object")
    if not isinstance(data.get("dependencies", []), list):
        raise ValueError("dependencies is not a list")
    deps = set()
    for dep in data.get("dependencies", []):
        name = dep.get("name", "") if isinstance(dep, dict) else str(dep)
        deps.add(name.removeprefix("warno-"))
    return data.get("name"), deps


def _pyproject_deps(path: Path) -> tuple[str | None, set[str]]:
    """(distribution name, dependency component names) from a pyproject.toml; only ``modkit-*`` count."""
    with open(path, "rb") as fh:
        project = tomllib.load(fh).get("project", {})
    deps = set()
    for req in project.get("dependencies", []):
        name = re.split(r"[\s<>=!~;\[(]", req.strip(), maxsplit=1)[0]
        if name.lower().replace("_", "-").startswith("modkit-"):
            deps.add(name.lower().replace("_", "-").removeprefix("modkit-"))
    return project.get("name"), deps


def _installed_package_dir(name: str) -> Path | None:
    try:
        spec = importlib.util.find_spec(f"modkit.{name}")
    except (ImportError, ValueError):
        return None
    if spec is None:
        return None
    if spec.origin and spec.origin not in ("namespace", "frozen"):
        return Path(spec.origin).parent
    locations = list(spec.submodule_search_locations or [])
    return Path(locations[0]) if locations else None


def resolve_installed(name: str) -> tuple[bool, set[str]]:
    """(found, declared dependencies) for ``modkit.<name>`` installed outside this repository."""
    pkg = _installed_package_dir(name)
    if pkg is None:
        return False, set()
    comp = pkg.parent.parent.parent
    plugin, pyproject = comp / ".claude-plugin" / "plugin.json", comp / "pyproject.toml"
    if plugin.is_file() and pyproject.is_file():
        try:
            return True, _plugin_deps(plugin)[1] | _pyproject_deps(pyproject)[1]
        except (OSError, ValueError):
            pass
    try:
        requires = importlib.metadata.distribution(f"modkit-{name}").requires or []
    except importlib.metadata.PackageNotFoundError:
        return True, set()
    return True, {m.group(1) for r in requires if (m := re.match(r"modkit[-_]([\w]+)", r, re.I))}


def declared_dependencies(comp: Path) -> set[str]:
    """The dependency component names a component folder declares in plugin.json and pyproject.toml (both
    are read; an unreadable file contributes nothing, ``check`` is what reports it)."""
    comp, out = Path(comp), set()
    for reader, rel in ((_plugin_deps, ".claude-plugin/plugin.json"), (_pyproject_deps, "pyproject.toml")):
        try:
            out |= reader(comp / rel)[1]
        except (OSError, ValueError):
            pass
    return out


def dependency_closure(name: str, graph: dict[str, set[str]]) -> set[str]:
    """Every component ``name`` depends on, directly or not, in ``graph`` (name -> direct dependencies)."""
    return _closure(name, graph)


def _installed_from(dist: importlib.metadata.Distribution) -> Path | None:
    """The local folder `dist` was installed from, as pip records it in ``direct_url.json`` (PEP 610) for a plain
    install from a folder and an editable one alike; None when it was not installed from a folder that still exists."""
    try:
        data = json.loads(dist.read_text("direct_url.json") or "null")
        folder = Path.from_uri(data["url"])
    except (OSError, ValueError, TypeError, KeyError):
        return None
    return folder if folder.is_dir() else None


def installed_components() -> dict[str, Path]:
    """Components found through installed ``modkit-*`` distributions: name -> the component folder. Each one's
    folder is the one pip installed it from (``direct_url.json``), which covers a plain install from a plugin's
    folder; a package found on the path in a ``src/modkit/<name>`` layout with no such record (an editable or path
    install) gives the folder above ``src``. Packages installed from neither are left out."""
    out: dict[str, Path] = {}
    for dist in importlib.metadata.distributions():
        name = (dist.metadata["Name"] or "").lower().replace("_", "-")
        if name.startswith("modkit-") and (folder := _installed_from(dist)) is not None:
            out.setdefault(name.removeprefix("modkit-"), folder)
    try:
        spec = importlib.util.find_spec("modkit")
    except (ImportError, ValueError):
        return out
    for location in (spec.submodule_search_locations or []) if spec else []:
        base = Path(location)
        if not base.is_dir():
            continue
        for pkg in sorted(base.iterdir()):
            if (pkg / "__init__.py").is_file() and base.parent.name == "src":
                out.setdefault(pkg.name, base.parent.parent)
    return out


def _shape(comp: Path, name: str) -> list[Problem]:
    out = []
    for rel in SHAPE_FILES:
        if not (comp / rel).is_file():
            out.append(Problem(name, f"missing file {rel}"))
    for rel in SHAPE_DIRS:
        folder = comp / rel
        if not folder.is_dir():
            out.append(Problem(name, f"missing folder {rel}"))
        elif not any(folder.iterdir()):
            out.append(Problem(name, f"empty folder {rel} (add a .gitkeep)"))
    if not (comp / "src" / "modkit" / name / "__init__.py").is_file():
        out.append(Problem(name, f"missing src/modkit/{name}/__init__.py"))
    if (comp / "src" / "modkit" / "__init__.py").exists():
        out.append(Problem(name, "src/modkit/__init__.py must not exist (modkit is a namespace package)"))
    return out


def _declared(comp: Path, name: str, problems: list[Problem]) -> set[str]:
    """The component's dependency names, checking that plugin.json and pyproject.toml agree."""
    plugin_path, pyproject_path = comp / ".claude-plugin" / "plugin.json", comp / "pyproject.toml"
    plugin_deps = pyproject_deps = set()
    try:
        if plugin_path.is_file():
            plugin_name, plugin_deps = _plugin_deps(plugin_path)
            if plugin_name != f"warno-{name}":
                problems.append(Problem(name, f"plugin name {plugin_name!r} must be 'warno-{name}'"))
    except (OSError, ValueError) as exc:
        problems.append(Problem(name, f"plugin.json unreadable: {exc}"))
    try:
        if pyproject_path.is_file():
            dist_name, pyproject_deps = _pyproject_deps(pyproject_path)
            if dist_name != f"modkit-{name}":
                problems.append(Problem(name, f"pyproject name {dist_name!r} must be 'modkit-{name}'"))
    except (OSError, ValueError) as exc:
        problems.append(Problem(name, f"pyproject.toml unreadable: {exc}"))
    for dep in sorted(plugin_deps - pyproject_deps):
        problems.append(Problem(name, f"plugin.json depends on warno-{dep} but pyproject.toml lacks modkit-{dep}"))
    for dep in sorted(pyproject_deps - plugin_deps):
        problems.append(Problem(name, f"pyproject.toml depends on modkit-{dep} but plugin.json lacks warno-{dep}"))
    return plugin_deps | pyproject_deps


def _closure(name: str, graph: dict[str, set[str]]) -> set[str]:
    seen, todo = set(), list(graph.get(name, ()))
    while todo:
        dep = todo.pop()
        if dep not in seen:
            seen.add(dep)
            todo.extend(graph.get(dep, ()))
    return seen


def _cycles(graph: dict[str, set[str]]) -> list[list[str]]:
    found, state = [], {}

    def visit(node, trail):
        state[node] = 1
        for dep in sorted(graph.get(node, ())):
            if state.get(dep) == 1:
                found.append(trail[trail.index(dep):] + [dep] if dep in trail else [node, dep])
            elif dep not in state:
                visit(dep, trail + [dep])
        state[node] = 2

    for node in sorted(graph):
        if node not in state:
            visit(node, [node])
    return found


def _leading_literal(node: ast.AST) -> str:
    """The string a name expression starts with, when it visibly starts with one: ``"a." + x``, f"a.{x}",
    ``"a.%s" % x``, ``"a.{}".format(x)``."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr) and node.values:
        return _leading_literal(node.values[0])
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Mod)):
        return _leading_literal(node.left)
    if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format"):
        return _leading_literal(node.func.value)
    return ""


def _is_import_call(node: ast.Call) -> bool:
    f = node.func
    return (isinstance(f, ast.Attribute) and f.attr in ("import_module", "__import__")) or (
        isinstance(f, ast.Name) and f.id in ("import_module", "__import__"))


def _imported_components(source: str, dynamic: list[int] | None = None) -> set[str]:
    """Components named by imports and by string literals ``modkit.<x>``; line numbers of dynamic imports whose
    argument starts with ``modkit.`` but is not a plain literal go into ``dynamic``."""
    tree = ast.parse(source)
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            m = LITERAL_REF.fullmatch(node.value)
            if m and not node.value.endswith(".toml"):
                names.add(m.group(1))
        elif isinstance(node, ast.Call) and _is_import_call(node) and node.args:
            arg = node.args[0]
            if not isinstance(arg, ast.Constant) and _leading_literal(arg).startswith("modkit."):
                if dynamic is not None:
                    dynamic.append(node.lineno)
        if isinstance(node, ast.Import):
            for alias in node.names:
                parts = alias.name.split(".")
                if parts[0] == "modkit" and len(parts) > 1:
                    names.add(parts[1])
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            parts = node.module.split(".")
            if parts[0] == "modkit":
                if len(parts) > 1:
                    names.add(parts[1])
                else:
                    names.update(alias.name for alias in node.names)
    return names


def _files(folder: Path):
    for path in sorted(folder.rglob("*")):
        rel = path.relative_to(folder).parts
        if path.is_file() and not (SKIP_DIRS & set(rel)) and not any(p.endswith(".egg-info") for p in rel):
            yield path


def _imports(comp: Path, name: str, allowed: set[str], problems: list[Problem]) -> None:
    for path in _files(comp):
        if path.suffix != ".py":
            continue
        rel = path.relative_to(comp).as_posix()
        dynamic: list[int] = []
        try:
            used = _imported_components(path.read_text(encoding="utf-8"), dynamic)
        except (SyntaxError, UnicodeDecodeError, ValueError) as exc:
            problems.append(Problem(name, f"{rel} cannot be parsed for imports: {exc}"))
            continue
        for line in dynamic:
            problems.append(Problem(name, f"{rel}:{line} dynamic-import of a modkit module that cannot be checked"))
        for x in sorted(used - allowed):
            problems.append(Problem(name, f"{rel} imports modkit.{x}, outside the dependency closure of {name}"))


def _escapes(comp: Path, name: str, problems: list[Problem]) -> None:
    for path in _files(comp):
        try:
            data = path.read_bytes()
        except OSError:
            continue
        if b"\0" in data:
            continue
        # The "referenced by" block on a mechanism or lesson page holds generated relative links between components'
        # knowledge folders; ``repocheck`` fails any page whose block is not exactly what ``render`` writes, so it
        # is not scanned here.
        generated = path.suffix == ".md" and path.parent.name in FOOTED and path.parent.parent.name == "knowledge"
        inside = False
        for number, line in enumerate(data.decode("utf-8", "replace").splitlines(), 1):
            if generated and FOOTER_START in line:
                inside = True
            if not inside and ESCAPE.search(line):
                problems.append(Problem(name, f"{path.relative_to(comp).as_posix()}:{number} reaches outside its component folder"))
            if generated and FOOTER_END in line:
                inside = False


def check(root: Path) -> list[Problem]:
    root = Path(root)
    problems: list[Problem] = []
    public = visibility(root)
    if public is None:
        problems.append(Problem("", f"{REPO_FILE} is missing or does not say visibility = public|private"))
    names = repo_components(root)
    graph: dict[str, set[str]] = {}
    for name in names:
        comp = root / "components" / name
        problems += _shape(comp, name)
        graph[name] = _declared(comp, name, problems)
    for name in names:
        for dep in sorted(graph[name]):
            if dep in graph:
                continue
            found, deps = resolve_installed(dep)
            if not found:
                problems.append(Problem(name, f"dependency {dep} is neither in this repository nor installed"))
                graph[dep] = set()
            elif public == "public":
                problems.append(Problem(name, f"public component depends on {dep}, outside the repo"))
                graph[dep] = deps
            else:
                graph[dep] = deps
    for cycle in _cycles(graph):
        problems.append(Problem("", "dependency cycle: " + " -> ".join(cycle)))
    for name in names:
        comp = root / "components" / name
        _imports(comp, name, _closure(name, graph) | {name}, problems)
        _escapes(comp, name, problems)
    return problems
