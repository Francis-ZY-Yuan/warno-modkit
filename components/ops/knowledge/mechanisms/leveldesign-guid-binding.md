---
id: leveldesign-guid-binding
title: A script names a map item by the item's GUID in LevelDesign (210942 one GUID value, 201602 four words)
status: PLAYED
last_verified: 201602 2026-11-06
source: stock-data
topics: [zones-and-map, game-updates]
gates: [modkit.ops.gates.check_binding]
shapes: [modkit.ops.leveldesign.gd_tags, modkit.ops.leveldesign.ld_guid]
trials: [2026-11-02-leveldesign-api-survey, 2026-11-02-kreide-op-playtest-1, 2026-11-06-probe2-play-run-a, 2026-11-12-port-210942-survey]
stock_precedent: 2,133 of 2,133 GUID handles in the 16 Operations resolve, each to the item of the same name (on 201602 and on 210942)
---
**What the game does.** A GDScript reaches the map through `GdItems` tags. Since build 210942 a tag's
`GameDesignAddonId` is the 16-byte GUID of an item in the Details pack's `out/LevelDesign.ndfbin`, one GUID value
(on 201602 it was four properties, `GUID1`..`GUID4`, the GUID's big-endian 32-bit words, which 210942 no longer has),
and its editor name equals the item's `Name`. Spawns (unit groups), circular detectors and plain positions all bind this
way.

**Gotchas.** The binding must be exact: each tag names exactly one item of the same Ranking/Name and a matching
add-on type, and each item has exactly one tag (`check_binding`). Generate item GUIDs under a namespace of your own
(`ld_guid`), so two mods cloned from one template never share one.

**On build 210942: unverified in play.** All 2,133 tags of the 16 stock challenges bind by `GameDesignAddonId`; the
LevelDesign side is unchanged ([[2026-11-12-port-210942-survey]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-playtest-1](../trials/2026-11-02-kreide-op-playtest-1.md), [2026-11-02-leveldesign-api-survey](../trials/2026-11-02-leveldesign-api-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md)
- Gates: [`modkit.ops.gates.check_binding`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.leveldesign.gd_tags`](../../src/modkit/ops/leveldesign.py), [`modkit.ops.leveldesign.ld_guid`](../../src/modkit/ops/leveldesign.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
- Records: [game-build-classes](game-build-classes.md)
<!-- referenced-by:end -->
