"""A scenario's bilingual string table and the gates that stop a broken Chinese string shipping.

A ``Table`` maps dictionary name -> token -> ``(English, Chinese)``; an Operation ships three dictionaries,
SCENARIO_DEFINITION, Scripting/Dialog and Scripting/Localization. ``payloads`` turns a table into its ``.dic`` files,
one per dictionary and language: SC gets the Chinese column, the other seven languages get the English one.

The gates catch what no English launch can: a Chinese string that drops a ``%1`` placeholder, a ``#bold{`` markup opener, a
closing brace or a line break shows raw markup to Chinese players only, and a character outside the game's Chinese font
renders as an empty box. Every gate raises ``StringError`` naming the dictionary, the token and the problem.

``modkit.ops.gates.check_strings`` (a build's gate 1) runs them; ``modkit.ops.build`` packs ``payloads``.
"""
from __future__ import annotations

import collections
import re
from typing import Iterable

from modkit.core import trad
from modkit.core.gates import CheckError

Table = dict[str, dict[str, tuple[str, str]]]  # dictionary name -> token -> (English, Chinese)

LANGS = ("DEV", "FR", "GER", "POL", "RU", "SC", "SPA", "US")
TITLE_DICT = "SCENARIO_DEFINITION"

# What must agree between the English and the Chinese text of one token, as (what it is, how to find it).
_MATCHED = (
    ("placeholder", re.compile(r"%\d+")),
    ("markup opener", re.compile(r"#\w+\{")),
    ("closing brace", re.compile(r"\}")),
    ("line break", re.compile(r"\n")),
)


class StringError(CheckError, ValueError):
    """A string-table gate failed; the message names the dictionary, the token and the problem. It is a CheckError,
    so a profile can hold a reviewed-pending entry for it, and a ValueError, as it always was."""


def _fail(dic: str, token: str, problem: str) -> StringError:
    return StringError(f"{dic} {token!r}: {problem}")


def check_parity(table: Table) -> None:
    """Every token is a valid key; Chinese is non-empty wherever English is; the English and Chinese texts carry the same
    ``%N`` placeholders, ``#name{`` markup openers, ``}`` and line breaks (as multisets, so Chinese may reorder them)."""
    for dic, tokens in table.items():
        for token, (en, zh) in tokens.items():
            try:
                trad.token_key(token)
            except trad.TradError as exc:
                raise _fail(dic, token, str(exc)) from None
            if en and not zh:
                raise _fail(dic, token, "Chinese text is empty")
            for what, pattern in _MATCHED:
                want, got = collections.Counter(pattern.findall(en)), collections.Counter(pattern.findall(zh))
                if want != got:
                    missing, extra = list((want - got).elements()), list((got - want).elements())
                    raise _fail(dic, token, f"{what} differs: missing from Chinese {missing}, extra in Chinese {extra}")


def check_glyphs(table: Table, allowed: set[str]) -> None:
    """Every character of every Chinese text is in ``allowed``, printable ASCII (U+0020-U+007E) or a line break."""
    for dic, tokens in table.items():
        for token, (_, zh) in tokens.items():
            bad = [ch for ch in dict.fromkeys(zh) if ch not in allowed and ch != "\n" and not " " <= ch <= "~"]
            if bad:
                raise _fail(dic, token, "Chinese text has characters outside the stock set: "
                            + ", ".join(f"{ch} (U+{ord(ch):04X})" for ch in bad))


def _units(text: str) -> int:
    """Length in UTF-16 code units, which is how a ``.dic`` row and the game measure a text."""
    return len(text.encode("utf-16-le", "surrogatepass")) // 2


def check_titles(table: Table, tokens: Iterable[str], limit: int = 30) -> None:
    """Both texts of each named SCENARIO_DEFINITION token are at most ``limit`` UTF-16 units.

    A toolkit convention, not a game limit: no stock text shows one. Stock's menu titles (MissionName, TitreObjectifs)
    run 9..20 English units, but its briefing (TextePresentationScenario) runs 1037..1416 and its other menu texts
    35..991 (test_gates_stock.MenuTexts). Name only the tokens to hold to it (``Content.menu_tokens``): Open Door and
    the probes name all seven of theirs, so their briefings stay short too; Twin Strike names its two titles, and its
    other menu texts take stock's lengths."""
    titles = table.get(TITLE_DICT, {})
    for token in tokens:
        if token not in titles:
            raise _fail(TITLE_DICT, token, "title token is not in the table")
        for lang, text in zip(("English", "Chinese"), titles[token]):
            if _units(text) > limit:
                raise _fail(TITLE_DICT, token, f"{lang} title is {_units(text)} UTF-16 units, over the limit of {limit}")


def stock_sc_chars(paths: Iterable[str]) -> set[str]:
    """Every character of every text in the given ``.dic`` files, charset rows included."""
    chars: set[str] = set()
    for path in paths:
        with open(path, "rb") as fh:
            for _, text in trad.read_dic(fh.read()):
                chars.update(text)
    return chars


def payloads(table: Table) -> dict[tuple[str, str], bytes]:
    """``(dictionary name, language) -> .dic bytes``: SC from the Chinese column, the other seven from the English.

    Runs ``check_parity`` first."""
    check_parity(table)
    out = {}
    for dic, tokens in table.items():
        english = trad.build_dic({token: en for token, (en, _) in tokens.items()})
        chinese = trad.build_dic({token: zh for token, (_, zh) in tokens.items()})
        for lang in LANGS:
            out[(dic, lang)] = chinese if lang == "SC" else english
    return out
