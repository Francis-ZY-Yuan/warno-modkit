---
id: garrison-roe-and-hold
title: A garrison in a camp with no AI holds its ground only with the ROE and smart orders the script gives it
status: STOCK
last_verified: 201602 2026-11-11
source: stock-data
topics: [units-and-orders]
shapes: [modkit.ops.bricks.g_idle_roe, modkit.ops.bricks.g_roe, modkit.ops.bricks.g_smart_hold]
trials: [2026-11-11-twin-strike-play1]
stock_precedent: Survivors gives 271/333 garrison units Cover and 280/333 Aggressive; Sledgehammer and RunningTheGauntlet give every enemy unit of their AI-less camps Hold Position and Aggressive; RedJuggernaut's village defenders get a Hold smart order at their village
---
**What stock does.** A unit pre-placed in a camp with no AI strategy does nothing of its own beyond its idle default.
Stock gives each garrison its orders at load, last after the group is filled:
- `SetIdleROEBehavior`: what an idle unit does. 0 Nothing, 1 AutoCover (the COVER button: the nearest cover within a
  short range), 2 IADefend (the HOLD POSITION button: the computer holds the unit and redeploys it to the best
  defensive positions near it). Survivors writes 1 on its garrison groups (#188); Sledgehammer #319 and
  RunningTheGauntlet #105 write 2 on every enemy unit of their AI-less camps.
- `SetShotReactionROEBehavior`: what a unit fired on from out of its range does. 0 Passive, 1 Defensive, 2
  Aggressive; stock's garrisons get 2 (Survivors #189, Sledgehammer #316, RunningTheGauntlet #104).
- `LaunchSmartOrder` Hold (SmartOrderType 2, beside Seize's 1 and ManageArtillery_Auto's 6) at a place: RedJuggernaut
  #249/#250 on its village defenders, at the village's tag, last in their container; Sledgehammer #382 on groups found
  in its town circles. It finishes at once (TheDieburgSalient #414-#416 run three in a row).

No LevelDesign property puts a unit in a building: stock gets infantry into houses through these behaviours.

**Seen in play:** Twin Strike's garrison, given only its group, stood idle in the village
([[2026-11-11-twin-strike-play1]]). It now gets HOLD POSITION, Aggressive and a Hold at the village.

**Not seen in play:** that these orders put the infantry into the houses, or how far Hold Position moves a unit (a
garrison that leaves a detector circle stops counting there).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Shapes: [`modkit.ops.bricks.g_idle_roe`](../../src/modkit/ops/bricks.py), [`modkit.ops.bricks.g_roe`](../../src/modkit/ops/bricks.py), [`modkit.ops.bricks.g_smart_hold`](../../src/modkit/ops/bricks.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md), [wave-ends-with-attack](wave-ends-with-attack.md)
<!-- referenced-by:end -->
