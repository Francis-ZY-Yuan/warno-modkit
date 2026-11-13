"""Tests for modkit.core.gates: the one CheckError, gates that a reviewed exception lets through, and the fixture
comparison."""
import contextlib
import io
import os
import tempfile
import unittest

from pydantic import ValidationError

from modkit.core import gates
from modkit.core.gates import CheckError, check, check_fixture_text, run_gate


def gate(n: int) -> int:
    check(n > 0, f"{n} is not positive")
    return n * 2


class CheckTest(unittest.TestCase):
    def test_check_raises_check_error(self):
        self.assertIsNone(check(True, "fine"))
        with self.assertRaisesRegex(CheckError, "^broken$"):
            check(False, "broken")
        self.assertTrue(issubclass(CheckError, RuntimeError))


class RunGateTest(unittest.TestCase):
    def run_quiet(self, *args, **kwargs):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            result = run_gate(*args, **kwargs)
        return result, out.getvalue()

    def test_run_gate_passes_result_through(self):
        self.assertEqual(self.run_quiet("positive", gate, 3, pending={}), (6, ""))

    def test_run_gate_pending_matches_exact_message(self):
        result, out = self.run_quiet("positive", gate, -1, pending={"positive": ("-1 is not positive",)})
        self.assertIsNone(result)
        self.assertEqual(out, "REVIEW PENDING: positive: -1 is not positive (the rest of this gate did not run)\n")

    def test_a_pending_entry_suspends_the_rest_of_its_gate_call(self):
        """The entry covers the first failure the gate call raised; a second fault the same call would have found
        is never checked, and the log line says the rest of the gate did not run."""
        seen = []

        def two_checks(a: int, b: int) -> None:
            check(a > 0, f"{a} is not positive")
            seen.append("second check ran")
            check(b > 0, f"{b} is not positive")

        result, out = self.run_quiet("pair", two_checks, -1, -2, pending={"pair": ("-1 is not positive",)})
        self.assertEqual((result, seen), (None, []))
        self.assertTrue(out.endswith(" (the rest of this gate did not run)\n"), out)
        with self.assertRaisesRegex(CheckError, "^-2 is not positive$"):  # once the first is fixed, the second shows
            self.run_quiet("pair", two_checks, 1, -2, pending={"pair": ("-1 is not positive",)})

    def test_run_gate_other_message_raises(self):
        for pending in ({"positive": ("-2 is not positive",)},   # same gate, another message
                        {"positive": ("-1 is not positive.",)},  # not exact
                        {"other": ("-1 is not positive",)},      # same message, another gate
                        {}):
            with self.subTest(pending=pending), self.assertRaisesRegex(CheckError, "-1 is not positive"):
                self.run_quiet("positive", gate, -1, pending=pending)

    def test_run_gate_never_swallows_other_errors(self):
        def boom():
            raise ValueError("not a gate failure")
        with self.assertRaises(ValueError):
            self.run_quiet("boom", boom, pending={"boom": ("not a gate failure",)})

    def test_several_messages_per_gate(self):
        """A gate that runs once per file may hold one reviewed failure per file."""
        pending = {"positive": ("-1 is not positive", "-2 is not positive")}
        for n in (-1, -2):
            with self.subTest(n=n):
                self.assertEqual(self.run_quiet("positive", gate, n, pending=pending),
                                 (None, f"REVIEW PENDING: positive: {n} is not positive "
                                        f"(the rest of this gate did not run)\n"))
        with self.assertRaisesRegex(CheckError, "-3 is not positive"):
            self.run_quiet("positive", gate, -3, pending=pending)

    def test_fired_entries_and_the_ones_that_no_longer_fire(self):
        pending = {"positive": ("-1 is not positive", "-2 is not positive"), "other": ("x",)}
        fired: list[tuple[str, str]] = []
        with contextlib.redirect_stdout(io.StringIO()):
            run_gate("positive", gate, -1, pending=pending, fired=fired)
            run_gate("positive", gate, 3, pending=pending, fired=fired)
        self.assertEqual(fired, [("positive", "-1 is not positive")])
        self.assertEqual(gates.unfired(pending, fired), [("other", "x"), ("positive", "-2 is not positive")])

    def test_a_bare_message_is_refused(self):
        """Each gate's messages are a tuple: a bare string, which a message would match any part of, is refused."""
        for pending in ({"positive": "-1 is not positive"}, {"positive": "is not"}):
            with self.subTest(pending=pending), self.assertRaises(ValidationError):
                self.run_quiet("positive", gate, -1, pending=pending)
        with self.assertRaises(ValidationError):
            gates.unfired({"positive": "x"}, [])


class FixtureTextTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.path = os.path.join(tmp.name, "expected", "x.txt")

    def run_it(self, text: str, bless: bool = False) -> str:
        return check_fixture_text(self.path, text, bless=bless, label="expected/x.txt", subject="x.ndfbin: dump")

    def test_missing_then_bless_then_match(self):
        with self.assertRaisesRegex(CheckError, r"^expected/x\.txt is missing: run with --bless and review it$"):
            self.run_it("a\nb\n")
        self.assertEqual(self.run_it("a\nb\n", bless=True), "blessed expected/x.txt")
        with open(self.path, "rb") as fh:
            self.assertEqual(fh.read(), b"a\nb\n")  # UTF-8, LF
        self.assertEqual(self.run_it("a\nb\n"), "matches expected/x.txt")

    def test_a_difference_fails_with_the_diff(self):
        self.run_it("a\nb\nc\n", bless=True)
        with self.assertRaises(CheckError) as cm:
            self.run_it("a\nB\nc\n")
        self.assertEqual(str(cm.exception).split("\n"), [
            "x.ndfbin: dump differs from expected/x.txt (re-run with --bless if intended):",
            "--- expected", "+++ generated", "@@ -1,3 +1,3 @@", " a", "-b", "+B", " c"])

    def test_the_diff_is_cut_at_60_lines(self):
        self.run_it("".join(f"{i}\n" for i in range(200)), bless=True)
        with self.assertRaises(CheckError) as cm:
            self.run_it("".join(f"x{i}\n" for i in range(200)))
        self.assertEqual(len(str(cm.exception).split("\n")), 61)


if __name__ == "__main__":
    unittest.main()
