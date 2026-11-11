---
id: objective-waits-until-resolved
title: An objective finishes only after it resolves and its chosen actions finish
status: PROBED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [objectives-and-text, script-flow]
gates: [modkit.ops.gates.check_never_finishing]
trials: [2026-11-04-lifecycle-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: 104 GereObjectif nodes in the 30 stock GDScripts; 2 are followed in a Sequential while unresolved (Sledgehammer, Kitzingen)
---
**What the game does.** `GereObjectif` (and its variable-owner form) stays active until its `Condition` or
`ConditionEchec` holds, then runs `ActionsReussi` or `ActionsEchec`, and finishes only when that subtree finishes.
An unresolved objective placed mid-Sequential freezes everything after it, the same way a SetEffect does.

**The shape.** Put objectives in a Simultaneous, or last in their Sequential; chain a second objective through the
first one's `ActionsReussi`. The second probe ran objectives that complete, fail and chain, plus a bonus, without a
stall; the objective panel's states were not read.

**Gotchas.** How bonus points (`BonusScoreMission`) are applied is unknown.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Gates: [`modkit.ops.gates.check_never_finishing`](../../src/modkit/ops/gates.py)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
- Records: [script-container-semantics](script-container-semantics.md)
<!-- referenced-by:end -->
