"""Gate 3, fall-zone: a script test of what the game captures (its filter counts command units) reads the command zone
(UnitDansZone ZoneType 1), not a detector circle, and counts commander-module units only. The game captures a command
zone by the commander-module units anywhere in it; a circle inside the zone sees part of it only. Seen in play (Twin
Strike, build 211352): the village turned the player's and none of the fall's consequences followed, its test reading a
circle at the village centre."""

from __future__ import annotations

import os
import tempfile
import unittest
import zipfile

from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.ops import gates
from modkit.ops.bricks import c_all, c_any, c_none, c_team, c_type, g_detect, g_units_in_zones, g_until, unit_path
from modkit.ops.build import details_files
from modkit.ops.graph import Node, i32
from modkit.ops.leveldesign import LdItem, gd_tags
from test_build import profile
from test_gates_stock import stock_scripts
from test_script_gates import zone

S, NS = "challenge_ModkitTest", "test-a"
PROFILE = profile(NS)

UNITS = """\
export Descriptor_Unit_Cmd_A is TEntityDescriptor
(
    ModulesDescriptors = [
        TCommanderModuleDescriptor
        (
        ),
    ]
)
export Descriptor_Unit_Tank_A is TEntityDescriptor
(
    ModulesDescriptors = [
        TTagsModuleDescriptor
        (
            TagSet = ['Commandant']
        ),
    ]
)
"""

CMD = (unit_path("Cmd_A"), unit_path("Cmd_B"), unit_path("Cmd_C"))


def commanders() -> frozenset[str]:
    return frozenset(CMD)


def never() -> frozenset[str]:
    raise AssertionError("the commander set is read only when the script holds a type-filtered place test")


class CommanderUnits(unittest.TestCase):
    """The commander-module set: the units whose descriptor carries TCommanderModuleDescriptor, not the units the
    "Commandant" search tag marks."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.zip = os.path.join(self.tmp.name, "base.zip")
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr(gates.UNIT_DATABASE[0], UNITS)

    def tearDown(self):
        gates._commander_units.cache_clear()
        gates.database_text.cache_clear()
        self.tmp.cleanup()

    def test_the_module_not_the_tag(self):
        self.assertEqual(gates.commander_units(self.zip), {unit_path("Cmd_A")})

    def test_none_fails(self):
        with zipfile.ZipFile(self.zip, "w") as z:
            z.writestr(gates.UNIT_DATABASE[0], UNITS.replace("TCommanderModuleDescriptor", "TOtherDescriptor"))
        with self.assertRaisesRegex(CheckError, "no unit carries TCommanderModuleDescriptor"):
            gates.commander_units(self.zip)


class FallZone(unittest.TestCase):
    """The rule on synthetic layouts: a command zone with a detector circle at its centre, the 13 Nov Twin Strike
    shape, and a second zone away from it."""

    box, far = (500000, 500000, 600000, 600000), (800000, 500000, 900000, 600000)

    def setUp(self):
        self.items = [zone("TS_CZ_Village", "CommandPoints", self.box, points=1),
                      zone("TS_CZ_Far", "CommandPoints", self.far, points=1),
                      LdItem("CircularZones", "TS_RingVillage", 550000, 550000, "CircularZone", radius_gru=40.0)]
        self.tags = {k.split("/", 1)[1]: v for k, v in gd_tags(self.items, S, NS).items()}
        self.camp = Node("TGDCamp", [], "$/GDScript/TS/Camps/ts_camp")

    def violations(self, *conds: Node, units=commanders) -> tuple[dict[str, int], list[str]]:
        return gates.fall_zone_violations([g_until(c) for c in conds], details_files(PROFILE, self.items, S), units)

    def cmd(self, *extra: str) -> Node:
        return c_any(*(c_type(u.removeprefix("$/GFX/Unit/Descriptor_Unit_")) for u in CMD), *map(c_type, extra))

    def test_the_ring_shape_fails(self):
        """The 13 Nov fall: command units counted in the village circle. The line names the zone to read."""
        counts, bad = self.violations(g_detect(self.tags["TS_RingVillage"], self.cmd(), 1, 2))
        self.assertEqual(counts, {"typed place tests": 1, "command tests": 1})
        self.assertEqual(bad, [
            "DetectUnitDansDetecteur on the circle CircularZones/TS_RingVillage counts command units (Cmd_A, Cmd_B, "
            "Cmd_C): the game captures by the command zone TS_CZ_Village, which holds the circle's centre, counting "
            "a commander-module unit anywhere in it, so the zone can turn the player's while this test never holds; "
            "read TS_CZ_Village with UnitDansZone ZoneType 1"])

    def test_the_command_zone_passes(self):
        """The fix: UnitDansZone on the command zone, ZoneType 1, with a team filter beside the types."""
        counts, bad = self.violations(g_units_in_zones([self.tags["TS_CZ_Village"]],
                                                       c_all(c_team(self.camp), self.cmd()), 1, 2))
        self.assertEqual((counts, bad), ({"typed place tests": 1, "command tests": 1}, []))

    def test_deployment_zones_fail(self):
        """ZoneType 0 looks the tag up in the deployment zones, not the command zones."""
        test = Node("TGDConditionUnitDansZone", [("Detecteurs", [self.tags["TS_CZ_Village"]]),
                                                 ("Contrainte", self.cmd()), ("ZoneType", i32(0))])
        _, bad = self.violations(test)
        self.assertEqual(bad, ["UnitDansZone ZoneType 0 on CommandPoints/TS_CZ_Village counts command units (Cmd_A, "
                               "Cmd_B, Cmd_C): the game captures by the command zones, ZoneType 1"])

    def test_types_without_the_module_fail(self):
        """A filter of mostly command units that also lists a unit the capture never counts (the 13 Nov list was
        checked against the deck by name, not against the module)."""
        _, bad = self.violations(g_units_in_zones([self.tags["TS_CZ_Village"]], self.cmd("T80BV_SOV"), 1, 2))
        self.assertEqual(bad, ["UnitDansZone on CommandPoints/TS_CZ_Village counts command units and also 1 types "
                               "without the commander module, which the game's capture never counts: T80BV_SOV"])

    def test_a_force_count_passes(self):
        """Fewer command types than others: a force count, not a capture (Open Door's defeat circle counts six
        main-body vehicles of seven types, two of them command vehicles)."""
        force = c_any(c_type("Cmd_A"), c_type("Cmd_B"), *(c_type(f"Tank_{i}") for i in range(5)))
        counts, bad = self.violations(g_detect(self.tags["TS_RingVillage"], force, 6, 2))
        self.assertEqual((counts, bad), ({"typed place tests": 1, "command tests": 0}, []))

    def test_left_out_types_are_not_counted(self):
        """A NoContrainte's types are the ones a filter leaves out: all units but the command ones count no command
        unit."""
        counts, bad = self.violations(g_detect(self.tags["TS_RingVillage"], c_all(c_team(self.camp),
                                                                                  c_none(self.cmd())), 1, 2))
        self.assertEqual((counts, bad), ({"typed place tests": 0, "command tests": 0}, []))

    def test_untyped_tests_never_read_the_units(self):
        counts, bad = self.violations(g_detect(self.tags["TS_RingVillage"], c_team(self.camp), 1, 2), units=never)
        self.assertEqual((counts, bad), ({"typed place tests": 0, "command tests": 0}, []))

    def test_the_check_raises(self):
        script = [g_until(g_detect(self.tags["TS_RingVillage"], self.cmd(), 1, 2))]
        with self.assertRaisesRegex(CheckError, r"(?s)1 script tests of what the game captures.*TS_CZ_Village"):
            gates.check_fall_zone(script, details_files(PROFILE, self.items, S), commanders)
        fixed = [g_until(g_units_in_zones([self.tags["TS_CZ_Village"]], self.cmd(), 1, 2))]
        self.assertEqual(gates.check_fall_zone(fixed, details_files(PROFILE, self.items, S), commanders),
                         {"typed place tests": 1, "command tests": 1})


@paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
class StockCommanders(unittest.TestCase):
    """The commander-module set of the game's own unit database."""

    def test_the_set(self):
        """Build 211352: 357 units carry the module, every *_CMD_* unit among them and helicopters the "Commandant"
        tag leaves out; Twin Strike's four command cards are in it, its tanks and its FOB are not."""
        units = gates.commander_units()
        self.assertGreaterEqual(len(units), 300)
        for name in ("T80BV_CMD_SOV", "BMP_2_CMD_SOV", "MTLB_CMD_SOV", "T80U_CMD_SOV", "UH60A_CO_US"):
            self.assertIn(unit_path(name), units)
        for name in ("T80BV_SOV", "FOB_SOV", "BRDM_2_SOV"):
            self.assertNotIn(unit_path(name), units)


@paths.skip_unless_extracted("scenarios")
@paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
class StockFallZone(unittest.TestCase):
    def test_no_stock_script_tests_a_capture(self):
        """The 35 stock GDScripts: 74 type-filtered place tests in 4 scripts. 10 (Survivors 7, BackhandBlow 3) name
        their types only to leave them out (NoContrainte); the other 64 (63 circles, 1 command zone, in
        CampagneStrat_Invasion_of_Cuba and RunningTheGauntlet) count strategic pawns and units, none with the
        commander module. No stock script holds a test of what the game captures, so the gate passes all of them."""
        total, bad = {}, []
        for name, nodes in stock_scripts():
            counts, why = gates.fall_zone_violations(nodes, {}, gates.commander_units)
            total, bad = {k: total.get(k, 0) + v for k, v in counts.items()}, bad + [f"{name}: {w}" for w in why]
        self.assertEqual(len(stock_scripts()), 35)
        self.assertEqual((total, bad), ({"typed place tests": 64, "command tests": 0}, []))
