---
id: objective-counters
title: Objective text shows live counters from a variable list
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [objectives-and-text]
shapes: [modkit.ops.shapes.objective, modkit.ops.bricks.g_timer, modkit.ops.bricks.g_start_timer]
trials: [2026-11-03-probe1-play1-worked, 2026-11-06-probe2-play-run-a]
stock_precedent: stock objectives show at most 2 numbers each; 7 stock objectives and 3 map labels show a timer
---
**What the game does.** An objective whose text holds `%1`/`%2` and lists variables shows them as live counters;
`LDHint` takes a variable list too. The counters update when a loop writes the variables.

Timer counters work the same way in a label: 7 stock objectives list a timer for their label's `%1`
(`ListTimersForEtiquetteText`, never beside variables), each started by `StartTimer` (TheWingedHussars' hold, won
once its timer reads 0: "HOLD ALL ZONES FOR 3 MIN", "Time remaining %1", with no position, so in the panel only), and
3 map labels do on `DrawLabelOnPosition`. A countdown in the objective panel's title has no stock precedent. Twin Strike's end clock is
the toolkit's first timer objective, not yet played.

**Gotchas.** Write the polled copy last, after every count it depends on. Keep the objective list short (the second
probe used at most 10 rows); how the panel overflows has not been seen.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Shapes: [`modkit.ops.shapes.objective`](../../src/modkit/ops/shapes.py), [`modkit.ops.bricks.g_timer`](../../src/modkit/ops/bricks.py), [`modkit.ops.bricks.g_start_timer`](../../src/modkit/ops/bricks.py)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md)
- Records: [dialog-text-takes-no-variables](dialog-text-takes-no-variables.md), [mission-ends-only-by-script](mission-ends-only-by-script.md)
<!-- referenced-by:end -->
