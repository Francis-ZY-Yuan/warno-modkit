---
id: script-container-semantics
title: How script containers run their children, and when each action finishes
status: PLAYED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [script-flow]
trials: [2026-11-02-leveldesign-api-survey, 2026-11-03-play2-stock-survey, 2026-11-04-lifecycle-survey, 2026-11-06-probe2-play-run-a]
---
**What the game does.**
- **Sequential** starts a child and moves on only when that child reports it has finished.
- **Simultaneous** starts every child and finishes when all have finished.
- **Competition** finishes when its first child finishes, and retires the others. A retired action's lasting
  effect is removed ([[seteffect-never-finishes]]).
- `NbExecutions = -1` repeats forever; stock polling loops always wait a second or more per round.
- **WaitCondition** finishes when its condition holds; **IfThenElse** evaluates once and finishes when the chosen
  branch finishes (an absent branch finishes at once); **RandomLauncher** runs one child at random and finishes
  with it.
- Timers, counters and most actions are instantaneous: they finish in the update that starts them. A counter
  (GetNbKillsCamp, GetNbLossCamp, SetVariableIntegerFromUnitGroup) is a snapshot, so a live readout needs a loop.
- KillAllUnit and ChangeCamp finish a moment later; stock puts nodes after them.
- Dialogs finish when dismissed or answered; ProductionUnites when the units are produced.
- Some actions never finish at all ([[seteffect-never-finishes]]), and an objective waits until it resolves
  ([[objective-waits-until-resolved]]).

**How we know.** A read-only analysis of the runtime action classes, checked against how stock places each class,
and the second probe Operation, which ran every beat under these rules.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-leveldesign-api-survey](../trials/2026-11-02-leveldesign-api-survey.md), [2026-11-03-play2-stock-survey](../trials/2026-11-03-play2-stock-survey.md), [2026-11-03-probe1-play2-soviet-freeze](../trials/2026-11-03-probe1-play2-soviet-freeze.md), [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
<!-- referenced-by:end -->
