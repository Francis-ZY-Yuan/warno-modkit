"""Tests for modkit.core.models: what a Texts refuses."""
from __future__ import annotations

import unittest

from pydantic import ValidationError

from modkit.core.models import Texts


class TextsTest(unittest.TestCase):
    def test_an_unknown_language_is_refused(self):
        for lang in ("EN", "ZH", "sc"):
            with self.subTest(lang=lang), self.assertRaisesRegex(ValidationError, lang):
                Texts(US="Hold", **{lang: "x"})

    def test_us_is_required(self):
        with self.assertRaisesRegex(ValidationError, "US"):
            Texts(SC="坚守")


if __name__ == "__main__":
    unittest.main()
