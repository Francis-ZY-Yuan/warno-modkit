---
id: zone-lookup-by-point
title: Zone conditions find their zone by a tag's point, and a point in no zone fails silently
status: PLAYED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [zones-and-map]
gates: [modkit.ops.gates.check_zone_tags]
shapes: [modkit.ops.shapes.Minimap.zone_item]
trials: [2026-11-04-zone-capture-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: every stock zone item's point lies inside its own polygon; 131/131 ConditionCampControleZone use ZoneType 1 with AutoriseControleAllie
---
**What the game does.** `ConditionCampControleZone` (its `Position`), `SetCommandZoneOwnerAndForceConvergence` (its
`Positions`) and `ConditionUnitDansZone` (its `Detecteurs`) take a tag's point and look it up in the polygons of the
zone file for their `ZoneType`: 1 for command zones, 0 for deployment zones.

**Gotchas.**
- A point inside no polygon gives no error. The control test stays false forever, the forced owner does nothing,
  and `UnitDansZone` then counts every unit that is outside all zones.
- A left-out `ZoneType` reads as 0, the deployment zones. Set it to 1 for command zones.
- In overlapping command zones a unit counts for one zone only (stock overlaps once in 24 files).
- Zone-control tests only listen in the Command phase.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-zone-capture-survey](../trials/2026-11-04-zone-capture-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Gates: [`modkit.ops.gates.check_zone_tags`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.shapes.Minimap.zone_item`](../../src/modkit/ops/shapes.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py)
<!-- referenced-by:end -->
