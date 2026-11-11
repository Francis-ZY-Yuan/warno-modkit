"""The build driver prints the game-build warning to the console (stderr) once, at the start, and writes it nowhere."""
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from modkit.core import gamebuild
from modkit.ops import build as ops_build

LINE = "GAME BUILD: installed 999999; test line"


class Stop(Exception):
    pass


class DriverWarning(unittest.TestCase):
    def start(self, warning):
        content = mock.Mock(scenario="s")
        out, err = io.StringIO(), io.StringIO()
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(gamebuild, "build_warning", return_value=warning), \
                mock.patch.object(ops_build, "GateRun", side_effect=Stop), \
                contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            out_dir = os.path.join(tmp, "out")
            with self.assertRaises(Stop):
                ops_build.build(mock.Mock(), content, out_dir)
            self.assertFalse(os.path.exists(out_dir))
        return out.getvalue(), err.getvalue()

    def test_warning_goes_to_the_console_only(self):
        out, err = self.start(LINE)
        self.assertEqual(err.count(LINE), 1)
        self.assertNotIn(LINE, out)

    def test_no_warning_prints_nothing(self):
        out, err = self.start(None)
        self.assertEqual((out, err), ("", ""))


if __name__ == "__main__":
    unittest.main()
