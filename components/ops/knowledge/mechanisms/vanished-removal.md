---
id: vanished-removal
title: KillAllUnit with Vanished removes units at once; count them before you remove them
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [units-and-orders]
trials: [2026-11-04-lifecycle-survey, 2026-11-06-probe2-play-run-a]
---
**What the game does.** `KillAllUnit` with the Vanished cause removes every unit of the listed groups at once.

**Gotchas.** Whether a vanished unit counts as a loss or a kill is unknown. Read the group's size first, then
remove it, and never read a loss counter after the removal. Stock uses KillAllUnit with Penetration only in the
campaign tutorials.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [scripted-fires](scripted-fires.md), [scripted-nuke-effect](scripted-nuke-effect.md)
<!-- referenced-by:end -->
