"""An Operation's string table, each text in each language, and the gates that stop a broken one shipping.

A ``StringTable`` (modkit.core.models) maps dictionary name -> token -> ``Texts(US=..., SC=...)``, one text per game
language; an Operation ships three dictionaries, SCENARIO_DEFINITION, Scripting/Dialog and Scripting/Localization.
``US`` is required; any other language is optional and gets the US text when packed. An op keeps its table in a TOML
file, one section per token and one key per language, and ``load`` reads it::

    [SCENARIO_DEFINITION.ts_name]
    US = "Operation Twin Strike"
    SC = "双重突击行动"

The op's term table (warno-localization) has the same shape, read by ``load(path, Term)``: a section per English
term, one key per language, and ``source.<language>`` beside each text that is not US.

``payloads`` turns a table into its ``.dic`` files, one per dictionary and language.

The gates catch what no English launch can: a translation that drops a ``%1`` placeholder, a ``#bold{`` markup opener,
a closing brace or a line break shows raw markup in that language only, and a character no stock text of its language
uses may be missing from that language's font (an empty box). Every gate raises one ``StringError`` naming each
violation on its own line: the dictionary, the token, the language and the problem. ``modkit.ops.gates.check_strings``
(a build's gate 1) runs them all and raises once; ``modkit.ops.build`` packs ``payloads``.
"""
from __future__ import annotations

import collections
import os
import re
import tomllib
from typing import Iterable, Mapping

from pydantic import ValidationError

from modkit.core import trad
from modkit.core.gates import CheckError
from modkit.core.models import LANGS, StringTable, Texts

TITLE_DICT = "SCENARIO_DEFINITION"

# What must agree between a token's US text and its text in each other language, as (what it is, how to find it).
_MATCHED = (
    ("placeholder", re.compile(r"%\d+")),
    ("markup opener", re.compile(r"#\w+\{")),
    ("closing brace", re.compile(r"\}")),
    ("line break", re.compile(r"\n")),
)


class StringError(CheckError, ValueError):
    """A string table failed to load or a string-table gate failed; the message names the dictionary, the token and
    the problem, one line per violation. It is a CheckError, so a profile can hold a reviewed-pending entry for it, and a ValueError, as it always
    was."""


def _raise(problems: list[str]) -> None:
    if problems:
        raise StringError("\n".join(problems))


def load[T: Texts](path: str | os.PathLike[str], model: type[T] = Texts) -> dict[str, dict[str, T]]:
    """The table in the TOML file at ``path``: a ``[<dictionary>.<token>]`` section per token, one key per language,
    each validated into ``model``: ``Texts`` (US required, the game's languages only) for a string table
    (``StringTable``), ``Term`` for a term table (``TermTable``, its groups in place of dictionaries). The file's order
    is kept: it is the order ``payloads`` writes each ``.dic``'s texts in. A dictionary with no token is an empty
    ``[<dictionary>]`` table. Raises one ``StringError`` naming the file and each bad entry, one per line."""
    with open(path, "rb") as fh:
        try:
            data = tomllib.load(fh)
        except tomllib.TOMLDecodeError as exc:
            raise StringError(f"{path}: not TOML: {exc}") from None
    table: dict[str, dict[str, T]] = {}
    problems = []
    for dic, tokens in data.items():
        if not isinstance(tokens, dict):
            problems.append(f"{path}: {dic}: not a dictionary of tokens (write each token as a [{dic}.<token>] "
                            "section)")
            continue
        table[dic] = {}
        for token, texts in tokens.items():
            try:
                table[dic][token] = model.model_validate(texts)
            except ValidationError as exc:
                problems += [f"{path}: {dic}.{token}: {'.'.join(map(str, e['loc'])) or 'the entry'}: {e['msg']}"
                             for e in exc.errors()]
    _raise(problems)
    return table


def check_parity(table: StringTable) -> None:
    """Every token is a valid key; each other language's text is non-empty wherever US is, and carries the US text's
    ``%N`` placeholders, ``#name{`` markup openers, ``}`` and line breaks (as multisets, so a translation may reorder
    them). ``Texts`` itself holds a US text and the game's languages only."""
    problems = []
    for dic, tokens in table.items():
        for token, texts in tokens.items():
            where = f"{dic} {token!r}"
            try:
                trad.token_key(token)
            except trad.TradError as exc:
                problems.append(f"{where}: {exc}")
            for lang, text in texts.items():
                if texts.US and not text:
                    problems.append(f"{where}: the {lang} text is empty")
                for what, pattern in _MATCHED:
                    want, got = (collections.Counter(pattern.findall(t)) for t in (texts.US, text))
                    if want != got:
                        problems.append(f"{where}: {lang} {what} differs from US: missing "
                                        f"{list((want - got).elements())}, extra {list((got - want).elements())}")
    _raise(problems)


def check_glyphs(table: StringTable, chars: Mapping[str, set[str]]) -> None:
    """Every character of each text in a language of ``chars`` is in that language's set, printable ASCII
    (U+0020-U+007E) or a line break."""
    problems = []
    for dic, tokens in table.items():
        for token, texts in tokens.items():
            for lang, text in texts.items():
                bad = [ch for ch in dict.fromkeys(text) if lang in chars and ch not in chars[lang] and ch != "\n"
                       and not " " <= ch <= "~"]
                if bad:
                    problems.append(f"{dic} {token!r}: the {lang} text has characters outside the stock {lang} set: "
                                    + ", ".join(f"{ch} (U+{ord(ch):04X})" for ch in bad))
    _raise(problems)


def _units(text: str) -> int:
    """Length in UTF-16 code units, which is how a ``.dic`` row and the game measure a text."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def check_titles(table: StringTable, tokens: Iterable[str], limit: int = 30) -> None:
    """Each named SCENARIO_DEFINITION token's text in every language is at most ``limit`` UTF-16 units.

    A toolkit convention, not a game limit: no stock text shows one. Stock's menu titles (MissionName, TitreObjectifs)
    run 9..20 English units, but its briefing (TextePresentationScenario) runs 1037..1416 and its other menu texts
    35..991 (test_gates_stock.MenuTexts). Name only the tokens to hold to it (``Content.menu_tokens``): Open Door and
    the probes name all seven of theirs, so their briefings stay short too; Twin Strike names its two titles, and its
    other menu texts take stock's lengths."""
    titles, problems = table.get(TITLE_DICT, {}), []
    for token in tokens:
        if token not in titles:
            problems.append(f"{TITLE_DICT} {token!r}: title token is not in the table")
            continue
        problems += [f"{TITLE_DICT} {token!r}: the {lang} title is {_units(text)} UTF-16 units, over the limit of "
                     f"{limit}" for lang, text in titles[token].items() if _units(text) > limit]
    _raise(problems)


def stock_chars(dics: Iterable[str]) -> set[str]:
    """Every character of every text in the given ``.dic`` files, charset rows included: given one language's stock
    dictionaries (``modkit.core.glossary.stock_dictionaries``), the characters its font has, gate 1's glyph set."""
    chars: set[str] = set()
    for path in dics:
        with open(path, "rb") as fh:
            for _, text in trad.read_dic(fh.read()):
                chars.update(text)
    return chars


def payloads(table: StringTable) -> dict[tuple[str, str], bytes]:
    """``(dictionary name, language) -> .dic bytes``, each language from its own texts, US where a token has none.

    Runs ``check_parity`` first."""
    check_parity(table)
    return {(dic, lang): trad.build_dic({token: texts.get(lang) for token, texts in tokens.items()})
            for dic, tokens in table.items() for lang in LANGS}
