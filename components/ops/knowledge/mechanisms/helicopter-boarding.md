---
id: helicopter-boarding
title: Scripted infantry boarding of a helicopter does not work
status: FAILED
last_verified: 201602 2026-11-03
source: play
topics: [units-and-orders]
trials: [2026-11-03-probe1-play1-helicopter-empty, 2026-11-03-probe1-play2-helicopter-separate, 2026-11-03-play1-stock-survey, 2026-11-03-play2-stock-survey]
stock_precedent: none of the 57 stock LoadIntoTransporter nodes targets a helicopter
---
**What happened.** Twice the scripted squad and its helicopter stayed apart: first with a raced
`LoadIntoTransporter`, then with a Land order before the boarding.

**Why.** Stock loads infantry only into ground vehicles (spawn both, gather them in one group, then a blocking
`LoadIntoTransporter`). No stock script orders a helicopter to land or loads one. Land (18) is an instant order
that takes no target, so the helicopter lands where it is, and a blocking Land may never end.

**Alternatives.**
- Drop the boarding: create or reveal the squad at the landing zone when the helicopter arrives (stock-proven
  primitives). This is the fallback in use.
- `ProductionUnites` has a native `Transporter` property, and the squad-plus-helicopter pair is a stock deck pack,
  but no stock script sets it. Untested.
- A deck card with a transporter ([[add-unit-to-deck]]), also untested.

Unloading at the landing zone (`UnloadFromTransporter`) and lifting off again (GoUp) are untested too.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-play1-stock-survey](../trials/2026-11-03-play1-stock-survey.md), [2026-11-03-play2-stock-survey](../trials/2026-11-03-play2-stock-survey.md), [2026-11-03-probe1-play1-helicopter-empty](../trials/2026-11-03-probe1-play1-helicopter-empty.md), [2026-11-03-probe1-play2-helicopter-separate](../trials/2026-11-03-probe1-play2-helicopter-separate.md)
- Skills: [`components/core/skills/warno-stock-precedent/SKILL.md`](../../../core/skills/warno-stock-precedent/SKILL.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
- Records: [spawn-and-create-units](spawn-and-create-units.md)
<!-- referenced-by:end -->
