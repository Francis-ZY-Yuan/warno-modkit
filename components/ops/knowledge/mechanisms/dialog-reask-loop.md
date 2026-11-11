---
id: dialog-reask-loop
title: A multiple-choice dialog can be asked again in a loop if the choice is reset before each ask
status: PLAYED
last_verified: 201602 2026-11-11
source: play
topics: [objectives-and-text, script-flow]
shapes: [modkit.ops.mission.reask_loop]
trials: [2026-11-04-lifecycle-survey, 2026-11-06-probe2-play-run-a, 2026-11-11-twin-strike-play1]
---
**What the game does.** No stock dialog is ever asked twice. Asked in a loop, a multiple-choice dialog comes back
each round, and its answer can be read each time.

**The shape.** Before each ask, set the choice variable to a value no button gives; test each button's value
explicitly; read the answer only from a copy taken after the dialog has closed, or the loop's exit can read a stale
value while the dialog is still open. In the second probe it came back 30 s after each "hold" answer and stopped
after "fire".

**Gotcha: the answer exit cuts the loop mid-step, too.** The loop is raced against its exits in a Competition. After an
answer it writes the copy, then clears its "asking" flag; a race won by the answer's WaitCondition can end between the
two writes, leaving the flag set for good. In Twin Strike's first play the division fire plan was fired, its flag
stayed set, and the release dialog, which waited for that flag to clear, never showed
([[2026-11-11-twin-strike-play1]]). So reset the flag right after the race, in its Sequential, whichever exit won, and
bound any other wait on such a flag (a Competition with a WaitDuration).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Shapes: [`modkit.ops.mission.reask_loop`](../../src/modkit/ops/mission.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
<!-- referenced-by:end -->
