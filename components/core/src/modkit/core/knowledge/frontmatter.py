"""A restricted YAML front matter, parsed without third-party code.

A record starts with a line ``---``, then ``key: value`` lines, then a line ``---``; the rest is the body. A value
is a scalar, an inline list ``[a, b]`` or a block list (``key:`` followed by ``- item`` lines). Scalars are plain
text or in single or double quotes and always stay strings. Whole-line ``#`` comments and blank lines are skipped.
Anything else (nesting, a repeated key, an unclosed list) is a ``FrontMatterError``.
"""
from __future__ import annotations

import re

KEY = re.compile(r"([A-Za-z_][A-Za-z0-9_]*)\s*:(?:\s+(.*)|\s*)$")
ESCAPES = {"n": "\n", "t": "\t", '"': '"', "\\": "\\"}


class FrontMatterError(ValueError):
    """The text is not valid restricted front matter."""


def _unquote(raw: str, where: str) -> str:
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        inner = raw[1:-1]
        if raw[0] == "'":
            return inner.replace("''", "'")
        return re.sub(r"\\(.)", lambda m: ESCAPES.get(m.group(1), m.group(0)), inner)
    if raw[:1] in "\"'":
        raise FrontMatterError(f"{where}: unclosed quote")
    return raw


def _split_inline(inner: str, where: str) -> list[str]:
    items, cur, quote = [], [], ""
    for ch in inner:
        if quote:
            cur.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'" and not "".join(cur).strip():
            quote = ch
            cur.append(ch)
        elif ch == ",":
            items.append("".join(cur))
            cur = []
        else:
            cur.append(ch)
    if quote:
        raise FrontMatterError(f"{where}: unclosed quote in list")
    items.append("".join(cur))
    items = [i.strip() for i in items]
    if items == [""]:
        return []
    if any(not i for i in items):
        raise FrontMatterError(f"{where}: empty list item")
    return [_unquote(i, where) for i in items]


def split(text: str) -> tuple[list[str], str]:
    """(front matter lines, body) of a record's text."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if not lines or lines[0].rstrip() != "---":
        raise FrontMatterError("line 1: the record must start with a --- line")
    for i in range(1, len(lines)):
        if lines[i].rstrip() == "---":
            body = "\n".join(lines[i + 1:])
            return lines[1:i], body
    raise FrontMatterError("the front matter is not closed by a --- line")


def parse(text: str) -> tuple[dict, str]:
    """``(meta, body)``: ``meta`` maps keys to strings or lists of strings."""
    lines, body = split(text)
    meta: dict = {}
    i = 0
    while i < len(lines):
        number, line = i + 2, lines[i]
        i += 1
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        where = f"line {number}"
        m = KEY.match(line) if not line[0].isspace() else None
        if not m:
            raise FrontMatterError(f"{where}: expected 'key: value', got {line.strip()!r}")
        key, raw = m.group(1), (m.group(2) or "").strip()
        if key in meta:
            raise FrontMatterError(f"{where}: key {key!r} appears twice")
        if raw.startswith("["):
            if not raw.endswith("]"):
                raise FrontMatterError(f"{where}: the list for {key!r} is not closed on the same line")
            meta[key] = _split_inline(raw[1:-1], where)
        elif raw.startswith("- ") or raw == "-":
            raise FrontMatterError(f"{where}: a list item on the key line; use [a, b] or put the items below")
        elif raw:
            meta[key] = _unquote(raw, where)
        else:
            items = []
            while i < len(lines):
                nxt = lines[i]
                if not nxt.strip() or nxt.lstrip().startswith("#"):
                    i += 1
                    continue
                m2 = re.match(r"\s*-\s+(.*\S)\s*$", nxt)
                if not m2:
                    break
                items.append(_unquote(m2.group(1), f"line {i + 2}"))
                i += 1
            meta[key] = items if items else ""
    if body.startswith("\n"):
        body = body[1:]
    return meta, body
