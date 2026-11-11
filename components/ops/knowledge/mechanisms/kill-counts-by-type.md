---
id: kill-counts-by-type
title: Kill counts are by unit type, not by group; count a group's survivors instead
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [units-and-orders]
trials: [2026-11-04-lifecycle-survey, 2026-11-06-probe2-play-run-a]
---
**What the game does.** `GetNbKillsCamp` counts kills of the listed unit types, wherever the units came from, so two
groups of the same type share one count. `SetVariableIntegerFromUnitGroup` gives a group's alive count. To score a
group, count its survivors and take kills as spawned minus alive.

**How we know.** The second probe read both counts as planned.

**Gotchas.** Infantry riding in vehicles might not count as alive in their group; not checked.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
<!-- referenced-by:end -->
