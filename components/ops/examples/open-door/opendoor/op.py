"""Operation Open Door, the mission: the playable core of the design (docs/design.md, docs/storyline-map.html).

The op is its own scenario, challenge_OperationOpenDoor, in its own mod folder, OpenDoor, with its own GUID and menu
tokens (o3_*: opendoor.profile), so it installs beside the probes (challenge_OpenDoor in OpenDoorOps,
challenge_OpenDoorTest in OpenDoorTest) [[content-identity-unique]]. Build it with `python build.py --content op`.

As in the probes, the op is a list of beats (modkit.ops.shapes.Beat), each its own branch of the battle's
Simultaneous. The phase flags (FLAGS: od_released, od_window, od_sprung, od_sealed_mid, od_sealed_s, od_sealed,
od_end) are the only cross-beat reads; all are declared here, at 0, before any beat writes them.

  Main: SetDeck x4, HUD hidden, deployment setup (DEPLOY_POINTS; every tier and anvil command zone forced to NATO:
        OWNED_AT_LOAD), LoadingDone, HUD restored, then
        Simultaneous[ the load beats (deck, difficulty, the end funnel, P2),
                      the Groupe_Joueur refresh loop,
                      Sequential[ wait for "Launch battle" (hint od_hdep), Simultaneous[ one Sequential[wait t, beat]
                                                                                       per timed beat ] ] ]

The load beats are the deck, the difficulty, the end funnel (end_funnel: the one ending node, run from load) and P2.
The two defeats arm with the launch (anvil, rear_exit; zone_race is their shared race). Phase 1 is five timed beats:
P1 with the phase hint and B1 at H+0:00, PL BLUE's per-town fall (pl_blue, also from H+0:00: each town's command zone
goes to PACT as it falls, the rest at H+12, then od_released), the captured T-80U at H+0:30 (a backup for the captured
cards) and the first echelon at H+1:00 (FE_COMPANIES, three companies that Seize their towns). Phase 2 is three beats
from H+0:00 that each wait for od_released: the main body (WAVES, six waves one a minute down the MID and BOTTOM
lanes), PL GREEN (pl_green: B6's stand, and the window whose close hands the necks to PACT) and the spring (spring: the
sack count, P4, then Corps's re-asked dialog until FIRE AT WILL, H+30 or the anvil contested, then od_sprung). Phases
3 and 4 are two beats from H+0:00 that each wait for od_sprung: phase3 (the codeword dialog, the jaws revealed and the
spring cards: spring_effects; P5 per neck, whose seal hands the neck back to NATO; the hints one at a time:
seal_hints) and pocket (the seal and od_sealed, P6, the surrender or the backstop, then the catch: counts read, the
pocket removed, the CATCH row and the grade through set_end).

Arrivals (the tiers gate, gate 3). A unit bought after the launch spawns at the usable Start nearest the click, and an
entry is usable while the zone holding its End is NATO's [[arrival-end-in-zone]]. TIERS are five reinforcement
locations: one per PL BLUE town (the east tier) and one per neck (the neck tier), each ending in its town's or neck's
command zone; Geisa's west-edge entries (modkit.ops.maps.GEISA.west_arrivals) end in the anvil deployment zone and are
permanent, aircraft included. TIER_MODE picks how the five behave:
  - "tiered": each End lies in its command zone only, so a tier closes when tier_handover gives its zone to PACT and
    reopens when it comes back (Content.tiered_arrivals names them for gate 3 tiers);
  - "fixed": each End also lies in a small player deployment zone of its own (FIXED_DZ_HALF_PX), so the tiers stay
    open all battle (the fallback if tiers misbehave in play).
"tiered" is the default: gate 3 tiers asks each tier zone for a PACT hand-over, and pl_blue gives the towns theirs,
pl_green the necks theirs. "fixed" still builds and passes every gate.

The probes' shortcuts are not inherited: no reveal() or other SetEffect on Soviet units, no readout objectives, no run
dialog.

The composed pieces another op uses too are modkit.ops.mission's: the script frame (script_frame), the lanes and
waves (Leg, Lane, Wave, lane_route, wave, create_rows, board), the re-ask loop (reask_loop), the zone race and
hand-over (zone_race, zone_handover as tier_handover), the circle counts (ring_round), the end funnel, the difficulty
branches and the hidden jaws (hidden_units). This module holds Open Door's story: its constants, names and texts.
"""
from __future__ import annotations

import math
from collections import Counter
from pathlib import Path
from typing import Iterable, NamedTuple

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.core.models import Box, Point
from modkit.ops import mission as ops_mission
from modkit.ops import shapes
from modkit.ops.bricks import (
    c_all, c_any, c_none, c_team, c_type, g_and, g_cmp, g_compete, g_count, g_detect, g_dialog, g_hint, g_if,
    g_kills, g_modify, g_or, g_seize, g_seq, g_set, g_simul, g_spawn, g_union, g_units_in_zones, g_until, g_vanish,
    g_wait, g_zone_control, g_zone_owner,
)
from modkit.ops.forces import group_total, scaled, share_count
from modkit.ops.graph import Node, i32
from modkit.ops.leveldesign import LdItem
from modkit.ops.maps import GEISA, GEISA_BOXES
from modkit.ops.mission import (
    CHOICE_NONE, Lane, Leg, Wave, board, create_rows, hidden_units, reask_loop, ring_round, wave, zone_race,
)
from modkit.ops.mission import zone_handover as tier_handover  # the tiers' hand-over: see "shared pieces" below
from modkit.ops.models import Buttons, Ending, ForceRow, Knobs
from modkit.ops.profile import Content
from modkit.ops.script import BRICK_DEFAULT
from modkit.ops.shapes import Beat, lock_card, objective  # noqa: F401  (lock_card: the deck beat's and the tests')
from modkit.ops.strings import load
from opendoor import forces, profile
from opendoor.map import MAP, POINTS

TABLE = Path(__file__).with_name("strings.toml")   # every text the mission shows, per token and language (load)

# --------------------------------------------------------------------------- knobs

DEPLOY_POINTS = 6000                 # starting points: four groups to deploy (design 4); probe 2 had 3,000
HINT_S = shapes.HINT_S              # 'shint' panel time (Sledgehammer #601)
EASY, MEDIUM, HARD = shapes.EASY, shapes.MEDIUM, shapes.HARD
DIFF_NONE = shapes.DIFF_NONE       # od_diff before the difficulty branches: no difficulty reached the script
BATTLE_PHASE = shapes.BATTLE_PHASE  # TGDConditionPhase: the battle is launched (profile.deploy_phase's wait)
# The difficulty knobs, (Easy, Medium, Hard) [[difficulty-branches]]. Medium is written first, unconditionally; the
# Easy and Hard branches overwrite it. B1's kills are design 5.7's shares 28/42/55 % of the first echelon
# (forces.threshold: 10/15/20 at 1x); S_min is 0.25/0.33/0.40 of the main body's 60 vehicles; B6's contact seconds
# 1:30/2:00/2:30 and the surrender share 45/35/25 % are design 5.7's.
KNOBS: dict[str, Knobs] = {
    "od_b1_n": Knobs(*(forces.threshold("B1", d, scaled(forces.ROWS, forces.FORCE_SCALE))
                       for d in ("easy", "medium", "hard"))),
    "od_smin": Knobs(15, 20, 24),
    "od_b6_s": Knobs(90, 120, 150),
    "od_surr_pct": Knobs(45, 35, 25),
}
# The difficulty hint shows this long after "Launch battle": after phase 1's hint (H+0:00, HINT_S long) and before the
# captured T-80U's (H+0:30), and never beside the deploy hint, the one hint of the deployment phase.
DIFF_HINT_T = 15.0
# The phase flags, every cross-beat read, declared at 0 (a TGDVariableInteger without Value, as 83 of the 97 stock
# ones) before any beat writes them.
FLAGS = ("od_released", "od_window", "od_sprung", "od_sealed_mid", "od_sealed_s", "od_sealed", "od_end")
# od_end's values. The first writer wins (shapes.set_end); the funnel (end_funnel) shows that value's dialog and
# ends the battle: Total (6) on 1, Major (5) on 2 and 3, a loss on 4 to 6.
END_TOTAL, END_MAJOR, END_MINOR, END_ANVIL, END_REAR, END_LOST = 1, 2, 3, 4, 5, 6
# The funnel's rows: od_end value -> (dialog token, EVictoryType, whether the player loses). No stock Minor screen
# exists for a win we call Minor (the band under 40 %): it shows Major's, with its own dialog.
ENDINGS: dict[int, Ending] = {
    END_TOTAL: Ending("od_dtotal", shapes.TOTAL_VICTORY, False),
    END_MAJOR: Ending("od_dmajor", shapes.MAJOR_VICTORY, False),
    END_MINOR: Ending("od_dminor", shapes.MAJOR_VICTORY, False),
    END_ANVIL: Ending("od_danvil", shapes.TOTAL_VICTORY, True),   # a loss: the winner is the Soviet alliance (#254)
    END_REAR: Ending("od_drear", shapes.TOTAL_VICTORY, True),
    END_LOST: Ending("od_dlost", shapes.TOTAL_VICTORY, True),
}
# The defeats (design 4). The anvil falls when PACT has ANVIL_PACT_N units in an anvil command zone and NATO none for
# ANVIL_HOLD_S; the rear exit when REAR_N Soviet main-body vehicles stand in its circle (0.10 of the main body's 60
# vehicles, S_min's base).
ANVIL_PACT_N, ANVIL_HOLD_S = 4, 30.0
REAR_N = 6
GE, LE = shapes.GE, shapes.LE
SUB = shapes.SUB                   # EVariableIntegerModification Substract
POLL_S, FOREVER = shapes.POLL_S, shapes.FOREVER
# Phase 1 (seconds after "Launch battle"). P1: PL BLUE is given up by H+12 whatever happens (design 4.1); its %1
# counts the minutes left down from P1_MINUTES, one a minute (a variable: no stock objective shows a timer in the
# panel). The captured T-80U comes at H+0:30 and the first echelon at H+1:00 (the design's timeline).
P1_DEADLINE_S = 720.0
P1_MINUTES = int(P1_DEADLINE_S // 60)
CAPTURED_T, FE_T = 30.0, 60.0
# A town's race [[count-race-forced-owner]]: probe 2's count race, played at TOWN NE: PACT >= 3 and NATO none for 20 s.
TOWN_PACT_N, TOWN_HOLD_S = 3, 20.0  # probe 2's count race rule (its RACE_PACT_MIN, RACE_HOLD_S)
# Riflemen board their BMP-2s (LoadIntoTransporter, ground carriers), raced against BOARD_S; else they follow on foot
# with their company's Seize (phase 1) or their wave's route (phase 2).
BOARD_S = 30.0
# Phase 2 (seconds after the release, od_released = 1, unless said otherwise): the main body's six waves (WAVES), one
# every WAVE_GAP_S from the release, each down its lane (LANES) by waypoints.
WAVE_GAP_S = 60.0
# A lane leg's timeout: probe 2's traffic beat races each blocking GiveOrderStandard against one, so a vehicle that
# never arrives cannot hold its wave at a waypoint. Probe 2's pace, its TRAFFIC_LEG_S (240 s) for the 362 px of road
# from ENTRY E to NECK MID (Minimap), on each leg's road length (the item tests measure them), rounded up to 10 s and
# at least LEG_MIN_S. A timeout that comes early only sends the wave on, by road, to its next waypoint.
LEG_PACE_S_PER_PX = 240.0 / 362  # probe 2's traffic leg (240 s) over its 362 px
LEG_MIN_S = 60.0
# The sack count (design 5.2, P4): every SACK_POLL_S, the Soviet vehicles in the sack's circles (the two lane exits
# and the kill zone's three, design 3: SACK / KILL ZONE). Vehicles are every PACT unit but the main body's and the
# first echelon's infantry types (no category brick exists).
SACK_POLL_S = 2.0
SACK_RINGS = ("OD_RingSackMid", "OD_RingSackS", "OD_RingPlainN", "OD_RingPlainC", "OD_RingPlainS")
SACK_INFANTRY = ("MotRifles_SOV", "Scout_SOV")
# The spring (design 5.2): once P4 is done, Corps asks every SPRING_GAP_S (game time after each answer: the dialog
# pauses the game) until FIRE AT WILL; it springs the trap itself at H+30 (SPRING_DEADLINE_S after "Launch battle") or
# once a Soviet unit is inside an anvil command zone [[dialog-reask-loop]]. Probe 2's choice values and buttons (stock
# INGAME tokens [[dialog-button-ingame-dictionary]]); no answer yet is modkit.ops.mission.CHOICE_NONE (2).
SPRING_GAP_S = 120.0
SPRING_DEADLINE_S = 1800.0
SPRING_NOW, SPRING_WAIT = 0, 1   # probe 2's: button 0, button 1
BUTTON_NOW, BUTTON_WAIT = "ORD_AIARA", "ORD_HOLDF"   # 'FIRE AT WILL', 'HOLD FIRE'
# PL GREEN (design 5.1): the window opens at the release and closes when B6 is done, when no player unit is left in
# either neck after the first contact, WINDOW_S after the release (the design's 6:00 made 8:00), or at the spring if
# it is still open (the spring ends phase 2, and the necks go to PACT in that same close, so before P5 can seal one:
# it starts at the spring and needs 30 s held). Whatever closes it, the close hands both necks to PACT, once; a spring
# after an earlier close does nothing more. od_window is 0 until the close, then WINDOW_CLOSED. The close's hint says
# why: od_hgrn (break contact, fall back) or, closed by the spring, od_hgrs (seal the necks again). B6's hint comes
# B6_HINT_T after the release: after the last town's hint and od_hopen (HINT_S after it, HINT_S long), so two hints
# never land together. The town hints take turns (pl_blue's town_hints), so when the towns fall in the release's second
# the last shows 2 x HINT_S after it, and od_hopen ends 4 x HINT_S after it.
# B6_PAIRS: each neck's command zone and its approach circle, where contact is counted.
WINDOW_S = 480.0
WINDOW_CLOSED = 1
B6_HINT_T = 4 * HINT_S
B6_PAIRS = (("OD_CZ_NeckMid", "OD_RingApprMid"), ("OD_CZ_NeckS", "OD_RingApprS"))
# Phase 3 (from the spring, od_sprung = 1, design 5.3). The codeword dialog, the jaws revealed and design 6.1's spring
# cards (the A-10A lock in load_deck ends on od_sprung itself; the design's F-4G, EF-111 and AH-64 cards are not built
# yet). P5 per neck (design 5.4): a neck is sealed once NATO has SEAL_NATO_N or more units in its command zone and PACT
# none for SEAL_HOLD_S (zone_race); then the zone goes back to NATO (its tier reopens) and od_sealed_<key> = 1. The
# seal hints take turns through od_hturn (seal_hints): HTURN_MID or HTURN_S names the one that shows first, HTURN_ANY
# lets the other.
SPRING_CARDS = (ForceRow("M1A1HA_Abrams_US", 4), ForceRow("Leopard_2A4_RFA", 4),
                ForceRow("OH58D_Kiowa_Warrior_US", 2))
SEAL_NATO_N, SEAL_HOLD_S = 1, 30.0
HTURN_MID, HTURN_S, HTURN_ANY = 1, 2, 3
# Phase 4 (design 5.4-5.5). Once both necks are sealed, od_sealed_n = the Soviet vehicles in the pocket (the sack's
# circles, SACK_RINGS), and the pocket surrenders once it holds od_surr_n = od_sealed_n x od_surr_pct / SURR_PCT_BASE
# or fewer (the difficulty's 45/35/25 %, rounded down), or T_HOLD_S after the seal (design 5.4's T_hold). No Multiply:
# no stock script uses it, and probe 1's first launch failed on a value no stock file had serialised
# [[changestress-damagetype-zero]]; a loop of Adds, then the Divide (share_of). The backstop: if the pocket is not
# sealed BACKSTOP_S after the spring, Corps ends the battle, and the catch counts the destroyed only. The grade bands
# (design 5.5) are CATCH_SHARES of the main body's MB_TOTAL vehicles (CATCH_TOTAL_N, CATCH_MAJOR_N, below MB_TOTAL).
T_HOLD_S = 900.0
BACKSTOP_S = 1500.0
SURR_PCT_BASE = 100
ADD, DIVIDE = shapes.ADD, shapes.DIVIDE                # EVariableIntegerModification Add, Divide
STRICTLY_LESS = shapes.STRICTLY_LESS                     # EGDOperator
check(len({KNOBS["od_surr_pct"].at(level) for level in (EASY, MEDIUM, HARD)}) == 3,
      "share_of branches on od_surr_pct's value: the three shares must differ")
CATCH_SHARES = (0.70, 0.40)                                # Total (with both necks sealed), Major; below: Minor

# The load beat's cards (design 6.1, Start rows) [[add-unit-to-deck]]. The rearguard's are written at Experience 0,
# the worn 8th ID (an Experience is written even when 0: shapes.add_card); the rest leave it out, as SigurdsStrike
# #1042 does.
REARGUARD_EXPERIENCE = 0
REARGUARD_CARDS = (ForceRow("M1_Abrams_US", 6), ForceRow("Rifles_US", 6, "M113A3_US"), ForceRow("M901_TOW_US", 3),
                   ForceRow("M113_Dragon_US", 2), ForceRow("AH1F_Cobra_US", 2))
SUPPORT_CARDS = (ForceRow("ATteam_TOW2_US", 4), ForceRow("Engineers_Dragon_US", 2))    # the shoulder and the anvil
FOREST_CARDS = (ForceRow("Rifles_half_Dragon_US", 6), ForceRow("Engineers_Flash_US", 2),  # the screen's forest infantry
                ForceRow("Panzergrenadier_IFV_RFA", 6), ForceRow("ATteam_Milan_2_RFA", 2))
# Captured Soviet equipment, hard to miss: no NATO look-alike, none in the Soviet waves, all self-propelled (no
# Transporter). The deploy hint names them by unit and count: their factory tabs (Tanks, Helis, Art) are only
# reachable once the buy menu may leave Groups mode (PROD_MENU_SWITCH).
SOVIET_CARDS = (ForceRow("T80U_SOV", 2), ForceRow("Ka_50_SOV", 2), ForceRow("TOS1_Buratino_SOV", 2))
# The buy menu's Groups/factory-tabs switch at the HUD restore (Content.prod_menu_switch). Every stock HUD node that
# shows the buy menu force-hides it, so the menu stays in Groups mode, and where that mode shows a card with no group
# (the Soviet cards, design 6.1's start cards) is unread; Default (stock's other value, written by omission, as the
# HUD restore leaves out ShowMinimap to show the minimap) should let the player switch to the factory tabs (the play
# sheet asks). Never ForceShow (no stock use).
PROD_MENU_SWITCH = BRICK_DEFAULT
# Locked until the spring (od_sprung = 1): the air corridor "is not open yet". Probe 1's A-10A [AT] card.
A10_CARD = "A10_Thunderbolt_II_ATGM_US"

EXTRA_SHAPES = (shapes.TRANSPORTER_SHAPE,)  # the deck cards with a carrier (shapes.add_card)

# --------------------------------------------------------------------------- geometry (one place: ITEMS)

# The mission's own named positions, minimap px (opendoor.map.POINTS holds the design's), each with its reason. Roads
# are read off Geisa's Minimap as probe 2's traffic road was (luminance 55-69 road, 70+ built-up); forest tracks read
# 43-49, the forest about 30 (the item tests check each). ENTRY_SE and FARM_ROAD, where the captured T-80U waits, are
# places the probes use too (modkit.ops.maps.GEISA_POINTS).
POINTS_OP: dict[str, Point] = {
    # the east tier's Starts: on a road 40-85 px W of each town (0.5-1 km)
    "START_TOWN_NE": (612.0, 234.0),    # the road into Town NE from the W (y 233-235), 46 px W of TOWN_NE
    "START_VILLAGE_E": (640.0, 491.0),  # the E-W road at y 489-492, 60 px W and 16 px S of VILLAGE_E
    "START_TOWN_SE": (590.0, 587.0),    # the road into Town SE from the W (y 585-588), 55 px W of TOWN_SE
    # the neck tier's Starts: on the jaws' forest tracks, never W of a neck (the sack)
    "START_NECK_MID": (379.0, 345.0),   # the M1A1HA's track N of NECK MID (x 377-381 here), 57 px N of it
    "START_NECK_S": (444.0, 692.0),     # the south-west track S of NECK S; SCREEN_SW (449, 692) is 5 px off the track
    # lane waypoints
    "SACK_S": (398.0, 621.0),           # the defile exit: the defile road 72 px WSW of NECK S, 40 px W of its zone
    "ANVIL_C": (140.0, 484.0),          # design 3's anvil vertex (138, 480), moved 4 px onto its village's E-W road
    # B6's approaches, just E of each neck's zone
    "APPR_MID": (452.0, 414.0),         # the passage road E of NECK MID (y 410-418 at x 428-475)
    "APPR_S": (526.0, 590.0),           # the road junction NE of NECK S, where the roads from the E meet (x 506-525)
    # the kill zone (design 3: the open plain between the lane exits, x 260-330, and the anvil, x 100-140): fields
    "PLAIN_N": (270.0, 440.0),          # W of the passage exit (SACK_MID)
    "PLAIN_C": (235.0, 525.0),          # the plain's middle, E of ANVIL_C
    "PLAIN_S": (310.0, 640.0),          # the defile's W stretch, from SACK_S toward Town SW
}


def px(point: str) -> Point:
    """A point of opendoor.map.POINTS or POINTS_OP, minimap px."""
    check(point in POINTS or point in POINTS_OP, f"{point} is in neither POINTS nor POINTS_OP")
    return POINTS[point] if point in POINTS else POINTS_OP[point]


def square(point: str, half: float) -> Box:
    """The square `half` px each side of `point`, minimap px (x0, y0, x1, y1)."""
    x, y = px(point)
    return Box(x - half, y - half, x + half, y + half)


CZ_HALF_PX = 30.0     # 30: probe 2's town squares (they cover each town's buildings on the Preview)
CZ_POINTS = 2                        # probe 1's (stock zones hold 1-5; 2 is the most common)
# Command zones: the three PL BLUE towns and the two necks (probe 2's 60 px squares on their points; no polygon of
# Geisa's own layout holds them: the probe and item tests check it), the anvil's north and centre (the same squares on
# ANVIL_N and ANVIL_C), and Town SW's (modkit.ops.maps.GEISA_BOXES, probe 1's OD_CZ_SW). Not Geisa's own zones
# P0_AutoName_6/_11 for the necks: _6 holds SACK_MID, inside the pocket, where a Soviet commander would keep a reopened
# tier neutral [[zone-capture-command-units]].
TOWN_CZ = {"OD_CZ_TownNE": "TOWN_NE", "OD_CZ_VillageE": "VILLAGE_E", "OD_CZ_TownSE": "TOWN_SE"}
NECK_CZ = {"OD_CZ_NeckMid": "NECK_MID", "OD_CZ_NeckS": "NECK_S"}
ANVIL_CZ = {"OD_CZ_AnvilN": square("ANVIL_N", CZ_HALF_PX), "OD_CZ_AnvilC": square("ANVIL_C", CZ_HALF_PX),
            "OD_CZ_SW": GEISA_BOXES["TOWN_SW"]}
# Load: every tier zone and the anvil's forced to NATO (deploy_phase, HoldUntilRelieved #107).
OWNED_AT_LOAD = (*TOWN_CZ, *NECK_CZ, *ANVIL_CZ)
# Deployment zones: each town's rearguard zone is its command zone minus the west REARGUARD_CUT_PX, where the tier's
# End lies; SHOULDER's is a square like the towns'; the anvil's (13, 250, 260, 800) holds Geisa's four west-edge
# arrival Ends (x 24-26 px) and the three anvil zones, and stops 105 px W of NECK MID's.
REARGUARD_CUT_PX = 12.0
TOWN_DZ = {"OD_DZ_TownNE": "TOWN_NE", "OD_DZ_VillageE": "VILLAGE_E", "OD_DZ_TownSE": "TOWN_SE"}
SHOULDER_DZ = square("SHOULDER", CZ_HALF_PX)
ANVIL_DZ = Box(13.0, 250.0, 260.0, 800.0)


def rearguard_box(point: str) -> Box:
    """A town's rearguard deployment zone: its command zone square minus the west REARGUARD_CUT_PX."""
    x0, y0, x1, y1 = square(point, CZ_HALF_PX)
    return Box(x0 + REARGUARD_CUT_PX, y0, x1, y1)


# The tiers. Each End lies END_INSET_PX inside the edge of its zone that faces the Start, on the zone's centre line: the
# east tier's inside the west edge (outside the rearguard zone, which starts 12 px in), the necks' inside the north
# (NECK MID) or south (NECK S) edge. In "fixed" mode each End also gets a FIXED_DZ_HALF_PX square deployment zone.
TIER_MODES = ("tiered", "fixed")
TIER_MODE = "tiered"                 # pl_blue hands the towns to PACT, pl_green the necks; "fixed" still builds
END_INSET_PX = 6.0
FIXED_DZ_HALF_PX = 6.0


class Tier(NamedTuple):
    name: str                        # the ReinforcementLocation item
    tier: str                        # "east" or "neck"
    cz: str                          # the command zone its End lies in
    start: Point                     # minimap px
    end: Point


def inset_end(point: str, side: str) -> Point:
    """END_INSET_PX inside the `side` edge ("W", "N" or "S") of the CZ_HALF_PX square on `point`, on its centre line."""
    x, y = px(point)
    reach = CZ_HALF_PX - END_INSET_PX
    return {"W": Point(x - reach, y), "N": Point(x, y - reach), "S": Point(x, y + reach)}[side]


TIERS: tuple[Tier, ...] = (
    Tier("OD_RL_TownNE", "east", "OD_CZ_TownNE", px("START_TOWN_NE"), inset_end("TOWN_NE", "W")),
    Tier("OD_RL_VillageE", "east", "OD_CZ_VillageE", px("START_VILLAGE_E"), inset_end("VILLAGE_E", "W")),
    Tier("OD_RL_TownSE", "east", "OD_CZ_TownSE", px("START_TOWN_SE"), inset_end("TOWN_SE", "W")),
    Tier("OD_RL_NeckMid", "neck", "OD_CZ_NeckMid", px("START_NECK_MID"), inset_end("NECK_MID", "N")),
    Tier("OD_RL_NeckS", "neck", "OD_CZ_NeckS", px("START_NECK_S"), inset_end("NECK_S", "S")),
)

# Circles (DetectUnitDansDetecteur reads circles only [[detector-circles-only]]; RadiusGRU from px at
# shapes.GRU_WORLD): the sack (the two lane exits and the kill zone, phase 2's count and the pocket), B6's approaches,
# and the rear exit.
RINGS = {
    "OD_RingSackMid": ("SACK_MID", 20.0),  # probe 2's passage-exit circle
    "OD_RingSackS": ("SACK_S", 20.0),
    "OD_RingPlainN": ("PLAIN_N", 40.0),
    "OD_RingPlainC": ("PLAIN_C", 40.0),
    "OD_RingPlainS": ("PLAIN_S", 40.0),
    "OD_RingApprMid": ("APPR_MID", 20.0),
    "OD_RingApprS": ("APPR_S", 22.0),
    "OD_RingRear": ("EDGE_W", 30.0),                         # the rear exit: the E-W road at the west edge
}
# Hidden jaws (design 6.2): the force table's rows at FORCE_SCALE, in a grid RESERVE_SPACING_PX apart, `cols` to a
# row, centred on their point (formation). Revealed by SpawnUnits on the spring [[spawn-and-create-units]].
RESERVE_SPACING_PX = 8.0             # probe 1's hidden reserves' spacing
JAWS = {"north_jaw": ("OD_NorthJaw", "RESERVE_N", 6), "south_jaw": ("OD_SouthJaw", "HIDE_S", 4)}
CAPTURED_UNIT = "T80U_SOV"
# Spawn and waypoint tags: the first echelon's entries, and each lane's named waypoints.
TAGS = {"OD_EntryN": "ENTRY_N", "OD_EntryE": "ENTRY_E", "OD_EntrySE": "ENTRY_SE",
        "OD_NeckMid": "NECK_MID", "OD_SackMid": "SACK_MID", "OD_AnvilC": "ANVIL_C", "OD_RearExit": "EDGE_W",
        "OD_TownSE": "TOWN_SE", "OD_NeckS": "NECK_S", "OD_SackS": "SACK_S", "OD_TownSW": "TOWN_SW"}
# Each PL BLUE town's flag key (od_town_<key>, its race's od_town_<key>_held, its hint od_hf<key>).
TOWN_KEYS = {"OD_CZ_TownNE": "ne", "OD_CZ_VillageE": "ve", "OD_CZ_TownSE": "se"}


class Company(NamedTuple):
    """A first-echelon company: its rows, created at `entry` into od_fe_<key> but for the riflemen (od_fe_<key>_inf)
    and their carriers (od_fe_<key>_ifv), which board first; then it seizes `town`."""
    key: str
    entry: str                       # its spawn tag (TAGS)
    town: str                        # the command zone it seizes (TOWN_CZ)
    rows: tuple[ForceRow, ...]       # the first_echelon rows


# Design 6.3's first echelon (the force table's "first_echelon" at FORCE_SCALE, 36) split into three companies, one per
# lane: N 11 from ENTRY N on Town NE, C 14 with the battalion's BMP-1 command vehicle (the one unit that captures
# [[zone-capture-command-units]]) from ENTRY E on Village E, S 11 from ENTRY SE on Town SE (tanks 3/4/3, a BMP-2
# platoon with its riflemen 2/4/2, recon, ATGM and air defence spread). Towns NE and SE fall by the race.
_FLANK = (ForceRow("T80B_SOV", 3), ForceRow("BMP_2_SOV", 2), ForceRow("MotRifles_SOV", 2, "BMP_2_SOV"),
          ForceRow("BRDM_2_SOV", 1), ForceRow("BRDM_2_Konkurs_SOV", 1), ForceRow("Scout_SOV", 1),
          ForceRow("ZSU_23_Shilka_SOV", 1))
FE_COMPANIES: tuple[Company, ...] = (
    Company("n", "OD_EntryN", "OD_CZ_TownNE", _FLANK),
    Company("c", "OD_EntryE", "OD_CZ_VillageE", (ForceRow("T80B_SOV", 4), ForceRow("BMP_2_SOV", 4),
                                                 ForceRow("MotRifles_SOV", 4, "BMP_2_SOV"),
                                                 ForceRow("BMP_1_CMD_SOV", 1), ForceRow("BRDM_Strela_1_SOV", 1))),
    Company("s", "OD_EntrySE", "OD_CZ_TownSE", _FLANK),
)
FE_TOTAL = group_total(forces.force_rows("first_echelon"), "first_echelon")
# B1 counts the player's kills of these types (GetNbKillsCamp [[kill-counts-by-type]]): the first echelon's
# descriptors, in table order.
FE_TYPES = tuple(dict.fromkeys(r.unit for r in forces.force_rows("first_echelon")))


def tally(rows: Iterable[ForceRow]) -> Counter:
    """(unit, transport) -> count over `rows`: FE_COMPANIES' or the table's."""
    out: Counter = Counter()
    for r in rows:
        out[r.unit, r.transport] += r.count
    return out


def fe_tallies() -> tuple[Counter, Counter]:
    """(FE_COMPANIES' tally, the first_echelon rows' tally at FORCE_SCALE): equal while the split holds."""
    return (tally(row for c in FE_COMPANIES for row in c.rows),
            tally(forces.force_rows("first_echelon")))


# A FORCE_SCALE or table change must re-split the companies (design 6.4: a table edit plus one replay).
check(fe_tallies()[0] == fe_tallies()[1], "FE_COMPANIES no longer split the first_echelon rows at FORCE_SCALE: "
                                          "re-split them")


# The lanes (modkit.ops.mission.Lane: an entry tag and its legs, each Leg a waypoint tag of TAGS, by FastMoveAndAttack
# [[fast-move-and-attack-keeps-roads]], raced against its timeout but the last). The two lanes into the sack, each
# ending at the rear exit (EDGE W, OD_RingRear's centre): design 3's passage (MID)
# and defile (BOTTOM). The roads between the waypoints are Geisa's own (the item tests follow each on the Minimap):
# MID from ENTRY E along probe 2's traffic road through NECK MID and out of the passage at SACK MID, across the plain
# to the anvil's village; BOTTOM from ENTRY SE into Town SE, north-west then south-west to the defile village NECK S,
# down the defile to SACK S and west to Town SW. Timeouts: LEG_PACE_S_PER_PX on each leg's road (MID 362, 56, 214 px;
# BOTTOM 112, 219, 71, 292 px), rounded up to 10 s, at least LEG_MIN_S.
LANES: dict[str, Lane] = {
    "MID": Lane("OD_EntryE", (Leg("OD_NeckMid", 240.0), Leg("OD_SackMid", 60.0), Leg("OD_AnvilC", 150.0),
                              Leg("OD_RearExit", None))),
    "BOTTOM": Lane("OD_EntrySE", (Leg("OD_TownSE", 80.0), Leg("OD_NeckS", 150.0), Leg("OD_SackS", 60.0),
                                  Leg("OD_TownSW", 200.0), Leg("OD_RearExit", None))),
}


# Design 6.3's main body and its Pocket_AD (the force table's "main_body" and "pocket_ad" at FORCE_SCALE: 60 vehicles
# and 9 riflemen) in six waves (modkit.ops.mission.Wave: key, offset after the release, a LANES key, the force table's
# rows), one a minute from the release, alternating MID and BOTTOM. Each is created into od_mb<key> but for the
# riflemen (od_mb<key>_inf) and their carriers (od_mb<key>_ifv), which board first; then it drives its lane.
WAVES: tuple[Wave, ...] = (
    Wave(1, 0 * WAVE_GAP_S, "MID", (ForceRow("T80BV_SOV", 10),)),
    Wave(2, 1 * WAVE_GAP_S, "BOTTOM", (ForceRow("T80BV_SOV", 10),)),
    Wave(3, 2 * WAVE_GAP_S, "MID", (ForceRow("BMP_2_SOV", 10), ForceRow("MotRifles_SOV", 9, "BMP_2_SOV"),
                                    ForceRow("BRDM_2_Konkurs_SOV", 3))),
    Wave(4, 3 * WAVE_GAP_S, "BOTTOM", (ForceRow("T80BV_SOV", 10), ForceRow("T80BV_CMD_SOV", 1))),
    Wave(5, 4 * WAVE_GAP_S, "MID", (ForceRow("Tunguska_2K22_SOV", 2), ForceRow("Osa_9K33M3_SOV", 2),
                                    ForceRow("MTLB_Strela10_SOV", 2), ForceRow("BMP_1_CMD_SOV", 1))),
    Wave(6, 5 * WAVE_GAP_S, "BOTTOM", (ForceRow("2S3M_Akatsiya_SOV", 6), ForceRow("MTLB_supply_SOV", 3))),
)
MB_ROWS = (*forces.force_rows("main_body"), *forces.force_rows("pocket_ad"))
MB_TOTAL = sum(r.count for r in MB_ROWS if r.transport is None)      # od_mb: the vehicles (the catch's base)
MB_DISMOUNTS = sum(r.count for r in MB_ROWS if r.transport is not None)
# Design 5.5's grade bands as counts of MB_TOTAL (design 6.4: thresholds are shares): 42 and 24 of 60.
CATCH_TOTAL_N, CATCH_MAJOR_N = (share_count(share, MB_TOTAL) for share in CATCH_SHARES)


class Seal(NamedTuple):
    """A neck P5 seals: its command zone, the key of its flag (od_sealed_<key>, a phase flag) and race
    (od_p5_<key>_held), its seal hint's turn (seal_hints), its seal hint token (mode_hint) and P5's text token (the
    label is text + "l")."""
    cz: str
    key: str
    turn: int
    hint: str
    text: str


SEALS: tuple[Seal, ...] = (Seal("OD_CZ_NeckMid", "mid", HTURN_MID, "od_hsm", "od_p5m"),
                           Seal("OD_CZ_NeckS", "s", HTURN_S, "od_hss", "od_p5s"))


def mb_tallies() -> tuple[Counter, Counter]:
    """(WAVES' tally, the main_body and pocket_ad rows' tally at FORCE_SCALE): equal while the split holds."""
    return (tally(row for w in WAVES for row in w.rows),
            tally(MB_ROWS))


check(mb_tallies()[0] == mb_tallies()[1], "WAVES no longer split the main_body and pocket_ad rows at FORCE_SCALE: "
                                          "re-split them")


def tier_item(t: Tier) -> LdItem:
    """A tier's ReinforcementLocation, laid out as Geisa's own (GEISA.west_arrivals): the item at the middle of Start
    and End, Rotation the angle from Start to End (world y grows southward), NumAlliance omitted (never -1: a zone the
    enemy holds must close it for both sides)."""
    (sx, sy), (ex, ey) = GEISA.px_to_world(t.start), GEISA.px_to_world(t.end)
    return LdItem("ReinforcementLocations", t.name, (sx + ex) / 2, (sy + ey) / 2, "ReinforcementLocation",
                  rotation=math.atan2(ey - sy, ex - sx), start=(sx, sy), end=(ex, ey))


def jaw_items(group: str) -> list[LdItem]:
    """The hidden player (camp 0) spawns of a jaw (modkit.ops.mission.hidden_units): one per unit of its force table
    rows, in row order, named <prefix>_01, <prefix>_02, ..."""
    prefix, point, cols = JAWS[group]
    units = [r.unit for r in forces.force_rows(group) for _ in range(r.count)]
    return hidden_units(MAP, px(point), [(f"{prefix}_{k + 1:02d}", unit) for k, unit in enumerate(units)],
                        RESERVE_SPACING_PX, cols, group)


def items(tier_mode: str | None = None) -> list[LdItem]:
    """Every LevelDesign item of the op for `tier_mode` (TIER_MODE when None)."""
    mode = tier_mode or TIER_MODE
    check(mode in TIER_MODES, f"tier mode {mode!r} is not one of {TIER_MODES}")
    zone = MAP.zone_item
    out = [
        # deployment zones: the rearguard's three towns, SHOULDER, the anvil (the design's deploy row)
        *(zone("DeploymentZone", name, rearguard_box(point), "DeploymentZone") for name, point in TOWN_DZ.items()),
        zone("DeploymentZone", "OD_DZ_Shoulder", SHOULDER_DZ, "DeploymentZone"),
        zone("DeploymentZone", "OD_DZ_Anvil", ANVIL_DZ, "DeploymentZone"),
        # command zones
        *(zone("CommandPoints", name, square(point, CZ_HALF_PX), "CommandPoints", points=CZ_POINTS)
          for name, point in {**TOWN_CZ, **NECK_CZ}.items()),
        *(zone("CommandPoints", name, box, "CommandPoints", points=CZ_POINTS) for name, box in ANVIL_CZ.items()),
        # arrivals: the permanent west tier (Ends in OD_DZ_Anvil) and the five tiers
        *GEISA.player_arrivals("OD"),
        *(tier_item(t) for t in TIERS),
        # circles
        *(MAP.ring_item(name, px(point), radius) for name, (point, radius) in RINGS.items()),
        # hidden: the jaws, and the captured T-80U (a backup for the captured cards)
        *jaw_items("north_jaw"), *jaw_items("south_jaw"),
        MAP.item("Camp_0", "OD_Captured", px("FARM_ROAD"), "Spawn", unit=CAPTURED_UNIT, camp=0,
                 disable_auto_spawn=True, group="captured"),
        # spawn and waypoint tags
        *(MAP.item("Tags", name, px(point), "Name") for name, point in TAGS.items()),
    ]
    if mode == "fixed":  # the fallback: each tier End in a small player deployment zone of its own
        out += [zone("DeploymentZone", f"OD_DZ_{t.name.removeprefix('OD_')}",
                     (t.end[0] - FIXED_DZ_HALF_PX, t.end[1] - FIXED_DZ_HALF_PX,
                      t.end[0] + FIXED_DZ_HALF_PX, t.end[1] + FIXED_DZ_HALF_PX), "DeploymentZone") for t in TIERS]
    return out


ITEMS: list[LdItem] = items()


def tiered_arrivals(tier_mode: str | None = None) -> tuple[str, ...]:
    """The tier entries gate 3 tiers holds to the tier rule: all five in "tiered" mode, none in "fixed" (each End
    also lies in a player deployment zone there, as check_arrivals asks of any entry)."""
    return tuple(t.name for t in TIERS) if (tier_mode or TIER_MODE) == "tiered" else ()


class Ctx(profile.Ctx):
    """opendoor.profile.Ctx over the op's items for `tier_mode` (TIER_MODE when None), its tags keyed to the op's
    scenario (the binding gate fails tags made for another scenario)."""

    def __init__(self, tier_mode: str | None = None) -> None:
        self.tier_mode = tier_mode or TIER_MODE
        super().__init__(items(self.tier_mode), profile.SCENARIO)


def item(name: str, tier_mode: str | None = None) -> LdItem:
    """The item named `name` (of `tier_mode`'s items)."""
    hits = [it for it in (ITEMS if tier_mode is None else items(tier_mode)) if it.name == name]
    check(len(hits) == 1, f"{len(hits)} items are named {name}")
    return hits[0]


# --------------------------------------------------------------------------- shared pieces of the beats

# tier_handover(ctx, side, zones, hint) is modkit.ops.mission.zone_handover: `side` ("NATO" or "PACT") takes the
# command zones named `zones`, then the hint: the game shows nothing when a land corridor opens or closes. In "tiered"
# mode a zone handed to PACT closes its tier and one handed back to NATO reopens it; in "fixed" mode only the zone's
# colour changes, so the caller's hint says so (mode_hint). Probe 2's count-race hand-over [[count-race-forced-owner]]:
# a hint picked at run time is an action (pl_green), and towns whose hints take turns elsewhere (pl_blue's town_hints)
# pass None.


# --------------------------------------------------------------------------- endings and defeats

def end_funnel(ctx: Ctx) -> Node:
    """The one ending node (profile.END_FUNNEL; modkit.ops.mission.end_funnel), run from load beside the battle: once
    od_end >= 1, the dialog and the TriggerEndGame of od_end's ENDINGS row, END_LOST the last else. There is no
    EndRace. Only the first TriggerEndGame of a battle counts [[mission-ends-only-by-script]], and od_end is written
    only through shapes.set_end, so the first ending stands and later writers find it nonzero."""
    return ops_mission.end_funnel(ctx.int_var("od_end"), ENDINGS, profile.END_FUNNEL)


def anvil(ctx: Ctx) -> Node:
    """Defeat (design 4): one zone_race per anvil command zone, PACT >= ANVIL_PACT_N and NATO none for ANVIL_HOLD_S,
    then set_end(END_ANVIL). Each Sequential ends in the IfThenElse of set_end, so every race can fire and the first
    od_end stands."""
    return g_simul([g_seq([zone_race(ctx, [zone], "PACT", "NATO", ANVIL_PACT_N, ANVIL_HOLD_S,
                                     ctx.int_var(f"od_anv_held_{k}")),
                           shapes.set_end(ctx.int_var("od_end"), END_ANVIL)]) for k, zone in enumerate(ANVIL_CZ)])


def rear_exit(ctx: Ctx) -> Node:
    """Defeat (design 4): WaitCondition(REAR_N or more main-body vehicles inside the circle OD_RingRear), then
    set_end(END_REAR). The constraint is the types alone, as probe 1's probe ring (stock has no All-of-Any constraint,
    gate 2); the player's deck holds none of them (the captured cards are T-80U, Ka-50, TOS-1). Infantry (rows with a
    transport) are not counted."""
    vehicles = [r.unit for r in forces.force_rows("main_body") if r.transport is None]
    ring = ctx.tag("OD_RingRear")
    pact_vehicles = c_any(*(c_type(u) for u in dict.fromkeys(vehicles)))
    return g_seq([g_until(g_detect(ring, pact_vehicles, REAR_N, GE)), shapes.set_end(ctx.int_var("od_end"), END_REAR)])


def p2(ctx: Ctx) -> Node:
    """Armed at load: P2 HOLD THE ANVIL, fail-only (TheHydra #101: no Condition). It starts after the battle is
    launched (Phase BATTLE_PHASE: the timeline shows it from H+0:00) and Groupe_Joueur >= 1 (an objective whose
    condition already holds resolves at its start: gates.check_empty_group_guard). ConditionEchec = Or[Groupe_Joueur
    == 0, od_end >= END_ANVIL]: the whole force lost, or an anvil or rear-exit loss already written. ActionsEchec =
    set_end(END_LOST), which does nothing once od_end is set, so that loss stands. The objective goes last in its
    Sequential (it never finishes [[objective-waits-until-resolved]], gate 3)."""
    group, end = ctx.group("Groupe_Joueur"), ctx.int_var("od_end")
    return g_seq([g_until(Node("TGDConditionPhase", [("Phase", i32(BATTLE_PHASE))])), g_until(g_cmp(group, 1, GE)),
                  objective("od_p2", "od_p2l", None, fail=g_or(g_cmp(group), g_cmp(end, END_ANVIL, GE)),
                            echec=g_seq([shapes.set_end(ctx.int_var("od_end"), END_LOST)]))])


# --------------------------------------------------------------------------- beats

def load_deck(ctx: Ctx) -> Node:
    """Load: design 6.1's start cards (the rearguard's at Experience 0, the Rifles in M113A3; TOW-2 and engineers for
    the shoulder and the anvil; the screen's forest infantry), then the captured Soviet cards (SigurdsStrike #1042's
    shape, Experience omitted), then the A-10A lock until the spring (od_sprung = 1). The lock goes last: its race
    holds the Sequential until the spring."""
    cards = [shapes.add_card(ctx, c.unit, c.count, transport=c.transport, experience=REARGUARD_EXPERIENCE)
             for c in REARGUARD_CARDS]
    cards += [shapes.add_card(ctx, c.unit, c.count) for c in (*SUPPORT_CARDS, *FOREST_CARDS, *SOVIET_CARDS)]
    return g_seq([*cards, lock_card(ctx, A10_CARD, g_cmp(ctx.int_var("od_sprung"), 1))])


def difficulty(ctx: Ctx) -> Node:
    """Load: modkit.ops.mission.difficulty over od_diff and KNOBS: od_diff = DIFF_NONE, every knob at its Medium
    value, then the three branches (read right after LoadingDone and its intro, during deployment) set od_diff to 0,
    1 or 2, Easy's and Hard's overwriting the knobs; with none (no difficulty reached the script: every condition is
    false [[difficulty-branches]]) od_diff becomes Medium. Each case's hint (od_hdif0/1/2, od_hdif9 for "not
    received") shows DIFF_HINT_T after "Launch battle", never beside the deploy hint."""
    return ops_mission.difficulty(ctx, ctx.int_var("od_diff"), KNOBS, "od_hdif", DIFF_HINT_T)


# --------------------------------------------------------------------------- phase 1

def mode_hint(ctx: Ctx, token: str) -> str:
    """A hint about a tier: `token` in "tiered" mode, `token`_f in "fixed" mode, where the tier stays open and only the
    zone's colour changes (the fallback's hints say so)."""
    return token if ctx.tier_mode == "tiered" else f"{token}_f"


def p1(ctx: Ctx) -> Node:
    """H+0:00: the phase hint beside P1 SELL THE RETREAT (design 4.1), pinned on Village E (PL BLUE's point):
    od_p1_min = P1_MINUTES, then one a minute off it (its %1) beside the objective. P1 completes on od_plblue (all three
    towns fell, pl_blue). It fails once PL BLUE is released without its fall (od_released = 1, od_plblue = 0: H+12,
    since the release always writes od_plblue before od_released) and its own counter reads 0: the countdown's 12th
    step and the release both come at H+12 on two clocks, and the failure waits for both, so the row freezes on "0 min
    left" whichever comes first (the objective reads the variable it shows [[objective-counters]]). Failing shows the
    dialog od_dheld (or od_dheld_f in "fixed" mode), H+12's one announcement: no hint beside it. The objective is last
    in its Simultaneous (gate 3)."""
    left, plblue, released = ctx.int_var("od_p1_min"), ctx.int_var("od_plblue"), ctx.int_var("od_released")
    countdown = g_seq([g_wait(60.0), g_modify(left, SUB, 1)], runs=P1_MINUTES)
    p1_objective = objective("od_p1", "od_p1l", g_cmp(plblue, 1), ctx.tag("OD_CZ_VillageE"), [left],
                             fail=g_and(g_cmp(released, 1), g_cmp(plblue), g_cmp(left)),
                             echec=g_seq([g_dialog(mode_hint(ctx, "od_dheld"))]))
    return shapes.beat_hint("od_hph1", g_seq([g_set(left, P1_MINUTES), g_simul([countdown, p1_objective])]))


def b1(ctx: Ctx) -> Node:
    """H+0:00: bonus B1 MAKE THEM PAY (design 4.1), "%1 / %2" = the player's first-echelon kills and od_b1_n (a
    difficulty knob). Condition: kills >= od_b1_n, a variable against a variable as HoldUntilRelieved #161 (#267: Reach
    %1 / %2, its Condition reading the variable it shows); ConditionEchec: od_released = 1, the window's close (a
    windowed objective resolves through its ConditionEchec). Kills are counted by type [[kill-counts-by-type]]: every
    POLL_S, GetNbKillsCamp(NATO, FE_TYPES) writes od_b1_k (g_kills: probe 2's counter, proven in its first play;
    TheDieburgSalient #332 polls it in Sequential(forever)[it, WaitDuration 1]). Until od_released the first echelon is
    the only Soviet force on the map, so these are first-echelon kills; a group's alive count would instead depend on
    whether riflemen riding in their BMP-2s count as alive (unread). The poll's one write is the round's last, and the
    objective reads the variable it shows, so it freezes on the round that completes it (probe 2's shape). The poll
    stops at the release."""
    released, kills, need = ctx.int_var("od_released"), ctx.int_var("od_b1_k"), ctx.int_var("od_b1_n")
    poll = g_seq([g_kills(kills, ctx.camp("NATO"), FE_TYPES), g_wait(POLL_S)], runs=FOREVER)
    bonus = objective("od_b1", "od_b1l", g_cmp(kills, op=GE, other=need), counters=[kills, need],
                      fail=g_cmp(released, 1), kind="Bonus")
    return g_simul([g_seq([g_compete([poll, g_until(g_cmp(released, 1))])]), bonus])


def captured(ctx: Ctx) -> Node:
    """H+0:30, the captured cards' backup: SpawnUnits reveals OD_Captured, the hidden T-80U, which joins
    Groupe_Joueur, then the hint od_hcapt. Survivors' captured T-55 (Sequential #1086: SpawnUnits #1330,
    AddUnitGroupListToUnitGroup #1331) without its SetAmmo and SetFuel: it comes full."""
    tank = ctx.tag("OD_Captured")
    return g_seq([g_spawn([tank]), g_union(ctx.group("Groupe_Joueur"), [tank]),
                  g_simul([g_hint("od_hcapt", HINT_S, "shint")])])


def first_echelon(ctx: Ctx) -> Node:
    """H+1:00: each FE_COMPANIES row is created at its company's entry (create_rows: CreateUnitOnPosition, PACT): the
    riflemen into od_fe_<key>_inf, their BMP-2s into od_fe_<key>_ifv, the rest into od_fe_<key>, which the two then
    join. Then, per company and side by side, the riflemen board (board(), up to BOARD_S) and the company seizes its
    town (LaunchSmartOrder Seize: TheDieburgSalient #514/#519 create, then seize). The Seize is the company's last order
    (gates.check_smart_orders): no stock script orders a smart-ordered group again in a Sequential, and nothing may
    route these groups west (the rear exit counts BMP-2s, which they share with the main body). No beat reads these
    groups (B1 counts kills by type)."""
    attacks, creates = [], []
    for c in FE_COMPANIES:
        group, inf, ifv = (ctx.group(f"od_fe_{c.key}{suffix}") for suffix in ("", "_inf", "_ifv"))
        creates += create_rows(ctx, "PACT", c.rows, ctx.tag(c.entry), group, inf, ifv)
        creates.append(g_union(group, [inf, ifv]))
        attacks.append(g_seq([board(inf, ifv, BOARD_S), g_seize(group, ctx.tag(c.town))]))
    return g_seq([*creates, g_simul(attacks)])


def town_hints(ctx: Ctx) -> Node:
    """PL BLUE's fall hints one at a time (towns falling within one hint's 15 s would overlap), as phase 3's
    seal_hints: Sequential[Competition[
      Sequential(NbExecutions = 3)[WaitCondition(a town fallen and not yet said: Or[And[od_town_<key> = 1,
        od_said_<key> = 0]] over the towns), the first such town in TOWN_CZ order (an IfThenElse chain, the last town
        the last else: the wait just found one): od_said_<key> = 1, then its hint (mode_hint: od_hf<key>, or the _f
        twin in "fixed" mode) beside a HINT_S wait],
      WaitCondition(od_released = 1 and od_plblue = 0: H+12)]].
    Each round says one town and holds the next round its whole 15 s, so towns that fall in one second show their hints
    HINT_S apart, each once, and a town that falls later shows at once. If PL BLUE fell (od_plblue = 1, written before
    od_released) all three are said and the race never cuts it; at H+12 it stops, so the forcing adds no hint and a town
    still waiting its turn is dropped: H+12 shows P1's dialog od_dheld and at most the one hint already showing. With
    every town held it waits for nothing until H+12. In its own Sequential, as b1's poll."""
    released, plblue = ctx.int_var("od_released"), ctx.int_var("od_plblue")
    keys = list(TOWN_KEYS.values())

    def pending(key: str) -> Node:
        return g_and(g_cmp(ctx.int_var(f"od_town_{key}"), 1), g_cmp(ctx.int_var(f"od_said_{key}")))

    def say(key: str) -> Node:
        return g_seq([g_set(ctx.int_var(f"od_said_{key}"), 1),
                      g_simul([g_hint(mode_hint(ctx, f"od_hf{key}"), HINT_S, "shint"), g_wait(HINT_S)])])

    pick = say(keys[-1])
    for key in reversed(keys[:-1]):
        pick = g_if(pending(key), say(key), pick)
    rounds = g_seq([g_until(g_or(*(pending(key) for key in keys))), pick], runs=len(keys))
    return g_seq([g_compete([rounds, g_until(g_and(g_cmp(released, 1), g_cmp(plblue)))])])


def pl_blue(ctx: Ctx) -> Node:
    """From H+0:00. Per town, side by side: Competition[WaitCondition(PACT controls it), Sequential[its race]
    (zone_race: PACT >= TOWN_PACT_N and NATO none for TOWN_HOLD_S; no stock Competition holds a Competition bare),
    WaitCondition(od_released = 1)]; then, if PL BLUE is not released yet, od_town_<key> = 1 and tier_handover(PACT,
    the town) with no hint: the towns' hints take turns in town_hints, beside them. Beside those the release:
    Competition[all three flags, then od_plblue = 1; WaitDuration P1_DEADLINE_S (H+12)], then od_released = 1, then, if
    PL BLUE fell, the hint od_hopen once town_hints has said all three (od_said_<key> = 1 each: it only says fallen
    towns, and with od_plblue = 1 all three fell), HINT_S after the last (no two hints at once); else (H+12) the forcing
    of all three towns to PACT with no hint of its own: P1's failure dialog (od_dheld, od_dheld_f) announces it, so
    H+12 shows one dialog and at most one hint, a town's that fell just before. The rest are forced (one already PACT's
    stays PACT's), and a town still racing ends quietly on the flag. A NATO unit parked in a town holds its race false;
    H+12 still releases. A NATO commander may win a town back and reopen its tier [[zone-capture-command-units]]."""
    released, plblue, pact = ctx.int_var("od_released"), ctx.int_var("od_plblue"), ctx.camp("PACT")

    def town(cz: str) -> Node:
        key = TOWN_KEYS[cz]
        falls = g_compete([g_until(g_zone_control(pact, ctx.tag(cz))),
                           g_seq([zone_race(ctx, [cz], "PACT", "NATO", TOWN_PACT_N, TOWN_HOLD_S,
                                            ctx.int_var(f"od_town_{key}_held"))]),
                           g_until(g_cmp(released, 1))])
        handover = tier_handover(ctx, "PACT", [cz], None)
        return g_seq([falls, g_if(g_cmp(released), g_seq([g_set(ctx.int_var(f"od_town_{key}"), 1), handover]))])

    fell = g_and(*(g_cmp(ctx.int_var(f"od_town_{key}"), 1) for key in TOWN_KEYS.values()))
    said = g_and(*(g_cmp(ctx.int_var(f"od_said_{key}"), 1) for key in TOWN_KEYS.values()))
    release = g_seq([g_compete([g_seq([g_until(fell), g_set(plblue, 1)]), g_wait(P1_DEADLINE_S)]),
                     g_set(released, 1),
                     g_if(g_cmp(plblue, 1), g_seq([g_until(said), g_wait(HINT_S),
                                                   g_simul([g_hint("od_hopen", HINT_S, "shint")])]),
                          g_seq([g_zone_owner(pact, [ctx.tag(cz) for cz in TOWN_CZ])]))])
    return g_simul([*(town(cz) for cz in TOWN_CZ), town_hints(ctx), release])


# --------------------------------------------------------------------------- phase 2

def lane_route(ctx: Ctx, group: Node, lane: str) -> Node:
    """`group` drives the lane LANES[`lane`] by its waypoints (modkit.ops.mission.lane_route: FastMoveAndAttack, each
    leg but the last raced against its timeout, probe 2's traffic beat). The last leg, to the rear exit, is a plain
    order: nothing follows it."""
    return ops_mission.lane_route(ctx, group, LANES[lane].legs)


def main_body(ctx: Ctx) -> Node:
    """From H+0:00: once PL BLUE is released (od_released = 1), the six WAVES side by side, each its own
    Sequential from its offset (modkit.ops.mission.wave, PACT, into the groups od_mb<key>): created at its lane's
    entry, the vehicles joining od_mb (MB_TOTAL, the catch's base) and the riflemen od_mb_inf, the riflemen boarding
    (up to BOARD_S), then its lane (lane_route), its only order. Each lane ends at the rear exit, which counts the main
    body's vehicle types (rear_exit)."""
    return g_seq([g_until(g_cmp(ctx.int_var("od_released"), 1)),
                  g_simul([wave(ctx, w, LANES, side="PACT", prefix="od_mb", board_s=BOARD_S) for w in WAVES])])


def sack_vehicles(ctx: Ctx) -> Node:
    """The Soviet vehicles: AllContrainte[Team PACT, NoContrainte[the SACK_INFANTRY types]] (no category brick exists;
    stock nests both: gate 2). A fresh node per call."""
    return c_all(c_team(ctx.camp("PACT")), c_none(*(c_type(u) for u in SACK_INFANTRY)))


def sack(ctx: Ctx) -> Node:
    """The sack count (design 5.2): every SACK_POLL_S and forever, a ring_round over SACK_RINGS (modkit.ops.mission:
    a group never holds a unit twice [[detector-circles-only]], so the overlapping circles count a unit once) of the
    Soviet vehicles (sack_vehicles) into od_sackg, whose count is od_sack, so P4 never reads a half-done value."""
    units = ctx.group("od_sackg")
    return g_seq([*ring_round(ctx, units, SACK_RINGS, lambda: sack_vehicles(ctx), ctx.int_var("od_sack")),
                  g_wait(SACK_POLL_S)], runs=FOREVER)


def p4(ctx: Ctx) -> Node:
    """P4 LET THEM IN (design 4.1), "%1 / %2" = od_sack and od_smin (a difficulty knob): Condition od_sack >= od_smin,
    a variable against a variable (HoldUntilRelieved #161), reading the variable it shows, so the row freezes on the
    round that completes it; ActionsReussi od_p4 = 1 (a bare ModifieVariableInteger: stock), which starts the spring's
    asks. ConditionEchec od_sprung = 1: Corps sprang the trap at H+30 or at the anvil before S_min was reached (the
    design: "none; Corps springs it at the deadline"), so the row does not stay open (no Competition retires an
    objective)."""
    count, smin = ctx.int_var("od_sack"), ctx.int_var("od_smin")
    return objective("od_p4", "od_p4l", g_cmp(count, op=GE, other=smin), counters=[count, smin],
                     fail=g_cmp(ctx.int_var("od_sprung"), 1), reussi=g_set(ctx.int_var("od_p4"), 1))


def spring(ctx: Ctx) -> Node:
    """From H+0:00, design 5.2: once PL BLUE is released, the sack count and P4 side by side; beside them the spring.
    od_spr_pick = od_spr_ans = CHOICE_NONE (a stale or unset 0 would read as FIRE AT WILL), then Competition[
      - once P4 is done (od_p4 = 1), the ask loop (modkit.ops.mission.reask_loop), forever: pick = ans =
        CHOICE_NONE, od_spr_open = 1, the dialog od_dspring (g_choice: FIRE AT WILL = now, HOLD FIRE = wait;
        SelectedButton = pick), ans = pick once the dialog has closed (no exit reads the live SelectedButton
        [[dialog-reask-loop]]), od_spr_open = 0, then SPRING_GAP_S;
      - WaitCondition(ans == SPRING_NOW);
      - H+30: WaitDuration SPRING_DEADLINE_S from the beat's start ("Launch battle"), then od_spr_open = 0;
      - the anvil contested: once released, WaitCondition(And[PACT >= 1 in the union of the anvil command zones,
        od_spr_open = 0])]
    (probe 2's ask loop raced against its exits: BackhandBlow Competition#194's forever dialog loops against a
    WaitCondition). The two automatic exits wait for no dialog to be open, so the race never ends mid-dialog. Then,
    unless the answer was FIRE AT WILL, the dialog od_dauto ("Corps springs it"); then od_sprung = 1, written once
    (IfThenElse on 0, set_end's latch). Phase 3 starts on od_sprung."""
    released, sprung = ctx.int_var("od_released"), ctx.int_var("od_sprung")
    pick, ans, asking = ctx.int_var("od_spr_pick"), ctx.int_var("od_spr_ans"), ctx.int_var("od_spr_open")
    ask = reask_loop("od_dspring", Buttons(BUTTON_NOW, BUTTON_WAIT), ctx.camp("NATO"), pick, ans, asking, SPRING_GAP_S)
    contested = g_and(g_units_in_zones([ctx.tag(z) for z in ANVIL_CZ], c_team(ctx.camp("PACT")), 1, GE),
                      g_cmp(asking))
    exits = g_compete([g_seq([g_until(g_cmp(ctx.int_var("od_p4"), 1)), ask]),
                       g_until(g_cmp(ans, SPRING_NOW)),
                       g_seq([g_wait(SPRING_DEADLINE_S), g_until(g_cmp(asking))]),
                       g_seq([g_until(g_cmp(released, 1)), g_until(contested)])])
    decide = g_seq([g_set(pick, CHOICE_NONE), g_set(ans, CHOICE_NONE), exits,
                    g_if(g_cmp(ans, SPRING_WAIT, GE), g_seq([g_dialog("od_dauto")])),
                    g_if(g_cmp(sprung), g_simul([g_set(sprung, 1)]))])
    return g_simul([g_seq([g_until(g_cmp(released, 1)), g_simul([sack(ctx), p4(ctx)])]), decide])


def b6(ctx: Ctx) -> Node:
    """Bonus B6 MAKE A STAND AT PL GREEN (design 4.1), "%1 / %2" = od_b6_t and od_b6_s (a difficulty knob, seconds):
    Condition od_b6_t >= od_b6_s (variable against variable, as P4), ActionsReussi od_b6 = 1 (the window's first
    close); ConditionEchec od_window = WINDOW_CLOSED, the window's close (a windowed objective resolves through its
    ConditionEchec). It buys nothing yet."""
    seconds, need = ctx.int_var("od_b6_t"), ctx.int_var("od_b6_s")
    return objective("od_b6", "od_b6l", g_cmp(seconds, op=GE, other=need), counters=[seconds, need],
                     fail=g_cmp(ctx.int_var("od_window"), WINDOW_CLOSED), reussi=g_set(ctx.int_var("od_b6"), 1),
                     kind="Bonus")


def b6_contact(ctx: Ctx) -> Node:
    """B6's contact seconds (one shapes.seconds_while): od_b6_t += 1 every POLL_S while a neck holds a player
    unit (ConditionUnitDansZone on its command zone) and its approach circle a Soviet one (DetectUnitDansDetecteur),
    at either neck: both necks add to one timer, a second counting once. Holds: Or[And[NATO >= 1 in the neck, PACT >= 1
    in its approach]] per B6_PAIRS; broken: And[Or[And[NATO <= 0 in the neck], PACT <= 0 in its approach]] per pair (a
    UnitDansZone sits in an And of its own: stock Or holds none bare)."""
    def in_neck(neck: str, value: int, op: int) -> Node:
        return g_units_in_zones([ctx.tag(neck)], c_team(ctx.camp("NATO")), value, op)

    def in_approach(ring: str, value: int, op: int) -> Node:
        return g_detect(ctx.tag(ring), c_team(ctx.camp("PACT")), value, op)

    holds = lambda: g_or(*(g_and(in_neck(n, 1, GE), in_approach(a, 1, GE)) for n, a in B6_PAIRS))  # noqa: E731
    broken = lambda: g_and(*(g_or(g_and(in_neck(n, 0, LE)), in_approach(a, 0, LE)) for n, a in B6_PAIRS))  # noqa: E731
    return shapes.seconds_while(holds, broken, ctx.int_var("od_b6_t"), reset=False)


def pl_green(ctx: Ctx) -> Node:
    """From H+0:00, design 5.1's PL GREEN: once PL BLUE is released, side by side:
      - B6_HINT_T later, the phase hint od_hph2 (B6 appears, with the stand's hint);
      - B6's contact timer (b6_contact) until the window closes (Competition, in its own Sequential as b1's poll);
      - the window: Competition[B6 done (od_b6 = 1), Sequential[the first contact (od_b6_t >= 1), no player unit in
        either neck's command zone], WaitDuration WINDOW_S, the spring (od_sprung = 1)], then od_window =
        WINDOW_CLOSED, then tier_handover(PACT, both necks): the necks' tiers close and reinforcements arrive only at
        the anvil, whatever closed the window. Its hint, picked when the hand-over runs: od_hgrn (break contact, fall
        back on the anvil) or, once the trap is sprung, od_hgrs (seal the necks again: P5 races a neck back to NATO,
        30 s held from the spring at the earliest, so always after this hand-over);
      - B6 (b6), last.
    The window closes once, so the hand-over runs exactly once: at the spring at the latest, and never after it."""
    window, sprung, seconds = ctx.int_var("od_window"), ctx.int_var("od_sprung"), ctx.int_var("od_b6_t")
    necks = list(NECK_CZ)
    emptied = g_and(g_units_in_zones([ctx.tag(n) for n in necks], c_team(ctx.camp("NATO")), 0, LE))
    close = g_compete([g_until(g_cmp(ctx.int_var("od_b6"), 1)),
                       g_seq([g_until(g_cmp(seconds, 1, GE)), g_until(emptied)]),
                       g_wait(WINDOW_S),
                       g_until(g_cmp(sprung, 1))])
    said = g_if(g_cmp(sprung, 1), g_simul([g_hint(mode_hint(ctx, "od_hgrs"), HINT_S, "shint")]),
                g_simul([g_hint(mode_hint(ctx, "od_hgrn"), HINT_S, "shint")]))
    shut = g_seq([close, g_set(window, WINDOW_CLOSED), tier_handover(ctx, "PACT", necks, said)])
    timer = g_seq([g_compete([b6_contact(ctx), g_until(g_cmp(window, WINDOW_CLOSED))])])
    hint = g_seq([g_wait(B6_HINT_T), g_simul([g_hint("od_hph2", HINT_S, "shint")])])
    return g_seq([g_until(g_cmp(ctx.int_var("od_released"), 1)), g_simul([hint, timer, shut, b6(ctx)])])


# --------------------------------------------------------------------------- phase 3

def jaw_tags(ctx: Ctx) -> list[Node]:
    """The tags of the hidden jaw items (JAWS: the north_jaw and south_jaw rows at RESERVE N and HIDE S), in item
    order."""
    return [ctx.tag(it.name) for it in ctx.items if it.group in JAWS]


def spring_effects(ctx: Ctx) -> Node:
    """Design 5.3 at the spring: the codeword dialog od_dcode (it comes after Corps's od_dauto on an automatic spring:
    the spring beat writes od_sprung after that dialog); SpawnUnits reveals every jaw item, hidden camp 0 units
    (DisableAutoSpawn) at RESERVE N and HIDE S (probe 1's reserves beat, played [[spawn-and-create-units]]); they join
    Groupe_Joueur (Survivors #1330-#1331, as the captured T-80U); then design 6.1's spring cards (AddUnitToDeck in
    SigurdsStrike #1042's shape, Experience omitted). The A-10A card unlocks on od_sprung through load_deck's lock
    race. Every node finishes at once, SpawnUnits in a Sequential (stock never puts one straight in a Simultaneous);
    the jaw hint comes later (seal_hints)."""
    tags = jaw_tags(ctx)
    return g_seq([g_dialog("od_dcode"), g_spawn(tags),
                  g_union(ctx.group("Groupe_Joueur"), tags),
                  *(shapes.add_card(ctx, c.unit, c.count) for c in SPRING_CARDS)])


def seal_hints(ctx: Ctx) -> Node:
    """Phase 3's hints one at a time (od_hgrs may show at the spring's tick): HINT_S after
    spring_effects (so after the codeword dialog, at least HINT_S after the spring), the jaw hint od_hjaw beside a
    HINT_S wait, so the next hint waits its whole 15 s whether or not an LDHint holds its Sequential. Then, once a
    neck is sealed, od_hturn = HTURN_MID if NECK MID is (both at once: NECK MID first), else HTURN_S, and HINT_S later
    HTURN_ANY: each neck's seal hint waits for its turn or HTURN_ANY (seal_hint). One Sequential decides the order, so
    two seals in one tick still show one hint at a time, and a neck sealed long after the other shows at once."""
    turn = ctx.int_var("od_hturn")
    first, second = (ctx.int_var(f"od_sealed_{s.key}") for s in SEALS)
    return g_seq([g_wait(HINT_S), g_simul([g_hint("od_hjaw", HINT_S, "shint"), g_wait(HINT_S)]),
                  g_until(g_or(g_cmp(first, 1), g_cmp(second, 1))),
                  g_if(g_cmp(first, 1), g_simul([g_set(turn, SEALS[0].turn)]), g_simul([g_set(turn, SEALS[1].turn)])),
                  g_wait(HINT_S), g_set(turn, HTURN_ANY)])


def seal_hint(ctx: Ctx, seal: Seal) -> Node:
    """A seal's hint, the hand-over's (tier_handover takes the action): WaitCondition(od_hturn is its turn or
    HTURN_ANY), then its hint (mode_hint: "tiered" says its reinforcements arrive again; "fixed", only that it is
    ours)."""
    turn = ctx.int_var("od_hturn")
    return g_seq([g_until(g_or(g_cmp(turn, seal.turn), g_cmp(turn, HTURN_ANY))),
                  g_simul([g_hint(mode_hint(ctx, seal.hint), HINT_S, "shint")])])


def p5(ctx: Ctx, seal: Seal) -> Node:
    """P5 SHUT THE DOOR for one neck (design 4.1, 5.4), from the spring: Simultaneous[Sequential[the seal race
    (zone_race: NATO >= SEAL_NATO_N and PACT none in the neck's command zone for SEAL_HOLD_S), od_sealed_<key> = 1,
    then tier_handover(NATO, the neck, its seal_hint)], the objective]. The flag comes before the hand-over, whose hint
    may wait its turn. The PL GREEN window's close hands the necks to PACT at the spring at the latest, so the seal,
    30 s held at the earliest, always comes after it. The objective is pinned on the neck and shows the race's held
    seconds (%1 / 30 s; it stays at 30 once held: zone_race); done on od_sealed_<key> = 1; failed if the battle ends
    first (od_end >= END_TOTAL: the backstop, the anvil, the rear exit, the whole force), so an unsealed neck does not
    stay open on the end screen (the design: "none; it stays open until done"). No reassert loop: a Soviet commander
    may win a sealed neck back."""
    held, sealed = ctx.int_var(f"od_p5_{seal.key}_held"), ctx.int_var(f"od_sealed_{seal.key}")
    race = g_seq([zone_race(ctx, [seal.cz], "NATO", "PACT", SEAL_NATO_N, SEAL_HOLD_S, held), g_set(sealed, 1),
                  tier_handover(ctx, "NATO", [seal.cz], seal_hint(ctx, seal))])
    return g_simul([race, objective(seal.text, seal.text + "l", g_cmp(sealed, 1), ctx.tag(seal.cz), [held],
                                    fail=g_cmp(ctx.int_var("od_end"), END_TOTAL, GE))])


def p5_mid(ctx: Ctx) -> Node:
    return p5(ctx, SEALS[0])


def p5_s(ctx: Ctx) -> Node:
    return p5(ctx, SEALS[1])


def phase3(ctx: Ctx) -> Node:
    """From H+0:00: once the trap is sprung (od_sprung = 1), spring_effects, then side by side seal_hints and P5 for
    each neck (the timeline: P5 x2 pinned on the necks)."""
    return g_seq([g_until(g_cmp(ctx.int_var("od_sprung"), 1)), spring_effects(ctx),
                  g_simul([seal_hints(ctx), p5_mid(ctx), p5_s(ctx)])])


# --------------------------------------------------------------------------- phase 4 and the catch

def share_of(ctx: Ctx, into: Node, base: Node) -> list[Node]:
    """`into` = `base` x od_surr_pct / SURR_PCT_BASE, rounded down, from modifications stock uses (no Multiply):
    `into` = 0; then IfThenElse on od_surr_pct's value, one branch per difficulty share, each Sequential(NbExecutions =
    that share)[`into` += `base`] (Add by a variable: 2 stock uses; a counted loop as P1's countdown); Medium's share is
    the last else, the difficulty fallback; then `into` /= SURR_PCT_BASE (Divide by a constant Value: TheHydra #170,
    probe 1's shapes.DIVIDE). The knob is the one source of the share: the branches read its value, and their loop
    counts are KNOBS'."""
    pct = ctx.int_var("od_surr_pct")
    shares = KNOBS["od_surr_pct"]
    easy, medium, hard = shares.easy, shares.medium, shares.hard

    def adds(n: int) -> Node:
        return g_seq([g_modify(into, ADD, other=base)], runs=n)

    return [g_set(into),
            g_if(g_cmp(pct, easy), adds(easy), g_if(g_cmp(pct, hard), adds(hard), adds(medium))),
            g_modify(into, DIVIDE, SURR_PCT_BASE)]


def seal_pocket(ctx: Ctx) -> list[Node]:
    """Both necks sealed (design 5.4): WaitCondition(od_sealed_mid = 1 and od_sealed_s = 1); the Soviet vehicles in the
    pocket (a ring_round of sack_vehicles over SACK_RINGS: the pocket is the sack) into od_sealed_n; od_pocket (P6's
    %1) = od_sealed_n; od_surr_x = od_sealed_n x od_surr_pct / 100 (share_of: a loop of Adds, then the Divide, so an
    integer rounded down), then od_surr_n = od_surr_x, its one write; then od_sealed = 1, last, so whoever reads
    od_sealed finds the rest final."""
    sealed_n, surr_x, left = ctx.int_var("od_sealed_n"), ctx.int_var("od_surr_x"), ctx.int_var("od_pocket")
    return [g_until(g_and(*(g_cmp(ctx.int_var(f"od_sealed_{s.key}"), 1) for s in SEALS))),
            *ring_round(ctx, ctx.group("od_pocketg"), SACK_RINGS, lambda: sack_vehicles(ctx), sealed_n),
            g_set(left, other=sealed_n),
            *share_of(ctx, surr_x, sealed_n),
            g_set(ctx.int_var("od_surr_n"), other=surr_x),
            g_set(ctx.int_var("od_sealed"), 1)]


def surrender(ctx: Ctx) -> Node:
    """Design 5.4's surrender, up to its reads: seal_pocket(), then Competition[the pocket loop (every SACK_POLL_S a
    ring_round of sack_vehicles into od_pocket, P6's %1), Sequential[Competition[WaitCondition(od_surr_n >=
    od_pocket), WaitDuration T_HOLD_S]]] (the surrender's wait ends the loop with it, in the same step: no pocket count
    runs after it), od_surr = 1, then WaitCondition(od_p6 = 1): P6 has frozen its row (catch reads and removes after
    this). The pocket is at its surrender point when od_surr_n >= od_pocket: MoreOrEqual against a variable, the form
    stock uses (45 uses; P4, B1, B6), never LessOrEqual against one (no stock use)."""
    left, surr = ctx.int_var("od_pocket"), ctx.int_var("od_surr")
    loop = g_seq([*ring_round(ctx, ctx.group("od_pocketg"), SACK_RINGS, lambda: sack_vehicles(ctx), left),
                  g_wait(SACK_POLL_S)], runs=FOREVER)
    gives_up = g_seq([g_compete([g_until(g_cmp(ctx.int_var("od_surr_n"), op=GE, other=left)), g_wait(T_HOLD_S)])])
    return g_seq([*seal_pocket(ctx), g_compete([loop, gives_up]), g_set(surr, 1),
                  g_until(g_cmp(ctx.int_var("od_p6"), 1))])


def backstop(ctx: Ctx) -> Node:
    """The backstop: Sequential[WaitDuration BACKSTOP_S, WaitCondition(And[od_sealed = 0, od_end = 0])]: it finishes at
    spring + 25:00 only if the pocket is not sealed by then and no ending is written. Once sealed it never finishes
    (nothing resets od_sealed), so it cannot end the surrender's race, and P6 (which starts on od_sealed) is never left
    open by it. Once an ending is written (a defeat: the anvil, the rear exit, the whole force) it never finishes either
    (od_end is never reset), so neither od_dback nor the CATCH shows over the defeat's dialog."""
    return g_seq([g_wait(BACKSTOP_S), g_until(g_and(g_cmp(ctx.int_var("od_sealed")), g_cmp(ctx.int_var("od_end"))))])


def p6(ctx: Ctx) -> Node:
    """P6 REDUCE THE POCKET (design 4.1), once od_sealed = 1: "%1 ... %2" = od_pocket (the surrender's loop) and
    od_surr_n. Condition Or[od_surr_n >= od_pocket (variable against variable in stock's MoreOrEqual form, as
    surrender's; the row frozen on the round that reaches it), od_surr = 1 (T_hold)]; ActionsReussi od_p6 = 1, which
    the surrender waits for before it removes the pocket; failed if the battle ends first (od_end >= END_TOTAL, as
    P5). Last in its Sequential (gate 3)."""
    left, surr_n = ctx.int_var("od_pocket"), ctx.int_var("od_surr_n")
    return g_seq([g_until(g_cmp(ctx.int_var("od_sealed"), 1)),
                  objective("od_p6", "od_p6l", g_or(g_cmp(surr_n, op=GE, other=left), g_cmp(ctx.int_var("od_surr"), 1)),
                            counters=[left, surr_n], fail=g_cmp(ctx.int_var("od_end"), END_TOTAL, GE),
                            reussi=g_set(ctx.int_var("od_p6"), 1))])


def catch(ctx: Ctx) -> list[Node]:
    """After the surrender or the backstop (design 5.4-5.5). Every count is read before the KillAllUnit:
      - od_alive = od_mb's count (the main body's 60 vehicles still alive: the dead and the removed leave a group);
      - surrendered (od_surr = 1): od_captured = the Soviet vehicles in the pocket (a ring_round of sack_vehicles), at
        most od_alive (a first-echelon vehicle in the pocket must not lift the catch above MB_TOTAL); then every Soviet
        unit in the pocket (a ring_round of Team PACT into od_pocket_all) is removed: KillAllUnit, DeathCause omitted
        (Vanished: all 17 stock Operation uses; proven in probe 2's first play [[vanished-removal]]), last in its
        Sequential;
      - else (the backstop): od_captured = 0 and the dialog od_dback (why the battle ends);
    then od_mb_n = MB_TOTAL (the CATCH row's %2) and od_catch = MB_TOTAL - od_alive + od_captured (destroyed plus
    captured), then the CATCH objective, last. It resolves at its start: Condition od_catch >= CATCH_MAJOR_N, whose
    ActionsReussi sets Total if od_catch >= CATCH_TOTAL_N and both necks are sealed, else Major; ConditionEchec
    od_catch <= CATCH_MAJOR_N - 1, whose ActionsEchec sets Minor. set_end writes only while od_end is 0, and the
    funnel shows the grade's dialog and screen."""
    alive, captured, total, got = (ctx.int_var(n) for n in ("od_alive", "od_captured", "od_mb_n", "od_catch"))
    sealed = ctx.int_var("od_sealed")
    everyone = ctx.group("od_pocket_all")
    surrendered = g_seq([*ring_round(ctx, ctx.group("od_pocketg"), SACK_RINGS, lambda: sack_vehicles(ctx), captured),
                         g_if(g_cmp(alive, op=STRICTLY_LESS, other=captured), g_simul([g_set(captured, other=alive)])),
                         *ring_round(ctx, everyone, SACK_RINGS, lambda: c_team(ctx.camp("PACT"))),
                         g_vanish(everyone)])
    ended = g_seq([g_set(captured), g_dialog("od_dback")])
    grade = objective("od_catch", "od_catchl", g_cmp(got, CATCH_MAJOR_N, GE), counters=[got, total],
                      fail=g_cmp(got, CATCH_MAJOR_N - 1, LE),
                      reussi=g_seq([g_if(g_and(g_cmp(got, CATCH_TOTAL_N, GE), g_cmp(sealed, 1)),
                                         g_seq([shapes.set_end(ctx.int_var("od_end"), END_TOTAL)]),
                                         g_seq([shapes.set_end(ctx.int_var("od_end"), END_MAJOR)]))]),
                      echec=g_seq([shapes.set_end(ctx.int_var("od_end"), END_MINOR)]))
    return [g_count(alive, ctx.group("od_mb")),
            g_if(g_cmp(ctx.int_var("od_surr"), 1), surrendered, ended),
            g_set(total, MB_TOTAL), g_set(got, MB_TOTAL), g_modify(got, SUB, other=alive),
            g_modify(got, ADD, other=captured),
            grade]


def pocket(ctx: Ctx) -> Node:
    """From H+0:00: once the trap is sprung (od_sprung = 1), side by side:
      - Sequential[Competition[surrender (seal, the pocket loop, the surrender's wait), backstop], catch]: the first to
        finish decides, and the catch reads, removes and grades;
      - P6 (p6), from the seal.
    The flags read across beats are the phase flags (od_sprung, od_sealed_mid, od_sealed_s); od_sealed is written
    here, once."""
    return g_seq([g_until(g_cmp(ctx.int_var("od_sprung"), 1)),
                  g_simul([g_seq([g_compete([surrender(ctx), backstop(ctx)]), *catch(ctx)]), p6(ctx)])])


BEATS: list[Beat] = [
    Beat(None, "deck", load_deck),
    Beat(None, "difficulty", difficulty),
    Beat(None, "funnel", end_funnel),
    Beat(None, "p2", p2),
    Beat(0.0, "anvil", anvil),           # H+0:00: the races arm with the launch
    Beat(0.0, "rear", rear_exit),
    Beat(0.0, "p1", p1),                 # phase 1: the phase hint and P1, B1, PL BLUE's fall
    Beat(0.0, "b1", b1),
    Beat(0.0, "pl_blue", pl_blue),
    Beat(CAPTURED_T, "captured", captured),
    Beat(FE_T, "first_echelon", first_echelon),
    Beat(0.0, "main_body", main_body),   # phase 2: each waits for od_released; the spring's H+30 counts
    Beat(0.0, "pl_green", pl_green),     # from H+0:00
    Beat(0.0, "spring", spring),
    Beat(0.0, "phase3", phase3),         # phases 3 and 4: each waits for od_sprung
    Beat(0.0, "pocket", pocket),
]


# --------------------------------------------------------------------------- script and content

def script(tpl: ndfbin.NdfBin, tier_mode: str | None = None) -> tuple[list[Node], list[Node]]:
    """The op's GDScript (layout in the module docstring; modkit.ops.mission.script_frame), from Survivors' GDScript
    template `tpl`: the deployment phase owns OWNED_AT_LOAD with DEPLOY_POINTS, FLAGS are declared even before a beat
    writes them, and the end funnel is exported after the deployment's refresh loop."""
    ctx = Ctx(tier_mode)
    deploy = profile.deploy_phase(tpl, ctx.camp("NATO"), ctx.group("Groupe_Joueur"),
                                  [ctx.tag(name) for name in OWNED_AT_LOAD], DEPLOY_POINTS, hint="od_hdep")
    return ops_mission.script_frame(tpl, profile.TEMPLATES, ctx, deploy, BEATS, camp_rows=profile.CAMP_ROWS,
                                    folder=profile.FOLDER, start_delay_s=profile.START_DELAY_S,
                                    prod_menu_switch=PROD_MENU_SWITCH, flags=FLAGS)


def content(tier_mode: str | None = None) -> Content:
    """The op (its own scenario, mod folder, GUID and menu tokens) in `tier_mode` (TIER_MODE when None); its buy menu
    may switch to the factory tabs (PROD_MENU_SWITCH, which its script's HUD restore writes)."""
    mode = tier_mode or TIER_MODE
    return Content("op", tuple(items(mode)), lambda tpl: script(tpl, mode), load(TABLE), profile.MENU_TOKENS,
                   extra_shapes=EXTRA_SHAPES, scenario=profile.SCENARIO, mod_name=profile.MOD_NAME,
                   menu_renames=profile.MENU_RENAMES, tiered_arrivals=tiered_arrivals(mode),
                   prod_menu_switch=PROD_MENU_SWITCH)
