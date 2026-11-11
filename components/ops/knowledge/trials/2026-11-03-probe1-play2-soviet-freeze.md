---
id: 2026-11-03-probe1-play2-soviet-freeze
kind: play
build: 4b99a5a
game_version: 201602
mechanisms: [seteffect-never-finishes, script-container-semantics, weapons-jammed-effect, scripted-fires]
outcome: fail
symptom: No enemy unit moved and no barrage came; the decoys kept their ammunition
cause: A SetEffect, which never finishes, sat mid-Sequential after every enemy create, so every later order, fire and wave row was skipped
result: Each beat ends with a Simultaneous holding the SetEffect beside the rest, and a gate fails any node after a never-finishing action
---
The first probe's second play. A spike-only reveal effect had been added after each enemy create; every beat
stopped right there, exactly as the stock placement rule predicts ([[2026-11-03-never-finishing-stock-sweep]]).
