---
id: scripted-air-sweep
title: Hidden aircraft revealed, sent over a circle and sent home once spent give an AI-less camp air sweeps
status: STOCK
last_verified: 201602 2026-11-11
source: stock-data
topics: [units-and-orders]
shapes: [modkit.ops.bricks.g_planes_spent, modkit.ops.shapes.order, modkit.ops.bricks.g_spawn]
stock_precedent: Survivors' end strike, one camp's aircraft (#1483-#1489, #1496, #1647/#1648); no stock script creates an aeroplane
---
**What stock does.** A camp with no AI buys no aircraft, so Survivors scripts its end strike:
1. its aircraft stand in LevelDesign hidden (DisableAutoSpawn, ExperienceLevel 2), off the battle;
2. `SpawnUnits` reveals them and their groups are filled (#1483-#1488), then `SetIdleROEBehavior` 2 (#1489);
3. a second later, `GiveOrderStandard` OrderType 3 (AirplaneMoveAndEngage), OrderCancelable, onto a CircularZones tag
   (#1496), in a Simultaneous;
4. beside it, a Sequential waits until the group's aircraft are out of fuel or ammunition (`UnitGroupWithFilter`,
   at least 2 of its 2, over three `ContrainteOnUnitLogistic`, #1682) and then gives OrderType 2 (AirplaneEvacuate),
   Blocking, with no place (#1647/#1648).
No stock script creates an aeroplane with CreateUnitOnPosition (only helicopters); camps with an AI strategy buy
theirs from a deck.

**Twin Strike** flies NATO's fighter sweeps so, each its own group in its own branch, so none holds up a phase: F-15Cs
over the fire boxes in phase 3 (a third over the village on Hard), and Phantoms over the village once battalion 2
attacks. Survivors' aircraft are its player's ally's; Twin Strike's are the enemy's.

**Not seen in play:** aircraft revealed in an enemy camp, what AirplaneMoveAndEngage does with helicopters inside its
circle, and where AirplaneEvacuate sends an aircraft when its camp has no aerial corridor (Survivors has none).

<!-- referenced-by:start -->
## Referenced by

- Shapes: [`modkit.ops.bricks.g_planes_spent`](../../src/modkit/ops/bricks.py), [`modkit.ops.shapes.order`](../../src/modkit/ops/shapes.py), [`modkit.ops.bricks.g_spawn`](../../src/modkit/ops/bricks.py)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
<!-- referenced-by:end -->
