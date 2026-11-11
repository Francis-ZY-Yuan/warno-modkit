---
id: 2026-11-11-twin-strike-play1
kind: play
build: ded6b61
game_version: 201602
mechanisms: [soviet-player-camp, add-unit-to-deck, scripted-fires, garrison-roe-and-hold, wave-ends-with-attack, dialog-reask-loop, detector-circles-only, scripted-economy]
# the brief's outcome is "partial"; the schema's word for it is mixed
outcome: mixed
symptom: The division's guns drove toward the front and died; the release dialog never showed after the fire plan was fired
cause: Several, one per observation below; the guns' trigger is not settled from stock data
result: Each fire creates its battery out of sight north of the cut and removes it after (the fire-range gate holds the spot), the garrison and the waves get stock's orders, every re-ask flag is reset after its race and the release's wait is bounded, the empty-village count reads the command zone, and the economy is the modder's
---
Twin Strike's first play, built from ded6b61. The game loaded and the battle played through phase 4, with a Soviet
player in a clone of Survivors ([[soviet-player-camp]]). What was seen, each with its record:

- A transport card added by AddUnitToDeck (motor rifles in their BMP-2s) was bought and deployed loaded
  ([[add-unit-to-deck]]); the infantry cards added with no carrier deployed on foot.
- The cards the script adds show only in the buy menu's battlegroup view; the menu opened on the groups view
  ([[add-unit-to-deck]]).
- The division's guns, pre-placed in the allied camp, emptied with SetAmmo at load and refilled for each
  ShootOnPosition, drove toward the front and died ([[scripted-fires]]).
- The garrison stood idle in the village ([[garrison-roe-and-hold]]).
- A NATO wave stopped at its last waypoint ([[wave-ends-with-attack]]).
- The release dialog never showed after the fire plan was fired, and battalion 2 attacked with the strike unanswered
  ([[dialog-reask-loop]]).
- The empty-village warning showed while the village was contested: its count read a circle smaller than the zone
  ([[detector-circles-only]]).
- Phase 1's points ran short against battalion 1 ([[scripted-economy]]).

Not read in this play: whether the 2S7Ms moved before or after the preparation fire, and whether any shell landed.
