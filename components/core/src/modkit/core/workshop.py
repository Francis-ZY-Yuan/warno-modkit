"""A Steam Workshop item's page, kept in a repository and checked against the live page.

An ``item.toml`` names the item and the files its page shows: ``id``, ``mod_name`` (``Config.ini``'s ``Name``, the
title every upload resets to), ``title``, ``description`` (a BBCode template), ``preview`` (the main image), ``gallery``
(the extra images, in order) and ``vars``, the ``{{name}}`` placeholders of the template. A path is relative to the
toml's folder, or, when it starts with ``/``, to the repository root: the nearest folder above the toml that holds
``.git`` (a folder, or a file in a worktree) or ``modkit.repo.toml``. A placeholder's value is personal (such as the
GitHub owner), so it is never in the tracked files: it comes from the git-ignored ``modkit.local.toml``, table
``[workshop.vars]``.

The live page is read from Steam's public ``GetPublishedFileDetails``, which needs no key: the title, description,
main image, visibility and counts, not the gallery. What sets each part of the page: [[workshop-item-page]].

  python -m modkit.core.workshop check <item.toml> [--offline]   validate, then compare with the live page
  python -m modkit.core.workshop render <item.toml>              the filled description, to paste (UTF-8)
  python -m modkit.core.workshop status <id> [<id> ...]          title, visibility, dates and counts per item

``check`` exits 0 when everything matches, 1 on a problem or a mismatch, 2 on a usage or network error.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tomllib
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from modkit.core import paths

API_URL = "https://api.steampowered.com/ISteamRemoteStorage/GetPublishedFileDetails/v1/"
USER_AGENT = "warno-modkit"
# Steam's limits on an item's page.
MAX_TITLE = 128
MAX_DESCRIPTION = 8000
MAX_PREVIEW_BYTES = 1048576
PREVIEW_SUFFIXES = (".jpg", ".jpeg", ".png", ".gif")
VISIBILITY = {0: "public", 1: "friends-only", 2: "private", 3: "unlisted"}
# Fields only reported, never a mismatch.
REPORT_ONLY = ("visibility", "gallery")
# What `status` prints, in this order, when the API returns it.
STATUS_COUNTS = ("file_size", "subscriptions", "lifetime_subscriptions", "favorited", "views")
VARS_TABLE = "[workshop.vars]"
ROOT_MARKERS = (".git", "modkit.repo.toml")  # a folder holding either is a repository root

PLACEHOLDER = re.compile(r"\{\{([A-Za-z_]\w*)\}\}")
BRACES = re.compile(r"\{\{.*?\}\}")
_FIELDS = {"id": int, "mod_name": str, "title": str, "description": str, "preview": str, "gallery": list,
           "vars": list}


class FetchError(RuntimeError):
    """Steam's answer is not the expected JSON."""


@dataclass(frozen=True)
class Item:
    path: Path
    id: int
    mod_name: str
    title: str
    template: str
    preview: Path
    gallery: tuple[Path, ...]
    vars: tuple[str, ...]
    description: Path  # the template's file; ``template`` is "" when it is missing


@dataclass(frozen=True)
class Diff:
    field: str
    ok: bool
    detail: str


def repo_root(path) -> Path | None:
    """The nearest folder holding ``path`` (resolved) that has one of ``ROOT_MARKERS``; None when there is none."""
    start = Path(path).resolve()
    for folder in [start.parent, *start.parent.parents]:
        if any((folder / m).exists() for m in ROOT_MARKERS):
            return folder
    return None


def load_item(path) -> Item:
    """Read an ``item.toml``. Raises ``ValueError`` naming a missing, mistyped or unknown field, or a ``/`` path with
    no repository root above the toml; an absent toml raises ``OSError``. A missing description file reads as an empty
    template (``validate`` reports it)."""
    path = Path(path)
    with open(path, "rb") as fh:
        raw = tomllib.load(fh)
    unknown = sorted(set(raw) - set(_FIELDS))
    if unknown:
        raise ValueError(f"{path.name}: unknown field(s) {', '.join(unknown)}")
    for name, kind in _FIELDS.items():
        if name not in raw:
            raise ValueError(f"{path.name}: missing field {name!r}")
        value = raw[name]
        if not isinstance(value, kind) or isinstance(value, bool):
            raise ValueError(f"{path.name}: {name!r} must be {kind.__name__}, not {type(value).__name__}")
        if kind is list and not all(isinstance(v, str) for v in value):
            raise ValueError(f"{path.name}: {name!r} must be a list of strings")
    root = None

    def resolve(value: str) -> Path:
        nonlocal root
        if not value.startswith("/"):
            return path.parent / value
        root = root or repo_root(path)
        if root is None:
            raise ValueError(f"{path.name}: {value!r} is from the repository root, but no folder above "
                             f"{path.name} holds {' or '.join(ROOT_MARKERS)}")
        return root / value.lstrip("/")

    description = resolve(raw["description"])
    template = description.read_text(encoding="utf-8") if description.is_file() else ""
    return Item(path=path, id=raw["id"], mod_name=raw["mod_name"], title=raw["title"], template=template,
                preview=resolve(raw["preview"]), gallery=tuple(resolve(g) for g in raw["gallery"]),
                vars=tuple(raw["vars"]), description=description)


def _rel(item: Item, p: Path) -> str:
    """``p`` as the toml would write it: from the toml's folder, else ``/`` and from the repository root."""
    try:
        return p.relative_to(item.path.parent).as_posix()
    except ValueError:
        pass
    root = repo_root(item.path)
    try:
        return "/" + p.resolve().relative_to(root).as_posix() if root is not None else p.as_posix()
    except ValueError:
        return p.as_posix()


def validate(item: Item) -> list[str]:
    """The problems found offline, one line each; ``[]`` when there are none."""
    out = []
    if item.id <= 0:
        out.append(f"id: {item.id} is not a Workshop item ID")
    if not item.title:
        out.append("title: empty")
    elif len(item.title) > MAX_TITLE:
        out.append(f"title: {len(item.title)} characters, over Steam's {MAX_TITLE}")
    if not item.description.is_file():
        out.append(f"description: {_rel(item, item.description)} not found")
    elif len(item.template) > MAX_DESCRIPTION:
        out.append(f"description: {len(item.template)} characters, over Steam's {MAX_DESCRIPTION}")
    if not item.preview.is_file():
        out.append(f"preview: {_rel(item, item.preview)} not found")
    else:
        if item.preview.suffix.lower() not in PREVIEW_SUFFIXES:
            out.append(f"preview: {_rel(item, item.preview)} is not one of {', '.join(PREVIEW_SUFFIXES)}")
        size = item.preview.stat().st_size
        if size > MAX_PREVIEW_BYTES:
            out.append(f"preview: {size} bytes, over Steam's {MAX_PREVIEW_BYTES}")
    for g in item.gallery:
        if not g.is_file():
            out.append(f"gallery: {_rel(item, g)} not found")
    used = PLACEHOLDER.findall(item.template)
    for bad in BRACES.findall(item.template):
        if not PLACEHOLDER.fullmatch(bad):
            out.append(f"description: {bad} is not a placeholder (write {{{{name}}}})")
    for name in sorted(set(used) - set(item.vars)):
        out.append(f"description: {{{{{name}}}}} is not in vars")
    for name in item.vars:
        if name not in used:
            out.append(f"vars: {name!r} is not used in the description")
    return out


def local_vars() -> dict[str, str]:
    """``[workshop.vars]`` of ``modkit.local.toml`` (found as ``modkit.core.paths`` finds it); ``{}`` when absent."""
    table = paths.local_config().get("workshop", {}).get("vars", {})
    if not isinstance(table, dict) or not all(isinstance(v, str) for v in table.values()):
        raise ValueError(f"{paths.CONFIG_NAME}: {VARS_TABLE} must hold strings")
    return dict(table)


def render(item: Item, values: dict[str, str]) -> str:
    """The description with every placeholder filled, without trailing newlines (the live page has none). Raises
    ``ValueError`` naming each placeholder that has no value."""
    missing = sorted({n for n in PLACEHOLDER.findall(item.template) if n not in values})
    if missing:
        raise ValueError("no value for " + ", ".join(f"{{{{{n}}}}}" for n in missing))
    return PLACEHOLDER.sub(lambda m: values[m.group(1)], item.template).rstrip("\r\n")


def _request(url: str, data: bytes | None = None) -> urllib.request.Request:
    headers = {"User-Agent": USER_AGENT}
    if data is not None:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    return urllib.request.Request(url, data=data, headers=headers, method="POST" if data is not None else "GET")


def fetch(ids, *, opener=urllib.request.urlopen, timeout=20) -> list[dict]:
    """``response.publishedfiledetails`` for these item IDs, from Steam's keyless API. A network failure raises
    ``OSError``; an answer of another shape raises ``FetchError``."""
    ids = [int(i) for i in ids]
    if not ids:
        raise ValueError("no item IDs")
    form = [("itemcount", str(len(ids)))] + [(f"publishedfileids[{n}]", str(i)) for n, i in enumerate(ids)]
    with opener(_request(API_URL, urllib.parse.urlencode(form).encode("ascii")), timeout=timeout) as resp:
        body = resp.read()
    try:
        details = json.loads(body.decode("utf-8"))["response"]["publishedfiledetails"]
    except (ValueError, KeyError, TypeError) as exc:
        raise FetchError(f"unexpected answer from {API_URL}: {exc}") from None
    if not isinstance(details, list) or not all(isinstance(d, dict) for d in details):
        raise FetchError(f"unexpected answer from {API_URL}: publishedfiledetails is not a list of items")
    return details


def download(url: str, *, opener=urllib.request.urlopen, timeout=20) -> bytes:
    """The bytes served at ``url``."""
    with opener(_request(url), timeout=timeout) as resp:
        return resp.read()


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _first_difference(live: str, local: str) -> str:
    a, b = live.split("\n"), local.split("\n")
    for n, (x, y) in enumerate(zip(a, b), 1):
        if x != y:
            return f"line {n} differs: live {x[:60]!r}, local {y[:60]!r}"
    return f"live has {len(a)} lines, local {len(b)}"


def compare(item: Item, live: dict, description: str | None, preview_bytes: bytes | None) -> list[Diff]:
    """The live item (one entry of ``fetch``) against the item: one ``Diff`` per field. ``description`` is the
    rendered description (None when it could not be rendered); ``preview_bytes`` the bytes served at the live
    ``preview_url`` (None when not downloaded). Only ``item`` is returned when the live item is not found."""
    result = live.get("result")
    if result != 1:
        return [Diff("item", False, f"{item.id} not found (result {result})")]
    if str(live.get("publishedfileid", item.id)) != str(item.id):
        return [Diff("item", False, f"the answer is for {live.get('publishedfileid')}, not {item.id}")]
    out = [Diff("item", True, f"{item.id} found")]

    title = live.get("title", "")
    if title == item.title:
        out.append(Diff("title", True, "matches"))
    else:
        reset = " (an upload reset it to mod_name)" if title == item.mod_name else ""
        out.append(Diff("title", False, f"live {title!r}{reset}, local {item.title!r}"))

    if description is None:
        out.append(Diff("description", False, "not compared: the description could not be rendered"))
    else:
        text = live.get("description", "").replace("\r\n", "\n")
        if text == description:
            out.append(Diff("description", True, f"matches ({len(text)} characters)"))
        else:
            out.append(Diff("description", False, _first_difference(text, description)))

    if not live.get("preview_url"):
        out.append(Diff("preview", False, "the live item has no preview_url"))
    elif preview_bytes is None:
        out.append(Diff("preview", False, "the live preview was not downloaded"))
    elif not item.preview.is_file():
        out.append(Diff("preview", False, f"{_rel(item, item.preview)} not found"))
    else:
        live_sha, local_sha = _sha(preview_bytes), _sha(item.preview.read_bytes())
        if live_sha == local_sha:
            out.append(Diff("preview", True, f"matches (sha256 {local_sha[:12]})"))
        else:
            out.append(Diff("preview", False, f"live sha256 {live_sha[:12]} ({len(preview_bytes)} bytes), local "
                                              f"{local_sha[:12]} ({item.preview.stat().st_size} bytes)"))

    vis = live.get("visibility")
    out.append(Diff("visibility", True, VISIBILITY.get(vis, f"unknown ({vis})")))
    out.append(Diff("gallery", True, f"not checked: the keyless API does not list the extra images; compare the "
                                     f"{len(item.gallery)} local ones with the item's page by eye"))
    return out


# --------------------------------------------------------------------------- CLI

def _advice(item: Item, diff: Diff, render_error: Exception | None) -> str:
    if diff.field == "description" and render_error is not None:
        return f"{render_error}: add it under {VARS_TABLE} in {paths.CONFIG_NAME}"
    if diff.field in ("title", "description"):
        return (f"re-apply it on the item's \"Edit title & description\" page (every upload resets the title to "
                f"mod_name, {item.mod_name!r})")
    if diff.field == "preview":
        return (f"point PreviewImagePath in the installed mod's Config.ini at a copy of {_rel(item, item.preview)} "
                f"outside the mod folder, at a path without your user name, and upload again")
    return ""


def _line(diff: Diff, advice: str = "") -> str:
    mark = "info" if diff.field in REPORT_ONLY else ("ok" if diff.ok else "FAIL")
    return f"{mark:<4}  {diff.field}: {diff.detail}" + (f" -> {advice}" if advice else "")


def _when(stamp) -> str:
    return datetime.fromtimestamp(int(stamp), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _check(args, opener) -> int:
    try:
        item = load_item(args.item)
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"FAIL  {exc}")
        return 1
    print(f"{item.path.as_posix()}: {item.mod_name}, Workshop item {item.id}")
    problems = validate(item)
    try:
        values = local_vars()
    except ValueError as exc:
        problems.append(str(exc))
        values = {}
    for p in problems:
        print(f"FAIL  {p}")
    try:
        description, render_error = render(item, values), None
    except ValueError as exc:
        description, render_error = None, exc
    if args.offline:
        if not problems:
            print(f"ok    offline: {len(item.vars)} var(s), {len(item.gallery)} gallery image(s), every file present")
        if render_error is not None:
            print(f"info  vars: {render_error}: add it under {VARS_TABLE} in {paths.CONFIG_NAME} to render or check "
                  f"online")
        return 1 if problems else 0
    try:
        live = fetch([item.id], opener=opener)
        live = live[0] if live else {"result": None}
        preview = None
        if live.get("result") == 1 and live.get("preview_url"):
            preview = download(live["preview_url"], opener=opener)
    except (OSError, FetchError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    diffs = compare(item, live, description, preview)
    for d in diffs:
        print(_line(d, "" if d.ok else _advice(item, d, render_error)))
    return 1 if problems or not all(d.ok for d in diffs) else 0


def _render(args) -> int:
    try:
        item = load_item(args.item)
        values = local_vars()
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    try:
        text = render(item, values)
    except ValueError as exc:
        print(f"error: {exc}: add it under {VARS_TABLE} in {paths.CONFIG_NAME}", file=sys.stderr)
        return 1
    buffer = getattr(sys.stdout, "buffer", None)
    if sys.stdout.isatty() or buffer is None:
        sys.stdout.write(text + ("\n" if sys.stdout.isatty() else ""))
    else:
        # Piped: the exact UTF-8 bytes, with no newline translation (Windows text mode would write CRLF).
        sys.stdout.flush()
        buffer.write(text.encode("utf-8"))
        buffer.flush()
    return 0


def _status(args, opener) -> int:
    try:
        details = fetch(args.ids, opener=opener)
    except (OSError, FetchError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    missing = 0
    by_id = {str(d.get("publishedfileid")): d for d in details}
    for i in args.ids:
        d = by_id.get(str(i), {})
        if d.get("result") != 1:
            missing += 1
            print(f"{i}: not found (result {d.get('result')})")
            continue
        print(f"{i}: {d.get('title', '')}")
        vis = d.get("visibility")
        print(f"  visibility: {VISIBILITY.get(vis, f'unknown ({vis})')}")
        for key, label in (("time_created", "created"), ("time_updated", "updated")):
            if d.get(key) is not None:
                print(f"  {label}: {_when(d[key])}")
        for key in STATUS_COUNTS:
            if d.get(key) is not None:
                print(f"  {key}: {d[key]}")
    return 1 if missing else 0


def main(argv: list[str] | None = None, *, opener=urllib.request.urlopen) -> int:
    ap = argparse.ArgumentParser(prog="python -m modkit.core.workshop", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("check", help="validate an item.toml, then compare it with the live page")
    p.add_argument("item", type=Path)
    p.add_argument("--offline", action="store_true", help="validate only")
    p = sub.add_parser("render", help="print the filled description, to paste")
    p.add_argument("item", type=Path)
    p = sub.add_parser("status", help="title, visibility, dates and counts of live items")
    p.add_argument("ids", nargs="+", type=int)
    args = ap.parse_args(sys.argv[1:] if argv is None else argv)
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is not None:
        reconfigure(encoding="utf-8")
    if args.cmd == "check":
        return _check(args, opener)
    if args.cmd == "render":
        return _render(args)
    return _status(args, opener)


if __name__ == "__main__":
    sys.exit(main())
