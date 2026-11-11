"""Tests for modkit.ops.strings, the bilingual string table and its gates.

The gates are pure string checks. Only test_stock_sc_chars_real reads files: the stock Simplified-Chinese dictionaries
in the extraction (skipped without one).
"""
from __future__ import annotations

import glob
import os
import tempfile
import unittest

from modkit.core import paths, trad
from modkit.ops.strings import LANGS, StringError, check_glyphs, check_parity, check_titles, payloads, stock_sc_chars

DICTS = ("SCENARIO_DEFINITION", "Scripting/Dialog", "Scripting/Localization")


def one(text: tuple[str, str], token: str = "od_t", dic: str = "Scripting/Localization"):
    """A one-token table."""
    return {dic: {token: text}}


class Payloads(unittest.TestCase):
    def test_payloads_languages(self):
        table = {
            "SCENARIO_DEFINITION": {"od_name": ("Open Door", "敞开的门")},
            "Scripting/Dialog": {"od_dlg": ("Hold %1", "坚守 %1")},
            "Scripting/Localization": {"od_hint": ("#bold{Go}", "#bold{出发}")},
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
            payloads(one(("Hold %1 / %2", "坚守 %1")))


class Parity(unittest.TestCase):
    def test_parity_placeholder_missing(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(("Hold %1 / %2", "坚守 %1"), token="od_dlg", dic="Scripting/Dialog"))
        msg = str(cm.exception)
        self.assertIn("od_dlg", msg)
        self.assertIn("%2", msg)
        self.assertIn("Scripting/Dialog", msg)

    def test_parity_placeholder_extra(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(("Hold %1", "坚守 %1 / %3")))
        self.assertIn("%3", str(cm.exception))

    def test_parity_placeholders_are_a_multiset_not_a_sequence(self):
        check_parity(one(("Hold %1 / %2", "%2 号坚守 %1")))  # Chinese may reorder them
        with self.assertRaises(StringError):
            check_parity(one(("%1 and %1", "%1 和 %2")))
        with self.assertRaises(StringError):
            check_parity(one(("%1 and %1", "%1 和")))  # a repeat counts

    def test_parity_markup_missing(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(("#bold{Corps:} spring it?", "军部：收网？")))
        self.assertIn("#bold{", str(cm.exception))

    def test_parity_markup_opener_differs(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(("#bold{Corps:} go", "#shint{军部：} 出发")))
        self.assertIn("#shint{", str(cm.exception))

    def test_parity_closing_brace_missing(self):
        check_parity(one(("#bold{Corps:} go", "#bold{军部：} 出发")))
        with self.assertRaises(StringError) as cm:
            check_parity(one(("#bold{Corps:} go", "#bold{军部： 出发")))
        self.assertIn("}", str(cm.exception))

    def test_parity_newline(self):
        with self.assertRaises(StringError):
            check_parity(one(("a\nb", "ab")))
        with self.assertRaises(StringError):
            check_parity(one(("ab", "a\nb")))
        check_parity(one(("a\nb", "甲\n乙")))
        check_parity(one(("", "")))
        with self.assertRaises(StringError):
            check_parity(one(("Hold", "")))

    def test_bad_token(self):
        with self.assertRaises(StringError) as cm:
            check_parity(one(("Hold", "坚守"), token="od_too_long_x"))
        self.assertIn("od_too_long_x", str(cm.exception))


class Glyphs(unittest.TestCase):
    ALLOWED = set("坚守")

    def test_glyph_outside_stock_set(self):
        with self.assertRaises(StringError) as cm:
            check_glyphs(one(("Hold %1 / %2", "坚守阵 %1"), token="od_dlg", dic="Scripting/Dialog"), self.ALLOWED)
        msg = str(cm.exception)
        self.assertIn("阵", msg)
        self.assertIn("od_dlg", msg)
        self.assertIn("Scripting/Dialog", msg)
        check_glyphs(one(("Hold %1 / %2", "坚守 %1 / %2")), self.ALLOWED)

    def test_glyph_ascii_and_newline_are_always_allowed(self):
        check_glyphs(one(("x", "坚守\n#bold{A-z 0~9 %1}")), self.ALLOWED)

    def test_glyph_other_control_and_non_ascii_punctuation_are_not(self):
        for bad in ("坚守\t", "坚守\x7f", "坚守é", "坚守　"):
            with self.subTest(bad=bad), self.assertRaises(StringError):
                check_glyphs(one(("x", bad)), self.ALLOWED)

    def test_glyph_checks_only_the_chinese_column(self):
        check_glyphs(one(("Café", "坚守")), self.ALLOWED)


class Titles(unittest.TestCase):
    def test_titles(self):
        ok = one(("a" * 30, "守" * 30), token="od_name", dic="SCENARIO_DEFINITION")
        check_titles(ok, ["od_name"])
        with self.assertRaises(StringError) as cm:
            check_titles(one(("a" * 31, "守"), token="od_name", dic="SCENARIO_DEFINITION"), ["od_name"])
        self.assertIn("od_name", str(cm.exception))
        with self.assertRaises(StringError):  # the Chinese column is measured too
            check_titles(one(("a", "守" * 31), token="od_name", dic="SCENARIO_DEFINITION"), ["od_name"])

    def test_titles_count_utf16_units(self):
        sd = "SCENARIO_DEFINITION"
        check_titles(one(("a", "守" * 30), "od_name", sd), ["od_name"])  # 30 CJK = 30 units, not 90 bytes
        check_titles(one(("\U0001F600" * 15, "守"), "od_name", sd), ["od_name"])  # astral = 2 units: 30
        with self.assertRaises(StringError):
            check_titles(one(("\U0001F600" * 16, "守"), "od_name", sd), ["od_name"])  # 32 units

    def test_titles_limit_and_named_tokens_only(self):
        sd = "SCENARIO_DEFINITION"
        table = {sd: {"od_name": ("a" * 12, "守" * 12), "od_long": ("b" * 40, "守")},
                 "Scripting/Localization": {"od_hint": ("c" * 99, "守")}}
        check_titles(table, ["od_name"])                  # od_long and the hint are not titles
        check_titles(table, iter(["od_name"]), limit=12)  # any iterable; 12 is within a limit of 12
        with self.assertRaises(StringError):
            check_titles(table, ["od_name"], limit=11)
        with self.assertRaises(StringError):
            check_titles(table, ["od_name", "od_long"])

    def test_titles_unknown_token(self):
        with self.assertRaises(StringError) as cm:
            check_titles(one(("a", "守"), "od_name", "SCENARIO_DEFINITION"), ["od_nope"])
        self.assertIn("od_nope", str(cm.exception))


class StockChars(unittest.TestCase):
    def test_stock_sc_chars_includes_charset_row(self):
        """The charset row's characters count, even ones no other text uses."""
        entries = [(trad.token_key("a"), "x守"), (trad.CHARSET_KEY, "x守阵")]
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "t-SC.dic")
            with open(path, "wb") as fh:
                fh.write(trad.write_dic(entries))
            self.assertEqual(stock_sc_chars([path]), set("x守阵"))
            other = os.path.join(tmp, "u-SC.dic")
            with open(other, "wb") as fh:
                fh.write(trad.build_dic({"b": "领"}))
            self.assertEqual(stock_sc_chars(iter([path, other])), set("x守阵领"))

    @paths.skip_unless_extracted("scenarios")
    def test_stock_sc_chars_real(self):
        paths_ = glob.glob(os.path.join(str(paths.extracted_root()), "**", "*-SC.dic"), recursive=True)
        self.assertTrue(paths_)
        chars = stock_sc_chars(paths_)
        for ch in "占领区":
            self.assertIn(ch, chars)
        self.assertGreater(len(chars), 1000)


if __name__ == "__main__":
    unittest.main()
