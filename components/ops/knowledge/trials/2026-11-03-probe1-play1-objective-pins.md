---
id: 2026-11-03-probe1-play1-objective-pins
kind: play
build: 46dccf8
game_version: 201602
mechanisms: [objective-label-needs-position]
outcome: fail
symptom: Every objective counter showed as a pin at the map corner or edge
cause: The counters set ShowEtiquette with no Position, so each label anchored at the missing position
result: Labels show only with a position, and a gate fails a label without one
---
