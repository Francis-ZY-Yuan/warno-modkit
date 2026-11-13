# Probes: small Operation mods that verify game mechanisms in play

A probe is a throwaway Operation built for one play session. Each of its beats exercises one mechanism a real mission
relies on, and announces itself with a hint naming its check, so what you see on screen can be matched to the
checklist below. The mechanisms the probes settled are recorded in the ops knowledge base
(`components/ops/knowledge/`), cited here by their record IDs in double brackets.

All six contents are clones of the stock challenge Survivors moved onto the stock map Geisa
(`modkit.ops.profile.SURVIVORS`, `modkit.ops.maps.GEISA`), built by the shared driver `modkit.ops.build` with every
gate, from the blocks in `modkit.ops.shapes` and `modkit.ops.bricks`.

| `--content` | Scenario, mod folder | What it is |
|---|---|---|
| `empty` | `challenge_OpenDoor`, `OpenDoorOps` | The smallest clone: one tank holds a point for 10 minutes |
| `spike` | `challenge_OpenDoor`, `OpenDoorOps` | Probe 1: 11 checks in one launch |
| `spike_safe` | `challenge_OpenDoor`, `OpenDoorOps` | Probe 1 without the shapes no stock file uses (install one or the other) |
| `spike2` | `challenge_OpenDoorTest`, `OpenDoorTest` | Probe 2: capture, objectives, endings; three short runs |
| `nuke` | `challenge_OpenDoorNuke`, `OpenDoorNuke` | Probe 3: a scripted strike's look on two groups of tanks |
| `nuke_sov` | `challenge_OpenDoorNukeSov`, `OpenDoorNukeSov` | Probe 3 again, with a Soviet player and NATO victims |
| `fxprobe` | `challenge_OpenDoorFx`, `OpenDoorFx` | Every strike effect at once: camera, fog, massed effects, kill, damage, stun, the real nuke |

`empty`, `spike` and `spike_safe` share one identity: install one at a time. `spike2`, `nuke`, `nuke_sov` and `fxprobe`
each have their own and install beside them. Every Operation active at once also needs its own menu order (`OrderToChainMission`)
[[content-identity-unique]]: `nuke`, `nuke_sov` and `fxprobe` hold their derived orders
(`modkit.ops.leveldesign.derived_menu_order`, a hash of the scenario GUID), but `empty`, `spike`, `spike_safe` and
`spike2` keep Open Door's 1001, as regression baselines whose builds never change. Have only one of those four, or Open
Door, active at a time.

## Build

```
python build.py --content {empty,spike,spike_safe,spike2,nuke,nuke_sov,fxprobe} [--out DIR]
```

`DIR` defaults to `probes/<content>` in the build folder: `build/` beside your `modkit.local.toml` (in the working
folder without one), unless its `build_dir` or `MODKIT_BUILD` names another (`modkit.core.paths.build_root`). The
output is the mod folder (`Config.ini`, `Gen/Version.ndf`, the scenario's `Definition`, `Details` and `Assets` packs),
`MANIFEST.tsv` (every packed entry and where it came from), `dumps/` (a typed dump of each generated file) and `od_overlay.png` (every item on Geisa's
Preview, for review). A failed gate prints one `FAILED:` line and exits 1. The build needs the stock extraction and
the game folder (`warno-setup`).

## What each probe verifies

### `empty`

That a Survivors clone, re-keyed to its own scenario id and GUID and moved to another map, loads and plays:
[[custom-operation-from-stock-parts]], [[operation-menu-registration]], [[gdscript-is-what-loads]],
[[content-identity-unique]], [[leveldesign-guid-binding]].

### `spike` (probe 1)

The start dialog (check 5) sets the scale of the 10:00 stress wave; every later hint names its check.

| Check | Time | Beat | Mechanisms |
|---|---|---|---|
| 1 | 0:05 | two objective markers on named points: is the pixel-to-world transform right? | [[objective-label-needs-position]], [[leveldesign-guid-binding]] |
| 2 | load, 1:00 | deck cards added at load, one with a transport; the A-10A card locked, then unlocked | [[add-unit-to-deck]], [[seteffect-never-finishes]] |
| 2 | deployment | deploy in the west zone with 3,000 points; units bought later arrive | [[deployment-phase-recipe]], [[arrival-end-in-zone]] |
| 3 | 2:00, 3:00 | a BMP column, then eight hidden tanks revealed by SpawnUnits | [[spawn-and-create-units]] |
| 4, 11 | 0:30, 1:30 | a T-80 company by road with a losses counter; a recon probe on a forest track to a ring | [[fast-move-and-attack-keeps-roads]], [[objective-counters]], [[detector-circles-only]] |
| 5 | 0:00 | the two-button dialog, its labels stock INGAME tokens | [[dialog-button-ingame-dictionary]] |
| 6 | 5:00, 6:00 | an artillery barrage on a box, then a scripted strike that kills half the units caught and stuns the rest | [[scripted-fires]], [[changestress-damagetype-zero]] |
| 7 | 7:00 | a helicopter carrying infantry to a landing zone | [[helicopter-boarding]] |
| 8 | 10:00 | the stress wave at the chosen scale: note the frame rate | [[script-and-battle-scale]] |
| 9 | 0:20 | AI-camp decoys emptied of ammunition and immobilised | [[weapons-jammed-effect]], [[seteffect-never-finishes]] |
| 10 | 8:00 | helicopters revealed, a SEAD card, a fuel-starved air defence | [[add-unit-to-deck]], [[spawn-and-create-units]] |

Every beat that creates enemy units ends with a SetEffect that reveals them, run beside the rest of the beat:
[[seteffect-never-finishes]], [[script-container-semantics]].

### `spike2` (probe 2)

The start dialog picks the run: ALL (the full test, ended at 15:00 by the end dialog) or FAST (the ending race 30 s
after the answer). Run A: Medium, ALL, VICTORY!. Run B: Easy, FAST. Run C: Hard, FAST.

| Time | Beat | Mechanisms |
|---|---|---|
| load | a transport card and an experience-0 card; four command zones forced to the player | [[add-unit-to-deck]], [[count-race-forced-owner]] |
| load | the defeat guard: lose every unit and the test ends | [[objective-waits-until-resolved]], [[mission-ends-only-by-script]] |
| 0:00 | the start dialog, and the ending race on quick runs | [[mission-ends-only-by-script]] |
| 0:05 | the difficulty the script reads | [[difficulty-branches]] |
| 0:10 | objectives that complete, fail and chain; a bonus objective | [[objective-waits-until-resolved]], [[objective-counters]] |
| 0:15 | kill counters on parked groups | [[kill-counts-by-type]], [[objective-counters]] |
| 1:00 | a command tank seizes a town; another is killed mid-capture | [[zone-capture-command-units]], [[zone-lookup-by-point]] |
| 2:00 | the count race: held 20 s, the script hands a zone over | [[count-race-forced-owner]] |
| 3:00 | removal by KillAllUnit, read as losses and kills | [[vanished-removal]], [[kill-counts-by-type]] |
| 5:00 | a dialog asked again until answered | [[dialog-reask-loop]] |
| 8:00 | two companies by road through a passage | [[fast-move-and-attack-keeps-roads]], [[detector-circles-only]] |
| 15:00 | the end dialog: the battle ends as chosen | [[mission-ends-only-by-script]] |

The plays and what they found are the trials `2026-11-03-probe1-*` and `2026-11-06-probe2-play-run-a`.

### `nuke` and `nuke_sov` (probe 3)

One short launch shows how a scripted strike looks with effects a script can launch, and whether a clone of Survivors
can have a Soviet player ([[soviet-player-camp]]). The first play crashed the game at the effect steps, which then
launched the tactical-nuke impact effects: those are parameterised, and a script launch cannot bind them
([[scripted-nuke-effect]], trial [[2026-11-10-probe3-play1-effect-crash]]). The steps now launch self-contained effects
only, which the build's script-effects gate holds ([[script-effects-self-contained]]). The steps run on the clock of
LoadingDone, so nothing needs deploying and nobody needs to launch the battle; just look at the victims' pins on the map.
The victims are two groups of five, A and B, about 600 m apart on open fields east of the deployment zone, each pinned
by a map objective. Nothing orders them. Each step shows a hint naming it.

| Step | Time | What happens |
|---|---|---|
| N1 | 0:20 | the victims appear at A and B |
| N2 | 0:40 | the script-only mega bomb `fx_HE_Mega_Bomb_ForScript` on A (no stock scenario launches it); 3 s later every victim within 300 m of A is killed with Penetration |
| N3 | 1:10 | the 203 mm barrage `fx_HE_Artillery_203mm_ForScript_RandomPosition` and the black smoke `fx_FumeeNoire_ForScript_RandomPosition` together on B (both stock-launched); 3 s later every victim within 300 m of B is removed with Vanished |
| N4 | 1:40 | "Probe done: answer the play sheet" |

`nuke_sov` adds four steps to test the links a Soviet-player Operation leans on, and N4 moves to 2:10 so no hint
panel (15 s) overlaps another:

| Step | Time | What happens |
|---|---|---|
| N0 | load | deck cards: a `MotRifles_SOV` card in a `BMP_2_SOV` (Transporter set), a `T80U_SOV` card locked ([[add-unit-to-deck]]), and the Soviet player's supply, `Ural_4320_SOV` ×4 and `Mi_8TZ_SOV` ×2 (`modkit.ops.profile.SOVIET_PLAYER_SUPPLY`: RJ's deck has none to buy [[soviet-player-camp]]); the deployment hint names them |
| N1b | 0:25 | the stock script-only effect `fx_HE_Artillery_203mm_ForScript_RandomPosition` alone near A, to compare with N3's barrage and smoke |
| N5 | 1:30 | two `2S7M_Malka_SOV` in the player's ally camp appear at the west edge and ShootOnPosition on an empty spot south of A (about 22,500 GRU, inside the gun's 7,000 to 35,000) |
| N6 | 1:50 | the T-80U lock is lifted; hint "N6: T-80U unlocked, check the buy menu" |

In `nuke` the player stays NATO and the victims are five T-80BV in each group (PACT). In `nuke_sov` the player's camp
is REDFOR/PACT on `OP_BASE_RJ_Player`, the other Alliance 0 camp is PACT, the two Alliance 1 camps are BLUFOR/NATO, and
the victims are five M1A1HA Abrams in each group (NATO). Install one at a time or both: each has its own identity.

Play sheet, for both contents:
1. Did the game get past N2 and N3, or did it crash at either?
2. How big was each look against the five tanks: N2's mega bomb, and N3's barrage with black smoke?
3. Did either have a sound?
4. After N2, did Penetration leave wrecks?
5. Which look reads as the strike?

For `nuke_sov` also:
6. Did the menu and the briefing show the player as Soviet?
7. Were the deployment buy menu's cards Soviet, and could you buy and deploy them?
8. Did the victims show as enemies?
9. During deployment, did a BMP-2 card show with riflemen in it? Could you buy it, and did it arrive mounted?
10. Was the T-80U card visible but locked before N6, and buyable after?
11. At N5, did the 2S7M shells land on the spot?
12. At N1b, how did the 203 mm effect alone look beside N3's barrage with smoke?
13. Were the supply trucks (Ural-4320) and supply helicopters (Mi-8TZ) in the buy menu, and could they deliver supply
    to your units?

### `fxprobe` (strike effects)

One launch tries every way a script can make a strike look massive and visible, on one target group, so the player
sees each in turn. The player is Soviet, as in `nuke_sov` ([[soviet-player-camp]]); the targets are NATO. Every step
runs on the battle clock: its hint shows 5 s before it acts and names it, and the riskiest steps come last, so a crash
points at the step its hint named. Each step is its own branch. The probe's camera paths file is Geisa's stock one,
shipped as is; the build's `camera-looks` gate holds the look to it (`modkit.ops.maps.check_camera_looks`).

The real nuke (F8, F9) is the game's tactical-nuke impact effect, which crashed a direct script launch
([[scripted-nuke-effect]]). Here the script exports its own wrapper (`modkit.ops.bricks.fx_wrapper`): a
TSimultaneousAction whose TActionCall binds all four of the effect's parameters, the shape of stock's script-launched
`fx_FumeeNoire_ForScript_RandomPosition`, whose TActionCall binds the one parameter its effect has no default for.
The launch names the wrapper's export path. The script-effects gate holds each such call to bind every parameter its
effect declares with no default ([[script-effects-self-contained]]).

| Step | Time | What happens |
|---|---|---|
| F1 | 0:15 | 6 M1A1HA Abrams and 6 M2A2 Bradleys appear at T (pinned), off their camp's AI and without ammunition |
| F2 | 0:40 | the camera flies from your view to Geisa's stock path Camp1, over T, in 4 s (stock's mid-battle look, SigurdsStrike's MLRS); Escape skips |
| F3 | 1:05 | fog off: `TGDDescriptorFow` (the scenario API's fog switch; no stock script uses it) |
| F3b | 1:25 | 3 BRDM-2 of yours appear at V, 400 m west of T: vision if the fog stayed |
| F4 | 1:50 | the proven effects massed, at RedJuggernaut's scale: 10 `fx_HE_Mega_Bomb_ForScript` (T and a ring of 9 at 300 m), the 203 mm random barrage 10 times at 5 tags (50), white and black smoke at 4 tags |
| F5 | 2:20 | 40 % of the targets (4 of 12) move to a subgroup (TransferUnitToUnitGroup) and are killed with Penetration |
| F6 | 2:45 | the survivors take ChangeStress with DamageType Physical, 5 of their 10 hit points |
| F7 | 3:10 | the survivors take ChangeStress with DamageType Stun, 240 ([[changestress-damagetype-zero]]) |
| F8 | 3:40 | the nuke wrapper with parPosition 0, on T |
| F9 | 4:10 | the nuke wrapper with parPosition U's world position, on U (595 m east of T) |
| F10 | 4:45 | fog back on; "probe done" |

**Install:** `OpenDoorFx` beside the other mods; it has its own identity and menu order. **Where to deploy:** one cheap
unit west of the central forest, nothing east of it, then launch the battle. Your own units must not see T before F3.

Play sheet: for each step, report seen, not seen, or a crash after its hint.

| Step | Look at | Report |
|---|---|---|
| F1 | the pin T on the map | did the targets show before F3? (they should not) |
| F2 | the screen | did the camera fly to T on its own? did Escape skip it? |
| F3 | T, before F3b | did the 12 targets show with nothing of yours near? did other NATO units show anywhere? |
| F3b | west of T | did the BRDM-2s appear? |
| F4 | T and around | how big, against the 12 vehicles and against the ring of pins? sound? camera shake? a hitch? |
| F5 | T | did 4 die? wrecks, or nothing? |
| F6 | the survivors' health bars | did they lose about half, or die, or nothing? |
| F7 | the survivors | stunned (icons, no movement), or nothing? |
| F8 | T, and the map's north-west corner | a crash right after the hint? where did it show: on T, at the corner, nowhere? a mushroom? how big? |
| F9 | U | the same questions; which of F8 and F9 sat on its pin? |
| F10 | the map | did the fog come back? |

The first play is recorded as [[2026-11-11-fxprobe-play1]] (build d7ca595): no crash; the nuke played on its tag through
the wrapper both ways; ChangeStress Physical 5 took 5 of 10 hit points; the fog lifted; black smoke beside the massed
effects slowed the game. A next play is recorded the same way: `YYYY-MM-DD-fxprobe-play2`, kind `play`, the build's
commit, mechanisms `script-effects-self-contained`, `scripted-nuke-effect`, `changestress-damagetype-zero`,
`soviet-player-camp`, `fog-switch`; outcome and result from the sheet. Each step's answer goes to its record: F4, F8 and F9 to `scripted-nuke-effect`
(F5 answers its wrecks question), F6 and F7 to `changestress-damagetype-zero`.

## After a game update

The probes are records: nothing here changes unless a probe is meant to, so a rebuild after a library change should
write the same bytes as before (compare against a build kept from the last version). To
re-verify the mechanisms on a new game version:

1. Refresh the stock data: `python -m modkit.core.setup check` reports STALE after an update; re-run
   `python -m modkit.core.setup extract --into DIR` and `python -m modkit.core.ndfrules extract` (the `warno-setup`
   skill).
2. Rebuild each probe with `build.py`. Every gate runs against the new data: a shape, key, rule or unit the update
   removed fails the build with its gate's message, before anything is written.
3. If the bytes differ from before, read `MANIFEST.tsv` and `dumps/` to see what the new data changed.
4. Install the mod and play the checklist above (the `warno-probe-and-playtest` skill). Record what you see as a
   trial, and update each cited mechanism's `last_verified` (the `warno-record-finding` skill).

## Layout

- `build.py`: the command line (`modkit.ops.build.cli` over the probes' profile and `CONTENTS`)
- `probes/profile.py`: the profile and the identity the probes share
- `probes/geisa.py`: the named points on Geisa and the force rows the probes create, read from the tables they share
  with Open Door (`modkit.ops.maps.GEISA_POINTS`, `modkit.ops.forces.GEISA_SOVIET_ROWS`)
- `probes/empty.py`, `probes/spike.py`, `probes/spike2.py`, `probes/nuke.py`, `probes/fxprobe.py`: one module per
  probe (items, beats, script)
- `probes/<content>.strings.toml`: each probe's string table, one section per token and one key per language
  (`modkit.ops.strings.load`); spike_safe shares spike's, and nuke and nuke_sov have one each

The tests are `components/ops/tests/test_probes.py`, `test_probe_spike.py`, `test_probe_spike2.py` and `test_probe_nuke.py`.
