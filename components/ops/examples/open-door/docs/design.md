# Operation Open Door: mission design

Operation Open Door is a single-player WARNO Operation: NATO against a Soviet AI on the stock map Geisa, built from
stock parts only. This is its full design. The example in this folder builds the **playable core**: phases 1 to 4,
their primaries, two of the bonuses and the endings. Each section says what the core builds and what waits for a
later build; the code (`opendoor/op.py`) cites these sections as "design 5.4" and so on.

Mechanisms the design relies on are recorded in the ops knowledge base (`components/ops/knowledge/`), cited by their
record IDs in double brackets.

**Markers:** ✓ = a stock Operation uses this script command; ? = the engine binds it, but no stock Operation uses it
and no build of ours has proven it yet.

## 1. Intent

A single-player Operation for the Steam Workshop: a NATO player against a Soviet AI, on a stock map, using only
vanilla units and a "custom-ish" player deck.

**The story:** NATO learns that a major Soviet armoured push is coming down one axis. NATO fakes weakness, falls back,
lets the spearhead in, and then encircles it. The battles are big armour fights on both sides.

**The fun** is a gamble the player makes. You give ground convincingly enough that the Soviets commit: you bloody
their first echelon and make one more short stand at the necks on the way back. You keep their recon out of the
forests where your reserves wait, and you hold the far end of the trap while they pile in. Then you **choose the moment
to spring it**. Spring it early and the anvil is safe, but the catch is small. Wait and the catch is bigger, but the
anvil may break. The payoff: an M1A1HA company team swings south from the held north road, a hidden Leopard 2 company
bursts out of the southern forest, and an M1A1/Leopard 2 against T-80 fight follows at the closing necks.

**Setting:** the Fulda Gap, mid-July 1989, about three weeks into WARNO's war (which starts on 20 June 1989).
- **The story so far, in WARNO's canon:** on day 0 the Pact breaks through at Fulda and drives on Frankfurt; NATO holds
  at Bad Orb; NATO strikes back north of Hanau.
- **This mission's addition:** NATO's counteroffensive has since pushed back to the inner-German border and bitten off
  a small salient around Geisa, just inside the GDR. V Corps is worn out.
  - A worn brigade of the 8th Infantry Division (Mech) holds the salient. Its last company team forward plays the
    rearguard. A 3rd Armored Division tank company team (Team E, 2-32nd Armor) holds the anvil, and the 3rd AD's
    cavalry squadron screens the forests (section 6).
- **The Soviet counter-stroke** aims to retake Fulda: in contact, 8th Guards Army's rebuilt 39th Guards Motor Rifle
  Division; the fresh punch, the 5th Guards Tank Army, up from Belorussia with the second strategic echelon. It leads
  with a T-80BV tank division and holds a T-80U division back as its follow-on force.
- **NATO's plan:** prisoners and signals intelligence give V Corps the axis and the timing. V Corps gives up the
  exposed salient as if spent, lets the counter-stroke in, and cuts its spearhead off with reserves that have just
  arrived: a 3rd Armored Division tank company team and a reinforced Panzer company of the Bundeswehr 5. Panzerdivision.
- **Why the feint is believable now:** NATO's units really are tired, so the withdrawal looks forced; giving up
  captured GDR ground costs nothing politically; the reserves exist by now; and the Soviets want to believe NATO is
  spent. None of that holds on day 0.
- **Scale:** every counter carries its real echelon at the in-game counts, where one unit is one vehicle or squad. The
  trap closes on the lead tank division's **forward detachment**, a reinforced T-80BV battalion racing through the gap
  for a deep objective; the rest of the division is still east of the necks. NATO's counter-stroke is a reinforced
  battalion-level ambush: company teams, an air cavalry platoon and an attack helicopter company. The budget stays
  inside the stock Operations' envelope, and a scale knob (6.4) moves it.

## 2. Goals, non-goals, anti-goals

- **Goals**
  - The trap is the player's doing: when to yield, how long to hold, when to spring it.
  - Big, readable armour set pieces: the first-echelon assault, the T-80 flood into the sack, the hammer reveal, the
    fight at the necks.
  - It installs from a plain Workshop subscription and stays **scenario-only**. One engine rule remains: an Operation
    relaunches without mods whenever a *Gameplay* mod is active, which turns Open Door off too
    [[gameplay-mod-relaunch]]. Players who run Gameplay mods must disable them first, and the Workshop page says so.
  - Replayable: three difficulties.
  - Every text in English and Simplified Chinese (section 7).
- **Non-goals:** multiplayer or co-op, playing as the Pact, new units, models, terrain or AI strategies, Army General,
  other languages, voice acting.
- **Anti-goals** (failure even if it technically works):
  - **A shooting gallery.** If the Soviets file into the sack in a single line and die, the trap is meaningless. Waves
    come on several lanes and threaten the anvil for real.
  - **A trap that springs itself.** If the script does all the clever parts on a timer, the player is a spectator.
  - **Unreadable failure.** Every rule that changes the outcome (held too long, anvil lost, breakout) is announced in a
    dialog when it fires.
  - **Bonus objectives that only add points.** Each bonus changes the battle that follows.
  - **A turkey shoot at the end.** The Apaches are earned and arrive while the necks are under attack (5.10).
  - **A Gameplay mod.** Shipping any of the 16 Gameplay files makes every Operation relaunch without mods. Open Door
    ships none (the build's package gate checks it).

## 3. Map and geometry

**Map: `_4x3_geisa`.** It is a 10vs10 skirmish map that no stock Operation uses, named for the GDR town opposite the
Fulda Gap, and it has the right shape. `docs/storyline-map.html` draws the storyline on it, phase by phase.

Read off the minimap, north up:
- The Soviets enter on the north and east edges into the open eastern belt (Town NE, Village E, Town SE). **PL BLUE**
  runs through those three.
- **Three main roads cross the forest belt west of PL BLUE**, top to bottom: the **north road** (y ≈ 255–280) between
  the north forest and the central forest; the **passage road** (y ≈ 400–410) between the central forest and the south
  lobe, narrowing to ≈ 20 px at the passage village; and the **defile**, the diagonal road between the south lobe and
  the big southern forest.
- **NATO holds the north road firmly.** A dug-in SHOULDER sits at its east mouth, held from deployment to the end, so
  the Soviets have **two lanes into the sack**: the passage (MID) and the defile (BOTTOM).
- **The necks:** NECK MID is the passage village, NECK S the defile village. Holding both cuts both lanes behind the
  spearhead.
- **The anvil sits far back, near the west edge.** The Soviets coming out of the passage and the defile cross the open
  west plain, the KILL ZONE, under long-range fire before they reach it. Its north end ties into the central forest, so
  the sack is closed on three sides once the necks shut.
- **Reserves:** the north jaw waits at RESERVE N, on the north road behind the shoulder, on NATO's own ground. The south
  jaw waits at HIDE S, in a road-free block of the southern forest, with a forest track to NECK S.
- **Forest routes:** four forest tracks lead from Soviet ground toward the reserves (north, central, south-west,
  south-east). Soviet recon probes use them, and the NATO screen holds a post on each (5.8).

Named positions, in minimap pixels (768 × 1024; one pixel is 2,560 world units). The nine below are fixed; the rest
are in `opendoor/map.py` and `opendoor/op.py`, each with its reason.
- Town NE (658, 232); Village E (700, 475); Town SE (645, 590).
- SHOULDER (520, 281); RESERVE N (352, 270).
- NECK MID (395, 402), with LZ MID just north of it (386, 382); NECK S (468, 600).
- HIDE S (522, 740).
- The anvil runs (200, 298) → (118, 318) → (138, 480) → Town SW (116, 655) → (98, 792).
- The kill zone is the open plain south of the central forest, between the lane exits (x ≈ 260–330) and the anvil
  (x ≈ 100–140).

| Zone | Role |
|---|---|
| ENTRY | Soviet spawn points on the north and east edges |
| PL BLUE | The bait line through Town NE, Village E and Town SE. The rearguard fights here, then yields it. |
| PL GREEN | The delay line through the two neck villages. The rearguard's survivors make a short stand there (5.1). |
| SACK / KILL ZONE | The passage and the defile plus the open plain between their exits and the anvil. Soviet vehicles here are counted. |
| ANVIL | The village line near the west edge, anchored on Town SW, that the player must not lose |
| SHOULDER | NATO's blocking position at the north road's east mouth |
| RESERVE N, HIDE S | The two jaws' assembly areas |
| NECK MID, NECK S | The two necks |
| LZ MID | The air-assault landing zone just north of the passage village (5.3) |
| SCREEN POSTS, TRIP-WIRES, RINGS | The counter-recon screen's posts, warning zones and exposure zones (5.8) |
| STRIKE BOXES | Named target areas for scripted fires (5.6) |
| POCKET | Everything west of the necks and east of the anvil, once both necks are held |
| REAR EXIT | The west edge behind the anvil. Soviets reaching it means the breakthrough succeeded. |

**The playable core builds:** deployment zones on the three towns (each its command zone minus a west strip), on
SHOULDER and on the anvil; command zones on the towns, the necks, the anvil's north and centre and Town SW; the sack's
five counting circles, the two approach circles and the rear exit's circle; the tags the waves and companies drive to.
The playable zone, the AI grid and the camera paths are Geisa's own, shipped byte for byte.

## 4. Mission flow (target 45–60 minutes)

| Phase | Rough time | What happens | Ends when |
|---|---|---|---|
| 0 Briefing | 0:00 | Briefing dialog. Corps intelligence has the counter-stroke's axis and timing; Corps gives up the salient as if spent: "We open the door." | Dialog done |
| 1 The Screen | deploy + 0–12 | A deployment phase ✓ [[deployment-phase-recipe]]. You deploy the rearguard on PL BLUE, the SHOULDER force, the forest screen and the anvil force. At H+1 the first echelon (a worn motor rifle battalion with a tank company) attacks on three lanes. **Objective:** sell the retreat. Bleed the first echelon, then fall back through the passage and the defile toward the anvil, with one short stand at PL GREEN. | PL BLUE in Soviet hands, or H+12 |
| 2 The Sack | ~12–28 | The rearguard's stand at PL GREEN, then the break for the anvil. The lead division's forward detachment floods down the passage and the defile and out across the kill zone. The jaws stay hidden. | The player springs the trap (5.2), or the deadline |
| 3 Close the Door | ~25–35 | The codeword. The north jaw (an M1A1HA company team) swings south from RESERVE N through the central forest; the south jaw (a Leopard 2A4 company) drives out of HIDE S to the defile. The hammer cards unlock. **Objective:** seal NECK MID and NECK S. | Both necks sealed |
| 4 The Cauldron | ~35–55 | The pocket is sealed and reduced until it surrenders. In the full design a relief force attacks the necks from the north-east and SEAD and Apaches reduce the pocket (5.10). | The pocket surrenders (5.4) |
| End | | The grade from the catch (5.5) | |

**Defeat:** Soviet units hold an anvil zone, or Soviet vehicles reach the rear exit ("the breakthrough succeeds"), or
the player's whole force is destroyed.

**The playable core's timeline** (H = "Launch battle"):

| When | What | What the player sees |
|---|---|---|
| load | Start cards, the captured Soviet cards, the A-10A lock; every tier and anvil command zone forced to NATO; the difficulty | The deploy hint naming the T-80U, Ka-50 and TOS-1 cards |
| H+0:00 | Phase 1's hint; P1 (yield by H+12, a countdown pinned on Village E), B1, P2 | The objective panel |
| H+0:15 | The difficulty hint | A hint |
| H+0:30 | The captured T-80U revealed | A T-80U in NATO colours west of Village E |
| H+1:00 | The first echelon: three companies Seize Town NE, Village E and Town SE | Three attacks; B1 counts up |
| a town falls | Its command zone goes to the Pact; its reinforcement entry closes | The town turns red; a hint |
| all three fall, or H+12 | The release: P1 done, or failed with a dialog; B6 and the PL GREEN window open | "The door is open" |
| release +0:00 to +5:00 | Six waves, one a minute, alternating MID and BOTTOM | Columns on the roads |
| the window closes | Both necks' command zones go to the Pact | Necks red; reinforcements only at the anvil |
| sack ≥ S_min | P4 done; the spring dialog, asked again every 2 minutes | FIRE AT WILL / HOLD FIRE |
| FIRE AT WILL, H+30, or the anvil contested | The spring: codeword, jaws revealed, spring cards, the A-10A unlocked; P5 on each neck | Tanks at RESERVE N and HIDE S |
| a neck held 30 s | That neck goes back to NATO; its entry reopens | Neck blue; a hint |
| both sealed | P6 counts the pocket down to its surrender point | The panel |
| surrender, or seal + 15:00 | Counts read, the pocket removed, the CATCH row and the grade | Grade dialog; end screen |
| spring + 25:00, not sealed | The backstop: Corps ends the battle | Dialog; the Major screen |

### 4.1 Objectives

**The mission's aim** is the catch: trap the lead division's forward detachment and destroy or capture as much of it
as possible without losing the anvil. The grade measures it (5.5).

**Primary objectives** are the plan's steps. They appear one phase at a time (GereObjectif ✓ with `LabelComponent
'Primary'`), so the panel shows what the plan needs now. Only the anvil can lose the mission.

| # | Phase | Panel text | Done when | If it fails | Core |
|---|---|---|---|---|---|
| P1 | 1 | **SELL THE RETREAT**: fight on PL BLUE, then give it up by H+12 (a countdown) | the three towns fall | Still held at H+12: the main body is released anyway (5.1) | built |
| P2 | 1–end | **HOLD THE ANVIL**: at all costs | the end | the anvil lost, the rear exit reached, or the whole force lost: **defeat** | built |
| P3 | 1–3 | **HOLD THE SHOULDER** | the spring | the north road opens and RESERVE N is revealed early, under attack | later |
| P4 | 2 | **LET THEM IN**: Soviet vehicles in the sack, %1 / %2 | S_min reached; Corps asks to spring (5.2) | none; Corps springs it at the deadline | built |
| P5 | 3 | **SHUT THE DOOR**: seal NECK MID and NECK S (one row per neck) | both necks sealed (5.4) | none; it stays open until done | built |
| P6 | 4 | **REDUCE THE POCKET**: Soviet vehicles left in the pocket | the pocket surrenders (5.4) | none | built |
| P7 | 4 | **KEEP THE DOOR SHUT**: hold both necks against the relief | the end | a neck falls: the pocket reopens until it is retaken | later |

**Bonus objectives** (`LabelComponent 'Bonus'` ✓) are optional, and each one changes the fight that follows:

| # | Phase | Panel text | Done when | What it buys | Core |
|---|---|---|---|---|---|
| B1 | 1 | **MAKE THEM PAY**: destroy %1 / %2 first-echelon units before PL BLUE falls | the count is reached first | credibility: one more T-80BV company goes into the sack (5.9) | built; it buys nothing yet |
| B2 | 1 | **LET THEM BURN THE DECOYS**: %1 / 4 decoys destroyed while PL BLUE holds | 4 of the 8 decoys destroyed first | credibility (5.9) | later |
| B3 | 1–2 | **KEEP THE RESERVES HIDDEN** | the spring with neither reserve exposed | both jaws go in with no Soviet blocking force in their way (5.8) | later |
| B4 | 4 | **BLIND THE POCKET**: air-defence vehicles left in the pocket | the pocket's air defence is down to ≤ 1 | the Apache company comes at once, and a second follows (5.10) | later |
| B5 | 4 | **BREAK THE RELIEF**: destroy %1 / %2 relief tanks | the count is reached | the relief's last wave is called off | later |
| B6 | 2 | **MAKE A STAND AT PL GREEN**: hold a neck village with Soviets at its approach for %1 / %2 s | the time is reached before the PL GREEN window closes (5.1) | credibility (5.9) | built; it buys nothing yet |

The playable core's panel holds nine rows: P1, B1, P2, P4, B6, P5 ×2, P6 and THE CATCH (the grade row, 5.5).
The core keeps to probe 2's limits: at most ten objectives in a run, at most two numbers each.

## 5. Mechanics

### 5.1 The bait: yielding PL BLUE

- The Soviet main body is released when the Pact holds PL BLUE: "the door is open."
- **A town falls** when the Pact captures its command zone, or when a count race is held: three or more Soviet units
  and no NATO unit in it for 20 s [[count-race-forced-owner]]. Only command units capture a zone, and an enemy command
  unit inside makes it neutral [[zone-capture-command-units]], so the race decides the towns the first echelon cannot
  capture. The fallen town's command zone is then forced to the Pact.
- **Hold too long:** if the player still holds PL BLUE at H+12, the main body is released anyway, and the rest of the
  towns are forced to the Pact. P1 fails with a dialog. In the full design HIDE S also counts as exposed (5.8).
- **The rearguard falls back through the sack**, with one stand on the way: a fighting withdrawal that breaks twice.
- **The shoulder does not yield.** In the full design, if the Pact ever holds SHOULDER, the next Soviet wave takes the
  north road toward RESERVE N, which is revealed early under attack (P3).

**PL GREEN, the second stand.** Covering forces delay from successive positions. A rearguard that runs ≈ 8 km straight
back looks like a lure; one that breaks, stands again and breaks again looks beaten. The stand also shows the player
the necks before they have to close them.
- **The window** opens when PL BLUE falls. B6 appears with a hint: make one more stand at the necks, then break contact
  for the anvil.
- **The stand:** a timer counts the seconds a neck village holds player units while Soviet units are in that neck's
  approach. Both necks add to one timer. At the difficulty's time (2:00 on Medium) B6 is done.
- **The window closes** when B6 is done, when no player unit is left in either neck after the first contact, 8
  minutes after the release, or at the spring. Whatever closes it hands both necks' command zones to the Pact, so
  reinforcements arrive only at the anvil until a neck is sealed again.
- **No failure rule.** Standing longer earns nothing more; the hint says so.

**Reinforcement tiers.** Units bought after the launch arrive along reinforcement entries, and an entry belongs to the
side that owns the zone its End lies in [[arrival-end-in-zone]]. The core uses that to move the player's arrivals back
as the lines fall: one entry per PL BLUE town (the east tier) and one per neck (the neck tier) end in their town's or
neck's command zone, forced to NATO at load; Geisa's own west-edge entries end in the anvil's deployment zone and stay
NATO's all battle. A town's fall closes its entry, the PL GREEN close closes the necks', and a seal reopens its neck's.
The game shows nothing when an entry opens or closes, so each change has a hint. A fallback mode ("fixed") gives each
entry a small deployment zone of its own, so all stay open.

### 5.2 Springing the trap: the player's call

- Once at least **S_min** Soviet vehicles are in the sack (counted in its five circles [[detector-circles-only]]),
  Corps asks: **spring the trap now?** The multiple-choice dialog ✓ has two stock buttons, FIRE AT WILL (now) and HOLD
  FIRE (wait) [[dialog-button-ingame-dictionary]].
- HOLD FIRE asks again 2 minutes later [[dialog-reask-loop]].
- At H+30, or the moment a Soviet unit enters an anvil command zone, Corps springs it anyway and says so.
- **Early** means a small catch and a safe anvil. **Late** means a big catch, a stretched anvil, and the risk of
  defeat.

### 5.3 The hammer reveal

**Order of events:** the codeword dialog, then the jaws. In the full design an air assault lands first and cuts the
passage, and NATO's higher-echelon strikes land on their boxes as the jaws close (5.6).

**The armoured jaws** are pre-placed hidden units, revealed with SpawnUnits ✓ [[spawn-and-create-units]]. Until then
they are not on the map, so the player can't commit them early.
- **North jaw:** a 3rd Armored Division tank company team, an M1A1HA company with a Bradley platoon and an M1A1HA
  command tank. It waits at RESERVE N and swings south through the central forest on a forest track to NECK MID.
- **South jaw:** a reinforced Bundeswehr Panzer company: Leopard 2A4 with a Panzergrenadier platoon in Marders, a
  Gepard and a Luchs. It waits in HIDE S and comes out on the defile road just east of NECK S.
- **Cards:** AddUnitToDeck ✓ adds the hammer cards (M1A1HA, Leopard 2A4, OH-58D) [[add-unit-to-deck]], and the A-10A,
  locked since the start, unlocks.

**The air assault** (later): one lift from the 3rd AD's aviation brigade, UH-60A ×4 carrying air cavalry troopers under
an AH-64A pair, lands at LZ MID, seizes the passage village and blocks the passage road until the M1A1HA arrive.
Helicopters spawned loaded at an edge and unloaded at a point are what probe 1 tried [[helicopter-boarding]].

### 5.4 The cauldron

- **A neck is sealed** when NATO has units in its command zone and the Pact none for 30 s, the count race again. Its
  zone then goes back to NATO and its reinforcement entry reopens. A Soviet commander may still win it back.
- **The pocket is sealed** when both necks are. Its Soviet vehicles are counted then, and the pocket **surrenders** when
  it holds a share of that count or fewer (45 / 35 / 25 % by difficulty), or 15 minutes after the seal (out of fuel and
  ammunition), so the mission can't stall. Every Soviet unit left in the pocket is then removed (KillAllUnit,
  Vanished ✓) and counted as captured [[vanished-removal]]; every count is read before the removal.
- **The backstop:** if the pocket is not sealed 25 minutes after the spring, Corps ends the battle. The catch then
  counts only what was destroyed.
- **Later:** on sealing, the trapped Soviets break out toward the nearer neck, then fall back and hold; the pocket's fuel
  drops to 25 %; and a relief force (the follow-on division's forward detachment, a reinforced T-80U battalion) attacks
  the necks from the north-east behind an opening barrage (P7, B5). Units that leave through a lost neck count as
  escaped.

### 5.5 Score and grade

- The catch = main-body vehicles destroyed or captured, out of the main body's vehicles. The core counts the main body's
  60 vehicles still alive, and the captured are the Soviet vehicles in the pocket at the surrender (at most those
  alive).
- Grade:
  - **Total victory:** catch ≥ 70 % and both necks sealed;
  - **Major victory:** catch ≥ 40 %;
  - **Minor victory** otherwise. No stock screen exists for a minor win, so it shows the major one, with its own
    dialog.
- The script alone decides the ending: the game rules leave the engine's own endings off, and only the first
  TriggerEndGame of a battle counts [[mission-ends-only-by-script]]. Every ending goes through one funnel: each writer
  sets a variable once, and the funnel shows that ending's dialog, then the end screen.
- The bonuses don't enter the grade directly. They act through the catch.

### 5.6 Strategic fires (later)

Fires at army level and above that the player does not call, each on a named strike box and each announced first with
the box's label and a countdown. **Scripted fires open assaults:** the Soviet barrage opens the mission; NATO's
higher-echelon strikes come when the trap closes and again when NATO assaults the pocket; none fall during the sack.

| When | Who | Where | Effect |
|---|---|---|---|
| H-hour | Soviet front artillery | the PL BLUE towns | the barrage that opens the first echelon's assault |
| the spring | V Corps artillery and 4 ATAF air | the approaches east of the necks | bomb strikes that thin and stun the units following the spearhead |
| the spring | 4 ATAF air interdiction | the Town NE road junction | delays the relief |
| phase 4, the relief's first attack | Soviet army artillery | both necks | one barrage opening the relief's assault |
| phase 4, NATO's assault on the pocket | V Corps MLRS | the pocket's air defence | destroys a share and stuns the rest, so the Apaches can go in (5.10) |

Soviet shelling uses real rounds from a hidden corner battery (ShootOnPosition ✓); probe 1 played it
[[scripted-fires]]. NATO strikes are impact effects ✓ plus a scripted share destroyed and the rest stunned; a stun is
the only stress a script may apply [[changestress-damagetype-zero]].

### 5.7 Difficulty

ConditionOnGameDifficulty ✓ sets the difficulty's knobs at load [[difficulty-branches]]. The core writes Medium first
and lets the Easy and Hard branches overwrite it; if no difficulty reaches the script, it plays Medium and says so.

| Knob | Easy / Medium / Hard | Core |
|---|---|---|
| B1: kills before PL BLUE falls | 28 / 42 / 55 % of the first echelon (10 / 15 / 20 at 1×) | built |
| S_min: Soviet vehicles in the sack before Corps asks | 15 / 20 / 24 (0.25 / 0.33 / 0.40 of the main body's 60 vehicles) | built |
| B6: the PL GREEN stand | 1:30 / 2:00 / 2:30 of contact | built |
| the surrender share | 45 / 35 / 25 % | built |
| B2: decoys | 3 / 4 / 5 of 8 | later |
| B5: relief tanks | 35 / 50 / 65 % (11 / 16 / 20 at 1×) | later |
| recon probes | 2 / 3 / 4–5, a T-80 platoon in some on Hard | later |
| the pocket's air defence; the J-SEAD share | 4 / 6 / 8 vehicles; 50 / 35 / 25 % destroyed | later |
| the Apache company | 6 / 4 / 3 helicopters | later |

### 5.8 Counter-recon: forest probes (later)

Soviet divisions advance behind a reconnaissance screen; a company hidden 3 km off the axis is exactly what their recon
hunts. Probes of 3–6 recon units use the four forest tracks of section 3. The player's fourth deployment group, the
screen, holds a post astride each track: dismounted 3rd AD infantry on the north and central tracks, the south jaw's
dismounted Panzergrenadiere on the two southern ones, with 4-7th Cavalry's M3A1s and scouts as the eyes. A probe
entering a track's trip-wire triggers a radio warning. A probe unit that stays about 20 s in a reserve's ring exposes
that reserve, and a Soviet blocking force then takes post in the jaw's way. The rings switch off at the spring, so a
probe only slowed past the spring costs nothing.

### 5.9 The deception: credibility and decoys (later)

A defence that gives way without a fight looks like a trap; one that fights hard, takes losses and then breaks looks
real. **Credibility** is a 0–3 counter, one point each for B1, B2 and B6; any two bring the whole main body in. With
fewer, one or two T-80BV companies stay at the Town NE junction (they count in the main body's total but sit outside
the pocket, so the best catch drops) and join the relief in phase 4; at 0 one more recon probe goes into the forests.

**The decoys** are eight 8th ID M1 Abrams that couldn't be recovered, left in their positions on PL BLUE in an
AI-controlled NATO camp: real stock tanks given the game's own broken-tracks and weapons-jammed criticals, so the
Soviets shoot them like any other NATO tank. Probe 1 found that the weapons-jammed critical did not stop them firing
[[weapons-jammed-effect]], so the decoys need another way to stay silent.

### 5.10 Reducing the pocket: SEAD, then Apaches (later)

The pocket holds the main body's air defence (Tunguska, Strela-10, Osa); Apaches flown into it die. So the pocket is
blinded first: a scripted MLRS fire mission on its air defence, then F-4G Wild Weasel and EF-111 cards for the player
(anti-radar missiles only hit radar air defence, so the Strela-10s must die to guns). An AH-64A company then comes when
B4 is done, or at a deadline. The relief attacks the necks at the same time, so it is never a turkey shoot.

## 6. Forces and deck (all vanilla units)

Every unit name is a stock descriptor (`Descriptor_Unit_<name>`); the build's unit gate checks each one the op names
against the game's unit database, and the tests check the whole table. WARNO counts a squad and its carrier as two
units. Counts are the Medium intent at 1×.

**Formations:** the rearguard is the last company team of a worn 8th Infantry Division (Mech) brigade (M113s and M1
Abrams); the anvil is Team E, 2-32nd Armor (3rd AD); the screen is 3rd AD's 4-7th Cavalry; the north jaw is a 3rd AD
M1A1HA company team (the M1A1HA exists only in the 3rd AD); the south jaw is a reinforced 5. Panzerdivision Panzer
company (the Leopard 2A4 exists only in the 5. Pz).

### 6.1 Player deck

**Base: `OP_BASE_BB_Player`**, the 3rd Armored Division's operation deck: its tank company team (E-2-32nd Armored), its
battalion HQ and support, its cavalry troop (N-4-7th Cavalry) and two A-10A [AT]. The build swaps it in for
Survivors' player deck, and the script reshapes it at run time:

| When | Script | Cards | Core |
|---|---|---|---|
| start | AddUnitToDeck, Experience 0 (worn) | the 8th ID rearguard: `M1_Abrams_US` ×6; `Rifles_US` ×6 in `M113A3_US`; `M901_TOW_US` ×3; `M113_Dragon_US` ×2; `AH1F_Cobra_US` ×2 | built |
| start | AddUnitToDeck | the shoulder and the anvil: `ATteam_TOW2_US` ×4; `Engineers_Dragon_US` ×2 | built |
| start | AddUnitToDeck | the screen's forest infantry: `Rifles_half_Dragon_US` ×6; `Engineers_Flash_US` ×2; `Panzergrenadier_IFV_RFA` ×6; `ATteam_Milan_2_RFA` ×2 | built |
| start | AddUnitToDeck | captured Soviet equipment: `T80U_SOV` ×2; `Ka_50_SOV` ×2; `TOS1_Buratino_SOV` ×2 | built |
| start | LockDeckUnit | the A-10A [AT] (the air corridor isn't open yet) | built |
| the spring | unlock + AddUnitToDeck | the A-10A [AT]; `M1A1HA_Abrams_US` ×4; `Leopard_2A4_RFA` ×4; `OH58D_Kiowa_Warrior_US` ×2 | built |
| pocket sealed | AddUnitToDeck | `F4_Wild_Weasel_US` ×3; `EF111_Raven_US` ×1 | later |
| Apaches in | AddUnitToDeck | `AH64_Apache_US` ×2 | later |

- **The captured Soviet cards** are hard to miss: no NATO look-alike, none in the Soviet waves, all self-propelled. The
  buy menu opens in Groups mode, so the deploy hint names them by unit and count, and the core lets the player switch
  the menu to the factory tabs (Tanks, Helis, Art). As a backup, a captured T-80U already in NATO's hands appears west
  of Village E at H+0:30.
- **The player deploys four groups from this one deck:** the rearguard on PL BLUE, the shoulder, the screen and the
  anvil. Deployment zones, not the deck, decide where each card goes.

### 6.2 Scripted NATO units (not in the deck)

| Group | Units | How it arrives | Core |
|---|---|---|---|
| North jaw | `M1A1HA_Abrams_US` ×10; `M1A1HA_Abrams_CMD_US` ×1; `M2A2_Bradley_IFV_US` ×4 carrying `Rifles_half_AT4_US` ×4; `M3A1_Bradley_CFV_US` ×2; `M163_PIVADS_US` ×1; `M981_FISTV_US` ×1 | revealed at RESERVE N on the spring | built |
| South jaw | `Leopard_2A4_RFA` ×7; `Leopard_2A4_CMD_RFA` ×1; `Marder_1A2_RFA` ×3 carrying `Panzergrenadier_IFV_RFA` ×3; `Gepard_1A2_RFA` ×1; `Luchs_A1_RFA` ×1 | revealed in HIDE S on the spring | built |
| Captured T-80U | `T80U_SOV` ×1 | revealed west of Village E at H+0:30 | built |
| Decoys | `M1_Abrams_US` ×8, in the AI-controlled camp `Decoys` | created at start | later |
| Air assault | `UH60A_Black_Hawk_US` ×4 carrying `AeroRifles_US` ×4; `AH64_Apache_emp1_US` ×2 | revealed at the north edge on the codeword | later |
| Apaches | `AH64_Apache_emp1_US`: one company, plus a second if B4 is done | revealed at the west edge | later |
| Strike fallback | `M270_MLRS_cluster_US` ×2, hidden | only if the scripted strike effect fails | later |

### 6.3 Soviet forces (all scripted spawns)

CreateUnitOnPosition ✓ [[spawn-and-create-units]]. Spawns aren't limited by decks, and no operation deck carries the
T-80U, so scripting is the only route.

| Wave | Formation | Units | ≈ | Core |
|---|---|---|---|---|
| First echelon | a worn 39th GMRD motor rifle battalion (−) with a tank company, in three company groups | `T80B_SOV` ×10; `BMP_2_SOV` ×8 + `MotRifles_SOV` ×8; `BMP_1_CMD_SOV` ×1; `BRDM_2_SOV` ×2; `BRDM_2_Konkurs_SOV` ×2; `Scout_SOV` ×2; `ZSU_23_Shilka_SOV` ×2; `BRDM_Strela_1_SOV` ×1 | 36 | built: three companies, one per lane, that Seize their towns |
| Main body | the lead tank division's forward detachment, a reinforced T-80BV battalion | `T80BV_SOV` ×30 + `T80BV_CMD_SOV` ×1; `BMP_2_SOV` ×10 + `MotRifles_SOV` ×9; `BRDM_2_Konkurs_SOV` ×3; `2S3M_Akatsiya_SOV` ×6; `BMP_1_CMD_SOV` ×1; `MTLB_supply_SOV` ×3 | 63 | built: six waves on two lanes |
| ↳ its air defence | | `Tunguska_2K22_SOV` ×2, `Osa_9K33M3_SOV` ×2, `MTLB_Strela10_SOV` ×2 | 6 | built, in the fifth wave |
| Opener battery | 8th Guards Army artillery, in a hidden corner | `BM27_Uragan_SOV` ×2, `2S3M_Akatsiya_SOV` ×4 | 6 | later |
| Recon probes | the lead division's recon battalion and recon companies | each probe: `BRM_1_SOV`, `BRDM_2_SOV`, `Scout_SOV`; on Hard some add `T80BV_SOV` ×3 | 15–25 | later |
| Relief | the follow-on tank division's forward detachment, a reinforced T-80U battalion | `T80U_SOV` ×30 + `T80U_CMD_SOV` ×1; `BMP_2_SOV` ×10 + `MotRifles_SOV` ×9; `Tunguska_2K22_SOV` ×3; `MTLB_Strela10_SOV` ×2; `Mi_24V_AT_SOV` ×4 | 55–59 | later |

- **Movement:** the waves drive their lanes by waypoints with FastMoveAndAttack, which keeps to the roads and engages
  on sight [[fast-move-and-attack-keeps-roads]]; each leg is raced against a timeout so a stuck vehicle cannot hold its
  wave. Riflemen board their BMP-2s first, raced against 30 s. Both lanes end at the rear exit.
- **B1 counts kills by unit type** [[kill-counts-by-type]]: until the release the first echelon is the only Soviet
  force on the map.
- **Budget:** ≈ 36 + 69 + 55–79 + 15–25 Soviet units at 1×, plus 6 hidden guns, with at most ~120 alive at once,
  inside the stock envelope.

### 6.4 Scale knob and thresholds

Moving an echelon's size is a table edit plus one replay:
- **Forces are tables** (`opendoor/forces.py`): one row per unit type, with its count at 1×, its spawn point and its
  echelon label. One `FORCE_SCALE` (1.0 at release) multiplies every row but the fixed ones, rounded per row. The
  Soviet groups the probes create too come from one shared table (`modkit.ops.forces.GEISA_SOVIET_ROWS`).
- **Thresholds are shares, not counts:** B1 of the first echelon, B5 of the relief's tanks, S_min, the rear exit and
  the grade bands of the main body, the surrender point of what was sealed in. The build turns each into a count.
  Counts that don't scale stay fixed (the decoys, the Apache sizes, the PL GREEN stand time).
- **The hidden jaws** are laid out by a formation helper around their point, so more units need no hand-placed
  positions.
- **What a resize still costs:** a replay. Lane capacity, the time to fill the sack, and the frame rate don't scale for
  free.

The strategic AI is not used: scripted waves keep the story on rails.

## 7. Presentation

- **Languages: English and Simplified Chinese.** WARNO has eight dictionary languages; the SC dictionaries get the
  Chinese text and the other seven the English, so no client ever sees a raw token. Everything the op shows is
  translated: the menu entry, dialogs, objectives and hints.
- **One string table** (`opendoor/strings.toml`) holds every token with its English and Chinese text side by side. A
  native reader should check the Chinese in game before release.
- **Chinese conventions,** taken from the game's own SC texts: zone code names stay in Latin capitals in both languages
  (PL BLUE, NECK MID, HIDE S), as the game keeps ALPHA and BRAVO; vehicle designations stay in Latin (T-80BV,
  M1A1HA); markup and %1/%2 placeholders are kept exactly; punctuation is full-width.
- **The build's string gate:** the SC dictionaries hold exactly the US key set; each key has the same placeholders and
  markup in both languages; every Chinese character appears in the stock SC dictionaries, so the Chinese client's font
  carries it (a character outside that set is reworded, and the table says so beside it); menu titles stay within 30
  UTF-16 units; a dialog takes no variables [[dialog-text-takes-no-variables]].
- **Hints:** every key result shows on the map (zone colours, units appearing) or in a hint, one hint at a time.
- **Later:** a Workshop page with a preview image of the storyline, the setting and phases in both languages, and at
  the top: disable all Gameplay mods before launching.

## 8. Build route

- The op is a clone of the stock challenge Survivors moved onto Geisa [[custom-operation-from-stock-parts]]: the
  Definition re-keyed to the op's own scenario id and GUID [[content-identity-unique]], Geisa's own playable zone, AI
  grid and camera paths shipped byte for byte, and a generated LevelDesign, zone files, GDScript and dictionaries
  [[gdscript-is-what-loads]]. `opendoor/profile.py` holds those settings; `modkit.ops.build` runs the build and every
  gate.
- The gates every Operation build runs (strings, canonical layout and stock shapes, the game's load-time property
  rules, bindings and references, arrivals and tiers, the mission's script rules, the dump diff, the package, the read
  back), plus Open Door's own: every unit in the game's unit database, no leftover template name in a re-keyed or
  generated file, and Geisa's AI grid and the zones and arrivals held to stock's layout rules, read from the shipped
  files.
- A Workshop release (later) ships the built mod folder with a stable item, a preview free of local paths, and a frozen
  file set.

## 9. The probes

Two throwaway probe Operations tested the mechanisms this design needs, one play session each, before the core was
built: see the probes example (`components/ops/examples/probes/`). What they settled shaped the core: the 3rd AD deck
swap and AddUnitToDeck with a transport; hidden reserves revealed with SpawnUnits; a multiple-choice dialog asked again
in a loop; zone capture by command units only, and the count race that decides the rest; kill counts by type;
KillAllUnit Vanished; road columns on FastMoveAndAttack; the end funnel and the total-victory screen; and the deployment
phase's arrival entries. What they left open stays "later" in this document.

## 10. Left to the builder

Exact zone polygons and lanes; wave composition and timings within the budgets above; S_min, T_hold and the grade
bands (tuned in play); the names of label and dialog tokens; the screen posts, trip-wires and ring sizes; probe
timings; the decoy positions; the credibility dialogs; the pocket's air-defence mix and the J-SEAD boxes; the Apache
holding point and deadline.

## 11. Risks

- **No precedent:** no Workshop item has shipped an Operation before.
- **Game updates:** each game update can silently break a scenario mod. Rebuild and re-check after each one.
- **A big map plus big waves:** the frame rate is untested at the full design's scale.
- **Translation:** a wrong military term reads badly to Chinese players. The glossary comes from the game's own SC
  texts, and a native reader should check the text in game.
- **Gameplay-mod users** must disable those mods by hand (section 2). Other mods' unit changes could also break the
  scripted spawns.
