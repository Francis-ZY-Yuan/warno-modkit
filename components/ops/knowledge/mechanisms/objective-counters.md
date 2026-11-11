---
id: objective-counters
title: Objective text shows live counters from a variable list
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [objectives-and-text]
trials: [2026-11-03-probe1-play1-worked, 2026-11-06-probe2-play-run-a]
stock_precedent: stock objectives show at most 2 numbers each
---
**What the game does.** An objective whose text holds `%1`/`%2` and lists variables shows them as live counters;
`LDHint` takes a variable list too. The counters update when a loop writes the variables.

Timer counters work the same way: 10 stock objectives show a timer in their label. A countdown in the objective
panel's title has no stock precedent.

**Gotchas.** Write the polled copy last, after every count it depends on. Keep the objective list short (the second
probe used at most 10 rows); how the panel overflows has not been seen.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md)
- Records: [dialog-text-takes-no-variables](dialog-text-takes-no-variables.md)
<!-- referenced-by:end -->
