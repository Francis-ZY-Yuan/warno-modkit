"""The shapes more than one module or component shares, in one place.

``Texts`` is one text in each of the game's dictionary languages (``LANGS``): an Operation's string table
(``StringTable``, ``modkit.ops.strings``) holds one per token. ``AnyTexts`` is the same with no language required: a
stock dictionary row (``modkit.core.glossary``), since some stock tokens have no US text. ``Term`` is a ``Texts``
that also names, for each language other than US, where its text comes from: a mod's term table (``TermTable``) holds
one per English term, in the same file shape as the string table. ``Pending`` is a build's
reviewed-pending map and ``Fired`` the reviews that fired (``modkit.core.gates.run_gate``). ``Dropped`` is a source
file a build does not ship and why, and ``ManifestRow`` a row of a mod's own in its MANIFEST.tsv
(``modkit.core.packaging.write_manifest``).

``Point`` (x, y) and ``Box`` (x0, y0, x1, y1) are plane geometry, in whatever units their user works in (world units,
minimap or picture px). They are named tuples, not models: they sit in pixel and geometry loops, code unpacks them as
tuples, and they compare equal to the plain tuples they replace. Each prints as that plain tuple, so a message showing
one reads ``(x, y)``.

The byte codecs (``trad``, ``edat``, ``ndfbin`` and the rest) do not use these: they stay standard library only.
"""
from __future__ import annotations

from typing import Mapping, NamedTuple

from pydantic import BaseModel, ConfigDict, TypeAdapter, model_validator
from pydantic.dataclasses import dataclass


class Point(NamedTuple):
    """A point of the plane."""
    x: float
    y: float

    def __repr__(self) -> str:
        return tuple.__repr__(self)


class Box(NamedTuple):
    """An axis-aligned box of the plane: its least corner (`x0`, `y0`) and its greatest (`x1`, `y1`)."""
    x0: float
    y0: float
    x1: float
    y1: float

    def __repr__(self) -> str:
        return tuple.__repr__(self)


class AnyTexts(BaseModel):
    """A text in some of the game's dictionary languages, each optional; any other key is refused."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    DEV: str | None = None
    FR: str | None = None
    GER: str | None = None
    POL: str | None = None
    RU: str | None = None
    SC: str | None = None
    SPA: str | None = None
    US: str | None = None

    def items(self) -> list[tuple[str, str]]:
        """(language, text) for each language that has a text, in ``LANGS`` order."""
        return [(lang, text) for lang in LANGS if (text := getattr(self, lang)) is not None]

    def values(self) -> list[str]:
        """The text of each language that has one, in ``LANGS`` order."""
        return [text for _, text in self.items()]


class Texts(AnyTexts):
    """One text of a mod in each game language, written ``Texts(US="...", SC="...")``: US is required, any other
    language optional (it shows the US text: ``get``)."""

    US: str

    def get(self, lang: str) -> str:
        """The text in ``lang``; the US text when it has none."""
        text = getattr(self, lang)
        return self.US if text is None else text


class Term(Texts):
    """A term of a mod's term table: US is the English term, each other language its text there, and ``source`` names
    where each of those texts comes from (a stock token, doctrine, a review, the mod's own wording). Every language
    with a text other than US has a source, and only those."""

    source: AnyTexts = AnyTexts()

    @model_validator(mode="after")
    def _sourced(self) -> Term:
        texts = {lang for lang, _ in self.items()} - {"US"}
        sources = {lang for lang, text in self.source.items() if text}
        if texts != sources:
            raise ValueError(f"source names {sorted(sources) or 'no language'}, the texts are in "
                             f"{sorted(texts) or 'no language but US'}")
        return self


LANGS: tuple[str, ...] = tuple(AnyTexts.model_fields)  # the game's dictionary languages: DEV, FR, ..., SPA, US

# dictionary name -> token -> its texts. The order is kept: a .dic's text pool is written in it (trad.build_dic).
StringTable = dict[str, dict[str, Texts]]
# group -> English term -> its Term. The groups are headings only (modkit.ops.strings.load reads both tables).
TermTable = dict[str, dict[str, Term]]

Pending = Mapping[str, tuple[str, ...]]  # gate name -> its reviewed messages, word for word
Fired = list[tuple[str, str]]  # (gate name, message) of each reviewed failure that fired

# Checks a Pending map: each gate's messages a tuple of strings. A bare string is refused, since a message would match
# any part of it.
PENDING: TypeAdapter[Pending] = TypeAdapter(Pending)


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class Dropped:
    """A source a build does not ship (its `path`), and `why`: a drop row of MANIFEST.tsv."""
    path: str
    why: str


@dataclass(frozen=True, config=ConfigDict(extra="forbid"))
class ManifestRow:
    """A row of a mod's own in MANIFEST.tsv: its `name`, `action` and `source`."""
    name: str
    action: str
    source: str
