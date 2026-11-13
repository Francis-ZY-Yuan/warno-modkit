"""Probe 2 (`spike2`): the mission mechanics no reading can settle, in one install and three short runs.

It is its own scenario, challenge_OpenDoorTest, in its own mod folder, OpenDoorTest, with its own GUID and menu tokens
(o2_*), so it installs beside probe 1 (OpenDoorOps).

The start dialog picks the run. ALL (C_ALL) is the full test, which ends at 15:00 through the end dialog; FAST
(HTP_SPDFAT) is the quick run, which ends in the ending race 30 s after the dialog is answered. Run A: Medium, ALL,
VICTORY!. Run B: Easy, FAST. Run C: Hard, FAST (the race's order flips on Hard).

As in probe 1, the op is a list of beats (modkit.ops.shapes.Beat), each its own branch of the battle Simultaneous:

  Main: SetDeck x4, HUD hidden, deployment setup (3,000 points; OD_CZ_SW, CAP A, CAP B and TOWN NE owned: the load
        beat's forced ownership), LoadingDone, HUD restored, then
        Simultaneous[ the load beats (deck cards, the defeat guard),
                      the Groupe_Joueur refresh loop,
                      the end funnel ($/GDScript/OD/EndFunnel: always running),
                      Sequential[ wait for "Launch battle" (hint od_hdep), Simultaneous[ one Sequential[wait t, beat]
                                                                                       per timed beat ] ] ]

The timed beats: 0:00 start dialog; 0:00 the race (it waits for the dialog's answer, then 30 s); 0:05 difficulty; 0:10
objectives; 0:15 counters; 1:00 capture (CAP A and CAP B); 2:00 count race (TOWN NE + SHOULDER); 3:00 vanish; 5:00
spring dialog; 8:00 traffic (ENTRY E -> NECK MID -> SACK MID); 15:00 end dialog. Only the race and bonus B1 wait on
another beat's flag. Every LevelDesign item is in `ITEMS`, so the geometry lives in one place. Every beat that
creates PACT units ends with shapes.reveal(). Every readout is an objective with ListVariables, of at most 2 numbers,
and the run holds at most 10 objectives (OBJECTIVE_VARIABLES_MAX, OBJECTIVE_ROWS_MAX). A readout that is computed,
not read off a variable the game sets, is computed by event-driven loops (WaitCondition, as stock's count waits)
rather than by IfThenElse on a count, which stock does once only (BlackHorsesLastStand #223).

The player's own deployment zone, OD_DZ_W2, ends west of SHOULDER's command zone (probe 1's OD_DZ_W reaches x 540
and covers part of it: a unit deployed there would break the count race's NATO = 0).

Endings: every ending sets od_end (END_WIN or END_LOSS) only while it is still 0 (shapes.set_end), and the one funnel
node calls TriggerEndGame. The ending race (quick runs) is the only other TriggerEndGame pair, under
$/GDScript/OD/EndRace. The end-funnel gate (gates.check_end_funnel) holds every TriggerEndGame to the two.
"""
from __future__ import annotations

from pathlib import Path
from typing import Callable

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.core.models import Box
from modkit.ops import script as ops_script
from modkit.ops.bricks import (
    c_team, g_and, g_choice, g_cmp, g_collect, g_compete, g_count, g_detect, g_difficulty, g_end_game, g_hint, g_if,
    g_kill, g_kills, g_losses, g_modify, g_or, g_random, g_seize, g_seq, g_set, g_simul, g_spawn, g_units_in_zones,
    g_until, g_vanish, g_wait, g_zone_control, g_zone_owner, unit_path,
)
from modkit.ops.graph import Node, i32, template_scalars, walk
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA
from modkit.ops.mission import Leg, lane_route
from modkit.ops.profile import Content
from modkit.ops.script import BRICK_FORCE_HIDE
from modkit.ops.strings import load
from modkit.ops.shapes import (
    ADD, BATTLE_PHASE, DEATH_CAUSE_SHAPE, DIFF_NONE, EASY, FOREVER, GD, GE, HARD, HINT_S, LE, MAJOR_VICTORY, MEDIUM,
    MINOR_VICTORY, PACT_ALLIANCE, PENETRATION, POLL_S, SUB, TOTAL_VICTORY, TRANSPORTER_SHAPE, Beat, add_card,
    beat_hint, count_ladder, create, dialog_tokens, objective, reveal, seconds_while, set_end, setdeck_block,
)
from probes import profile, spike
from probes.geisa import MAP

# --------------------------------------------------------------------------- identity

SCENARIO = "challenge_OpenDoorTest"
MOD_NAME = "OpenDoorTest"
MENU_RENAMES = profile.menu_renames("o2")   # Survivors' op13_* -> o2_*: probe 1's od_* menu texts stay its own
MENU_TOKENS = tuple(MENU_RENAMES.values())

# --------------------------------------------------------------------------- knobs

DEPLOY_POINTS = spike.DEPLOY_POINTS
# Probe 2's own deployment zone, OD_DZ_W2 (minimap px x0, y0, x1, y1): probe 1's DZ_W (13, 250, 540, 780) with its
# east edge moved to x 480, 10 px (120 m) west of SHOULDER's command zone (x 490). Probe 1's covers SHOULDER's west 50
# px, and one unit deployed there would make the 2:00 count race's NATO = 0 false. x0 13 keeps Geisa's four west-edge
# arrival Ends inside it (gates.check_arrivals).
DZ_W2 = (13, 250, 480, 780)
# One km in minimap px: 1 LBU = 215 world units (MapSizeX / LBU) and 1 LBU is about a metre; 2560 world units per px.
KM_PX = 1000 * 215.0 / GEISA.world_per_px   # 84.0
# The four town zones (command zones, owned by the player at load but SHOULDER). No polygon of Geisa's own layout
# covers any of the four points (the tests read its out/CommandZone.ndfbin to check), so each is a square CZ_HALF_PX
# each side of its point, which covers the town's buildings on the Preview: Village E's blob is about 25 px across,
# Town SE's and Town NE's about 50 px. The squares keep apart (gate 6) and stay off the arrivals.
CZ_HALF_PX = 30.0
TOWN_ZONES = {"OD_CZ_CapA": "VILLAGE_E", "OD_CZ_CapB": "TOWN_SE", "OD_CZ_TownNE": "TOWN_NE",
              "OD_CZ_Shoulder": "SHOULDER"}
CZ_POINTS = spike.CZ_POINTS
OWNED_AT_START = ("OD_CZ_SW", "OD_CZ_CapA", "OD_CZ_CapB", "OD_CZ_TownNE")  # the load beat's forced ownership
# The one circle, for the traffic's count (DetectUnitDansDetecteur reads circles only). The capture beat tests the CAP
# zones themselves (ConditionUnitDansZone on their polygons), so they have no circles.
RING_SACK_PX = 20.0                  # the passage exit at SACK MID: the road there is 3 px wide, in forest
# Counters part 1: groups X and Y parked about 1 km east of probe 1's DZ east edge (x 540: X 0.86 km, Y 1.14 km; from
# OD_DZ_W2's x 480 they are 1.6 and 1.9 km, so the checklist sends a tank platoon out after the launch), on the open
# fields between SHOULDER and TOWN NE (Preview and Minimap: ploughed fields, the nearest road and buildings to the west
# and south). They lie at least 85 px north of the E-W road the 8:00 traffic takes (y 400), 160 px from the NATO CMD
# tank's drive into CAP A (y 475), and outside every zone and circle (the tests check it).
PARK_X, PARK_Y = (612.0, 288.0), (636.0, 312.0)
COUNTER_UNIT, X_COUNT, Y_COUNT = "BRDM_2_SOV", 3, 3
COUNTER_POLL_S = 2.0
B1_KILLS = 2                         # bonus B1 completes once this many of group X are dead
# The counters poll stops at COUNTERS_STOP_T and X and Y are removed (KillAllUnit, Vanished) at GROUPS_GONE_T, so no
# BRDM of theirs can drift into TOWN NE for the 2:00 count race. B1 reads the poll's copy, so its input is frozen from
# 1:54: a removal can't complete it (a group count can't tell a dead unit from a removed one).
COUNTERS_STOP_T, GROUPS_GONE_T = 114.0, 115.0   # 1:54, 1:55
# The NATO command tank the capture beat reveals, about 1 km west of CAP A: on the E-W road just south of a farmstead
# (Minimap: road and yard pixels at y 486-494; due west, (616, 475), is the farm's trees), 54 px west of CAP A's
# square, 72 px north of CAP B's, 95 px south of the traffic's road.
NATO_CMD_UNIT = "M1A1HA_Abrams_CMD_US"
NATO_CMD_AT = MAP.points["FARM_ROAD"]
# The load beat's deck cards
RIFLES_CARDS, M1_CARDS, M1_EXPERIENCE = 2, 2, 0  # Experience 0: a worn rearguard
# Timeline (seconds after "Launch battle")
OBJECTIVES_T, COUNTERS_T = 10.0, 15.0
O1_DONE_S, O2_FAIL_S, O3_DONE_S = 60.0, 90.0, 120.0
RACE_AFTER_ANSWER_S = 30.0           # the quick run's race comes this long after the start dialog is answered
END_DIALOG_T = 900.0                 # 15:00: the traffic needs the time
CAPTURE_T, COUNT_RACE_T, VANISH_T, SPRING_T, TRAFFIC_T = 60.0, 120.0, 180.0, 300.0, 480.0
# Traffic at 8:00: CAP A's test (1:00 to 7:45 at the latest, the NATO CMD tank's contest included) runs with no column
# on the road 0.6 km north of it. Its worst case, the 240 s first leg and the last 660 m, ends about 13:00, before the
# 15:00 end dialog.
# Variable values
RUN_FULL, RUN_QUICK = 0, 1           # od_run: the start dialog's ALL / FAST
END_WIN, END_LOSS = 1, 2             # od_end: 0 until an ending; the funnel ends the game on 1 or 2
# Readouts. No stock objective shows more than 2 numbers: in the 29 stock GDScripts, ListVariables and
# ListVariablesForEtiquetteText hold 1 or 2 variables, and no objective text or label uses more than %1 and %2
# (208 texts read in the US dictionaries). A resolved objective stays on the panel, so the whole run holds at most
# OBJECTIVE_ROWS_MAX objectives: O1, O2, O3, B1, the defeat guard and five readouts. B1 also shows group X and the BRDM
# kills, and the guard the difficulty, rather than rows of their own.
OBJECTIVE_VARIABLES_MAX, OBJECTIVE_ROWS_MAX = 2, 10
# Dialog buttons: stock INGAME tokens only (gates.INGAME_PROPS; the game looks button labels up there)
BUTTON_FULL, BUTTON_QUICK = "C_ALL", "HTP_SPDFAT"  # 'ALL'/全部, 'FAST'/快
BUTTON_WIN, BUTTON_LOSS = "win", "lose"           # 'VICTORY!'/胜利！, 'DEFEAT!'/败北！
# 1:00 capture. Tank A (a T-80BV CMD: only a command unit captures) comes from ENTRY E and seizes CAP A
# (TheDieburgSalient #514 creates a T80BV_CMD_SOV, #519 seizes a player-owned zone with it). Once PACT owns CAP A, or
# after CAPTURE_GIVE_UP_S, it is removed (KillAllUnit, Vanished). No stock script gives a smart-ordered group a later
# order (a survey of 44 groups), so a MoveUnitGroup could leave A in CAP A; removed, it can't fire on the NATO CMD tank
# that then contests the zone, and "Soviet seconds inside" stops at the capture. Tank B comes from ENTRY_SE on the
# east-edge road at y 585, which runs straight west into Town SE (CAP B): 80 px south of CAP A's square all the way.
# From ENTRY E, B could only reach Town SE by the N-S road that skirts CAP A's west edge 7-10 px out, or by the road
# through CAP A's centre. B is killed CAPB_KILL_DELAY_S after a Soviet unit is inside CAP B's command zone (its
# polygon, ConditionUnitDansZone: a circle inscribed in the square misses its corners): a capturer killed
# mid-capture. A's "seconds inside" read the same way.
CMD_UNIT = "T80BV_CMD_SOV"
CAPTURE_GIVE_UP_S = 180.0
CAPB_KILL_DELAY_S = 3.0
ENTRY_SE = MAP.points["ENTRY_SE"]    # east-edge road (Minimap: y 583-586 there), 81 px east of CAP B's square
OWNER_NONE, OWNER_NATO, OWNER_PACT = 0, 1, 2  # the CAP owner readouts
# 2:00 count race: the units of a side in the union of TOWN NE's and SHOULDER's command zones (ConditionUnitDansZone,
# Marauders #1343/#1344), PACT >= RACE_PACT_MIN and NATO = 0, held RACE_HOLD_S, then
# SetCommandZoneOwnerAndForceConvergence(PACT, TOWN NE) (Marauders #1134). The BMPs (no command unit, so they cannot
# capture: BlackHorsesLastStand #259's raid) spawn on the E-W road 44 px north of TOWN NE (Minimap: y 157-158), at the
# junction of the road that runs south into the town, away from the parking field south of it.
RACE_UNIT, RACE_COUNT = "BMP_2_SOV", 4
RACE_SPAWN = (655.0, 158.0)
RACE_PACT_MIN, RACE_HOLD_S = 3, 20
RACE_LADDER = 4                      # "Soviet in" counts up to this many (4 = 4 or more)
# 3:00 vanish: group V is filled, the PACT losses and the player's kills are read, V is removed (KillAllUnit, DeathCause
# omitted = Vanished: all 17 stock Operation uses), and both are read again VANISH_READ_S after the kill, as changes.
# One readout of two numbers (OBJECTIVE_VARIABLES_MAX).
VANISH_UNIT, VANISH_COUNT = "BRDM_2_SOV", 4
VANISH_FILL_S = 5.0                  # the kill waits at most this long for all of V to be in the group
VANISH_READ_S = 2.0
# 8:00 traffic: two companies from ENTRY E, FastMoveAndAttack (by road, engaging on sight) by waypoints NECK MID, then
# SACK MID (the passage exit), not through VILLAGE E (CAP A). Both waypoints are named points on the passage road
# (NECK MID in its hamlet, SACK MID on the road at y 404-407). The blocking first leg is raced against TRAFFIC_LEG_S,
# so one vehicle that never reaches NECK MID can't hold the column there.
TRAFFIC = (("T80BV_SOV", 10), ("BMP_2_SOV", 10))
TRAFFIC_WAYPOINTS = ("OD_NeckMid", "OD_SackMid")
TRAFFIC_LEG_S = 240.0
# The road the column takes, read off Geisa's Minimap (luminance columns every 6 px, x 330-762, y 370-440; road
# pixels 55-69, built-up 70+, fields and forest below 50): the east road at y 389-398 from ENTRY E to the village at x
# 540-550, then two parallel roads (y 383-407 north, y 409-422 south) that meet at x 420, and the passage road at y
# 402-407 through NECK MID to SACK MID. The tests hold it 40 px or more from every capture and count-race zone (the
# nearest: CAP A's square, 49 px south of the road at x 700).
TRAFFIC_ROAD_PX = (
    ((756, 397), (666, 395), (630, 393), (594, 389), (576, 394), (558, 401), (545, 407), (528, 414), (516, 418),
     (498, 416), (474, 418), (450, 416), (432, 411), (420, 406), (402, 405), (395, 402), (372, 404), (340, 406)),
    ((510, 400), (492, 388), (474, 389), (456, 392), (438, 398), (426, 402), (420, 406)),  # the north branch
)
# 5:00 spring dialog: up to SPRING_ASKS asks SPRING_GAP_S apart (game time after each answer: the dialog pauses), the
# choice set to CHOICE_NONE before each; NOW (button 0) ends the loop through its Competition's WaitCondition
# (BackhandBlow Competition#194 races its forever dialog loops #251-#253 against Sequential#254's WaitCondition).
SPRING_ASKS, SPRING_GAP_S = 4, 30.0
SPRING_NOW, SPRING_WAIT, CHOICE_NONE = 0, 1, 2
# The loop exits on od_spr_ans, a copy of the choice made once the dialog has closed, never on the live SelectedButton:
# a default the dialog might write when it opens (DefaultButtonChoice) would otherwise end the loop on its first frame.
# Stock reads SelectedButton only after its dialog (Sledgehammer #590 -> #591).
BUTTON_NOW, BUTTON_WAIT = "ORD_AIARA", "ORD_HOLDF"  # 'FIRE AT WILL'/自由射击, 'HOLD FIRE'/不射击 (all 8 languages)

# The load beat's Rifles card rides in an M113A3 (shapes.add_card); the capture beat kills tank B with Penetration.
EXTRA_SHAPES = (TRANSPORTER_SHAPE, DEATH_CAUSE_SHAPE)


# --------------------------------------------------------------------------- items (one place for probe 2's geometry)

def town_box(point: str) -> Box:
    """The CZ_HALF_PX square around named point `point`, minimap px (x0, y0, x1, y1)."""
    x, y = MAP.points[point]
    return Box(x - CZ_HALF_PX, y - CZ_HALF_PX, x + CZ_HALF_PX, y + CZ_HALF_PX)


ITEMS: list[LdItem] = [
    # the player's side: its own deployment zone (DZ_W2: probe 1's, ending west of SHOULDER), probe 1's OD_CZ_SW and
    # Geisa's west-edge arrivals ending in the DZ
    MAP.zone_item("DeploymentZone", "OD_DZ_W2", DZ_W2, "DeploymentZone"),
    MAP.zone_item("CommandPoints", "OD_CZ_SW", spike.CZ_SW, "CommandPoints", points=CZ_POINTS),
    *MAP.map.player_arrivals("OD"),
    # CAP A (Village E), CAP B (Town SE), TOWN NE and SHOULDER
    *(MAP.zone_item("CommandPoints", name, town_box(point), "CommandPoints", points=CZ_POINTS)
      for name, point in TOWN_ZONES.items()),
    # the passage exit, for the traffic's count
    MAP.ring_item("OD_RingSackExit", "SACK_MID", RING_SACK_PX),
    # counters part 1: where groups X and Y park
    MAP.item("Tags", "OD_ParkX", PARK_X, "Name"),
    MAP.item("Tags", "OD_ParkY", PARK_Y, "Name"),
    # the capture beat reveals this (SpawnUnits of a DisableAutoSpawn item: spike.hidden_spawns' form)
    MAP.item("Camp_0", "OD_NatoCmd", NATO_CMD_AT, "Spawn", unit=NATO_CMD_UNIT, camp=0, disable_auto_spawn=True,
                 group="nato_cmd"),
    # spawn and waypoint tags: tank A and the traffic (ENTRY E), tank B (ENTRY SE), the count race's BMPs (north of
    # TOWN NE), group V (CORNER PACT); the traffic's waypoints (NECK MID, SACK MID)
    MAP.item("Tags", "OD_EntryE", "ENTRY_E", "Name"),
    MAP.item("Tags", "OD_EntrySE", ENTRY_SE, "Name"),
    MAP.item("Tags", "OD_TownNENorth", RACE_SPAWN, "Name"),
    MAP.item("Tags", "OD_NeckMid", "NECK_MID", "Name"),
    MAP.item("Tags", "OD_SackMid", "SACK_MID", "Name"),
    MAP.item("Tags", "OD_CornerPact", "CORNER_PACT", "Name"),
]


class Ctx(profile.Ctx):
    """The probes' Ctx over probe 2's ITEMS, its tags keyed to SCENARIO (gates.check_binding fails tags made for
    another scenario)."""

    def __init__(self) -> None:
        super().__init__(ITEMS, SCENARIO)


def item(name: str) -> LdItem:
    """The ITEMS entry named `name`."""
    hits = [it for it in ITEMS if it.name == name]
    check(len(hits) == 1, f"{len(hits)} ITEMS entries are named {name}")
    return hits[0]


# --------------------------------------------------------------------------- shared pieces of the beats

def stay(ctx: Ctx) -> Node:
    """A Condition that never holds, for a readout objective that stays up (probe 1's od_obj6 shape): od_stay is never
    set."""
    return g_cmp(ctx.int_var("od_stay"), 1)


def owner_reading(ctx: Ctx, zone: Node, var: Node) -> Node:
    """`var` = OWNER_NATO, OWNER_PACT or OWNER_NONE: who owns the command zone at tag `zone` now. IfThenElse on
    ConditionTeamControleZone (g_zone_control: ZoneType 1, AutoriseControleAllie True) for joueur, else for PACT,
    else none, as TheWingedHussars' forever loop Sequential#530 tests "joueur controls Anna" once a round. The condition
    reads the zone's current owner when it subscribes, so each round's fresh test reads
    the owner of the moment. Each branch is a Simultaneous, the else of the first a second IfThenElse (stock branch
    forms); `var` gets one write per round, never an intermediate value."""
    return g_if(g_zone_control(ctx.camp("NATO"), zone), g_simul([g_set(var, OWNER_NATO)]),
                g_if(g_zone_control(ctx.camp("PACT"), zone), g_simul([g_set(var, OWNER_PACT)]),
                     g_simul([g_set(var, OWNER_NONE)])))


def pact_in_zone(ctx: Ctx, zone: Node, value: int, op: int) -> Node:
    """And[ConditionUnitDansZone([zone], team PACT, <op> value, ZoneType 1)]: the Soviet units inside the command zone at
    tag `zone`, by its polygon (a circle inscribed in the square misses its corners). In an And of its own,
    as stock has every UnitDansZone in a WaitCondition (Marauders Sequential#516); g_units_in_zones writes ZoneType
    1 (gate 6 resolves the tag in out/CommandZone.ndfbin)."""
    return g_and(g_units_in_zones([zone], c_team(ctx.camp("PACT")), value, op))


def end_funnel(ctx: Ctx) -> Node:
    """The one ending node, exported as profile.END_FUNNEL and run from load beside the battle: wait for od_end >= 1,
    then on 1 the player's total victory, else the loss. The pair is Gotterdammerung's (#258: VictoryReason 6,
    VictoryType 6; #254: the same with WinningAlliance 1), each the last node of its Sequential as in every stock
    Operation; the HUD stays (DelayedRetribution #130 ends with a bare TriggerEndGame), so a mod op's ending that does
    not end shows."""
    end = ctx.int_var("od_end")
    return g_seq([g_until(g_cmp(end, END_WIN, 2)),
                  g_if(g_cmp(end, END_WIN), g_seq([g_end_game(TOTAL_VICTORY)]),
                       g_seq([g_end_game(TOTAL_VICTORY, PACT_ALLIANCE)]))],
                 export=profile.END_FUNNEL)


def end_race() -> Node:
    """The ending race (quick runs), exported as profile.END_RACE: the player's minor victory and a loss (Major for alliance 1,
    so its screen differs from the funnel's Total loss) in one Simultaneous, each the last node of its own Sequential
    (no stock Simultaneous holds a TriggerEndGame). The first to run wins, so the order is the test: win
    first, flipped to loss first on Hard (ConditionOnGameDifficulty, HoldUntilRelieved #203)."""
    def pair(win_first: bool) -> Node:
        win = g_seq([g_end_game(MINOR_VICTORY)])
        loss = g_seq([g_end_game(MAJOR_VICTORY, PACT_ALLIANCE)])
        return g_simul([win, loss] if win_first else [loss, win])

    return g_seq([g_if(g_difficulty(HARD), pair(False), pair(True))], export=profile.END_RACE)


# --------------------------------------------------------------------------- beats

def load_deck(ctx: Ctx) -> Node:
    """Load: the Rifles card with a Transporter (M113A3) and the M1 Abrams card at Experience 0 (shapes.add_card;
    HoldUntilRelieved #383 sets Experience 1)."""
    return g_seq([add_card(ctx, "Rifles_US", RIFLES_CARDS, transport="M113A3_US"),
                  add_card(ctx, "M1_Abrams_US", M1_CARDS, experience=M1_EXPERIENCE)])


def defeat_guard(ctx: Ctx) -> Node:
    """The defeat guard, armed at load: the fail-only objective "Lose every unit and the test ends in defeat" (TheHydra #101: no
    Condition, ActionsEchec), whose ConditionEchec is Groupe_Joueur == 0 (Survivors #728). It starts only once the
    group holds a unit (WaitCondition(Groupe_Joueur >= 1), the empty op's guard; gates.check_empty_group_guard), since
    an objective whose condition holds at its start resolves at once, which during deployment it would. It also waits
    for the battle (Phase 2, deploy_phase's "Launch battle" wait: HoldUntilRelieved #283/#333), so a unit deployed and
    taken back during deployment cannot end the test. Failing sets od_end = END_LOSS.

    It also shows the difficulty readout, od_diff (OBJECTIVE_ROWS_MAX), as its %1: it is up from the launch to the
    end in every run, unresolved, so its text follows od_diff live. od_diff = DIFF_NONE at load, so it never reads 0
    (Easy) before the 0:05 beat sets it."""
    group, diff = ctx.group("Groupe_Joueur"), ctx.int_var("od_diff")
    return g_seq([g_set(diff, DIFF_NONE),
                  g_until(Node("TGDConditionPhase", [("Phase", i32(BATTLE_PHASE))])), g_until(g_cmp(group, 1, 2)),
                  objective("od_guard", "od_guardl", None, counters=[diff], fail=g_cmp(group),
                            echec=g_seq([set_end(ctx.int_var("od_end"), END_LOSS)]))])


def start_dialog(ctx: Ctx) -> Node:
    """0:00: [ALL] (button 0) sets od_run to RUN_FULL, [FAST] to RUN_QUICK, each with its hint (probe 1's
    start_dialog shape: Sledgehammer #590 and SigurdsStrike #498's routing on SelectedButton == 0). od_answered = 1 as
    soon as the dialog closes, before the routing (whose branches last the hints' 15 s), so the race can wait for the
    answer rather than read od_run at a fixed time; the routing sets od_run right after, and the race reads it
    RACE_AFTER_ANSWER_S later."""
    chosen, run = ctx.int_var("od_choice"), ctx.int_var("od_run")
    return g_seq([g_choice("od_start", BUTTON_FULL, BUTTON_QUICK, ctx.camp("NATO"), chosen),
                  g_set(ctx.int_var("od_answered"), 1),
                  g_if(g_cmp(chosen), g_simul([g_set(run, RUN_FULL), g_hint("od_hfull", HINT_S, "shint")]),
                       g_simul([g_set(run, RUN_QUICK), g_hint("od_hquick", HINT_S, "shint")]))])


def difficulty(ctx: Ctx) -> Node:
    """0:05: od_diff starts at DIFF_NONE; three IfThenElse on ConditionOnGameDifficulty, consecutive children of a
    Simultaneous with no else (HoldUntilRelieved #154-#156, DelayedRetribution's [0..2/3]), set it to 0, 1 or 2 and
    show a hint each. The defeat guard's objective shows od_diff (defeat_guard), so 9 means no difficulty reached the
    script."""
    diff = ctx.int_var("od_diff")

    def branch(level: int) -> Node:
        return g_if(g_difficulty(level), g_simul([g_set(diff, level), g_hint(f"od_hdif{level}", HINT_S, "shint")]))

    return g_seq([g_set(diff, DIFF_NONE), g_simul([branch(EASY), branch(MEDIUM), branch(HARD)])])


def objectives(ctx: Ctx) -> Node:
    """0:10: the objective lifecycle. O1 completes at 1:00 (od_o1 = 1) and chains O3 through its ActionsReussi
    (Simultaneous[O3]: BlackHorsesLastStand #141 -> Simultaneous #179), which completes at 2:00; O2 fails at 1:30
    (fail-only, TheHydra #101); bonus B1 (LabelComponent Bonus, pinned on group X: Survivors #775) completes once
    B1_KILLS of group X are dead. B1 reads group X, which the 0:15 beat fills (one of the two cross-beat reads): it starts after
    WaitCondition(X >= 3), as a count condition holds on an empty group. The beat's own timers set the flags, and every
    objective is last in its Sequential or in the beat's Simultaneous (gate 3). B1 also shows the 0:15 beat's counters,
    X alive and the player's BRDM-2 kills (a counter on a resolving objective is stock, HoldUntilRelieved
    #161 "Reach %1 / %2 Conquest Points"); they freeze when B1 completes.

    B1's start guard and Condition read od_xdone, the poll's copy of X alive, written last in each poll
    round, not the group itself (as HoldUntilRelieved #161's Condition reads the variable it shows). So B1 resolves on
    the round that also wrote the completing kill, and its frozen row shows that round's numbers; and since the poll
    stops at COUNTERS_STOP_T, the 1:55 removal of X and Y can't complete it."""
    o1, o2, o3, done = ctx.int_var("od_o1"), ctx.int_var("od_o2"), ctx.int_var("od_o3"), ctx.int_var("od_xdone")
    o3_objective = objective("od_o3", "od_o3l", g_cmp(o3, 1))
    b1 = objective("od_b1", "od_b1l", g_cmp(done, X_COUNT - B1_KILLS, LE), ctx.tag("OD_ParkX"),
                   [ctx.int_var("od_xalive"), ctx.int_var("od_kills")], kind="Bonus")

    def flag_at(t: float, var: Node) -> Node:
        return g_seq([g_wait(t - OBJECTIVES_T), g_set(var, 1)])

    return beat_hint("od_hobj",
                     objective("od_o1", "od_o1l", g_cmp(o1, 1), reussi=g_simul([o3_objective])),
                     objective("od_o2", "od_o2l", None, fail=g_cmp(o2, 1)),
                     g_seq([g_until(g_cmp(done, X_COUNT, GE)), b1]),
                     flag_at(O1_DONE_S, o1), flag_at(O2_FAIL_S, o2), flag_at(O3_DONE_S, o3))


def counters(ctx: Ctx) -> Node:
    """0:15, counters part 1: groups X and Y, X_COUNT and Y_COUNT BRDM-2 parked at OD_ParkX and OD_ParkY. A
    forever loop polls X alive (SetVariableIntegerFromUnitGroup: Survivors #306) and the player's BRDM-2 kills
    (GetNbKillsCamp(joueur, [BRDM_2_SOV]): TheDieburgSalient #332) every 2 s; bonus B1 shows both (no row
    of its own). The alive count is per group, the kills per type: kills = X dead + Y dead. Ends with reveal() on both
    groups.

    Each round reads the kills first, then X alive, then copies X alive into od_xdone, B1's input, as its
    last write. The poll runs until COUNTERS_STOP_T (Competition[poll, WaitDuration]: Marauders Competition#325's
    shape), then at GROUPS_GONE_T KillAllUnit (Vanished) removes X and Y."""
    x, y = ctx.group("od_x"), ctx.group("od_y")
    x_alive, kills, done = ctx.int_var("od_xalive"), ctx.int_var("od_kills"), ctx.int_var("od_xdone")
    poll = g_seq([g_kills(kills, ctx.camp("NATO"), [COUNTER_UNIT]), g_count(x_alive, x),
                  g_set(done, other=x_alive), g_wait(COUNTER_POLL_S)], runs=FOREVER)
    return beat_hint("od_hcnt", g_seq([
        create(ctx, "PACT", x, X_COUNT, ctx.tag("OD_ParkX"), unit_path(COUNTER_UNIT)),
        create(ctx, "PACT", y, Y_COUNT, ctx.tag("OD_ParkY"), unit_path(COUNTER_UNIT)),
        reveal([x, y], [g_compete([poll, g_wait(COUNTERS_STOP_T - COUNTERS_T)]),
                        g_wait(GROUPS_GONE_T - COUNTERS_STOP_T), g_vanish(x, y)]),
    ]))


def race(ctx: Ctx) -> Node:
    """From 0:00, quick runs only: once the start dialog is answered (od_answered = 1) and RACE_AFTER_ANSWER_S more
    have passed, the ending race (end_race) if od_run == RUN_QUICK. It must not read od_run at
    a fixed time, or a slow answer (if the clock runs while the dialog pauses the game) would turn a quick run into a
    full one. The start dialog's FAST hint announces it; the end screen is its readout. The other cross-beat read: it
    waits on the start dialog's flag."""
    return g_seq([g_until(g_cmp(ctx.int_var("od_answered"), 1)), g_wait(RACE_AFTER_ANSWER_S),
                  g_if(g_cmp(ctx.int_var("od_run"), RUN_QUICK), end_race())])


def capture(ctx: Ctx) -> Node:
    """1:00, capture. Two T-80BV CMD tanks, each alone in
    its group; the beat ends with reveal():
      - A (od_capa) from ENTRY E seizes CAP A (g_seize: TheDieburgSalient #514 creates a T80BV_CMD_SOV, #519
        seizes a player-owned zone with it). Once PACT owns CAP A (WaitCondition on ConditionTeamControleZone, as
        BackhandBlow #306), or after CAPTURE_GIVE_UP_S, whichever is first (a Competition), KillAllUnit with DeathCause
        omitted (Vanished, bricks.g_vanish) removes A (no stock group gets an order after a smart order), and
        SpawnUnits reveals the hidden NATO M1A1HA CMD (spike.reserves' form) with the hint od_hnato.
      - B (od_capb) from ENTRY SE seizes CAP B; CAPB_KILL_DELAY_S after a PACT unit is inside CAP B's command zone
        (pact_in_zone: ConditionUnitDansZone on its polygon, ZoneType 1; B is the only PACT unit there), KillAllUnit with
        DeathCause Penetration kills it (bricks.g_kill, as spike.strike's), hint od_hkillb.
      - One readout (OBJECTIVE_VARIABLES_MAX), every POLL_S and forever: CAP A's owner (owner_reading: 0 none, 1 NATO,
        2 PACT) and the seconds a PACT unit has been inside CAP A's command zone (seconds_while on pact_in_zone,
        summed). A is removed at the capture, so the seconds stop there: the fill time. CAP B's owner is read off the map
        (its colour): a resolved state, unlike the fill time, which needs a timer.
    Every objective and loop sits in the Simultaneous after the creates; nothing follows them."""
    a, b = ctx.group("od_capa"), ctx.group("od_capb")
    own_a, inside_a = ctx.int_var("od_owna"), ctx.int_var("od_capa_in")
    cap_a, cap_b, pact = ctx.tag("OD_CZ_CapA"), ctx.tag("OD_CZ_CapB"), ctx.camp("PACT")
    poll = g_seq([owner_reading(ctx, cap_a, own_a), g_wait(POLL_S)], runs=FOREVER)
    timer = seconds_while(lambda: pact_in_zone(ctx, cap_a, 1, GE), lambda: pact_in_zone(ctx, cap_a, 0, LE), inside_a,
                          reset=False)
    run_a = g_seq([g_seize(a, cap_a),
                   g_compete([g_until(g_zone_control(pact, cap_a)), g_wait(CAPTURE_GIVE_UP_S)]),
                   g_vanish(a),
                   g_spawn([ctx.tag("OD_NatoCmd")]),
                   g_simul([g_hint("od_hnato", HINT_S, "shint")])])
    run_b = g_seq([g_seize(b, cap_b),
                   g_until(pact_in_zone(ctx, cap_b, 1, GE)),
                   g_wait(CAPB_KILL_DELAY_S),
                   g_kill(b, cause=PENETRATION),
                   g_simul([g_hint("od_hkillb", HINT_S, "shint")])])
    return beat_hint("od_hcap", g_seq([
        create(ctx, "PACT", a, 1, ctx.tag("OD_EntryE"), unit_path(CMD_UNIT)),
        create(ctx, "PACT", b, 1, ctx.tag("OD_EntrySE"), unit_path(CMD_UNIT)),
        reveal([a, b], [g_simul([poll, timer, run_a, run_b,
                                 objective("od_capa", "od_capal", stay(ctx), counters=[own_a, inside_a])])]),
    ]))


def count_race(ctx: Ctx) -> Node:
    """2:00, the count race. RACE_COUNT BMP-2 (no command unit) from north of TOWN NE seize it
    (g_seize; BlackHorsesLastStand #259 seizes with BMP-2s alone). The rule counts units in the union of TOWN NE's
    and SHOULDER's command zones (g_units_in_zones: ConditionUnitDansZone, ZoneType 1, Marauders #1343/#1344, each
    inside an And as stock has them): PACT >= RACE_PACT_MIN and NATO <= 0 starts a streak, PACT <= RACE_PACT_MIN - 1 or
    NATO >= 1 breaks it (an Or of Ands: stock Or holds no UnitDansZone bare). od_cr_held counts the streak's seconds
    (seconds_while, reset on a break); at RACE_HOLD_S, SetCommandZoneOwnerAndForceConvergence(PACT, TOWN NE)
    (Marauders #1134, after its count wait) and the hint od_hcrown. Readout (OBJECTIVE_VARIABLES_MAX): Soviet in
    (count_ladder up to RACE_LADDER) and held; NATO in has no number (the checklist keeps the player out, and a NATO
    unit inside shows as held stuck at 0). Ends with reveal()."""
    bmps = ctx.group("od_cr")
    pact_in, held = ctx.int_var("od_cr_pact"), ctx.int_var("od_cr_held")
    zones = [ctx.tag("OD_CZ_TownNE"), ctx.tag("OD_CZ_Shoulder")]

    def inside(side: str) -> Callable[[int, int], Node]:
        return lambda value, op: g_units_in_zones(zones, c_team(ctx.camp(side)), value, op)

    pact, nato = inside("PACT"), inside("NATO")
    holds = lambda: g_and(pact(RACE_PACT_MIN, GE), nato(0, LE))  # noqa: E731
    broken = lambda: g_or(g_and(pact(RACE_PACT_MIN - 1, LE)), g_and(nato(1, GE)))  # noqa: E731
    force = g_seq([g_until(g_cmp(held, int(RACE_HOLD_S), GE)),
                   g_zone_owner(ctx.camp("PACT"), [ctx.tag("OD_CZ_TownNE")]),
                   g_simul([g_hint("od_hcrown", HINT_S, "shint")])])
    return beat_hint("od_hcr", g_seq([
        create(ctx, "PACT", bmps, RACE_COUNT, ctx.tag("OD_TownNENorth"), unit_path(RACE_UNIT)),
        reveal([bmps], [g_simul([
            g_seize(bmps, ctx.tag("OD_CZ_TownNE")),
            *count_ladder(lambda v, op: g_and(pact(v, op)), pact_in, RACE_LADDER),
            seconds_while(holds, broken, held, reset=True),
            force,
            objective("od_cr", "od_crl", stay(ctx), counters=[pact_in, held]),
        ])]),
    ]))


def vanish(ctx: Ctx) -> Node:
    """3:00, vanish: VANISH_COUNT BRDM-2 into group V at CORNER PACT. Once V holds
    them all (or after VANISH_FILL_S), read the PACT losses (GetNbLossCamp, GloryOrAttrition #161) into od_vl0 and the
    player's BRDM-2 kills (GetNbKillsCamp with TypeUnitList [VANISH_UNIT], as both stock uses carry a list)
    into od_vk0; KillAllUnit with DeathCause omitted (Vanished, all 17
    stock Operation uses: bricks.g_vanish); VANISH_READ_S later read both again into od_vl and od_vk and subtract the
    first reads, so the one readout shows the changes (OBJECTIVE_VARIABLES_MAX). It starts only after the subtraction,
    so it never shows a raw total. After the beat's hint has had its 15 s, a RandomLauncher shows one of two hints
    (g_random; each child Sequential[Simultaneous[LDHint]]: stock RandomLauncher children are Sequentials, and stock
    holds an LDHint in a Simultaneous). Ends with reveal()."""
    v, pact, nato = ctx.group("od_v"), ctx.camp("PACT"), ctx.camp("NATO")
    losses0, kills0 = ctx.int_var("od_vl0"), ctx.int_var("od_vk0")
    losses, kills = ctx.int_var("od_vl"), ctx.int_var("od_vk")
    picks = g_seq([g_wait(HINT_S), g_random([g_seq([g_simul([g_hint(tok, HINT_S, "shint")])])
                                                  for tok in ("od_hvana", "od_hvanb")])])
    return beat_hint("od_hvan", g_seq([
        create(ctx, "PACT", v, VANISH_COUNT, ctx.tag("OD_CornerPact"), unit_path(VANISH_UNIT)),
        reveal([v], [
            g_compete([g_until(g_cmp(v, VANISH_COUNT, GE)), g_wait(VANISH_FILL_S)]),
            g_losses(losses0, pact), g_kills(kills0, nato, [VANISH_UNIT]),
            g_vanish(v),
            g_wait(VANISH_READ_S),
            g_losses(losses, pact), g_kills(kills, nato, [VANISH_UNIT]),
            g_modify(losses, SUB, other=losses0), g_modify(kills, SUB, other=kills0),
            g_simul([picks, objective("od_vn", "od_vnl", stay(ctx), counters=[losses, kills])]),
        ]),
    ]))


def traffic(ctx: Ctx) -> Node:
    """8:00, traffic (lane capacity, road use): TRAFFIC's two companies into od_tr
    at ENTRY E, then FastMoveAndAttack (FAST_MOVE_AND_ATTACK: by road, engaging on sight) by waypoints, a lane of two
    legs (modkit.ops.mission.lane_route): a GiveOrderStandard Blocking to NECK MID (DelayedRetribution #275/#276 block
    on GiveOrderStandard) raced against WaitDuration TRAFFIC_LEG_S, then a GiveOrderStandard to SACK MID, the passage
    exit. The race is Marauders Competition#325's shape, [WaitDuration 300, Sequential#694[...]], before the next node;
    stock Competitions take no GiveOrderStandard bare, so the order sits in its Sequential. Not by VILLAGE E (CAP A);
    TRAFFIC_ROAD_PX is the road it takes. Readout, every POLL_S: the seconds since the spawn, and how
    many have reached the SACK MID circle (AddDetectedUnitsToUnitGroup into od_through, HoldUntilRelieved #112's shape,
    then its count: a group never holds a unit twice, and loses its dead). Ends with reveal()."""
    column, through = ctx.group("od_tr"), ctx.group("od_through")
    seconds, passed = ctx.int_var("od_tr_s"), ctx.int_var("od_tr_n")
    neck, sack = TRAFFIC_WAYPOINTS
    route = lane_route(ctx, column, (Leg(neck, TRAFFIC_LEG_S), Leg(sack, None)))
    poll = g_seq([g_wait(POLL_S), g_modify(seconds, ADD, 1),
                  g_collect(through, g_detect(ctx.tag("OD_RingSackExit"), c_team(ctx.camp("PACT")), compare=False)),
                  g_count(passed, through)], runs=FOREVER)
    return beat_hint("od_htr", g_seq([
        *(create(ctx, "PACT", column, n, ctx.tag("OD_EntryE"), unit_path(unit)) for unit, n in TRAFFIC),
        reveal([column], [g_simul([route, poll,
                                   objective("od_tr", "od_trl", stay(ctx), counters=[seconds, passed])])]),
    ]))


def spring(ctx: Ctx) -> Node:
    """5:00, the re-asked spring dialog. od_spr_pick = od_spr_ans = CHOICE_NONE,
    then the readout (asks so far, last answer: the live SelectedButton, so a default written at the dialog's start
    shows) beside Sequential[Competition[ask loop, WaitCondition(ans == SPRING_NOW)], IfThenElse(ans == SPRING_NOW, hint
    od_hnow, hint od_hwait)]. The ask loop runs SPRING_ASKS times: pick = ans = CHOICE_NONE (a stale 0 would read as
    NOW), asks += 1 (before the ask: the exit can end the loop the moment NOW is answered), the dialog (g_choice,
    buttons BUTTON_NOW and BUTTON_WAIT, SelectedButton = pick), ans = pick once the dialog has closed (the
    exit and the verdict read that copy, never the live SelectedButton), WaitDuration SPRING_GAP_S. The Competition is
    the loop's exit, as BackhandBlow Competition#194 races its forever dialog loops (#251, with EncapsuleCutscene #307)
    against a WaitCondition; after a NOW, or four asks, the beat shows its hint and stops asking."""
    pick, asks, ans = ctx.int_var("od_spr_pick"), ctx.int_var("od_spr_asks"), ctx.int_var("od_spr_ans")
    ask = g_seq([g_set(pick, CHOICE_NONE), g_set(ans, CHOICE_NONE), g_modify(asks, ADD, 1),
                 g_choice("od_springq", BUTTON_NOW, BUTTON_WAIT, ctx.camp("NATO"), pick),
                 g_set(ans, other=pick), g_wait(SPRING_GAP_S)], runs=SPRING_ASKS)
    then = g_seq([g_compete([ask, g_until(g_cmp(ans, SPRING_NOW))]),
                  g_if(g_cmp(ans, SPRING_NOW), g_simul([g_hint("od_hnow", HINT_S, "shint")]),
                       g_simul([g_hint("od_hwait", HINT_S, "shint")]))])
    return beat_hint("od_hspr", g_seq([g_set(pick, CHOICE_NONE), g_set(ans, CHOICE_NONE), g_simul([
        objective("od_spr", "od_sprl", stay(ctx), counters=[asks, pick]), then])]))


def end_dialog(ctx: Ctx) -> Node:
    """15:00 (the 8:00 column needs about 5 minutes to SACK MID, and this dialog pauses the
    game), full runs only (od_run == RUN_FULL): [VICTORY!] (button 0) sets od_end to END_WIN, [DEFEAT!] to
    END_LOSS, each only while od_end is 0 (set_end); the funnel then ends the game."""
    pick = ctx.int_var("od_endpick")
    return g_if(g_cmp(ctx.int_var("od_run"), RUN_FULL), g_seq([
        g_choice("od_endq", BUTTON_WIN, BUTTON_LOSS, ctx.camp("NATO"), pick),
        g_if(g_cmp(pick), set_end(ctx.int_var("od_end"), END_WIN), set_end(ctx.int_var("od_end"), END_LOSS)),
    ]))


BEATS: list[Beat] = [
    Beat(None, "deck", load_deck),
    Beat(None, "guard", defeat_guard),
    Beat(0.0, "dialog", start_dialog),
    Beat(0.0, "race", race),          # waits for the start dialog's answer, then RACE_AFTER_ANSWER_S
    Beat(5.0, "difficulty", difficulty),
    Beat(OBJECTIVES_T, "objectives", objectives),
    Beat(COUNTERS_T, "counters", counters),
    Beat(CAPTURE_T, "capture", capture),
    Beat(COUNT_RACE_T, "count", count_race),
    Beat(VANISH_T, "vanish", vanish),
    Beat(SPRING_T, "spring", spring),
    Beat(TRAFFIC_T, "traffic", traffic),  # 8:00: clear of CAP A's test
    Beat(END_DIALOG_T, "end", end_dialog),
]


# --------------------------------------------------------------------------- strings

TABLE = Path(__file__).with_name("spike2.strings.toml")   # its texts, per token and language (load)


# --------------------------------------------------------------------------- script and content

def script(tpl: ndfbin.NdfBin) -> tuple[list[Node], list[Node]]:
    """Probe 2's GDScript (layout in the module docstring), from Survivors' GDScript template `tpl`."""
    ctx = Ctx()
    deploy = ops_script.deploy_phase(tpl, profile.TEMPLATES, ctx.camp("NATO"), ctx.group("Groupe_Joueur"),
                                     [ctx.tag(name) for name in OWNED_AT_START], points=DEPLOY_POINTS,
                                     income=profile.PLAYER_INCOME, hint="od_hdep",
                                     refresh_export=profile.REFRESH_EXPORT, refresh_s=profile.REFRESH_S)
    load = [b.build(ctx) for b in BEATS if b.t is None]
    battle = g_simul([g_seq([g_wait(b.t), b.build(ctx)]) for b in BEATS if b.t is not None])
    funnel = end_funnel(ctx)
    main = g_seq([
        *setdeck_block(ctx.camps, profile.CAMP_ROWS),                                          # S#117-#120
        Node("TGDDescriptorForceDisplayUIElement", template_scalars(tpl, profile.TEMPLATES.hud_hide)),  # S#121
        *deploy.setup,
        Node("TGDDescriptorLoadingDone"),                                                     # S#122
        Node("TGDDescriptorForceDisplayUIElement",                                            # S#296 + DEPLOY_HUD
             ops_script.hud_restore(tpl, profile.TEMPLATES, True, BRICK_FORCE_HIDE)),
        g_simul([*load, deploy.refresh, funnel, g_seq([deploy.launched, battle])]),
    ], export=f"{profile.FOLDER}/Main")
    root = Node(ops_script.ROOT_CLASS, [                                                      # S#108
        ("CampList", list(ctx.camps.values())),
        ("EffetMap", g_seq([g_wait(profile.START_DELAY_S), main])),                           # S#113
        ("GameRules", deploy.game_rules),
    ], export=f"{GD}/RootDescriptor")
    races = [nd for nd in walk([root]) if nd.export == profile.END_RACE]
    exports = [root, *ctx.camps.values(), *ctx.tags.values(), main, deploy.refresh, funnel, *races,
               *ctx.variables.values()]
    missing = [nd.export for nd in walk([root]) if nd.export and nd not in exports]
    check(not missing, f"exported nodes missing from the export list: {missing}")
    return [ops_script.silent_cutscenes(dialog_tokens([root])), root], exports


def content() -> Content:
    """Probe 2: its own scenario, mod folder, GUID and menu tokens."""
    return profile.content("spike2", ITEMS, script, load(TABLE), MENU_TOKENS, extra_shapes=EXTRA_SHAPES,
                           scenario=SCENARIO, mod_name=MOD_NAME, menu_renames=MENU_RENAMES)
