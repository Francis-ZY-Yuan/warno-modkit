---
id: 2026-11-02-kreide-op-relaunch-loop
kind: launch
build: 5f22187
game_version: 201602
mechanisms: [gameplay-mod-relaunch]
outcome: fail
symptom: Relaunch Game prompt on starting any Operation; after Continue, the game came back with no mod active
cause: The build shipped a unit cluster (Gen/NDF/GFX/Unit.ndfbin), which made the mod a Gameplay mod
result: Operation mods ship scenario packs only; unit content went into a separate mod
---
A custom Operation on Kreide with one custom unit added. The build without the unit file never showed the prompt.
Two fixes before the real cause was found changed nothing: removing another installed mod, and giving the mod its
own ID. Both rested on untested inferences ([[test-the-theory-against-every-observation]]).
