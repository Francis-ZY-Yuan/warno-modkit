"""Tests for the small shared helpers every generator uses: modkit.core.names and ndfbin.as_f32."""
import unittest
import uuid

from modkit.core import names, ndfbin


class NamesTest(unittest.TestCase):
    def test_unit_path(self):
        self.assertEqual(names.unit_path("T80BV_SOV"), "$/GFX/Unit/Descriptor_Unit_T80BV_SOV")

    def test_name_guid_is_uuid5_of_the_name_under_the_namespace(self):
        got = names.name_guid("my-mod", "challenge_X/Ranking/Name")
        self.assertEqual(got, uuid.uuid5(uuid.NAMESPACE_URL, "my-mod/challenge_X/Ranking/Name").bytes)
        self.assertEqual(got.hex(), "17a7513f0aa8517793d316879effda14")  # pinned: the stored bytes never drift
        self.assertNotEqual(got, names.name_guid("other-mod", "challenge_X/Ranking/Name"))


class AsF32Test(unittest.TestCase):
    def test_rounds_through_single_precision(self):
        self.assertEqual(ndfbin.as_f32(0.1, 2.0), (0.10000000149011612, 2.0))
        self.assertEqual(ndfbin.as_f32(), ())


if __name__ == "__main__":
    unittest.main()
