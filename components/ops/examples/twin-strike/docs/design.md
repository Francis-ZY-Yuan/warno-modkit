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
| GUN_SPAWN | (15, 158), the cut's north-west corner | Where each fire's battery is created, in the player's allied camp, and removed (5.4) |
| FOB_W, FOB_E | (62, 198), (188, 198), in the Soviet box | The player's two FOBs (6.2) |

**Distances.** Everything is close: from the village, BOX_W is about 3,200 GRU, BOX_C about 4,700 and ASSEMBLY about
5,200. GUN_SPAWN stands in the forest of the cut's north-west corner, outside the Soviet box, and from it:
- the village is 7,846 GRU;
- BOX_W 10,991;
- BOX_C 11,818;
- ASSEMBLY 12,867.
The `fire-range` gate holds these ranges on every build, and the build's own gate keeps every unit the script creates
inside the cut [[created-units-stand-in-zone]].

**The guns' bands decide the guns.** The 2S7M (7,000–35,000) reaches every target from GUN_SPAWN, the BM-27
(10,000–35,000) the boxes and ASSEMBLY but not the village; the plan keeps the BM-27 off the village, its preparation
fire the 2S7Ms' alone. Nothing on the map is far enough for the BM-30, so it is dropped (6.2).

## 4. Mission flow (target 35–40 minutes)

| Phase | Time | What happens | Ends when |
|---|---|---|---|
| 0. Deploy | 3 min | Buy and place the forward detachment in the north zone | The player launches |
| 1. Assault | ~10 min | Take the village from its pre-placed garrison. A preparation fire on it is offered (5.4). | The village falls (5.1); deadline 20 min |
| 2. Unlock | ~2 min | The best Soviet cards unlock. The recon screen is reported. | Timer |
| 3. Counter-attack | ~12 min | US battalion 1 comes on both lanes, NATO fighters sweep the boxes. Fire missions and the division fire plan run. | Battalion 1 is broken (6.4), or 15 min with the village held |
| 4. Surprise | ~5 min | Battalion 2 appears at ASSEMBLY with "attacks in 05:00". The release dialog follows; after a strike, the Soviets finish what it left of battalion 2. | Battalion 2 broken after a strike (20 min at most), or the countdown runs out |
| 5. Hold | 5 min after a struck battalion 2 breaks; up to 20 min after withholding; P3 shows the time left | Hold the village (5.8) | The end clock, NATO has no ground unit left, or the village is lost |

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
| B2 | Deal with the second battalion; after a strike, finish it | the countdown, then "N tanks left" | – |
| P3 | Hold on (phase 5): 5 min after a struck battalion 2 breaks, or 20 min at most after withholding | the end clock, "Ends in 4:59", a running timer | – (done or failed with the ending) |

Objective counters ✓ [[objective-counters]]. Each label is pinned to its place [[objective-label-needs-position]]; B1,
whose battalion comes on both lanes, shows in the objectives panel only. P3's label, its clock, is pinned on the
village's command zone. The fire boxes' labels are done once nothing more comes through the boxes (battalion 2
broken, struck or not, or the end), so no label the player cannot act on stays open in phase 5.

### 4.3 Economy

The player's points come only from the script (the rules' scripted-only income) ◐ [[scripted-economy]]:
- **Phase 1:** 3,000 points to deploy the forward detachment, and no income (SetIncomeToTeam with no amount, as
  RunningTheGauntlet writes a zero income).
- **The fall:** 8,000 points at once (GiveRessourceToTeam in a Simultaneous, BlackHorsesLastStand's form), then an
  income of 500 a tick from then on (SetIncomeToTeam, TheWingedHussars' mid-battle form). The fall's hint names both.
- No cap: nothing else pays under scripted-only income.
The three values are named constants in `op.py` (`DEPLOY_POINTS`, `FALL_GRANT`, `FALL_INCOME`). The first play's 4,000
with an income of 150 from the start ran short against battalion 1. Its fix, 2,000, then 4,000 and 250 at the fall,
still left NATO well ahead in the next smoke play; the balance (6.5) sets the values now, the income doubled.

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
- **The points.** 8,000 at once and an income from then on (4.3).
- **The hint.** "Village taken. Front releases the division's reserve and 8,000 points, with income from now on. NATO
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

**Each fire, its own battery.** In the first play the guns stood pre-placed in the allied camp at GUN_SPAWN, in
view, emptied between orders, and drove toward the front and died. The next build created each fire's battery 4,577
GRU north of the cut, in the unused NATO2 camp, to hide it: in play it stood on the cut's north edge beside the Soviet
box, an enemy to the player, and the player's Ka-50s killed it, though its shells landed
[[created-units-stand-in-zone]]. Now no gun is pre-placed; each fire:
1. creates its battery (the fire's 2S7M ×6, BM-27 ×6, or both for the fire plan) with CreateUnitOnPosition into its
   own group at GUN_SPAWN (3), in the player's allied camp (SovietAlly), so the player's units never engage it and
   the player sees it for about 2 minutes (probe 1's played create-then-fire shape);
2. keeps it off that camp's AI (AddIgnoredUnitByScript, TheDieburgSalient's form);
3. waits 20 s (probe 1's lead time);
4. orders ShootOnPosition, non-blocking, on the target's Name tag (`TS_Village`, `TS_BoxW`, `TS_BoxC`, `TS_Assembly`),
   not on a detector circle; stock's artillery ShootOnPosition is TheWingedHussars #362 and Marauders #1341;
5. holds 90 s while the salvo lands;
6. removes the battery (KillAllUnit, Vanished ✓ [[vanished-removal]]).
A created battery comes with full ammunition, and stock never empties artillery: no SetAmmo anywhere. BUSY keeps one
fire at a time. A battery lives 110 s, so even a drive toward the front, as the first play's guns did, ends before it
gets far.

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
- **On release** (seconds after the answer):
  1. **0:00.** A hint: "Release granted. Strike in 0:30. Keep clear of the marked zone." The zone's label is pinned.
     The guns stay held from the release on, so no fire lands in the strike's window.
  2. **0:25, the camera.** It flies to the zone from wherever the player's camera is, in 4 s, easing in and out,
     Escape skipping the move, and arrives a second before the flash; it holds the zone 11 s, the player's actions
     blocked, then hands control back ◐ [[camera-shot-from-current-position]]. The view: ASSEMBLY, facing south,
     40 degrees down from 390,000 world units above the ground, the whole zone ahead (`twinstrike.map.STRIKE_SHOT`,
     the camera path `TS_Strike`). With the fog lift switched on (below), the fog goes off as the camera starts.
  3. **0:30, the flash.** The game's own tactical-nuke effect on ASSEMBLY, with a light accent round it (below).
  4. **0:30.5, the toll**, inside the fireball (below): a share of battalion 2 killed, the rest damaged and stunned.
     B2's countdown completes; B2 becomes "FINISH THE SECOND BATTALION: N tanks left".
  5. **0:40, as the camera hands back control,** the fog comes back on if the lift is on, the guns are freed, and a
     hint says what is left: "The strike has
     gutted the second battalion. Its survivors are stunned and damaged: finish it." Timed, not chained to the
     cutscene, so Escape or a slow cutscene holds nothing.
  6. **Then the Soviets finish it.** B2 completes once battalion 2 is broken (BN2_BROKEN_N tanks or fewer left, as on
     the withheld road; a destroyed battalion has none), with the hint "The second battalion is broken." Phase 5 starts
     then, or at once when NATO has no ground unit left, or 20 min after the camera hands back at most (no phase
     hangs, 4.2).
     Phase 5 never starts inside the cutscene, so its end never opens a dialog there.
  No gun fires the strike. The first build's lone 2S7M round landed 36 to 46 s after the kill, on a zone already
  empty, and is gone.
- **On "fight it conventionally":** the countdown runs, battalion 2 attacks, and the division fire plan, if unused, is
  still there. The ending text differs (5.8).

**The flash: the game's own nuke, with a light accent** ✓ [[scripted-nuke-effect]]. In one Simultaneous, 19
launches:
- **The nuke, once, on ASSEMBLY.** The game's tactical-nuke impact effect (`fx_impact_sol_Tactical_Nuke`) crashes the
  game when a script launches it directly: its four parameters are left unbound. The script exports a wrapper of its
  own instead (`$/GDScript/TS/FxNuke`, `shapes.nuke_wrapper`), a call that binds all four, as stock's black smoke binds
  its effect's one ✓ [[script-effects-self-contained]]. The launch names the wrapper. parPosition is ASSEMBLY's world
  position on the map's ground, the form the strike-effects probe played on its tag; parRadiusPhysical is the probe's
  60,000 world units (some 280 m of ground scorch and scenery destroyed, far short of the village). In that play it
  made a large nuclear fireball and dust cloud, with no crash, and killed nothing: the toll below does.
- **The accent, 18 self-contained launches round the fireball:** 4 mega bombs (`fx_HE_Mega_Bomb_ForScript`) on the
  four outer spots off the axes (NNW, NNE, SE, SW; the spots are six inner ones over battalion 2, 0.15 to 0.32 R, and
  six outer ones about 0.5 R out, the two southern ones pulled north inside the cut); the 203 mm barrage
  (`fx_HE_Artillery_203mm_ForScript_RandomPosition`, each launch one impact up to about 900 m round its tag) once on
  each of the 12 spots; white smoke with a ground fire (`fx_FumeeBlanche_ForScript_RandomPosition`, it lasts minutes)
  on the two outer spots on the axis, W and E.
- **No black smoke.** In the probe's play, black smoke at 4 tags beside 10 mega bombs and 50 impacts grew into huge
  plumes that lingered for minutes, and the game slowed, worse with time. The first build of this flash launched 97
  effects, 7 of them black smoke; this one launches 19.
The napalm binder (`fx_binder_fire_Napalm_Lourd`) declares three parameters; it is not used.

**The fog: a lift, off by default** (`STRIKE_FOG_LIFT` in `twinstrike/op.py`). Switched on, the fog goes off as the
camera starts (0:25) and back on as it hands control back (0:40), map-wide (`TGDDescriptorFow`) [[fog-switch]]. The
probe's play showed the switch lift the fog; it did not show the fog come back, and no stock script switches it. So
the build leaves it off: the zone lies in fog for the player, and the camera and the effects show the strike through
it (script effects show in fog).

**The toll: kill, damage, stun; the Soviets finish them.** The strike no longer kills every NATO unit in the zone.
1. **The zone.** A circular detector of radius R over ASSEMBLY, constrained to the NATO camps, gathers every NATO
   unit inside into one group ✓ [[detector-circles-only]].
2. **The kill: a share of battalion 2, by difficulty** (the knob `ts_kill_pct`): 50 % on Easy, 40 % on Medium, 30 %
   on Hard, 26, 21 or 16 of its 52 units. They are whole units, apportioned over its types by largest remainder, so
   tanks and IFVs both lose about the share (15, 12 or 9 of its 29 tanks; 4, 3 or 2 of its 8 Marders), and spread
   through both halves' formations (`op.strike_kills`). Each is killed by its spawn tag: `KillAllUnit` on spawn tags
   is stock (Marauders kills pre-placed units so) ◐, with DeathCause Penetration, which leaves wrecks ?; Vanished ✓
   [[vanished-removal]] is the fallback. A count loop of `TransferUnitToUnitGroup` would have needed a shape no play
   has run.
3. **The damage:** `ChangeStress` Physical, 5 health points off every unit left in the zone: half of a tank's or a
   Marder's 10, five of a Panzergrenadier squad's 6. It kills nothing ✓ [[changestress-damagetype-zero]]: in the
   probe's play, Value 5 left an Abrams and a Bradley at 5 of 10 health segments.
4. **The stun:** `ChangeStress` Stun, 240 points on every one of them, 0.8 of a ground unit's 300 cap ?. No stock
   script writes `ChangeStress`; in the probe's play Stun 240 showed no visible sign. Suppress cannot be written: it
   fails at load.
5. **The finish.** The survivors stay at ASSEMBLY: their tanks left (14, 17 or 20) are above the 9 that break the
   battalion, so the Soviets must go in and finish it (step 6 above).

Soviet units inside are not touched; the warning keeps them out. NATO units of battalion 1 caught in the zone are
damaged and stunned, not killed.

**The radius.** R is 800 m. Battalion 2's layout fits inside 0.8 R. The nuke's fireball sits on its centre; the
mega bombs stand about 0.5 R out, and the barrage's impacts reach past R.

### 5.7 Difficulty

Difficulty reaches the script as three conditions, with Medium as the baseline ◐ [[difficulty-branches]]. It scales:
- the waves' company counts;
- the fire-mission cooldown;
- the garrison's threshold;
- the strike's kill: 50, 40 or 30 % of battalion 2 (5.6).

### 5.8 End and grade

With CheckEndGame off, only the script ends the battle, and the first TriggerEndGame wins ✓
[[mission-ends-only-by-script]].

- **Loss** (WinningAlliance 1): any loss in 4.2.
- **The end clock** starts when phase 5 starts. Its length depends on the release dialog:
  - **after a strike:** 5 min, from when the Soviets have broken what the strike left of battalion 2 (5.6), or NATO
    has no ground unit left; 20 min after the strike at most, so the phase cannot hang;
  - **after withholding:** phase 5 runs until battalion 2 is broken or the village is lost, capped at 20 min. Battalion
    2 starts its attack when the countdown runs out, from about 5,200 GRU away, so the fight comes fast. It needs the
    longer window to be beaten.
- **NATO spent.** Either clock is cut short the moment NATO has no ground unit left on the map (its garrison,
  battalion 1 and battalion 2 groups all empty): the battle ends at once with the grade that state earns. Its fighters
  do not count: a sweep can neither take nor hold the village, and where an evacuated fighter goes is unseen
  [[scripted-air-sweep]].
- **The clock is shown**, in stock's way: P3 (HOLD ON) lists a timer in its label, "Ends in %1", started with the
  clock and shown on the village's command zone and in the objective list, as stock shows its timed holds on the zone
  held (TheKitzingenRuse's "HOLD DMITRI", "Reinforcements in %1"; 7 stock objectives list a timer)
  [[objective-counters]]. The smoke play's end had none: after the strike the panel showed only P2's failure clocks
  and the two box labels, open with nothing to do, and the player left before the 5 min ran out.
- **Win**, by its own type:
  - **Total:** the village is held, battalion 1 is broken, and battalion 2 is destroyed or broken.
  - **Major:** the village is held.
  - **Minor:** the village is held, but the player lost more than half of what they bought.
- **The end dialog** names the strike: "released" or "withheld". There is no moral score; the choice only changes the
  ending text and the battle that came before.
- **Both roads reach the top grade.** Release makes Total easier: the strike guts battalion 2 and the Soviets finish
  it. The strike alone no longer beats it. Withholding is the harder road to the same grade: break battalion 2 in the
  field.

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
| start | AddUnitToDeck, only what RJ lacks or holds too few of (diffed against RJ's packs, pinned in `forces.py`; a stock test re-derives it) | to reach at least `T80BV_SOV` ×10, `T80BV_CMD_SOV` ×2, `BMP_2_CMD_SOV` ×1, `BMP_2_SOV` ×8 with `MotRifles_SOV` ×8, `BTR_80_SOV` ×2 with `ATteam_KonkursM_TTsko_SOV` ×2, `MTLB_transp_SOV` ×2 with `Engineers_Flam_SOV` ×2, `BRM_1_SOV` ×2, `UAZ_469_SOV` ×2 with `Scout_SOV` ×2, `ZSU_23_Shilka_SOV` ×2, `MTLB_Strela10_SOV` ×1, `2S1_Gvozdika_SOV` ×4, `Ka_29_SOV` ×4 |
| start, after those | AddUnitToDeck, the Soviet player's supply (`modkit.ops.profile.SOVIET_PLAYER_SUPPLY`, `forces.SUPPLY`): RJ's deck has no supply helicopter, and its supply trucks sit only in battlegroups 2 and 3's HQ groups (a stock test re-checks both) | `Ural_4320_SOV` ×4, `Mi_8TZ_SOV` ×2 |
| start, until the village falls | LockDeckUnit, by type | RJ's own defence-grade types: `Tunguska_2K22_SOV`, the Su-24M and Mi-24P variants it holds |
| the fall | unlock, then AddUnitToDeck | `T80U_Obr89_SOV` ×15, `T80U_CMD_SOV` ×1, `Tunguska_2K22_SOV` ×2, `Osa_9K33M3_SOV` ×2, `Mi_24V_AT_SOV` ×6, `Ka_50_SOV` ×4, `Su_25T_SOV` ×2, `Su_24M_clu_SOV` ×2, `BRDM_2_Konkurs_SOV` ×6, `BMP_2_SOV` ×8 with `MotRifles_Metis_SOV` ×8, `BTR_80_SOV` ×4 with `ATteam_KonkursM_TTsko_SOV` ×4, `2K12_KUB_SOV` ×2 |

- **Every infantry card rides in a carrier,** as stock fields each of these squads (no stock deck holds one bare): in
  the first play the bare engineers and scouts deployed on foot, while the motor rifles in their BMP-2s deployed
  loaded ✓ [[add-unit-to-deck]]. Each carrier is one stock pairs the squad with: the engineers in MT-LBs (the 2S12's
  tractor, in RJ's deck), the scouts in UAZ-469s (RJ's), the Metis teams in BMP-2s (the start adds'), the Konkurs-M
  teams in BTR-80s (their division's).
- **ATGM teams, with the best missile.** Two Konkurs-M teams in BTR-80s from the start, four more with the reserve.
  The team (`ATteam_KonkursM_TTsko_SOV`) fires the 9M113M (late), 23 AP at 2,625 GRU: the highest AT penetration of
  any Soviet ATGM infantry a Soviet division's rules field (every other is 20 AP or less). Its division, the 27th Guards
  Motor Rifle, fields it in a UAZ-469 or a BTR-80; the BTR-80 is the armoured one. AT infantry is a defence asset, as
  the reserve's are, but the smoke play asked for the start's two: they are in the deck from the deployment on, for
  the assault's flank or to dig into the village once it falls. A stock test re-derives the team and its carrier.
- **The T-80U is the obr. 1989** (`T80U_Obr89_SOV`), whose 9M119M Invar has 25 AP; the T-80U, the T-80UD and the
  T-80U command tank fire the 21 AP Refleks. No command variant has the Invar, so the reserve's command tank stays
  `T80U_CMD_SOV`. A stock test re-checks the AP.
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
| Division artillery | `2S7M_Malka_SOV` ×6, `BM27_Uragan_SOV` ×6 (no gun fires the strike, 5.6) | Not pre-placed: each fire creates its battery at GUN_SPAWN, the cut's north-west corner, in the player's allied camp, and removes it once the salvo has landed (5.4). Uncontrolled; they fire on order only. In the first play they stood pre-placed in the allied camp there and drove toward the front; created north of the cut in an enemy camp, they stood on its edge and the player's units killed them. |

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
  - The peak is about 90 of the player's units (what 14,000 to 17,000 points buy, the supply's 4 trucks and 2
    helicopters included, before losses), 20 left of battalion 1, and 52 of battalion 2: about 160, with a battery of
    up to 12 guns in the north-west corner for a fire's two minutes and a sweep's few fighters.
  - That is over Open Door's ~120 envelope. No play has gone that big yet ? [[script-and-battle-scale]].
  - All of it is packed into the 216 × 378 px cut. The density is the point: one concentrated battle.
  - If frame rate suffers, or the columns jam, the knob comes down.

### 6.5 Balance

A smoke play of the first play's fixes found NATO still well ahead. The rule since:
- **The assault:** the start's points at least 3:1 over the garrison by value, the attacker's rule.
- **Each battalion:** on Easy and Medium, the points the player has been given by the time the battalion is all in at
  least its value: battalion 1 once its last wave is created, battalion 2 once it appears (never before that). Hard
  may sit lower. The division's fires and the strike come on top.

A unit's value is its deck cost in the game's unit database (a transport card costs its squad and its carrier). The
points given are the start, the grant and one income tick a minute after the fall, the income's period
[[scripted-economy]]; losses are not counted. The stock test `test_twin_strike_forces.Balance` holds the rule.

| Phase: NATO | NATO units, value | Points counted at | Before (2,000 / 4,000 / 250) | Now (3,000 / 8,000 / 500) |
|---|---|---|---|---|
| 1: the garrison | 14, 945 | the start | 2.12 | 3.17 |
| 3, Easy: battalion 1, 2 teams | 47, 8,480 | the fall + 5:00 | 0.85 | 1.59 |
| 3, Medium: 3 teams | 67, 12,310 | the fall + 6:00 | 0.61 | 1.14 |
| 3, Hard: 4 teams | 86, 15,990 | the fall + 7:00 | 0.48 | 0.91 |
| 4: battalion 2, every level | 52, 9,335 | the fall + 5:20 to 7:20 | 0.78 to 0.83 | 1.45 to 1.55 |

- **The reserve** is worth more than the fall's points buy: with RJ's three unlocked types, 11,590 against the 11,000
  the grant and Medium's income bring by battalion 1's last wave. It holds 54 units (37 before), the deck at the start
  122 (120).
- **The knobs.** The economy's constants (4.3) are the player's side. Difficulty (5.7) and the scale knob (6.4) move
  NATO alone, so lowering either only raises the ratios.

## 7. Presentation

- **Hints and dialogs:**
  - a start hint names the village;
  - every phase change has a hint;
  - the fire-mission, fire-plan and release dialogs are two-button choices whose labels come from the in-game
    dictionary ✓ [[dialog-button-ingame-dictionary]].
- **Labels.** Objective labels are pinned to VILLAGE, the two boxes and ASSEMBLY.
- **Camera.** The deployment phase opens with a short camera move, where stock opens its deployment-phase Operations:
  right after LoadingDone, before the HUD returns ◐ [[start-camera-before-loading-done]].
  - `TS_Open`, three keys in 8 s, easing in and out, Escape skips it: from 720,000 world units above the ground over
    the cut's north-east, looking south-south-west at its middle (an operational view of the whole cut), down and
    west, turning south, to the playable view.
  - `TS_Start`, its last key, snapped after it, so a skipped move ends there too: 400,000 up, 40 degrees down, facing
    south, centred on (105, 245) px, where the layout's own deployment camera centres its view: the Soviet box near,
    the village beyond.
  - Eleven of stock's twelve deployment-phase Operations hand the camera over 312,898 to 604,542 up, 34.7 to 40
    degrees down, and its start cameras stand 376,057 up or more; the camera gate holds every key above that, every
    eye over the map and the last view inside the cut.
  - v0.1 snapped a one-key path over the village before LoadingDone instead. The deployment phase's start lost it, and
    the camera sat on the ground [[2026-11-11-twin-strike-opening-camera]].
  - `TS_Strike`, the strike's shot (5.6): one key over ASSEMBLY, flown from the player's camera in 4 s and held 11 s
    ◐ [[camera-shot-from-current-position]]; the camera gate holds it too.
- **Text.** English. Simplified Chinese is a later build; the toolkit's glyph gate is ready for it.
- **The Operations menu** takes stock's form: a briefing dated July 1989 in four numbered points, the forces line, the
  background and the outcome texts, at stock's lengths. Its emblems are RedJuggernaut's (the 79th Guards Tank
  Division's star, flag and Guards badge); its map picture is still Survivors'.
- **Screenshots** for the README: the assault on the village under fire, the counter-attack's columns on the tactical
  map, the strike over ASSEMBLY, and the end screen.

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
| The nuke effect does not play from a script | No cloud | Answered: a direct launch crashes; the script's own wrapper plays it (fxprobe). Fallback: the mega bombs and the 203 mm barrage massed, as the first build did |
| Penetration leaves no wrecks or fails at load | Units vanish | Vanished ✓, under the cloud |
| A Soviet player camp breaks the clone | Twin Strike cannot be Soviet | Re-clone from a Soviet-player stock challenge. That is a new `Template`, and the largest cost. |
| Battle size: about 160 at the peak, 35–40 min | Frame rate, script load | The scale knob; shorter phases |
| The cut's AI grid fails at load, as a whole-map grid under a smaller zone once did | The Operation does not load | Play the stock layout's whole 432 × 622 px zone, whose files ship as they are. The grid subset is the shape probe 1 played on Geisa ✓ [[ai-grid-tiles-playable-zone]]. |
| Two battalions and the player's force in a 216 × 378 px box | Columns jam; frame rate | The scale knob; stagger the waves |
| Transport cards (infantry in BMPs) | Infantry cannot be bought mounted | Separate infantry and vehicle cards |
| A pre-placed FOB in the player's camp, under a Soviet player | No FOB at the start | Create both by script at launch, with `CreateUnitOnPosition` ✓ [[spawn-and-create-units]] |
