---
id: changestress-damagetype-zero
title: A script's ChangeStress cannot suppress; DamageType 0 fails at load
status: RE
last_verified: 201602 2026-11-03
source: exe-analysis
topics: [units-and-orders, loading-and-crashes]
gates: [modkit.core.ndfrules.check_file]
trials: [2026-11-03-probe1-launch1-damagetype, 2026-11-03-ndfrules-stock-sweep]
---
**What the game does.** `TGDDescriptorChangeStress` must have a non-zero `DamageType`, and 0 is Suppress. So only
Physical (1) and Stun (2) load; a script cannot apply suppression.

**Gotchas.** No stock script uses ChangeStress at all, so whether Stun behaves as expected in play is still open.
A stress value of 0.8 of the ground-unit stun cap (240) loaded.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-ndfrules-stock-sweep](../../../core/knowledge/trials/2026-11-03-ndfrules-stock-sweep.md), [2026-11-03-probe1-launch1-damagetype](../../../core/knowledge/trials/2026-11-03-probe1-launch1-damagetype.md)
- Gates: [`modkit.core.ndfrules.check_file`](../../../core/src/modkit/core/ndfrules.py)
- Skills: [`components/core/skills/warno-gates/references/load-time-rules.md`](../../../core/skills/warno-gates/references/load-time-rules.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/spike.py`](../../examples/probes/probes/spike.py)
- Records: [load-time-validation-rules](../../../core/knowledge/mechanisms/load-time-validation-rules.md), [scripted-fires](scripted-fires.md)
<!-- referenced-by:end -->
