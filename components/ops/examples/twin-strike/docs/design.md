# Operation Twin Strike: mission design

Operation Twin Strike (working title) is a single-player WARNO Operation: a **Soviet player** against a NATO AI, on
the stock map Twin Cities, built from stock parts only. It is the toolkit's **showcase**. Open Door shows how far the
toolkit goes; Twin Strike shows how little it takes to get a lot on screen. This is its full design. It is built
(section 8, steps 1 to 5: the map, the frame and the mission) and was played once
([[2026-11-11-twin-strike-play1]]); this design carries that play's fixes, which the next play checks.

Mechanisms the design relies on are recorded in the ops knowledge base (`components/ops/knowledge/`), cited by their
record IDs in double brackets.

**Markers:**
- ✓ the mechanism worked in a real play;
- ◐ stock does it, or a probe built it, but no play of ours has shown it;
- ? nothing has shown it yet. Probe 3 is built to answer these (section 9).

## 1. Intent

**What it is for.** The showcase Operation for the README and the Workshop. It is short, readable and loud: three
set pieces, each shown by a different part of the toolkit.

**The story.** It is early July 1989, two weeks into WARNO's war, which starts on 20 June 1989.
- A Soviet tank division's forward detachment is ordered to seize a road-junction village on the western edge of a
  pair of towns. The village opens the road west.
- NATO answers in two blows:
  - first, a US armoured battalion counter-attacks at once;
  - then a West German Panzer battalion assembles just south of the village for a second, heavier blow.
- Soviet doctrine of the time planned nuclear strikes against exactly this: an enemy reserve concentrating to
  counter-attack. Front command offers the player release for one tactical nuclear strike on the assembly area.

**The fun.**
- **Assault.** Take a defended village with a forward detachment and the division's guns.
- **Defence.** Hold it against a battalion that comes on two lanes behind a recon screen and under heavy air defence.
  Choose where the division's fires land.
- **Release.** Then a new threat appears, with a countdown. Ask for release and watch the mushroom cloud, or fight the
  second battalion conventionally.

**Scale.** Every counter carries its real echelon at the in-game counts: one unit is one vehicle or squad. Both NATO
blows are battalion-level. A scale knob (6.4) moves them.

## 2. Goals, non-goals, anti-goals

**Goals:**
- **Three set pieces**, each readable on the map: the assault, the counter-attack on two lanes, and the strike.
- **Player choices that change the battle:** where each fire mission lands; when to fire the one division fire plan;
  release or not.
- **Showcase economy.** One op module a fraction of Open Door's size, built only from the toolkit's existing shapes
  plus what probe 3 proves.
- **Scenario-only.** It ships none of the 16 Gameplay files [[gameplay-mod-relaunch]].
- **Replayable.** Three difficulties (5.7).

**Non-goals:**
- multiplayer;
- playing as NATO (Open Door covers that);
- new units, models or terrain;
- a nuclear weapon as a unit or a card;
- an escalation sequel;
- Army General;
- voice acting.

**Anti-goals** (failure even if it technically works):
- **A nuke that solves everything.** The strike comes only after the first battalion has been beaten conventionally,
  and only on the second battalion's assembly area. Withholding it is a real option with its own ending.
- **A shooting gallery.** The counter-attack comes on two lanes, its recon and AA first, and threatens the village for
  real.
- **Unreadable fires.** Every fire mission names its box. The division fire plan's target is announced. The nuke zone
  is marked on the map with a label pinned at its centre, and a hint gives 30 s warning before the strike. The toolkit
  can pin labels at points, but it cannot draw an area.
- **A mission that hangs.** Every phase has a deadline (4.2), so no missed trigger leaves the battle running forever.
- **A Gameplay mod.** The package gate checks that none of the 16 Gameplay files ships.

## 3. Map and zones

**The map: `_3x3_TwinCities`.**
- Two towns sit side by side in the middle, with a lake behind the eastern one.
- A small village sits at the western edge. It is the objective.
- **Only the far-left village's corner of the map is played: one concentrated battle.** Every set piece, both NATO
  battalions and the strike happen inside a box around the village.
- The toolkit knows it as `modkit.ops.maps.TWIN_CITIES` (section 8, step 1).

**The cut: a box of the stock layout `SM_SU_3x3_TwinCities_03`'s own AI grid.**
- **The playable zone** is the box x 0–216, y 146–524 in minimap px: 216 × 378 px, about 7,500 × 13,200 GRU.
  - It holds the village, the fields and woods north and south of it, and a stream east of it.
  - Its east edge runs along the north–south valley, just west of the crossroads.
  - The crossroads, both towns and the lake are outside it.
- **The AI grid** is the 40 tiles of the stock layout's grid that lie inside the box. The box's every edge is on a tile
  edge (x 0 and 216.125, y 145.6 and 523.6 exactly), so they cover it, up to the stock grid's own seams of 1/8 px
  [[ai-grid-tiles-playable-zone]].
  - `maps.Cut` ships them: `zones.ia_grid_subset` keeps them and the path-cache entries between them.
  - Its `grid` gate's tile-aligned check holds the cut, with the seam `TWIN_CITIES.grid_seam` (320 world).
  - The stock layout's own 432 × 622 px zone was the first cut, and the fallback (section 11).
- **One command zone**, the village: the stock zone `AutoName_5`, 2 points, about x 6–132, y 332–422, kept as it
  ships. The stock crossroads zone straddles the cut's edge, and the left twin's zone is outside it; both are dropped.
- **Two deployment zones**, the op's own, generated from their boxes:
  - **Soviet** (alliance 0): the north strip, about x 40–210, y 158–212. This is the stock north zone's western part.
  - **NATO** (alliance 1): the south strip, about x 6–210, y 490–520.
- The player is alliance 0 in every stock Operation, so **the Soviet player deploys north and NATO comes from the
  south**.
- **The player's arrivals**, the op's own: a ReinforcementLocation for land cards and an AerialCorridor for aircraft
  and helicopters, both entering at the cut's north edge and ending inside the Soviet box. Cards bought after the
  launch, the Ka-50s among them, arrive there ✓ [[deployment-phase-recipe]] [[arrival-end-in-zone]].

**Named places.** All are in minimap px of the full map (768 × 768). One px is 2,560 world units, the same scale as
Geisa: 1 px ≈ 34.8 GRU at `shapes.GRU_WORLD`. The zones are exact. Everything else was read off the satellite picture
by eye, then checked on the Minimap's roads and the satellite picture: `twinstrike/map.py` gives each place its reason,
and those that were off moved at most 20 px.

| Name | px | Role |
|---|---|---|
| VILLAGE | (69, 377) | The objective, the one command zone |
| SOV_ENTRY | the north zone, (110, 190) | Where the assault starts |
| ASSAULT | (110, 215) → (85, 300) → VILLAGE | South across the fields, into the village from the north |
| NATO_ENTRY | the south zone, (60, 511) on the south road and (163, 510) on the east road | Where both battalions' waves are created, one per lane |
| LANE_W | (60, 511) → (65, 470) → VILLAGE | The counter-attack's west lane, straight up the main road at the village's south side |
| LANE_C | (163, 510) → (180, 455) → (150, 409) → VILLAGE | The centre lane, up the east road east of the stream, then west on the road across it into the village |
| BOX_W, BOX_C | (65, 470), (180, 455) | Fire boxes, one on each lane, on its road |
| ASSEMBLY | (156, 500), in the NATO zone | The second battalion's assembly area, on open fields: the nuke zone (5.6) |
| GUN_SPAWN | (140, 14), north of the cut | Where each fire's battery is created and removed (5.4), out of the player's sight |
| GUNS | (15, 158), the cut's north-west corner | The guns' first place; now GUN_SPAWN's unbuilt fallback (5.4) |
| FOB_W, FOB_E | (62, 198), (188, 198), in the Soviet box | The player's two FOBs (6.2) |

**Distances.** Everything is close: from the village, BOX_W is about 3,200 GRU, BOX_C about 4,700 and ASSEMBLY about
5,200. GUN_SPAWN stands 4,577 GRU north of the cut, past the longest ground vision range of any unit the player can
field (4,250 GRU, the MiG-23ML's), and from it:
- the village is 12,865 GRU;
- BOX_W 16,074;
- BOX_C 15,402;
- ASSEMBLY 16,914.
The `fire-range` gate holds these rules on every build.

**The guns' bands decide the guns.** The 2S7M (7,000–35,000) and the BM-27 (10,000–35,000) both reach every target
from GUN_SPAWN; the plan keeps the BM-27 off the village, its preparation fire the 2S7Ms' alone. Nothing on the map is
far enough for the BM-30, so it is dropped (6.2).

## 4. Mission flow (target 35–40 minutes)

| Phase | Time | What happens | Ends when |
|---|---|---|---|
| 0. Deploy | 3 min | Buy and place the forward detachment in the north zone | The player launches |
| 1. Assault | ~10 min | Take the village from its pre-placed garrison. A preparation fire on it is offered (5.4). | The village falls (5.1); deadline 20 min |
| 2. Unlock | ~2 min | The best Soviet cards unlock. The recon screen is reported. | Timer |
| 3. Counter-attack | ~12 min | US battalion 1 comes on both lanes, NATO fighters sweep the boxes. Fire missions and the division fire plan run. | Battalion 1 is broken (6.4), or 15 min with the village held |
| 4. Surprise | ~5 min | Battalion 2 appears at ASSEMBLY with "attacks in 05:00". The release dialog follows. | Strike, or the countdown runs out |
| 5. Hold | 5 min after a strike; up to 20 min after withholding | Hold the village (5.8) | The end clock, or the village is lost |

### 4.2 Deadlines and losses (no phase can hang)

- **Phase 1.** If the village has not fallen 20 min after launch, the battle is lost: "The detachment failed to take
  the village." The deck carries enough command units for the fall (6.1), so the deadline is a real failure, not a
  lost key.
- **Phase 3.** Battalion 1 is beaten when it is broken or after 15 min of counter-attack with the village still held,
  whichever comes first.
  - On the deadline, its survivors break off: FastMoveAndAttack by road to their lane's entry in the south zone (no
    stock order uses FastMove), then Vanished ✓ [[vanished-removal]].
  - Either way it has been beaten conventionally before battalion 2 appears, so the strike never comes early.
- **Losses**, from phase 2 on. Either of these ends the battle:
  - NATO owns the village for 60 s;
  - no Soviet unit is inside the village's command zone for 3 min. This also covers the player's whole force being
    lost. The count reads the zone itself (`ConditionUnitDansZone`, ZoneType 1), the outline the player sees and the
    game calls contested, not the 40 px circle the first play counted, which covered 44 % of the zone
    [[detector-circles-only]]. Its warning comes 20 s into an empty streak and names the time left (2:40); the clock
    is P2's second counter.

### 4.1 Objectives

| ID | Text, in short | Counter | Fails when |
|---|---|---|---|
| P1 | Take the village | "Enemy left in the village: N" | – |
| P2 | Hold the village | "NATO N/60 s, empty N/180 s", the failures' clocks | NATO owns the village for 60 s, or its zone is empty of Soviet units for 3 min |
| B1 | Break the first battalion | "Battalion 1 tanks destroyed: N / 31" (31 at Medium; the difficulty's company teams move it) | – |
| B2 | Deal with the second battalion | the countdown, then "N tanks left" | – |

Objective counters ✓ [[objective-counters]]. Each label is pinned to its place [[objective-label-needs-position]]; B1,
whose battalion comes on both lanes, shows in the objectives panel only.

### 4.3 Economy

The player's points come only from the script (the rules' scripted-only income) ◐ [[scripted-economy]]:
- **Phase 1:** 2,000 points to deploy the forward detachment, and no income (SetIncomeToTeam with no amount, as
  RunningTheGauntlet writes a zero income).
- **The fall:** 4,000 points at once (GiveRessourceToTeam in a Simultaneous, BlackHorsesLastStand's form), then an
  income of 250 from then on (SetIncomeToTeam, TheWingedHussars' mid-battle form). The fall's hint names both.
- No cap: nothing else pays under scripted-only income.
The three values are named constants in `op.py` (`DEPLOY_POINTS`, `FALL_GRANT`, `FALL_INCOME`). The first play's 4,000
with an income of 150 from the start ran short against battalion 1.

## 5. Mechanics

### 5.1 The assault

- **The garrison** is pre-placed and auto-spawned in the village and around it (Marauders' and Survivors' shape) ✓
  [[spawn-and-create-units]]. Its camp has no AI, so at load the script gives it stock's orders, last after its group
  is filled: HOLD POSITION when idle and Aggressive when fired on, then a Hold smart order at the village
  (RedJuggernaut's village defenders) ◐ [[garrison-roe-and-hold]]. In the first play, with none, it stood idle.
- **The fall.** A circular detector over the village counts NATO units ✓ [[detector-circles-only]]. The village falls
  when that count is at or below the garrison's threshold (6.4) and a Soviet command unit is inside.
- **On the fall**, the script forces the village's owner to the player, so the map shows it ✓
  [[count-race-forced-owner]] [[zone-capture-command-units]].

### 5.2 The unlock

- **The cards.** The defence cards are in the deck from the start, locked with `LockDeckUnit` until the village
  falls, then unlocked and added to ◐ [[add-unit-to-deck]].
- **The points.** 4,000 at once and an income from then on (4.3).
- **The hint.** "Village taken. Front releases the division's reserve and 4,000 points, with income from now on. NATO
  recon is moving north."

### 5.3 The counter-attack

- **The waves** are created at the south zone ✓ [[spawn-and-create-units]]. They drive their lanes with
  FastMoveAndAttack, which keeps to the roads ✓ [[fast-move-and-attack-keeps-roads]], and each leg is raced against a
  timeout.
- **The order on each lane** is the recon screen first, then a tank company team with its air defence, about 2 min
  apart.
- **Each wave's ROE**, before its route: HOLD POSITION when idle, Aggressive when fired on (RunningTheGauntlet's
  values for a camp with no AI) [[garrison-roe-and-hold]].
- **The last leg** is MoveAndAttack into the village, raced against a timeout like the others (2 min). Then the wave
  attacks the player's units: an Attack on the refreshed `Groupe_Joueur`, last in its Sequential and never looped, the
  follow-on Survivors gives its AI-less camps ◐ [[wave-ends-with-attack]]. In the first play a wave whose last order
  was the MoveAndAttack stopped at the crossroads. Battalion 2's halves end the same way (5.5).
- **B1 counts battalion 1's tanks destroyed** as its tanks created less those alive, the guns' kills included ✓
  [[kill-counts-by-type]].

### 5.4 Division fires

The division's artillery is real units the player cannot control, outside the deck. They fire with ShootOnPosition ✓
[[scripted-fires]]: real shells, real damage, real suppression. No stock script action deals damage at a place
without a weapon, so this is the only proven way.

**Each fire, its own battery.** In the first play the guns stood pre-placed in the allied camp at GUNS, in view,
emptied between orders, and drove toward the front and died. Now no gun is pre-placed; each fire:
1. creates its battery (the fire's 2S7M ×6, BM-27 ×6, or both for the fire plan) with CreateUnitOnPosition into its
   own group at GUN_SPAWN (3), north of the cut past the player's sight, in the unused NATO2 camp, which fog hides
   from the player (probe 1's played create-then-fire shape);
2. keeps it off that camp's AI (AddIgnoredUnitByScript, TheDieburgSalient's form);
3. waits 20 s (probe 1's lead time);
4. orders ShootOnPosition, non-blocking, on the target's Name tag (`TS_Village`, `TS_BoxW`, `TS_BoxC`, `TS_Assembly`),
   not on a detector circle; stock's artillery ShootOnPosition is TheWingedHussars #362 and Marauders #1341;
5. holds 90 s while the salvo lands;
6. removes the battery (KillAllUnit, Vanished ✓ [[vanished-removal]]).
A created battery comes with full ammunition, and stock never empties artillery: no SetAmmo anywhere. BUSY keeps one
fire at a time. The fallback, unbuilt: the batteries created in the player's allied camp inside the cut's north-west
corner (GUNS), seen for about a minute per fire.

- **Preparation fire**, in phase 1, once.
  - **The offer.** A dialog asks "Preparation fire on the village: Fire now / Not yet". It is asked again every 2 min
    until it is fired or the village falls. Its "asking" flag is reset right after the race, whichever exit won
    [[dialog-reask-loop]].
  - **The fire.** The 2S7Ms hit the village for one salvo each.
  - **The risk.** Shells land wherever the player's units are, so a hint warns before the dialog: "Keep the assault
    out of the village while the guns fire".
- **Fire missions.** These are repeatable, on a cooldown, and start with phase 3. Before that, BOX W and BOX C hold
  nothing.
  - **What and where.** A choice dialog has exactly two buttons, so two dialogs ask in turn: first "Rockets / Heavy
    guns", then "BOX W / BOX C". Both are asked again on each mission ✓ [[dialog-reask-loop]]
    [[dialog-button-ingame-dictionary]].
  - **One salvo.** One ShootOnPosition fires one salvo (its ammunition's `NbSalvosShootOnPosition` is 1).
- **The division fire plan**, once per battle.
  - **When.** During phase 3, a dialog offers "Fire it now / Hold it", again every 2:20 until fired; its flag is reset
    after the race, as the preparation fire's.
  - **Where.** Both batteries fire at once on whichever box holds more NATO vehicles, counted by the boxes' detector
    circles at the moment of firing.
- **Dressing.** `LaunchFXFireAndForgetOnPosition` with `fx_HE_Artillery_203mm_ForScript_RandomPosition` scatters
  extra impacts over the box. Stock uses this in three challenges, and it is visual only ◐.

### 5.5 The surprise

- **The appearance.** When battalion 1 is broken (6.4), battalion 2 is created at ASSEMBLY ✓, laid out by a formation
  helper to fit inside the nuke zone.
- **The pressure.** A pinned objective label and a hint show where it is: "A second NATO battalion is assembling.
  It attacks in 05:00." The countdown is an objective counter ✓.
- **If the countdown runs out**, battalion 2 attacks down both lanes as in 5.3, each half ending with its Attack.

### 5.6 The strike

- **The release dialog** follows the hint: "Request nuclear release / Fight it conventionally" ✓. It waits for no fire
  to hold the guns and no other dialog to be open, but 2 min at most, so a flag left set never hides it (in the first
  play the fire plan's flag stayed set and the dialog never showed); 2:50 of the countdown are left at worst.
- **On release:**
  1. A hint: "Release granted. Strike in 0:30. Keep clear of the marked zone." The zone's label is pinned.
  2. With the hint, the round, a fire of its own (5.4): one `2S7M_Malka_SOV` created at GUN_SPAWN, ordered 20 s later
     to fire at ASSEMBLY's Name tag: one salvo, its three shells, which leave after the gun's 30 s aiming time, so
     they land on the zone after the effect. The 2S7 was the Soviet nuclear-capable gun.
  3. At 0:30, the strike itself: the effect, then the kill (both below).
  4. Dressing: ground fires (`feu_fx_script`, the game's script fire) and black smoke
     (`fx_FumeeNoire_ForScript_RandomPosition`, the burning-wreck effect at random spots) across the zone for a
     minute. The napalm binder (`fx_binder_fire_Napalm_Lourd`) declares three parameters, so a script cannot launch it
     [[script-effects-self-contained]].
  5. B2 completes. Phase 5 starts.
- **On "fight it conventionally":** the countdown runs, battalion 2 attacks, and the division fire plan, if unused, is
  still there. The ending text differs (5.8).

**The effect.** `LaunchFXFireAndForgetOnPosition` with `$/GFX/GameFx/fx_HE_Mega_Bomb_ForScript`, the game's
script-only mega bomb ? [[script-effects-self-contained]]. The game's own mushroom cloud, the tactical-nuke impact
effect (`fx_impact_sol_Tactical_Nuke`, `fx_impact_Tactical_Nuke`), crashes the game when a script launches it
[[scripted-nuke-effect]].

**The kill: every NATO unit inside the zone.** No more and no less.
1. A circular detector of radius R over ASSEMBLY, constrained to the NATO camps.
2. `AddDetectedUnitsToUnitGroup` gathers them into one group ✓ [[detector-circles-only]].
3. `KillAllUnit` kills the group with DeathCause Penetration, which leaves wrecks ?. Vanished ✓ [[vanished-removal]]
   is the fallback if probe 3 shows no wrecks.

Soviet units inside are not touched; the warning keeps them out.

**The radius.** R starts at 800 m and is tuned to the effect's visible size in probe 3. Battalion 2's layout fits
inside 0.8 R.

### 5.7 Difficulty

Difficulty reaches the script as three conditions, with Medium as the baseline ◐ [[difficulty-branches]]. It scales:
- the waves' company counts;
- the fire-mission cooldown;
- the garrison's threshold.

### 5.8 End and grade

With CheckEndGame off, only the script ends the battle, and the first TriggerEndGame wins ✓
[[mission-ends-only-by-script]].

- **Loss** (WinningAlliance 1): any loss in 4.2.
- **The end clock** starts when phase 5 starts. Its length depends on the release dialog:
  - **after a strike:** 5 min;
  - **after withholding:** phase 5 runs until battalion 2 is broken or the village is lost, capped at 20 min. Battalion
    2 starts its attack when the countdown runs out, from about 5,200 GRU away, so the fight comes fast. It needs the
    longer window to be beaten.
- **Win**, by its own type:
  - **Total:** the village is held, battalion 1 is broken, and battalion 2 is destroyed or broken.
  - **Major:** the village is held.
  - **Minor:** the village is held, but the player lost more than half of what they bought.
- **The end dialog** names the strike: "released" or "withheld". There is no moral score; the choice only changes the
  ending text and the battle that came before.
- **Both roads reach the top grade.** Release makes Total easy. Withholding is the harder road to the same grade: break
  battalion 2 in the field.

## 6. Forces and deck

All units are vanilla. Every name below is in the game's DeckPacks. Each build's `units` gate re-checks them.

### 6.1 Player deck

**The base is `OP_BASE_RJ_Player`**, RedJuggernaut's deck for the 79th Guards Tank Division ✓ [[soviet-player-camp]].
- **It keeps its own cards.** These include T-80B and T-80BV packs, a Tunguska, 2S1s, BRM-1, Strela-10, Mi-24K/P,
  Su-25, MiG-23, Su-24M, and DShV in Mi-8s.
- **The script only adds to it**, because a script cannot remove cards.
- **`OP_BASE_GOT_Player` is not used.** It is an East German division.

| When | Script | Cards |
|---|---|---|
| start | AddUnitToDeck, only what RJ lacks or holds too few of (diffed against RJ's packs, pinned in `forces.py`; a stock test re-derives it) | to reach at least `T80BV_SOV` ×10, `T80BV_CMD_SOV` ×2, `BMP_2_CMD_SOV` ×1, `BMP_2_SOV` ×8 with `MotRifles_SOV` ×8, `MTLB_transp_SOV` ×2 with `Engineers_Flam_SOV` ×2, `BRM_1_SOV` ×2, `UAZ_469_SOV` ×2 with `Scout_SOV` ×2, `ZSU_23_Shilka_SOV` ×2, `MTLB_Strela10_SOV` ×1, `2S1_Gvozdika_SOV` ×4, `Ka_29_SOV` ×4 |
| start, after those | AddUnitToDeck, the Soviet player's supply (`modkit.ops.profile.SOVIET_PLAYER_SUPPLY`, `forces.SUPPLY`): RJ's deck has no supply helicopter, and its supply trucks sit only in battlegroups 2 and 3's HQ groups (a stock test re-checks both) | `Ural_4320_SOV` ×4, `Mi_8TZ_SOV` ×2 |
| start, until the village falls | LockDeckUnit, by type | RJ's own defence-grade types: `Tunguska_2K22_SOV`, the Su-24M and Mi-24P variants it holds |
| the fall | unlock, then AddUnitToDeck | `T80U_SOV` ×10, `T80U_CMD_SOV` ×1, `Tunguska_2K22_SOV` ×2, `Osa_9K33M3_SOV` ×2, `Mi_24V_AT_SOV` ×4, `Ka_50_SOV` ×4, `Su_25T_SOV` ×2, `Su_24M_clu_SOV` ×2, `BRDM_2_Konkurs_SOV` ×4, `BMP_2_SOV` ×4 with `MotRifles_Metis_SOV` ×4, `2K12_KUB_SOV` ×2 |

- **Every infantry card rides in a carrier,** as stock fields each of these squads (no stock deck holds one bare): in
  the first play the bare engineers and scouts deployed on foot, while the motor rifles in their BMP-2s deployed
  loaded ✓ [[add-unit-to-deck]]. Each carrier is one RJ's deck already fields or the start adds bring: the engineers
  in MT-LBs (the 2S12's tractor), the scouts in UAZ-469s, the Metis teams in BMP-2s.
- **The buy menu opens on its BATTLEGROUP view** (`ChangeProductionType` Deck, 0, Twin Strike's alone through
  `profile.PRODUCTION_TYPE`; every other content keeps stock's Groups, 1). The cards the script adds join no
  battlegroup, so they show in that view only, as the first play showed; the view switch stays, so GROUPS is a click
  away.
- **Heavy air defence** against NATO's fighter sweeps (6.3): `2K12_KUB_SOV` ×2 with the reserve, the 79th Guards Tank
  Division's own SAM, bare as every stock pack holds it.

- **Helicopters.** RJ's deck already flies Mi-8s with DShV, Mi-2s and Mi-24K/P, so a Soviet player's helicopter
  cards are stock.
  - **Ka-29 ×4 from the start**, bare, as its only stock pack has it: rocket and gun runs on the garrison. Loaded with
    infantry it would be a transport card (6.1's proof line).
  - **Ka-50 ×4 with the reserve.** The game has no Ka-52; the Ka-50 is its single-seat parent. It is a tank killer,
    held for battalion 1's Abrams, like the Mi-24V. At the start it would make short work of the garrison's three
    Leopards and one Gepard. Stock's own mid-battle AddUnitToDeck uses are all aircraft ◐ [[add-unit-to-deck]].

- **Command units.** Three of them (2 T-80BV CMD, 1 BMP-2 CMD), so the fall (5.1) does not depend on one vehicle.
- **Supply.** RJ's deck was shaped for RedJuggernaut: no supply helicopter, and its Ural-4320s only in the two tank
  battalions' HQ groups, so a player who never opens those groups finds no supply ([[soviet-player-camp]]). The
  script adds four Ural-4320 trucks and two Mi-8TZ supply helicopters at the start, the toolkit's shared Soviet
  supply, so the player can supply by road and by air whatever battlegroups the buy menu shows.
- **The lock acts by type,** so it never names a type the player needs before the fall.
- **Proof.** A transport card played ✓ [[add-unit-to-deck]]; lock-then-unlock is ◐.

### 6.2 Soviet units not in the deck

| Group | Units | How |
|---|---|---|
| FOBs, at FOB_W and FOB_E | `FOB_SOV` ×2 | Pre-placed in the player's camp and auto-spawned, so they stand in the north zone from the deployment on. No deck that `SetDeck` can address holds a FOB [[deployment-phase-recipe]]. Marauders and SigurdsStrike place the player's FOB the same way (`C0_FOB_UK_2`, `C0_FOB_TCH_1`, in Camp 0) ◐. |
| Division artillery | `2S7M_Malka_SOV` ×6, `BM27_Uragan_SOV` ×6, and one `2S7M_Malka_SOV` for the strike's round | Not pre-placed: each fire creates its battery at GUN_SPAWN, north of the cut out of the player's sight, in the unused NATO2 camp, and removes it once the salvo has landed (5.4). Uncontrolled; they fire on order only, and no NATO unit can reach them. In the first play they stood pre-placed in the allied camp at GUNS and drove toward the front. |

### 6.3 NATO forces (all scripted)

| Group | Units | ≈ | How |
|---|---|---|---|
| Garrison (West German) | `Panzergrenadier_IFV_RFA` ×4, `Marder_1A3_RFA` ×3, `ATteam_Milan_2_RFA` ×2, `Leopard_1A5_RFA` ×3, `Gepard_1A2_RFA` ×1, `Fernspaher_RFA` ×1 | 14 | Pre-placed, auto-spawned |
| Battalion 1 (US armoured task force) | `M1A1HA_Abrams_US` ×30, `M1A1HA_Abrams_CMD_US` ×1, `M2A2_Bradley_IFV_US` ×10 with `Rifles_half_AT4_US` ×9 | 50 | Created in waves on both lanes |
| ↳ its recon screen | `M3A2_Bradley_CFV_US` ×3, `Scout_US` ×3, `OH58D_Kiowa_Warrior_US` ×2 | 8 | First wave on each lane |
| ↳ its air defence | `M163_PIVADS_US` ×2, `M48_Chaparral_MIM72F_US` ×2, `M998_Avenger_US` ×2, `MANPAD_Stinger_C_US` ×3 | 9 | With the tank companies |
| Battalion 2 (West German Panzer battalion) | `Leopard_2A4_RFA` ×28, `Leopard_2A3_CMD_RFA` ×1, `Marder_1A3_RFA` ×8 with `Panzergrenadier_IFV_RFA` ×8, `Gepard_1A2_RFA` ×3, `Marder_Roland_2_RFA` ×2, `Luchs_A1_RFA` ×2 | 52 | Created at ASSEMBLY (5.5) |
| Fighter sweeps | `F15C_Eagle_AA_US` ×5, `F4F_Phantom_II_AA_RFA` ×2 | 7 | Pre-placed hidden in the NATO deployment zone, revealed by sweep (below) |

**The AI decks** come from the stock NATO Operation decks that probe 3 loads.

**NATO's fighter sweeps**, Survivors' end strike node for node ◐ [[scripted-air-sweep]]: the fighters stand hidden in
the NATO camp; a sweep reveals its set (SpawnUnits), sets HOLD POSITION when idle, a second later sends it over its
circle (AirplaneMoveAndEngage, cancelable), and sends it home (AirplaneEvacuate) once every fighter of it is out of
fuel or ammunition. Each sweep is its own group, in its own branch, so none holds up a phase.

| When | Who | Where |
|---|---|---|
| phase 3 + 2:30 | 2 × `F15C_Eagle_AA_US` | BOX W's circle |
| phase 3 + 6:00 | 2 × `F15C_Eagle_AA_US` | BOX C's circle |
| phase 3 + 10:00, Hard only | 1 × `F15C_Eagle_AA_US` | the village's circle |
| after a withheld strike, once battalion 2 attacks | 2 × `F4F_Phantom_II_AA_RFA` | the village's circle |

### 6.4 Scale knob and thresholds

- **Forces are tables** (one row per unit type, with its count at 1×, its place and its group), as in Open Door's
  `forces.py`. One `FORCE_SCALE` multiplies every row.
- **Thresholds are shares, not counts.** The build turns each into a count.
  - The village falls at 25 % of the garrison left.
  - Battalion 1 is broken at 30 % of its tanks left.
  - Battalion 2 is broken at 30 %.
- **Budget.**
  - Battalion 2 appears only after battalion 1 is broken.
  - The peak is about 66 of the player's units (the supply's 4 trucks and 2 helicopters included), 20 left of
    battalion 1, and 52 of battalion 2: about 140, with a battery of up to 12 guns north of the cut for a fire's
    two minutes and a sweep's few fighters.
  - That is over Open Door's ~120 envelope. No play has gone that big yet ? [[script-and-battle-scale]].
  - All of it is packed into the 216 × 378 px cut. The density is the point: one concentrated battle.
  - If frame rate suffers, or the columns jam, the knob comes down.

## 7. Presentation

- **Hints and dialogs:**
  - a start hint names the village;
  - every phase change has a hint;
  - the fire-mission, fire-plan and release dialogs are two-button choices whose labels come from the in-game
    dictionary ✓ [[dialog-button-ingame-dictionary]].
- **Labels.** Objective labels are pinned to VILLAGE, the two boxes and ASSEMBLY.
- **Camera.** It snaps to the village before LoadingDone ◐ [[start-camera-before-loading-done]].
- **Text.** English. Simplified Chinese is a later build; the toolkit's glyph gate is ready for it.
- **Screenshots** for the README: the assault on the village under fire, the counter-attack's columns on the tactical
  map, the mushroom cloud over ASSEMBLY, and the end screen.

## 8. Build route

**What the toolkit already has:**
- the Operation driver and every gate;
- the deployment recipe;
- waves, road orders, detectors, counters, dialogs and hidden batteries;
- the formation helper;
- the scale-knob pattern.

**What it needs:**
1. **Twin Cities support.**
   - A `StockMap` record for `_3x3_TwinCities`.
   - `STOCK_PATHS` already holds the layout `SM_SU_3x3_TwinCities_03_Details` and the map's Preview and Minimap (added
     with the storyboard).
   - **The cut** (3):
     - the op's own PlayableZone, the box;
     - the AI grid as `zones.ia_grid_subset` of the stock layout's grid, held by the `grid` gate's tile-aligned check;
     - the village's command zone as it ships;
     - the two deployment zones generated from their boxes;
   - the player's arrival entries, ending in the Soviet box;
   - the two FOBs, pre-placed in the player's camp.
   - Named points.
2. **A Soviet player**, by the camp shape probe 3 proves [[soviet-player-camp]]. Probe 3 added `Content.deck_swap` for
   the menu's player deck.
3. **Lift Open Door's composed pieces into `modkit.ops`.** The library has the primitives, but the composed mission
   pieces Twin Strike needs live only in Open Door's `op.py`:
   - lane legs raced against timeouts;
   - waves and boarding;
   - the dialog re-ask loop;
   - the end funnel, the zone race, the difficulty branches and the script frame.

   Probe 1's hidden battery lives only in `probes/spike.py`. The toolkit's rule is one source of truth with no copies,
   so this is a refactor task of its own, before the example. Open Door and the probes must build byte-identical
   before and after.
4. **The example** `components/ops/examples/twin-strike/`:
   - a `twinstrike/` package with its own `forces.py`, `map.py`, `strings.py` and `op.py`;
   - a `build.py`;
   - its README and play sheet;
   - extra gates as Open Door has: `units`, `no-template-name`, `grid` and `zone-layout`.
5. **The strike**, by the effect and the death cause probe 3 proves [[scripted-nuke-effect]].

Each step is one task with its own gates. Steps 1, 2 and 3 are independent of each other, and all three come before
4. Step 5 is part of 4.

## 9. The probe

Probe 3 (`components/ops/examples/probes`, contents `nuke` and `nuke_sov`) answers every "?" above in one short
launch:
- **The effect.** Does a script launch the nuke effect, under which name, how big, and with sound?
- **The kill.** Does Penetration leave wrecks?
- **The flip.** Can the player's camp be Soviet in a clone of Survivors, with which stock deck?

`nuke_sov` also checks, with a Soviet player:
- a transport card bought;
- lock-then-unlock in the buy menu;
- a battery in the player's allied AI camp firing ShootOnPosition. Probe 1 proved only an enemy-camp battery.
- the stock 203 mm script effect, beside the nuke.

Its answers set R (5.6), the death cause, and the deck bases (6.1, 6.3).

## 10. Left to the builder

- The exact lane waypoints, box radii and the GUN_SPAWN point, checked on the overlay against roads and the zone
  layout. Each target's range from GUN_SPAWN must sit inside its gun's band (3); the `fire-range` gate checks it.
- The deployment boxes' exact edges, inside the cut.
- Wave timings within the phase budgets.
- Hint and dialog wording. Keep it short and in WARNO's voice.
- Whether the village's stock command zone file ships as it is, or is regenerated from its polygon, as the toolkit's
  gates prefer.

## 11. Risks

| Risk | If it bites | Fallback |
|---|---|---|
| The nuke effect does not play from a script | No cloud | Stack the 203 mm script effect and the black smoke; keep the kill |
| Penetration leaves no wrecks or fails at load | Units vanish | Vanished ✓, under the cloud |
| A Soviet player camp breaks the clone | Twin Strike cannot be Soviet | Re-clone from a Soviet-player stock challenge. That is a new `Template`, and the largest cost. |
| Battle size: about 130 at the peak, 35–40 min | Frame rate, script load | The scale knob; shorter phases |
| The cut's AI grid fails at load, as a whole-map grid under a smaller zone once did | The Operation does not load | Play the stock layout's whole 432 × 622 px zone, whose files ship as they are. The grid subset is the shape probe 1 played on Geisa ✓ [[ai-grid-tiles-playable-zone]]. |
| Two battalions and the player's force in a 216 × 378 px box | Columns jam; frame rate | The scale knob; stagger the waves |
| Transport cards (infantry in BMPs) | Infantry cannot be bought mounted | Separate infantry and vehicle cards |
| A pre-placed FOB in the player's camp, under a Soviet player | No FOB at the start | Create both by script at launch, with `CreateUnitOnPosition` ✓ [[spawn-and-create-units]] |
