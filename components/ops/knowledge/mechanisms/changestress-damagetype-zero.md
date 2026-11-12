---
id: changestress-damagetype-zero
title: A script's ChangeStress damages with Physical and cannot suppress; DamageType 0 fails at load
status: PLAYED
last_verified: 210942 2026-11-12
source: exe-analysis
topics: [units-and-orders, loading-and-crashes, game-updates]
gates: [modkit.core.ndfrules.check_file]
trials: [2026-11-03-probe1-launch1-damagetype, 2026-11-03-ndfrules-stock-sweep, 2026-11-11-fxprobe-play1, 2026-11-12-port-210942-survey, 2026-11-12-twin-strike-210942-play1]
---
**What the game does.** `TGDDescriptorChangeStress` must have a non-zero `DamageType`, and 0 is Suppress. So only
Physical (1) and Stun (2) load; a script cannot apply suppression.

**Seen in play** ([[2026-11-11-fxprobe-play1]]):
- Physical takes hit points: Value 5 left an M1A1(HA) and an M2A2, each of 10 hit points (`MaxPhysicalDamages`), at 5
  of 10 health segments;
- Stun, Value 240 (0.8 of the ground-unit stun cap, 300): no visible sign on the unit panel or the icons;
  inconclusive.

**Gotchas.** No stock script uses ChangeStress at all. On 201602 Stun showed no sign; on 210942 a stunned unit shows
it (below).

**On build 210942.** The load rule above is 201602's: the 210942 rules table's `TGDDescriptorChangeStress` validation
tests `Group` alone, no longer `DamageType` ([[2026-11-12-port-210942-survey]]). What a DamageType of 0 does on 210942
is unknown, so the toolkit keeps writing only Physical or Stun. Seen in play ([[2026-11-12-twin-strike-210942-play1]]):
- Physical with its DamageType, then Stun, loaded with no error;
- the stun shows: after Twin Strike's strike (Stun 240), a survivor was labelled "STUNNED! (1.3)", where the 201602
  probe saw no sign;
- the damage (Physical 5) was not read.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-ndfrules-stock-sweep](../../../core/knowledge/trials/2026-11-03-ndfrules-stock-sweep.md), [2026-11-03-probe1-launch1-damagetype](../../../core/knowledge/trials/2026-11-03-probe1-launch1-damagetype.md), [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md)
- Gates: [`modkit.core.ndfrules.check_file`](../../../core/src/modkit/core/ndfrules.py)
- Skills: [`components/core/skills/warno-gates/references/load-time-rules.md`](../../../core/skills/warno-gates/references/load-time-rules.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/fxprobe.py`](../../examples/probes/probes/fxprobe.py), [`components/ops/examples/probes/probes/spike.py`](../../examples/probes/probes/spike.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [load-time-validation-rules](../../../core/knowledge/mechanisms/load-time-validation-rules.md), [scripted-fires](scripted-fires.md), [scripted-nuke-effect](scripted-nuke-effect.md)
<!-- referenced-by:end -->
