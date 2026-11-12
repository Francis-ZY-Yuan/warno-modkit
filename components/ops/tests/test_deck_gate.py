"""Tests for an op-exported deck [[op-exported-deck]]: the deck data (modkit.ops.forces: Platoon, DeckPage,
deck_packs; its cards are modkit.ops.models.ForceRow), its writer and its page lock (modkit.ops.shapes: player_deck,
lock_page, with_deck; graph.pair; leveldesign.derived_deck_identifier), and the decks gate (modkit.ops.gates: check_decks and its parts) with the deck
names' lists in the tokens gate and the dictionary resources a build appends to MapConfiguration (modkit.ops.rekey).

`DeckData`, `Writer`, `Gate`, `Tokens` and `DumpRows` need no stock data: each gate rule fails a bad deck built for it
and passes a good one. `StockGate` holds the gate to the game's own decks, units and scripts (every stock deck passes
the game's load checks; every stock challenge script's SetDecks and page locks pass), and `StockResources` appends the
resources to Survivors' MapConfiguration; they skip without the extraction."""
from __future__ import annotations

import dataclasses
import os
import tempfile
import unittest

from modkit.core import dbg, ndfbin, paths, trad
from modkit.core.gates import CheckError
from modkit.ops import gates, rekey
from modkit.ops.bricks import g_cmp, unit_path
from modkit.ops.files import read_file
from modkit.ops.forces import DeckPage, Platoon, deck_packs
from modkit.ops.gates import (
    Carriage, DeckRules, StockDecks, check_decks, check_dump_diff, check_tokens, deck_load_violations,
    deck_rule_violations, deck_violations, read_decks, unit_carriage,
)
from modkit.ops.graph import Node, Str, build_graph, decode, encode, i32, loc, pair
from modkit.ops.items import mem_item
from modkit.ops.leveldesign import derived_deck_identifier
from modkit.ops.models import CampRow, ForceRow
from modkit.ops.profile import SURVIVORS
from modkit.ops.rekey import TXN, Rekey, def_path
from modkit.ops.shapes import Ctx, camp_nodes, lock_page, player_deck, setdeck_block, with_deck
from modkit.ops.strings import LANGS

S = "challenge_Test"
DIVISION = "Descriptor_Deck_Division_TEST_challenge"
ROWS = (CampRow("joueur", (), "OP_STOCK"), CampRow("ennemi", (("Alliance", 0x03, 1),), "OP_STOCK"))
STOCK = StockDecks({"OP_STOCK": 4}, DeckRules(5, 6, 3), frozenset({f"{gates.DIVISION_PREFIX}{DIVISION}"}), 1)
U = gates.UNIT_PREFIX + "Descriptor_Unit_"
CARRIAGE = {
    U + "Rifles": Carriage(frozenset({"Infanterie", "Crew"}), True, None),
    U + "Gun": Carriage(frozenset({"Canon", "Unite_transportable"}), True, None),
    U + "Truck": Carriage(frozenset({"Vehicule"}), False, frozenset({"Crew", "Unite_transportable"})),
    U + "Apc": Carriage(frozenset({"Vehicule"}), False, frozenset({"Crew"})),
    U + "Gunship": Carriage(frozenset({"Helo"}), False, None),
    U + "Tank": Carriage(frozenset({"Char"}), False, None),
}
GOOD = (
    DeckPage("pg_a", (Platoon("pl_a", (ForceRow("Tank", 3, xp=1), ForceRow("Rifles", 2, "Apc"))),
                      Platoon("pl_b", (ForceRow("Tank", 2, xp=1),)))),
    DeckPage("pg_b", (Platoon("pl_c", (ForceRow("Gun", 2, "Truck"), ForceRow("Rifles", 1, "Apc", xp=1))),)),
)


def ctx(rows=ROWS) -> Ctx:
    camps = camp_nodes(rows, {row.name: f"c_{row.name}" for row in rows})
    return Ctx(camps, {"Player": "joueur", "Enemy": "ennemi"}, "Player", [], S, "test-ns", "$/GDScript/T")


def script(pages=GOOD, rows=None, locks=(), identifier="T_ABC_Player", division=DIVISION, extra=()) -> bytes:
    """A GDScript of the SetDecks of `rows` (the player's on `identifier`), page locks `locks` on the player's camp,
    the deck of `pages` exported, and `extra` decks besides."""
    rows = rows if rows is not None else with_deck(ROWS, "joueur", identifier)
    c = ctx(rows)
    flag = c.int_var("flag")
    main = Node("TGDDescriptorSequential", [("SubActions", [*setdeck_block(c.camps, rows),
                                                            *(lock_page(c, k, g_cmp(flag, 1)) for k in locks)])])
    decks = [player_deck(f"$/GDScript/T/Deck{k}", ident, "u_name", division, p)
             for k, (ident, p) in enumerate(((identifier, pages), *extra))]
    return encode(build_graph([main], [*c.camps.values(), *decks, *c.variables.values()]), "GDScript")


def violations(raw: bytes, stock: StockDecks = STOCK) -> list[str]:
    nb, _, _ = decode(raw)
    return deck_violations(nb, S, stock, lambda: CARRIAGE)[1]


class DeckData(unittest.TestCase):
    def test_packs_are_one_per_key_summed(self):
        """One pack per (unit, carrier, experience), in first-use order, its count the sum over its platoons."""
        self.assertEqual(deck_packs(GOOD), (ForceRow("Tank", 5, None, xp=1), ForceRow("Rifles", 2, "Apc"),
                                            ForceRow("Gun", 2, "Truck"), ForceRow("Rifles", 1, "Apc", xp=1)))
        self.assertEqual(ForceRow("A", 1, "B", xp=2).key, ("A", "B", 2))

    def test_a_card_counts_one_or_more(self):
        with self.assertRaisesRegex(ValueError, r"pg/pl: A x0"):
            deck_packs([DeckPage("pg", (Platoon("pl", (ForceRow("A", 0),)),))])


class Writer(unittest.TestCase):
    def test_pair(self):
        """A (uint32 pack index, int32 units) NDF pair, as the game's decks hold it."""
        self.assertEqual(pair(3, 2), ndfbin.Value(0x22, (ndfbin.Value(0x03, 3), ndfbin.Value(0x02, 2))))

    def test_player_deck_in_stock_shape(self):
        """The game's deck shape: DeckPackList, DeckCombatGroupList, DeckName, DeckIdentifier, DeckDivision; packs
        inline (ExperienceLevel left out at 0, the carrier as TransporterDescriptor), pages and platoons named by
        token, each card a (pack index, count) pair; it reads back as written."""
        nd = player_deck("$/GDScript/T/Deck", "T_X_Player", "u_name", DIVISION, GOOD)
        self.assertEqual([k for k, _ in nd.props],
                         ["DeckPackList", "DeckCombatGroupList", "DeckName", "DeckIdentifier", "DeckDivision"])
        packs = dict(nd.props)["DeckPackList"]
        self.assertEqual([[k for k, _ in p.props] for p in packs[:2]],
                         [["ExperienceLevel", "UnitDescriptor", "Number"],
                          ["UnitDescriptor", "TransporterDescriptor", "Number"]])
        self.assertEqual(dict(packs[1].props)["TransporterDescriptor"].path, unit_path("Apc"))
        page = dict(nd.props)["DeckCombatGroupList"][0]
        self.assertEqual([k for k, _ in page.props], ["Name", "SmartGroupList"])
        platoon = dict(page.props)["SmartGroupList"][0]
        self.assertEqual(dict(platoon.props)["PackIndexUnitNumberList"], [pair(0, 3), pair(1, 2)])
        (deck,) = read_decks(decode(encode(build_graph([], [nd]), "deck"))[0])
        self.assertEqual((deck.where, deck.identifier, deck.division), ("$/GDScript/T/Deck", "T_X_Player",
                                                                        gates.DIVISION_PREFIX + DIVISION))
        self.assertEqual(deck.pages, ((((0, 3), (1, 2)), ((0, 2),)), (((2, 2), (3, 1)),)))
        self.assertEqual([p.number for p in deck.packs], [5, 2, 2, 1])

    def test_lock_page_in_stock_order(self):
        """Competition[LockCombatGroup(Camp, [TGDVariableInteger index]), WaitCondition] (RunningTheGauntlet #178)."""
        c = ctx()
        race = lock_page(c, 3, g_cmp(c.int_var("flag"), 1))
        lock, wait = dict(race.props)["SubActions"]
        self.assertEqual((race.cls, lock.cls, wait.cls), ("TGDDescriptorCompetition", gates.LOCK_PAGE,
                                                          "TGDDescriptorWaitCondition"))
        self.assertIs(dict(lock.props)["Camp"], c.camps["joueur"])
        (index,) = dict(lock.props)["CombatGroupIndexes"]
        self.assertEqual((index.cls, index.props, index.export), ("TGDVariableInteger", [("Value", i32(3))], None))

    def test_with_deck(self):
        """One camp's SetDeck replaced; the other rows are the same objects."""
        rows = with_deck(ROWS, "joueur", "T_X")
        self.assertEqual(rows[0], CampRow("joueur", (), "T_X"))
        self.assertIs(rows[1], ROWS[1])
        with self.assertRaisesRegex(CheckError, "no camp row nobody"):
            with_deck(ROWS, "nobody", "T_X")

    def test_derived_identifier(self):
        """'<prefix>_<12 hex>_<name>', from the scenario, the namespace and the name, never the scenario id."""
        a = derived_deck_identifier(S, "ns", "TS", "Player")
        self.assertRegex(a, r"^TS_[0-9A-F]{12}_Player$")
        self.assertEqual(a, derived_deck_identifier(S, "ns", "TS", "Player"))
        self.assertNotEqual(a, derived_deck_identifier(S, "other", "TS", "Player"))
        self.assertNotEqual(a, derived_deck_identifier("challenge_Other", "ns", "TS", "Player"))
        with self.assertRaisesRegex(CheckError, "letters and digits only"):
            derived_deck_identifier(S, "ns", "T_S", "Player")


class Gate(unittest.TestCase):
    """Each rule of the decks gate fails a deck built to break it; the good deck passes."""

    def test_a_good_deck_passes(self):
        raw = script(locks=(1,))
        self.assertEqual(violations(raw), [])
        self.assertEqual(check_decks(raw, S, STOCK, lambda: CARRIAGE), {"setdecks": 2, "decks": 1, "locks": 1})

    def test_a_script_without_decks_reads_nothing(self):
        """No SetDeck, deck or lock: the gate reads no stock file."""
        raw = encode(build_graph([Node("TGDDescriptorWaitDuration", [("Duree", i32(1))])], []), "GDScript")
        self.assertEqual(check_decks(raw, S, None, lambda: self.fail("read the units")),
                         {"setdecks": 0, "decks": 0, "locks": 0})

    def test_pack_index_past_the_packs(self):
        """The game's first load check, on a raw platoon that names pack 9 of 4."""
        deck = gates.DeckRead("d", "T_X", None, (gates.DeckPack(U + "Tank", None, 0, 1),), ((((9, 1),),),))
        self.assertEqual(deck_load_violations(deck, CARRIAGE),
                         ["d: page 0 platoon 0 names pack 9, but the deck has 1 packs (the game refuses the deck at "
                          "load)"])

    def test_a_carrier_with_no_unit(self):
        deck = gates.DeckRead("d", "T_X", None, (gates.DeckPack(None, U + "Apc", 0, 1),), ((((0, 1),),),))
        self.assertIn("a carrier and no unit (the game crashes on it)", deck_load_violations(deck, CARRIAGE)[0])

    def test_the_transport_checks(self):
        """A unit that cannot be carried, a carrier that is no transport (a gunship), a carrier that takes none of the
        unit's tags, and a unit the game's unit file lacks."""
        cases = {("Tank", "Apc"): "the unit cannot be carried",
                 ("Rifles", "Gunship"): "the carrier is not a transport",
                 ("Gun", "Apc"): "the unit has none of the tags the carrier takes (Crew; the game refuses the deck)",
                 ("Nobody", "Apc"): "the unit is not in the game's unit file"}
        for (unit, carrier), message in cases.items():
            with self.subTest(unit=unit, carrier=carrier):
                pages = (DeckPage("pg", (Platoon("pl", (ForceRow(unit, 1, carrier),)),)),)
                (bad,) = violations(script(pages))
                self.assertIn(message, bad)

    def test_a_unit_sharing_one_tag_rides(self):
        """The carrier takes the unit when they share any one tag (Truck takes Crew and Unite_transportable)."""
        pages = (DeckPage("pg", (Platoon("pl", (ForceRow("Rifles", 1, "Truck"), ForceRow("Gun", 1, "Truck"))),)),)
        self.assertEqual(violations(script(pages)), [])

    def test_the_group_rules(self):
        """6 pages of 5 allowed; 7 platoons of 6; 4 packs in a platoon of 3."""
        page = DeckPage("pg", (Platoon("pl", (ForceRow("Tank", 1),)),))
        self.assertIn("6 pages, a Challenge's group rules allow 5", violations(script((page,) * 6))[0])
        wide = DeckPage("pg", (Platoon("pl", (ForceRow("Tank", 1),)),) * 7)
        self.assertIn("page 0 has 7 platoons, the group rules allow 6", violations(script((wide,)))[0])
        full = DeckPage("pg", (Platoon("pl", tuple(ForceRow("Tank", 1, xp=k) for k in range(4))),))
        self.assertIn("page 0 platoon 0 names 4 packs, the group rules allow 3", violations(script((full,)))[0])

    def test_the_identifier(self):
        """A stock deck's identifier stops the load; one holding the scenario id fails the references gate; none
        cannot be named; two decks of the script may not share one."""
        rows = with_deck(ROWS, "joueur", "OP_STOCK")
        self.assertIn("DeckIdentifier OP_STOCK is a stock deck's", violations(script(rows=rows,
                                                                                     identifier="OP_STOCK"))[0])
        self.assertIn("holds the scenario id", violations(script(identifier=f"T_{S}"))[0])
        self.assertIn("two decks of the script are identified T_ABC_Player",
                      violations(script(extra=(("T_ABC_Player", GOOD),)))[0])
        nb, _, _ = decode(script())
        (deck,) = read_decks(nb)
        self.assertIn("no DeckIdentifier", deck_rule_violations(deck._replace(identifier=None), STOCK, S)[0])

    def test_the_division(self):
        self.assertIn("DeckDivision $/GFX/Division/Nope is not a division of the game's",
                      violations(script(division="Nope"))[0])

    def test_every_pack_drawn_exactly(self):
        """A pack no platoon draws (an orphan) and packs over- or under-drawn fail; RedJuggernaut's deck has all three,
        so the rule is the op's, not the game's."""
        nb, _, _ = decode(script())
        (deck,) = read_decks(nb)
        orphan = deck._replace(packs=(*deck.packs, gates.DeckPack(U + "Tank", None, 2, 3)))
        self.assertEqual(deck_rule_violations(orphan, STOCK, S),
                         ["$/GDScript/T/Deck0: pack 4 (Tank x3) is drawn 0 times by its platoons: every card belongs "
                          "on a page, once (an orphan pack)"])
        over = deck._replace(pages=(*deck.pages, (((0, 1),),)))
        self.assertIn("pack 0 (Tank x5) is drawn 6 times", deck_rule_violations(over, STOCK, S)[0])

    def test_setdeck_names_a_registered_deck(self):
        """A SetDeck on an identifier neither stock nor exported fails (the mission fails at its launch)."""
        rows = (CampRow("joueur", (), "T_ABC_Player"), CampRow("ennemi", (("Alliance", 0x03, 1),), "OP_GONE"))
        self.assertEqual(violations(script(rows=rows)),
                         ["SetDeck of $/GDScript/RootDescriptor/ennemi names OP_GONE, which is no stock deck and no "
                          "deck the script exports: the mission fails at its launch (a GDBrick error naming "
                          "DeckIdentifier)"])

    def test_page_locks_in_range(self):
        """Index 2 of a 2-page deck locks nothing; the same on a stock deck of 4 pages passes."""
        self.assertIn("locks page [2] of T_ABC_Player, which has 2 pages (0-based)", violations(script(locks=(2,)))[0])
        rows = with_deck(ROWS, "joueur", "OP_STOCK")
        self.assertEqual(violations(script(rows=rows, locks=(3,))), [])

    def test_a_lock_needs_a_setdeck(self):
        c = ctx()
        lock = lock_page(c, 0, g_cmp(c.int_var("flag"), 1))
        raw = encode(build_graph([lock], [*c.camps.values(), *c.variables.values()]), "GDScript")
        self.assertEqual(violations(raw), ["LockCombatGroup of $/GDScript/RootDescriptor/joueur: no SetDeck gives the "
                                           "camp a deck to lock pages of"])

    def test_no_key_on_a_locked_page_and_an_open_one(self):
        """The game pools cards by (unit, carrier, experience): page 1's Rifles in Apc at experience 0 would also be
        sold by page 0 (bad); at experience 1, GOOD's, the key is page 1's own (good)."""
        bad = (GOOD[0], DeckPage("pg_b", (Platoon("pl_c", (ForceRow("Rifles", 2, "Apc"),)),)))
        (line,) = violations(script(bad, locks=(1,)))
        self.assertIn("Rifles in Apc at experience 0 is on a locked page and an open one", line)
        self.assertEqual(violations(script(GOOD, locks=(1,))), [])

    def test_the_gate_reports_them_all(self):
        with self.assertRaisesRegex(CheckError, r"^2 deck rules broken: "):
            check_decks(script(division="Nope", locks=(5,)), S, STOCK, lambda: CARRIAGE)


def dictionary_items(names: dict[str, dict[str, str]], scenario: str = S, langs=LANGS) -> list:
    return [mem_item("Assets", f"Localisation/{scenario}/{name}-{lang}.dic", trad.build_dic(rows), "generate", "t")
            for name, rows in names.items() for lang in langs]


def map_configuration(*resources: tuple[str, str]) -> bytes:
    """A MapConfiguration of one SCENARIO_DEFINITION token and a dictionary resource per (list, name)."""
    info = Node("TChallengeMapInfo", [("Name", loc("m_name"))])
    res = [Node(rekey.DICO_RESOURCE, [("DicoToken", loc(lst)), ("FileName", Str(rekey.dico_file(S, name), 0x1C))])
           for lst, name in resources]
    return encode(build_graph([info, *res], []), "MapConfiguration")


class Tokens(unittest.TestCase):
    """A deck's names resolve in the game's lists: its own (declared stock tokens) or a file appended to the list."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.ingame = os.path.join(self.tmp.name, "INTERFACE_INGAME-{lang}.dic")
        for lang in LANGS:
            with open(self.ingame.format(lang=lang), "wb") as fh:
                fh.write(trad.build_dic({"BTN_OK": "OK"}))
        self.scenario = dictionary_items({"SCENARIO_DEFINITION": {"m_name": "x"},
                                          "Scripting/Dialog": {"m_other": "x"},
                                          "Scripting/Localization": {"m_other": "x"}})

    def tearDown(self):
        self.tmp.cleanup()

    def items(self, resources=(), dictionaries=None, pages=GOOD) -> list:
        gd = player_deck("$/GDScript/T/Deck", "T_X", "u_name", DIVISION, pages)
        return [mem_item("Definition", def_path("GDScript", TXN, S), encode(build_graph([], [gd]), "GDScript"),
                         "generate", "t"),
                mem_item("Definition", def_path("MapConfiguration", TXN, S), map_configuration(*resources), "rekey",
                         "t"),
                *self.scenario, *dictionary_items(dictionaries or {})]

    def check(self, items, declared):
        return check_tokens(items, S, LANGS, global_tokens=(), ingame_dic=self.ingame, list_tokens_declared=declared)

    def test_declared_stock_tokens_pass(self):
        """Every name a stock token of its list: 1 deck name, 2 page names, 3 platoon names."""
        declared = {"UNITS": ("u_name",), "COMPANIES": ("pg_a", "pg_b"), "PLATOONS": ("pl_a", "pl_b", "pl_c")}
        self.assertEqual(self.check(self.items(), declared), (7, 0, 6))

    def test_appended_dictionaries_pass(self):
        """Page and platoon names in files MapConfiguration appends to COMPANIES and PLATOONS, shipped per language."""
        items = self.items((("COMPANIES", "DECK_C"), ("PLATOONS", "DECK_P")),
                           {"DECK_C": {"pg_a": "A", "pg_b": "B"}, "DECK_P": {"pl_a": "a", "pl_b": "b", "pl_c": "c"}})
        self.assertEqual(self.check(items, {"UNITS": ("u_name",)}), (7, 0, 6))

    def test_a_name_in_the_wrong_list_fails(self):
        """A platoon name in the COMPANIES file: the game looks it up in PLATOONS, where no file holds it."""
        items = self.items((("COMPANIES", "DECK_C"), ("PLATOONS", "DECK_P")),
                           {"DECK_C": {"pg_a": "A", "pg_b": "B", "pl_c": "c"}, "DECK_P": {"pl_a": "a", "pl_b": "b"}})
        with self.assertRaisesRegex(CheckError, r"deck name tokens missing from the game's PLATOONS list in DEV: "
                                                r"\['pl_c'\]"):
            self.check(items, {"UNITS": ("u_name",)})

    def test_the_scenario_dictionaries_do_not_count(self):
        """A page name in the scenario's own Localization dictionary: not a COMPANIES file, so it fails."""
        self.scenario = dictionary_items({"SCENARIO_DEFINITION": {"m_name": "x"}, "Scripting/Dialog": {"m": "x"},
                                          "Scripting/Localization": {"pg_a": "x", "pg_b": "x"}})
        with self.assertRaisesRegex(CheckError, r"missing from the game's COMPANIES list in DEV: \['pg_a', 'pg_b'\]"):
            self.check(self.items(), {"UNITS": ("u_name",), "PLATOONS": ("pl_a", "pl_b", "pl_c")})

    def test_an_appended_file_must_ship_in_every_language(self):
        items = self.items((("COMPANIES", "DECK_C"),), {})
        items += dictionary_items({"DECK_C": {"pg_a": "A", "pg_b": "B"}}, langs=[lang for lang in LANGS if lang != "SC"])
        with self.assertRaisesRegex(CheckError, r"appends DECK_C\.csv to the game's COMPANIES list, but DECK_C-SC\.dic "
                                                r"is not shipped"):
            self.check(items, {"UNITS": ("u_name",), "PLATOONS": ("pl_a", "pl_b", "pl_c")})

    def test_only_known_lists(self):
        with self.assertRaisesRegex(CheckError, r"declared stock tokens for \['MAPS'\]"):
            self.check(self.items(), {"MAPS": ("x",)})

    def test_appended_dictionaries_are_read_from_the_resources(self):
        nb, _, _ = decode(map_configuration(("COMPANIES", "DECK_C"), ("PLATOONS", "DECK_P")))
        self.assertEqual(gates.appended_dictionaries(nb, S), [("COMPANIES", "DECK_C"), ("PLATOONS", "DECK_P")])
        self.assertEqual(gates.appended_dictionaries(nb, "challenge_Other"), [])


class DumpRows(unittest.TestCase):
    """The dump gate takes appended lines only as the rows name them."""

    def item(self, raw: bytes, stock: bytes):
        return mem_item("Definition", def_path("MapConfiguration", TXN, S), raw, "rekey", "t", stock)

    def test_appended_lines(self):
        rows = rekey.dico_rows(S, (("COMPANIES", "DECK_C"),))
        stock = map_configuration(("MAPS", "SCENARIO_DEFINITION"))
        nb, _, _ = decode(stock)
        rekey.append_dico_resources(nb, S, (("COMPANIES", "DECK_C"),))
        report, fired = check_dump_diff(self.item(encode(nb, "m"), stock), rows)
        self.assertEqual(fired, {"MapConfiguration +1 dictionary resources: counts", "dictionary DECK_C -> COMPANIES"})
        self.assertIn('    +FileName = <path> "ScenariosData:/challenge_Test/DECK_C.csv"', report)

    def test_unexplained_appended_lines_fail(self):
        """A resource appended to PLATOONS where the rows name COMPANIES; and appended lines no row names."""
        stock = map_configuration(("MAPS", "SCENARIO_DEFINITION"))
        nb, _, _ = decode(stock)
        rekey.append_dico_resources(nb, S, (("PLATOONS", "DECK_C"),))
        with self.assertRaisesRegex(CheckError, r"unexplained appended line \(dictionary DECK_C -> COMPANIES\)"):
            check_dump_diff(self.item(encode(nb, "m"), stock), rekey.dico_rows(S, (("COMPANIES", "DECK_C"),)))
        with self.assertRaisesRegex(CheckError, r"dump has \d+ lines, stock \d+$"):
            check_dump_diff(self.item(encode(nb, "m"), stock), [])

    def test_the_template_needs_its_own_resource(self):
        nb, _, _ = decode(encode(build_graph([Node("TChallengeMapInfo", [("Name", loc("m"))])], []), "m"))
        with self.assertRaisesRegex(CheckError, "0 TLocalisationDicoResource objects, expected the template's one"):
            rekey.append_dico_resources(nb, S, (("COMPANIES", "DECK_C"),))


def extracted(rel: str) -> str:
    return os.path.join(str(paths.extracted_root()), *rel.split("/"))


@paths.skip_unless_extracted(*gates.DECK_FILE.split("/"))
@paths.skip_unless_extracted(*gates.UNIT_FILE.split("/"))
class StockGate(unittest.TestCase):
    """The decks gate on the game's own data (game build 210942)."""

    @classmethod
    def setUpClass(cls):
        cls.stock = gates.stock_decks()
        cls.carriage = gates.stock_carriage()
        cls.decks = read_decks(decode(read_file(extracted(gates.DECK_FILE)))[0])

    def test_the_stock_facts(self):
        """2,486 decks, 2,409 of them identified; a Challenge's rules are 5 pages, 6 platoons and 3 packs; the Ka-29
        carries nothing, an MT-LB command vehicle and a BMP-2 are there, and the BMP-2 carries Crew, which motor rifles
        have."""
        self.assertEqual((self.stock.decks, len(self.stock.pages)), (2486, 2409))
        self.assertEqual(self.stock.rules, DeckRules(5, 6, 3))
        self.assertEqual(self.stock.pages["OP_BASE_RJ_Player"], 5)
        self.assertIn(gates.DIVISION_PREFIX + "Descriptor_Deck_Division_SOV_79_Gds_Tank_challenge",
                      self.stock.divisions)
        ka29, bmp2, rifles = (self.carriage[U + name] for name in ("Ka_29_SOV", "BMP_2_SOV", "MotRifles_SOV"))
        self.assertIsNone(ka29.carries)
        self.assertEqual(bmp2.carries, frozenset({"Crew"}))
        self.assertTrue(rifles.transportable and "Crew" in rifles.tags)
        self.assertIn(U + "MTLB_CMD_SOV", self.carriage)

    def test_every_stock_deck_passes_the_load_checks(self):
        """The game's 2,486 decks pass the four load checks the gate models (2,873 of their 5,775 packs carried)."""
        bad = [v for d in self.decks for v in deck_load_violations(d, self.carriage)]
        self.assertEqual(bad, [])
        nb, _, _ = decode(read_file(extracted(gates.DECK_FILE)))
        packs = [{nb.pname(pi) for pi, _ in ob.props} for ob in nb.objects if nb.cname(ob.cls) == gates.PACK]
        self.assertEqual((len(packs), sum("TransporterDescriptor" in p for p in packs)), (5775, 2873))

    def test_the_operation_decks_keep_the_group_rules(self):
        """The 17 Operation decks with pages keep a Challenge's group rules and name a division of the game's; most
        draw their packs unevenly, which the op's rule refuses (RedJuggernaut's among them)."""
        ops = [d for d in self.decks if d.pages and "_challenge_" in d.where]
        self.assertEqual(len(ops), 17)
        uneven = 0
        for d in ops:
            lines = deck_rule_violations(d._replace(identifier="T_X"), self.stock, S)
            with self.subTest(deck=d.identifier):
                self.assertEqual([v for v in lines if "is drawn" not in v], [])
            uneven += bool(lines)
        self.assertEqual(uneven, 16)

    def test_a_ka29_carrier_fails(self):
        """The bad build of the brief: motor rifles in a Ka-29 (no transporter module) fail the game's check."""
        deck = gates.DeckRead("d", "T_X", None, (gates.DeckPack(U + "MotRifles_SOV", U + "Ka_29_SOV", 0, 2),),
                              ((((0, 2),),),))
        self.assertEqual(deck_load_violations(deck, self.carriage),
                         ["d: pack 0 (MotRifles_SOV in Ka_29_SOV): the carrier is not a transport (no transporter "
                          "module; the game refuses the deck)"])

    def test_every_stock_script_passes(self):
        """Every SetDeck of the stock challenge scripts names a stock deck, and their three page locks (Marauders' and
        RunningTheGauntlet's) are in range of the locked camp's deck."""
        pattern = extracted("scenarios")
        found = 0
        for name in sorted(os.listdir(pattern)):
            path = os.path.join(pattern, name, "NDF", "Scenarios", name, "GDScript.txn")
            if not name.startswith("challenge_") or not os.path.isfile(path):
                continue
            counts, bad = deck_violations(decode(read_file(path))[0], name, self.stock, gates.stock_carriage)
            with self.subTest(scenario=name):
                self.assertEqual(bad, [])
            found += counts["locks"]
        self.assertEqual(found, 3)

    def test_unit_carriage_reads_the_modules(self):
        """The reader on a unit file of three units: tags, a transportable module, a transporter module."""
        tags = Node("TTagsModuleDescriptor", [("TagSet", [Str("Crew"), Str("Infanterie")])])
        units = [Node("TEntityDescriptor", [("ModulesDescriptors", mods)], export=f"{U}{name}")
                 for name, mods in (("A", [tags, Node("TTransportableModuleDescriptor")]),
                                    ("B", [Node("TTransporterModuleDescriptor", [("TransportableTagSet",
                                                                                  [Str("Crew")])])]),
                                    ("C", []))]
        got = unit_carriage(decode(encode(build_graph([], units), "units"))[0])
        self.assertEqual(got, {U + "A": Carriage(frozenset({"Crew", "Infanterie"}), True, None),
                               U + "B": Carriage(frozenset(), False, frozenset({"Crew"})),
                               U + "C": Carriage(frozenset(), False, None)})

    def test_the_deck_file_is_a_stock_class_source(self):
        """The deck classes are classes the game's build has (gate 5)."""
        self.assertIn(gates.DECK_FILE, gates.STOCK_CLASS_SOURCES)
        self.assertLessEqual({"TDeckDescriptor", "TDeckPackDescriptor", "TDeckCombatGroupDescriptor",
                              "TDeckSmartGroupDescriptor"}, gates.stock_classes().classes)


@paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
class StockResources(unittest.TestCase):
    """The deck dictionaries' resources appended to Survivors' MapConfiguration, as a clone's build appends them."""

    def setUp(self):
        folder = os.path.join(SURVIVORS.path("definition"), "NDF", "Scenarios", SURVIVORS.source)
        self.txn = read_file(os.path.join(folder, "MapConfiguration.txn"))
        self.dbg = read_file(os.path.join(folder, "MapConfiguration.dbg"))
        renames = {f"op13_{k}": f"t_{k}" for k in ("name", "order", "headr", "cname", "recap", "vic", "def")}
        self.rk = Rekey(SURVIVORS.source, S, SURVIVORS.guid, b"\x01" * 16, renames, SURVIVORS.token_prefix, (), {},
                        {}, {}, ("MapConfiguration",), (("COMPANIES", "DECK_C"), ("PLATOONS", "DECK_P")))

    def test_rekeyed_with_two_resources(self):
        """Two resources after the template's MAPS one, in its shape; the .dbg gains a line each on the lines after
        the template's resource; every changed and appended line is a dump row's."""
        raw = rekey.rekey_definition(self.txn, "MapConfiguration", self.rk)
        nb, _, _ = decode(raw)
        self.assertEqual(gates.appended_dictionaries(nb, S),
                         [("MAPS", "SCENARIO_DEFINITION"), ("COMPANIES", "DECK_C"), ("PLATOONS", "DECK_P")])
        self.assertEqual(nb.topo, [0, 5, 6, 7])
        new_dbg = rekey.rekey_dbg(self.dbg, "MapConfiguration", self.rk, len(nb.objects))
        lines = dbg.read(new_dbg)
        self.assertEqual([(ln.source, ln.line) for ln in lines[-3:]],
                         [(f"ScenariosData:/{S}/MapPack.ndf", n) for n in (51, 52, 53)])
        rows = rekey.dump_rows(self.rk)
        fired = set()
        for path, new, old in ((def_path("MapConfiguration", TXN, S), raw, self.txn),
                               (def_path("MapConfiguration", "dbg", S), new_dbg, self.dbg)):
            fired |= check_dump_diff(mem_item("Definition", path, new, "rekey", "t", old), rows)[1]
        self.assertTrue({r.label for r in rows if "dictionary" in r.label} <= fired)

    def test_without_resources_nothing_changes(self):
        """No resource asked: the bytes are what they were before the feature."""
        plain = dataclasses.replace(self.rk, dico_resources=())
        self.assertEqual(len(decode(rekey.rekey_definition(self.txn, "MapConfiguration", plain))[0].objects), 6)
        self.assertNotIn("dictionary", " ".join(r.label for r in rekey.dump_rows(plain)))


if __name__ == "__main__":
    unittest.main()
