"""Tests for Open Door's force table, the scale knob and the share thresholds (opendoor.forces).

The table, rounding and thresholds are pure arithmetic. Only test_descriptors_exist_in_the_game reads a file, the
game's unit database (skipped without the game folder).
"""
from __future__ import annotations

import itertools
import math
import unittest

from modkit.ops import gates
from modkit.ops.forces import GEISA_SOVIET_ROWS, formation, group_total, scaled, share_count
from open_door_support import GAME
from opendoor import op
from opendoor.forces import ROWS, threshold
from opendoor.map import POINTS

UNIT_PREFIX = "$/GFX/Unit/Descriptor_Unit_"


class Forces(unittest.TestCase):
    def test_group_totals_1x(self):
        """Group totals at 1x, Medium."""
        want = {"first_echelon": 36, "main_body": 63, "pocket_ad": 6, "relief": 55, "relief_helo": 4,
                "opener_battery": 6, "probe": 4, "decoys": 8, "north_jaw": 23, "south_jaw": 16, "air_assault": 10}
        for group, total in want.items():
            with self.subTest(group=group):
                self.assertEqual(group_total(ROWS, group), total)

    def test_share_count_design_values(self):
        """floor(share * base + 0.5) reproduces the design's Medium values (design 6.4)."""
        for share, base, want in ((0.28, 36, 10), (0.42, 36, 15), (0.55, 36, 20),
                                  (0.35, 31, 11), (0.50, 31, 16), (0.65, 31, 20)):
            with self.subTest(share=share, base=base):
                self.assertEqual(share_count(share, base), want)

    def test_threshold_bounds(self):
        """A non-empty base never rounds a positive share to 0 or past the base."""
        for share, base in itertools.product((0.01, 0.28, 0.5, 0.99, 1.0), (1, 2, 36, 72)):
            with self.subTest(share=share, base=base):
                self.assertTrue(1 <= share_count(share, base) <= base)
        self.assertEqual(share_count(0, 36), 0)
        self.assertEqual(share_count(0.5, 0), 0)

    def test_thresholds_medium(self):
        self.assertEqual(threshold("B1", "medium", ROWS), 15)
        self.assertEqual(threshold("B5", "medium", ROWS), 16)
        self.assertEqual(threshold("B1", "easy", ROWS), 10)
        self.assertEqual(threshold("B5", "hard", ROWS), 20)

    def test_threshold_rejects_unknown_names(self):
        with self.assertRaises(KeyError):
            threshold("B9", "medium", ROWS)
        with self.assertRaises(KeyError):
            threshold("B1", "nightmare", ROWS)

    def test_scaled_2x(self):
        rows = scaled(ROWS, 2.0)
        self.assertEqual(group_total(rows, "main_body"), 126)
        self.assertEqual(group_total(rows, "first_echelon"), 72)
        self.assertEqual(group_total(rows, "decoys"), 8)           # fixed
        self.assertEqual(group_total(rows, "air_assault"), 10)     # fixed
        self.assertEqual(threshold("B1", "medium", rows), 30)
        self.assertEqual(threshold("B5", "medium", rows), 31)

    def test_scaled_half_keeps_every_row(self):
        rows = scaled(ROWS, 0.5)
        self.assertEqual(len(rows), len(ROWS))
        for row in rows:
            with self.subTest(group=row.group, descriptor=row.descriptor):
                self.assertGreaterEqual(row.count, 1)

    def test_scaled_half_threshold_stays_in_bounds(self):
        """At 0.5x a threshold still lies in [1, base] for every difficulty."""
        rows = scaled(ROWS, 0.5)
        base = {"B1": group_total(rows, "first_echelon"),
                "B5": sum(r.count for r in rows if r.group == "relief"
                          and r.descriptor in ("T80U_SOV", "T80U_CMD_SOV"))}
        for name, diff in itertools.product(("B1", "B5"), ("easy", "medium", "hard")):
            with self.subTest(name=name, difficulty=diff):
                self.assertTrue(1 <= threshold(name, diff, rows) <= base[name])

    def test_scaled_1x_is_identity(self):
        self.assertEqual(scaled(ROWS, 1.0), list(ROWS))

    def test_scaled_rejects_non_positive_scale(self):
        for bad in (0, -1.0):
            with self.subTest(scale=bad), self.assertRaises(ValueError):
                scaled(ROWS, bad)

    def test_formation(self):
        self.assertEqual(formation((0.0, 0.0), 1, 10.0, 3), [(0.0, 0.0)])
        pts = formation((0.0, 0.0), 7, 10.0, 3)
        self.assertEqual(len(pts), 7)
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        self.assertAlmostEqual((min(xs) + max(xs)) / 2, 0.0, delta=1e-9)
        self.assertAlmostEqual((min(ys) + max(ys)) / 2, 0.0, delta=1e-9)
        for a, b in itertools.combinations(pts, 2):
            self.assertGreaterEqual(math.dist(a, b), 10.0 - 1e-9)

    def test_formation_is_row_major_around_the_anchor(self):
        pts = formation((100.0, 200.0), 4, 10.0, 2)
        self.assertEqual(pts, [(95.0, 195.0), (105.0, 195.0), (95.0, 205.0), (105.0, 205.0)])
        self.assertEqual(formation((50.0, 50.0), 0, 10.0, 3), [])
        # fewer points than columns: one row of n, centred
        self.assertEqual(formation((0.0, 0.0), 2, 10.0, 5), [(-5.0, 0.0), (5.0, 0.0)])

    @GAME
    def test_descriptors_exist_in_the_game(self):
        """Every unit the force table and the op's deck cards name, carriers included, is in the game's unit database
        (the mod SDK's descriptors: what the build's unit gate checks a generated file against)."""
        names = {r.descriptor for r in ROWS} | {r.transport for r in ROWS if r.transport}
        names |= {u for u, *_ in (*op.REARGUARD_CARDS, *op.SUPPORT_CARDS, *op.FOREST_CARDS, *op.SOVIET_CARDS,
                                   *op.SPRING_CARDS)}
        names |= {t for _, _, t in op.REARGUARD_CARDS if t} | {op.A10_CARD, op.CAPTURED_UNIT}
        known = gates.unit_database()
        self.assertEqual(sorted(n for n in names if UNIT_PREFIX + n not in known), [])

    def test_rows_are_well_formed(self):
        for row in ROWS:
            with self.subTest(group=row.group, descriptor=row.descriptor):
                self.assertIn(row.camp, ("PACT", "NATO", "Decoys"))
                self.assertGreaterEqual(row.count, 1)
                self.assertTrue(row.spawn and row.echelon)

    def test_shared_rows_are_read_not_copied(self):
        """The Soviet groups the probes create too come from the one shared table, and no row of Open Door's own
        names one of their groups."""
        shared = {r.group for r in GEISA_SOVIET_ROWS}
        self.assertEqual([r for r in ROWS if r.group in shared], list(GEISA_SOVIET_ROWS))
        self.assertTrue(all(any(r is s for s in GEISA_SOVIET_ROWS) for r in ROWS if r.group in shared))

    def test_spawns_are_named_points(self):
        self.assertLessEqual({r.spawn for r in ROWS}, POINTS.keys())


if __name__ == "__main__":
    unittest.main()
