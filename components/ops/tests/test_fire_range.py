"""The batteries a script creates and its fires: modkit.ops.gates.check_created_in_zone (the driver's gate 3: every unit
created inside the playable zone), check_fire_range and fire_range_gate (a fire's battery in the player's alliance,
every target in range from where it stands), and the unit-database readers they read: shoot_on_position_bands,
deck_packs and stock_deck_packs.

`Readers` reads a small synthetic database archive; `Gate` and `CreatedInZone` build small synthetic scripts,
LevelDesigns and playable zones with the toolkit and hold the gates' rules both ways. `StockCreates` runs the in-zone
gate over every stock script and `StockReaders` reads the game's own database; both skip without their data. Twin
Strike's tests prove the gates on its build (test_twin_strike_frame)."""
from __future__ import annotations

import os
import tempfile
import unittest
import zipfile

from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.ops import gates
from modkit.ops.bricks import g_create, g_seq, unit_path
from modkit.ops.build import details_files
from modkit.ops.graph import Node, build_graph, decode, encode, nodes_of, u32
from modkit.ops.leveldesign import LD_FILE, LdItem, gd_tags
from modkit.ops.models import ForceRow
from modkit.ops.rekey import TXN, def_path
from modkit.ops.shapes import GRU_WORLD, SHOOT_ON_POSITION, order
from modkit.ops.zones import playable_zone_graph, rect_polygon
from test_build import profile

S, NS = "challenge_ModkitTest", "test-a"
PROFILE = profile(NS)
G = GRU_WORLD          # world units per GRU
TOP = 600_000.0        # the synthetic playable zone's north edge, world units
BOX = (0.0, TOP, 3_000_000.0, TOP + 3_000_000.0)   # the synthetic playable zone, world units (over 40,000 GRU a side)
CAMPS = {"joueur": 0, "allie": 0, "ordinateur": 1}  # the synthetic camps and their alliances

UNITS = """\
export Descriptor_Unit_Gun_A is TEntityDescriptor
(
    ModulesDescriptors = [
        TScannerConfigurationDescriptor
        (
            VisionRangesGRU = MAP [
                ( EVisionRange/Standard, 3000.0 ),
                ( EVisionRange/LowAltitude, 4000.0 ),
            ]
        ),
        $/GFX/Weapon/WeaponDescriptor_Gun_A,
    ]
)
export Descriptor_Unit_Scout_A is TEntityDescriptor
(
    ModulesDescriptors = [
        TScannerConfigurationDescriptor
        (
            VisionRangesGRU = MAP [
                ( EVisionRange/Standard, 5000.0 ),
            ]
        ),
    ]
)
export Descriptor_Unit_Base_A is TEntityDescriptor
(
    ModulesDescriptors = []
)
"""
WEAPONS = """\
export WeaponDescriptor_Gun_A is TWeaponManagerModuleDescriptor
(
    TurretDescriptorList = [ TTurretTwoAxisDescriptor ( MountedWeaponDescriptorList = [
        TMountedWeaponDescriptor ( Ammunition = $/GFX/Weapon/Ammo_HE ),
        TMountedWeaponDescriptor ( Ammunition = $/GFX/Weapon/Ammo_Smoke ),
        TMountedWeaponDescriptor ( Ammunition = $/GFX/Weapon/Ammo_MG ),
    ] ) ]
)
"""
AMMO = """\
Ammo_HE is TAmmunitionDescriptor
(
    MinimumRangeGRU                   = 7000
    MaximumRangeGRU                   = 35000
    CanShootOnPosition                = True
)
Ammo_Smoke is TAmmunitionDescriptor
(
    MinimumRangeGRU                   = 8000
    MaximumRangeGRU                   = 30000
    CanShootOnPosition                = True
)
export Ammo_MG is TAmmunitionDescriptor
(
    MinimumRangeGRU                   = 0
    MaximumRangeGRU                   = 2000
    CanShootOnPosition                = False
)
"""
DECKS = """\
export Descriptor_Deck_A is TDeckDescriptor
(
    DeckIdentifier = "DECK_A"
    DeckPackList =
    [
        ~/Descriptor_Deck_Pack_Scout_A_Car_1_2,
        ~/Descriptor_Deck_Pack_Gun_A_1_1,
    ]
)
"""
PACKS = """\
Descriptor_Deck_Pack_Gun_A_1_1 is DeckPackDescriptor
(
    Xp = 1
    Unit = $/GFX/Unit/Descriptor_Unit_Gun_A
    Number = 1
)

Descriptor_Deck_Pack_Scout_A_Car_1_2 is DeckPackDescriptor
(
    Unit = $/GFX/Unit/Descriptor_Unit_Scout_A
    Transport = $/GFX/Unit/Descriptor_Unit_Car_A
    Number = 2
)
"""


def archive(folder: str) -> str:
    """A database archive holding the synthetic texts where the game's base.zip holds its own."""
    path = os.path.join(folder, "base.zip")
    with zipfile.ZipFile(path, "w") as z:
        z.writestr(gates.UNIT_DATABASE[0], UNITS)
        z.writestr(gates.WEAPON_DATABASE, WEAPONS)
        z.writestr(gates.AMMO_DATABASE[0], AMMO)
        z.writestr(gates.AMMO_DATABASE[1], "")
        z.writestr(gates.DECK_DATABASE[0], DECKS)
        z.writestr(gates.DECK_DATABASE[1], PACKS)
    return path


class Readers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.zip = archive(cls.tmp.name)

    @classmethod
    def tearDownClass(cls):
        gates.database_text.cache_clear()
        cls.tmp.cleanup()

    def test_shoot_on_position_bands(self):
        """The band every ShootOnPosition ammunition of the unit reaches: the largest minimum, the smallest maximum;
        an ammunition that cannot shoot on a position does not count, and a unit with none is left out."""
        self.assertEqual(gates.shoot_on_position_bands(self.zip), {unit_path("Gun_A"): (8000.0, 30000.0)})

    def test_deck_packs(self):
        """A deck's packs, in its DeckPackList order, each a row (unit, number, transport)."""
        self.assertEqual(gates.stock_deck_packs("DECK_A", self.zip),
                         [ForceRow("Scout_A", 2, "Car_A"), ForceRow("Gun_A", 1)])
        with self.assertRaisesRegex(CheckError, "0 stock decks are named NO_DECK"):
            gates.deck_packs(DECKS, PACKS, "NO_DECK")


def playable(box: tuple[float, float, float, float] | None = BOX) -> bytes:
    """A PlayableZone file: one area, the rectangle `box`; None: no area (the whole map is playable)."""
    if box is None:
        return encode(build_graph([Node("TMapAreaSet", [("Areas", [])])], []), "PlayableZone")
    x0, y0, x1, y1 = box
    zone = playable_zone_graph(list(rect_polygon(box)), ((x0 + x1) / 2, (y0 + y1) / 2, 0.0))
    return encode(build_graph(zone, []), "PlayableZone")


def script(spawn_y: float, target_y: float, camp: str = "allie", fire: bool = True,
           units: tuple[str, ...] = ("Gun_A",)) -> tuple[bytes, bytes]:
    """(script, LevelDesign) bytes: a battery of `units` created in `camp` at T_Spawn (x 50,000, y `spawn_y`) and,
    with `fire`, ordered to ShootOnPosition on T_Target (x 50,000, y `target_y`); the camps are CAMPS, each with its
    Alliance written as stock writes it (left out for 0)."""
    items = [LdItem("Tags", "T_Spawn", 50_000.0, spawn_y, "Name"),
             LdItem("Tags", "T_Target", 50_000.0, target_y, "Name")]
    tags = {k.split("/", 1)[1]: v for k, v in gd_tags(items, S, NS).items()}
    camps = {name: Node("TGDVariableCamp", [("Alliance", u32(a))] if a else [],
                        export=f"$/GDScript/RootDescriptor/{name}") for name, a in CAMPS.items()}
    group = Node("TGDVariableUnitGroup", export="$/GDScript/T/Variables/battery")
    actions = [g_create(camps[camp], group, 2, tags["T_Spawn"], unit_path(u)) for u in units]
    actions += [order(group, SHOOT_ON_POSITION, tags["T_Target"])] if fire else []
    root = Node("TGDDescriptorLaunchEffetStandard", [("CampList", list(camps.values())), ("EffetMap", g_seq(actions))],
                export="$/GDScript/RootDescriptor")
    gd = encode(build_graph([root], [root, *camps.values(), *tags.values(), group]), "GDScript")
    return gd, details_files(PROFILE, items, S)[LD_FILE]


class Gate(unittest.TestCase):
    """check_fire_range on a synthetic op: a playable zone over 40,000 GRU a side (BOX), a battery created at T_Spawn
    and fired on T_Target."""

    BANDS = {unit_path("Gun_A"): (7000.0, 35000.0), unit_path("Rocket_A"): (10000.0, 35000.0)}
    IN = TOP + 50_000.0     # a spawn inside the zone

    def check(self, spawn_y: float, target_y: float, *, zone: bytes | None = None, **kw) -> gates.FireRange:
        gd, ld = script(spawn_y, target_y, **kw)
        return gates.check_fire_range(gd, ld, playable() if zone is None else zone, "T_Spawn", "joueur",
                                      bands=self.BANDS)

    def test_passes_in_the_players_alliance_and_in_range(self):
        """The battery in the player's ally's camp (alliance 0, as the player's), created inside the zone, its target
        15,000 GRU off, inside the gun's 7,000-35,000; it stands where it is created. In the player's own camp too."""
        r = self.check(self.IN, self.IN + 15000 * G)
        self.assertEqual((r.alliance, r.camps, r.stand), (0, ("allie",), r.at))
        ((unit, target, d, lo, hi),) = r.fires
        self.assertEqual((unit, target, lo, hi), ("Gun_A", "T_Target", 7000.0, 35000.0))
        self.assertAlmostEqual(d, 15000.0, places=3)
        self.assertEqual(self.check(self.IN, self.IN + 15000 * G, camp="joueur").camps, ("joueur",))

    def test_a_battery_outside_the_players_alliance_fails(self):
        """The same battery in an enemy-alliance camp: the player's units would engage it."""
        with self.assertRaisesRegex(CheckError, r"Gun_A is created at T_Spawn in ordinateur, outside the player's "
                                                r"alliance \(0\): the player's units engage it"):
            self.check(self.IN, self.IN + 15000 * G, camp="ordinateur")

    def test_a_target_out_of_range_fails(self):
        """The target 5,000 GRU from the spawn, inside the gun's 7,000 minimum; a battery with a type whose band the
        target misses fails too, by that type."""
        with self.assertRaisesRegex(CheckError, r"T_Target is 5,000 GRU from where Gun_A stands at T_Spawn, outside "
                                                r"its ShootOnPosition band \(7,000-35,000 GRU\): move the spawn"):
            self.check(self.IN, self.IN + 5000 * G)
        with self.assertRaisesRegex(CheckError, r"T_Target is 8,000 GRU from where Rocket_A stands"):
            self.check(self.IN, self.IN + 8000 * G, units=("Gun_A", "Rocket_A"))

    def test_the_range_is_measured_from_where_the_battery_stands(self):
        """A spawn 6,000 GRU north of the zone stands on its edge [[created-units-stand-in-zone]]: a target 12,000
        GRU from the spawn is 6,000 from the edge, inside the gun's minimum. With a whole-map zone (no area) the same
        battery stands at its spawn and passes."""
        y = TOP - 6000 * G
        with self.assertRaisesRegex(CheckError, r"T_Target is 6,000 GRU from where Gun_A stands"):
            self.check(y, y + 12000 * G)
        r = self.check(y, y + 12000 * G, zone=playable(None))
        self.assertEqual(r.stand, r.at)
        self.assertAlmostEqual(r.fires[0][2], 12000.0, places=3)

    def test_a_battery_never_fired_fails(self):
        with self.assertRaisesRegex(CheckError, "battery is created at T_Spawn but never ordered to ShootOnPosition"):
            self.check(self.IN, self.IN, fire=False)


class CreatedInZone(unittest.TestCase):
    """check_created_in_zone, the driver's gate 3, on the synthetic script: every CreateUnitOnPosition stands inside
    the shipped playable zone [[created-units-stand-in-zone]]."""

    @staticmethod
    def check(spawn_y: float, zone: bytes | None = None, ld: bool = True) -> int:
        gd, ld_raw = script(spawn_y, spawn_y)
        details = {gates.PLAYABLE_FILE: playable() if zone is None else zone, **({LD_FILE: ld_raw} if ld else {})}
        return gates.check_created_in_zone(nodes_of(decode(gd)[0]), details)

    def test_inside_passes(self):
        self.assertEqual(self.check(TOP + 50_000.0), 1)

    def test_outside_fails(self):
        """4,000 GRU north of the zone: the game would put the battery on the zone's edge."""
        with self.assertRaisesRegex(CheckError, r"1 of 1 CreateUnitOnPosition create units outside the playable zone:"
                                                r"\n  Gun_A is created at T_Spawn, 4,000 GRU N of the playable zone: it "
                                                r"stands on the zone's edge, where the player's units see and engage it"):
            self.check(TOP - 4000 * G)

    def test_a_whole_map_zone_holds_everything(self):
        """A PlayableZone file with no area (Survivors, RedJuggernaut): the whole map is playable."""
        self.assertEqual(self.check(TOP - 4000 * G, zone=playable(None)), 1)

    def test_an_unbound_position_or_no_zone_fails(self):
        with self.assertRaisesRegex(CheckError, "a CreateUnitOnPosition of Gun_A names no LevelDesign item"):
            self.check(TOP + 50_000.0, ld=False)
        gd, ld = script(TOP, TOP)
        with self.assertRaisesRegex(CheckError, "the script creates units but the mod ships no out/PlayableZone"):
            gates.check_created_in_zone(nodes_of(decode(gd)[0]), {LD_FILE: ld})

    def test_a_script_that_creates_nothing_needs_no_zone(self):
        self.assertEqual(gates.check_created_in_zone([Node("TGDDescriptorSequential", [("SubActions", [])])], {}), 0)


@paths.skip_unless_extracted("scenarios")
class StockCreates(unittest.TestCase):
    """Stock creates every unit inside the playable zone: the in-zone gate passes all 313 CreateUnitOnPosition of the
    22 stock scenarios that create units, each read with its own LevelDesign and PlayableZone (four ship a zone file
    with no area: the whole map). Build 201602 had 300 in 21: 210942 adds the scenario CampagneStrat_Invasion_of_Cuba
    (13), the others unchanged."""

    def test_every_stock_create_stands_inside(self):
        root = str(paths.extracted_root())
        creates, scenarios, whole = 0, 0, 0
        for name in sorted(os.listdir(os.path.join(root, "scenarios"))):
            folder = os.path.join(root, "scenarios", name)
            gd = os.path.join(folder, *def_path("GDScript", TXN, name).split("/"))
            if not os.path.isfile(gd):
                continue
            details = {}
            for inner in (LD_FILE, gates.PLAYABLE_FILE):
                with open(os.path.join(folder, *inner.split("/")), "rb") as fh:
                    details[inner] = fh.read()
            with open(gd, "rb") as fh:
                n = gates.check_created_in_zone(nodes_of(decode(fh.read())[0]), details)
            creates, scenarios = creates + n, scenarios + (n > 0)
            whole += gates.playable_ring(details[gates.PLAYABLE_FILE]) is None
        self.assertEqual((creates, scenarios, whole), (313, 22, 4))


@paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
class StockReaders(unittest.TestCase):
    """The readers over the game's own database, as Twin Strike's fire-range gate reads it."""

    def test_the_division_guns(self):
        bands = gates.shoot_on_position_bands()
        self.assertEqual(bands[unit_path("2S7M_Malka_SOV")], (7000.0, 35000.0))
        self.assertEqual(bands[unit_path("BM27_Uragan_SOV")], (10000.0, 35000.0))

    def test_a_stock_deck(self):
        """RedJuggernaut's player deck: 26 packs, its heavy scouts in their BMP-1P reco."""
        packs = gates.stock_deck_packs("OP_BASE_RJ_Player")
        self.assertEqual(len(packs), 26)
        self.assertIn(("HvyScout_SOV", "BMP_1P_reco_SOV"), [(p.unit, p.transport) for p in packs])


if __name__ == "__main__":
    unittest.main()
