"""Tests for the co-install check (modkit.ops.coinstall): what every Operation must keep unique across the mods a
player runs at once [[check-against-every-active-mod]].

`Clashes`, `Tokens`, `Which` and `Cli` run on synthetic mods (toolkit-made MapConfigurations and dictionaries in
temporary mods and Workshop folders; no game data), with a synthetic stock. `Stock` holds the stock Operations to
the check, and `Builds` proves it both ways on real builds of the empty probe: two Operations on one menu order fail,
the derived order passes. They skip without the extraction or the game folder.
"""
from __future__ import annotations

import contextlib
import dataclasses
import hashlib
import io
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from probe_support import OUT_ROOT, quiet_build
from modkit.core import edat, paths, trad
from modkit.core.ndfbin import Value
from modkit.ops import coinstall
from modkit.ops.gates import MENU_PACK, StockOperation, stock_operations
from modkit.ops.graph import Imp, Node, build_graph, encode, u32
from modkit.ops.leveldesign import derived_menu_order
from modkit.ops.rekey import TXN, def_path
from probes import empty
from probes import profile as probe_profile

GUID_A, GUID_B, GUID_STOCK = bytes(range(16)), bytes(range(1, 17)), bytes(range(2, 18))
STOCK = (StockOperation("challenge_Stock", 130, GUID_STOCK),)
SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")


def map_config(order: int | None, guid: bytes, pack: str = MENU_PACK) -> bytes:
    """A MapConfiguration-like file: one TChallengeMapInfo in ChapterPack `pack` with `guid` and `order` (None: no
    OrderToChainMission)."""
    props = [("GUID", Value(0x1A, guid)), ("ChapterPack", Imp(pack))]
    props += [("OrderToChainMission", u32(order))] if order is not None else []
    return encode(build_graph([Node("TChallengeMapInfo", props)], []), "MapConfiguration")


def write_mod(folder: Path, scenario: str, order: int | None, guid: bytes, tokens: tuple[str, ...] = (),
              name: str | None = None, mod_id: int = 0, clusters: bool = False, old_layout: bool = False) -> Path:
    """A mod folder: its Config.ini (Name, ID, and a cluster line under [Config] when `clusters`), a Definition pack
    holding the scenario's MapConfiguration (NDF/Scenarios/<scenario>/MapConfiguration.txn, build 210942's layout;
    `old_layout`: NDF/Scenarios/MapConfiguration/<scenario>.ndfbin, build 201602's) and an Assets pack holding one
    dictionary of `tokens`."""
    (folder / "Scenarios").mkdir(parents=True)
    (folder / "Config.ini").write_text(f"[Properties]\nName = {name or folder.name}\nID = {mod_id}\n\n[Config]\n"
                                       + ("GFX/Unit=0123456789abcdef0123456789abcdef\n" if clusters else ""),
                                       encoding="utf-8")
    inner = (f"NDF/Scenarios/MapConfiguration/{scenario}.ndfbin" if old_layout
             else def_path("MapConfiguration", TXN, scenario))
    edat.write_edat(str(folder / "Scenarios" / f"{scenario}_Definition.dat"), [(inner, map_config(order, guid))])
    edat.write_edat(str(folder / "Scenarios" / f"{scenario}_Assets.dat"),
                    [(f"Localisation/{scenario}/Scripting/Localization-US.dic",
                      trad.build_dic({t: t.upper() for t in tokens} or {"x_none": "x"}))])
    return folder


def tree(*roots: Path) -> dict[str, str]:
    """{path: SHA-256} of every file under `roots`: a read-only run leaves it unchanged."""
    return {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for r in roots if r.exists()
            for p in sorted(r.rglob("*")) if p.is_file()}


class Base(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.root = self.tmp / "mod"
        self.workshop = self.tmp / "content" / "1611600"
        self.root.mkdir(parents=True)
        self.workshop.mkdir(parents=True)

    def mod(self, *args, **kw) -> coinstall.Mod:
        folder = write_mod(*args, **kw)
        return coinstall.read_mod(folder, "workshop" if folder.parent == self.workshop else "local")

    def activate(self, *entries: str) -> None:
        (self.root / "Config.ini").write_text(f"[Config]\nActivatedMods = {'|'.join(entries)}|;comment\n",
                                              encoding="utf-8")


class Clashes(Base):
    def test_read_mod(self):
        a = self.mod(self.root / "A", "challenge_A", 1001, GUID_A, ("aa_name",))
        self.assertEqual((a.label, a.kind, a.scenarios), ("A (local)", "local", {"challenge_A"}))
        self.assertEqual(a.menus, [coinstall.Menu("challenge_A", 1001, GUID_A)])
        self.assertEqual(set(a.keys) - coinstall.IGNORED_KEYS, {trad.token_key("aa_name")})
        self.assertIn(trad.CHARSET_KEY, a.keys)
        self.assertEqual(a.warnings, [])

    def test_a_build_201602_map_configuration_warns_and_lists_no_menu(self):
        """A MapConfiguration in build 201602's layout is one build 210942 never reads: a warning, and no menu entry
        (so it holds no menu order or GUID against the others)."""
        old = self.mod(self.root / "Old", "challenge_O", 1001, GUID_A, old_layout=True)
        self.assertEqual(old.menus, [])
        self.assertEqual(old.scenarios, {"challenge_O"})
        self.assertEqual(old.warnings, [
            "Old (local): challenge_O_Definition.dat:NDF/Scenarios/MapConfiguration/challenge_O.ndfbin is a build "
            "201602 MapConfiguration, which this game build never reads: its Operation is not listed until the mod "
            "is rebuilt"])
        a = self.mod(self.root / "A", "challenge_A", 1001, GUID_A)
        self.assertEqual(coinstall.clashes([old, a], STOCK), [])

    def test_one_menu_order_fails_naming_both_and_the_value(self):
        a = self.mod(self.root / "A", "challenge_A", 1001, GUID_A)
        b = self.mod(self.root / "B", "challenge_B", 1001, GUID_B)
        self.assertEqual(coinstall.clashes([a, b], STOCK),
                         ["OrderToChainMission 1001 is held by challenge_A of A (local) and challenge_B of B (local)"])

    def test_order_zero_or_none_never_clashes(self):
        """0 means no order: two mods on 0, or without the property, do not clash."""
        a = self.mod(self.root / "A", "challenge_A", 0, GUID_A)
        b = self.mod(self.root / "B", "challenge_B", 0, GUID_B)
        c = self.mod(self.root / "C", "challenge_C", None, bytes(range(5, 21)))
        self.assertEqual(coinstall.clashes([a, b, c], STOCK), [])

    def test_a_stock_operations_order_guid_or_scenario(self):
        a = self.mod(self.root / "A", "challenge_A", 130, GUID_A)
        b = self.mod(self.root / "B", "challenge_Stock", 7, GUID_STOCK)
        self.assertEqual(coinstall.clashes([a, b], STOCK), [
            "OrderToChainMission 130 is held by the stock Operation challenge_Stock and challenge_A of A (local)",
            f"the MapConfiguration GUID GUID:{{02030405-06070809-0a0b0c0d-0e0f1011}} is held by the stock Operation "
            f"challenge_Stock and challenge_Stock of B (local)",
            "the scenario id challenge_Stock is held by the stock Operation challenge_Stock and B (local)"])

    def test_two_mods_on_one_guid_or_scenario(self):
        a = self.mod(self.root / "A", "challenge_Same", 1, GUID_A)
        b = self.mod(self.workshop / "42", "challenge_Same", 2, GUID_A, name="Far", mod_id=42)
        self.assertEqual(coinstall.clashes([a, b], ()), [
            "the MapConfiguration GUID GUID:{00010203-04050607-08090a0b-0c0d0e0f} is held by challenge_Same of A "
            "(local) and challenge_Same of Far (workshop 42)",
            "the scenario id challenge_Same is held by A (local) and Far (workshop 42)"])

    def test_one_mod_folder(self):
        a = self.mod(self.tmp / "one" / "Same", "challenge_A", 1, GUID_A)
        b = self.mod(self.tmp / "two" / "Same", "challenge_B", 2, GUID_B)
        self.assertEqual(coinstall.clashes([a, b], ()), [f"the mod folder same is held by Same (local) in "
                                                         f"{self.tmp / 'one'} and Same (local) in {self.tmp / 'two'}"])


class Tokens(Base):
    def test_shared_keys_warn_and_the_charset_row_is_ignored(self):
        a = self.mod(self.root / "A", "challenge_A", 1, GUID_A, ("t_name", "a_only"))
        b = self.mod(self.root / "B", "challenge_B", 2, GUID_B, ("t_name", "b_only"))
        c = self.mod(self.root / "C", "challenge_C", 3, bytes(range(5, 21)), ("c_only",))
        self.assertEqual(coinstall.shared_tokens([a, b, c]),
                         ["A (local) and B (local) share 1 text token keys (t_name)"])
        self.assertEqual(coinstall.clashes([a, b, c], ()), [])


class Which(Base):
    def setUp(self):
        super().setUp()
        write_mod(self.root / "A", "challenge_A", 1, GUID_A)
        write_mod(self.root / "Idd", "challenge_I", 2, GUID_B, mod_id=77)
        write_mod(self.workshop / "88", "challenge_W", 3, bytes(range(5, 21)), name="Far", mod_id=88)
        write_mod(self.root / "Idle", "challenge_Idle", 4, bytes(range(6, 22)))

    def test_the_active_list_by_name_id_and_workshop_item(self):
        self.activate("A", "77", "88", "Gone")
        found, notes = coinstall.gather(self.root, self.workshop, False, [])
        self.assertEqual(found, [(self.root / "A", "local"), (self.root / "Idd", "local"),
                                 (self.workshop / "88", "workshop")])
        self.assertEqual(len(notes), 1)
        self.assertIn("the active mod Gone is not on disk", notes[0])

    def test_all_and_no_config(self):
        found, notes = coinstall.gather(self.root, self.workshop, True, [])
        self.assertEqual([f.name for f, _ in found], ["A", "Idd", "Idle", "88"])
        found, notes = coinstall.gather(self.root, self.workshop, False, [])
        self.assertEqual(found, [])
        self.assertIn("no Config.ini", notes[0])

    def test_a_build_replaces_the_installed_mod_of_its_folder_or_id(self):
        self.activate("A", "77")
        build_a = write_mod(self.tmp / "build" / "A", "challenge_A", 1, GUID_A)
        build_i = write_mod(self.tmp / "build" / "Renamed", "challenge_I", 2, GUID_B, mod_id=77)
        found, notes = coinstall.gather(self.root, self.workshop, False, [build_a, build_i])
        self.assertEqual(found, [(build_a, "build"), (build_i, "build")])
        self.assertEqual([n.split(" replaces ")[1] for n in notes], ["the installed A", "the installed Idd"])

    def test_workshop_config_id_and_gameplay_warn(self):
        odd = coinstall.read_mod(write_mod(self.workshop / "99", "challenge_O", 5, bytes(range(7, 23)), mod_id=0),
                                 "workshop")
        self.assertEqual(odd.warnings, ["99 (workshop): its Config.ini ID is 0, not its Workshop item 99"])
        heavy = coinstall.read_mod(write_mod(self.root / "Heavy", "challenge_H", 6, bytes(range(8, 24)),
                                             clusters=True), "local")
        self.assertEqual(heavy.warnings, ["Heavy (local): a Gameplay mod; while it is active, no Operation starts"])


class Cli(Base):
    def run_check(self, *builds: Path, every: bool = False, stock=STOCK) -> tuple[int, str]:
        out = io.StringIO()
        with mock.patch.object(coinstall, "stock_operations", return_value=stock), contextlib.redirect_stdout(out):
            code = coinstall.run(self.root, self.workshop, every, list(builds))
        return code, out.getvalue()

    def test_a_clash_fails_and_nothing_is_written(self):
        write_mod(self.root / "A", "challenge_A", 1001, GUID_A)
        write_mod(self.workshop / "88", "challenge_W", 1001, GUID_B, name="Far", mod_id=88)
        self.activate("A", "88")
        before = tree(self.root, self.workshop)
        code, out = self.run_check()
        self.assertEqual(code, 1)
        self.assertIn("FAILED: OrderToChainMission 1001 is held by challenge_A of A (local) and challenge_W of Far "
                      "(workshop 88)", out)
        self.assertEqual(tree(self.root, self.workshop), before)

    def test_apart_passes(self):
        write_mod(self.root / "A", "challenge_A", 1001, GUID_A)
        build = write_mod(self.tmp / "build" / "B", "challenge_B", 1002, GUID_B)
        self.activate("A")
        code, out = self.run_check(build)
        self.assertEqual(code, 0, out)
        self.assertTrue(out.splitlines()[-1].startswith("ok: 2 mods and the 1 stock Operations share no menu order"))

    def test_without_the_extraction_it_fails_naming_setup(self):
        out = io.StringIO()
        with mock.patch.object(coinstall, "stock_operations",
                               side_effect=paths.NotConfigured("not configured: run the warno-setup skill")), \
                contextlib.redirect_stdout(out):
            self.assertEqual(coinstall.run(self.root, self.workshop, False, []), 1)
        self.assertIn("FAILED: the stock Operations could not be read: not configured: run the warno-setup skill",
                      out.getvalue())


@paths.skip_unless_extracted("scenarios")
class Stock(unittest.TestCase):
    def test_no_two_stock_operations_clash(self):
        """The 16 stock Operations, checked against each other: distinct menu orders, GUIDs and scenario ids."""
        stock = stock_operations()
        self.assertEqual(len(stock), 16)
        self.assertEqual(coinstall.clashes([], stock), [])
        self.assertEqual(len({op.guid for op in stock}), 16)


@SCRIPT_DATA
@GAME
class Builds(unittest.TestCase):
    """Both ways on real builds: the empty probe and the empty probe under probe 2's identity, both on the probes'
    1001, fail; with the second on its derived order, they pass."""

    def test_one_menu_order_fails_and_the_derived_order_passes(self):
        one = Path(OUT_ROOT, "co-one", "OpenDoorOps")
        quiet_build(empty.content(), str(one.parent))
        test = empty.content("challenge_OpenDoorTest", "OpenDoorTest")
        two = Path(OUT_ROOT, "co-two", "OpenDoorTest")
        quiet_build(test, str(two.parent))
        derived = derived_menu_order(test.scenario, probe_profile.GUID_NAMESPACE)
        three = Path(OUT_ROOT, "co-three", "OpenDoorTest")
        quiet_build(dataclasses.replace(test, scalar_edits=probe_profile.scalar_edits(derived)), str(three.parent))
        with tempfile.TemporaryDirectory() as mods_dir:
            for builds, code in (((one, two), 1), ((one, three), 0)):
                out = io.StringIO()
                with self.subTest(second=builds[1].parent.name), contextlib.redirect_stdout(out):
                    self.assertEqual(coinstall.run(Path(mods_dir), None, False, list(builds)), code)
                if code:
                    self.assertIn("FAILED: OrderToChainMission 1001 is held by challenge_OpenDoor of OpenDoorOps "
                                  "(build) and challenge_OpenDoorTest of OpenDoorTest (build)", out.getvalue())


if __name__ == "__main__":
    unittest.main()
