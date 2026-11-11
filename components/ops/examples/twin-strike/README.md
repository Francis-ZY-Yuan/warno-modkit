# Operation Twin Strike: the showcase Operation

Early July 1989. A Soviet tank division's forward detachment must seize a road-junction village at the western edge of
Twin Cities, then hold it against two NATO blows, and decide whether to ask Front for one tactical nuclear strike on the
second. You play the Soviets.

> **v0 demo.** Twin Strike has been played once. The fixes from that play are built but not yet played:
> - transports for the infantry;
> - the battlegroup view of the buy menu;
> - hidden division guns;
> - garrison and wave orders;
> - the release dialog;
> - the economy;
> - NATO fighter sweeps.
>
> Known issues:
> - RedJuggernaut's stock cards still show in the buy menu beside the op's own (the op is getting its own deck).
> - The division's guns are created outside the playable area, which no stock scenario does, so a fire may not land.
>
> Tell us what you see: each play becomes a record in the knowledge base.

Twin Strike is the toolkit's showcase example: a clone of the stock challenge Survivors (`modkit.ops.profile.SURVIVORS`)
moved onto a cut of the stock map Twin Cities (`modkit.ops.maps.TWIN_CITIES`, `twinstrike.map.CUT`)
[[custom-operation-from-stock-parts]] [[ai-grid-tiles-playable-zone]], with the player's camp flipped to the stock
Soviet-player shape (`modkit.ops.profile.SOVIET_PLAYER_CAMP_ROWS`) [[soviet-player-camp]]. It uses vanilla units only
and ships no Gameplay file [[gameplay-mod-relaunch]]. Its design is `docs/design.md`.

| `--content` | Scenario, mod folder | What it is |
|---|---|---|
| `op` | `challenge_OperationTwinStrike`, `TwinStrike` | The whole op: five phases, the division's fires, the strike, three difficulties, three endings and three defeats |

It installs beside Open Door and the probes: each has its own scenario, GUID, mod folder and menu texts, and Twin
Strike its own menu order, `OrderToChainMission` derived from its scenario GUID
(`modkit.ops.leveldesign.derived_menu_order`) [[content-identity-unique]].

## The op

| Phase | What happens | Ends when |
|---|---|---|
| 0. Deploy | Buy and place the forward detachment in the north box (2,000 points, no income yet) | You launch the battle |
| 1. Assault | Take the village from its West German garrison, which holds it. Division guns offer a preparation fire on it. | The village falls: few of its defenders left and one of your command units inside. Lost at 20 min. |
| 2. Unlock | The division's reserve joins your deck, with 4,000 points and an income from then on; NATO's recon moves north | 2 min |
| 3. Counter-attack | A US armoured battalion comes up both lanes, its recon screen first, then company teams with their air defence, each attacking your units once in the village; NATO fighters sweep the boxes. Fire missions on BOX W or BOX C, and one division fire plan. | The battalion is broken, or 15 min on (its survivors break off) |
| 4. Surprise | A West German Panzer battalion appears at the assembly area: it attacks in 5:00. Front offers nuclear release. | The strike, or the countdown runs out |
| 5. Hold | Hold the village | 5 min after a strike; after withholding, until the second battalion is broken, up to 20 min |

You lose if NATO owns the village for 60 s, or none of your units is inside its zone for 3 min (from phase 2 on). A win is
Total (the village held, both battalions beaten: the first broken, the second destroyed or broken), Minor (held, but
you lost more than half of what you bought) or Major; the end dialog names it and whether the strike was released or
withheld. Difficulty moves the garrison's breaking point, the first battalion's company teams and the fire-mission
cooldown.

## Build

```
python build.py --content op [--out DIR]
```

`DIR` defaults to `twin-strike/op` in the build folder: `build/` beside your `modkit.local.toml` (in the working folder
without one), unless its `build_dir` or `MODKIT_BUILD` names another (`modkit.core.paths.build_root`). The output is the
mod folder (`TwinStrike/Config.ini`, `Gen/Version.ndf`, the scenario's `Definition`, `Details` and `Assets` packs),
`MANIFEST.tsv`, `dumps/` (a typed dump of each generated file) and `ts_overlay.png` (every item, the cut, the zones,
the circles and the arrivals on Twin Cities' Preview, for review). The build needs the stock extraction and the game
folder (the `warno-setup` skill). Nothing is read from either until a build runs: unconfigured, the build prints one
`FAILED:` line naming `warno-setup` and exits 1.

Every gate of `modkit.ops.build` runs before anything is written (the end funnel and the script-effects gate among
them), and every written pack is read back. Twin Strike adds six extra gates (`twinstrike/profile.py`):

| Gate | What it holds |
|---|---|
| `units` | every unit the generated files name is in the game's unit database |
| `no-template-name` | no re-keyed or generated file still names Survivors |
| `grid` | the shipped playable zone and AI grid are the cut's: 40 tiles of the layout's own grid (`CUT.gate()`) |
| `zone-layout` | the shipped zones and arrivals keep stock's layout rules |
| `menu-order` | its menu order is no stock Operation's |
| `fire-range` | each fire's battery is created at `TS_GunSpawn`, outside the cut, past the ground vision of every unit you can field, with every target inside each battery's range band (`modkit.ops.gates.check_fire_range`) |

The opening camera's paths file is held to the camera gate when the build plans it (`modkit.ops.maps.check_camera_paths`):
stock's key shape, the move then its last key, every eye over the map and at least 376,057 world units above the
ground (stock's lowest start camera), and the last view inside the cut.

A failed gate prints one `FAILED:` line and exits 1.

## Install and play

`python -m modkit.core.install build/twin-strike/op/TwinStrike --title "Operation Twin Strike"` packs the built mod
folder as a zip with a one-click `.cmd` installer, in `share/` in the build folder (the `warno-ship` skill). Run the
installer, switch every Gameplay mod off, and play one run with the play sheet below beside you. Record what you see as
a trial (the `warno-record-finding` skill).

**After the first Workshop upload,** set `WORKSHOP_ID` in `twinstrike/profile.py` to the new item's ID and commit. The
upload writes that ID into the installed `Config.ini` only, and every build writes `ID = 0`: without it, the next build
and reinstall reset the ID, and the next upload creates a second Workshop item instead of updating the first. (The share
installer also keeps an installed non-zero ID over a build's 0, and refuses a build with a different non-zero one.)

## Play sheet

Play one run on Medium. Answer each question with what the map shows; a number or a yes/no is enough. Every phase
announces itself with a hint, so what you see can be matched to the sheet. (The first play's answers are trial
`2026-11-11-twin-strike-play1`; this sheet is for the next.)

**Loading and the deploy screen**
1. Does the op load, past the deploy screen, with the map clipped to the cut: the village in the south-west, your
   deployment box north of it, nothing playable east of the valley?
2. Does the buy menu open on the BATTLEGROUP view, with the Ka-29s, the Ural and Mi-8TZ supply and the start cards in
   it without switching? Is the switch to the GROUPS view still there? Do the engineers and scouts come in their
   MT-LBs and UAZs?
3. Does the deploy screen open with a camera move of about 8 s, from high over the whole cut down to a view facing
   south, your deployment box in the near part of it and the village beyond? Does Escape skip straight to that view?
   Do you start with 2,000 points and no income?

**The guns** (no gun stands on the map: each fire's battery appears north of the cut, out of sight, and is removed)
4. Do you ever see a 2S7M or a BM-27 on the map or the minimap?
5. Does each ordered fire land where it was named, about 50 s after you answer: the village for the preparation fire,
   BOX W or BOX C for a fire mission, the fuller box for the fire plan? Does each battery fire one salvo and stop?

**Dialogs and hints**
6. Do the dialogs read right, and does each button do what the text says: the preparation fire (FIRE AT WILL / HOLD
   FIRE), the fire mission (ROCKET / ARTILLERY, then ALPHA / BRAVO), the fire plan, the release (Yes / No)?
7. Did you see each phase's hint: PHASE 1, the difficulty, the preparation fire's warning, "Village taken", PHASE 3,
   the first battalion broken (or breaking off), the second battalion, the release (granted or withheld), PHASE 5?
8. Are the labels where they belong: P1 and P2 on the village, BOX W and BOX C on their roads, the second battalion's
   countdown and STRIKE ZONE at the assembly area? Does B1's tanks-destroyed count match the Abrams you saw destroyed,
   by your units and by the guns?

**The battle**
9. AI pathing: do the first battalion's columns drive up the roads (the main road through BOX W; the east road through
   BOX C, then west across the stream) into the village, and once there keep attacking your units rather than stand?
   Does the garrison fight from the village (into the houses, or holding its ground)?
10. At the fall, did the village's zone turn yours, did 4,000 points arrive, and did the locked cards (Tunguska, Su-24M,
    Mi-24P) unlock and the reserve (T-80U, Ka-50, the two Kubs and the rest) appear in the buy menu?
11. The frame rate at the peak, when the second battalion appears with the first's survivors and your force on the
    map: smooth, or stuttering?

**The strike** (answer Yes to the release)
12. Did the release dialog show (after the fire plan too)? The lone 2S7M's round is ordered 20 s after the release's
    warning and aims for 30 s, so its shells should land on the zone after the strike: do you see them? How many?
13. Does the mega bomb at 0:30 read as the strike? How big is it against the battalion?
14. What does the kill leave: wrecks, or nothing?
15. Did the fires and the black smoke show across the zone, and for about a minute?

**The end**
16. Which ending was reached (the end dialog's first line and its last sentence), and on which difficulty?

**Supply**
17. Were the supply trucks (Ural-4320 ×4) and supply helicopters (Mi-8TZ ×2) in the buy menu from the start, and could
    they deliver supply to your units?

**The new pieces**
18. NATO fighters: did two F-15Cs come over BOX W about 2:30 into phase 3, and two over BOX C at 6:00? Did they leave
    once spent?
19. The empty-village warning: did it show only after your units had been out of the village's zone for 20 s, while P2
    counted the empty clock?

## What the op stands on

- The Soviet player: the stock camp shape and RedJuggernaut's deck, as probe 3's `nuke_sov` built it
  [[soviet-player-camp]].
- The deployment phase and its arrivals ending in the Soviet box: [[deployment-phase-recipe]], [[arrival-end-in-zone]].
- The garrison is pre-placed, standing from the start, and holds the village by stock's orders
  [[garrison-roe-and-hold]]; the second battalion and the fighters are pre-placed hidden and revealed:
  [[spawn-and-create-units]] [[scripted-air-sweep]]. The circles are detectors: [[detector-circles-only]].
- The economy: 2,000 points with no income, then 4,000 and an income at the fall [[scripted-economy]].
- The deck: AddUnitToDeck adds only what RedJuggernaut's deck lacks, and LockDeckUnit holds its defence types back
  until the village falls: [[add-unit-to-deck]]. It adds the Soviet player's supply too: the deck has no supply
  helicopter, and its supply trucks sit only in the tank battalions' groups [[soviet-player-camp]].
- The fall: a count in the village's circle and a command unit inside, then the zone forced to the player
  [[count-race-forced-owner]] [[zone-capture-command-units]].
- The waves and lanes: [[fast-move-and-attack-keeps-roads]], each ending with an Attack on your units
  [[wave-ends-with-attack]]; B1's count, battalion 1's tanks created less those alive: [[kill-counts-by-type]].
- The fires: ShootOnPosition from a battery created for each fire out of your sight and removed after
  [[scripted-fires]]; the dialogs [[dialog-reask-loop]] [[dialog-button-ingame-dictionary]].
- The strike: a self-contained script effect [[script-effects-self-contained]] (the nuke impact effects crash a script
  [[scripted-nuke-effect]]), then KillAllUnit on the units a circle detects.
- The endings: [[mission-ends-only-by-script]]; the difficulty: [[difficulty-branches]].
- The opening camera: after LoadingDone, a three-key move from high over the cut down to the Soviet box and the
  village, then a snap to its last key, as stock opens a deployment-phase Operation; a snap before LoadingDone, as v0.1
  shipped, left the camera on the ground [[start-camera-before-loading-done]].

## Layout

- `build.py`: the command line (`modkit.ops.build.cli` over Twin Strike's profile and `CONTENTS`)
- `twinstrike/profile.py`: the identity and the profile (Survivors on the cut, the Soviet-player camps, the re-keying,
  the extra gates, the review picture)
- `twinstrike/map.py`: the cut, the named places, the zones, the arrivals, the FOBs and the opening camera;
  `python -m twinstrike.map overlay OUT.png` draws them on Twin Cities' Preview
- `twinstrike/forces.py`: the player's deck (start cards, locks, reserve, command units), the force tables, the scale
  knob and the share thresholds
- `twinstrike/strings.py`: the string table, English only for now (the Chinese column holds the English text)
- `twinstrike/op.py`: the mission: its items, its beats (the five phases, the losses, the fires, the strike, the
  difficulty and the end funnel), its script (`modkit.ops.mission.script_frame`) and its content

The tests are `components/ops/tests/test_twin_strike_*.py`, with `twin_strike_support.py` (which holds a step model of
the script runtime that the mission tests drive).
