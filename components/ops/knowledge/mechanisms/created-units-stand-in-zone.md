---
id: created-units-stand-in-zone
title: A script cannot hide a unit outside the playable zone; a unit created there stands on the zone's edge, where the player's units see and engage it
status: FAILED
last_verified: 201602 2026-11-11
source: play
topics: [units-and-orders, zones-and-map]
gates: [modkit.ops.gates.check_created_in_zone]
trials: [2026-11-11-twin-strike-guns-on-the-edge]
stock_precedent: all 300 stock CreateUnitOnPosition stand inside their scenario's playable zone, and every stock land arrival and aerial corridor starts inside it
---
**What the game does.** Twin Strike created each fire's battery with `CreateUnitOnPosition` at a Name tag 4,577 GRU
north of its playable zone, to hide it from the player. In play the battery stood on the zone's north edge, at the
zone's point nearest the tag: a tight block of icons on the border line, partly over it, beside the player's
deployment box ([[2026-11-11-twin-strike-guns-on-the-edge]]). It was a real unit there, not a marker for one still
outside. The player's units saw it, and since its camp was of the enemy alliance, the player's Ka-50s fired on it and
killed it. Its `ShootOnPosition` still fired, and the shells landed on the target, which was in range from the edge.

**Not settled.** Whether the game puts the units on the edge as it creates them, or they drive there at once. The
battery was kept off its camp's AI and every target was in range from the tag, so nothing gave it a reason to move.
Either way, nothing created outside the zone stays hidden there.

**Stock.** All 300 `CreateUnitOnPosition` of the 21 stock scenarios that create units stand inside the scenario's
playable zone; four of them (Survivors, RedJuggernaut, Gotterdammerung, ClosingTheTrap) ship a zone file with no area,
which makes the whole map playable. Every stock land arrival and aerial corridor starts inside the zone too. Only two
pre-placed stock items stand outside: DelayedRetribution's 11 hidden T-72Ms, about 600 GRU out, and a HoldUntilRelieved
D-20, 20 GRU out.

**The alternative.** Create every unit inside the playable zone. `check_created_in_zone`, gate 3 of every build,
holds a script to it: each `CreateUnitOnPosition` names a LevelDesign item inside the shipped playable zone. A unit the
player must not engage goes in a camp of the player's alliance ([[scripted-fires]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-twin-strike-guns-on-the-edge](../trials/2026-11-11-twin-strike-guns-on-the-edge.md)
- Gates: [`modkit.ops.gates.check_created_in_zone`](../../src/modkit/ops/gates.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-guns-on-the-edge](../trials/2026-11-11-twin-strike-guns-on-the-edge.md), [scripted-fires](scripted-fires.md)
<!-- referenced-by:end -->
