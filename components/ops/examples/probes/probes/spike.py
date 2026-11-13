"""Probe 1 (`spike`): every scripting mechanism a full mission needs, in one launch, each beat answering one check.

The op is a list of beats (modkit.ops.shapes.Beat). Each timed beat opens with a hint naming its check number, so
what the tester sees can be matched to the checklist (README.md). `script()` lays them out:

  Main: SetDeck x4, HUD hidden, deployment setup (3,000 points, OD_CZ_SW owned), LoadingDone, HUD restored, then
        Simultaneous[ the load beats,
                      the Groupe_Joueur refresh loop,
                      Sequential[ wait for "Launch battle" (hint od_h2), Simultaneous[ one Sequential[wait t, beat]
                                                                                      per timed beat ] ] ]

The load beats start once loading is done and run beside the deployment phase, not in Main's sequence: a load beat may
run long. The A-10A card lock does: LockDeckUnit holds its card only while it runs (shapes.lock_card), and the 60 s
beat sets the flag that ends it.

`spike_safe` (content(safe=True)) is the fallback build, under the same mod name (install one or the other): the spike
without the shapes no stock file has serialised (ChangeStress, AddUnitToDeck's Transporter, ProductionUnites'
Transporter and Group), any of which might stop the whole GDScript loading. It answers every check but those parts
(check 2's transport card, check 6's stress); its check 7 boards the rifles by script instead of spawning them aboard.
"""
from __future__ import annotations

import functools
from typing import Sequence

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.core.models import StringTable, Texts
from modkit.ops import script as ops_script
from modkit.ops.bricks import (
    c_any, c_team, c_type, g_ammo, g_choice, g_cmp, g_collect, g_compete, g_count, g_create, g_detect, g_fx, g_hint,
    g_hold, g_if, g_kill, g_modify, g_seize, g_seq, g_set, g_simul, g_spawn, g_stress, g_until, g_wait, unit_path,
)
from modkit.ops.forces import ForceRow, group_rows, scaled
from modkit.ops.graph import TRUE, Imp, Node, i32
from modkit.ops.mission import board, hidden_units, script_frame
from modkit.ops.profile import Content
from modkit.ops.script import BRICK_FORCE_HIDE
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA_BOXES
from modkit.ops.shapes import (  # noqa: F401  (GRU_WORLD and the order types are the probe's knobs too)
    DEATH_CAUSE_SHAPE, DIVIDE, FAST_MOVE_AND_ATTACK, FOREVER, GRU_WORLD, HINT_S, LAND, PENETRATION, REVEAL_EFFECT,
    SEIZE, SHOOT_ON_POSITION, STRESS_SHAPES, STRICTLY_LESS, STUN, TRANSPORTER_SHAPE, Beat, add_card, beat_hint, create,
    lock_card, move, objective, order, reveal, set_effect,
)
from probes import profile
from probes.geisa import FORCE_SCALE, MAP, ROWS

VARIABLES = f"{profile.FOLDER}/Variables"

# --------------------------------------------------------------------------- knobs

DEPLOY_POINTS = 3000                 # the player's starting points in the deployment phase
# OD_DZ_W, minimap px (x0, y0, x1, y1). x0 13 px is 33,280 world, the west edge of Geisa's own alliance-0 deployment
# zone: the four west-edge arrival Ends (px 24..26) lie inside it. A land unit bought in battle arrives only where its
# entry's End lies in a zone of the player's side (gates.check_arrivals).
DZ_W = (13, 250, 540, 780)
CZ_SW = GEISA_BOXES["TOWN_SW"]       # OD_CZ_SW, minimap px, owned by the player at start
CZ_POINTS = 2                        # CommandPoints Points (stock zones hold 1-5; 2 is the most common)
BUTTON_1X, BUTTON_2X = "CMP_EASY", "CMP_HARD"  # check 5's buttons: stock INGAME 'EASY'/简单, 'HARD'/困难 (start_dialog)
A10_CARD = "A10_Thunderbolt_II_ATGM_US"  # the player deck's A-10A [AT]
T80_COUNT = 10
RESERVE_SPACING_PX = 8.0             # 4 hidden tanks in a 2 x 2 box this far apart, centred on the point
RING_S_PX, BOX_MID_PX, BOX_S_PX = 30.0, 25.0, 26.0  # OD_RingS at HIDE S, OD_BoxMid at NECK MID, OD_BoxS at NECK S
PROBE_WAYPOINTS = ((600, 645), (570, 710))  # minimap px of the forest track, then OD_RingS (HIDE S)
RING_HOLD_S = 20.0                   # a probe unit this long in OD_RingS without a break shows od_h4r
COLUMN_UNIT, COLUMN_COUNT = "BMP_2_SOV", 6
DECOY_UNIT, DECOY_COUNT = "M1_Abrams_US", 2  # per group, od_decoyA and od_decoyB
DECOY_EFFECTS = ("UnitEffect_Critic_Chenille_Detruite",)  # tracks broken (a weapons-jammed critical lets them fire)
DECOY_REAPPLY_S = 30.0               # od_decoyB is emptied again (SetAmmo) this often
WARNING_S = 20.0                     # each fire comes this long after its warning hint
FX_BOMB = "$/GFX/GameFx/fx_HE_Artillery_203mm_ForScript_RandomPosition"  # stock barrage FX (BackhandBlow #79-#85)
BOX_S_FX = ((0, -12), (-11, 7), (11, 7))  # px offsets from NECK S of the FX tags, inside OD_BoxS
BOX_CAP = 50                         # the halving loop moves at most this many units to od_struck
STRESS_VALUE = 240                   # ChangeStress Value: 0.8 x GroundUnit_MaxStunDamages (300), the top level
F4G_CARD = "F4_Wild_Weasel_US"
POCKET_FUEL = 25                     # SetFuel MaxFuelRatio on od_pocket_ad
BOARD_TIMEOUT_S = 60.0               # the 7:00 boarding gives up after this long and the helicopter flies anyway
LAND_WAIT_S = 5.0                    # spike_safe's 7:00 beat: the instant Land order gets this long before the boarding
SEED_UNIT, SEED_COUNT = "BMP_2_SOV", 4  # od_boxseed, created in BOX S at 6:00 so the 6:20 strike always has targets
SAM_WAIT_S = 60.0                    # the 8:00 pocket AD waits at most this long for the air assault's unload flag

EXTRA_SHAPES = (
    # Check 2 asks whether AddUnitToDeck's Transporter works (shapes.add_card).
    TRANSPORTER_SHAPE,
    # Check 6 kills with Penetration.
    DEATH_CAUSE_SHAPE,
    # Check 6 stuns with ChangeStress, a class no stock file uses (shapes.STRESS_SHAPES: the class, its properties, and
    # its place in a Sequential, the 6:00 beat's) [[changestress-damagetype-zero]].
    *STRESS_SHAPES,
    # Check 7: the UH-60A spawned with its AeroRifles aboard. ProductionUnites is stock (SigurdsStrike #1046-#1055),
    # but none of its 6 objects sets Group or Transporter; the class has both, and its load check tests
    # neither (modkit.core.ndfrules).
    ("TGDDescriptorProductionUnites", "Group", 0x09, "TGDVariableUnitGroup"),
    ("TGDDescriptorProductionUnites", "Transporter", 0x09, "import $/GFX/Unit"),
)
SAFE_DROPS = ("TGDDescriptorChangeStress", "TGDDescriptorProductionUnites")  # spike_safe emits neither class


# --------------------------------------------------------------------------- frame

class Ctx(profile.Ctx):
    """The probes' Ctx over `items` (default ITEMS) keyed to `scenario`. `safe` builds spike_safe: the beats leave out
    ChangeStress and AddUnitToDeck's Transporter, and check 7 boards the rifles by script."""

    def __init__(self, safe: bool = False, items: Sequence[LdItem] | None = None,
                 scenario: str = profile.SCENARIO) -> None:
        self.safe = safe
        super().__init__(ITEMS if items is None else items, scenario)


def hidden_spawns(prefix: str, point: str, unit: str) -> list[LdItem]:
    """Four player (camp 0) units in a 2 x 2 box around `point` that stay hidden until a SpawnUnits reveals them
    (check 3; modkit.ops.mission.hidden_units), named <prefix>_1 to <prefix>_4, in the item group "reserves"."""
    return hidden_units(MAP, MAP.points[point], [(f"{prefix}_{k + 1}", unit) for k in range(4)], RESERVE_SPACING_PX, 2,
                        "reserves")


def hidden_row(group: str, point: str, *units: tuple[str, str]) -> list[LdItem]:
    """Player (camp 0) units, (item name, unit) each, in a row RESERVE_SPACING_PX apart centred on `point`, hidden
    until a SpawnUnits reveals them (modkit.ops.mission.hidden_units)."""
    return hidden_units(MAP, MAP.points[point], units, RESERVE_SPACING_PX, len(units), group)


def force_rows(group: str) -> list[ForceRow]:
    """The ROWS of `group` at FORCE_SCALE."""
    return group_rows(ROWS, group, FORCE_SCALE)


def stress_rows(scale: float) -> list[ForceRow]:
    """The 10:00 stress wave (check 8): the main_body and relief rows at `scale`."""
    return [r for r in scaled(ROWS, scale) if r.group in ("main_body", "relief")]


def point_tag(ctx: Ctx, point: str) -> Node:
    """The GdItems tag of the Name item standing on named point `point` (PL_BLUE is VILLAGE_E's)."""
    at = MAP.map.px_to_world(MAP.points[point])
    names = [it.name for it in ctx.items if it.addon == "Name" and (it.x, it.y) == at]
    check(len(names) == 1, f"{len(names)} Name items stand on {point}")
    return ctx.tag(names[0])


def create_row(ctx: Ctx, row: ForceRow, group: Node, at: str | None = None) -> Node:
    """create() of one force row into `group`, in the row's camp, at point `at` or else the row's spawn. A row with a
    transport is created as units of its own beside its carriers' row."""
    return create(ctx, row.camp, group, row.count, point_tag(ctx, at or row.spawn), unit_path(row.descriptor))


# --------------------------------------------------------------------------- items

ITEMS: list[LdItem] = [
    MAP.item("Tags", "OD_TownNE", "TOWN_NE", "Name"),
    MAP.item("Tags", "OD_NeckMid", "NECK_MID", "Name"),
    MAP.item("Tags", "OD_EntryE", "ENTRY_E", "Name"),
    MAP.item("Tags", "OD_VillageE", "VILLAGE_E", "Name"),
    MAP.zone_item("DeploymentZone", "OD_DZ_W", DZ_W, "DeploymentZone"),
    MAP.zone_item("CommandPoints", "OD_CZ_SW", CZ_SW, "CommandPoints", points=CZ_POINTS),
    *MAP.map.player_arrivals("OD"),  # where units bought after the launch arrive: Geisa's west-edge entries
    *hidden_spawns("OD_ResN", "RESERVE_N", "M1A1HA_Abrams_US"),
    *hidden_spawns("OD_HideS", "HIDE_S", "Leopard_2A4_RFA"),
    # the probe (check 4)
    MAP.item("Tags", "OD_TrackSeIn", "TRACK_SE_IN", "Name"),
    *(MAP.item("Tags", f"OD_ProbeWp{k + 1}", px, "Name") for k, px in enumerate(PROBE_WAYPOINTS)),
    MAP.ring_item("OD_RingS", "HIDE_S", RING_S_PX),
    # the fires (check 6): the battery's corner, the two boxes and the FX tags across BOX S (LaunchFX takes a Name
    # tag, never a zone, in all 75 stock uses)
    MAP.item("Tags", "OD_CornerPact", "CORNER_PACT", "Name"),
    MAP.ring_item("OD_BoxMid", "NECK_MID", BOX_MID_PX),
    MAP.ring_item("OD_BoxS", "NECK_S", BOX_S_PX),
    *(MAP.item("Tags", f"OD_BoxS_Fx{k + 1}", (MAP.points["NECK_S"][0] + dx, MAP.points["NECK_S"][1] + dy), "Name")
      for k, (dx, dy) in enumerate(BOX_S_FX)),
    # the air assault (check 7). No stock Spawn add-on carries passengers (every TGameDesignAddOn_Spawn holds only
    # Name, Ranking, GUID, AutoNameBase, Camp, ClassName, ExperienceLevel, DisableAutoSpawn, Dead and
    # NbOfUnitToSpawn), so the AeroRifles get their own hidden item beside the helicopter, as Survivors' start
    # infantry stand beside their FV432s, which its script boards with LoadIntoTransporter (Survivors #785-#789).
    # spike_safe's 7:00 beat boards them the same way; the spike's makes the rifles aboard instead (air_assault) and
    # leaves these two hidden.
    *hidden_row("air_assault", "EDGE_N", ("OD_AA_Helo", "UH60A_Black_Hawk_US"), ("OD_AA_Rifles", "AeroRifles_US")),
    MAP.item("Tags", "OD_EdgeN", "EDGE_N", "Name"),  # where the spike's loaded helicopter appears
    MAP.item("Tags", "OD_LzMid", "LZ_MID", "Name"),
    # air (check 10)
    *hidden_row("apaches", "EDGE_W", ("OD_Apache_1", "AH64_Apache_emp1_US"), ("OD_Apache_2", "AH64_Apache_emp1_US")),
    MAP.item("Tags", "OD_HoldW", "HOLD_W", "Name"),
    MAP.item("Tags", "OD_SackMid", "SACK_MID", "Name"),
    # the stress wave (check 8): its rows' spawns and its target
    MAP.item("Tags", "OD_EntryN", "ENTRY_N", "Name"),
    MAP.item("Tags", "OD_EntryNE", "ENTRY_NE", "Name"),
    MAP.item("Tags", "OD_TownSW", "TOWN_SW", "Name"),
]


# --------------------------------------------------------------------------- beats

def load_deck(ctx: Ctx) -> Node:
    """Check 2 at load: the RFA card, the card with a Transporter (spike_safe: the same card without one), and the
    A-10A card locked until the 60 s beat sets od_a10 (shapes.lock_card)."""
    return g_seq([add_card(ctx, "Leopard_2A4_RFA", 2),
                  add_card(ctx, "Rifles_US", 2, transport=None if ctx.safe else "M113A3_US"),
                  lock_card(ctx, A10_CARD, g_cmp(ctx.int_var("od_a10"), 1))])


def start_dialog(ctx: Ctx) -> Node:
    """Check 5 at 0:00: the multiple-choice dialog (Sledgehammer #590/#621 shape) and its routing (SigurdsStrike
    #498: button 0 pressed = SelectedButton Equal 0). Button EASY sets od_scale 1, HARD sets it 2; each branch shows
    its own hint. The labels are stock INGAME tokens (CMP_EASY 'EASY'/简单, CMP_HARD 'HARD'/困难): the game looks
    button labels up in INGAME only (gates.INGAME_PROPS). The dialog text says which button runs which scale."""
    chosen, scale = ctx.int_var("od_choice"), ctx.int_var("od_scale")
    dialog = g_choice("od_start", BUTTON_1X, BUTTON_2X, ctx.camp("NATO"), chosen)
    return g_seq([dialog, g_if(g_cmp(chosen),
                               g_simul([g_set(scale, 1), g_hint("od_h5a", HINT_S, "shint")]),
                               g_simul([g_set(scale, 2), g_hint("od_h5b", HINT_S, "shint")]))])


def markers(ctx: Ctx) -> Node:
    """Check 1 at 0:05: two objectives with map markers on the TOWN NE and NECK MID tags, which check the px/world
    transform. Nothing sets od_marks, so they stay up for the whole session."""
    up = ctx.int_var("od_marks")
    return beat_hint("od_h1",
                     objective("od_obj1a", "od_lbl1a", g_cmp(up, 1), ctx.tag("OD_TownNE")),
                     objective("od_obj1b", "od_lbl1b", g_cmp(up, 1), ctx.tag("OD_NeckMid")))


def t80_company(ctx: Ctx) -> Node:
    """Checks 4 and 11 at 0:30: 10 T-80BV at ENTRY E fast-move-and-attack by road to VILLAGE E (blocking), then
    seize NECK MID. Objective od_obj4 counts their losses: lost = 10 - alive, polled each second (DelayedRetribution
    #343) and written in one step from a scratch variable, so the objective never reads a half-done value."""
    t80 = ctx.group("od_t80")
    alive, scratch, lost = ctx.int_var("od_t80_alive"), ctx.int_var("od_t80_tmp"), ctx.int_var("od_t80_lost")
    count = g_seq([g_count(alive, t80), g_set(scratch, T80_COUNT), g_modify(scratch, 2, other=alive),
                   g_set(lost, other=scratch), g_wait(1.0)], runs=FOREVER)
    attack = g_seq([order(t80, FAST_MOVE_AND_ATTACK, ctx.tag("OD_VillageE"), blocking=True),
                    g_seize(t80, ctx.tag("OD_NeckMid"))])   # LaunchSmartOrder Seize (SmartOrderType SEIZE)
    return beat_hint("od_h4", g_seq([
        create(ctx, "PACT", t80, T80_COUNT, ctx.tag("OD_EntryE"), unit_path("T80BV_SOV")),
        reveal([t80], [
            g_until(g_cmp(t80, 1, 2)),                   # the company exists before its losses are counted
            g_simul([count, objective("od_obj4", "od_obj4l", g_cmp(lost, T80_COUNT, 2), counters=[lost]), attack]),
        ]),
    ]))


def unlock_a10(ctx: Ctx) -> Node:
    """Check 2 at 1:00: od_a10 = 1 ends the load beat's lock race, which unlocks the A-10A card."""
    return beat_hint("od_h2b", g_set(ctx.int_var("od_a10"), 1))


def reserves(ctx: Ctx) -> Node:
    """Check 3 at 3:00: SpawnUnits reveals the eight hidden camp 0 tanks at RESERVE N and HIDE S (in a Sequential:
    stock never puts SpawnUnits straight in a Simultaneous)."""
    return beat_hint("od_h3", g_seq([g_spawn([ctx.tag(it.name) for it in ITEMS if it.group == "reserves"])]))


def decoys(ctx: Ctx) -> Node:
    """Check 9 at 0:20: 2 + 2 M1s in the Decoys camp (Survivors' Allie, AI-controlled) on PL BLUE, both emptied by
    SetAmmo and given the broken-tracks critical by SetEffect; od_decoyB is emptied again every 30 s and od_decoyA is
    not, so the tester can see whether they hold without the loop (a resupply could refill A). The weapons-jammed
    critical only zeroes ranges and locks the turret, so the decoys are emptied instead, as Survivors spawns its
    abandoned T-55 with no ammunition: SetAmmo with Units only, MaxAmmoRatio left at its 0 (bricks.g_ammo).

    SetAmmo is instantaneous, so both run first. SetEffect never finishes and holds its effect only while it runs, so
    one SetEffect on both groups runs, as the beat's last node, beside the re-empty loop (reveal()'s shape); being a
    live binding, it needs no re-applying."""
    groups, camp, at = [ctx.group("od_decoyA"), ctx.group("od_decoyB")], ctx.camp("Decoys"), point_tag(ctx, "PL_BLUE")
    return beat_hint("od_h9", g_seq([
        *(g_create(camp, g, DECOY_COUNT, at, unit_path(DECOY_UNIT)) for g in groups),
        *(g_ammo([g]) for g in groups),
        g_simul([*(set_effect(e, groups) for e in DECOY_EFFECTS),
                 g_seq([g_wait(DECOY_REAPPLY_S), g_ammo([groups[1]])], runs=FOREVER)]),
    ]))


def probe(ctx: Ctx) -> Node:
    """Check 4 at 1:30: the probe rows at TRACK SE IN take the forest-track waypoints to HIDE S. Once one of the
    probe's units has stayed in ring OD_RingS for 20 s without a break (bricks.g_hold), od_h4r shows: the exposure
    branch. The ring counts the probe's own unit types, since no stock constraint selects a unit group."""
    group, ring, rows = ctx.group("od_probe"), ctx.tag("OD_RingS"), force_rows("probe")

    def in_ring(value: int | None = None, op: int | None = None) -> Node:
        return g_detect(ring, c_any(*(c_type(r.descriptor) for r in rows)), value, op)

    waypoints = [ctx.tag(f"OD_ProbeWp{k + 1}") for k in range(len(PROBE_WAYPOINTS))]
    return beat_hint("od_h4p", g_seq([
        *(create_row(ctx, r, group) for r in rows),
        reveal([group], [
            move(group, *waypoints, ring),
            g_hold(lambda: in_ring(1, 2), in_ring, RING_HOLD_S, ctx.int_var("od_probe_in")),  # >= 1 held; 0 breaks
            g_simul([g_hint("od_h4r", HINT_S, "shint")]),  # stock holds an LDHint in a Simultaneous, not a Sequential
        ]),
    ]))


def column(ctx: Ctx) -> Node:
    """Check 3 at 2:00: 6 BMP-2 from ENTRY E down the defile to NECK S (OD_BoxS stands on it), past HIDE S, before
    the 3:00 reveal."""
    group = ctx.group("od_column")
    return beat_hint("od_h3c", g_seq([
        create(ctx, "PACT", group, COLUMN_COUNT, ctx.tag("OD_EntryE"), unit_path(COLUMN_UNIT)),
        reveal([group], [move(group, ctx.tag("OD_BoxS"))]),
    ]))


def battery(ctx: Ctx) -> Node:
    """Check 6 at 5:00: the opener battery rows at CORNER PACT, then 20 s after the warning hint, ShootOnPosition
    into OD_BoxMid (GiveOrderStandard OrderType 31 on a zone: stock's artillery ShootOnPosition is TheWingedHussars
    #362 and Marauders #1341/#1352/#1353, on CommandPoints)."""
    group = ctx.group("od_battery")
    return beat_hint("od_h6a", g_seq([
        *(create_row(ctx, r, group) for r in force_rows("opener_battery")),
        reveal([group], [g_wait(WARNING_S), order(group, SHOOT_ON_POSITION, ctx.tag("OD_BoxMid"))]),
    ]))


def strike(ctx: Ctx) -> Node:
    """Check 6 at 6:00: 20 s after the warning hint, the scripted NATO strike on BOX S. With the hint, 4 BMP-2 are
    created in the box (od_boxseed, PACT; CreateUnitOnPosition on a CircularZone, as RunningTheGauntlet's
    Noise_Bravo_Spawn), so the strike has targets whether or not the 2:00 column is still there; the column adds to
    them. Impact FX land across the box (BackhandBlow #70's Simultaneous of FX). The Soviet units inside go into
    od_boxed (AddDetectedUnitsToUnitGroup: can the script select the units inside a box?), and od_obj6 shows how many
    were caught. Half of them, rounded down, move one at a time to od_struck (NBToTransfert is a constant, so a bounded
    loop repeats a one-unit TransferUnitToUnitGroup while od_struck < half), which KillAllUnit destroys with
    Penetration; ChangeStress stuns the rest (not in spike_safe)."""
    boxed, struck = ctx.group("od_boxed"), ctx.group("od_struck")
    caught, half = ctx.int_var("od_boxed_n"), ctx.int_var("od_half")
    transfer = Node("TGDDescriptorTransferUnitToUnitGroup", [  # Sledgehammer #612's order, without CopyUnits
        ("GroupDestination", struck), ("GroupSource", boxed), ("NBToTransfert", i32(1))])
    seed = ctx.group("od_boxseed")
    return beat_hint("od_h6b", g_seq([
        create(ctx, "PACT", seed, SEED_COUNT, ctx.tag("OD_BoxS"), unit_path(SEED_UNIT)),
        reveal([seed], [
            g_wait(WARNING_S),
            g_simul([g_fx(FX_BOMB, ctx.tag(f"OD_BoxS_Fx{k + 1}")) for k in range(len(BOX_S_FX))]),
            g_collect(boxed, g_detect(ctx.tag("OD_BoxS"), c_team(ctx.camp("PACT")), compare=False)),
            g_count(caught, boxed),
            g_set(half, other=caught),
            g_modify(half, DIVIDE, 2),
            g_seq([g_if(g_cmp(struck, op=STRICTLY_LESS, other=half), g_seq([transfer]))], runs=BOX_CAP),
            g_kill(struck, cause=PENETRATION),
            *([] if ctx.safe else [g_stress(boxed, STRESS_VALUE, STUN)]),
            objective("od_obj6", "od_obj6l", g_cmp(ctx.int_var("od_obj6_end"), 1), counters=[caught]),  # stays up
        ]),
    ]))


def produce_loaded(ctx: Ctx, group: Node, unit: str, transport: str, at: Node) -> Node:
    """ProductionUnites of one `unit` inside a `transport` (unit_path suffixes) into `group`, in NATO's camp, at tag
    `at`. Property order and value forms are stock's (SigurdsStrike #1046-#1048, #1053-#1055: Camp, NbUnit <int32> 1,
    Position a GdItems tag, ProduceOutMap, TypeUnit an import), with the natives' alphabetical order for the two
    properties stock never sets: Group after Camp, Transporter before TypeUnit (as in add_card). ProduceOutMap is left
    out (False): stock's True brings its aircraft in from off the map, and this unit must appear at `at`."""
    return Node("TGDDescriptorProductionUnites", [
        ("Camp", ctx.camp("NATO")), ("Group", group), ("NbUnit", i32(1)), ("Position", at),
        ("Transporter", Imp(unit_path(transport))), ("TypeUnit", Imp(unit_path(unit)))])


def air_assault(ctx: Ctx) -> Node:
    """Check 7 at 7:00: a UH-60A carries AeroRifles from EDGE N to LZ MID and unloads them there (UnloadFromTransporter
    at a position, SigurdsStrike #425), every step blocking; then od_aa_down = 1 lets the 8:00 beat's air defence
    appear at SACK MID, about 50 px from LZ MID. No stock script boards a helicopter (all 57 LoadIntoTransporter
    target ground vehicles).

    spike: one ProductionUnites makes the AeroRifles inside a UH-60A (its Transporter: the stock deck pack
    AeroRifles_US + UH60A_Black_Hawk_US) into the new group od_aa at OD_EdgeN, which then moves to LZ MID and unloads.
    No stock script sets Transporter, so whether the cargo is placed aboard, and which units join od_aa (the
    helicopter, the rifles, or both), is what the run tells; the move and the unload both name od_aa and take
    whatever it holds.

    spike_safe (ctx.safe): SpawnUnits reveals the hidden UH-60A and AeroRifles items at EDGE N. The helicopter is
    ordered to land, non-blocking and with no Position (Land is an instant order with no target; stock positionless
    GiveOrderStandard, Survivors #1453), then a LAND_WAIT_S wait, then the rifles board (modkit.ops.mission.board:
    LoadIntoTransporter, Survivors #786's shape) blocking, raced against BOARD_TIMEOUT_S so a boarding that never ends
    cannot hold the flight; then the move and the unload."""
    lz = ctx.tag("OD_LzMid")
    if ctx.safe:
        helo, rifles = ctx.tag("OD_AA_Helo"), ctx.tag("OD_AA_Rifles")
        land = Node("TGDDescriptorGiveOrderStandard", [("Group", helo), ("OrderType", i32(LAND))])
        steps = [g_spawn([ctx.tag(it.name) for it in ITEMS if it.group == "air_assault"]),
                 land, g_wait(LAND_WAIT_S),
                 board(rifles, helo, BOARD_TIMEOUT_S)]
    else:
        helo = ctx.group("od_aa")
        steps = [produce_loaded(ctx, helo, "AeroRifles_US", "UH60A_Black_Hawk_US", ctx.tag("OD_EdgeN"))]
    return beat_hint("od_h7", g_seq([
        *steps,
        move(helo, lz, blocking=True),
        Node("TGDDescriptorUnloadFromTransporter", [("Blocking", TRUE), ("Group", helo), ("Position", lz)]),
        g_set(ctx.int_var("od_aa_down"), 1),
    ]))


def air(ctx: Ctx) -> Node:
    """Check 10 at 8:00: SpawnUnits reveals the two AH-64A at EDGE W, which move to HOLD W; one F-4G card joins the
    deck; then, once the air assault has unloaded (od_aa_down = 1) or after 60 s, whichever comes first, the
    pocket_ad rows are created at SACK MID and get SetFuel 25. The 7:00 boarding may let the helicopter leave as late
    as 8:00, and SACK MID lies about 50 px from LZ MID: the air defence must not meet it on its way in."""
    apaches, pocket = [ctx.tag(it.name) for it in ITEMS if it.group == "apaches"], ctx.group("od_pocket_ad")
    return beat_hint("od_h10", g_seq([
        g_spawn(apaches),
        *(move(a, ctx.tag("OD_HoldW")) for a in apaches),
        add_card(ctx, F4G_CARD, 1),
        g_compete([g_until(g_cmp(ctx.int_var("od_aa_down"), 1)), g_wait(SAM_WAIT_S)]),
        *(create_row(ctx, r, pocket, at="SACK_MID") for r in force_rows("pocket_ad")),
        reveal([pocket], [Node("TGDDescriptorSetFuel", [("MaxFuelRatio", i32(POCKET_FUEL)), ("Units", [pocket])])]),
    ]))


def stress_wave(ctx: Ctx) -> Node:
    """Check 8 at 10:00: stress_rows at the scale the start dialog chose (od_scale 2: 2x; anything else: 1x), each
    row into od_stress_<group> at its spawn, then both groups FastMoveAndAttack (by road) to TOWN SW. Every row is
    created first; the orders run beside the one reveal of both groups."""

    def wave(scale: float) -> Node:
        rows = stress_rows(scale)
        groups = [ctx.group(f"od_stress_{g}") for g in dict.fromkeys(r.group for r in rows)]
        return g_seq([*(create_row(ctx, r, ctx.group(f"od_stress_{r.group}")) for r in rows),
                      reveal(groups, [order(g, FAST_MOVE_AND_ATTACK, ctx.tag("OD_TownSW")) for g in groups])])

    return beat_hint("od_h8", g_seq([g_if(g_cmp(ctx.int_var("od_scale"), 2), wave(2.0), wave(1.0))]))


BEATS: list[Beat] = [
    Beat(None, "2", load_deck),
    Beat(0.0, "5", start_dialog),
    Beat(5.0, "1", markers),
    Beat(20.0, "9", decoys),   # not 0:05: its hint would collide with od_h1's
    Beat(30.0, "4,11", t80_company),
    Beat(60.0, "2", unlock_a10),
    Beat(90.0, "4", probe),
    Beat(120.0, "3", column),
    Beat(180.0, "3", reserves),
    Beat(300.0, "6", battery),
    Beat(360.0, "6", strike),
    Beat(420.0, "7", air_assault),
    Beat(480.0, "10", air),
    Beat(600.0, "8", stress_wave),
]


# --------------------------------------------------------------------------- strings

STRINGS: StringTable = {
    "SCENARIO_DEFINITION": {  # menu tokens, each text at most 30 UTF-16 units
        "od_name": Texts(US="Open Door: spike", SC="开门行动：机制测试"),
        "od_cname": Texts(US="OPEN DOOR: SPIKE", SC="开门行动：机制测试"),
        "od_headr": Texts(US="Open Door spike checklist", SC="开门行动测试清单"),
        "od_order": Texts(US="Each hint names its check.", SC="每条提示都标明检查编号。"),
        "od_recap": Texts(US="Test op: 11 checks in one run", SC="测试行动：一局完成11项检查"),
        "od_vic": Texts(US="Spike complete.", SC="测试完成。"),
        "od_def": Texts(US="Spike ended.", SC="测试结束。"),
    },
    "Scripting/Dialog": {
        "od_start": Texts(US="#bold{CHECK 5: choose the stress test scale.}\n"
                             "EASY: the 10:00 stress wave at 1x. HARD: the same wave at 2x.\n"
                             "Play once per button. Every later hint names its check number.",
                          SC="#bold{检查5：选择压力测试规模。}\n"
                             "简单：10:00的压力测试按1x兵力进行。困难：按2x兵力进行。\n"
                             "每个按钮各玩一局。之后的每条提示都会标明检查编号。"),
    },  # the buttons' own labels are stock INGAME tokens (BUTTON_1X, BUTTON_2X), not ours
    "Scripting/Localization": {
        "od_cnato": Texts(US="NATO", SC="北约"),
        "od_cdecoy": Texts(US="NATO decoys", SC="北约佯动部队"),  # 诱饵 (decoy) is outside the stock SC set
        "od_cddr": Texts(US="NVA", SC="东德军"),
        "od_csov": Texts(US="Soviet Army", SC="苏军"),
        "od_h1": Texts(US="CHECK 1: two markers, on TOWN NE and NECK MID. Are they where the map shows those places?",
                       SC="检查1：TOWN NE和NECK MID上各有一个标记。它们是否位于地图上相应的地点？"),
        "od_h2": Texts(US="CHECK 1, 2: deploy in the west zone (3,000 points). Deck: is the A-10A [AT] card locked? "
                          "Are the Leopard 2A4 card and the Rifles in M113A3 card there? Which badge shows?",
                       SC="检查1、2：在西侧部署区部署（3,000点）。卡组：A-10A [AT]卡是否已锁定？是否有Leopard 2A4卡和乘坐"
                          "M113A3的步兵卡？显示的是哪个师的标志？"),  # 徽 (badge) was outside the stock SC set of the time
        "od_h2b": Texts(US="CHECK 2: the A-10A [AT] card should be unlocked now.", SC="检查2：A-10A [AT]卡现在应已解锁。"),
        "od_h3": Texts(US="CHECK 3: reserves revealed: 4 M1A1HA at RESERVE N and 4 Leopard 2A4 at HIDE S. Can you "
                          "command them?",
                       SC="检查3：预备队已出现：RESERVE N有4辆M1A1HA，HIDE S有4辆Leopard 2A4。您能指挥它们吗？"),
        "od_h4": Texts(US="CHECK 4, 11: 10 T-80BV attack from ENTRY E through VILLAGE E, then seize NECK MID. Do they "
                          "fight convincingly?",
                       SC="检查4、11：10辆T-80BV从ENTRY E经VILLAGE E发起进攻，随后夺取NECK MID。它们的战斗表现是否可信？"),
        "od_h5a": Texts(US="CHECK 5: you chose 1x. The 10:00 stress wave runs at 1x.",
                        SC="检查5：您选择了1x。10:00的压力测试按1x兵力进行。"),
        "od_h5b": Texts(US="CHECK 5: you chose 2x. The 10:00 stress wave runs at 2x.",
                        SC="检查5：您选择了2x。10:00的压力测试按2x兵力进行。"),
        "od_obj1a": Texts(US="CHECK 1: marker on TOWN NE", SC="检查1：TOWN NE标记"),
        "od_obj1b": Texts(US="CHECK 1: marker on NECK MID", SC="检查1：NECK MID标记"),
        "od_lbl1a": Texts(US="TOWN NE", SC="TOWN NE"),
        "od_lbl1b": Texts(US="NECK MID", SC="NECK MID"),
        "od_obj4": Texts(US="Destroy %1 / 10 T-80BV", SC="摧毁%1 / 10辆T-80BV"),
        "od_obj4l": Texts(US="%1 / 10", SC="%1 / 10"),
        "od_h3c": Texts(US="CHECK 3: a column of 6 BMP-2 drives from ENTRY E down the defile to NECK S. The HIDE S "
                           "reserves appear at 3:00, with the column nearby.",
                        SC="检查3：一支由6辆BMP-2组成的纵队从ENTRY E沿山谷驶向NECK S。HIDE S的预备队将在3:00出现，"
                           "那时纵队就在附近。"),
        "od_h4p": Texts(US="CHECK 4: a 4-unit recon probe leaves TRACK SE IN on the forest track to HIDE S. Does it "
                           "stay on the track instead of detouring onto the main roads?",
                        SC="检查4：一支4个单位的侦察分队从TRACK SE IN沿林间小路前往HIDE S。它是否一直沿小路行进，"
                           "而没有绕上大路？"),
        "od_h4r": Texts(US="CHECK 4: a probe unit has stayed in the HIDE S ring for 20 s: the exposure branch fired.",
                        SC="检查4：一个侦察单位已在HIDE S圈内停留20秒：暴露分支已触发。"),
        "od_h6a": Texts(US="CHECK 6: WARNING: in 20 s, Soviet artillery in the NE corner fires on BOX MID (NECK MID).",
                        SC="检查6：警告：20秒后，东北角的苏军炮兵将炮击BOX MID（NECK MID）。"),
        "od_h6b": Texts(US="CHECK 6: WARNING: NATO strike on BOX S (NECK S) in 20 s. Half the Soviet units in it are "
                           "destroyed and the rest stunned. Does the objective count them?",
                        SC="检查6：警告：20秒后，北约将打击BOX S（NECK S）。其中一半苏军单位将被摧毁，其余将被击昏。"
                           "目标是否统计了它们的数量？"),
        "od_h7": Texts(US="CHECK 7: a UH-60A with AeroRifles appears at EDGE N and should fly them to LZ MID and "
                          "unload them there. If the rifles appear outside the helicopter and have not boarded after "
                          "30 s, board them by hand. Can you command both?",
                       SC="检查7：一架UH-60A和空降步兵出现在EDGE N，直升机应载着步兵飞往LZ MID并让他们下机。如果步兵出现在"
                          "直升机外，且30秒后仍未登机，请手动让他们登机。您能指挥两者吗？"),
        "od_h8": Texts(US="CHECK 8: the stress wave, main body and relief at the scale you chose, attacks from ENTRY N "
                          "and ENTRY NE towards TOWN SW. Note the frame rate.",
                       SC="检查8：压力测试波次（主力和增援部队，按您选择的规模）从ENTRY N和ENTRY NE向TOWN SW发起进攻。"
                          "请记下FPS。"),
        "od_h9": Texts(US="CHECK 9: 4 decoy M1 (an AI camp) on PL BLUE with broken tracks and no ammunition; 2 of them "
                          "are emptied again every 30 s. Do they stay put and silent, outside your control and losses?",
                       SC="检查9：PL BLUE上有4辆佯动M1（AI阵营），无法移动且没有弹药；其中2辆每30秒重新清空弹药。"
                          "它们是否原地不动、保持沉默，并且不受您控制、不计入您的损失？"),
        "od_h10": Texts(US="CHECK 10: 2 AH-64A arrive at EDGE W and move to HOLD W. An F-4G card is in your deck. The "
                           "6 Soviet air-defence vehicles at SACK MID have a quarter of their fuel. Do the F-4G's "
                           "anti-radar missiles fire on the Osa or Tunguska?",
                        SC="检查10：2架AH-64A从EDGE W抵达并前往HOLD W。您的卡组中新增了一张F-4G卡。SACK MID的6辆苏军"
                           "防空车辆只剩四分之一燃料。F-4G的反辐射导弹是否会攻击Osa或Tunguska？"),
        "od_obj6": Texts(US="Units caught in BOX S: %1", SC="BOX S内被困单位：%1"),
        "od_obj6l": Texts(US="%1", SC="%1"),
    },
}


# --------------------------------------------------------------------------- script and content

def script(tpl: ndfbin.NdfBin, safe: bool = False) -> tuple[list[Node], list[Node]]:
    """The spike's GDScript (layout in the module docstring; modkit.ops.mission.script_frame), from Survivors' GDScript
    template `tpl`; `safe`: spike_safe's."""
    ctx = Ctx(safe)
    deploy = ops_script.deploy_phase(tpl, profile.TEMPLATES, ctx.camp("NATO"), ctx.group("Groupe_Joueur"),
                                     [ctx.tag("OD_CZ_SW")], points=DEPLOY_POINTS, income=profile.PLAYER_INCOME,
                                     hint="od_h2", refresh_export=profile.REFRESH_EXPORT, refresh_s=profile.REFRESH_S)
    return script_frame(tpl, profile.TEMPLATES, ctx, deploy, BEATS, camp_rows=profile.CAMP_ROWS, folder=profile.FOLDER,
                        start_delay_s=profile.START_DELAY_S, prod_menu_switch=BRICK_FORCE_HIDE)


def content(safe: bool = False) -> Content:
    """The spike, or with `safe` spike_safe, whose script leaves out ChangeStress, AddUnitToDeck's Transporter and the
    loaded-helicopter ProductionUnites, and whose shape gate admits none of them."""
    if not safe:
        return profile.content("spike", ITEMS, script, STRINGS, profile.MENU_TOKENS, extra_shapes=EXTRA_SHAPES)
    shapes = tuple(s for s in EXTRA_SHAPES if not {s[0], s[3]} & set(SAFE_DROPS) and s != TRANSPORTER_SHAPE)
    return profile.content("spike_safe", ITEMS, functools.partial(script, safe=True), STRINGS, profile.MENU_TOKENS,
                           extra_shapes=shapes)
