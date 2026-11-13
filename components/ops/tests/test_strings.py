"""Tests for modkit.ops.strings, the per-language string table, its TOML file (Load) and its gates. Most tables hold US
and SC; Languages holds the others to US.

The gates are pure string checks. Load reads TOML files it writes to a temporary folder; test_stock_chars_real reads
the stock dictionaries in the extraction (skipped without one).
"""
from __future__ import annotations

import os
import tempfile
import textwrap
import unittest

from modkit.core import paths, trad
from modkit.core.glossary import stock_dictionaries
from modkit.core.models import LANGS, Texts
from modkit.ops.strings import StringError, check_glyphs, check_parity, check_titles, load, payloads, stock_chars

DICTS = ("SCENARIO_DEFINITION", "Scripting/Dialog", "Scripting/Localization")


def one(text: Texts, token: str = "od_t", dic: str = "Scripting/Localization"):
    """A one-token table."""
    return {dic: {token: text}}


class Load(unittest.TestCase):
    """An op's table file: a [<dictionary>.<token>] section per token, one key per language."""

    def load(self, toml: str):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "strings.toml")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write(textwrap.dedent(toml))
            return load(path)

    def test_order_is_the_file_order(self):
        """Dictionaries and tokens come back in the file's order (the order a .dic's texts are written in), however
        the sections are spread; an empty [<dictionary>] table is an empty dictionary."""
        table = self.load('''
            ["Scripting/Localization".od_z]
            US = "Z"
            [SCENARIO_DEFINITION.od_name]
            SC = "门"
            US = "Door"
            ["Scripting/Dialog"]
            ["Scripting/Localization".od_a]
            US = """
            Line one
            Line two"""
        ''')
        self.assertEqual(list(table), ["Scripting/Localization", "SCENARIO_DEFINITION", "Scripting/Dialog"])
        self.assertEqual(list(table["Scripting/Localization"]), ["od_z", "od_a"])
        self.assertEqual(table["Scripting/Dialog"], {})
        self.assertEqual(table["SCENARIO_DEFINITION"]["od_name"], Texts(US="Door", SC="门"))
        self.assertEqual(table["Scripting/Localization"]["od_a"].US, "Line one\nLine two")

    def test_entry_errors_name_the_file_and_the_token(self):
        """An unknown language key and a missing US text each fail, every bad entry on its own line of one error."""
        with self.assertRaises(StringError) as cm:
            self.load("""
                [SCENARIO_DEFINITION.od_name]
                US = "Door"
                EN = "Door"
                ["Scripting/Dialog".od_dlg]
                SC = "门"
            """)
        lines = str(cm.exception).splitlines()
        self.assertEqual(len(lines), 2, lines)
        self.assertRegex(lines[0], r"strings\.toml: SCENARIO_DEFINITION\.od_name: EN: Extra inputs are not permitted")
        self.assertRegex(lines[1], r"strings\.toml: Scripting/Dialog\.od_dlg: US: Field required")

    def test_bad_shape(self):
        """Not TOML, a language key straight under a dictionary (no token section), a key at the top level."""
        for toml, want in (('[SCENARIO_DEFINITION.od_name\nUS = "Door"', r"strings\.toml: not TOML"),
                           ('[SCENARIO_DEFINITION]\nUS = "Door"', r"strings\.toml: SCENARIO_DEFINITION\.US: the entry: "),
                           ('US = "Door"', r"strings\.toml: US: not a dictionary of tokens")):
            with self.subTest(toml=toml), self.assertRaisesRegex(StringError, want):
                self.load(toml)


class Payloads(unittest.TestCase):
    def test_payloads_languages(self):
        table = {
            "SCENARIO_DEFINITION": {"od_name": Texts(US="Open Door", SC="敞开的门")},
            "Scripting/Dialog": {"od_dlg": Texts(US="Hold %1", SC="坚守 %1")},
            "Scripting/Localization": {"od_hint": Texts(US="#bold{Go}", SC="#bold{出发}")},
        }
        out = payloads(table)
        self.assertEqual(len(out), 24)
        self.assertEqual(set(out), {(dic, lang) for dic in DICTS for lang in LANGS})

        def body(dic, lang):
            return {k: t for k, t in trad.read_dic(out[(dic, lang)]) if k != trad.CHARSET_KEY}

        key = trad.token_key("od_dlg")
        self.assertEqual(body("Scripting/Dialog", "SC"), {key: "坚守 %1"})
        self.assertEqual(body("Scripting/Dialog", "US"), {key: "Hold %1"})
        self.assertEqual(out[("Scripting/Dialog", "FR")], out[("Scripting/Dialog", "US")])
        for lang in LANGS:
            if lang != "SC":
                self.assertEqual(out[("Scripting/Dialog", lang)], out[("Scripting/Dialog", "US")], lang)
        # the charset row is the dictionary's own, built from the texts it carries
        sc_charset = dict(trad.read_dic(out[("Scripting/Dialog", "SC")]))[trad.CHARSET_KEY]
        self.assertIn("坚", sc_charset)

    def test_payloads_run_the_parity_gate(self):
        with self.assertRaises(StringError):
            payloads(one(Texts(US="Hold %1 / %2", SC="坚守 %1")))


class Languages(unittest.TestCase):
    """Any language beside US is optional, each packed from its own texts or US's."""

    def test_each_language_from_its_own_texts_else_us(self):
        out = payloads(one(Texts(US="Hold", FR="Tenir")))
        texts = [dict(trad.read_dic(out[("Scripting/Localization", lang)]))[trad.token_key("od_t")]
                 for lang in ("FR", "US", "SC", "GER")]
        self.assertEqual(texts, ["Tenir", "Hold", "Hold", "Hold"])

    def test_parity_holds_each_language_to_us(self):
        with self.assertRaisesRegex(StringError, r"'od_t': FR placeholder differs from US: missing \['%1'\]"):
            check_parity(one(Texts(US="Hold %1", SC="坚守 %1", FR="Tenir")))

    def test_every_violation_in_one_error(self):
        table = {"Scripting/Dialog": {"od_a": Texts(US="Go %1", SC="走", FR="Va"), "od_b": Texts(US="Hold", SC="")}}
        with self.assertRaises(StringError) as cm:
            check_parity(table)
        self.assertEqual(len(str(cm.exception).splitlines()), 3, cm.exception)  # od_a in SC and FR, od_b's empty SC

    def test_titles_in_every_language(self):
        with self.assertRaisesRegex(StringError, "the FR title is 31 UTF-16 units"):
            check_titles(one(Texts(US="a", FR="b" * 31), "od_name", "SCENARIO_DEFINITION"), ["od_name"])


class Parity(unittest.TestCase):
    def test_parity_placeholder_missing(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(Texts(US="Hold %1 / %2", SC="坚守 %1"), token="od_dlg", dic="Scripting/Dialog"))
        msg = str(cm.exception)
        self.assertIn("od_dlg", msg)
        self.assertIn("%2", msg)
        self.assertIn("Scripting/Dialog", msg)

    def test_parity_placeholder_extra(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(Texts(US="Hold %1", SC="坚守 %1 / %3")))
        self.assertIn("%3", str(cm.exception))

    def test_parity_placeholders_are_a_multiset_not_a_sequence(self):
        check_parity(one(Texts(US="Hold %1 / %2", SC="%2 号坚守 %1")))  # Chinese may reorder them
        with self.assertRaises(StringError):
            check_parity(one(Texts(US="%1 and %1", SC="%1 和 %2")))
        with self.assertRaises(StringError):
            check_parity(one(Texts(US="%1 and %1", SC="%1 和")))  # a repeat counts

    def test_parity_markup_missing(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(Texts(US="#bold{Corps:} spring it?", SC="军部：收网？")))
        self.assertIn("#bold{", str(cm.exception))

    def test_parity_markup_opener_differs(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(Texts(US="#bold{Corps:} go", SC="#shint{军部：} 出发")))
        self.assertIn("#shint{", str(cm.exception))

    def test_parity_closing_brace_missing(self):
        check_parity(one(Texts(US="#bold{Corps:} go", SC="#bold{军部：} 出发")))
        with self.assertRaises(StringError) as cm:
            check_parity(one(Texts(US="#bold{Corps:} go", SC="#bold{军部： 出发")))
        self.assertIn("}", str(cm.exception))

    def test_parity_newline(self):
        with self.assertRaises(StringError):
            check_parity(one(Texts(US="a\nb", SC="ab")))
        with self.assertRaises(StringError):
            check_parity(one(Texts(US="ab", SC="a\nb")))
        check_parity(one(Texts(US="a\nb", SC="甲\n乙")))
        check_parity(one(Texts(US="", SC="")))
        with self.assertRaises(StringError):
            check_parity(one(Texts(US="Hold", SC="")))

    def test_bad_token(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(Texts(US="Hold", SC="坚守"), token="od_too_long_x"))
        self.assertIn("od_too_long_x", str(cm.exception))


class Glyphs(unittest.TestCase):
    ALLOWED = {"SC": set("坚守")}

    def test_glyph_outside_stock_set(self):
        with self.assertRaises(StringError) as cm:
            check_glyphs(one(Texts(US="Hold %1 / %2", SC="坚守阵 %1"), token="od_dlg", dic="Scripting/Dialog"),
                         self.ALLOWED)
        msg = str(cm.exception)
        self.assertIn("阵", msg)
        self.assertIn("od_dlg", msg)
        self.assertIn("Scripting/Dialog", msg)
        check_glyphs(one(Texts(US="Hold %1 / %2", SC="坚守 %1 / %2")), self.ALLOWED)

    def test_glyph_ascii_and_newline_are_always_allowed(self):
        check_glyphs(one(Texts(US="x", SC="坚守\n#bold{A-z 0~9 %1}")), self.ALLOWED)

    def test_glyph_other_control_and_non_ascii_punctuation_are_not(self):
        for bad in ("坚守\t", "坚守\x7f", "坚守é", "坚守　"):
            with self.subTest(bad=bad), self.assertRaises(StringError):
                check_glyphs(one(Texts(US="x", SC=bad)), self.ALLOWED)

    def test_glyph_checks_only_the_languages_given(self):
        check_glyphs(one(Texts(US="Café", SC="坚守")), self.ALLOWED)
        with self.assertRaisesRegex(StringError, "the US text has characters outside the stock US set: é"):
            check_glyphs(one(Texts(US="Café", SC="坚守")), {**self.ALLOWED, "US": set()})


class Titles(unittest.TestCase):
    def test_titles(self):
        ok = one(Texts(US="a" * 30, SC="守" * 30), token="od_name", dic="SCENARIO_DEFINITION")
        check_titles(ok, ["od_name"])
        with self.assertRaises(StringError) as cm:
            check_titles(one(Texts(US="a" * 31, SC="守"), token="od_name", dic="SCENARIO_DEFINITION"), ["od_name"])
        self.assertIn("od_name", str(cm.exception))
        with self.assertRaises(StringError):  # the Chinese column is measured too
            check_titles(one(Texts(US="a", SC="守" * 31), token="od_name", dic="SCENARIO_DEFINITION"), ["od_name"])

    def test_titles_count_utf16_units(self):
        sd = "SCENARIO_DEFINITION"
        check_titles(one(Texts(US="a", SC="守" * 30), "od_name", sd), ["od_name"])  # 30 CJK = 30 units, not 90 bytes
        check_titles(one(Texts(US="\U0001F600" * 15, SC="守"), "od_name", sd), ["od_name"])  # astral = 2 units: 30
        with self.assertRaises(StringError):
            check_titles(one(Texts(US="\U0001F600" * 16, SC="守"), "od_name", sd), ["od_name"])  # 32 units

    def test_titles_limit_and_named_tokens_only(self):
        sd = "SCENARIO_DEFINITION"
        table = {sd: {"od_name": Texts(US="a" * 12, SC="守" * 12), "od_long": Texts(US="b" * 40, SC="守")},
                 "Scripting/Localization": {"od_hint": Texts(US="c" * 99, SC="守")}}
        check_titles(table, ["od_name"])                  # od_long and the hint are not titles
        check_titles(table, iter(["od_name"]), limit=12)  # any iterable; 12 is within a limit of 12
        with self.assertRaises(StringError):
            check_titles(table, ["od_name"], limit=11)
        with self.assertRaises(StringError):
            check_titles(table, ["od_name", "od_long"])

    def test_titles_unknown_token(self):
        with self.assertRaises(StringError) as cm:
            check_titles(one(Texts(US="a", SC="守"), "od_name", "SCENARIO_DEFINITION"), ["od_nope"])
        self.assertIn("od_nope", str(cm.exception))


class StockChars(unittest.TestCase):
    def test_stock_sc_chars_includes_charset_row(self):
        """The charset row's characters count, even ones no other text uses."""
        entries = [(trad.token_key("a"), "x守"), (trad.CHARSET_KEY, "x守阵")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t-SC.dic")
            with open(path, "wb") as fh:
                fh.write(trad.write_dic(entries))
            self.assertEqual(stock_chars([path]), set("x守阵"))
            other = os.path.join(tmp, "u-SC.dic")
            with open(other, "wb") as fh:
                fh.write(trad.build_dic({"b": "领"}))
            self.assertEqual(stock_chars(iter([path, other])), set("x守阵领"))

    @paths.skip_unless_extracted("localisation")
    def test_stock_chars_real(self):
        """Each language's set is its stock dictionaries', the game's own (core's localisation) with the scenarios'
        [[chinese-text-stock-glyphs]]: 核 (nuclear), which only the game's own SC dictionaries use, is in the SC set;
        龘, which no stock text uses, is not."""
        chars = {lang: stock_chars(stock_dictionaries(lang)) for lang in LANGS}
        for ch in "占领区核":
            self.assertIn(ch, chars["SC"])
        self.assertNotIn("龘", chars["SC"])
        self.assertGreater(len(chars["SC"]), 2000)
        for lang in LANGS:
            self.assertGreater(len(chars[lang]), 50, lang)


if __name__ == "__main__":
    unittest.main()
