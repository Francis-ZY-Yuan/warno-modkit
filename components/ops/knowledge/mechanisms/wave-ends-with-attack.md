---
id: wave-ends-with-attack
title: An AI-less wave stops at its last waypoint unless its route ends with an Attack on the player's units
status: STOCK
last_verified: 201602 2026-11-11
source: stock-data
topics: [units-and-orders, script-flow]
shapes: [modkit.ops.bricks.g_attack, modkit.ops.mission.lane_route, modkit.ops.mission.wave]
trials: [2026-11-11-twin-strike-play1]
stock_precedent: 65/65 stock Attacks sit last in their Sequential and none in a loop; 48 of them are Survivors', its AI-less enemy camps' groups
---
**What stock does.** A group a script drives by its waypoints, in a camp with no AI strategy, does nothing after its
last order completes: it stands there and engages only what comes into its own range. Survivors, the template, ends
its enemy groups' scripts with an `Attack` on the player's units: Blocking, Group, AttackEnPrioriteUniteNotUbserstress
True, Targets the player's unit group (#1099; 41 of its 48 Attacks are exactly this). Every stock Attack is the last
node of its Sequential and none sits in a loop, so the toolkit treats it as the end of a route
(`mission.lane_route`'s final node, after every leg raced against its timeout). In camps with an AI strategy stock
hands the scripted units back to the AI instead (RemoveIgnoredUnitByScript).

RunningTheGauntlet #326 also sets its counter-attack group's idle behaviour before its legs
([[garrison-roe-and-hold]] for the values).

**Seen in play:** a Twin Strike wave, its last leg a plain MoveAndAttack into the village, stopped at that waypoint
([[2026-11-11-twin-strike-play1]]). Its waves now race the last leg too and end with the Attack on `Groupe_Joueur`,
which the script refreshes every 2 s.

**Not seen in play:** which of the player's units an Attack picks, what it does with ones it cannot reach (aircraft),
and whether a blocking Attack ever finishes (keep it last).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Shapes: [`modkit.ops.bricks.g_attack`](../../src/modkit/ops/bricks.py), [`modkit.ops.mission.lane_route`](../../src/modkit/ops/mission.py), [`modkit.ops.mission.wave`](../../src/modkit/ops/mission.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
<!-- referenced-by:end -->
