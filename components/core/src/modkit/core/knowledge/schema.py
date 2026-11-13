"""The record schema: the three record types, their fields, the validation of a parsed front matter, and topics.

``Mechanism``, ``Trial`` and ``Lesson`` are pydantic models of a record: its front matter's fields, its body and its
file. ``read`` validates the front matter ``frontmatter.parse`` returns into a record, or raises ``SchemaError``
listing every problem in the words ``knowledge check`` prints. ``parse_topics`` reads a component's ``topics.md``: the
topics its mechanisms are filed under. Topic IDs are a namespace of their own; a ``[[id]]`` never cites a topic.
"""
from __future__ import annotations

import datetime
import re
from dataclasses import dataclass
from typing import Annotated, ClassVar, Literal, Self, get_args

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, ValidationError, ValidationInfo, field_validator
from pydantic_core import ErrorDetails, PydanticCustomError

Status = Literal["PLAYED", "PROBED", "RE", "STOCK", "FAILED", "UNTESTED"]
Source = Literal["play", "stock-data", "exe-analysis"]
Kind = Literal["launch", "play", "probe-run", "re", "survey"]
Outcome = Literal["pass", "fail", "mixed"]
STATUSES: tuple[str, ...] = get_args(Status)

ID_RE = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
TRIAL_ID_RE = re.compile(r"(\d{4}-\d{2}-\d{2})-([a-z0-9]+(?:-[a-z0-9]+)*)")
LAST_VERIFIED_RE = re.compile(r"(\d+) (\d{4}-\d{2}-\d{2})")
DOTTED_RE = re.compile(r"modkit(?:\.[A-Za-z_]\w*){3,}")
# Anything that looks like [[...]] is a citation; the text inside, trimmed, must be a record ID or the check
# reports it as malformed-citation (so [[ id ]], [[a|b]] and [[id#x]] never slip through unread).
CITATION_RE = re.compile(r"\[\[([^\[\]]*)\]\]")

MAX_TOPICS = 3
# The body and the file come in under keys no front matter key can be (frontmatter.KEY), so a front matter key
# `body` or `where` is an unknown field, not the record's body.
BODY, WHERE = "(body)", "(where)"


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


def _valid_date(text: str) -> bool:
    try:
        datetime.date.fromisoformat(text)
    except ValueError:
        return False
    return True


def _invalid(message: str) -> PydanticCustomError:
    """A broken rule, in the words ``knowledge check`` prints."""
    return PydanticCustomError("record", message)


def _kebab_id(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise _invalid(f"id {value!r} must be kebab-case (lower case letters, digits and single dashes)")
    return value


def _trial_id(value: str) -> str:
    m = TRIAL_ID_RE.fullmatch(value)
    if not m or not _valid_date(m.group(1)):
        raise _invalid(f"id {value!r} must read YYYY-MM-DD-slug with a real date and a kebab-case slug")
    return value


def _topic(value: str) -> str:
    if not ID_RE.fullmatch(value):
        raise _invalid(f"topic {value!r} must be kebab-case")
    return value


Given = Annotated[str, Field(min_length=1)]  # a required value; empty counts as missing
RecordId = Annotated[str, Field(min_length=1), AfterValidator(_kebab_id)]


class _Record(BaseModel):
    """A record: its front matter's fields (each subclass's), then its body and its file."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    record_kind: ClassVar[str]

    body: str = Field(validation_alias=BODY)
    where: Where = Field(validation_alias=WHERE)

    @classmethod
    def read(cls, meta: dict, body: str, where: Where) -> Self:
        """The record of a parsed front matter (``frontmatter.parse``), or ``SchemaError`` listing every problem."""
        try:
            return cls.model_validate({**meta, BODY: body, WHERE: where})
        except ValidationError as exc:
            raise SchemaError([cls._problem(e) for e in exc.errors()]) from None

    @classmethod
    def _problem(cls, error: ErrorDetails) -> str:
        """One validation error in the words ``knowledge check`` prints."""
        name, kind, value = str(error["loc"][0]), error["type"], error["input"]
        if kind == "extra_forbidden":
            return f"unknown field {name!r}"
        if kind in ("missing", "string_too_short", "too_short") or (kind == "literal_error" and value == ""):
            hint = cls.model_fields[name].description
            return f"missing field {name}" + (f" ({hint})" if hint else "")
        if kind == "string_type":
            return f"{name} must be a single value, not a list"
        if kind == "tuple_type":
            return f"{name} must be a list like [a, b]"
        if kind == "literal_error":
            return f"{name} {value!r} must be one of {', '.join(get_args(cls.model_fields[name].annotation))}"
        return error["msg"]  # a rule's own words (_invalid)


class Mechanism(_Record):
    record_kind: ClassVar[str] = "mechanism"

    id: RecordId
    title: Given
    status: Status
    last_verified: str = Field("", validate_default=True)  # '<game build> <YYYY-MM-DD>'
    source: Source
    topics: tuple[Annotated[str, AfterValidator(_topic)], ...] = Field(
        min_length=1, description=f"1 to {MAX_TOPICS} topic IDs declared in a topics.md")
    gates: tuple[str, ...] = ()
    shapes: tuple[str, ...] = ()
    trials: tuple[str, ...] = ()
    stock_precedent: str = ""

    @field_validator("last_verified")
    @classmethod
    def _last_verified(cls, value: str, info: ValidationInfo) -> str:
        if not value:
            if info.data.get("status", "UNTESTED") != "UNTESTED":  # a status that failed is reported already
                raise _invalid("missing field last_verified (only UNTESTED may leave it out)")
            return value
        m = LAST_VERIFIED_RE.fullmatch(value)
        if not m or not _valid_date(m.group(2)):
            raise _invalid(f"last_verified {value!r} must read '<game build> <YYYY-MM-DD>'")
        return value

    @field_validator("topics")
    @classmethod
    def _topics(cls, topics: tuple[str, ...]) -> tuple[str, ...]:
        if len(topics) > MAX_TOPICS:
            raise _invalid(f"topics lists {len(topics)} topics; give 1 to {MAX_TOPICS}")
        if len(set(topics)) != len(topics):
            raise _invalid("topics lists a topic twice")
        return topics

    @property
    def verified_build(self) -> str | None:
        m = LAST_VERIFIED_RE.fullmatch(self.last_verified)
        return m.group(1) if m else None


class Trial(_Record):
    record_kind: ClassVar[str] = "trial"

    id: Annotated[str, Field(min_length=1), AfterValidator(_trial_id)]
    kind: Kind
    build: Given
    game_version: Given
    mechanisms: tuple[str, ...] = ()
    outcome: Outcome
    symptom: str = ""
    cause: str = ""
    result: str = ""

    @property
    def date(self) -> str:
        return self.id[:10]


class Lesson(_Record):
    record_kind: ClassVar[str] = "lesson"

    id: RecordId
    title: Given  # the rule
    trials: tuple[str, ...] = Field(min_length=1, description="the trials that taught the lesson")


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
