"""Tests for modkit.core.models: what a Texts refuses."""
from __future__ import annotations

import unittest

from pydantic import ValidationError

from modkit.core.models import Term, Texts


class TextsTest(unittest.TestCase):
    def test_an_unknown_language_is_refused(self):
        for lang in ("EN", "ZH", "sc"):
            with self.subTest(lang=lang), self.assertRaisesRegex(ValidationError, lang):
                Texts(US="Hold", **{lang: "x"})

    def test_us_is_required(self):
        with self.assertRaisesRegex(ValidationError, "US"):
            Texts(SC="坚守")


class TermTest(unittest.TestCase):
    def test_each_text_but_us_has_a_source(self):
        term = Term(US="Front", SC="方面军", source={"SC": "doctrine: фронт"})
        self.assertEqual((term.SC, term.source.SC), ("方面军", "doctrine: фронт"))
        for kwargs in ({"SC": "方面军", "source": {}},                    # a text without its source
                       {"source": {"SC": "doctrine"}},                    # a source without its text
                       {"SC": "方面军", "source": {"SC": ""}},            # an empty source
                       {"SC": "方面军", "source": {"SC": "x", "ZH": "y"}}):  # not a game language
            with self.subTest(kwargs=kwargs), self.assertRaises(ValidationError):
                Term(US="Front", **kwargs)


if __name__ == "__main__":
    unittest.main()
