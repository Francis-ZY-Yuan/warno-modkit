"""Tests for Twin Strike's Workshop page files (examples/twin-strike/workshop): the item.toml loads, passes
modkit.core.workshop's offline checks, names the item and the mod its profile does, shows each half its own
changelog and fits Steam's description limit. No network."""
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

    def test_each_half_shows_its_changelog(self):
        text = workshop.render(workshop.uploaded(self.item), {"repo": "example.invalid/warno-modkit"})
        english, chinese = text.split("[hr][/hr]")
        for r in self.item.releases:
            self.assertIn(r.note, english)
            self.assertIn(r.text("zh"), chinese)
            self.assertNotIn(r.note, chinese)

    def test_the_page_fits_once_next_is_uploaded(self):
        # the longest path the repo can have: github.com/, a 39-character user name, /warno-modkit
        values = {"repo": "github.com/" + "x" * 39 + "/warno-modkit"}
        size = workshop.description_size(workshop.render(workshop.uploaded(self.item), values))
        self.assertLessEqual(size, workshop.MAX_DESCRIPTION)


if __name__ == "__main__":
    unittest.main()
