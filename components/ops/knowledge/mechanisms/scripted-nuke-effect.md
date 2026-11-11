---
id: scripted-nuke-effect
title: A script cannot launch the tactical-nuke impact effect; the game crashes
status: FAILED
last_verified: 201602 2026-11-10
source: play
topics: [script-flow, units-and-orders]
gates: [modkit.ops.gates.check_script_effects]
trials: [2026-11-10-probe3-play1-effect-crash]
stock_precedent: no stock script launches an impact effect; every one of its effect launches names a ForScript effect
---
**What the data says.** The game has the tactical-nuke impact effect under two names: `$/GFX/GameFx/fx_impact_sol_Tactical_Nuke`
(the ground-impact wrapper, which plays the second) and `$/GFX/GameFx/fx_impact_Tactical_Nuke`. The impact-mapping
table keys the first to an impact named `ArtillerieM185155MmNUKE`, which no ammunition uses, so the effect is reachable in
the data and in no stock fire.

**What happened** (Q1, answered: a script launch of either name crashes the game). The third probe's first play
crashed the game during the deploy phase, at its effect steps ([[2026-11-10-probe3-play1-effect-crash]]).

**Why.** Both names are parameterised impact actions. The wrapper declares four parameters (position, direction and
two radii) with no defaults; the effect itself declares five, with defaults, and passes the position down to its
flash. The impact system binds them when a shell lands. `LaunchFXFireAndForgetOnPosition` carries only the effect's
name and a position, so nothing binds them ([[script-effects-self-contained]]). The build's script-effects gate now
refuses both names.

**Alternatives** (self-contained, so a script may launch them):
- `fx_HE_Mega_Bomb_ForScript`, the game's script-only mega bomb: named for scripts, though no stock scenario
  launches it. The probe's N2 now launches it;
- the 203 mm barrage and black smoke launched together (`fx_HE_Artillery_203mm_ForScript_RandomPosition` and
  `fx_FumeeNoire_ForScript_RandomPosition`, both stock-launched). The probe's N3 now launches them.

**Still open** (the probe's replay asks):
- Q2: how big each look is against five tanks, and whether it has a sound;
- Q3: whether `KillAllUnit` with DeathCause Penetration leaves wrecks, where Vanished removes the units
  ([[vanished-removal]]).

The effect is visual: nothing here suggests it kills. The probe's script collects the units in a 300 m circle
([[detector-circles-only]]) and kills them itself.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md)
- Gates: [`modkit.ops.gates.check_script_effects`](../../src/modkit/ops/gates.py)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/nuke.py`](../../examples/probes/probes/nuke.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [script-effects-self-contained](script-effects-self-contained.md)
<!-- referenced-by:end -->
