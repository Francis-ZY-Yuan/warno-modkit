"""Tests for probe 1 (examples/probes/probes/spike.py, the `spike` and `spike_safe` contents).

`Script` builds `spike.script(tpl)` once and walks it with `graph.walk`, matching classes by name substring. Checks that
need to tie two beats together (the A-10A lock and unlock) build those beats with one shared `spike.Ctx`, whose
variables are created once per name. `CombatBeats` builds the combat beats one at a time (`built`), each with its own
Ctx; `start_s` gives a lower bound on when a node starts from the WaitDurations before it. `Build` runs the full build
(every gate) into a temporary folder and removes it afterwards. Classes that read the stock extraction or the game
install skip without them.
"""
from __future__ import annotations

import contextlib
import dataclasses
import io
import math
import os
import shutil
import unittest

from probe_support import OUT_ROOT, check_canonical, details_files, probe_main, quiet_build, template_gdscript
from modkit.core import ndfbin, ndfrules, paths
from modkit.core.gates import CheckError
from modkit.ops import bricks, gates, graph
from modkit.ops.bricks import unit_path
from modkit.ops.files import read_file
from modkit.ops.forces import ForceRow, scaled
from modkit.ops.graph import Node, build_graph, decode, encode
from modkit.ops.items import Item
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA
from modkit.ops.profile import Content
from modkit.ops.shapes import camp_nodes
from modkit.ops.testing import (  # noqa: F401
    COMP, SEQ, SIM, hints, last, least_s, of, prop, remove_out, sets, start_s, token, within,
)
from modkit.ops.zones import point_in_polygon
from probes import profile, spike
from probes.geisa import MAP, POINTS, ROWS

OUT = os.path.join(OUT_ROOT, "spike")
GD_ITEMS = "$/GDScript/GdItems"
FOREVER = spike.FOREVER
SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
STOCK_DATA = paths.skip_unless_extracted("scenarios")
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")


def item_of(tag: Node) -> LdItem:
    """The ITEMS entry a GdItems tag binds to, by its export path."""
    ranking, name = tag.export.removeprefix(GD_ITEMS + "/").split("/")
    hits = [it for it in spike.ITEMS if (it.ranking, it.name) == (ranking, name)]
    assert len(hits) == 1, tag.export
    return hits[0]


px_of = MAP.px_of


def beat_at(t: float | None) -> list[spike.Beat]:
    return [b for b in spike.BEATS if b.t == t]


def built(t: float, check: str, ctx: spike.Ctx | None = None) -> tuple[spike.Ctx, Node, list[Node]]:
    """The beat at `t` that answers `check`, built with `ctx` (two beats sharing one see the same variables) or else
    a fresh Ctx: (ctx, its action, every node under it)."""
    (beat,) = [b for b in spike.BEATS if b.t == t and check in b.check.split(",")]
    ctx = ctx or spike.Ctx()
    root = beat.build(ctx)
    return ctx, root, list(graph.walk([root]))


def creates_of(nodes: list[Node], group: Node) -> list[tuple[str, int, tuple[float, float], str]]:
    """(unit path, count, spawn px, camp export) of every CreateUnitOnPosition into `group`, sorted."""
    return sorted((prop(c, "TypeUnit").path, prop(c, "NbUnit").v, px_of(item_of(prop(c, "Position"))),
                   prop(c, "Camp").export)
                  for c in of(nodes, "CreateUnitOnPosition") if prop(c, "Group") is group)


def rows_of(rows: list[ForceRow], camp: str,
            at: str | None = None) -> list[tuple[str, int, tuple[float, float], str]]:
    """What creates_of should find for the force `rows`, created in side `camp` (profile.CAMPS) at point `at` or else
    each row's spawn."""
    return sorted((unit_path(r.unit), r.count, POINTS[at or r.spawn],
                   f"$/GDScript/RootDescriptor/{profile.CAMPS[camp]}") for r in rows)


radius_px = MAP.radius_px


@SCRIPT_DATA
class Script(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tpl, _, _ = decode(read_file(template_gdscript()))
        cls.roots, cls.exports = spike.script(cls.tpl)
        cls.nodes = list(graph.walk(cls.roots))

    def test_load_deck_actions(self):
        setdecks = of(self.nodes, "SetDeck")
        self.assertEqual(len(setdecks), 4)
        joueur = [n for n in setdecks if prop(n, "Camp").export.endswith("/joueur")]
        self.assertEqual([prop(n, "DeckIdentifier").text for n in joueur], ["OP_BASE_BB_Player"])

        adds = of(self.nodes, "AddUnitToDeck")

        def cards(unit: str) -> list[Node]:
            return [n for n in adds if prop(n, "TypeUnit").path == unit_path(unit)]

        leo = cards("Leopard_2A4_RFA")
        self.assertEqual(len(leo), 1)
        self.assertEqual(prop(leo[0], "NbUnitsToAdd").v, 2)
        rifles = cards("Rifles_US")
        self.assertEqual(len(rifles), 1)
        self.assertEqual(prop(rifles[0], "NbUnitsToAdd").v, 2)
        self.assertEqual(prop(rifles[0], "Transporter").path, "$/GFX/Unit/Descriptor_Unit_M113A3_US")

    def test_lock_and_unlock_same_card(self):
        """LockDeckUnit holds its cards for as long as it runs (stock: Competition[WaitCondition, LockDeckUnit],
        BlackHorsesLastStand A10_Blocking). The lock starts in the load beat; the 60 s beat sets the flag that ends
        the Competition, which unlocks the same A-10A card."""
        locks = of(self.nodes, "LockDeckUnit")
        self.assertEqual(len(locks), 1)
        ctx = spike.Ctx()
        (load,), (unlock,) = beat_at(None), beat_at(60.0)
        load_nodes, unlock_nodes = list(graph.walk([load.build(ctx)])), list(graph.walk([unlock.build(ctx)]))
        (lock,) = of(load_nodes, "LockDeckUnit")
        self.assertIs(prop(lock, "Camp"), ctx.camp("NATO"))
        self.assertEqual([prop(u, "Unit").path for u in prop(lock, "Units")],
                         [unit_path("A10_Thunderbolt_II_ATGM_US")])
        (race,) = [n for n in of(load_nodes, "Competition") if lock in prop(n, "SubActions")]
        self.assertEqual([n.cls for n in prop(race, "SubActions")],  # stock order, BHLS #94 = [#131, #132]
                         ["TGDDescriptorWaitCondition", "TGDDescriptorLockDeckUnit"])
        (until,) = [n for n in prop(race, "SubActions") if n is not lock]
        cond = prop(until, "Condition")
        self.assertEqual((until.cls, cond.cls), ("TGDDescriptorWaitCondition", "TGDConditionVariable"))
        flag = prop(cond, "Variable")
        self.assertEqual(prop(prop(cond, "Operator"), "Value").v, 1)
        self.assertEqual(sets(unlock_nodes, flag), [1])
        self.assertEqual(sets(load_nodes, flag), [])
        self.assertEqual(of(unlock_nodes, "LockDeckUnit"), [])

    def test_dialog_routes(self):
        (dialog,) = [n for n in self.nodes if n.cls == "TGDDescriptorCutsceneDialogWithMultipleChoice"]
        # Stock INGAME labels: the game looks button tokens up there, and a scenario token on a button failed the probe's second launch
        self.assertEqual((token(prop(dialog, "TokenBoutonChoix0")), token(prop(dialog, "TokenBoutonChoix1"))),
                         ("CMP_EASY", "CMP_HARD"))
        (text,) = prop(dialog, "TextComponentsToFill")
        self.assertEqual(token(prop(text, "LocalizedText")), "od_start")
        chosen = prop(dialog, "SelectedButton")
        (route,) = [n for n in of(self.nodes, "IfThenElse")
                    if prop(prop(n, "Condition"), "Variable") is chosen]
        self.assertEqual(prop(route, "Condition").cls, "TGDConditionVariable")
        self.assertEqual(prop(prop(route, "Condition"), "Operator").props, [])  # Equal 0: button 0 was pressed
        (scale,) = [n for n in self.exports if n.export.endswith("/od_scale")]
        for branch, value, hint in (("EffetIfTrue", 1, "od_h5a"), ("EffetIfFalse", 2, "od_h5b")):
            with self.subTest(branch=branch):
                nodes = list(graph.walk([prop(route, branch)]))
                self.assertEqual(sets(nodes, scale), [value])
                self.assertEqual(hints(nodes), [hint])

    def test_soviets_revealed(self):
        """In the first play the tester could not see what the Soviet beats did, so every Soviet unit is visible: each
        beat that creates PACT units reveals them with SetEffect(UnitEffect_revealUnit) (a stock pack,
        TUnitEffectMakeUnitVisibleDescriptor, that no stock script applies). In the second play SetEffect never finished, and every
        Soviet beat stopped at the one right after its first create. So no SetEffect has anything after it in a
        Sequential, and each Sequential holding PACT creates (a beat, or a branch of the stress wave) ends, after all
        of them, with Simultaneous[one reveal SetEffect on exactly the groups they fill, Sequential[the rest]]. Every
        reveal ends one such beat; no other camp's group is revealed."""
        pact = f"$/GDScript/RootDescriptor/{profile.CAMPS['PACT']}"
        reveal = "$/GFX/EffectCapacity/UnitEffect_revealUnit"
        for seq in of(self.nodes, "Sequential"):
            self.assertEqual([n for n in prop(seq, "SubActions")[:-1] if n.cls == "TGDDescriptorSetEffect"], [])
        self.assertEqual(gates.never_finishing_violations(self.roots)[1], [])  # the gate agrees

        def pact_creates(seq: Node) -> list[int]:
            return [k for k, n in enumerate(prop(seq, "SubActions"))
                    if n.cls == "TGDDescriptorCreateUnitOnPosition" and prop(n, "Camp").export == pact]

        reveals = [e for e in of(self.nodes, "SetEffect") if prop(e, "Effet").path == reveal]
        beats = [s for s in of(self.nodes, "Sequential") if pact_creates(s)]
        self.assertGreaterEqual(len(beats), 8)  # T-80s, probe, column, battery, box seed, pocket AD, wave 1x and 2x
        ends = []
        for seq in beats:
            subs, made = prop(seq, "SubActions"), pact_creates(seq)
            groups = list(dict.fromkeys(prop(subs[k], "Group") for k in made))
            with self.subTest(groups=[last(g) for g in groups]):
                end = subs[-1]
                self.assertEqual(end.cls, SIM)
                self.assertLess(max(made), len(subs) - 1)  # every create comes first
                effect, *rest = prop(end, "SubActions")
                self.assertIn(effect, reveals)
                self.assertEqual(prop(effect, "UnitGroup"), groups)
                self.assertEqual([n.cls for n in rest], [SEQ])
                ends.append(effect)
        self.assertEqual(sorted(map(id, ends)), sorted(map(id, reveals)))  # one reveal per beat, each ending one
        others = {id(prop(n, "Group")) for n in of(self.nodes, "CreateUnitOnPosition") if prop(n, "Camp").export != pact}
        self.assertTrue(others)  # the decoys
        self.assertEqual([last(g) for e in reveals for g in prop(e, "UnitGroup") if id(g) in others], [])
        with open(os.path.join(str(paths.extracted_root()), "moddata_base", "GameData", "Generated", "Gameplay", "Effects",
                               "EffetsSurUnite.ndf"), encoding="utf-8", errors="replace") as fh:
            self.assertRegex(fh.read(), r"(?m)^export UnitEffect_revealUnit is TEffectsPackDescriptor\s*$")

    def test_counters_have_no_pin(self):
        """In the first play the positionless counters' pins sat in the map corner. Only the two placed markers show a
        label; gates.check_objective_pins counts them."""
        labelled = {token(prop(o, "ObjectiveText")): prop(o, "ShowEtiquette") is not None
                    for o in of(self.nodes, "GereObjectif")}
        self.assertEqual(labelled, {"od_obj1a": True, "od_obj1b": True, "od_obj4": False, "od_obj6": False})
        self.assertEqual(gates.check_objective_pins(self.roots), 2)

    def test_markers(self):
        placed = [o for o in of(self.nodes, "GereObjectif") if prop(o, "Position") is not None]
        where = sorted(prop(o, "Position").export for o in placed)
        self.assertEqual(where, [f"{GD_ITEMS}/Tags/OD_NeckMid", f"{GD_ITEMS}/Tags/OD_TownNE"])
        for o, point in zip(sorted(placed, key=lambda o: prop(o, "Position").export), ("NECK_MID", "TOWN_NE")):
            with self.subTest(point=point):
                self.assertEqual(px_of(item_of(prop(o, "Position"))), POINTS[point])

    def test_reserves_hidden(self):
        items = {it.name: it for it in spike.ITEMS}
        names = []
        for prefix, point, unit in (("OD_ResN", "RESERVE_N", "M1A1HA_Abrams_US"),
                                    ("OD_HideS", "HIDE_S", "Leopard_2A4_RFA")):
            for k in range(1, 5):
                it = items[f"{prefix}_{k}"]
                names.append(f"{GD_ITEMS}/{it.ranking}/{it.name}")
                with self.subTest(item=it.name):
                    self.assertEqual((it.addon, it.unit, it.disable_auto_spawn, it.camp), ("Spawn", unit, True, 0))
                    self.assertLessEqual(math.dist(px_of(it), POINTS[point]), 15.0)
        (beat,) = beat_at(180.0)
        (spawn,) = of(list(graph.walk([beat.build(spike.Ctx())])), "SpawnUnits")
        self.assertEqual(sorted(t.export for t in prop(spawn, "Units")), sorted(names))

    def test_t80_company(self):
        (create,) = [n for n in of(self.nodes, "CreateUnitOnPosition") if prop(n, "Group").export.endswith("/od_t80")]
        self.assertEqual(prop(create, "NbUnit").v, 10)
        self.assertEqual(prop(create, "TypeUnit").path, unit_path("T80BV_SOV"))
        self.assertEqual(px_of(item_of(prop(create, "Position"))), POINTS["ENTRY_E"])
        self.assertEqual(prop(create, "Camp").export, f"$/GDScript/RootDescriptor/{profile.CAMPS['PACT']}")
        t80 = prop(create, "Group")

        (move,) = [n for n in of(self.nodes, "GiveOrderStandard") if prop(n, "Group") is t80]
        self.assertEqual(prop(move, "OrderType").v, 12)  # EOrderType FastMoveAndAttack: roads (the first play: woods on 24)
        self.assertEqual(px_of(item_of(prop(move, "Position"))), POINTS["VILLAGE_E"])
        (seize,) = [n for n in of(self.nodes, "LaunchSmartOrder") if prop(n, "UnitGroup") is t80]
        self.assertEqual(prop(seize, "SmartOrderType").v, 1)  # PlayerMissionRequest Seize
        self.assertEqual(px_of(item_of(prop(seize, "Position"))), POINTS["NECK_MID"])

        # od_obj4 counts od_t80's losses: lost = 10 - alive, written in one step from a scratch variable.
        (obj,) = [o for o in of(self.nodes, "GereObjectif") if token(prop(o, "ObjectiveText")) == "od_obj4"]
        (lost,) = prop(obj, "ListVariables")
        self.assertEqual(prop(obj, "ListVariablesForEtiquetteText"), [lost])
        self.assertIs(prop(prop(obj, "Condition"), "Variable"), lost)
        self.assertEqual(prop(prop(prop(obj, "Condition"), "Operator"), "Value").v, 10)
        writes = [n for n in of(self.nodes, "ModifieVariableInteger") if prop(n, "Variable1") is lost]
        self.assertEqual(len(writes), 1)
        scratch = prop(writes[0], "Variable2")
        self.assertEqual(sets(self.nodes, scratch), [10])
        (minus,) = [n for n in of(self.nodes, "ModifieVariableInteger")
                    if prop(n, "Variable1") is scratch and prop(n, "ModificationType") is not None]
        self.assertEqual(prop(minus, "ModificationType").v, 2)  # Substract
        alive = prop(minus, "Variable2")
        (count,) = [n for n in of(self.nodes, "SetVariableIntegerFromUnitGroup") if prop(n, "Variable") is alive]
        self.assertIs(prop(count, "Group"), t80)

    def test_deploy_zones(self):
        items = {it.name: it for it in spike.ITEMS}
        for name, addon, box in (("OD_DZ_W", "DeploymentZone", (13, 250, 540, 780)),
                                 ("OD_CZ_SW", "CommandPoints", (90, 610, 190, 700))):
            with self.subTest(zone=name):
                it = items[name]
                self.assertEqual(it.addon, addon)
                xs, ys = zip(*(GEISA.world_to_px(p) for p in it.polygon))
                self.assertEqual((min(xs), min(ys), max(xs), max(ys)), box)
        (points,) = of(self.nodes, "SetRessourceForTeam")
        self.assertEqual(prop(points, "Quantite").v, 3000)
        (owner,) = of(self.nodes, "SetCommandZoneOwner")
        self.assertEqual([t.export for t in prop(owner, "Positions")], [f"{GD_ITEMS}/CommandPoints/OD_CZ_SW"])
        self.assertIn("od_h2", hints(self.nodes))

    def test_player_arrivals(self):
        """Units bought after the launch arrive at Geisa's west-edge entries (the probe's third launch had none), each ending
        inside OD_DZ_W: the game gives a corridor the side of the zone its End lies in (the second play: with the zone's
        west edge at 90 px, no land unit bought in battle arrived)."""
        arrivals = [it for it in spike.ITEMS if it.addon in ("ReinforcementLocation", "AerialCorridor")]
        self.assertEqual([it.name for it in arrivals], ["OD_RL_W1", "OD_RL_W2", "OD_AC_W1", "OD_AC_W2"])
        self.assertEqual(gates.check_arrivals(spike.ITEMS, details_files(spike.ITEMS)), (2, 2))
        dz = next(it for it in spike.ITEMS if it.name == "OD_DZ_W")
        for it in arrivals:  # each enters at the west edge, outside the zone, and ends inside it
            with self.subTest(item=it.name):
                (sx, sy), (ex, ey) = GEISA.world_to_px(it.start), GEISA.world_to_px(it.end)
                self.assertTrue(sx < spike.DZ_W[0] < ex and 250 <= sy <= 780, ((sx, sy), (ex, ey)))
                self.assertTrue(point_in_polygon(*it.end, list(dz.polygon)))

    def test_pre_fix_zone_fails_every_arrival(self):
        """Gate 3 fails the second play's geometry (OD_DZ_W from x 90 px) on all four entries, read from the Details bytes
        the build ships, each named with its distance to the zone."""
        old = MAP.zone_item("DeploymentZone", "OD_DZ_W", (90, *spike.DZ_W[1:]), "DeploymentZone")
        items = [old if it.name == "OD_DZ_W" else it for it in spike.ITEMS]
        with self.assertRaises(CheckError) as err:
            gates.check_arrivals(items, details_files(items))
        lines = [ln.strip() for ln in str(err.exception).splitlines() if ": End (" in ln]
        self.assertEqual([ln.split(":")[0] for ln in lines], ["OD_AC_W1", "OD_AC_W2", "OD_RL_W1", "OD_RL_W2"])
        self.assertIn("OD_RL_W1: End (66,701, 969,031) lies in no player deployment zone and no command zone, "
                      "163,699 W of OD_DZ_W", lines)
        self.assertTrue(all(" W of OD_DZ_W" in ln for ln in lines))

    def test_hint_first(self):
        """Every timed beat but the 0:00 dialog opens with the hint that names its checklist number."""
        ctx = spike.Ctx()
        for b in spike.BEATS:
            if b.t is None or b.t == 0.0:
                continue
            with self.subTest(t=b.t, check=b.check):
                first = prop(b.build(ctx), "SubActions")[0]
                self.assertEqual(first.cls, "TGDDescriptorLDHint")
                self.assertTrue(token(prop(first, "Info")).startswith("od_h"))

    def test_every_check_has_a_beat(self):
        """The 11 checks each have a beat (a beat may answer several, comma-separated)."""
        checks = set().union(*(b.check.split(",") for b in spike.BEATS))
        self.assertEqual(checks, {str(k) for k in range(1, 12)})


class CombatBeats(unittest.TestCase):
    """The combat beats, each built alone with its own Ctx (check 9 at 0:20; 1:30, 2:00,
    5:00 to 10:00)."""

    items = {it.name: it for it in spike.ITEMS}
    EFFECTS = ("UnitEffect_Critic_Chenille_Detruite",)

    def hidden(self, name: str, unit: str, point: str) -> LdItem:
        """Item `name` is a hidden player (camp 0) `unit` within 15 px of `point`."""
        it = self.items[name]
        self.assertEqual((it.addon, it.unit, it.camp, it.disable_auto_spawn), ("Spawn", unit, 0, True), name)
        self.assertLessEqual(math.dist(px_of(it), POINTS[point]), 15.0, name)
        return it

    @paths.skip_unless_extracted("moddata_base")
    def test_decoys(self):
        """Check 9 at 0:20 (at 0:05 its hint collided with od_h1's): 2 + 2 M1s in the Decoys camp (Survivors'
        Allie) on PL BLUE; an empty SetAmmo on both groups, then the beat ends with Simultaneous[one broken-tracks
        SetEffect on both groups, a forever loop emptying od_decoyB again every 30 s]. In the first play all four fired
        under the weapons-jammed critical, so SetAmmo empties them instead, in Survivors' shape for its abandoned T-55
        (Units only: MaxAmmoRatio left at its 0). In the second play the beat stopped at its first SetEffect, which never
        finishes; SetAmmo is instantaneous, so it goes first, and the effect, a live binding, is never re-applied."""
        self.assertEqual([b.t for b in spike.BEATS if "9" in b.check.split(",")], [20.0])
        ctx, root, nodes = built(20.0, "9")
        groups = (ctx.group("od_decoyA"), ctx.group("od_decoyB"))
        b = groups[1]
        for g in groups:
            with self.subTest(group=last(g)):
                self.assertEqual(creates_of(nodes, g), [(unit_path("M1_Abrams_US"), 2, POINTS["PL_BLUE"],
                                                         "$/GDScript/RootDescriptor/Allie")])
        self.assertEqual(len(of(nodes, "CreateUnitOnPosition")), 2)

        def pairs(effects: list[Node]) -> list[tuple[str, tuple[str, ...]]]:
            return sorted((prop(e, "Effet").path.rsplit("/", 1)[1], tuple(last(g) for g in prop(e, "UnitGroup")))
                          for e in effects)

        (loop,) = [n for n in of(nodes, "Sequential") if prop(n, "NbExecutions").v == FOREVER]
        inside = list(graph.walk([loop]))
        effects = of(nodes, "SetEffect")
        self.assertEqual(pairs(effects), sorted((e, tuple(last(g) for g in groups)) for e in self.EFFECTS))
        self.assertEqual(of(inside, "SetEffect"), [])
        (seq,) = [s for s in of(nodes, "Sequential") if of(prop(s, "SubActions"), "CreateUnitOnPosition")]
        subs = prop(seq, "SubActions")
        self.assertEqual(prop(subs[-1], "SubActions"), [*effects, loop])  # the beat's last node
        self.assertEqual(subs[-1].cls, SIM)
        self.assertEqual([n.cls.removeprefix("TGDDescriptor") for n in subs[:-1]],
                         ["CreateUnitOnPosition"] * 2 + ["SetAmmo"] * 2)  # SetAmmo is instantaneous: it goes first
        self.assertEqual(gates.never_finishing_violations([root])[1], [])
        with open(os.path.join(str(paths.extracted_root()), "moddata_base", "GameData", "Generated", "Gameplay", "Effects",
                               "EffetsSurUnite.ndf"), encoding="utf-8", errors="replace") as fh:
            packs = fh.read()  # gate 3 checks unit imports only, so the effect packs are pinned here
        for e in self.EFFECTS:
            self.assertRegex(packs, rf"(?m)^export {e} is TEffectsPackDescriptor\s*$")
        self.assertEqual([prop(w, "Duree").v for w in of(inside, "WaitDuration")], [30.0])
        self.assertNotIn("Stop_Armes", repr([prop(e, "Effet").path for e in of(nodes, "SetEffect")]))

        def emptied(ammo: list[Node]) -> list[str]:
            self.assertEqual({tuple(k for k, _ in a.props) for a in ammo}, {("Units",)})  # Survivors' SetAmmo shape
            return sorted(last(g) for a in ammo for g in prop(a, "Units"))

        self.assertEqual(emptied([a for a in of(nodes, "SetAmmo") if all(a is not n for n in inside)]),
                         sorted(last(g) for g in groups))
        self.assertEqual(emptied(of(inside, "SetAmmo")), [last(b)])
        for a in of(inside, "SetAmmo"):
            self.assertGreaterEqual(start_s(loop, a), 30.0)

    def test_probe_ring(self):
        """Check 4 at 1:30: the probe rows at TRACK SE IN take the forest-track waypoints to HIDE S; once a probe
        unit has been in ring OD_RingS (30 px at HIDE S) for 20 s without a break, od_h4r shows."""
        ring = self.items["OD_RingS"]
        self.assertEqual(ring.addon, "CircularZone")
        self.assertLessEqual(math.dist(px_of(ring), POINTS["HIDE_S"]), 5.0)
        self.assertAlmostEqual(radius_px(ring), 30.0, places=3)

        ctx, root, nodes = built(90.0, "4")
        probe, ring_tag = ctx.group("od_probe"), ctx.tag("OD_RingS")
        probe_rows = [r for r in ROWS if r.group == "probe"]
        self.assertEqual(creates_of(nodes, probe), rows_of(probe_rows, "PACT"))
        (move,) = [m for m in of(nodes, "MoveUnitGroup") if prop(m, "Group") is probe]
        self.assertEqual([px_of(item_of(p)) for p in prop(move, "Positions")],
                         [(600, 645), (570, 710), px_of(ring)])
        self.assertIs(prop(move, "Positions")[-1], ring_tag)

        def ring_detect(cond: Node) -> Node:
            """`cond` counts the probe's own unit types in the ring; returns its comparison."""
            self.assertEqual(cond.cls, "TGDConditionDetectUnitDansDetecteur")
            self.assertIs(prop(cond, "Detecteur"), ring_tag)
            types = {prop(c, "TypeUnit").path for c in of(list(graph.walk([prop(cond, "Contrainte")])), "OnUnitType")}
            self.assertEqual(types, {unit_path(r.unit) for r in probe_rows})
            return prop(cond, "ComparaisonNbUnits")

        (hint,) = [h for h in of(nodes, "LDHint") if token(prop(h, "Info")) == "od_h4r"]
        (seq,) = [s for s in of(nodes, "Sequential")
                  if any(k is hint or hint in (prop(k, "SubActions") or []) for k in prop(s, "SubActions"))]
        before = prop(seq, "SubActions")[:-1]
        self.assertIn(hint, list(graph.walk(prop(seq, "SubActions")[-1:])))  # the hint is the last step
        (flag,) = [prop(prop(w, "Condition"), "Variable") for w in of(list(graph.walk(before)), "WaitCondition")
                   if prop(w, "Condition").cls == "TGDConditionVariable"]
        # flag = 1 only after 20 s in the ring, raced against the ring emptying; the timer restarts on a break.
        (setter,) = [s for s in of(nodes, "Sequential") if sets(prop(s, "SubActions"), flag) == [1]]
        wait, _ = prop(setter, "SubActions")
        self.assertEqual((wait.cls, prop(wait, "Duree").v), ("TGDDescriptorWaitDuration", 20.0))
        (race,) = [c for c in of(nodes, "Competition") if any(k is setter for k in prop(c, "SubActions"))]
        (broken,) = [k for k in prop(race, "SubActions") if k is not setter]
        self.assertEqual(ring_detect(prop(broken, "Condition")).props, [])  # count == 0
        (watch,) = [s for s in of(nodes, "Sequential") if any(k is race for k in prop(s, "SubActions"))]
        entered = ring_detect(prop(prop(watch, "SubActions")[0], "Condition"))
        self.assertEqual((prop(entered, "Value").v, prop(entered, "OperatorType").v), (1, 2))  # count >= 1
        self.assertEqual(prop(watch, "NbExecutions").v, FOREVER)

    def test_fires(self):
        """Check 6: the 5:00 battery fires ShootOnPosition into OD_BoxMid; the 6:00 strike on OD_BoxS puts the
        Soviet units in the box into od_boxed, moves half of them to od_struck, kills those (Penetration) and
        stresses the rest. Each fire comes at least 15 s after its warning hint."""
        box_mid, box_s = self.items["OD_BoxMid"], self.items["OD_BoxS"]
        for it, point, r in ((box_mid, "NECK_MID", 25.0), (box_s, "NECK_S", 26.0)):
            with self.subTest(zone=it.name):
                self.assertEqual(it.addon, "CircularZone")
                self.assertEqual(px_of(it), POINTS[point])
                self.assertAlmostEqual(radius_px(it), r, places=3)

        ctx, root, nodes = built(300.0, "6")
        battery = ctx.group("od_battery")
        self.assertEqual(creates_of(nodes, battery),
                         rows_of([r for r in ROWS if r.group == "opener_battery"], "PACT"))
        # From CORNER PACT, BOX MID lies within the 2S3M's reach and beyond the BM-27's minimum range
        # (Ammunition.ndf: Ammo_Howz_Canon_D22_Howitzer_152mm_late MaximumRangeGRU 17500;
        # Ammo_RocketArt_9M27F_HE_220mm MinimumRangeGRU 10000, MaximumRangeGRU 35000).
        reach_px = math.dist(POINTS["CORNER_PACT"], POINTS["NECK_MID"])
        reach = reach_px * GEISA.world_per_px / spike.GRU_WORLD
        self.assertLess(reach, 17500.0)
        self.assertGreater(reach, 10000.0)
        (shot,) = [g for g in of(nodes, "GiveOrderStandard") if prop(g, "OrderType").v == 31]  # ShootOnPosition
        self.assertIs(prop(shot, "Position"), ctx.tag("OD_BoxMid"))
        self.assertIs(prop(shot, "Group"), battery)
        (warn,) = [h for h in of(nodes, "LDHint") if token(prop(h, "Info")) == "od_h6a"]
        self.assertGreaterEqual(start_s(root, shot) - start_s(root, warn), 15.0)

        ctx, root, nodes = built(360.0, "6")
        boxed, struck, tag = ctx.group("od_boxed"), ctx.group("od_struck"), ctx.tag("OD_BoxS")
        fx = of(nodes, "LaunchFXFireAndForgetOnPosition")
        self.assertGreaterEqual(len(fx), 2)
        for f in fx:
            with self.subTest(fx=last(prop(f, "Position"))):
                self.assertLess(math.dist(px_of(item_of(prop(f, "Position"))), POINTS["NECK_S"]), 26.0)
        (collect,) = of(nodes, "AddDetectedUnitsToUnitGroup")
        self.assertIs(prop(collect, "Group"), boxed)
        self.assertIs(prop(prop(collect, "Detector"), "Detecteur"), tag)
        self.assertIs(prop(prop(prop(collect, "Detector"), "Contrainte"), "Camp"), ctx.camp("PACT"))
        (move,) = of(nodes, "TransferUnitToUnitGroup")
        self.assertEqual((prop(move, "GroupSource"), prop(move, "GroupDestination"), prop(move, "NBToTransfert").v),
                         (boxed, struck, 1))
        # one unit at a time while od_struck < half, half = (units caught) / 2
        (step,) = [n for n in of(nodes, "IfThenElse") if move in graph.walk([prop(n, "EffetIfTrue")])]
        cond = prop(step, "Condition")
        self.assertIs(prop(cond, "Variable"), struck)
        self.assertEqual(prop(prop(cond, "Operator"), "OperatorType").v, 5)  # StrictlyLess
        half = prop(prop(cond, "Operator"), "Variable")
        (caught,) = [prop(n, "Variable") for n in of(nodes, "SetVariableIntegerFromUnitGroup")
                     if prop(n, "Group") is boxed]
        halving = [n for n in of(nodes, "ModifieVariableInteger") if prop(n, "Variable1") is half]
        self.assertEqual([(prop(n, "Variable2"), prop(n, "Value") and prop(n, "Value").v,
                           prop(n, "ModificationType") and prop(n, "ModificationType").v) for n in halving],
                         [(caught, None, None), (None, 2, 4)])  # half = caught; half /= 2 (Divide)
        (kill,) = of(nodes, "KillAllUnit")
        self.assertEqual(prop(kill, "GroupList"), [struck])
        self.assertEqual(prop(kill, "DeathCause").v, 2)  # EDeathCause Penetration
        (stress,) = of(nodes, "ChangeStress")
        self.assertIs(prop(stress, "Group"), boxed)
        self.assertGreater(prop(stress, "Value").v, 0)
        self.assertEqual(prop(stress, "DamageType").v, 2)  # EDamageType Stun: the game's validate rejects 0, Suppress
        (warn,) = [h for h in of(nodes, "LDHint") if token(prop(h, "Info")) == "od_h6b"]
        for f in [*fx, collect, kill, stress]:
            self.assertGreaterEqual(start_s(root, f) - start_s(root, warn), 15.0)
        (obj,) = [o for o in of(nodes, "GereObjectif") if token(prop(o, "ObjectiveText")) == "od_obj6"]
        self.assertEqual(prop(obj, "ListVariables"), [caught])
        tokens = {t: texts for dic in spike.STRINGS.values() for t, texts in dic.items()}
        for lang, text in tokens["od_obj6"].items():
            with self.subTest(token="od_obj6", lang=lang):
                self.assertIn("%1", text)

    def test_box_s_seeded(self):
        """Check 6 at 6:00: the strike must not hang on the 2:00 column still being in BOX S at 6:20. Right after
        the warning hint, 4 BMP-2 of their own group (od_boxseed, PACT) are created on OD_BoxS, at least 15 s before
        the strike selects the Soviet units in the box; the column, if it is there, adds to them."""
        ctx, root, nodes = built(360.0, "6")
        seed = ctx.group("od_boxseed")
        self.assertEqual(creates_of(nodes, seed), [(unit_path("BMP_2_SOV"), 4, POINTS["NECK_S"],
                                                    f"$/GDScript/RootDescriptor/{profile.CAMPS['PACT']}")])
        (create,) = [c for c in of(nodes, "CreateUnitOnPosition") if prop(c, "Group") is seed]
        self.assertIs(prop(create, "Position"), ctx.tag("OD_BoxS"))
        self.assertIsNot(seed, ctx.group("od_column"))
        (warn,) = [h for h in of(nodes, "LDHint") if token(prop(h, "Info")) == "od_h6b"]
        self.assertIs(prop(root, "SubActions")[0], warn)  # the hint still opens the beat
        (collect,) = of(nodes, "AddDetectedUnitsToUnitGroup")
        self.assertEqual(start_s(root, create), start_s(root, warn))
        self.assertGreaterEqual(start_s(root, collect) - start_s(root, create), 15.0)
        (seq,) = [s for s in of(nodes, "Sequential") if any(k is create for k in prop(s, "SubActions"))]
        self.assertEqual(within(seq, create), [0])
        self.assertIn(collect, list(graph.walk(prop(seq, "SubActions")[1:])))  # the strike runs beside the reveal

    def flight(self, ctx: spike.Ctx, nodes: list[Node], group: Node) -> tuple[Node, Node,
                                                                                            Node]:
        """Check 7's flight, the same in both variants: `group` moves to LZ MID (blocking) and unloads there
        (blocking), then od_aa_down = 1. Returns (move, unload, flag setter)."""
        (move,) = of(nodes, "MoveUnitGroup")
        self.assertEqual((prop(move, "Group"), prop(move, "Blocking")), (group, graph.TRUE))
        self.assertEqual([px_of(item_of(p)) for p in prop(move, "Positions")], [POINTS["LZ_MID"]])
        (unload,) = of(nodes, "UnloadFromTransporter")
        self.assertEqual((prop(unload, "Group"), prop(unload, "Blocking")), (group, graph.TRUE))
        self.assertEqual(px_of(item_of(prop(unload, "Position"))), POINTS["LZ_MID"])
        (setter,) = [n for n in of(nodes, "ModifieVariableInteger") if prop(n, "Variable1") is ctx.int_var("od_aa_down")]
        self.assertEqual(sets([setter], ctx.int_var("od_aa_down")), [1])
        return move, unload, setter

    def test_air_assault(self):
        """Check 7 at 7:00, spike: one ProductionUnites makes the AeroRifles inside a UH-60A at EDGE N, into a new
        group, which flies to LZ MID and unloads there (the first and second plays: no scripted boarding worked, and no stock
        script boards a helicopter). Stock's shape (SigurdsStrike #1046): Camp, NbUnit 1, Position a tag, TypeUnit,
        with Group and Transporter in the natives' alphabetical order; no ProduceOutMap, so it appears at the tag."""
        ctx, root, nodes = built(420.0, "7")
        (made,) = of(nodes, "ProductionUnites")
        self.assertEqual([k for k, _ in made.props], ["Camp", "Group", "NbUnit", "Position", "Transporter", "TypeUnit"])
        self.assertIs(prop(made, "Camp"), ctx.camp("NATO"))
        self.assertEqual(prop(made, "NbUnit").v, 1)
        self.assertIs(prop(made, "Position"), ctx.tag("OD_EdgeN"))
        self.assertEqual(px_of(item_of(prop(made, "Position"))), POINTS["EDGE_N"])
        self.assertEqual((prop(made, "Transporter").path, prop(made, "TypeUnit").path),
                         (unit_path("UH60A_Black_Hawk_US"), unit_path("AeroRifles_US")))
        group = prop(made, "Group")
        self.assertEqual((group.cls, last(group)), ("TGDVariableUnitGroup", "od_aa"))
        self.assertEqual([n.cls for n in nodes if n is not made and any(v is group for _, v in n.props)],
                         ["TGDDescriptorMoveUnitGroup", "TGDDescriptorUnloadFromTransporter"])  # od_aa is new
        for cls in ("SpawnUnits", "LoadIntoTransporter", "GiveOrderStandard", "Competition"):
            self.assertEqual(of(nodes, cls), [], cls)
        move, unload, setter = self.flight(ctx, nodes, group)
        (seq,) = [s for s in of(nodes, "Sequential") if any(k is made for k in prop(s, "SubActions"))]
        self.assertEqual(prop(seq, "SubActions"), [made, move, unload, setter])
        self.assertEqual(gates.never_finishing_violations([root])[1], [])

    def test_air_assault_safe(self):
        """Check 7 at 7:00, spike_safe: SpawnUnits reveals the hidden UH-60A at EDGE N and its AeroRifles (own item:
        no stock Spawn add-on carries passengers); the helicopter is ordered to land, non-blocking and with no
        Position (Land is an instant order and takes no target; stock positionless order: Survivors #1453), a short
        wait, then the rifles board, blocking but raced against 60 s, then the flight and the unload."""
        helo = self.hidden("OD_AA_Helo", "UH60A_Black_Hawk_US", "EDGE_N")
        rifles = self.hidden("OD_AA_Rifles", "AeroRifles_US", "EDGE_N")
        self.assertLessEqual(math.dist(px_of(helo), px_of(rifles)), 15.0)
        ctx, root, nodes = built(420.0, "7", spike.Ctx(safe=True))
        h, r = ctx.tag("OD_AA_Helo"), ctx.tag("OD_AA_Rifles")
        self.assertEqual(of(nodes, "ProductionUnites"), [])
        (spawn,) = of(nodes, "SpawnUnits")
        self.assertEqual(sorted(t.export for t in prop(spawn, "Units")), sorted([h.export, r.export]))
        (land,) = of(nodes, "GiveOrderStandard")
        self.assertEqual([k for k, _ in land.props], ["Group", "OrderType"])  # no Blocking, no Position
        self.assertEqual((prop(land, "Group"), prop(land, "OrderType").v), (h, 18))
        (board,) = of(nodes, "LoadIntoTransporter")
        self.assertEqual((prop(board, "Group"), prop(board, "Targets"), prop(board, "Blocking")), (r, h, graph.TRUE))
        (race,) = [c for c in of(nodes, "Competition") if any(n is board for n in graph.walk([c]))]
        boarding, timeout = prop(race, "SubActions")
        self.assertEqual(prop(boarding, "SubActions"), [board])  # stock never races a LoadIntoTransporter bare
        self.assertEqual((timeout.cls, prop(timeout, "Duree").v), ("TGDDescriptorWaitDuration", 60.0))
        move, unload, setter = self.flight(ctx, nodes, h)
        (seq,) = [s for s in of(nodes, "Sequential") if any(k is unload for k in prop(s, "SubActions"))]
        spawn_, land_, wait, race_, *rest = prop(seq, "SubActions")
        self.assertEqual([spawn_, land_, race_, rest], [spawn, land, race, [move, unload, setter]])
        self.assertEqual(wait.cls, "TGDDescriptorWaitDuration")
        self.assertTrue(0 < prop(wait, "Duree").v < 60.0)
        self.assertEqual(gates.never_finishing_violations([root])[1], [])

    def test_nothing_after_a_reveal(self):
        """reveal()'s Simultaneous never finishes (its SetEffect never does), so gate 3 fails a node placed after it,
        as it fails one after the SetEffect itself."""
        ctx = spike.Ctx()
        group = ctx.group("od_column")
        beat = bricks.g_seq([spike.create(ctx, "PACT", group, 1, ctx.tag("OD_EntryE"), unit_path("BMP_2_SOV")),
                           spike.reveal([group], [spike.move(group, ctx.tag("OD_BoxS"))])])
        self.assertEqual(gates.never_finishing_violations([beat])[1], [])
        prop(beat, "SubActions").append(spike.move(group, ctx.tag("OD_NeckMid")))
        with self.assertRaisesRegex(CheckError, r"Simultaneous > SetEffect\(UnitEffect_revealUnit, od_column\) "
                                                     r"\(never finishes\): what follows it in its Sequential never "
                                                     r"runs \(1: MoveUnitGroup\(od_column\)\)"):
            gates.check_never_finishing([beat])

    def test_air_assault_hint(self):
        """od_h7 is true of both variants: the rifles appear in the helicopter (spike) or beside it (spike_safe)."""
        h7 = spike.STRINGS["Scripting/Localization"]["od_h7"]
        en, zh = h7.US, h7.SC
        for text in ("UH-60A", "AeroRifles", "EDGE N", "LZ MID", "by hand", "30 s"):
            self.assertIn(text, en)
        self.assertNotIn("land", en.lower().replace("lz mid", ""))
        for text in ("UH-60A", "EDGE N", "LZ MID", "30秒", "手动"):
            self.assertIn(text, zh)

    def test_air(self):
        """Check 10 at 8:00: two hidden AH-64A at EDGE W are revealed and move to HOLD W; an F-4G card is added; the
        pocket_ad rows at SACK MID get SetFuel 25. The air defence waits for the 7:00 air assault: the boarding may
        let the helicopter leave as late as 8:00, and SACK MID is about 50 px from LZ MID. So before the pocket_ad
        rows are created, the beat races a wait on the flag the air assault sets after its unload against 60 s."""
        apaches = [self.hidden(f"OD_Apache_{k}", "AH64_Apache_emp1_US", "EDGE_W") for k in (1, 2)]
        ctx, root, nodes = built(480.0, "10")
        _, aa_root, aa_nodes = built(420.0, "7", ctx)  # one Ctx: the two beats share the flag
        tags = [ctx.tag(it.name) for it in apaches]
        (spawn,) = of(nodes, "SpawnUnits")
        self.assertEqual(sorted(t.export for t in prop(spawn, "Units")), sorted(t.export for t in tags))
        moves = of(nodes, "MoveUnitGroup")
        self.assertEqual(sorted(last(prop(m, "Group")) for m in moves), sorted(last(t) for t in tags))
        for m in moves:
            self.assertEqual([px_of(item_of(p)) for p in prop(m, "Positions")], [POINTS["HOLD_W"]])
        (card,) = of(nodes, "AddUnitToDeck")
        self.assertEqual(prop(card, "TypeUnit").path, unit_path("F4_Wild_Weasel_US"))
        self.assertEqual(prop(card, "NbUnitsToAdd").v, 1)
        self.assertIs(prop(card, "Camp"), ctx.camp("NATO"))
        pocket = ctx.group("od_pocket_ad")
        self.assertEqual(creates_of(nodes, pocket),
                         rows_of([r for r in ROWS if r.group == "pocket_ad"], "PACT", at="SACK_MID"))
        (fuel,) = of(nodes, "SetFuel")
        self.assertEqual((prop(fuel, "MaxFuelRatio").v, prop(fuel, "Units")), (25, [pocket]))

        # The race: WaitCondition(flag == 1) against WaitDuration 60, ahead of every pocket_ad create.
        (race,) = of(nodes, "Competition")
        until, wait = prop(race, "SubActions")
        self.assertEqual((until.cls, wait.cls, prop(wait, "Duree").v),
                         ("TGDDescriptorWaitCondition", "TGDDescriptorWaitDuration", 60.0))
        cond = prop(until, "Condition")
        self.assertEqual(cond.cls, "TGDConditionVariable")
        self.assertEqual(prop(prop(cond, "Operator"), "Value").v, 1)
        flag = prop(cond, "Variable")
        creates = [c for c in of(nodes, "CreateUnitOnPosition") if prop(c, "Group") is pocket]
        (seq,) = [s for s in of(nodes, "Sequential") if any(k is race for k in prop(s, "SubActions"))]
        at = within(seq, card, race, *creates)
        self.assertEqual(at, sorted(at))
        self.assertIn(fuel, list(graph.walk(prop(seq, "SubActions")[-1:])))  # after them, beside the reveal
        # Only the air assault sets the flag, to 1, right after its Blocking unload.
        self.assertEqual(sets(nodes, flag), [])
        self.assertEqual(sets(aa_nodes, flag), [1])
        (unload,) = of(aa_nodes, "UnloadFromTransporter")
        (setter,) = [n for n in of(aa_nodes, "ModifieVariableInteger") if prop(n, "Variable1") is flag]
        (aa_seq,) = [s for s in of(aa_nodes, "Sequential") if any(k is unload for k in prop(s, "SubActions"))]
        first, second = within(aa_seq, unload, setter)
        self.assertEqual(second, first + 1)
        self.assertIs(prop(unload, "Blocking"), graph.TRUE)


class Strings(unittest.TestCase):
    def test_strings_task5(self):
        tokens = {t: texts for dic in spike.STRINGS.values() for t, texts in dic.items()}
        want = ["od_start", "od_obj4", "od_h1", "od_h2", "od_h2b", "od_h3", "od_h4", "od_h5a",
                "od_h5b", *profile.MENU_TOKENS]
        self.assertEqual([t for t in want if t not in tokens], [])
        self.assertEqual([t for t in ("od_c1x", "od_c2x") if t in tokens], [])  # the buttons use stock INGAME labels
        self.assertEqual(sorted(spike.STRINGS["SCENARIO_DEFINITION"]), sorted(profile.MENU_TOKENS))
        for lang, text in tokens["od_start"].items():
            with self.subTest(token="od_start", lang=lang):
                self.assertIn("#bold{", text)
        for lang, text in tokens["od_obj4"].items():
            with self.subTest(token="od_obj4", lang=lang):
                self.assertIn("%1", text)

    def test_strings_task6(self):
        tokens = {t for dic in spike.STRINGS.values() for t in dic}
        want = ["od_h3c", "od_h4p", "od_h4r", "od_h6a", "od_h6b", "od_h7", "od_h8", "od_h9", "od_h10", "od_obj6"]
        self.assertEqual([t for t in want if t not in tokens], [])


class Forces(unittest.TestCase):
    def test_stress_rows(self):
        """Check 8 at 10:00: the main body and relief, 118 units at 1x and 236 at 2x; the beat creates the 2x rows
        when the start dialog set od_scale to 2 and the 1x rows otherwise, each row into od_stress_<group> at its
        spawn, and sends both groups MoveAndAttack to TOWN SW."""
        for scale, total in ((1.0, 118), (2.0, 236)):
            with self.subTest(scale=scale):
                want = [r for r in scaled(ROWS, scale) if r.group in ("main_body", "relief")]
                self.assertEqual(spike.stress_rows(scale), want)
                self.assertEqual({r.group for r in want}, {"main_body", "relief"})
                self.assertEqual(sum(r.count for r in spike.stress_rows(scale)), total)

        ctx, root, nodes = built(600.0, "8")
        (branch,) = [n for n in of(nodes, "IfThenElse")
                     if prop(prop(n, "Condition"), "Variable") is ctx.int_var("od_scale")]
        self.assertEqual(prop(prop(prop(branch, "Condition"), "Operator"), "Value").v, 2)  # od_scale == 2
        groups = [ctx.group(f"od_stress_{g}") for g in ("main_body", "relief")]
        for side, scale in (("EffetIfTrue", 2.0), ("EffetIfFalse", 1.0)):
            with self.subTest(branch=side):
                wave = list(graph.walk([prop(branch, side)]))
                rows = spike.stress_rows(scale)
                for g in groups:
                    self.assertEqual(creates_of(wave, g),
                                     rows_of([r for r in rows if f"od_stress_{r.group}" == last(g)], "PACT"))
                self.assertEqual(sum(prop(c, "NbUnit").v for c in of(wave, "CreateUnitOnPosition")),
                                 sum(r.count for r in rows))
                attacks = [o for o in of(wave, "GiveOrderStandard") if prop(o, "OrderType").v == 12]  # FastMoveAndAttack
                self.assertEqual(sorted(last(prop(o, "Group")) for o in attacks), sorted(last(g) for g in groups))
                for o in attacks:
                    self.assertEqual(px_of(item_of(prop(o, "Position"))), POINTS["TOWN_SW"])


@SCRIPT_DATA
@GAME
class Build(unittest.TestCase):
    def test_spike_builds(self):
        try:
            quiet_build(spike.content(), OUT)
        finally:
            remove_out(OUT)
        self.assertFalse(os.path.exists(OUT))

    def test_transporter_shape_is_admitted_by_the_content(self):
        """No stock GDScript sets AddUnitToDeck.Transporter (design 9 check 2 tests it), so the shape gate admits it only
        because the spike content declares it; without that, gate 2 fails before anything is written."""
        out = os.path.join(OUT_ROOT, "spike_bare")
        bare = dataclasses.replace(spike.content(), extra_shapes=())
        try:
            with self.assertRaisesRegex(CheckError, r"TGDDescriptorAddUnitToDeck.*Transporter"):
                quiet_build(bare, out)
            self.assertFalse(os.path.exists(out))
        finally:
            remove_out(out)

    def test_interleaved_imports_are_canonical(self):
        """Gate 2 takes stock's IMPR rule (check_canonical): imports in first-use order, their tree the trie of
        those paths in that order. A script whose first uses interleave unit and effect imports, as the spike's do
        (and TheWingedHussars'), passes it; the stricter "preorder = index order" rule rejects it. A tree that is not
        that trie still fails."""
        camp, group = camp_nodes(profile.CAMP_ROWS, profile.CAMP_TOKENS)["joueur"], Node("TGDVariableUnitGroup", export="$/GDScript/OD/G")

        def card(unit: str) -> Node:
            return Node("TGDDescriptorAddUnitToDeck", [("Camp", camp), ("NbUnitsToAdd", graph.i32(1)),
                                                            ("TypeUnit", graph.Imp(unit_path(unit)))])

        effect = Node("TGDDescriptorSetEffect", [
            ("Effet", graph.Imp("$/GFX/EffectCapacity/UnitEffect_Critic_Stop_Armes")), ("UnitGroup", [group])])
        root = bricks.g_seq([card("M1_Abrams_US"), effect, card("BMP_2_SOV")])
        raw = graph.encode(graph.build_graph([root], [camp, group]), "GDScript")
        check_canonical(raw, frozenset(), "GD")
        with self.assertRaisesRegex(CheckError, "IMPR tree is not in index order"):
            gates.check_canonical(raw, frozenset(), "GD", import_rule="preorder")

        nb, _, _ = decode(raw)
        units = next(k for k in nb.imports.children[0].children if nb.tname(k.tran) == "Unit").children
        units[0].obj, units[1].obj = units[1].obj, units[0].obj  # #0 and #2 swap places: not the trie in index order
        with self.assertRaisesRegex(CheckError, "IMPR tree is not the trie"):
            check_canonical(graph.encode(nb, "GDScript"), frozenset(), "GD")

    def test_spike_safe(self):
        """spike_safe is the spike without the shapes no stock file has serialised, any of which might stop the
        whole GDScript loading: no ChangeStress, the Rifles card added without a Transporter, and no ProductionUnites
        with a Transporter and Group (check 7 boards by script there). The rest of check 6 (the kill) stays, the
        content admits none of those shapes, and it builds under its CLI name."""
        tpl, _, _ = decode(read_file(template_gdscript()))
        roots, _ = spike.script(tpl, safe=True)
        nodes = list(graph.walk(roots))
        self.assertEqual(of(nodes, "ChangeStress"), [])
        adds = of(nodes, "AddUnitToDeck")
        self.assertEqual([prop(n, "TypeUnit").path for n in adds if prop(n, "Transporter") is not None], [])
        rifles = [n for n in adds if prop(n, "TypeUnit").path == unit_path("Rifles_US")]
        self.assertEqual([prop(n, "NbUnitsToAdd").v for n in rifles], [2])
        self.assertEqual(len(of(nodes, "KillAllUnit")), 1)
        safe = spike.content(safe=True)
        self.assertEqual(safe.name, "spike_safe")
        admitted = {s[0] for s in safe.extra_shapes} | {s[3] for s in safe.extra_shapes}
        self.assertNotIn("TGDDescriptorChangeStress", admitted)
        self.assertNotIn("TGDDescriptorProductionUnites", admitted)
        self.assertNotIn(("TGDDescriptorAddUnitToDeck", "Transporter"), {s[:2] for s in safe.extra_shapes})
        self.assertEqual(of(nodes, "ProductionUnites"), [])
        self.assertEqual(spike.content().name, "spike")

        out = os.path.join(OUT_ROOT, "spike_safe")
        try:
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(probe_main(["--content", "spike_safe", "--out", out]), 0)
            self.assertTrue(os.path.isfile(os.path.join(out, profile.MOD_NAME, "Scenarios",
                                                        f"{profile.SCENARIO}_Definition.dat")))
            with open(os.path.join(out, "dumps", "GDScript.txt"), encoding="utf-8") as fh:
                dump = fh.read()
            self.assertNotIn("ChangeStress", dump)
            self.assertNotIn("ProductionUnites", dump)
            self.assertNotRegex(dump, r"(?m)^\s*Transporter\s*=")
        finally:
            remove_out(out)

    def test_loaded_helicopter_properties_are_reviewed(self):
        """The spike's ProductionUnites sets Group and Transporter, which no rule of the class names: gate 2's
        ndfrules check passes them only because ndfrules.PROPERTIES reviews them; without that review it fails on
        exactly those two."""
        tpl, _, _ = decode(read_file(template_gdscript()))
        roots, exports = spike.script(tpl)
        nb, _, _ = decode(encode(build_graph(roots, exports), "GDScript"))
        rules, _ = ndfrules.load_table()
        self.assertEqual(ndfrules.violations(nb, rules), [])
        bad = ndfrules.violations(nb, rules, properties={"TGDDescriptorProductionUnites": {}})
        self.assertEqual([b.split("'")[1] for b in bad], ["Group", "Transporter"])

    def test_unstock_shapes_are_admitted_by_the_content(self):
        """Check 6's KillAllUnit DeathCause (stock only in the strategic-campaign tutorials, outside the gate's
        survey) and its ChangeStress (a class the game binds that no stock file uses) pass gate 2 only through the
        content's extra_shapes: without either class's entries, the build fails on that class."""
        out = os.path.join(OUT_ROOT, "spike_bare")
        for cls, error in (("TGDDescriptorKillAllUnit", r"TGDDescriptorKillAllUnit.*DeathCause"),
                           ("TGDDescriptorChangeStress", r"TGDDescriptorChangeStress")):
            with self.subTest(cls=cls):
                kept = tuple(s for s in spike.EXTRA_SHAPES if cls not in (s[0], s[3]))
                self.assertLess(len(kept), len(spike.EXTRA_SHAPES))
                try:
                    with self.assertRaisesRegex(CheckError, error):
                        quiet_build(dataclasses.replace(spike.content(), extra_shapes=kept), out)
                    self.assertFalse(os.path.exists(out))
                finally:
                    remove_out(out)


if __name__ == "__main__":
    unittest.main()
