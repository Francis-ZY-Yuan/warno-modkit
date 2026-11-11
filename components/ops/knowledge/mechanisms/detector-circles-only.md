---
id: detector-circles-only
title: DetectUnitDansDetecteur works only on circular zones
status: PLAYED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [zones-and-map]
gates: [modkit.ops.gates.check_zone_tags]
shapes: [modkit.ops.bricks.g_detect, modkit.ops.shapes.Minimap.ring_item, modkit.ops.mission.ring_round]
trials: [2026-11-04-zone-capture-survey, 2026-11-02-kreide-op-playtest-1, 2026-11-11-twin-strike-play1]
stock_precedent: 159/159 stock uses name a circular zone
---
**What the game does.** `ConditionDetectUnitDansDetecteur` reads a centre and a radius from its tag, so it works
only with a circular zone item (`TGDTagDetecteur` with a radius). On a plain position it never counts anything.

**Alternatives.**
- For a polygon, `ConditionUnitDansZone` with `ZoneType = 1` counts the units inside the union of its listed zones
  (4 stock uses).
- To count across several circles, add each circle's units to one group with `AddDetectedUnitsToUnitGroup`
  (53 stock uses); a unit already in the group is not added twice.

**How we know.** A custom Operation on Kreide counted its evacuated units in a circle in play.

**Gotcha: a circle is not the zone.** A circle inside a command zone covers only part of it. Twin Strike counted the
player's presence in the village by a 40 px circle that covered 44 % of the village's zone, so its empty-village
warning showed while the player's units fought in the zone's outer strips and the game showed the zone contested
([[2026-11-11-twin-strike-play1]]). When the rule is about the zone the player sees, count the zone itself
(`ConditionUnitDansZone`, ZoneType 1, as the toolkit's zone race does).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-playtest-1](../trials/2026-11-02-kreide-op-playtest-1.md), [2026-11-04-zone-capture-survey](../trials/2026-11-04-zone-capture-survey.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Gates: [`modkit.ops.gates.check_zone_tags`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.bricks.g_detect`](../../src/modkit/ops/bricks.py), [`modkit.ops.shapes.Minimap.ring_item`](../../src/modkit/ops/shapes.py), [`modkit.ops.mission.ring_round`](../../src/modkit/ops/mission.py)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md), [scripted-nuke-effect](scripted-nuke-effect.md)
<!-- referenced-by:end -->
