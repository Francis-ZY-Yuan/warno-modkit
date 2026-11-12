"""Tests for Twin Strike's Workshop page files (examples/twin-strike/workshop): the item.toml loads, passes
modkit.core.workshop's offline checks, and names the item and the mod its profile does. No network."""
from __future__ import annotations

import unittest

from twin_strike_support import TWIN_STRIKE
from modkit.core import workshop
from twinstrike import profile

ITEM = TWIN_STRIKE / "workshop" / "item.toml"


class Item(unittest.TestCase):
    def setUp(self):
        self.item = workshop.load_item(ITEM)

    def test_valid_offline(self):
        self.assertEqual(workshop.validate(self.item), [])

    def test_the_profile_names_it(self):
        self.assertEqual(self.item.id, profile.WORKSHOP_ID)
        self.assertEqual(self.item.mod_name, profile.MOD_NAME)

    def test_one_placeholder_filled_locally(self):
        self.assertEqual(self.item.vars, ("repo",))


if __name__ == "__main__":
    unittest.main()
