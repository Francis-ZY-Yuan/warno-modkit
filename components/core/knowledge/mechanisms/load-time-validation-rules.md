---
id: load-time-validation-rules
title: Every object is validated at load, and the first broken rule stops the load
status: PLAYED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [loading-and-crashes, game-updates]
gates: [modkit.core.ndfrules.check_file]
trials: [2026-11-03-probe1-launch1-damagetype, 2026-11-03-ndfrules-stock-sweep, 2026-11-06-probe2-play-run-a]
stock_precedent: 3,870 rules on 1,565 classes; 888 of 888 current stock files pass
---
**What the game does.** When a pack loads, each object is checked against its class's load-time rules: a property
that must be defined, a lower or upper bound, a key that must be valid. The first broken rule is a fatal error at
load that names the class and the property, for example `Property 'DamageType' must be defined`.

**How we know.** A read-only analysis of the game's code lists every class's rules.
`python -m modkit.core.ndfrules extract` writes them to a table on your own machine, and the gate `check_file`
applies them to every generated file. The gate fails the build that stopped at load, with the game's own message,
and passes every stock file of the current build.

**Gotchas.**
- For many numeric properties "must be defined" means "non-zero": an explicit 0 counts as undefined
  ([[changestress-damagetype-zero]]).
- Stock leaves "required" properties out 3,363 times and still loads, because the built-in default passes. Only an
  explicit zero is sure to fail, so the gate flags a left-out property only when no stock object of the class
  leaves it out.
- Some checks are free-form conditions the gate cannot evaluate. They fail the build until someone reviews them
  (`ndfrules.REVIEWED`). A class listed in `ndfrules.PROPERTIES` also refuses any property that no rule names and
  nobody has reviewed.
- The table covers what validation checks at load. Anything the game checks later, at run time, is not covered.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-ndfrules-stock-sweep](../trials/2026-11-03-ndfrules-stock-sweep.md), [2026-11-03-probe1-launch1-damagetype](../trials/2026-11-03-probe1-launch1-damagetype.md), [2026-11-06-probe2-play-run-a](../../../ops/knowledge/trials/2026-11-06-probe2-play-run-a.md)
- Gates: [`modkit.core.ndfrules.check_file`](../../src/modkit/core/ndfrules.py)
- Skills: [`components/core/skills/warno-gates/SKILL.md`](../../skills/warno-gates/SKILL.md), [`components/core/skills/warno-gates/references/load-time-rules.md`](../../skills/warno-gates/references/load-time-rules.md), [`components/core/skills/warno-launch-triage/SKILL.md`](../../skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../../ops/skills/warno-new-operation/references/op-anatomy.md)
<!-- referenced-by:end -->
