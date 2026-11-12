"""The stock lookup: the game's own text for an English term or a token, in every language.

    python -m modkit.core.glossary term "<English>" [--lang SC,FR] [--limit N]
    python -m modkit.core.glossary token TOKEN [TOKEN ...] [--dic STEM] [--lang SC,FR]

``stock_rows`` reads the stock dictionaries (``stock_dictionaries``) in the shape of an Operation's string table
(modkit.ops.strings): ``{stem: {token: {lang: text}}}``, the stem being a dictionary's name (``INTERFACE_INGAME``,
``MAPS``); of a token in several copies of a dictionary, the first copy's text in path order. Both commands print a
Markdown table, each row naming its dictionary, one column per language (US first; ``--lang`` picks the others):
``term`` the rows whose US text is the term, then the ``--limit`` shortest that hold it on word boundaries (exit 0);
``token`` each token's row in the dictionary ``--dic`` (default ``INTERFACE_INGAME``, where dialog button labels are),
exit 1 when one is not there. With no extraction, or no dictionary in it, one ``FAILED:`` line naming the warno-setup
skill and exit 2.
"""
from __future__ import annotations

import argparse
import glob
import os
import re
import sys
from typing import Sequence

from modkit.core import paths, trad
from modkit.core.ndfbin import token_unhash
from modkit.core.stock import SETUP_FIX

LANGS = ("DEV", "FR", "GER", "POL", "RU", "SC", "SPA", "US")  # the game's dictionary languages
INGAME = "INTERFACE_INGAME"  # token's default stem: the dictionary the game looks dialog button labels up in

Rows = dict[str, dict[str, dict[str, str]]]  # stem -> token -> lang -> text


class SetupError(RuntimeError):
    """The extraction holds no stock dictionary; the setup's extract fetches them."""


def stock_dictionaries(lang: str) -> list[str]:
    """Every stock dictionary of the language ``lang`` (a file named ``*-<lang>.dic``) anywhere in the extraction,
    sorted: the one glob for them (ops' glyph gate reads each language's set through it). Raises paths.NotConfigured
    without an extraction."""
    return sorted(glob.glob(os.path.join(str(paths.extracted_root()), "**", f"*-{lang}.dic"), recursive=True))


def stock_rows(stem: str | None = None) -> Rows:
    """Every stock dictionary's texts (only those named ``stem`` when given), by stem, token and language. Raises
    SetupError when the extraction holds no dictionary, ValueError when none has the stem ``stem``."""
    rows: Rows = {}
    found = False  # any stock dictionary at all
    for lang in LANGS:
        for path in stock_dictionaries(lang):
            found = True
            name = os.path.basename(path).rsplit("-", 1)[0]
            if stem not in (None, name):
                continue
            with open(path, "rb") as fh:
                for key, text in trad.read_dic(fh.read()):
                    if key != trad.CHARSET_KEY:
                        token = token_unhash(key) or f"0x{key:016x}"
                        rows.setdefault(name, {}).setdefault(token, {}).setdefault(lang, text)
    if not found:
        raise SetupError(f"no stock dictionary in the extraction {paths.extracted_root()}; {SETUP_FIX}")
    if not rows:
        raise ValueError(f"no stock {stem}-<lang>.dic in the extraction")
    return rows


def term_rows(rows: Rows, term: str, limit: int = 10) -> list[tuple[str, str, dict[str, str]]]:
    """(stem, token, texts) of the rows whose US text is ``term``, then the ``limit`` shortest that hold it on word
    boundaries (a space in the term matching any white space)."""
    words = term.split()
    if not words:
        raise ValueError(f"{term!r} is an empty term")
    pattern = re.compile(r"(?<!\w)" + r"\s+".join(map(re.escape, words)) + r"(?!\w)", re.IGNORECASE)
    flat = [(stem, token, texts) for stem, tokens in rows.items() for token, texts in tokens.items() if "US" in texts]
    exact = [row for row in flat if pattern.fullmatch(row[2]["US"].strip())]
    holding = sorted((row for row in flat if row not in exact and pattern.search(row[2]["US"])),
                     key=lambda row: (len(row[2]["US"]), row[0], row[1]))
    return exact + holding[:limit]


def table(found: list[tuple[str, str, dict[str, str]]], langs: Sequence[str]) -> list[str]:
    """``found`` as a Markdown table: dictionary, token, then one column per language of ``langs``."""
    def cell(text: str) -> str:
        return text.replace("\\", "\\\\").replace("|", "\\|").replace("\n", "\\n").replace("\r", "\\r")
    head = ["dictionary", "token", *langs]
    return ["| " + " | ".join(head) + " |", "|" + " --- |" * len(head)] + [
        "| " + " | ".join([stem, token, *(cell(texts.get(lang, "")) for lang in langs)]) + " |"
        for stem, token, texts in found]


def _langs(text: str) -> tuple[str, ...]:
    asked = [lang.strip().upper() for lang in text.split(",")]
    if not set(asked) <= set(LANGS):
        raise argparse.ArgumentTypeError(f"{text}: the game's languages are {', '.join(LANGS)}")
    return ("US", *(lang for lang in asked if lang != "US"))


def main(argv: Sequence[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):  # the texts are in every script; the console may be cp1252
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    ap = argparse.ArgumentParser(prog="python -m modkit.core.glossary", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("term", help="the stock rows whose US text is or holds an English term")
    p.add_argument("term", metavar="TERM")
    p.add_argument("--limit", type=int, default=10, metavar="N", help="rows holding the term to show (default 10)")
    p = sub.add_parser("token", help="each token's row in one stock dictionary")
    p.add_argument("tokens", nargs="+", metavar="TOKEN")
    p.add_argument("--dic", default=INGAME, metavar="STEM", help=f"the dictionary's name (default {INGAME})")
    for p in sub.choices.values():
        p.add_argument("--lang", type=_langs, default=("US", *(lang for lang in LANGS if lang != "US")),
                       metavar="SC,FR", help="the languages to show beside US (default all)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "term":
            found, status = term_rows(stock_rows(), args.term, max(args.limit, 0)), 0
        else:
            rows, status, found = stock_rows(args.dic)[args.dic], 0, []
            for token in args.tokens:
                trad.token_key(token)  # a TradError (one FAILED line) for what cannot be a token
                if token in rows:
                    found.append((args.dic, token, rows[token]))
                else:
                    print(f"{token}: not in {args.dic}", file=sys.stderr)
                    status = 1
        if found:
            print("\n".join(table(found, args.lang)))
        return status
    except (paths.NotConfigured, SetupError) as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 2
    except (ValueError, OSError) as exc:  # trad.TradError is a ValueError
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
