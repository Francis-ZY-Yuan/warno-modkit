---
id: scripted-nuke-effect
title: A script cannot launch the tactical-nuke impact effect; the game crashes
status: FAILED
last_verified: 201602 2026-11-11
source: play
topics: [script-flow, units-and-orders]
gates: [modkit.ops.gates.check_script_effects]
trials: [2026-11-10-probe3-play1-effect-crash, 2026-11-11-twin-strike-strike-unseen]
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

**Q2, answered for the mega bomb: small, and unseen.** Twin Strike's smoke play launched one mega bomb on its 800 m
strike zone, off screen and in fog, and killed every NATO unit in the zone 3 s later: the player saw small explosions
and units dead, no massive effect ([[2026-11-11-twin-strike-strike-unseen]]). One mega bomb is about a 203 mm shell's
size: dust some 47 m out, gone within 10 s.

**What Twin Strike builds now** (not yet played; design 5.6 of its `docs/design.md`):
- **Massed self-contained effects at the flash,** at RedJuggernaut's scale (61 launches at once in its intro): 13 mega
  bombs over the zone, the 203 mm barrage 70 times, and white and black smoke 14 times, 97 launches in one
  Simultaneous. It reads as a carpet of heavy impacts and lasting smoke, not a mushroom cloud.
- **The camera on it:** a one-key shot flown from the player's view to the zone in 4 s, arriving a second before the
  flash, held 11 s ([[camera-shot-from-current-position]]). No fog lift: no stock script lifts the fog.
- **A toll, not a wipe,** half a second after the flash: a share of battalion 2 killed by its spawn tags with
  Penetration (50, 40 or 30 % by difficulty, over its types), every NATO unit left in the zone damaged 5 health points
  and stunned 240 points with `ChangeStress` ([[changestress-damagetype-zero]]); the Soviets finish the battalion, and
  the phase after it waits for its break.

**Still open:**
- Q3: whether `KillAllUnit` with DeathCause Penetration leaves wrecks, where Vanished removes the units
  ([[vanished-removal]]);
- whether the massed flash reads as big from the camera, and holds the frame rate;
- what `ChangeStress` Physical and Stun do to the survivors.

The effect is visual: nothing here suggests it kills. The scripts collect the units in a circle
([[detector-circles-only]]) and kill them themselves.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-twin-strike-strike-unseen](../trials/2026-11-11-twin-strike-strike-unseen.md)
- Gates: [`modkit.ops.gates.check_script_effects`](../../src/modkit/ops/gates.py)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/nuke.py`](../../examples/probes/probes/nuke.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-twin-strike-strike-unseen](../trials/2026-11-11-twin-strike-strike-unseen.md), [script-effects-self-contained](script-effects-self-contained.md)
<!-- referenced-by:end -->
