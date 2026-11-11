"""The fire-range gate (modkit.ops.gates.check_fire_range, fire_range_gate) and the unit-database readers it reads:
ground_vision, shoot_on_position_bands, deck_packs and stock_deck_packs.

`Readers` reads a small synthetic database archive; `Gate` builds small synthetic scripts, LevelDesigns and playable
zones with the toolkit and holds the gate's rules both ways. `StockReaders` reads the game's own database and skips
without it; Twin Strike's tests prove the gate on its build (test_twin_strike_frame)."""
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
from modkit.ops.graph import Imp, Node, Str, build_graph, encode
from modkit.ops.leveldesign import LD_FILE, LdItem, gd_tags
from modkit.ops.shapes import GRU_WORLD, SHOOT_ON_POSITION, order
from modkit.ops.zones import playable_zone_graph, rect_polygon
from test_build import profile

S, NS = "challenge_ModkitTest", "test-a"
PROFILE = profile(NS)
G = GRU_WORLD          # world units per GRU
TOP = 600_000.0        # the synthetic playable zone's north edge, world units

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

    def test_ground_vision(self):
        """Each unit's EVisionRange/Standard entry; a unit with no scanner is left out."""
        self.assertEqual(gates.ground_vision(self.zip, minimum=2),
                         {unit_path("Gun_A"): 3000.0, unit_path("Scout_A"): 5000.0})
        with self.assertRaisesRegex(CheckError, "only 2 units with a ground vision range"):
            gates.ground_vision(self.zip)

    def test_shoot_on_position_bands(self):
        """The band every ShootOnPosition ammunition of the unit reaches: the largest minimum, the smallest maximum;
        an ammunition that cannot shoot on a position does not count, and a unit with none is left out."""
        self.assertEqual(gates.shoot_on_position_bands(self.zip), {unit_path("Gun_A"): (8000.0, 30000.0)})

    def test_deck_packs(self):
        """A deck's packs, in its DeckPackList order, each (unit, number, transport)."""
        self.assertEqual(gates.stock_deck_packs("DECK_A", self.zip), [("Scout_A", 2, "Car_A"), ("Gun_A", 1, None)])
        with self.assertRaisesRegex(CheckError, "0 stock decks are named NO_DECK"):
            gates.deck_packs(DECKS, PACKS, "NO_DECK")


class Gate(unittest.TestCase):
    """check_fire_range on a synthetic op: a 100,000 world square playable zone, a target inside it and a spawn
    north of it, a player camp with a deck, a card and a pre-placed unit."""

    BOX = (0.0, TOP, 100_000.0, TOP + 100_000.0)     # the playable zone, world units
    BOUNDS = (0.0, 0.0, 3_000_000.0, 3_000_000.0)
    VISION = {unit_path("Scout_A"): 5000.0, unit_path("Tank_A"): 2000.0, unit_path("Gun_A"): 3000.0}
    BANDS = {unit_path("Gun_A"): (7000.0, 35000.0), unit_path("Rocket_A"): (10000.0, 35000.0)}

    def build(self, spawn_y: float, target_y: float = TOP + 50_000.0, fire: bool = True,
              units: tuple[str, ...] = ("Gun_A",)) -> tuple[bytes, bytes, bytes]:
        """(script, LevelDesign, playable zone) bytes: a battery of `units` created at T_Spawn (x 50,000, y
        `spawn_y`) and, with `fire`, ordered to ShootOnPosition on T_Target (x 50,000, y `target_y`); the player's
        camp gets deck DECK_A, the card Tank_A and a pre-placed Base_A."""
        items = [LdItem("Tags", "T_Spawn", 50_000.0, spawn_y, "Name"),
                 LdItem("Tags", "T_Target", 50_000.0, target_y, "Name"),
                 LdItem("Camp_0", "C0_Base", 60_000.0, TOP + 50_000.0, "Spawn", unit="Base_A")]
        tags = {k.split("/", 1)[1]: v for k, v in gd_tags(items, S, NS).items()}
        camps = [Node("TGDVariableCamp", export=f"$/GDScript/RootDescriptor/{name}")
                 for name in ("joueur", "ordinateur")]
        group = Node("TGDVariableUnitGroup", export="$/GDScript/T/Variables/battery")
        actions = [Node("TGDDescriptorSetDeck", [("Camp", camps[0]), ("DeckIdentifier", Str("DECK_A"))]),
                   Node("TGDDescriptorAddUnitToDeck", [("Camp", camps[0]), ("TypeUnit", Imp(unit_path("Tank_A")))]),
                   *(g_create(camps[1], group, 2, tags["T_Spawn"], unit_path(u)) for u in units)]
        actions += [order(group, SHOOT_ON_POSITION, tags["T_Target"])] if fire else []
        root = Node("TGDDescriptorLaunchEffetStandard", [("CampList", camps), ("EffetMap", g_seq(actions))],
                    export="$/GDScript/RootDescriptor")
        gd = encode(build_graph([root], [root, *camps, *tags.values(), group]), "GDScript")
        zone = playable_zone_graph(list(rect_polygon(self.BOX)), (50_000.0, TOP + 50_000.0, 0.0))
        playable = encode(build_graph(zone, []), "PlayableZone")
        return gd, details_files(PROFILE, items, S)[LD_FILE], playable

    def check(self, *args, vision=None, **kw) -> gates.FireRange:
        return gates.check_fire_range(*self.build(*args, **kw), "T_Spawn", self.BOUNDS, "joueur",
                                      vision=self.VISION if vision is None else vision, bands=self.BANDS,
                                      deck_units=lambda deck: [unit_path("Scout_A"), unit_path("Car_A")])

    def test_passes_out_of_sight_and_in_range(self):
        """A spawn 6,000 GRU north of the zone, past the Scout's 5,000 (the deck's; the card's and the pre-placed
        unit's are shorter or none), its target 15,000 GRU off, inside the gun's 7,000-35,000."""
        r = self.check(TOP - 6000 * G, TOP - 6000 * G + 15000 * G)
        self.assertAlmostEqual(r.outside_gru, 6000.0, places=3)
        self.assertEqual((r.direction, r.vision_gru, r.watcher), ("N", 5000.0, unit_path("Scout_A")))
        ((unit, target, d, lo, hi),) = r.fires
        self.assertEqual((unit, target, lo, hi), ("Gun_A", "T_Target", 7000.0, 35000.0))
        self.assertAlmostEqual(d, 15000.0, places=3)

    def test_a_target_out_of_range_fails(self):
        """The target 5,000 GRU from the spawn, inside the gun's 7,000 minimum; a battery with a type whose band the
        target misses fails too, by that type."""
        y = TOP - 6000 * G
        with self.assertRaisesRegex(CheckError, r"T_Target is 5,000 GRU from T_Spawn, outside Gun_A's ShootOnPosition "
                                                r"band \(7,000-35,000 GRU\): move the spawn"):
            self.check(y, y + 5000 * G)
        with self.assertRaisesRegex(CheckError, r"T_Target is 8,000 GRU from T_Spawn, outside Rocket_A's"):
            self.check(y, y + 8000 * G, units=("Gun_A", "Rocket_A"))

    def test_in_sight_fails(self):
        """4,000 GRU north of the zone: inside the Scout's 5,000."""
        y = TOP - 4000 * G
        with self.assertRaisesRegex(CheckError, r"T_Spawn stands 4,000 GRU N of the playable zone, inside the ground "
                                                r"vision range of the player's Scout_A \(5,000 GRU\)"):
            self.check(y, y + 15000 * G)

    def test_no_vision_known_is_reported_only(self):
        r = self.check(TOP - 1000 * G, TOP + 10000 * G, vision={})
        self.assertEqual((r.vision_gru, r.watcher), (None, None))

    def test_inside_the_zone_or_off_the_map_fails(self):
        with self.assertRaisesRegex(CheckError, "lies inside the playable zone"):
            self.check(TOP + 50_000.0, TOP + 50_000.0 + 15000 * G, vision={})
        with self.assertRaisesRegex(CheckError, "lies outside the map"):
            self.check(-10_000.0, -10_000.0 + 15000 * G, vision={})

    def test_a_battery_never_fired_fails(self):
        with self.assertRaisesRegex(CheckError, "battery is created at T_Spawn but never ordered to ShootOnPosition"):
            self.check(TOP - 6000 * G, fire=False)

    def test_the_player_units(self):
        """The deck's units and transports, the cards, the units pre-placed in the player's camp."""
        gd, ld, _ = self.build(0.0)
        nb, _, _ = gates.decode(gd)
        got = gates.player_units(nb, gates.nodes_of(nb), gates.read_ld_items(ld), "joueur",
                                 lambda deck: [unit_path(f"{deck}_unit")])
        self.assertEqual(got, {unit_path("DECK_A_unit"), unit_path("Tank_A"), unit_path("Base_A")})


@paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
class StockReaders(unittest.TestCase):
    """The readers over the game's own database, as Twin Strike's fire-range gate reads it."""

    def test_the_division_guns(self):
        bands, vision = gates.shoot_on_position_bands(), gates.ground_vision()
        self.assertEqual(bands[unit_path("2S7M_Malka_SOV")], (7000.0, 35000.0))
        self.assertEqual(bands[unit_path("BM27_Uragan_SOV")], (10000.0, 35000.0))
        self.assertEqual(vision[unit_path("2S7M_Malka_SOV")], 3500.0)
        self.assertNotIn(unit_path("FOB_SOV"), vision)

    def test_a_stock_deck(self):
        """RedJuggernaut's player deck: 26 packs, its heavy scouts in their BMP-1P reco."""
        packs = gates.stock_deck_packs("OP_BASE_RJ_Player")
        self.assertEqual(len(packs), 26)
        self.assertIn(("HvyScout_SOV", "BMP_1P_reco_SOV"), [(u, t) for u, _, t in packs])


if __name__ == "__main__":
    unittest.main()
