"""Tests for Twin Strike's forces (examples/twin-strike/twinstrike/forces.py): the force tables, the scale knob and the
share thresholds (design 6.2-6.4), and the player's deck (design 6.1).

`Tables`, `Thresholds` and `Deck` need no stock data. `StockDeck` re-derives the start cards from RedJuggernaut's own
deck in the stock decks, so a game update that changes it fails here, not in the build; `StockSupply` re-checks why the
Soviet player's supply is added (the deck has no supply helicopter, and its trucks sit only in the tank battalions'
HQ groups); `StockChoices` re-derives the ATGM team, its carrier and the reserve's T-80U variant; `Balance` holds the
force ratios of design 6.5 by the unit database's deck costs; `Units` holds every name to the game's unit database.
They skip without the extraction or the game folder."""
from __future__ import annotations

import unittest

from twin_strike_support import (DECK_DATA, GAME, division_rules, stock_deck, stock_deck_groups, supply_units,
                                 unit_facts)
from modkit.ops import gates
from modkit.ops.forces import scaled
from modkit.ops.models import ForceRow
from modkit.ops.profile import RJ_PLAYER_DECK, SOVIET_PLAYER_SIDES, SOVIET_PLAYER_SUPPLY
from twinstrike import forces, op
from twinstrike.map import POINTS

EASY, MEDIUM, HARD = 0, 1, 2           # op.TEAMS' order
INCOME_TICK_S = 60.0                   # the income's period, the game's constant [[scripted-economy]]


def totals(rows) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        out[r.group] = out.get(r.group, 0) + r.count
    return out


class Tables(unittest.TestCase):
    def test_design_counts_at_1x(self):
        """Design 6.2 and 6.3's counts: the FOBs, the guns, the garrison (14), battalion 1 (50, its recon screen 8, its
        air defence 9) and battalion 2 (52)."""
        self.assertEqual(forces.FORCE_SCALE, 1.0)
        self.assertEqual(totals(forces.ROWS), {"fob": 2, "guns_heavy": 6, "guns_rockets": 6, "garrison": 14, "bn1": 50,
                                               "bn1_recon": 8, "bn1_ad": 9, "bn2": 52})
        self.assertEqual(forces.GROUPS, ("fob", "guns_heavy", "guns_rockets", "garrison", "bn1", "bn1_recon", "bn1_ad",
                                         "bn2"))

    def test_one_row_per_unit_type_and_group(self):
        keys = [(r.group, r.unit) for r in forces.ROWS if r.group != "fob"]
        self.assertEqual(len(keys), len(set(keys)))

    def test_places_camps_and_carriers(self):
        """Every row spawns at a named place of the map, in a side of the Soviet-player camps; a squad's carrier is a
        row of its own group."""
        for r in forces.ROWS:
            with self.subTest(row=(r.group, r.unit)):
                self.assertIn(r.spawn, POINTS)
                self.assertIn(r.camp, SOVIET_PLAYER_SIDES)
                if r.transport:
                    self.assertIn(r.transport, {x.unit for x in forces.ROWS if x.group == r.group})
        self.assertEqual({r.camp for r in forces.ROWS if r.group in ("garrison", "bn1", "bn1_recon", "bn1_ad", "bn2")},
                         {"NATO"})
        self.assertEqual({(r.camp, r.spawn) for r in forces.ROWS if r.group.startswith("guns")},
                         {("SovietAlly", "GUN_SPAWN")})
        self.assertEqual([(r.spawn, r.unit) for r in forces.ROWS if r.group == "fob"],
                         [("FOB_W", "FOB_SOV"), ("FOB_E", "FOB_SOV")])

    def test_the_knob_scales_nato_and_not_the_fixed_rows(self):
        """At 2x every NATO row doubles; the FOBs and the guns are fixed. At 0.1 no row drops below 1."""
        doubled = totals(scaled(forces.ROWS, 2.0))
        self.assertEqual({g: doubled[g] for g in ("fob", "guns_heavy", "guns_rockets")},
                         {"fob": 2, "guns_heavy": 6, "guns_rockets": 6})
        self.assertEqual({g: doubled[g] for g in ("garrison", "bn1", "bn2")}, {"garrison": 28, "bn1": 100, "bn2": 104})
        self.assertTrue(all(r.count >= 1 for r in scaled(forces.ROWS, 0.1)))

    def test_force_rows_is_the_group_at_the_knob(self):
        self.assertEqual([(r.unit, r.count) for r in forces.force_rows("guns_heavy")], [("2S7M_Malka_SOV", 6)])
        self.assertEqual(sum(r.count for r in forces.force_rows("garrison")), 14)


class Thresholds(unittest.TestCase):
    def test_design_shares_at_1x(self):
        """The village falls at 25 % of 14 left (3.5, half up: 4); a battalion is broken at 30 % of its tanks left
        (31 Abrams: 9.3, 9; 29 Leopards: 8.7, 9)."""
        self.assertEqual(forces.SHARES, {"fall": 0.25, "bn1": 0.30, "bn2": 0.30})
        self.assertEqual([forces.threshold(n) for n in ("fall", "bn1", "bn2")], [4, 9, 9])

    def test_the_bases(self):
        rows = scaled(forces.ROWS, 1.0)
        self.assertEqual(sum(r.count for r in rows if r.group == "bn1" and r.unit in forces.BN1_TANKS), 31)
        self.assertEqual(sum(r.count for r in rows if r.group == "bn2" and r.unit in forces.BN2_TANKS), 29)

    def test_scaled_and_own_shares(self):
        """At 2x the bases double (28, 62, 58); a difficulty's own share replaces the table's; a share is never past
        its base or 0."""
        rows = scaled(forces.ROWS, 2.0)
        self.assertEqual([forces.threshold(n, rows) for n in ("fall", "bn1", "bn2")], [7, 19, 17])
        self.assertEqual(forces.threshold("fall", share=0.35), 5)
        self.assertEqual(forces.threshold("fall", share=1.5), 14)
        self.assertEqual(forces.threshold("fall", share=0.01), 1)
        with self.assertRaises(KeyError):
            forces.threshold("bn3")


class Deck(unittest.TestCase):
    def test_top_up(self):
        """Only what the deck lacks, or holds too few of, in target order, the carrier kept; a met target adds
        nothing."""
        targets = (ForceRow("A", 4), ForceRow("B", 2, "C"), ForceRow("D", 3), ForceRow("E", 1))
        self.assertEqual(forces.top_up(targets, {"A": 1, "D": 3, "E": 9}), (ForceRow("A", 3), ForceRow("B", 2, "C")))
        self.assertEqual(forces.top_up(targets, {}), targets)
        self.assertEqual(forces.top_up(targets, {"A": 4, "B": 2, "D": 3, "E": 1}), ())

    def test_deck_units_counts_units_not_carriers(self):
        self.assertEqual(forces.deck_units([ForceRow("A", 2, "C"), ForceRow("A", 3), ForceRow("B", 1)]),
                         {"A": 5, "B": 1})

    def test_base_and_lists(self):
        """RJ's deck; the adds are targets cut down, never more; no lock is a start target (the lock never holds back
        what the assault needs); the reserve's Tunguskas join the locked type."""
        self.assertEqual(forces.DECK_BASE, RJ_PLAYER_DECK)
        targets = {c.unit: c for c in forces.START_TARGETS}
        for c in forces.START_ADDS:
            with self.subTest(unit=c.unit):
                self.assertLessEqual(c.count, targets[c.unit].count)
                self.assertEqual(c.transport, targets[c.unit].transport)
        self.assertFalse(set(forces.START_LOCKS) & set(targets))
        self.assertEqual(forces.START_LOCKS, ("Tunguska_2K22_SOV", "Su_24M_SOV", "Mi_24P_SOV"))
        self.assertIn("Tunguska_2K22_SOV", {c.unit for c in forces.RESERVE})

    def test_supply_is_the_shared_constant(self):
        """The supply is modkit.ops.profile's (not a copy): four Ural-4320 trucks and two Mi-8TZ supply helicopters, its
        own add beside START_ADDS (no unit of it is a start target)."""
        self.assertIs(forces.SUPPLY, SOVIET_PLAYER_SUPPLY)
        self.assertEqual(forces.SUPPLY, (ForceRow("Ural_4320_SOV", 4), ForceRow("Mi_8TZ_SOV", 2)))
        self.assertFalse({c.unit for c in forces.SUPPLY} & {c.unit for c in (*forces.START_TARGETS, *forces.RESERVE)})

    def test_design_counts(self):
        """Design 6.1's start targets (BMP-2s carrying 8 motor rifle squads, two Konkurs-M teams in BTR-80s, three
        command units, four Ka-29s) and its reserve (T-80U obr. 1989 x15 and the T-80U command tank, four more
        Konkurs-M teams, Ka-50 x4, ...)."""
        self.assertEqual(forces.deck_units(forces.START_TARGETS)["T80BV_SOV"], 10)
        self.assertEqual(sum(c.count for c in forces.START_TARGETS if "_CMD_" in c.unit), 3)
        self.assertIn(ForceRow("MotRifles_SOV", 8, "BMP_2_SOV"), forces.START_TARGETS)
        self.assertEqual((forces.ATGM_TEAM, forces.ATGM_CARRIER, forces.T80U_TANK),
                         ("ATteam_KonkursM_TTsko_SOV", "BTR_80_SOV", "T80U_Obr89_SOV"))
        self.assertIn(ForceRow(forces.ATGM_TEAM, 2, forces.ATGM_CARRIER), forces.START_TARGETS)
        self.assertEqual(forces.deck_units(forces.RESERVE),
                         {"T80U_Obr89_SOV": 15, "T80U_CMD_SOV": 1, "Tunguska_2K22_SOV": 2, "Osa_9K33M3_SOV": 2,
                          "Mi_24V_AT_SOV": 6, "Ka_50_SOV": 4, "Su_25T_SOV": 2, "Su_24M_clu_SOV": 2,
                          "BRDM_2_Konkurs_SOV": 6, "MotRifles_Metis_SOV": 8, "ATteam_KonkursM_TTsko_SOV": 4,
                          "2K12_KUB_SOV": 2})

    def test_every_infantry_card_rides_in_a_carrier(self):
        """The first play's fix: the engineers in MT-LBs, the scouts in UAZ-469s, the Metis teams in BMP-2s, the motor
        rifles in their BMP-2s as before, the Konkurs-M teams in BTR-80s wherever they are added; the Kubs bare, as
        every stock pack holds them."""
        cards = (*forces.START_TARGETS, *forces.START_ADDS, *forces.RESERVE)
        carriers = {c.unit: c.transport for c in cards}
        self.assertEqual({u: carriers[u] for u in ("MotRifles_SOV", "Engineers_Flam_SOV", "Scout_SOV",
                                                   "MotRifles_Metis_SOV", forces.ATGM_TEAM, "2K12_KUB_SOV")},
                         {"MotRifles_SOV": "BMP_2_SOV", "Engineers_Flam_SOV": "MTLB_transp_SOV",
                          "Scout_SOV": "UAZ_469_SOV", "MotRifles_Metis_SOV": "BMP_2_SOV",
                          forces.ATGM_TEAM: "BTR_80_SOV", "2K12_KUB_SOV": None})
        self.assertEqual({c.transport for c in cards if c.unit == forces.ATGM_TEAM}, {forces.ATGM_CARRIER})


@DECK_DATA
class StockDeck(unittest.TestCase):
    """RedJuggernaut's player deck, read from the stock decks: the pinned start cards are what it lacks or holds too few
    of, and every locked type is one of its own."""

    def setUp(self):
        self.packs = stock_deck(RJ_PLAYER_DECK)
        self.held = forces.deck_units(self.packs)

    def test_start_adds_are_rederived(self):
        self.assertEqual(forces.top_up(forces.START_TARGETS, self.held), forces.START_ADDS)

    def test_locks_are_rj_types(self):
        for unit in forces.START_LOCKS:
            self.assertGreaterEqual(self.held[unit], 1, unit)

    def test_rj_holds_what_the_adds_skip(self):
        """Why three targets add nothing, and the 2S1 only two (the stock counts behind START_ADDS)."""
        self.assertEqual({u: self.held[u] for u in ("T80BV_SOV", "BRM_1_SOV", "MTLB_Strela10_SOV", "2S1_Gvozdika_SOV")},
                         {"T80BV_SOV": 16, "BRM_1_SOV": 2, "MTLB_Strela10_SOV": 2, "2S1_Gvozdika_SOV": 2})

    def test_reader_knows_a_carried_pack(self):
        self.assertIn(ForceRow("DShV_SOV", 9, "Mi_8TV_non_arme_SOV"), self.packs)
        with self.assertRaises(LookupError):
            stock_deck("NO_SUCH_DECK")

    def test_command_units_are_every_cmd_card(self):
        """The fall's command units (design 5.1) are every *_CMD_* unit the player can field: RJ's, the start adds'
        and the reserve's."""
        cards = [p.unit for p in self.packs] + [c.unit for c in (*forces.START_ADDS, *forces.RESERVE)]
        self.assertEqual(sorted(forces.COMMAND_UNITS), sorted({u for u in cards if "_CMD_" in u}))


@DECK_DATA
@GAME
class StockSupply(unittest.TestCase):
    """Why the Soviet player's supply is added, re-checked on stock: RedJuggernaut's player deck (the stock decks) has
    no supply helicopter, and its only supply unit, the Ural-4320 truck, sits only in battlegroups 2 and 3's HQ groups
    (the two tank battalions); the supply added is a stock truck and a stock supply helicopter. Supply units are those
    the game's unit database gives a supply module [[soviet-player-camp]]."""

    def setUp(self):
        self.supply = supply_units()
        self.packs = stock_deck(RJ_PLAYER_DECK)
        self.groups = stock_deck_groups(RJ_PLAYER_DECK)

    def test_rj_has_no_supply_helicopter_and_trucks_only_in_the_tank_battalions(self):
        names = {p.unit for p in self.packs} | {p.transport for p in self.packs if p.transport}
        self.assertEqual(sorted(names & set(self.supply)), ["Ural_4320_SOV"])
        self.assertFalse(self.supply["Ural_4320_SOV"])                       # a truck: no supply helicopter at all
        supply_packs = {i for i, p in enumerate(self.packs) if p.unit in self.supply or p.transport in self.supply}
        held = {(k, name): set(packs) for k, group in enumerate(self.groups, 1) for name, packs in group
                if set(packs) & supply_packs}
        self.assertEqual(sorted(k for k, _ in held), [2, 3])                # battlegroups 2 and 3 only
        for (k, name), packs in held.items():
            with self.subTest(battlegroup=k, group=name):                    # each its HQ group, with a command tank
                self.assertTrue(any("_CMD_" in self.packs[i].unit for i in packs))
        self.assertEqual(len(self.groups), 5)

    def test_the_supply_added_is_stock_supply(self):
        """A Ural-4320 truck and an Mi-8TZ supply helicopter, both stock supply units."""
        self.assertEqual({c.unit: self.supply.get(c.unit) for c in forces.SUPPLY},
                         {"Ural_4320_SOV": False, "Mi_8TZ_SOV": True})


@GAME
class StockChoices(unittest.TestCase):
    """The deck's picks, re-derived from the game's unit database and division rules (game build 201602): the ATGM
    team is the Soviet ATGM infantry whose missile has the highest AP among the units a Soviet division's rule fields
    (the longer range on a tie), in a carrier that rule allows; the reserve's T-80U is the variant whose ATGM has 25
    AP."""

    @classmethod
    def setUpClass(cls):
        cls.units = unit_facts()
        cls.rules = {name: units for name, units in division_rules().items() if "_SOV_" in name}

    def test_the_atgm_team_fires_the_best_missile_a_soviet_division_fields(self):
        """Every Soviet infantry unit with a guided AT missile that a Soviet division fields, by its best (AP, range):
        the Konkurs-M team alone has the best, 23 AP at 2,625 GRU, and it is an AT team; no other has more than 20."""
        fielded = {unit for units in self.rules.values() for unit in units}
        atgm = {u: max(f.missiles) for u, f in self.units.items()
                if u in fielded and f.country == "SOV" and f.infantry and f.missiles}
        best = max(atgm.values())
        self.assertEqual(([u for u, m in atgm.items() if m == best], best), ([forces.ATGM_TEAM], (23, 2625.0)))
        self.assertEqual(self.units[forces.ATGM_TEAM].role, "AT")
        self.assertLessEqual(max(m for u, m in atgm.items() if u != forces.ATGM_TEAM)[0], 20)

    def test_its_carrier_is_the_armoured_one_its_division_allows(self):
        """Only the 27th Guards Motor Rifle Division fields the team, in a UAZ-469 or a BTR-80: the BTR-80 (a BMP, BTR or
        MT-LB, as the start's other squads ride)."""
        held = {name: units[forces.ATGM_TEAM] for name, units in self.rules.items() if forces.ATGM_TEAM in units}
        self.assertEqual(held, {"Descriptor_Deck_Division_SOV_27_Gds_Rifle_multi_Rule": ("UAZ_469_SOV", "BTR_80_SOV")})
        self.assertEqual(forces.ATGM_CARRIER, "BTR_80_SOV")

    def test_the_reserve_fields_the_25_ap_t80u(self):
        """Every T-80U variant's ATGM: only the obr. 1989 fires a 25 AP missile; no command variant does, so the T-80U
        command tank stays. The reserve holds no other T-80U tank."""
        t80u = {u: max(f.missiles)[0] for u, f in self.units.items() if u.startswith("T80U") and f.missiles}
        self.assertEqual(t80u, {"T80U_SOV": 21, "T80UD_SOV": 21, "T80U_CMD_SOV": 21, "T80U_Obr89_SOV": 25})
        self.assertEqual(t80u[forces.T80U_TANK], 25)
        self.assertEqual({c.unit for c in forces.RESERVE if c.unit.startswith("T80U")},
                         {forces.T80U_TANK, "T80U_CMD_SOV"})


@GAME
class Balance(unittest.TestCase):
    """Design 6.5's force ratios, by value (each unit's deck cost in the game's unit database; a transport card costs
    its unit and its carrier): the start's points 3:1 over the garrison; on Easy and Medium, the points given by the
    time each battalion is all in (battalion 1's last wave created; battalion 2 created, never before that) at least
    its value. The points given by a moment after the fall: the start, the grant and one income tick a minute. Hard
    sits below 1:1 against battalion 1 (the ruling lets it); the fires and the strike are not counted."""

    @classmethod
    def setUpClass(cls):
        cls.facts = unit_facts()

    def cost(self, cards) -> int:
        return sum(c.count * (self.facts[c.unit].cost + (self.facts[c.transport].cost if c.transport else 0))
                   for c in cards)

    @staticmethod
    def points_by(after_fall_s: float) -> int:
        return op.DEPLOY_POINTS + op.FALL_GRANT + int(after_fall_s // INCOME_TICK_S) * op.FALL_INCOME

    @staticmethod
    def bn1(level: int) -> tuple[list, float]:
        """Battalion 1's rows at `level` and when its last wave is created, in seconds after the fall."""
        waves = [t.wave for t in op.BN1_WAVES if t.team <= op.TEAMS[level]]
        return [row for w in waves for row in w.rows], op.PHASE2_S + max(w.offset for w in waves)

    def test_the_assault_is_three_to_one(self):
        garrison = forces.force_rows("garrison")
        self.assertGreaterEqual(op.DEPLOY_POINTS, 3 * self.cost(garrison))

    def test_each_battalion_is_met_on_easy_and_medium(self):
        bn2 = forces.force_rows("bn2")
        for level in (EASY, MEDIUM):
            rows, all_in = self.bn1(level)
            with self.subTest(level=level):
                self.assertGreaterEqual(self.points_by(all_in), self.cost(rows))
                self.assertGreaterEqual(self.points_by(all_in + op.BN2_GAP_S), self.cost(bn2))

    def test_the_reserve_holds_what_the_fall_buys(self):
        """The cards the fall unlocks and adds are worth at least the grant and Medium's income until battalion 1 is
        all in, so the fall's points buy the division's reserve, not only what is left of the start's deck."""
        unlocked = [c for c in gates.stock_deck_packs(RJ_PLAYER_DECK) if c.unit in forces.START_LOCKS]
        _, all_in = self.bn1(MEDIUM)
        self.assertGreaterEqual(self.cost([*unlocked, *forces.RESERVE]), self.points_by(all_in) - op.DEPLOY_POINTS)


@GAME
class Units(unittest.TestCase):
    def test_every_name_is_in_the_unit_database(self):
        """Every unit of the tables and the deck lists, carriers included, is a unit the game's database exports."""
        known = {name.removeprefix(gates.UNIT_PREFIX + "Descriptor_Unit_") for name in gates.unit_database()}
        names = {r.unit for r in forces.ROWS} | {r.transport for r in forces.ROWS if r.transport}
        for cards in (forces.START_TARGETS, forces.START_ADDS, forces.SUPPLY, forces.RESERVE):
            names |= {c.unit for c in cards} | {c.transport for c in cards if c.transport}
        names |= set(forces.START_LOCKS) | set(forces.COMMAND_UNITS) | set(forces.NATO_INFANTRY)
        self.assertEqual(sorted(names - known), [])


if __name__ == "__main__":
    unittest.main()
