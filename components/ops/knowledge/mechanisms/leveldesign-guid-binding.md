---
id: leveldesign-guid-binding
title: A script names a map item by the four words of the item's GUID in LevelDesign
status: PLAYED
last_verified: 201602 2026-11-06
source: stock-data
topics: [zones-and-map]
gates: [modkit.ops.gates.check_binding]
shapes: [modkit.ops.leveldesign.gd_tags, modkit.ops.leveldesign.ld_guid]
trials: [2026-11-02-leveldesign-api-survey, 2026-11-02-kreide-op-playtest-1, 2026-11-06-probe2-play-run-a]
stock_precedent: 2,133 of 2,133 GUID handles in the 16 Operations resolve, each to the item of the same name
---
**What the game does.** A GDScript reaches the map through `GdItems` tags. A tag's four GUID words are the
big-endian 32-bit words of the 16-byte GUID of an item in the Details pack's `out/LevelDesign.ndfbin`, and its
editor name equals the item's `Name`. Spawns (unit groups), circular detectors and plain positions all bind this
way.

**Gotchas.** The binding must be exact: each tag names exactly one item of the same Ranking/Name and a matching
add-on type, and each item has exactly one tag (`check_binding`). Generate item GUIDs under a namespace of your own
(`ld_guid`), so two mods cloned from one template never share one.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-playtest-1](../trials/2026-11-02-kreide-op-playtest-1.md), [2026-11-02-leveldesign-api-survey](../trials/2026-11-02-leveldesign-api-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Gates: [`modkit.ops.gates.check_binding`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.leveldesign.gd_tags`](../../src/modkit/ops/leveldesign.py), [`modkit.ops.leveldesign.ld_guid`](../../src/modkit/ops/leveldesign.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
<!-- referenced-by:end -->
