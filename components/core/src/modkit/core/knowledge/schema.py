"""The record schema: the three record types, their fields, the validation of a parsed front matter, and topics.

``mechanism_from``, ``trial_from`` and ``lesson_from`` turn ``(meta, body)`` into a record or raise ``SchemaError``
listing every problem. ``parse_topics`` reads a component's ``topics.md``: the topics its mechanisms are filed under.
Topic IDs are a namespace of their own; a ``[[id]]`` never cites a topic.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass

STATUSES = ("PLAYED", "PROBED", "RE", "STOCK", "FAILED", "UNTESTED")
SOURCES = ("play", "stock-data", "exe-analysis")
KINDS = ("launch", "play", "probe-run", "re", "survey")
OUTCOMES = ("pass", "fail", "mixed")

ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TRIAL_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)")
LAST_VERIFIED_RE = re.compile(r"(\d+) (\d{4}-\d{2}-\d{2})")
DOTTED_RE = re.compile(r"modkit(?:\.[A-Za-z_]\w*){3,}")
# Anything that looks like [[...]] is a citation; the text inside, trimmed, must be a record ID or the check
# reports it as malformed-citation (so [[ id ]], [[a|b]] and [[id#x]] never slip through unread).
CITATION_RE = re.compile(r"\[\[([^\[\]]*)\]\]")

MECHANISM_FIELDS = ("id", "title", "status", "last_verified", "source", "topics", "gates", "shapes", "trials",
                    "stock_precedent")
TRIAL_FIELDS = ("id", "kind", "build", "game_version", "mechanisms", "outcome", "symptom", "cause", "result")
LESSON_FIELDS = ("id", "title", "trials")
LIST_FIELDS = frozenset({"topics", "gates", "shapes", "trials", "mechanisms"})
MAX_TOPICS = 3


class SchemaError(ValueError):
    """A record breaks the schema; ``problems`` lists every violation."""

    def __init__(self, problems: list[str]):
        super().__init__("; ".join(problems))
        self.problems = problems


@dataclass(frozen=True)
class Where:
    """Where a record lives: its component, the repository's visibility and its file."""
    component: str
    visibility: str
    repo_root: str
    path: str


@dataclass(frozen=True)
class Mechanism:
    id: str
    title: str
    status: str
    last_verified: str
    source: str
    topics: tuple[str, ...]
    gates: tuple[str, ...]
    shapes: tuple[str, ...]
    trials: tuple[str, ...]
    stock_precedent: str
    body: str
    where: Where

    record_kind = "mechanism"

    @property
    def verified_build(self) -> str | None:
        m = LAST_VERIFIED_RE.fullmatch(self.last_verified)
        return m.group(1) if m else None


@dataclass(frozen=True)
class Trial:
    id: str
    kind: str
    build: str
    game_version: str
    mechanisms: tuple[str, ...]
    outcome: str
    symptom: str
    cause: str
    result: str
    body: str
    where: Where

    record_kind = "trial"

    @property
    def date(self) -> str:
        return self.id[:10]


@dataclass(frozen=True)
class Lesson:
    id: str
    title: str  # the rule
    trials: tuple[str, ...]
    body: str
    where: Where

    record_kind = "lesson"


@dataclass(frozen=True)
class Topic:
    """A heading of a component's ``topics.md``: what its mechanisms are filed under."""
    id: str
    title: str
    scope: str
    where: Where


@dataclass(frozen=True)
class Citation:
    """A ``[[id]]`` in a record body (kind ``record``), a skill or an example."""
    id: str
    kind: str  # record | skill | example
    source_id: str  # the citing record's ID, or "" for a skill or example
    where: Where


def _strings(meta: dict, names: tuple[str, ...], problems: list[str]) -> dict:
    unknown = sorted(set(meta) - set(names))
    for key in unknown:
        problems.append(f"unknown field {key!r}")
    out = {}
    for name in names:
        value = meta.get(name)
        if name in LIST_FIELDS:
            if value is None:
                out[name] = ()
            elif isinstance(value, list):
                out[name] = tuple(value)
            else:
                problems.append(f"{name} must be a list like [a, b]")
                out[name] = ()
        else:
            if isinstance(value, list):
                problems.append(f"{name} must be a single value, not a list")
                value = ""
            out[name] = value or ""
    return out


def _require(values: dict, names: tuple[str, ...], problems: list[str]) -> None:
    for name in names:
        if not values.get(name):
            problems.append(f"missing field {name}")


def _enum(values: dict, name: str, allowed: tuple[str, ...], problems: list[str]) -> None:
    if values[name] and values[name] not in allowed:
        problems.append(f"{name} {values[name]!r} must be one of {', '.join(allowed)}")


def _valid_date(text: str) -> bool:
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def mechanism_from(meta: dict, body: str, where: Where) -> Mechanism:
    problems: list[str] = []
    v = _strings(meta, MECHANISM_FIELDS, problems)
    _require(v, ("id", "title", "status", "source"), problems)
    if v["id"] and not ID_RE.fullmatch(v["id"]):
        problems.append(f"id {v['id']!r} must be kebab-case (lower case letters, digits and single dashes)")
    _enum(v, "status", STATUSES, problems)
    _enum(v, "source", SOURCES, problems)
    if not v["topics"]:
        problems.append(f"missing field topics (1 to {MAX_TOPICS} topic IDs declared in a topics.md)")
    elif len(v["topics"]) > MAX_TOPICS:
        problems.append(f"topics lists {len(v['topics'])} topics; give 1 to {MAX_TOPICS}")
    for topic in v["topics"]:
        if not ID_RE.fullmatch(topic):
            problems.append(f"topic {topic!r} must be kebab-case")
    if len(set(v["topics"])) != len(v["topics"]):
        problems.append("topics lists a topic twice")
    if v["status"] != "UNTESTED" and v["status"] in STATUSES and not v["last_verified"]:
        problems.append("missing field last_verified (only UNTESTED may leave it out)")
    if v["last_verified"]:
        m = LAST_VERIFIED_RE.fullmatch(v["last_verified"])
        if not m or not _valid_date(m.group(2)):
            problems.append(f"last_verified {v['last_verified']!r} must read '<game build> <YYYY-MM-DD>'")
    if problems:
        raise SchemaError(problems)
    return Mechanism(body=body, where=where, **v)


def trial_from(meta: dict, body: str, where: Where) -> Trial:
    problems: list[str] = []
    v = _strings(meta, TRIAL_FIELDS, problems)
    _require(v, ("id", "kind", "build", "game_version", "outcome"), problems)
    if v["id"]:
        m = TRIAL_ID_RE.fullmatch(v["id"])
        if not m or not _valid_date(m.group(1)):
            problems.append(f"id {v['id']!r} must read YYYY-MM-DD-slug with a real date and a kebab-case slug")
    _enum(v, "kind", KINDS, problems)
    _enum(v, "outcome", OUTCOMES, problems)
    if problems:
        raise SchemaError(problems)
    return Trial(body=body, where=where, **v)


def lesson_from(meta: dict, body: str, where: Where) -> Lesson:
    problems: list[str] = []
    v = _strings(meta, LESSON_FIELDS, problems)
    _require(v, ("id", "title"), problems)
    if v["id"] and not ID_RE.fullmatch(v["id"]):
        problems.append(f"id {v['id']!r} must be kebab-case (lower case letters, digits and single dashes)")
    if not v["trials"]:
        problems.append("missing field trials (the trials that taught the lesson)")
    if problems:
        raise SchemaError(problems)
    return Lesson(body=body, where=where, **v)


def parse_topics(text: str, where: Where) -> tuple[list[Topic], list[str]]:
    """``(topics, problems)`` of a ``topics.md``: one ``## <topic-id>: <title>`` heading per topic, followed by one
    sentence of scope. Text above the first heading is ignored."""
    topics: list[Topic] = []
    problems: list[str] = []
    sections: list[tuple[str, list[str]]] = []
    for line in text.replace("\r\n", "\n").split("\n"):
        if line.startswith("## "):
            sections.append((line[3:].strip(), []))
        elif sections:
            sections[-1][1].append(line)
    for heading, lines in sections:
        m = re.fullmatch(r"([^\s:]+):\s+(.+)", heading)
        if not m or not ID_RE.fullmatch(m.group(1)):
            problems.append(f"topic heading {'## ' + heading!r} must read '## <topic-id>: <title>' with a kebab-case id")
            continue
        scope = " ".join(line.strip() for line in lines if line.strip())
        if not scope:
            problems.append(f"topic {m.group(1)} needs a sentence of scope under its heading")
            continue
        topics.append(Topic(id=m.group(1), title=m.group(2).strip(), scope=scope, where=where))
    return topics, problems
