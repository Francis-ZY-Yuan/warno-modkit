"""Tests for modkit.core.glossary, the stock lookup, on synthetic dictionaries (modkit.core.trad.build_dic) in a
temporary extraction: never on stock text."""
from __future__ import annotations

import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from modkit.core import glossary, paths, trad
from modkit.core.models import AnyTexts

# (folder, file) -> {token: text}: two copies of INTERFACE_INGAME, the second holding a text the first lacks
STOCK = {
    ("core", "INTERFACE_INGAME-US.dic"): {"BTN_GO": "Go ahead", "BTN_HB": "Hold the bridge", "BTN_H": "Hold"},
    ("core", "INTERFACE_INGAME-SC.dic"): {"BTN_GO": "前进", "BTN_HB": "守桥", "BTN_H": "坚守"},
    ("core", "INTERFACE_INGAME-FR.dic"): {"BTN_GO": "En avant"},
    ("old", "INTERFACE_INGAME-SC.dic"): {"BTN_GO": "旧", "BTN_X": "仅此"},
    ("maps", "MAPS-US.dic"): {"M_TC": "Twin Cities", "M_SH": "Threshold of the bridge"},
    ("maps", "MAPS-SC.dic"): {"M_TC": "双城"},
}


def run(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = glossary.main(list(argv))
    return code, out.getvalue(), err.getvalue()


class Glossary(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for (folder, name), texts in STOCK.items():
            os.makedirs(os.path.join(tmp.name, folder), exist_ok=True)
            with open(os.path.join(tmp.name, folder, name), "wb") as fh:
                fh.write(trad.build_dic(texts))
        env = mock.patch.dict(os.environ, {paths.ENV_EXTRACTED: tmp.name})
        env.start()
        self.addCleanup(env.stop)

    def test_rows_by_stem_token_and_language(self):
        """Every language of a token in one row; a token in several copies keeps the first copy's text."""
        rows = glossary.stock_rows()
        self.assertEqual(rows["INTERFACE_INGAME"]["BTN_GO"], AnyTexts(FR="En avant", SC="前进", US="Go ahead"))
        self.assertEqual(rows["INTERFACE_INGAME"]["BTN_X"], AnyTexts(SC="仅此"))
        self.assertEqual(set(glossary.stock_rows("MAPS")), {"MAPS"})

    def test_term_exact_rows_first_then_the_shortest_holding_it(self):
        code, out, err = run("term", "hold", "--lang", "sc")
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.splitlines(), [
            "| dictionary | token | US | SC |", "| --- | --- | --- | --- |",
            "| INTERFACE_INGAME | BTN_H | Hold | 坚守 |",
            "| INTERFACE_INGAME | BTN_HB | Hold the bridge | 守桥 |"])   # not "Threshold": word boundaries
        self.assertEqual(len(run("term", "the bridge", "--limit", "1")[1].splitlines()), 3)

    def test_token_rows_in_every_language_by_default(self):
        code, out, _ = run("token", "BTN_GO", "M_TC", "--dic", "MAPS")
        self.assertEqual(code, 1)
        self.assertEqual(out.splitlines()[0], "| dictionary | token | US | DEV | FR | GER | POL | RU | SC | SPA |")
        self.assertEqual(out.splitlines()[2], "| MAPS | M_TC | Twin Cities |  |  |  |  |  | 双城 |  |")
        code, out, err = run("token", "BTN_GO", "--lang", "FR")
        self.assertEqual((code, out.splitlines()[2]), (0, "| INTERFACE_INGAME | BTN_GO | Go ahead | En avant |"))

    def test_failures(self):
        for argv, code, why in ((("token", "X", "--dic", "NOPE"), 1, "no stock NOPE-"),
                                (("token", "bad token!"), 1, "FAILED: "),
                                (("term", " "), 1, "empty term")):
            with self.subTest(argv=argv):
                got, _, err = run(*argv)
                self.assertEqual(got, code)
                self.assertIn(why, err)
        with mock.patch.dict(os.environ, {paths.ENV_EXTRACTED: tempfile.gettempdir() + os.sep + "absent"}):
            code, _, err = run("term", "x")
        self.assertEqual(code, 2)
        self.assertIn("warno-setup", err)


if __name__ == "__main__":
    unittest.main()
