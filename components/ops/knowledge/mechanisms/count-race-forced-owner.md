---
id: count-race-forced-owner
title: Decide a zone by a timed unit count, then force its owner so the map shows it
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [zones-and-map]
shapes: [modkit.ops.bricks.g_hold, modkit.ops.bricks.g_detect, modkit.ops.shapes.seconds_while, modkit.ops.bricks.g_units_in_zones, modkit.ops.bricks.g_zone_owner, modkit.ops.mission.zone_race, modkit.ops.mission.zone_handover]
trials: [2026-11-04-zone-capture-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: Marauders counts, then forces the owner; Gotterdammerung's "one side present, the other gone"
---
**The shape.** A count race: "side A has at least k units in the zone and side B none, for T seconds", with the
timer restarting whenever it breaks (`g_hold`). When it holds, `SetCommandZoneOwnerAndForceConvergence` gives the
zone to the winner, so the map colour and the game's own zone feedback follow.

**How we know.** In the second probe a zone turned red after 3 or more enemy units held two zones for 20 s, though
none of them could capture.

**Gotchas.** Count rules see every unit, not command units; restrict them with the condition's constraint (team,
plus a category or type where only vehicles should count).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-zone-capture-survey](../trials/2026-11-04-zone-capture-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Shapes: [`modkit.ops.bricks.g_hold`](../../src/modkit/ops/bricks.py), [`modkit.ops.bricks.g_detect`](../../src/modkit/ops/bricks.py), [`modkit.ops.shapes.seconds_while`](../../src/modkit/ops/shapes.py), [`modkit.ops.bricks.g_units_in_zones`](../../src/modkit/ops/bricks.py), [`modkit.ops.bricks.g_zone_owner`](../../src/modkit/ops/bricks.py), [`modkit.ops.mission.zone_race`](../../src/modkit/ops/mission.py), [`modkit.ops.mission.zone_handover`](../../src/modkit/ops/mission.py)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [zone-capture-command-units](zone-capture-command-units.md)
<!-- referenced-by:end -->
