"""Tests for modkit.ops.models: what the rows refuse."""
from __future__ import annotations

import dataclasses
import unittest

from pydantic import ValidationError

from modkit.ops.models import CampRow, Ending, ForceRow, Knobs


class RowsTest(unittest.TestCase):
    def test_a_count_is_a_whole_number(self):
        for bad in ("many", 2.5, None):
            with self.subTest(count=bad), self.assertRaisesRegex(ValidationError, "valid integer"):
                ForceRow("T80BV_SOV", bad)

    def test_a_force_tables_fields_are_named(self):
        """A row's placement is keyword-only, so a table row never shifts a transport into a group."""
        with self.assertRaisesRegex(ValidationError, "unexpected_positional_argument"):
            ForceRow("T80BV_SOV", 4, None, "main_body")
        self.assertEqual(ForceRow("T80BV_SOV", 4, group="main_body").group, "main_body")

    def test_rows_are_frozen(self):
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ForceRow("T80BV_SOV", 4).count = 5

    def test_the_other_rows_check_their_types(self):
        with self.assertRaisesRegex(ValidationError, "valid integer"):
            Ending("t_win", "total", False)
        with self.assertRaisesRegex(ValidationError, "valid integer"):
            Knobs(1, 2, "three")
        with self.assertRaisesRegex(ValidationError, "valid integer"):
            CampRow("joueur", (("AllianceStyle", "tag", 4),), "OP_DECK")

    def test_knobs_at_a_level(self):
        self.assertEqual([Knobs(1, 2, 3).at(level) for level in (0, 1, 2)], [1, 2, 3])


if __name__ == "__main__":
    unittest.main()
