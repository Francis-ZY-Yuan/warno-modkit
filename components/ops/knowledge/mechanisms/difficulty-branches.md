---
id: difficulty-branches
title: Difficulty reaches a script as three conditions; give it a Medium baseline
status: STOCK
last_verified: 201602 2026-11-06
source: stock-data
topics: [script-flow]
shapes: [modkit.ops.bricks.g_difficulty, modkit.ops.mission.difficulty]
trials: [2026-11-04-lifecycle-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: 87 stock uses, three sibling IfThenElse on ConditionOnGameDifficulty
---
**What stock does.** Three `IfThenElse` on `ConditionOnGameDifficulty` with Difficulty 0 (Easy), 1 (Medium) and 2
(Hard), no else branch, as siblings in a Simultaneous. Easy is 0, the default, so the Easy condition is an empty
object. No scenario file declares difficulty; the Operations screen offers a picker for each challenge-type
scenario.

**So.** Whether a mod Operation gets the picker, and which value its script receives, has not been seen. Apply
Medium's values unconditionally and let the Easy and Hard branches override them, so a missing value still plays
Medium.

**Gotchas.** A SetEffect inside a difficulty branch lasts only while its ancestors live.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Shapes: [`modkit.ops.bricks.g_difficulty`](../../src/modkit/ops/bricks.py), [`modkit.ops.mission.difficulty`](../../src/modkit/ops/mission.py)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
<!-- referenced-by:end -->
