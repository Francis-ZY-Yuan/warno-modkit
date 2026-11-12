---
id: 2026-11-11-fxprobe-play1
kind: play
build: d7ca595
game_version: 201602
mechanisms: [script-effects-self-contained, scripted-nuke-effect, changestress-damagetype-zero, soviet-player-camp, fog-switch, scripted-fires]
# every step ran, none crashed, and each step's question but F2, F7 and F10 got its answer; the slowdown is a cost
outcome: pass
symptom: The game became really slow after the black smoke, and slower through the last steps
cause: Black smoke at 4 tags beside the massed mega bombs and 203 mm impacts grew into huge plumes that lingered for minutes
result: The tactical-nuke impact effect plays from a script through the script's own wrapper; Twin Strike's strike launches it once, drops the black smoke and keeps a light accent of 18 launches
---
The strike-effects probe (`fxprobe`, build d7ca595), played once, with a Soviet player ([[soviet-player-camp]]) and 12
NATO targets at T. No crash. Step by step:
- F1: the targets did not show before the fog step.
- F2 (the camera look): not reported.
- F3, the fog switched off ([[fog-switch]]): the 12 targets showed, with nothing of the player's near them. Map-wide or
  local: not shown.
- F3b: the 3 BRDM-2s appeared west of T.
- F4, the massed effects: the mega bombs and 203 mm impacts showed as many scattered bursts and left craters. The black
  smoke grew into huge plumes over T that lingered for minutes, and the game became slow from there, worse through F8
  and F9 ([[script-effects-self-contained]]).
- F5: 4 of the 12 targets died (a TransferUnitToUnitGroup subgroup, then KillAllUnit Penetration; [[scripted-fires]]).
  Wrecks: hidden by the smoke.
- F6, ChangeStress Physical, Value 5: an M1A1(HA) and an M2A2 each showed 5 of 10 health segments
  ([[changestress-damagetype-zero]]).
- F7, ChangeStress Stun, 240: no visible sign on the unit panel or the icons; inconclusive.
- F8, the tactical-nuke impact effect through the script's wrapper with parPosition 0: a large nuclear fireball and dust
  cloud on T, not at the map's corner ([[scripted-nuke-effect]]).
- F9, the same with parPosition U's world position: the same, on U. The player: "big nuke effect".
- F8 and F9 killed nothing: 8 targets before and after.
- F10, the fog switched back on: not read.
