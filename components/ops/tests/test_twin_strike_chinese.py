"""Tests for Twin Strike's Simplified Chinese (examples/twin-strike: twinstrike.strings' SC texts and TERMS), for what
gate 1 does not check: every worded token has its Chinese (a token without SC would show the English), the texts take
their terms from the op's term table, and each dialog names its buttons by the labels the game draws. The menu texts'
lengths are test_twin_strike_frame.Strings'. `Buttons` reads the game's INTERFACE_INGAME dictionary and skips without
an extraction."""
from __future__ import annotations

import os
import re
import unittest

import twin_strike_support  # noqa: F401  (puts the example on sys.path)
from modkit.core import paths, trad
from modkit.ops import INGAME_DIC
from twinstrike import profile, strings

CJK = re.compile(r"[一-鿿]")
SC = {dic: {tok: texts.SC for tok, texts in tokens.items()} for dic, tokens in strings.STRINGS.items()}


class Terms(unittest.TestCase):
    def test_every_worded_text_is_translated(self):
        """Every token has an SC text, with Chinese words wherever the English has words (a bare counter, "%1 / %2",
        keeps the English)."""
        for tokens in strings.STRINGS.values():
            for tok, texts in tokens.items():
                with self.subTest(token=tok):
                    if re.search(r"[A-Za-z]{2,}", re.sub(r"#\w+\{", "", texts.US)):
                        self.assertRegex(texts.SC, CJK)
                    else:
                        self.assertEqual(texts.SC, texts.US)

    def test_texts_take_their_terms_from_the_table(self):
        """Every term of TERMS is used by some Chinese text; the titles, the difficulty names and the end grades are
        the table's."""
        texts = [zh for tokens in SC.values() for zh in tokens.values()]
        term = {english: t.SC.text for english, t in strings.TERMS.items()}
        for english, t in strings.TERMS.items():
            with self.subTest(term=english):
                self.assertTrue(t.SC.source)
                self.assertTrue(any(term[english] in text for text in texts), term[english])
        menu, loc = SC["SCENARIO_DEFINITION"], SC["Scripting/Localization"]
        for tok in profile.TITLE_TOKENS:
            self.assertEqual(menu[tok], term["Operation Twin Strike"])
        for level, name in enumerate(("Easy", "Medium", "Hard")):
            self.assertEqual(loc[f"ts_hdif{level}"], f"{term['difficulty']}：{term[name]}。")
        self.assertIn(term["Medium"], loc["ts_hdif9"])
        graded = 0
        for tok, texts in strings.STRINGS["Scripting/Dialog"].items():
            for grade in ("TOTAL VICTORY", "MAJOR VICTORY", "MINOR VICTORY", "DEFEAT"):
                if texts.US.startswith(f"#bold{{{grade}.}}"):
                    graded += 1
                    with self.subTest(token=tok):
                        self.assertTrue(texts.SC.startswith(f"#bold{{{term[grade]}。}}"), texts.SC)
        self.assertEqual(graded, 9)   # three wins, each released or withheld, and three defeats


@paths.skip_unless_extracted(os.path.dirname(INGAME_DIC))
class Buttons(unittest.TestCase):
    def test_buttons_named_by_the_labels_the_game_draws(self):
        """Each two-button dialog names its buttons by their labels in the game's INTERFACE_INGAME dictionary, where the
        game looks them up [[dialog-button-ingame-dictionary]]: the English text by the US label, the Chinese by the
        SC label, each opening a line with its colon; TERMS holds the same SC label under the US one."""
        labels = {}
        for lang in ("US", "SC"):
            with open(os.path.join(str(paths.extracted_root()), *INGAME_DIC.format(lang=lang).split("/")), "rb") as fh:
                labels[lang] = dict(trad.read_dic(fh.read()))
        for dialog, buttons in strings.BUTTONS.items():
            texts = strings.STRINGS["Scripting/Dialog"][dialog]
            for button in (buttons.yes, buttons.no):
                us, sc = (labels[lang][trad.token_key(button)] for lang in ("US", "SC"))
                with self.subTest(dialog=dialog, button=button):
                    self.assertIn(f"\n{us}: ", texts.US)
                    self.assertIn(f"\n{sc}：", texts.SC)
                    self.assertEqual(strings.TERMS[us].SC.text, sc)


if __name__ == "__main__":
    unittest.main()
