---
id: objective-label-needs-position
title: An objective's map label needs a position, or it pins the map corner
status: STOCK
last_verified: 201602 2026-11-03
source: stock-data
topics: [objectives-and-text]
gates: [modkit.ops.gates.check_objective_pins]
shapes: [modkit.ops.shapes.objective]
trials: [2026-11-03-probe1-play1-objective-pins, 2026-11-03-play1-stock-survey]
stock_precedent: ShowEtiquette is never False in the 30 stock GDScripts; 47 of the 52 GereObjectifs with no position leave it out (the other 5, in DelayedRetribution and HoldUntilRelieved, are why the gate is a toolkit convention)
---
**What the game does.** `ShowEtiquette` switches an objective's map label on; `Position` (or a unit-group position
list) only anchors it. A label with no anchor is drawn at the missing position: the map corner.

**The shape.** Show the label only with a position; otherwise leave `ShowEtiquette` out. The counter text in the
objective list still shows.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-play1-stock-survey](../trials/2026-11-03-play1-stock-survey.md), [2026-11-03-probe1-play1-objective-pins](../trials/2026-11-03-probe1-play1-objective-pins.md)
- Gates: [`modkit.ops.gates.check_objective_pins`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.shapes.objective`](../../src/modkit/ops/shapes.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md)
<!-- referenced-by:end -->
