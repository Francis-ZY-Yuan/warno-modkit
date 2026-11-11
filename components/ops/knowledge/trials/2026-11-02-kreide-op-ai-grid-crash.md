---
id: 2026-11-02-kreide-op-ai-grid-crash
kind: launch
build: 2f9312a
game_version: 201602
mechanisms: [ai-grid-tiles-playable-zone]
outcome: fail
symptom: The game crashed while loading the Operation, at the same place every time
cause: A whole-map AI strategic grid under a smaller playable zone; in stock the grid tiles exactly the zone
result: The generator builds the grid as the subset of the map's grid inside the playable zone
---
The build after the first play of a custom Operation on Kreide shrank the playable zone but kept the map's whole AI
grid.
