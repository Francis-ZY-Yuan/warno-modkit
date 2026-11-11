"""Operation Twin Strike, the mission (docs/design.md sections 4, 4.1, 4.2, 5 and 7), on the frame: the op loads with
every unit in place, then its phases run.

The op is its own scenario, challenge_OperationTwinStrike, in its own mod folder, TwinStrike, with its own GUID and
menu tokens (ts_*: twinstrike.profile), so it installs beside Open Door and the probes [[content-identity-unique]].
Build it with `python build.py --content op`. The player is Soviet [[soviet-player-camp]].

  Main: SetDeck x4, HUD hidden, deployment setup (DEPLOY_POINTS and no income; the buy menu on its BATTLEGROUP view;
        the village zone given to NATO, as RedJuggernaut gives the enemy its zones, #73), the start camera (CAMERA, a
        one-key path over the village), LoadingDone, HUD restored, then
        Simultaneous[ the load beats (the deck, the garrison's group and orders, the difficulty, the end funnel),
                      the Groupe_Joueur refresh loop,
                      Sequential[ wait for "Launch battle" (the start hint ts_hdep, naming the village),
                                  Simultaneous[ one Sequential[wait t, beat] per timed beat ] ] ]

What stands from the start (LevelDesign, every item in ITEMS):
- twinstrike.map's items: the village's command zone, the Soviet (north) and NATO (south) deployment zones, the
  player's arrivals at the cut's north edge [[deployment-phase-recipe]] [[arrival-end-in-zone]] and the two FOBs at
  FOB_W and FOB_E, pre-placed in the player's camp (design 6.2);
- the garrison in and around the village, pre-placed and auto-spawned in the NATO camp (Survivors' Camp_3 shape)
  [[spawn-and-create-units]], each force row at its post (GARRISON_POSTS), facing the Soviet box; at load it holds
  the village (HOLD POSITION when idle, Aggressive when fired on, then a Hold smart order) [[garrison-roe-and-hold]];
- battalion 2 at ASSEMBLY, pre-placed hidden in the NATO camp, laid out inside 0.8 R (bn2_items);
- NATO's fighters, pre-placed hidden in the NATO camp in its deployment zone, one set per sweep (air_items);
- the detector circles [[detector-circles-only]]: the village's (VILLAGE_RING), the two fire boxes' (BOX_RINGS) and
  the strike zone's (STRIKE_RING, radius R); Name tags at the places the mission orders units to or fires on (TAGS),
  among them GUN_SPAWN north of the cut, where each fire's battery is created; B2's label (BN2_PIN) and the
  dressing's spots (DRESSING).

The phases, every one with a deadline (design 4.2), each a timed beat from "Launch battle" that waits for its flag:
- phase 1 (phase1, H+0:00): P1 on the village, its count and the fall (the garrison left in the circle at or below
  ts_fall_n and a Soviet command unit inside: the zone forced to the player, FALLEN), the 20 min deadline, and the
  preparation fire's dialog, asked again every 2 min (prep);
- phase 2 (phase2): on FALLEN FALL_GRANT points and FALL_INCOME, the deck's locks lift and the reserve is added;
  PHASE2_S later phase 3 (PH3) [[scripted-economy]];
- the losses (losses, from FALLEN): P2, NATO owning the village for 60 s, no Soviet unit in its command zone for
  3 min (warned at EMPTY_WARN_S, the clock P2's second counter);
- phase 3 (phase3, from PH3): battalion 1's waves on both lanes (BN1_WAVES; ts_teams company teams), each ending
  with an Attack on the player's units [[wave-ends-with-attack]], B1 counting its tanks destroyed as created less
  alive, and battalion 1 beaten (BN1_DONE) when broken or 15 min on, its survivors then breaking off; beside it the
  fire missions (fire_missions), the division fire plan (fire_plan) and NATO's fighter sweeps (air)
  [[scripted-air-sweep]];
- phase 4 (phase4, from BN1_DONE): battalion 2 revealed, B2 and its 5:00 countdown, the release dialog (release);
  on Yes the strike (strike: the warning and the 2S7M's round, the effect at 0:30, then the kill, the dressing,
  STRUCK); on No the countdown runs out and battalion 2 attacks down both lanes (bn2_attack, ATTACK), and a last
  fighter sweep comes with it;
- phase 5 (phase5, from PH5): the end clock (5 min after a strike; after withholding until battalion 2 is broken, up
  to 20 min), then the grade (grade: Total, Minor or Major, released or withheld).
The guns fire through fire(): one fire at a time (BUSY), each battery created at GUN_SPAWN in the NATO2 camp (fogged
for the player), kept off its camp's AI, ordered, then removed FIRE_HOLD_S later (salvo) [[scripted-fires]].
The end funnel (end_funnel) is the one ending node: every ending writes END through shapes.set_end.

The composed pieces are modkit.ops.mission's: the script frame, the lanes and waves, the re-ask loop, the zone
hand-over, the circle counts, the end funnel and the difficulty branches. This module holds Twin Strike's story.
"""
from __future__ import annotations

import dataclasses
from collections import Counter
from typing import Iterable, NamedTuple

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.ops import mission as ops_mission
from modkit.ops import script as ops_script
from modkit.ops import shapes
from modkit.ops.bricks import (
    c_all, c_any, c_none, c_team, c_type, g_and, g_attack, g_camera, g_choice, g_cmp, g_collect, g_compete, g_count,
    g_detect, g_fx, g_grant, g_hint, g_idle_roe, g_if, g_ignored, g_income, g_kill, g_losses, g_modify, g_or,
    g_planes_spent, g_roe, g_seq, g_set, g_simul, g_smart_hold, g_spawn, g_union, g_units_in_zones, g_until, g_vanish,
    g_wait, g_zone_control, g_zone_owner, unit_path,
)
from modkit.ops.forces import group_total, share_count
from modkit.ops.graph import Node
from modkit.ops.leveldesign import LdItem
from modkit.ops.mission import (
    CHOICE_NONE, Lane, Leg, Wave, board, lane_route, placed_units, reask_loop, ring_round, wave, zone_handover,
)
from modkit.ops.profile import Content
from modkit.ops.script import BRICK_DEFAULT
from modkit.ops.shapes import (
    AGGRESSIVE, AIRPLANE_EVACUATE, AIRPLANE_MOVE_AND_ENGAGE, DEATH_CAUSE_SHAPE, FAST_MOVE_AND_ATTACK,
    IDLE_HOLD_POSITION, MOVE_AND_ATTACK, SHOOT_ON_POSITION, TRANSPORTER_SHAPE, Beat, add_card, beat_hint, create,
    lock_card, objective, order, seconds_while, set_end,
)
from modkit.ops.zones import heading
from twinstrike import forces, profile
from twinstrike.map import CAMERA, MAP, POINTS
from twinstrike.map import items as map_items
from twinstrike.strings import BUTTONS, STRINGS

# --------------------------------------------------------------------------- knobs

# The economy (design 4.3) [[scripted-economy]]: the forward detachment deploys on DEPLOY_POINTS with no income
# (START_INCOME 0, written as stock writes it, with no amount: RunningTheGauntlet #275); the village's fall brings
# FALL_GRANT at once (GiveRessourceToTeam in a Simultaneous, BlackHorsesLastStand #312) and FALL_INCOME a tick from
# then on (SetIncomeToTeam, TheWingedHussars #318). No cap: under the rules' scripted-only income nothing else pays.
DEPLOY_POINTS = 2000
START_INCOME = 0
FALL_GRANT = 4000
FALL_INCOME = 250
# The buy menu's Groups/factory-tabs switch at the HUD restore (Content.prod_menu_switch). The start cards belong to
# no battlegroup, so the menu must be able to leave Groups mode, as Open Door's (BRICK_DEFAULT: stock writes Default by
# leaving the property out).
PROD_MENU_SWITCH = BRICK_DEFAULT

# --------------------------------------------------------------------------- the strike (design 5.6)

# Each a one-line change: the look and the death cause are the rulings for now; probe 3b's play may swap either.
# The look: the game's script-only mega bomb, self-contained. The tactical-nuke impact effects crash the game when a
# script launches them [[scripted-nuke-effect]] (the script-effects gate refuses them).
STRIKE_FX = "$/GFX/GameFx/fx_HE_Mega_Bomb_ForScript"
# The kill's DeathCause: Penetration, hoping for wrecks; None is Vanished, the proven fallback [[vanished-removal]].
STRIKE_CAUSE: int | None = shapes.PENETRATION
# The zone's radius R (design 5.6: 800 m to start), converted as the probes convert metres: 1 LBU, about a metre, is
# 215 world units (MapSizeX / LBU; probes.spike2.KM_PX), on Twin Cities' 2,560 world units per minimap px.
WORLD_PER_METRE = 215.0
STRIKE_R_M = 800.0
STRIKE_R_PX = STRIKE_R_M * WORLD_PER_METRE / MAP.map.world_per_px      # 67.2 px, 2,337 GRU
BN2_FIT = 0.8                                                          # battalion 2's layout fits inside 0.8 R
# The dressing (design 5.6, step 4): ground fires and black smoke together at each DRESSING tag in turn, a minute in
# all. The design's burning wrecks, fx_binder_fire_Napalm_Lourd, declare three parameters (parDensityFire,
# parRadiusPhysical, parPosition), so the script-effects gate refuses them [[script-effects-self-contained]]:
# feu_fx_script, the game's script fire (a ground fire and a burned-ground mark, its parameters bound inside it),
# replaces them. The black smoke is itself the burning-wreck effect at random spots round its tag (FX_script.ndf).
DRESSING_FX = ("$/GFX/GameFx/feu_fx_script", "$/GFX/GameFx/fx_FumeeNoire_ForScript_RandomPosition")
DRESSING_PX = ((-20.0, -8.0), (0.0, -12.0), (20.0, -8.0), (-20.0, 8.0), (0.0, 10.0), (20.0, 8.0))  # from ASSEMBLY
DRESSING = tuple(f"TS_Fx{k + 1}" for k in range(len(DRESSING_PX)))
DRESSING_STEP_S = 10.0
EXTRA_SHAPES = (TRANSPORTER_SHAPE,                                   # the infantry cards carry their carriers
                *((DEATH_CAUSE_SHAPE,) if STRIKE_CAUSE is not None else ()))   # the strike's KillAllUnit DeathCause

# --------------------------------------------------------------------------- the names the mission uses

SIDES = profile.CAMPS                  # side -> camp export name (modkit.ops.profile.SOVIET_PLAYER_SIDES)
PLAYER = profile.PLAYER                # "Soviet": joueur, the player
ENEMY = "NATO"                         # ordinateur_SOV: the garrison, both battalions and the fighters
GUN_CAMP = "NATO2"                     # ordinateur_DDR, the unused Alliance 1 camp: each fire's battery, fogged
# Flags several beats read, declared at 0 (script_frame's flags), each written once (but BUSY, a lock).
FALLEN = "ts_fallen"                   # 1: the village has fallen (phase 1's end); the deck's locks lift
END = "ts_end"                         # the ending (ENDINGS), written only through shapes.set_end: the first stands
PH3 = "ts_ph3"                         # 1: phase 3, the counter-attack, has started (PHASE2_S after the fall)
BN1_DONE = "ts_bn1_done"               # 1: battalion 1 is beaten, broken or at its deadline
BN1_OFF = "ts_bn1_off"                 # 1: battalion 1 breaks off (its deadline): its routes stop
B1_DONE = "ts_b1_done"                 # 1: B1 is done, battalion 1 broken by its kills (the grade's Total)
BUSY = "ts_busy"                       # 1: a fire holds the guns (fire(): one at a time), or the strike does
STRIKE = "ts_strike"                   # the release dialog's answer: RELEASED or WITHHELD (0 before it)
STRUCK = "ts_struck"                   # 1: the strike's kill is done (B2 done, phase 5)
ATTACK = "ts_attack"                   # 1: battalion 2's countdown ran out (withheld): it attacks
BN2_BROKEN = "ts_bn2_broken"           # 1: battalion 2 is broken (B2's "tanks left" done)
PH5 = "ts_ph5"                         # 1: phase 5, the end clock, has started (after the strike, or at the attack)
FLAGS = (FALLEN, END, PH3, BN1_DONE, BN1_OFF, B1_DONE, BUSY, STRIKE, STRUCK, ATTACK, BN2_BROKEN, PH5)
# Script groups (TGDVariableUnitGroup).
GROUPE_JOUEUR = "Groupe_Joueur"        # every unit of the player's, refreshed every profile.REFRESH_S
GARRISON = "ts_garrison"               # the garrison's spawns
# Each fire's battery, created into its own group at GUN_SPAWN and removed after its fire (salvo): one fire at a time
# (BUSY), so a group is empty again before its next fire.
HEAVY = "ts_heavy"                     # the 2S7M battery
ROCKETS = "ts_rockets"                 # the BM-27 battery
GUNS = "ts_guns"                       # both batteries, the division fire plan's
BN1 = "ts_bn1_w"                       # battalion 1's waves: ts_bn1_w<key> each; ts_bn1_w, _inf: all vehicles, riflemen
TANKS = "tanks"                        # mission.wave's track: ts_bn1_w<key>_tanks, and all of them in BN1_TANKS_G
BN1_TANKS_G = f"{BN1}_{TANKS}"         # battalion 1's tanks (forces.BN1_TANKS), alive: B1's count
BN2 = "ts_bn2"                         # battalion 2: ts_bn2_w and ts_bn2_c its halves (each with _inf and _ifv)
BN2_TANKS_G = "ts_bn2_tanks"           # battalion 2's tanks (forces.BN2_TANKS): B2's "tanks left"
STRIKER = "ts_striker"                 # the one 2S7M that fires the strike's round
# The LevelDesign items the mission names.
VILLAGE_ZONE = "TS_CZ_Village"         # the village's command zone (twinstrike.map)
VILLAGE_RING = "TS_RingVillage"        # the detector circle over the village: the fall's count, a sweep's target
BOX_RINGS = {"W": "TS_RingBoxW", "C": "TS_RingBoxC"}   # the fire boxes' circles: the plan's count, the sweeps' targets
STRIKE_RING = "TS_RingStrike"          # the strike zone's circle, radius R round ASSEMBLY: the kill's detector
BN2_PIN = "TS_Bn2"                     # B2's label, at battalion 2's north edge (the zone's label is at its centre)
# Name tags at the design's places (twinstrike.map.POINTS): the objective, the assembly area (battalion 2's creation
# and the strike zone), the two fire boxes, the lanes' entries and turn (design 3, 5.3), and where each fire's battery
# is created (GUN_SPAWN, the fire-range gate's tag). The fires aim at the Name tags of the village, the boxes and the
# assembly area, as Survivors #1231/#1232 order ShootOnPosition onto Tags.
GUN_SPAWN = profile.GUN_SPAWN_TAG
TAGS = {"TS_Village": "VILLAGE", "TS_Assembly": "ASSEMBLY", "TS_BoxW": "BOX_W", "TS_BoxC": "BOX_C",
        "TS_EntryW": "NATO_ENTRY_W", "TS_EntryC": "NATO_ENTRY_C", "TS_TurnC": "TURN_C", GUN_SPAWN: "GUN_SPAWN"}
BOX_TAGS = {"W": "TS_BoxW", "C": "TS_BoxC"}   # the fire boxes' Name tags: the fires' targets

# --------------------------------------------------------------------------- the mission's knobs

HINT_S, POLL_S, FOREVER = shapes.HINT_S, shapes.POLL_S, shapes.FOREVER
GE, LE, ADD, SUB = shapes.GE, shapes.LE, shapes.ADD, shapes.SUB
EASY, MEDIUM, HARD = shapes.EASY, shapes.MEDIUM, shapes.HARD
# The endings (END's values; design 4.2, 5.8). A win names its grade and the strike, released (_R) or withheld (_W);
# the losses follow. The funnel (end_funnel) shows the value's dialog, then ends the battle. No stock screen exists for
# a Minor victory [[mission-ends-only-by-script]]: it shows Major's, with its own dialog (as Open Door's). A loss names
# the enemy's alliance (the Soviet alliance's Gotterdammerung #254, VictoryType 6).
END_TOTAL_R, END_TOTAL_W, END_MAJOR_R, END_MAJOR_W, END_MINOR_R, END_MINOR_W = 1, 2, 3, 4, 5, 6
END_FAIL, END_LOST, END_EMPTY = 7, 8, 9
WON = END_MINOR_W                      # END 1..WON is a win
ENDINGS: dict[int, ops_mission.Ending] = {
    END_TOTAL_R: ("ts_dtotr", shapes.TOTAL_VICTORY, False),
    END_TOTAL_W: ("ts_dtotw", shapes.TOTAL_VICTORY, False),
    END_MAJOR_R: ("ts_dmajr", shapes.MAJOR_VICTORY, False),
    END_MAJOR_W: ("ts_dmajw", shapes.MAJOR_VICTORY, False),
    END_MINOR_R: ("ts_dminr", shapes.MAJOR_VICTORY, False),
    END_MINOR_W: ("ts_dminw", shapes.MAJOR_VICTORY, False),
    END_FAIL: ("ts_dfail", shapes.TOTAL_VICTORY, True),     # phase 1's deadline
    END_LOST: ("ts_dlost", shapes.TOTAL_VICTORY, True),     # NATO owned the village for NATO_HOLD_S
    END_EMPTY: ("ts_dempty", shapes.TOTAL_VICTORY, True),   # no Soviet unit in the village's zone for EMPTY_S
}

# Phase 1 (seconds after "Launch battle"). The village falls once the NATO units left in its circle are ts_fall_n or
# fewer (a difficulty knob) and a Soviet command unit (forces.COMMAND_UNITS) is inside; the circle is counted every
# RING_POLL_S into P1's counter. If it has not fallen P1_DEADLINE_S after the launch, the battle is lost (design 4.2).
RING_POLL_S = 2.0
P1_DEADLINE_S = 1200.0
GARRISON_N = group_total(forces.force_rows("garrison"), "garrison")   # P1's count before its first round
# The preparation fire (design 5.4): its warning hint at PREP_HINT_T, after the phase hint and the difficulty's; the
# dialog at PREP_ASK_T, asked again PREP_GAP_S after each HOLD FIRE (game time: the dialog pauses the game) until FIRE
# AT WILL or the fall [[dialog-reask-loop]]. Each dialog's buttons are strings.BUTTONS' (button 0 is the "now" answer).
DIFF_HINT_T = 15.0
PREP_HINT_T, PREP_ASK_T, PREP_GAP_S = 30.0, 40.0, 120.0
NOW = 0                                # button 0: FIRE AT WILL (prep, plan), ROCKET (which guns), ALPHA = BOX W (where)
# Phase 2 (design 5.2): the reserve's cards RESERVE_DELAY_S after the fall (the locks lift on FALLEN first), and phase 3
# PHASE2_S after the fall.
RESERVE_DELAY_S = 1.0
PHASE2_S = 120.0
# Phase 3 (seconds after PH3, design 5.3). Battalion 1 is beaten when broken (B1's kills reach ts_b1_need) or
# BN1_DEADLINE_S on; at the deadline its survivors break off by road to their lane's entry, in the south zone, and are
# removed (Vanished [[vanished-removal]]) BREAK_OFF_S later. Riflemen board their Bradleys first, raced against BOARD_S
# (Open Door's). Each lane leg is raced against its timeout: LEG_S for each leg but the last, every one under 100 px
# of road, which probe 2's pace (240 s for 362 px, Open Door's LEG_PACE_S_PER_PX) drives in under 60 s; FINAL_LEG_S
# for the last, into the village, after which the wave attacks the player's units (wave_end) [[wave-ends-with-attack]].
BN1_DEADLINE_S = 900.0
BREAK_OFF_S = 120.0
BOARD_S = 30.0
LEG_S = 60.0
FINAL_LEG_S = 120.0
# The guns (design 5.4) [[scripted-fires]]. Each fire (salvo) creates its battery at GUN_SPAWN, keeps it off its camp's
# AI, orders ShootOnPosition FIRE_LEAD_S later (probe 1's battery fired 20 s after its create), and removes it
# (Vanished) FIRE_HOLD_S after the order: one ShootOnPosition fires one salvo (the 2S7M's and the BM-27's ammunition:
# NbSalvosShootOnPosition 1), after its deployment (5 s, 10 s), its aiming time (30 s, 25 s), its shots (3 shells 5 s
# apart, 16 rockets 1.5 s apart) and their flight (about 11 s from GUN_SPAWN). A created battery comes with full
# ammunition, and stock never empties artillery, so no SetAmmo.
FIRE_LEAD_S = 20.0
FIRE_HOLD_S = 90.0
# The fire missions (design 5.4): from FIRE_T0 after PH3 (the west recon screen is on BOX W by then), two dialogs in
# turn (which guns, then where), the fire, then the cooldown ts_cool_s (a difficulty knob). The division fire plan's
# dialog from PLAN_T0 after PH3 (the first company team is on BOX W by then), asked again every PLAN_GAP_S until fired:
# its asks fall 15 s or more from the missions' at every difficulty (the tests check it: a mission comes round every
# FIRE_LEAD_S + FIRE_HOLD_S + the cooldown), so two dialogs never open together.
FIRE_T0 = 90.0
PLAN_T0, PLAN_GAP_S = 195.0, 140.0
# The losses (design 4.2), from the fall: NATO owns the village for NATO_HOLD_S, or no Soviet unit is in its command
# zone for EMPTY_S, the zone's own outline, which the game's "contested" reads too (not its 40 px circle); the empty
# streak's warning shows once it has lasted EMPTY_WARN_S, naming the time left (EMPTY_S - EMPTY_WARN_S).
NATO_HOLD_S, EMPTY_S, EMPTY_WARN_S = 60, 180, 20
# Phase 4 (seconds after BN1_DONE, design 5.5). Battalion 2 appears BN2_GAP_S after battalion 1 is beaten (after its
# hint), its countdown COUNTDOWN_S; the release dialog RELEASE_ASK_S after it appears (after the hint), once no fire
# holds the guns and no other dialog is open, or RELEASE_MAX_WAIT_S on at most, so a flag left set never hides it: one
# whole fire and 10 s, which leaves 170 s of the countdown. It is broken with BN2_BROKEN_N of its tanks left
# (forces.SHARES: 30 %).
BN2_GAP_S = 20.0
COUNTDOWN_S = 300
RELEASE_ASK_S = 10.0
RELEASE_MAX_WAIT_S = FIRE_LEAD_S + FIRE_HOLD_S + 10.0
RELEASED, WITHHELD = 1, 2              # STRIKE's values: the dialog's Yes (button 0), No (button 1)
BN2_BROKEN_N = forces.threshold("bn2")
# The strike's timeline (seconds after the release, design 5.6): the round at STRIKE_ROUND_T, the effect at STRIKE_T,
# the kill STRIKE_KILL_S after it (probe 3's pause, so the effect is seen alone). The round is a fire of its own
# (salvo): one 2S7M created at GUN_SPAWN with the warning, ordered FIRE_LEAD_S later, its three shells leaving after
# the gun's 30 s aiming time, so they land on the zone after the effect.
STRIKE_ROUND_T, STRIKE_T, STRIKE_KILL_S = 0.0, 30.0, 3.0
# Phase 5 (design 5.8): the end clock, from PH5, after a strike, and its cap after withholding (or until battalion 2 is
# broken).
END_CLOCK_S, END_CLOCK_WITHHELD_S = 300.0, 1200.0

# Difficulty (design 5.7) [[difficulty-branches]]: (Easy, Medium, Hard). The garrison left at which the village falls
# (FALL_SHARES of the garrison: 35/25/15 %), battalion 1's company teams (TEAMS) and the fire-mission cooldown
# (COOLDOWN_S). B1's tanks and the kills that break battalion 1 (its tanks less 30 % of them left, forces.SHARES) follow
# the teams (bn1_tanks).
FALL_SHARES = (0.35, 0.25, 0.15)
TEAMS = (2, 3, 4)
COOLDOWN_S = (120, 180, 240)
check(len(set(COOLDOWN_S)) == 3, "cooldown() branches on ts_cool_s's value: the three cooldowns must differ")
SWEEP3 = (0, 0, 1)                     # the third fighter sweep flies on Hard only (SWEEPS)

# --------------------------------------------------------------------------- battalion 1's waves (design 5.3, 6.3)


class Team(NamedTuple):
    """A wave of battalion 1 (modkit.ops.mission.Wave: key, offset after PH3, lane, rows) and its company team's
    number: 0 for the recon screen (always sent), k for the k-th company team, sent while ts_teams >= k."""
    wave: Wave
    team: int


# The lanes (modkit.ops.mission.Lane), by FastMoveAndAttack [[fast-move-and-attack-keeps-roads]] but the last leg,
# MoveAndAttack into the village (design 5.3), timed as the others, after which the wave attacks the player's units
# (wave_end): LANE_W up the main road through BOX W, LANE_C up the east road through BOX C, then west across the
# stream at TURN C (twinstrike.map.PATHS).
LANES: dict[str, Lane] = {
    "W": Lane("TS_EntryW", (Leg("TS_BoxW", LEG_S), Leg("TS_Village", FINAL_LEG_S, MOVE_AND_ATTACK))),
    "C": Lane("TS_EntryC", (Leg("TS_BoxC", LEG_S), Leg("TS_TurnC", LEG_S),
                            Leg("TS_Village", FINAL_LEG_S, MOVE_AND_ATTACK))),
}
# The waves: on each lane the recon screen first, then a company team (its tanks, a Bradley platoon with its riflemen,
# and its share of the air defence) about WAVE_GAP_S apart; the centre lane runs LANE_STAGGER_S behind the west one,
# so no two waves are created together. Teams A, B and C split the table's battalion 1 at FORCE_SCALE (checked
# below); Hard's fourth team, D, is a second company like A.
WAVE_GAP_S, LANE_STAGGER_S = 120.0, 60.0
_TEAM_A = (("M1A1HA_Abrams_US", 10, None), ("M2A2_Bradley_IFV_US", 3, None),
           ("Rifles_half_AT4_US", 3, "M2A2_Bradley_IFV_US"), ("M163_PIVADS_US", 1, None), ("M998_Avenger_US", 1, None),
           ("MANPAD_Stinger_C_US", 1, None))
BN1_WAVES: tuple[Team, ...] = (
    Team(Wave(1, 0.0, "W", (("M3A2_Bradley_CFV_US", 2, None), ("Scout_US", 2, None),
                            ("OH58D_Kiowa_Warrior_US", 1, None))), 0),
    Team(Wave(2, LANE_STAGGER_S, "C", (("M3A2_Bradley_CFV_US", 1, None), ("Scout_US", 1, None),
                                       ("OH58D_Kiowa_Warrior_US", 1, None))), 0),
    Team(Wave(3, WAVE_GAP_S, "W", _TEAM_A), 1),
    Team(Wave(4, WAVE_GAP_S + LANE_STAGGER_S, "C", (
        ("M1A1HA_Abrams_US", 10, None), ("M1A1HA_Abrams_CMD_US", 1, None), ("M2A2_Bradley_IFV_US", 3, None),
        ("Rifles_half_AT4_US", 3, "M2A2_Bradley_IFV_US"), ("M163_PIVADS_US", 1, None),
        ("M48_Chaparral_MIM72F_US", 1, None), ("MANPAD_Stinger_C_US", 1, None))), 2),
    Team(Wave(5, 2 * WAVE_GAP_S, "W", (
        ("M1A1HA_Abrams_US", 10, None), ("M2A2_Bradley_IFV_US", 4, None),
        ("Rifles_half_AT4_US", 3, "M2A2_Bradley_IFV_US"), ("M48_Chaparral_MIM72F_US", 1, None),
        ("M998_Avenger_US", 1, None), ("MANPAD_Stinger_C_US", 1, None))), 3),
    Team(Wave(6, 2 * WAVE_GAP_S + LANE_STAGGER_S, "C", _TEAM_A), 4),
)


def tally(rows: Iterable[tuple[str, int, str | None]]) -> Counter:
    """(descriptor, transport) -> count over (descriptor, count, transport) rows."""
    out: Counter = Counter()
    for unit, n, transport in rows:
        out[unit, transport] += n
    return out


def bn1_tallies(teams: int = TEAMS[MEDIUM]) -> tuple[Counter, Counter]:
    """(the tally of the waves sent with `teams` company teams, the tally of battalion 1's table rows at FORCE_SCALE:
    bn1, bn1_recon, bn1_ad): equal at Medium while the split holds."""
    rows = [r for g in ("bn1", "bn1_recon", "bn1_ad") for r in forces.force_rows(g)]
    return (tally(row for t in BN1_WAVES if t.team <= teams for row in t.wave.rows),
            tally((r.descriptor, r.count, r.transport) for r in rows))


# A FORCE_SCALE or table change must re-split the waves (design 6.4: a table edit plus one replay).
check(bn1_tallies()[0] == bn1_tallies()[1],
      "BN1_WAVES no longer split battalion 1's rows at FORCE_SCALE: re-split them")


# Battalion 2 (design 5.5, 6.3): two halves, one per lane, laid out at ASSEMBLY (BN2_POSTS) by the formation helper,
# BN2_SPACING_PX apart, BN2_COLS to a row, all inside BN2_FIT of the strike zone's radius (the tests check it), facing
# the village; pre-placed hidden in the NATO camp until battalion 1 is beaten. They split the table's battalion 2 at
# FORCE_SCALE (checked below). The Panzergrenadiere stand beside their Marders: no spawn starts infantry aboard
# (spawn-and-create-units); they board when the battalion attacks.
BN2_HALVES: dict[str, tuple[tuple[str, int, str | None], ...]] = {
    "W": (("Leopard_2A4_RFA", 14, None), ("Leopard_2A3_CMD_RFA", 1, None), ("Marder_1A3_RFA", 4, None),
          ("Panzergrenadier_IFV_RFA", 4, "Marder_1A3_RFA"), ("Gepard_1A2_RFA", 2, None),
          ("Marder_Roland_2_RFA", 1, None), ("Luchs_A1_RFA", 1, None)),
    "C": (("Leopard_2A4_RFA", 14, None), ("Marder_1A3_RFA", 4, None), ("Panzergrenadier_IFV_RFA", 4, "Marder_1A3_RFA"),
          ("Gepard_1A2_RFA", 1, None), ("Marder_Roland_2_RFA", 1, None), ("Luchs_A1_RFA", 1, None)),
}
BN2_POSTS = {"W": (145.0, 500.0), "C": (167.0, 500.0)}
BN2_SPACING_PX, BN2_COLS = 5.0, 5
BN2_FACING = heading(MAP.map.px_to_world(POINTS["ASSEMBLY"]), MAP.map.px_to_world(POINTS["VILLAGE"]))
BN2_PIN_PX = (156.0, 485.0)            # 15 px north of ASSEMBLY, at the formation's north edge
# Battalion 2's lanes when it attacks (design 5.5: "down both lanes as in 5.3"), from ASSEMBLY: the west half to BOX W
# (96 px of road at probe 2's pace: 64 s, so BN2_LEG_W_S), then into the village; the centre half up battalion 1's
# centre lane from BOX C. As battalion 1's waves, each half ends with an Attack on the player's units (wave_end).
BN2_LEG_W_S = 70.0
BN2_LANES: dict[str, tuple[Leg, ...]] = {
    "W": (Leg("TS_BoxW", BN2_LEG_W_S), Leg("TS_Village", FINAL_LEG_S, MOVE_AND_ATTACK)),
    "C": LANES["C"].legs,
}
check(tally(row for rows in BN2_HALVES.values() for row in rows)
      == tally((r.descriptor, r.count, r.transport) for r in forces.force_rows("bn2")),
      "BN2_HALVES no longer split battalion 2's rows at FORCE_SCALE: re-split them")


def bn1_tanks(teams: int) -> int:
    """Battalion 1's tanks (forces.BN1_TANKS) with `teams` company teams sent: B1's %2."""
    return sum(n for t in BN1_WAVES if t.team <= teams for unit, n, _ in t.wave.rows if unit in forces.BN1_TANKS)


# The difficulty knobs, (Easy, Medium, Hard): each a script variable that mission.difficulty sets at load.
KNOBS: dict[str, tuple[int, int, int]] = {
    "ts_fall_n": tuple(forces.threshold("fall", share=s) for s in FALL_SHARES),
    "ts_teams": TEAMS,
    "ts_cool_s": COOLDOWN_S,
    "ts_b1_tanks": tuple(bn1_tanks(k) for k in TEAMS),
    "ts_b1_need": tuple(bn1_tanks(k) - share_count(forces.SHARES["bn1"], bn1_tanks(k)) for k in TEAMS),
    "ts_sweep3": SWEEP3,
}


# --------------------------------------------------------------------------- NATO's fighter sweeps (design 6.3)

class Sweep(NamedTuple):
    """A fighter sweep [[scripted-air-sweep]]: `count` `unit` fighters, pre-placed hidden in the NATO camp at `post`
    (minimap px), revealed `after` seconds after its trigger (PH3, or battalion 2's attack) and sent over the circle
    `target`, only while the difficulty knob `knob` is 1 if it names one; its group is ts_air_<key>, its item group
    air_<key>."""
    key: str
    unit: str
    count: int
    target: str
    after: float
    post: tuple[float, float]
    knob: str | None = None


# The sweeps (design 6.3), each its own group, none holding up a phase: the first two over the boxes as battalion 1's
# company teams reach them (team A on BOX W from about PH3 + 3:00), the third over the village on Hard only
# (ts_sweep3), and West German Phantoms over the village once battalion 2 attacks (the strike withheld). The fighters
# wait hidden in the NATO deployment zone, south of the cut's fields.
SWEEPS_AFTER_PH3: tuple[Sweep, ...] = (
    Sweep("s1", "F15C_Eagle_AA_US", 2, BOX_RINGS["W"], 150.0, (30.0, 512.0)),
    Sweep("s2", "F15C_Eagle_AA_US", 2, BOX_RINGS["C"], 360.0, (100.0, 512.0)),
    Sweep("s3", "F15C_Eagle_AA_US", 1, VILLAGE_RING, 600.0, (65.0, 512.0), knob="ts_sweep3"),
)
SWEEP_AT_ATTACK = Sweep("s4", "F4F_Phantom_II_AA_RFA", 2, VILLAGE_RING, 0.0, (195.0, 512.0))
SWEEPS = (*SWEEPS_AFTER_PH3, SWEEP_AT_ATTACK)
AIR_SPACING_PX = 6.0
AIR_EXPERIENCE = 2                     # Survivors' strike aircraft's ExperienceLevel (END_AirAA_Harrier_01/02)

# --------------------------------------------------------------------------- geometry (one place: ITEMS)

# The village's detector circle: 40 px (1,391 GRU) round VILLAGE, inside the village's command zone's north-south
# extent (y 331.6-421.6 px) and short of the fire boxes and the centre lane's turn (87 px and more away).
VILLAGE_RING_PX = 40.0
# The fire boxes' circles, round BOX_W and BOX_C on their roads: 20 px (238 m), short of the village's circle (BOX W's
# reaches y 450, the village's y 417).
BOX_RING_PX = 20.0
# The garrison's posts (design 5.1, "in and around the village"), minimap px, read off the Minimap's built-up area
# (x 20-115, y 350-420 round the crossroads at VILLAGE): each force row stands abreast at its post, `spacing` px
# apart, facing the Soviet box. Recon forward on the north road, the Milan teams and the Leopards along the north
# edge, the infantry in the middle street, the Marders and the Gepard behind them.
GARRISON_POSTS: dict[str, tuple[tuple[float, float], float]] = {
    "Fernspaher_RFA": ((70.0, 346.0), 6.0),
    "ATteam_Milan_2_RFA": ((70.0, 358.0), 30.0),
    "Leopard_1A5_RFA": ((69.0, 364.0), 32.0),
    "Panzergrenadier_IFV_RFA": ((70.0, 378.0), 12.0),
    "Marder_1A3_RFA": ((70.0, 392.0), 16.0),
    "Gepard_1A2_RFA": ((70.0, 402.0), 6.0),
}
GARRISON_FACING = heading(MAP.map.px_to_world(POINTS["VILLAGE"]), MAP.map.px_to_world(POINTS["SOV_ENTRY"]))
# The division artillery is not pre-placed: each fire creates its battery at GUN_SPAWN (salvo). The fighters face the
# village from the south.
AIR_FACING = heading(MAP.map.px_to_world(POINTS["ASSEMBLY"]), MAP.map.px_to_world(POINTS["VILLAGE"]))


def garrison_items() -> list[LdItem]:
    """The garrison, pre-placed and auto-spawned in the NATO camp: each row of forces' "garrison" group at its post
    (GARRISON_POSTS), named TS_Garrison_01, ... in table order."""
    out: list[LdItem] = []
    for row in forces.force_rows("garrison"):
        at, spacing = GARRISON_POSTS[row.descriptor]
        names = [(f"TS_Garrison_{len(out) + k + 1:02d}", row.descriptor) for k in range(row.count)]
        out += placed_units(MAP, at, names, spacing, row.count, "garrison", camp=profile.camp_index(ENEMY),
                            rotation=GARRISON_FACING)
    return out


def air_items() -> list[LdItem]:
    """NATO's fighters, pre-placed hidden (DisableAutoSpawn) in the NATO camp until a sweep reveals them, as Survivors
    places its strike aircraft (END_AirAA_Harrier_01/02: hidden, ExperienceLevel 2): each sweep's a row at its post,
    its item group air_<key>, named TS_Air_01, ... in SWEEPS order."""
    out: list[LdItem] = []
    for s in SWEEPS:
        names = [(f"TS_Air_{len(out) + k + 1:02d}", s.unit) for k in range(s.count)]
        out += placed_units(MAP, s.post, names, AIR_SPACING_PX, s.count, f"air_{s.key}", camp=profile.camp_index(ENEMY),
                            hidden=True, rotation=AIR_FACING, experience=AIR_EXPERIENCE)
    return out


def bn2_items() -> list[LdItem]:
    """Battalion 2, pre-placed hidden (DisableAutoSpawn) in the NATO camp until SpawnUnits reveals it: each half of
    BN2_HALVES a formation at its post (BN2_POSTS), its item group bn2_w or bn2_c, named TS_Bn2_01, ... in row
    order (modkit.ops.mission.placed_units)."""
    out: list[LdItem] = []
    for half, rows in BN2_HALVES.items():
        units = [unit for unit, n, _ in rows for _ in range(n)]
        names = [(f"TS_Bn2_{len(out) + k + 1:02d}", unit) for k, unit in enumerate(units)]
        out += placed_units(MAP, BN2_POSTS[half], names, BN2_SPACING_PX, BN2_COLS, f"bn2_{half.lower()}",
                            camp=profile.camp_index(ENEMY), hidden=True, rotation=BN2_FACING)
    return out


def items() -> list[LdItem]:
    """Every LevelDesign item of the op."""
    ax, ay = POINTS["ASSEMBLY"]
    return [
        *map_items(),                                  # the village's zone, the deployment zones, arrivals, FOBs
        *garrison_items(),
        MAP.ring_item(VILLAGE_RING, "VILLAGE", VILLAGE_RING_PX),
        *(MAP.item("Tags", name, point, "Name") for name, point in TAGS.items()),
        *(MAP.ring_item(ring, f"BOX_{lane}", BOX_RING_PX) for lane, ring in BOX_RINGS.items()),
        MAP.ring_item(STRIKE_RING, "ASSEMBLY", STRIKE_R_PX),
        MAP.item("Tags", BN2_PIN, BN2_PIN_PX, "Name"),
        *(MAP.item("Tags", name, (ax + dx, ay + dy), "Name") for name, (dx, dy) in zip(DRESSING, DRESSING_PX)),
        *bn2_items(),
        *air_items(),
    ]


ITEMS: list[LdItem] = items()


class Ctx(profile.Ctx):
    """twinstrike.profile.Ctx over the op's items, its tags keyed to the op's scenario."""

    def __init__(self) -> None:
        super().__init__(ITEMS, profile.SCENARIO)

    def spawn_tags(self, group: str) -> list[Node]:
        """The GdItems tags of the Spawn items of item group `group`, in ITEMS order."""
        return [self.tag(it.name) for it in ITEMS if it.addon == "Spawn" and it.group == group]


# --------------------------------------------------------------------------- the load beats

def load_deck(ctx: Ctx) -> Node:
    """Load: AddUnitToDeck for each start card (forces.START_ADDS; the motor rifles in their BMP-2s) and then for the
    Soviet player's supply (forces.SUPPLY), then, beside each other, a LockDeckUnit by type for each of
    forces.START_LOCKS until FALLEN = 1 (shapes.lock_card: a race that never finishes before the unlock, so the locks
    go last, in one Simultaneous)."""
    cards = [add_card(ctx, unit, n, transport=carrier) for unit, n, carrier in (*forces.START_ADDS, *forces.SUPPLY)]
    fallen = ctx.int_var(FALLEN)
    return g_seq([*cards, g_simul([lock_card(ctx, unit, g_cmp(fallen, 1)) for unit in forces.START_LOCKS])])


def load_groups(ctx: Ctx) -> Node:
    """Load: the garrison's script group from its spawns' tags (Survivors S#128's AddUnitGroupListToUnitGroup), then
    its orders as stock gives a garrison in a camp with no AI [[garrison-roe-and-hold]]: HOLD POSITION when idle and
    Aggressive when fired on (Survivors #188/#189's place, last after the union; the values RunningTheGauntlet
    #104/#105 and Sledgehammer #316/#319 give), then a Hold smart order at the village, last in its container
    (RedJuggernaut #249, its village defenders)."""
    garrison = ctx.group(GARRISON)
    return g_seq([g_union(garrison, ctx.spawn_tags("garrison")), g_idle_roe(garrison, IDLE_HOLD_POSITION),
                  g_roe(garrison, AGGRESSIVE), g_smart_hold(garrison, ctx.tag("TS_Village"))])


def difficulty(ctx: Ctx) -> Node:
    """Load: modkit.ops.mission.difficulty over ts_diff and KNOBS: every knob at its Medium value, then the Easy and
    Hard branches overwrite them [[difficulty-branches]]; the case's hint (ts_hdif0/1/2, ts_hdif9 for "not received")
    shows DIFF_HINT_T after "Launch battle", after phase 1's hint."""
    return ops_mission.difficulty(ctx, ctx.int_var("ts_diff"), KNOBS, "ts_hdif", DIFF_HINT_T)


def end_funnel(ctx: Ctx) -> Node:
    """Load: the one ending node (profile.END_FUNNEL; modkit.ops.mission.end_funnel): once END >= 1, the dialog and
    the TriggerEndGame of END's ENDINGS row. Only the first TriggerEndGame of a battle counts
    [[mission-ends-only-by-script]], and END is written only through shapes.set_end, so the first ending stands."""
    return ops_mission.end_funnel(ctx.int_var(END), ENDINGS, profile.END_FUNNEL)


# --------------------------------------------------------------------------- the guns (design 5.4)

# Each fire's battery, by its group: the force groups whose rows it creates (forces.ROWS: 2S7M x6, BM-27 x6, or both
# for the division fire plan), and the strike's round, one 2S7M.
BATTERIES: dict[str, tuple[tuple[str, int], ...]] = {
    HEAVY: tuple((r.descriptor, r.count) for r in forces.force_rows("guns_heavy")),
    ROCKETS: tuple((r.descriptor, r.count) for r in forces.force_rows("guns_rockets")),
    GUNS: tuple((r.descriptor, r.count) for g in ("guns_heavy", "guns_rockets") for r in forces.force_rows(g)),
    STRIKER: (("2S7M_Malka_SOV", 1),),
}


def salvo(ctx: Ctx, battery: str, target: str) -> list[Node]:
    """One fire of `battery` (a BATTERIES key) on the Name tag `target` [[scripted-fires]]: its rows created into its
    own group at GUN_SPAWN in the NATO2 camp, fogged for the player (CreateUnitOnPosition, probe 1's played shape), kept
    off the camp's AI (AddIgnoredUnitByScript, TheDieburgSalient #143's form), FIRE_LEAD_S (probe 1's lead time), then
    ShootOnPosition on `target`, non-blocking, so an order that never ends holds nothing (GiveOrderStandard OrderType 31:
    TheWingedHussars #362 and Marauders #1341 on CommandPoints, Survivors #1231/#1232 on Name tags), FIRE_HOLD_S for
    the salvo to land, then the battery removed (KillAllUnit, Vanished [[vanished-removal]]). Created guns come with
    full ammunition: no SetAmmo."""
    group, spawn = ctx.group(battery), ctx.tag(GUN_SPAWN)
    return [*(create(ctx, GUN_CAMP, group, n, spawn, unit_path(unit)) for unit, n in BATTERIES[battery]),
            g_ignored(group), g_wait(FIRE_LEAD_S), order(group, SHOOT_ON_POSITION, ctx.tag(target)),
            g_wait(FIRE_HOLD_S), g_vanish(group)]


def fire(ctx: Ctx, battery: str, target: str, hint: str | None) -> Node:
    """`battery` (HEAVY, ROCKETS or GUNS) fires one salvo on the Name tag `target`: once no other fire holds the guns
    (BUSY = 0, then BUSY = 1), the hint `hint` if any, the battery's salvo (created, ordered, removed), then BUSY = 0.
    One fire at a time."""
    busy = ctx.int_var(BUSY)
    said = [g_simul([g_hint(hint, HINT_S, "shint")])] if hint else []
    return g_seq([g_until(g_cmp(busy)), g_set(busy, 1), *said, *salvo(ctx, battery, target), g_set(busy)])


def cooldown(ctx: Ctx) -> Node:
    """The fire-mission cooldown, ts_cool_s seconds: an IfThenElse on the knob's value, one WaitDuration per
    difficulty, Medium's the last else (the difficulty fallback). The knob is the one source: the branches read its
    value, and their waits are KNOBS'."""
    cool = ctx.int_var("ts_cool_s")
    easy, medium, hard = KNOBS["ts_cool_s"]
    return g_if(g_cmp(cool, easy), g_seq([g_wait(easy)]),
                g_if(g_cmp(cool, hard), g_seq([g_wait(hard)]), g_seq([g_wait(medium)])))


def nato_vehicles(ctx: Ctx) -> Node:
    """NATO's vehicles: AllContrainte[Team NATO, NoContrainte[forces.NATO_INFANTRY types]] (Open Door's sack count;
    stock nests both). A fresh node per call."""
    return c_all(c_team(ctx.camp(ENEMY)), c_none(*(c_type(u) for u in forces.NATO_INFANTRY)))


# --------------------------------------------------------------------------- phase 1: the assault (design 5.1)

def prep(ctx: Ctx) -> Node:
    """The preparation fire (design 5.4), once: at PREP_HINT_T its warning hint ts_hprep, at PREP_ASK_T the dialog
    ts_dprep (FIRE AT WILL / HOLD FIRE), asked again PREP_GAP_S after each HOLD FIRE (modkit.ops.mission.reask_loop)
    raced against FIRE AT WILL and the fall (once no dialog is open), its asking flag reset right after the race (the
    answer exit can end it between the loop's two writes [[dialog-reask-loop]]); on FIRE AT WILL the 2S7Ms fire one
    salvo each on the village (fire())."""
    pick, ans, asking = (ctx.int_var(f"ts_prep_{s}") for s in ("pick", "ans", "open"))
    ask = reask_loop("ts_dprep", BUTTONS["ts_dprep"], ctx.camp(PLAYER), pick, ans, asking, PREP_GAP_S)
    return g_seq([g_wait(PREP_HINT_T), g_simul([g_hint("ts_hprep", HINT_S, "shint")]), g_wait(PREP_ASK_T - PREP_HINT_T),
                  g_set(pick, CHOICE_NONE), g_set(ans, CHOICE_NONE),
                  g_compete([ask, g_until(g_cmp(ans, NOW)),
                             g_until(g_and(g_cmp(ctx.int_var(FALLEN), 1), g_cmp(asking)))]),
                  g_set(asking),
                  g_if(g_cmp(ans, NOW), g_seq([fire(ctx, HEAVY, "TS_Village", None)]))])


def phase1(ctx: Ctx) -> Node:
    """H+0:00, phase 1 (design 4, 5.1, 4.2): the phase hint ts_hph1 beside
      - the fall: ts_left = GARRISON_N, then Competition[every RING_POLL_S a ring_round of the NATO units in the
        village's circle into ts_left (modkit.ops.mission: one write a round), WaitCondition(And[ts_fall_n >= ts_left
        (MoreOrEqual against a variable, stock's form), a Soviet command unit (forces.COMMAND_UNITS) in the circle])],
        then FALLEN = 1 and the zone forced to the player with the hint ts_hfall (zone_handover: the game shows nothing
        when a zone changes hands by script) [[count-race-forced-owner]] [[zone-capture-command-units]];
      - the deadline: Competition[the fall, P1_DEADLINE_S then set_end(END_FAIL)];
      - the preparation fire (prep);
      - P1 TAKE THE VILLAGE, pinned on the village, "%1" = ts_left, done on FALLEN (design 4.1: no failure), last."""
    left, fallen, end = ctx.int_var("ts_left"), ctx.int_var(FALLEN), ctx.int_var(END)
    ring = ctx.tag(VILLAGE_RING)
    count = g_seq([*ring_round(ctx, ctx.group("ts_villg"), [VILLAGE_RING], lambda: c_team(ctx.camp(ENEMY)), left),
                   g_wait(RING_POLL_S)], runs=FOREVER)
    falls = g_and(g_cmp(ctx.int_var("ts_fall_n"), op=GE, other=left),
                  g_detect(ring, c_any(*(c_type(u) for u in forces.COMMAND_UNITS)), 1, GE))
    fall = g_seq([g_set(left, GARRISON_N), g_compete([count, g_until(falls)]), g_set(fallen, 1),
                  zone_handover(ctx, PLAYER, [VILLAGE_ZONE], "ts_hfall")])
    deadline = g_compete([g_until(g_cmp(fallen, 1)), g_seq([g_wait(P1_DEADLINE_S), set_end(end, END_FAIL)])])
    p1 = objective("ts_p1", "ts_p1l", g_cmp(fallen, 1), ctx.tag("TS_Village"), [left])
    return beat_hint("ts_hph1", fall, deadline, prep(ctx), p1)


# --------------------------------------------------------------------------- phase 2: the unlock (design 5.2)

def phase2(ctx: Ctx) -> Node:
    """From H+0:00: once FALLEN (the deck's locks lift on it: load_deck), the fall's points [[scripted-economy]]:
    FALL_GRANT at once (GiveRessourceToTeam in a Simultaneous, BlackHorsesLastStand #312), then FALL_INCOME from now on
    (SetIncomeToTeam after the wait, TheWingedHussars #318); RESERVE_DELAY_S later the reserve's cards
    (forces.RESERVE, AddUnitToDeck) [[add-unit-to-deck]]; PHASE2_S after the fall, PH3 = 1. The fall's hint ts_hfall
    (phase1) names them: the reserve, the points, and NATO's recon moving north."""
    joueur = ctx.camp(PLAYER)
    return g_seq([g_until(g_cmp(ctx.int_var(FALLEN), 1)), g_simul([g_grant(joueur, FALL_GRANT)]),
                  g_income(joueur, FALL_INCOME), g_wait(RESERVE_DELAY_S),
                  *(add_card(ctx, unit, n, transport=carrier) for unit, n, carrier in forces.RESERVE),
                  g_wait(PHASE2_S - RESERVE_DELAY_S), g_set(ctx.int_var(PH3), 1)])


# --------------------------------------------------------------------------- the losses (design 4.2)

def warn(var: Node, token: str, after: int = 1) -> Node:
    """Forever: once `var` (a streak's seconds) is `after` or more, the hint `token`; then wait for the streak's
    reset."""
    return g_seq([g_until(g_cmp(var, after, GE)), g_simul([g_hint(token, HINT_S, "shint")]), g_until(g_cmp(var))],
                 runs=FOREVER)


def losses(ctx: Ctx) -> Node:
    """From H+0:00: once FALLEN, side by side
      - NATO owns the village: ts_nato_s counts the seconds NATO controls its zone, reset once the player does
        (shapes.seconds_while: a zone changes hands only by capture, so the player's control is the break); at
        NATO_HOLD_S, set_end(END_LOST); its warning ts_hnato as each streak starts (warn);
      - the village empty: ts_empty_s counts the seconds no Soviet unit is in its command zone (ConditionUnitDansZone,
        ZoneType 1, each in an And as mission.zone_race counts it: the zone's own outline, which "contested" reads,
        not the 40 px circle), reset once one is; at EMPTY_S, set_end(END_EMPTY) (the player's whole force lost
        included); its warning ts_hempty once the streak has lasted EMPTY_WARN_S, naming the time left;
      - P2 HOLD THE VILLAGE, pinned on the village, "%1" = ts_nato_s and "%2" = ts_empty_s (its failures' clocks);
        done once a win is written (END 1..WON), failed once a loss is (END > WON). Last."""
    end, nato_s, empty_s = ctx.int_var(END), ctx.int_var("ts_nato_s"), ctx.int_var("ts_empty_s")
    zone, joueur = ctx.tag(VILLAGE_ZONE), ctx.camp(PLAYER)
    nato_owns = lambda: g_zone_control(ctx.camp(ENEMY), zone)  # noqa: E731
    ours = lambda: g_zone_control(joueur, zone)  # noqa: E731
    empty = lambda: g_and(g_units_in_zones([zone], c_team(joueur), 0, LE))  # noqa: E731
    someone = lambda: g_and(g_units_in_zones([zone], c_team(joueur), 1, GE))  # noqa: E731
    lost = g_seq([g_compete([seconds_while(nato_owns, ours, nato_s, reset=True),
                             g_until(g_cmp(nato_s, NATO_HOLD_S, GE))]), set_end(end, END_LOST)])
    emptied = g_seq([g_compete([seconds_while(empty, someone, empty_s, reset=True),
                                g_until(g_cmp(empty_s, EMPTY_S, GE))]), set_end(end, END_EMPTY)])
    p2 = objective("ts_p2", "ts_p2l", g_and(g_cmp(end, 1, GE), g_cmp(end, WON, LE)), ctx.tag("TS_Village"),
                   [nato_s, empty_s], fail=g_cmp(end, WON + 1, GE))
    return g_seq([g_until(g_cmp(ctx.int_var(FALLEN), 1)),
                  g_simul([lost, emptied, warn(nato_s, "ts_hnato"), warn(empty_s, "ts_hempty", EMPTY_WARN_S), p2])])


# --------------------------------------------------------------------------- phase 3: the counter-attack (design 5.3)

def wave_roe(group: Node) -> list[Node]:
    """A NATO wave's ROE before its route, as stock gives the units of a camp with no AI (RunningTheGauntlet #105 and
    #104 on every enemy unit, #326 on its counter-attack group before its legs): HOLD POSITION when idle, Aggressive
    when fired on."""
    return [g_idle_roe(group, IDLE_HOLD_POSITION), g_roe(group, AGGRESSIVE)]


def wave_end(ctx: Ctx, group: Node) -> Node:
    """A NATO wave's last node, after its last leg into the village [[wave-ends-with-attack]]: an Attack on the
    player's units (Groupe_Joueur, refreshed every profile.REFRESH_S), blocking, last in the wave's Sequential and
    never looped, the follow-on Survivors gives its AI-less enemy camps' groups (#1099, 48 uses)."""
    return g_attack(group, ctx.group(GROUPE_JOUEUR))


def bn1_wave(ctx: Ctx, t: Team) -> Node:
    """One wave of battalion 1, its offset after PH3: if battalion 1 is not yet beaten (BN1_DONE = 0) and, for a
    company team, ts_teams >= its number, ts_b1_made += the wave's tanks, then the wave (modkit.ops.mission.wave:
    created at its lane's entry in the NATO camp into ts_bn1_w<key>, its tanks in a group of their own that joins
    BN1_TANKS_G, its riflemen boarding their Bradleys, its ROE (wave_roe), then its lane, every leg timed, and its
    Attack on the player's units, last: wave_end), raced against BN1_OFF so a break-off stops its route. The add and
    the creates run in one instant chain, so no count sees one without the other."""
    done = g_cmp(ctx.int_var(BN1_DONE))
    sent = done if not t.team else g_and(done, g_cmp(ctx.int_var("ts_teams"), t.team, GE))
    body = wave(ctx, t.wave._replace(offset=0.0), LANES, side=ENEMY, prefix=BN1, board_s=BOARD_S,
                track=(TANKS, forces.BN1_TANKS), before_route=wave_roe, final=lambda g: wave_end(ctx, g))
    tanks = sum(n for unit, n, _ in t.wave.rows if unit in forces.BN1_TANKS)
    made = [g_modify(ctx.int_var("ts_b1_made"), ADD, tanks)] if tanks else []
    go = g_if(sent, g_seq([*made, g_compete([body, g_until(g_cmp(ctx.int_var(BN1_OFF), 1))])]))
    return g_seq([g_wait(t.wave.offset), go] if t.wave.offset else [go])


def b1_count(ctx: Ctx) -> Node:
    """B1's count by battalion 1's survivors [[kill-counts-by-type]]: every POLL_S, ts_b1_alive = BN1_TANKS_G's count
    (SetVariableIntegerFromUnitGroup: the dead leave a group), then ts_b1_k = ts_b1_made - ts_b1_alive, the tanks
    destroyed by anyone, the guns included, in one write (ts_b1_kt holds it while it is made: Substract by a variable,
    as Open Door's catch). Raced against BN1_OFF: the break-off's removal is not a kill, so the count freezes there."""
    alive, made, tmp, kills = (ctx.int_var(f"ts_b1_{s}") for s in ("alive", "made", "kt", "k"))
    poll = g_seq([g_count(alive, ctx.group(BN1_TANKS_G)), g_set(tmp, other=made), g_modify(tmp, SUB, other=alive),
                  g_set(kills, other=tmp), g_wait(POLL_S)], runs=FOREVER)
    return g_seq([g_compete([poll, g_until(g_cmp(ctx.int_var(BN1_OFF), 1))])])


def break_off(ctx: Ctx) -> list[Node]:
    """Battalion 1's deadline (design 4.2): BN1_OFF = 1 (every wave's route stops), each wave by road to its lane's
    entry in the south zone (FastMoveAndAttack, the order its lanes keep the roads with; no stock GiveOrderStandard
    uses QuickMove), then BREAK_OFF_S later every vehicle and rifleman of battalion 1 removed (KillAllUnit,
    Vanished [[vanished-removal]])."""
    orders = [order(ctx.group(f"{BN1}{t.wave.key}"), FAST_MOVE_AND_ATTACK, ctx.tag(LANES[t.wave.lane].entry))
              for t in BN1_WAVES]
    return [g_set(ctx.int_var(BN1_OFF), 1), *orders, g_wait(BREAK_OFF_S),
            g_vanish(ctx.group(BN1), ctx.group(f"{BN1}_inf"))]


def bn1_watch(ctx: Ctx) -> Node:
    """Battalion 1 beaten (design 4.2): Competition[WaitCondition(ts_b1_k >= ts_b1_need), BN1_DEADLINE_S], then
    BN1_DONE = 1 with the hint ts_hbn1 if broken, else the hint ts_hbreak and its survivors' break_off."""
    kills, need, done = ctx.int_var("ts_b1_k"), ctx.int_var("ts_b1_need"), ctx.int_var(BN1_DONE)
    broken = lambda: g_cmp(kills, op=GE, other=need)  # noqa: E731
    return g_seq([g_compete([g_until(broken()), g_wait(BN1_DEADLINE_S)]),
                  g_if(broken(), g_seq([g_set(done, 1), g_simul([g_hint("ts_hbn1", HINT_S, "shint")])]),
                       g_seq([g_set(done, 1), g_simul([g_hint("ts_hbreak", HINT_S, "shint")]), *break_off(ctx)]))])


def phase3(ctx: Ctx) -> Node:
    """From H+0:00: once PH3, the phase hint ts_hph3 beside battalion 1's waves (bn1_wave, each from its offset), the
    count (b1_count), the watch (bn1_watch), the fire boxes' pinned labels (ts_obw, ts_obc: they stand until the battle
    ends) and B1 BREAK THE FIRST BATTALION, a bonus in the panel only (design 7 pins labels on the village, the boxes
    and ASSEMBLY): "%1 / %2" = ts_b1_k and ts_b1_tanks, done once ts_b1_k >= ts_b1_need (MoreOrEqual against a
    variable), which sets B1_DONE (design 4.1: no failure). Last."""
    kills, end = ctx.int_var("ts_b1_k"), ctx.int_var(END)
    boxes = [objective(f"ts_ob{lane.lower()}", f"ts_ob{lane.lower()}l", g_cmp(end, 1, GE), ctx.tag(ring), kind="Bonus")
             for lane, ring in BOX_RINGS.items()]
    b1 = objective("ts_b1", "ts_b1l", g_cmp(kills, op=GE, other=ctx.int_var("ts_b1_need")),
                   counters=[kills, ctx.int_var("ts_b1_tanks")], reussi=g_set(ctx.int_var(B1_DONE), 1), kind="Bonus")
    return g_seq([g_until(g_cmp(ctx.int_var(PH3), 1)),
                  beat_hint("ts_hph3", *(bn1_wave(ctx, t) for t in BN1_WAVES), b1_count(ctx), bn1_watch(ctx),
                            *boxes, b1)])


def fire_missions(ctx: Ctx) -> Node:
    """The fire missions (design 5.4), FIRE_T0 after PH3, forever: which guns (ts_dfire1: ROCKET or ARTILLERY), then
    where (ts_dfire2: ALPHA = BOX W or BRAVO = BOX C), each answer copied once its dialog has closed
    [[dialog-reask-loop]] [[dialog-button-ingame-dictionary]], ts_fire_open = 1 while they ask; then the chosen battery
    fires on the chosen box (fire(), its hint ts_hfirew or ts_hfirec naming the box), then the hint ts_hreload and
    the cooldown (ts_cool_s)."""
    camp = ctx.camp(PLAYER)
    pick1, ans1, pick2, ans2 = (ctx.int_var(f"ts_fire_{s}") for s in ("pick1", "ans1", "pick2", "ans2"))
    asking = ctx.int_var("ts_fire_open")

    def at(battery: str) -> Node:
        return g_if(g_cmp(ans2, NOW), g_seq([fire(ctx, battery, BOX_TAGS["W"], "ts_hfirew")]),
                    g_seq([fire(ctx, battery, BOX_TAGS["C"], "ts_hfirec")]))

    mission = g_seq([g_set(pick1, CHOICE_NONE), g_set(ans1, CHOICE_NONE), g_set(pick2, CHOICE_NONE),
                     g_set(ans2, CHOICE_NONE), g_set(asking, 1),
                     g_choice("ts_dfire1", *BUTTONS["ts_dfire1"], camp, pick1), g_set(ans1, other=pick1),
                     g_choice("ts_dfire2", *BUTTONS["ts_dfire2"], camp, pick2), g_set(ans2, other=pick2),
                     g_set(asking),
                     g_if(g_cmp(ans1, NOW), g_seq([at(ROCKETS)]), g_seq([at(HEAVY)])),
                     g_simul([g_hint("ts_hreload", HINT_S, "shint")]), cooldown(ctx)], runs=FOREVER)
    return g_seq([g_until(g_cmp(ctx.int_var(PH3), 1)), g_wait(FIRE_T0), mission])


def fire_plan(ctx: Ctx) -> Node:
    """The division fire plan (design 5.4), once per battle: PLAN_T0 after PH3 the dialog ts_dplan (FIRE AT WILL /
    HOLD FIRE), asked again PLAN_GAP_S after each HOLD FIRE (reask_loop) until FIRE AT WILL, through phases 4 and 5 if
    need be, its asking flag reset right after the race (the answer can end it between the loop's two writes
    [[dialog-reask-loop]]); then, once no fire holds the guns, the NATO vehicles in each box's circle (nato_vehicles:
    ring_round into ts_plan_w and ts_plan_c), and both batteries (GUNS) fire on the box holding more (BOX W on a tie),
    its hint ts_hplanw or ts_hplanc announcing it."""
    pick, ans, asking = (ctx.int_var(f"ts_plan_{s}") for s in ("pick", "ans", "open"))
    west, centre, counted = ctx.int_var("ts_plan_w"), ctx.int_var("ts_plan_c"), ctx.group("ts_plang")
    ask = reask_loop("ts_dplan", BUTTONS["ts_dplan"], ctx.camp(PLAYER), pick, ans, asking, PLAN_GAP_S)
    return g_seq([g_until(g_cmp(ctx.int_var(PH3), 1)), g_wait(PLAN_T0), g_set(pick, CHOICE_NONE),
                  g_set(ans, CHOICE_NONE), g_compete([ask, g_until(g_cmp(ans, NOW))]), g_set(asking),
                  g_until(g_cmp(ctx.int_var(BUSY))),
                  *ring_round(ctx, counted, [BOX_RINGS["W"]], lambda: nato_vehicles(ctx), west),
                  *ring_round(ctx, counted, [BOX_RINGS["C"]], lambda: nato_vehicles(ctx), centre),
                  g_if(g_cmp(west, op=GE, other=centre), g_seq([fire(ctx, GUNS, BOX_TAGS["W"], "ts_hplanw")]),
                       g_seq([fire(ctx, GUNS, BOX_TAGS["C"], "ts_hplanc")]))])


def sweep(ctx: Ctx, s: Sweep) -> Node:
    """Fighter sweep `s` [[scripted-air-sweep]], Survivors' end strike node for node: Sequential[SpawnUnits on its
    hidden fighters, their group, HOLD POSITION when idle] (#1483-#1489), WaitDuration 1 (#1294), Simultaneous[
    AirplaneMoveAndEngage onto its circle, cancelable] (#1496), Simultaneous[Sequential[WaitCondition(every fighter of
    it out of fuel or ammunition), AirplaneEvacuate, blocking]] (#1647/#1648)."""
    group, tags = ctx.group(f"ts_air_{s.key}"), ctx.spawn_tags(f"air_{s.key}")
    return g_seq([g_seq([g_spawn(tags), g_union(group, tags), g_idle_roe(group, IDLE_HOLD_POSITION)]), g_wait(1.0),
                  g_simul([order(group, AIRPLANE_MOVE_AND_ENGAGE, ctx.tag(s.target), cancelable=True)]),
                  g_simul([g_seq([g_until(g_planes_spent(group, s.count)),
                                  order(group, AIRPLANE_EVACUATE, None, blocking=True)])])])


def air(ctx: Ctx) -> Node:
    """NATO's fighter sweeps (design 6.3), side by side, none holding up a phase (their own beat): from PH3 each sweep
    of SWEEPS_AFTER_PH3 its `after` seconds on, the third only while ts_sweep3 is 1 (Hard); and once battalion 2
    attacks (ATTACK = 1, the strike withheld), SWEEP_AT_ATTACK."""
    def timed(s: Sweep) -> Node:
        go = sweep(ctx, s) if s.knob is None else g_if(g_cmp(ctx.int_var(s.knob), 1), g_seq([sweep(ctx, s)]))
        return g_seq([g_wait(s.after), go])

    after_ph3 = g_seq([g_until(g_cmp(ctx.int_var(PH3), 1)), g_simul([timed(s) for s in SWEEPS_AFTER_PH3])])
    at_attack = g_seq([g_until(g_cmp(ctx.int_var(ATTACK), 1)), sweep(ctx, SWEEP_AT_ATTACK)])
    return g_simul([after_ph3, at_attack])


# --------------------------------------------------------------------------- phase 4: the surprise (design 5.5)

def bn2_tags(ctx: Ctx, half: str | None = None, units: Iterable[str] | None = None) -> list[Node]:
    """The tags of battalion 2's hidden spawns: of half `half` ("W" or "C"; None: both), of the types `units` (None:
    every type), in ITEMS order."""
    groups = {f"bn2_{h.lower()}" for h in (BN2_HALVES if half is None else (half,))}
    wanted = None if units is None else set(units)
    return [ctx.tag(it.name) for it in ITEMS
            if it.addon == "Spawn" and it.group in groups and (wanted is None or it.unit in wanted)]


def bn2_reveal(ctx: Ctx) -> list[Node]:
    """Battalion 2 appears at ASSEMBLY: SpawnUnits on its hidden spawns (in the caller's Sequential: stock never puts
    one straight in a Simultaneous; Survivors #1330) [[spawn-and-create-units]], then its script groups from their
    tags (Survivors #1331): each half, the whole battalion (BN2), its tanks (BN2_TANKS_G, B2's count) and each half's
    Panzergrenadiere and their Marders (their boarding)."""
    halves = {h: ctx.group(f"{BN2}_{h.lower()}") for h in BN2_HALVES}
    unions = [*(g_union(group, bn2_tags(ctx, h)) for h, group in halves.items()),
              g_union(ctx.group(BN2), list(halves.values())),
              g_union(ctx.group(BN2_TANKS_G), bn2_tags(ctx, units=forces.BN2_TANKS))]
    for h, rows in BN2_HALVES.items():
        unions += [g_union(ctx.group(f"{BN2}_{h.lower()}_inf"), bn2_tags(ctx, h, [u for u, _, t in rows if t])),
                   g_union(ctx.group(f"{BN2}_{h.lower()}_ifv"), bn2_tags(ctx, h, [t for _, _, t in rows if t]))]
    return [g_spawn(bn2_tags(ctx)), *unions]


def bn2_attack(ctx: Ctx) -> Node:
    """Battalion 2 attacks (withheld, at the countdown's end; design 5.5, as 5.3): ATTACK = 1 and PH5 = 1 (phase 5
    starts), the hint ts_hatk, and each half, side by side, its Panzergrenadiere boarding their Marders (raced
    against BOARD_S), its ROE (wave_roe), then its lane from ASSEMBLY (BN2_LANES, modkit.ops.mission.lane_route), every
    leg timed, and its Attack on the player's units, last (wave_end), as battalion 1's waves."""
    def half(h: str) -> Node:
        group = ctx.group(f"{BN2}_{h.lower()}")
        return g_seq([board(ctx.group(f"{BN2}_{h.lower()}_inf"), ctx.group(f"{BN2}_{h.lower()}_ifv"), BOARD_S),
                      *wave_roe(group), lane_route(ctx, group, BN2_LANES[h], wave_end(ctx, group))])

    return g_seq([g_set(ctx.int_var(ATTACK), 1), g_set(ctx.int_var(PH5), 1),
                  g_simul([g_hint("ts_hatk", HINT_S, "shint"), *(half(h) for h in BN2_HALVES)])])


def strike(ctx: Ctx) -> Node:
    """The strike (design 5.6), from the release, side by side, each from its own wait:
      - at once the hint ts_hrel, and the zone's label ts_ozone pinned at its centre (done at the kill), last;
      - STRIKE_ROUND_T (with the warning): the round, a fire of its own (salvo): one 2S7M (STRIKER) created at
        GUN_SPAWN, ordered FIRE_LEAD_S later to ShootOnPosition on the assembly area's Name tag (one salvo, leaving
        after its 30 s aiming time), removed FIRE_HOLD_S after the order, then the guns freed (BUSY = 0: the release
        held them);
      - STRIKE_T: the effect STRIKE_FX on ASSEMBLY [[script-effects-self-contained]]; STRIKE_KILL_S later every NATO
        unit in the zone's circle (STRIKE_RING, radius R) gathered into ts_struck_g [[detector-circles-only]] and
        killed with STRIKE_CAUSE (bricks.g_kill), then STRUCK = 1 (B2 done) and PH5 = 1 (phase 5); then the dressing:
        DRESSING_FX together at each DRESSING tag in turn, DRESSING_STEP_S apart.
    The detector takes the NATO camp only: Soviet units inside are not touched (the warning keeps them out)."""
    zone, caught = ctx.tag(STRIKE_RING), ctx.group("ts_struck_g")
    shot = g_seq([*([g_wait(STRIKE_ROUND_T)] if STRIKE_ROUND_T else []), *salvo(ctx, STRIKER, "TS_Assembly"),
                  g_set(ctx.int_var(BUSY))])
    dressing = [g_seq([g_simul([g_fx(fx, ctx.tag(name)) for fx in DRESSING_FX]), g_wait(DRESSING_STEP_S)])
                for name in DRESSING]
    blast = g_seq([g_wait(STRIKE_T), g_fx(STRIKE_FX, ctx.tag("TS_Assembly")), g_wait(STRIKE_KILL_S),
                   g_collect(caught, g_detect(zone, c_team(ctx.camp(ENEMY)), compare=False)),
                   g_kill(caught, cause=STRIKE_CAUSE), g_set(ctx.int_var(STRUCK), 1), g_set(ctx.int_var(PH5), 1),
                   *dressing])
    label = objective("ts_ozone", "ts_ozonel", g_cmp(ctx.int_var(STRUCK), 1), zone, kind="Bonus")
    return g_simul([g_hint("ts_hrel", HINT_S, "shint"), shot, blast, label])


def release(ctx: Ctx) -> Node:
    """The release dialog (design 5.6), RELEASE_ASK_S after battalion 2 appears: once no fire holds the guns and no
    fire-mission or fire-plan dialog is open, or RELEASE_MAX_WAIT_S on at most (Competition[WaitCondition(quiet),
    WaitDuration], so a flag left set never hides the dialog), BUSY = 1 (the guns held for the strike's round), the
    dialog ts_drel (Yes / No), shown once; Yes: STRIKE = RELEASED and the strike; No: STRIKE = WITHHELD, the guns freed
    and the hint ts_hwith."""
    pick, choice, busy = ctx.int_var("ts_rel_pick"), ctx.int_var(STRIKE), ctx.int_var(BUSY)
    quiet = g_and(g_cmp(busy), g_cmp(ctx.int_var("ts_fire_open")), g_cmp(ctx.int_var("ts_plan_open")))
    return g_seq([g_wait(RELEASE_ASK_S), g_compete([g_until(quiet), g_wait(RELEASE_MAX_WAIT_S)]), g_set(busy, 1),
                  g_set(pick, CHOICE_NONE),
                  g_choice("ts_drel", *BUTTONS["ts_drel"], ctx.camp(PLAYER), pick),
                  g_if(g_cmp(pick, NOW), g_seq([g_set(choice, RELEASED), strike(ctx)]),
                       g_seq([g_set(choice, WITHHELD), g_set(busy), g_simul([g_hint("ts_hwith", HINT_S, "shint")])]))])


def phase4(ctx: Ctx) -> Node:
    """From H+0:00: once battalion 1 is beaten (BN1_DONE), BN2_GAP_S later battalion 2 appears (bn2_reveal) with its
    countdown ts_b2_s = COUNTDOWN_S, then side by side:
      - the hint ts_hbn2;
      - B2's count: every POLL_S, ts_bn2_left = its tanks alive (SetVariableIntegerFromUnitGroup: the dead leave a
        group [[kill-counts-by-type]]);
      - the countdown, one a second, raced against the release (STRIKE = RELEASED); run out unreleased, battalion 2
        attacks (bn2_attack);
      - the release dialog and the strike (release);
      - B2 DEAL WITH THE SECOND BATTALION, its countdown "%1 s" pinned at BN2_PIN, done at the strike's kill or the
        attack (design 4.1: no failure);
      - after the attack, B2's "%1 tanks left" pinned at BN2_PIN, done once BN2_BROKEN_N or fewer are left, which sets
        BN2_BROKEN with the hint ts_hbn2b. Last."""
    secs, left, choice = ctx.int_var("ts_b2_s"), ctx.int_var("ts_bn2_left"), ctx.int_var(STRIKE)
    attack, pin = ctx.int_var(ATTACK), ctx.tag(BN2_PIN)
    count = g_seq([g_count(left, ctx.group(BN2_TANKS_G)), g_wait(POLL_S)], runs=FOREVER)
    tick = g_seq([g_wait(1.0), g_modify(secs, SUB, 1)], runs=COUNTDOWN_S)
    countdown = g_seq([g_compete([tick, g_until(g_cmp(choice, RELEASED))]),
                       g_if(g_or(g_cmp(choice), g_cmp(choice, WITHHELD)), g_seq([bn2_attack(ctx)]))])
    b2 = objective("ts_b2", "ts_b2l", g_or(g_cmp(ctx.int_var(STRUCK), 1), g_cmp(attack, 1)), pin, [secs],
                   kind="Bonus")
    broken = g_seq([g_set(ctx.int_var(BN2_BROKEN), 1), g_simul([g_hint("ts_hbn2b", HINT_S, "shint")])])
    b2n = g_seq([g_until(g_cmp(attack, 1)),
                 objective("ts_b2n", "ts_b2nl", g_cmp(left, BN2_BROKEN_N, LE), pin, [left], reussi=broken,
                           kind="Bonus")])
    return g_seq([g_until(g_cmp(ctx.int_var(BN1_DONE), 1)), g_wait(BN2_GAP_S), *bn2_reveal(ctx),
                  g_set(secs, COUNTDOWN_S),
                  g_simul([g_hint("ts_hbn2", HINT_S, "shint"), count, countdown, release(ctx), b2, b2n])])


# --------------------------------------------------------------------------- phase 5 and the end (design 5.8)

def grade(ctx: Ctx) -> list[Node]:
    """The grade at the end clock (design 5.8), written through set_end (a loss already written stands):
    ts_lost = the player's losses (GetNbLossCamp, GloryOrAttrition #161) and ts_alive = Groupe_Joueur's count (what
    is left of what was bought), ts_alive1 = ts_alive + 1; then, if NATO owns the village, END_LOST; else, by the
    release (STRIKE): Total if B1 is done (battalion 1 broken) and battalion 2 struck or broken; else Minor if the
    losses are more than half of what was bought (ts_lost >= ts_alive1: MoreOrEqual against a variable); else
    Major. Total comes first: the design's "release makes Total easy"."""
    end, lost, alive, more = (ctx.int_var(n) for n in (END, "ts_lost", "ts_alive", "ts_alive1"))
    beaten = lambda: g_and(g_cmp(ctx.int_var(B1_DONE), 1),  # noqa: E731
                           g_or(g_cmp(ctx.int_var(STRUCK), 1), g_cmp(ctx.int_var(BN2_BROKEN), 1)))

    def won(total: int, minor: int, major: int) -> Node:
        return g_if(beaten(), g_seq([set_end(end, total)]),
                    g_if(g_cmp(lost, op=GE, other=more), g_seq([set_end(end, minor)]), g_seq([set_end(end, major)])))

    return [g_losses(lost, ctx.camp(PLAYER)), g_count(alive, ctx.group(GROUPE_JOUEUR)), g_set(more, other=alive),
            g_modify(more, ADD, 1),
            g_if(g_zone_control(ctx.camp(ENEMY), ctx.tag(VILLAGE_ZONE)), g_seq([set_end(end, END_LOST)]),
                 g_seq([g_if(g_cmp(ctx.int_var(STRIKE), RELEASED),
                             g_seq([won(END_TOTAL_R, END_MINOR_R, END_MAJOR_R)]),
                             g_seq([won(END_TOTAL_W, END_MINOR_W, END_MAJOR_W)]))]))]


def phase5(ctx: Ctx) -> Node:
    """From H+0:00: once PH5 (the strike's kill, or battalion 2's attack), the hint ts_hph5, then the end clock:
    END_CLOCK_S after a strike; after withholding, until battalion 2 is broken (BN2_BROKEN) or END_CLOCK_WITHHELD_S;
    then the grade."""
    released = g_cmp(ctx.int_var(STRIKE), RELEASED)
    clock = g_if(released, g_seq([g_wait(END_CLOCK_S)]),
                 g_seq([g_compete([g_wait(END_CLOCK_WITHHELD_S), g_until(g_cmp(ctx.int_var(BN2_BROKEN), 1))])]))
    return g_seq([g_until(g_cmp(ctx.int_var(PH5), 1)), g_simul([g_hint("ts_hph5", HINT_S, "shint")]), clock,
                  *grade(ctx)])


BEATS: list[Beat] = [
    Beat(None, "deck", load_deck),
    Beat(None, "groups", load_groups),
    Beat(None, "difficulty", difficulty),
    Beat(None, "funnel", end_funnel),
    Beat(0.0, "phase1", phase1),         # H+0:00: the assault, its deadline and the preparation fire
    Beat(0.0, "phase2", phase2),         # each later phase waits for its flag
    Beat(0.0, "losses", losses),
    Beat(0.0, "phase3", phase3),
    Beat(0.0, "fire_missions", fire_missions),
    Beat(0.0, "fire_plan", fire_plan),
    Beat(0.0, "air", air),               # NATO's fighter sweeps, from PH3 and at battalion 2's attack
    Beat(0.0, "phase4", phase4),
    Beat(0.0, "phase5", phase5),
]


# --------------------------------------------------------------------------- script and content

def deploy_phase(tpl: ndfbin.NdfBin, ctx: Ctx) -> ops_script.DeployPhase:
    """The deployment phase (modkit.ops.script.deploy_phase): DEPLOY_POINTS and START_INCOME (none, written with no
    amount), the buy menu on the profile's PRODUCTION_TYPE (its BATTLEGROUP view), the profile's refresh, the start hint
    ts_hdep until "Launch battle"; its setup then gives the village's zone to NATO and snaps the start camera, the last
    nodes before LoadingDone."""
    deploy = ops_script.deploy_phase(tpl, profile.TEMPLATES, ctx.camp(PLAYER), ctx.group(GROUPE_JOUEUR), [],
                                     points=DEPLOY_POINTS, income=START_INCOME, hint="ts_hdep",
                                     refresh_export=profile.REFRESH_EXPORT, refresh_s=profile.REFRESH_S,
                                     production_type=profile.PRODUCTION_TYPE)
    setup = (*deploy.setup, g_zone_owner(ctx.camp(ENEMY), [ctx.tag(VILLAGE_ZONE)]), g_camera(CAMERA.name))
    return dataclasses.replace(deploy, setup=setup)


def script(tpl: ndfbin.NdfBin) -> tuple[list[Node], list[Node]]:
    """The op's GDScript (layout in the module docstring; modkit.ops.mission.script_frame), from Survivors' GDScript
    template `tpl`: FLAGS are declared even before a beat writes them, and the end funnel is exported."""
    ctx = Ctx()
    return ops_mission.script_frame(tpl, profile.TEMPLATES, ctx, deploy_phase(tpl, ctx), BEATS,
                                    camp_rows=profile.CAMP_ROWS, folder=profile.FOLDER,
                                    start_delay_s=profile.START_DELAY_S, prod_menu_switch=PROD_MENU_SWITCH,
                                    flags=FLAGS)


def content() -> Content:
    """The op (its own scenario, mod folder, GUID and menu tokens); its buy menu may switch to the factory tabs
    (PROD_MENU_SWITCH, which its script's HUD restore writes)."""
    return Content("op", tuple(ITEMS), script, STRINGS, profile.MENU_TOKENS, extra_shapes=EXTRA_SHAPES,
                   scenario=profile.SCENARIO, mod_name=profile.MOD_NAME, menu_renames=profile.MENU_RENAMES,
                   prod_menu_switch=PROD_MENU_SWITCH)
