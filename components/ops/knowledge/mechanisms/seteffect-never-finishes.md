---
id: seteffect-never-finishes
title: SetEffect and other lasting actions never finish, so nothing after them in a Sequential ever runs
status: PLAYED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [script-flow, units-and-orders]
gates: [modkit.ops.gates.check_never_finishing]
shapes: [modkit.ops.shapes.reveal]
trials: [2026-11-03-probe1-play1-decoys-fired, 2026-11-03-probe1-play2-soviet-freeze, 2026-11-03-play2-stock-survey, 2026-11-03-never-finishing-stock-sweep, 2026-11-06-probe2-play-run-a]
stock_precedent: 37/37 stock SetEffects sit last in a Sequential, in a Simultaneous or in a Competition; 0 of 161 other never-finishing actions are followed in a Sequential; TriggerEndGame 1 of 88
---
**What the game does.** These actions never report that they have finished: **SetEffect, DrawLabelOnPosition,
LockDeckUnit, LockIncome, LockCombatGroup, GiveIncomeToTeam, WaitForEver and TriggerEndGame**. ModifyUnitSpeed and
the other ModifyUnit actions finish only when every unit they track is gone. A Sequential waits for each child to
finish, so anything placed after one of these never runs.

SetEffect is a live binding, not a one-shot: while the action lives, units that join the group get the effect,
units that leave lose it, and when the action is retired (an ancestor Competition ends, say) the effect is removed
from every unit. SetAmmo and SetFuel are instantaneous and leave nothing to undo.

**The stock shape.** Create the units, then end the beat with one Simultaneous holding the SetEffect beside a
Sequential with the rest of the beat. Nothing may follow that Simultaneous, it must not sit in a looping Sequential,
and no ancestor may wait on the beat. One SetEffect can cover a whole wave: its UnitGroup is a list. ModifyUnit
actions never sit in a Sequential in stock (48 of 48).

**Gotchas.**
- A loop that holds a SetEffect beside other nodes stalls in its first round.
- The reveal pack `UnitEffect_revealUnit` is stock, but only a capacity uses it; no stock script applies it, and
  whether it shows units to the player has not been seen.
- `Competition[SetEffect, short wait]` strips the effect when the wait ends; stock uses exactly that to bound how
  long an effect lasts.
- A stock precedent includes the node's place. Two of our docstrings cited stock SetEffect and ModifyUnitSpeed uses
  as precedent but missed that each was last in its container or inside a Simultaneous.

**The gate.** `gates.check_never_finishing` holds every action listed above, LockIncome and LockCombatGroup included
(the gate learned those two after a review found it let them through); all of stock's 34 LockIncome and 3
LockCombatGroup pass it. A LockIncome freezes income only while it lives, so stock races it against the condition that
lifts it (TheWingedHussars #165) [[scripted-economy]].

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-never-finishing-stock-sweep](../trials/2026-11-03-never-finishing-stock-sweep.md), [2026-11-03-play2-stock-survey](../trials/2026-11-03-play2-stock-survey.md), [2026-11-03-probe1-play1-decoys-fired](../trials/2026-11-03-probe1-play1-decoys-fired.md), [2026-11-03-probe1-play2-soviet-freeze](../trials/2026-11-03-probe1-play2-soviet-freeze.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Gates: [`modkit.ops.gates.check_never_finishing`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.shapes.reveal`](../../src/modkit/ops/shapes.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/core/skills/warno-stock-precedent/SKILL.md`](../../../core/skills/warno-stock-precedent/SKILL.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
- Records: [add-unit-to-deck](add-unit-to-deck.md), [know-whether-an-action-finishes](../lessons/know-whether-an-action-finishes.md), [script-container-semantics](script-container-semantics.md), [scripted-economy](scripted-economy.md), [weapons-jammed-effect](weapons-jammed-effect.md)
<!-- referenced-by:end -->
