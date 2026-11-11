---
id: spawn-and-create-units
title: SpawnUnits reveals pre-placed units; CreateUnitOnPosition makes new ones at a tag
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [units-and-orders]
shapes: [modkit.ops.bricks.g_create, modkit.ops.shapes.create, modkit.ops.bricks.g_spawn, modkit.ops.mission.hidden_units, modkit.ops.mission.placed_units]
trials: [2026-11-02-leveldesign-api-survey, 2026-11-03-probe1-play1-worked, 2026-11-06-probe2-play-run-a]
---
**What the game does.**
- `SpawnUnits(Units = [unit groups])` reveals pre-placed map items (`TGameDesignAddOn_Spawn` with
  `DisableAutoSpawn`). The first probe's 8 hidden reserve tanks appeared this way at 3:00.
- `CreateUnitOnPosition(TypeUnit, Position, Camp, NbUnit, Group)` creates units from a unit descriptor name at a
  position or circle tag. The first probe's BMP column was created and moved this way at 2:00.

**Gotchas.**
- No spawn add-on and no creation node starts infantry inside a transport ([[helicopter-boarding]]).
- Stock makes aircraft only off-map, with `ProductionUnites` at an aerial-corridor tag; creating a helicopter on the
  map with CreateUnitOnPosition has no stock precedent.
- Stock hands a player a unit of the other coalition by revealing a pre-placed one in the player's camp (Survivors'
  captured tank).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-leveldesign-api-survey](../trials/2026-11-02-leveldesign-api-survey.md), [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Shapes: [`modkit.ops.bricks.g_create`](../../src/modkit/ops/bricks.py), [`modkit.ops.shapes.create`](../../src/modkit/ops/shapes.py), [`modkit.ops.bricks.g_spawn`](../../src/modkit/ops/bricks.py), [`modkit.ops.mission.hidden_units`](../../src/modkit/ops/mission.py), [`modkit.ops.mission.placed_units`](../../src/modkit/ops/mission.py)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
<!-- referenced-by:end -->
