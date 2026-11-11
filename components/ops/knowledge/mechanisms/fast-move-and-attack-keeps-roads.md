---
id: fast-move-and-attack-keeps-roads
title: MoveAndAttack goes cross-country; FastMoveAndAttack and ForceRoad moves keep to roads
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [units-and-orders]
shapes: [modkit.ops.shapes.order, modkit.ops.mission.lane_route]
trials: [2026-11-03-probe1-play1-units-in-woods, 2026-11-03-play1-stock-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: final waves use FastMoveAndAttack (12) in Survivors; reinforcements move with ForceRoad, then FastMoveAndAttack (SigurdsStrike)
---
**What the game does.** `GiveOrderStandard` has no road flag; the order type decides. MoveAndAttack (24) is the
plain cross-country hunt order. FastMoveAndAttack (12) moves fast by road and still engages on sight.
`MoveUnitGroup` with `ForceRoad = True` (17 stock uses, any number of waypoints) and `Attack` with `ForceRoad`
(6 uses) route by road too.

**How we know.** Enemy armour on MoveAndAttack drove through the woods in the first probe's play. In the second
probe a 20-vehicle column on FastMoveAndAttack kept to the road through a narrow passage.

**Gotchas.** Roads help only if the target tag is on or near a road. Helicopters have no FastMoveAndAttack in their
order list; keep Move or MoveAndAttack for them.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-play1-stock-survey](../trials/2026-11-03-play1-stock-survey.md), [2026-11-03-probe1-play1-units-in-woods](../trials/2026-11-03-probe1-play1-units-in-woods.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Shapes: [`modkit.ops.shapes.order`](../../src/modkit/ops/shapes.py), [`modkit.ops.mission.lane_route`](../../src/modkit/ops/mission.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
<!-- referenced-by:end -->
