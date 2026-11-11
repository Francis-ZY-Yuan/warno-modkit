"""Build the stock corpus from your own WARNO install, and check it against the game's version.

Purpose: the toolkit ships no Eugen data. Every piece of it that a component reads (the "stock extraction") is
produced here from your install, read-only: the data archives (``edat``) and the mod SDK archive, found through an
index of the install. The list of what to build is declared by the components themselves, as ``STOCK_PATHS`` (see
``modkit.core.stock``).

    python -m modkit.core.setup extract --into DIR   build every declared path under DIR
    python -m modkit.core.setup check                game version; does the extraction / the ndfrules table match it?

``extract`` never writes into the game folder and deletes nothing: files it makes are overwritten on a re-run, other
files in DIR are left alone. Point ``modkit.local.toml`` (``extracted = ...``) at DIR afterwards. After a game update,
``check`` reports STALE: re-run ``extract`` and ``python -m modkit.core.ndfrules extract``.
"""
from __future__ import annotations

import argparse
import ast
import csv
import fnmatch
import importlib
import importlib.util
import json
import os
import pkgutil
import re
import struct
import sys
import zipfile
from dataclasses import dataclass
from pathlib import Path

from modkit.core import edat, ndfrules, paths
from modkit.core.stock import Stock

MANIFEST = "_extraction.json"
INDEX_NAME = "index_all.tsv"
PROVENANCE = "_provenance.tsv"
NOT_STOCK = "# not stock"  # on a line that joins extracted_root() with a path that is not a read of stock data


class SetupError(RuntimeError):
    """The install or the declaration is not what the extraction needs."""


# --------------------------------------------------------------------------- the declared set

def declared() -> list[Stock]:
    """Every ``STOCK_PATHS`` entry of every installed component package, in a stable order, without repeats."""
    spec = importlib.util.find_spec("modkit")  # the namespace package: one folder per installed component
    out: list[Stock] = []
    for info in sorted(pkgutil.iter_modules(spec.submodule_search_locations, "modkit."), key=lambda i: i.name):
        if info.ispkg:
            mod = importlib.import_module(info.name)
            out += [s for s in getattr(mod, "STOCK_PATHS", ()) if s not in out]
    return out


def declared_from_tree(components: Path) -> list[Stock]:
    """The same, read from a repository's ``components/<name>/src/modkit/<name>/__init__.py`` files (no install needed)."""
    out: list[Stock] = []
    for init in sorted(Path(components).glob("*/src/modkit/*/__init__.py")):
        spec = importlib.util.spec_from_file_location(f"_stock_{init.parent.name}", init)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        out += [s for s in getattr(mod, "STOCK_PATHS", ()) if s not in out]
    return out


# --------------------------------------------------------------------------- the reader scan

@dataclass(frozen=True)
class Read:
    file: str
    line: int
    parts: tuple[str, ...]  # path components below the extraction folder, up to the first non-literal or `**`


_WRAPPERS = {"str", "fspath", "Path", "abspath", "normpath", "realpath"}


def _is_root_call(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and
            ((isinstance(node.func, ast.Attribute) and node.func.attr == "extracted_root")
             or (isinstance(node.func, ast.Name) and node.func.id == "extracted_root")))


def _bare_root(node: ast.AST, aliases: set[str]) -> bool:
    """The extraction folder itself: `extracted_root()`, a name bound to it, or either wrapped in str/Path/..."""
    if _is_root_call(node):
        return True
    if isinstance(node, ast.Name):
        return node.id in aliases
    if isinstance(node, ast.Call) and len(node.args) == 1 and not node.keywords:
        name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
        return name in _WRAPPERS and _bare_root(node.args[0], aliases)
    return False


def _literals(args: list[ast.expr]) -> tuple[str, ...]:
    """The consecutive string literals at the start of `args`, split into path components, cut at a `**`."""
    parts: list[str] = []
    for a in args:
        if not (isinstance(a, ast.Constant) and isinstance(a.value, str)):
            break
        parts += [p for p in a.value.replace("\\", "/").split("/") if p]
    for i, p in enumerate(parts):
        if "**" in p:
            return tuple(parts[:i])
    return tuple(parts)


def _chain(node: ast.expr) -> list[ast.expr]:
    """The operands of a `a / b / c` chain, left to right."""
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div):
        return _chain(node.left) + [node.right]
    return [node]


def _scan_file(path: Path) -> list[Read]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), str(path))
    except (SyntaxError, UnicodeDecodeError):
        return []
    aliases: set[str] = set()
    for node in ast.walk(tree):  # names bound to the bare extraction folder
        if isinstance(node, (ast.Assign, ast.AnnAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if _bare_root(node.value, aliases):
                aliases |= {t.id for t in targets if isinstance(t, ast.Name)}
    lines = path.read_text(encoding="utf-8").splitlines()
    reads: list[Read] = []
    inner_chains: set[int] = set()
    for node in ast.walk(tree):
        parts = None
        if isinstance(node, ast.Call):
            fn = node.func
            name = fn.attr if isinstance(fn, ast.Attribute) else getattr(fn, "id", "")
            if name == "join" and node.args and _bare_root(node.args[0], aliases):
                parts = _literals(node.args[1:])
            elif name == "joinpath" and isinstance(fn, ast.Attribute) and _bare_root(fn.value, aliases):
                parts = _literals(node.args)
            elif name == "skip_unless_extracted":
                parts = _literals(node.args)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, ast.Div) and id(node) not in inner_chains:
            ops = _chain(node)
            inner_chains |= {id(n) for n in ast.walk(node.left) if isinstance(n, ast.BinOp)}
            if _bare_root(ops[0], aliases):
                parts = _literals(ops[1:])
        if parts and NOT_STOCK not in lines[node.lineno - 1]:
            reads.append(Read(str(path), node.lineno, parts))
    return reads


def scan_readers(folders) -> list[Read]:
    """Every read of a path below the extraction folder (`extracted_root()` joined with literals, an alias of it,
    or `skip_unless_extracted(...)`) in the Python files under `folders`. A read of the whole folder has no path to
    declare and is not listed; a line marked `# not stock` (a path that only exists to be excluded or tested) is
    skipped."""
    reads: list[Read] = []
    for folder in folders:
        for py in sorted(Path(folder).rglob("*.py")):
            if "__pycache__" not in py.parts:
                reads += _scan_file(py)
    return reads


def _part_match(a: str, b: str) -> bool:
    return a == b or fnmatch.fnmatchcase(a, b) or fnmatch.fnmatchcase(b, a)


def covers(parts: tuple[str, ...], stock: list[Stock]) -> bool:
    """Some entry declares `parts` or a folder above it, or a folder below it (a read of `scenarios` is met by
    `scenarios/challenge_*`). Wildcards match in both directions."""
    for s in stock:
        dest = s.dest.split("/")
        n = min(len(dest), len(parts))
        if all(_part_match(parts[i], dest[i]) for i in range(n)) and (len(parts) <= len(dest) or not s.index):
            return True
    return False


# --------------------------------------------------------------------------- the install's index

@dataclass(frozen=True)
class Row:
    revision: int
    relpath: str   # of the archive below Data/PC, '/'-separated
    inner: str
    size: int


def load_index(tsv: Path) -> dict[str, list[Row]]:
    """The index by archive name (the file name without `.dat`)."""
    by_pack: dict[str, list[Row]] = {}
    with open(tsv, encoding="utf-8", newline="") as fh:
        rows = csv.reader(fh, delimiter="\t")
        next(rows)
        for revision, relpath, inner, size in rows:
            name = relpath.rsplit("/", 1)[-1]
            name = name[:-4] if name.lower().endswith(".dat") else name
            by_pack.setdefault(name, []).append(Row(int(revision), relpath, inner, int(size)))
    return by_pack


def _select(rows: list[Row], stock: Stock, best: dict[str, Row]) -> None:
    """Fold one archive name's rows into `best` (target path -> the row that wins)."""
    if stock.latest:
        top = max(r.revision for r in rows)
        archives = {r.relpath for r in rows if r.revision == top}
        if len(archives) > 1:
            raise SetupError(f"{stock.dest}: revision {top} holds the archive in {sorted(archives)}: no way to pick")
        rows = [r for r in rows if r.revision == top]
    pattern = re.compile(stock.rename[0]) if stock.rename else None
    for r in rows:
        if stock.include and not any(fnmatch.fnmatchcase(r.inner.lower(), g.lower()) for g in stock.include):
            continue
        target = r.inner
        if pattern is not None:
            m = pattern.fullmatch(r.inner)
            if m is None:
                continue
            target = m.expand(stock.rename[1])
        held = best.get(target)
        if held is not None and held.revision == r.revision and held.relpath != r.relpath:
            raise SetupError(f"{stock.dest}/{target}: revision {r.revision} has it in both {held.relpath} and "
                             f"{r.relpath}: no way to pick")
        if held is None or r.revision > held.revision:
            best[target] = r


def plan(stock: Stock, index: dict[str, list[Row]]) -> list[tuple[str, dict[str, Row]]]:
    """[(dest folder, {path below it: the index row to take})] for an archive-pack entry."""
    names: list[tuple[str, tuple[str, ...]]]
    if "*" in stock.dest:
        star = stock.dest.rsplit("/", 1)[-1]
        found: set[str] = set()
        for template in stock.packs:
            rx = re.compile(re.escape(template).replace(re.escape("{}"), "(.+)"))
            found |= {m.group(1) for pack in index if (m := rx.fullmatch(pack))}
        names = [(stock.dest.rsplit("/", 1)[0] + "/" + s if "/" in stock.dest else s,
                  tuple(p.replace("{}", s) for p in stock.packs))
                 for s in sorted(found) if fnmatch.fnmatchcase(s, star)]
        names = [(d, packs) for d, packs in names if any(p in index for p in packs)]
    else:
        names = [(stock.dest, stock.packs)]
    out = []
    for dest, packs in names:
        best: dict[str, Row] = {}
        for pack in packs:
            if pack not in index:
                if "*" in stock.dest:
                    continue
                raise SetupError(f"{dest}: the archive {pack}.dat is not in this install (or the game version differs)")
            _select(index[pack], stock, best)
        out.append((dest, best))
    return out


# --------------------------------------------------------------------------- writing

def _long(path: str) -> str:
    """Windows extended-length form: some inner paths are 190+ characters."""
    path = os.path.abspath(path)
    return "\\\\?\\" + path if os.name == "nt" and not path.startswith("\\\\?\\") else path


def _target(root: Path, dest: str, rel: str) -> str:
    parts = [p for p in rel.split("/") if p not in ("", ".")]
    if not parts or ".." in parts or ":" in parts[0]:
        raise SetupError(f"unsafe inner path {rel!r}")
    return _long(os.path.join(root, *dest.split("/"), *parts))


def _write_pack(root: Path, data_pc: Path, dest: str, best: dict[str, Row], stock: Stock,
                done: set[tuple[str, str, str]]) -> int:
    """Write what `best` selects. A file another entry already wrote in this run (same place, same archive entry)
    is not written again; `done` remembers them."""
    by_archive: dict[str, dict[str, str]] = {}
    written = 0
    for target, row in best.items():
        if (key := (dest, target, row.relpath)) not in done:
            done.add(key)
            by_archive.setdefault(row.relpath, {})[row.inner] = target
            written += 1
    for relpath, wanted in sorted(by_archive.items()):
        dat = str(data_pc.joinpath(*relpath.split("/")))
        entries = {e.path: e for e in edat.read_index(dat)}
        for inner, target in sorted(wanted.items()):
            entry = entries.get(inner)
            if entry is None:
                raise SetupError(f"{relpath}: {inner} is in the index but not in the archive")
            out = _target(root, dest, target)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            check = edat._Checker(entry)
            with open(out, "wb") as fh:
                for chunk in edat.iter_entry_chunks(dat, entry):
                    fh.write(chunk)
                    check.update(chunk)
            if not check.ok():
                raise SetupError(f"{relpath}: {inner} fails its checksum: the archive is damaged (verify the game "
                                 "files in Steam)")
    if stock.provenance:
        prov = _target(root, dest, PROVENANCE)
        with open(prov, "w", encoding="utf-8", newline="") as fh:
            writer = csv.writer(fh, delimiter="\t", lineterminator="\n")
            for target in sorted(best):
                r = best[target]
                writer.writerow([target, r.revision, r.relpath, r.size, True])
    return written


def _write_zip(root: Path, game: Path, stock: Stock) -> int:
    archive = game.joinpath(*stock.archive.split("/"))
    if not archive.is_file():
        raise SetupError(f"{stock.dest}: {stock.archive} is not in the install {game}")
    n = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if stock.include and not any(fnmatch.fnmatchcase(info.filename.lower(), g.lower()) for g in stock.include):
                continue
            out = _target(root, stock.dest, info.filename)
            os.makedirs(os.path.dirname(out), exist_ok=True)
            with zf.open(info) as src, open(out, "wb") as fh:
                fh.write(src.read())
            n += 1
    return n


def extract(into: str | os.PathLike, stock: list[Stock] | None = None) -> dict:
    """Build every declared path under `into` from the configured install. Returns the manifest written."""
    stock = declared() if stock is None else stock
    game = paths.game_dir()
    data_pc = game / "Data" / "PC"
    if not data_pc.is_dir():
        raise SetupError(f"{data_pc} does not exist: game_dir should be the WARNO folder holding Data/PC")
    root = Path(into)
    root.mkdir(parents=True, exist_ok=True)
    build = paths.game_build()
    print(f"indexing {data_pc} ...", flush=True)
    tsv = root / INDEX_NAME
    n_dat, _, n_ent, errors = edat.scan(str(data_pc), str(tsv))
    if errors:
        raise SetupError(f"{len(errors)} archives are unreadable, first: {errors[0]}")
    print(f"  {n_dat} archives, {n_ent} entries", flush=True)
    index = load_index(tsv)
    files = 0
    done: set[tuple[str, str, str]] = set()
    for s in stock:
        if s.index:
            if s.dest != INDEX_NAME:
                raise SetupError(f"{s.dest}: the index is always written as {INDEX_NAME}")
            continue
        if s.archive:
            n = _write_zip(root, game, s)
            print(f"  {s.dest}: {n} files from {s.archive}", flush=True)
            files += n
            continue
        for dest, best in plan(s, index):
            n = _write_pack(root, data_pc, dest, best, s, done)
            files += n
            if n:
                print(f"  {dest}: {n} files", flush=True)
    manifest = {"format": 1, "game_build": build, "exe_size": _exe_size(),
                "stock": sorted({s.dest for s in stock}), "files": files}
    (root / MANIFEST).write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    return manifest


def _exe_size() -> int | None:
    try:
        return os.path.getsize(ndfrules.exe_path())
    except (OSError, paths.NotConfigured):
        return None


# --------------------------------------------------------------------------- check

def _present(root: Path, dest: str) -> bool:
    if "*" not in dest:
        return (root / dest).exists()
    head, _, last = dest.rpartition("/")
    folder = root / head if head else root
    return folder.is_dir() and any(fnmatch.fnmatchcase(p.name, last) for p in folder.iterdir())


def check() -> int:
    """Print the game version and whether the extraction and the ndfrules table match it. 0 when all do."""
    ok = True
    game = paths.game_dir()
    build, exe = paths.game_build(), _exe_size()
    print(f"game: {game}\n  build {build or 'unknown'}, WARNO.exe {exe if exe is not None else 'not found'} bytes")
    ok &= build is not None
    root = paths.extracted_root()
    manifest_path = root / MANIFEST
    if not manifest_path.is_file():
        print(f"extraction: {root}: not extracted (no {MANIFEST}); run `python -m modkit.core.setup extract --into DIR`")
        ok = False
    else:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest.get("game_build"), manifest.get("exe_size")) != (build, exe):
            print(f"extraction: {root}: STALE, made from build {manifest.get('game_build')} "
                  f"(WARNO.exe {manifest.get('exe_size')}), the install is {build} ({exe}); re-run extract")
            ok = False
        else:
            print(f"extraction: {root}: made from build {build}, matches")
        missing = [s.dest for s in declared() if not _present(root, s.dest)]
        if missing:
            shown = ", ".join(missing[:8]) + (f", ... {len(missing) - 8} more" if len(missing) > 8 else "")
            print(f"  {len(missing)} declared paths are missing: {shown}")
            ok = False
    try:
        table = ndfrules.table_path()
    except paths.NotConfigured:
        table = None
    if table is None or not table.is_file():
        print(f"ndfrules: no table{f' at {table}' if table else ''}; run `python -m modkit.core.ndfrules extract`")
        ok = False
    else:
        try:
            _, size = ndfrules.load_table(table)
        except ndfrules.CheckError as exc:
            print(f"ndfrules: {table}: unreadable ({exc}); re-run `python -m modkit.core.ndfrules extract`")
            ok = False
        else:
            if exe is not None and size != exe:
                print(f"ndfrules: {table}: STALE, read from a {size}-byte WARNO.exe, the install's is {exe}; "
                      "re-run `python -m modkit.core.ndfrules extract`")
                ok = False
            else:
                print(f"ndfrules: {table}: read from this WARNO.exe, matches")
    return 0 if ok else 1


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m modkit.core.setup", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("extract", help="build every declared stock path from the install under DIR")
    p.add_argument("--into", required=True, metavar="DIR")
    sub.add_parser("check", help="the game version, and whether the extraction and the ndfrules table match it")
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    try:
        if args.cmd == "extract":
            manifest = extract(args.into)
            print(f"done: {manifest['files']} files for build {manifest['game_build']} in {args.into}\n"
                  f"set `extracted = \"{Path(args.into).as_posix()}\"` in {paths.CONFIG_NAME} (or MODKIT_EXTRACTED)")
            return 0
        return check()
    except (SetupError, paths.NotConfigured, edat.EdatError, OSError, struct.error) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
