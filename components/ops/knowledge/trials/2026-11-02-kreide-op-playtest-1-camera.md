---
id: 2026-11-02-kreide-op-playtest-1-camera
kind: play
build: 3ea9299
game_version: 201602
mechanisms: [start-camera-before-loading-done, ai-grid-tiles-playable-zone]
outcome: fail
symptom: The opening camera was off, and the whole map was playable
cause: No start camera was snapped before LoadingDone, and the cloned playable zone covered the whole map
result: An opening camera over the town, and a generated playable zone covering only the mission area
---
The generated smaller playable zone led to the next failure ([[2026-11-02-kreide-op-ai-grid-crash]]).
