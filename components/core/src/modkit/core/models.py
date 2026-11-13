"""The shapes more than one module or component shares, in one place.

``Texts`` is one text in each of the game's dictionary languages (``LANGS``): an Operation's string table
(``StringTable``, ``modkit.ops.strings``) holds one per token. ``AnyTexts`` is the same with no language required: a
stock dictionary row (``modkit.core.glossary``), since some stock tokens have no US text. ``Pending`` is a build's
reviewed-pending map and ``Fired`` the reviews that fired (``modkit.core.gates.run_gate``). ``Dropped`` is a source
file a build does not ship and why, and ``ManifestRow`` a row of a mod's own in its MANIFEST.tsv
(``modkit.core.packaging.write_manifest``).

The byte codecs (``trad``, ``edat``, ``ndfbin`` and the rest) do not use these: they stay standard library only.
"""
from __future__ import annotations

from typing import Mapping

from pydantic import BaseModel, ConfigDict, TypeAdapter
from pydantic.dataclasses import dataclass


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


LANGS: tuple[str, ...] = tuple(AnyTexts.model_fields)  # the game's dictionary languages: DEV, FR, ..., SPA, US

# dictionary name -> token -> its texts. The order is kept: a .dic's text pool is written in it (trad.build_dic).
StringTable = dict[str, dict[str, Texts]]

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
