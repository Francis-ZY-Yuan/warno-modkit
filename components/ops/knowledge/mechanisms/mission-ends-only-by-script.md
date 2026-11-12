---
id: mission-ends-only-by-script
title: With CheckEndGame off, only the script's TriggerEndGame ends the battle, and the first one wins
status: PLAYED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [script-flow]
gates: [modkit.ops.gates.check_end_funnel, modkit.ops.gates.check_empty_group_guard, modkit.ops.gates.check_rules]
shapes: [modkit.ops.bricks.g_end_sequence, modkit.ops.shapes.set_end, modkit.ops.mission.end_funnel]
trials: [2026-11-02-leveldesign-api-survey, 2026-11-04-lifecycle-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: 15 of 16 stock Operations set CheckEndGame false; Total (6) and Major (5) victories are stock, Minor (4) has no stock use
---
**What the game does.** With `CheckEndGame` off, the game never ends the battle on its own, even when one side is
wiped out; only `TriggerEndGame` ends it (or the player leaving). The first `TriggerEndGame` wins and later ones are
ignored. A player win leaves `WinningAlliance` out; a loss is `WinningAlliance = 1`. The end screen has one text
for a win and one for a loss, not one per grade.

**So.**
- Route every ending through one latch, since victory and several defeats can fire in the same tick.
- Script the "whole force destroyed" defeat yourself, and arm it only after the player's group has had a unit, or it
  fires during deployment.
- Keep `CheckEndGame`, `GameTime` and `ModeFixedRandomSeed` out of the rules.
- Name the grade in a dialog before the end screen; treat Minor victory as untested.
- Script every ending the design wants, the enemy wiped out included, and show any end that waits on a clock (a timer
  in an objective's label, [[objective-counters]]): an end clock nobody can see reads as a battle that cannot be won.

**How we know.** In the second probe the end dialog's victory gave the total-victory screen, then the menu. The
same-tick ending race was built but not yet played.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-leveldesign-api-survey](../trials/2026-11-02-leveldesign-api-survey.md), [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Gates: [`modkit.ops.gates.check_end_funnel`](../../src/modkit/ops/gates.py), [`modkit.ops.gates.check_empty_group_guard`](../../src/modkit/ops/gates.py), [`modkit.ops.gates.check_rules`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.bricks.g_end_sequence`](../../src/modkit/ops/bricks.py), [`modkit.ops.shapes.set_end`](../../src/modkit/ops/shapes.py), [`modkit.ops.mission.end_funnel`](../../src/modkit/ops/mission.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
<!-- referenced-by:end -->
