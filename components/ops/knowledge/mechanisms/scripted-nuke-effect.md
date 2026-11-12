---
id: scripted-nuke-effect
title: A script plays the tactical-nuke impact effect only through a wrapper of its own that binds its parameters; a direct launch crashes the game
status: PLAYED
last_verified: 201602 2026-11-11
source: play
topics: [script-flow, units-and-orders]
gates: [modkit.ops.gates.check_script_effects]
shapes: [modkit.ops.bricks.fx_wrapper, modkit.ops.shapes.nuke_wrapper]
trials: [2026-11-10-probe3-play1-effect-crash, 2026-11-11-twin-strike-strike-unseen, 2026-11-11-fxprobe-play1, 2026-11-12-port-210942-survey]
stock_precedent: no stock script launches an impact effect; stock's script-launched fx_FumeeNoire_ForScript_RandomPosition reaches a parameterised effect through a TActionCall that binds its parameter, the wrapper's shape
---
**What the data says.** The game has the tactical-nuke impact effect under two names: `$/GFX/GameFx/fx_impact_sol_Tactical_Nuke`
(the ground-impact wrapper, which plays the second) and `$/GFX/GameFx/fx_impact_Tactical_Nuke`. The impact-mapping
table keys the first to an impact named `ArtillerieM185155MmNUKE`, which no ammunition uses, so the effect is reachable in
the data and in no stock fire.

**A direct launch crashes.** The third probe's first play launched either name with `LaunchFXFireAndForgetOnPosition`,
and the game crashed during the deploy phase ([[2026-11-10-probe3-play1-effect-crash]]). Both names are parameterised
impact actions: the first declares four parameters (position, direction and two radii) with no defaults; the second
five, with defaults, and passes the position down to its flash. The impact system binds them when a shell lands; a
script launch carries only a name and a position, so nothing binds them ([[script-effects-self-contained]]).

**Through a wrapper of the script's own, it plays.** Stock shows the way: its script-launched
`fx_FumeeNoire_ForScript_RandomPosition` is a `TSimultaneousAction` whose `TActionCall` binds the one parameter its
burning-wreck effect has no default for. The script exports such a wrapper of the nuke's own
(`shapes.nuke_wrapper`, over `bricks.fx_wrapper`): a `TActionCall` of `fx_impact_sol_Tactical_Nuke` binding all four
(parPosition, parDirection 0, parRadiusPhysical, parRadiusSuppress), and the launch names the wrapper's export path.
In the strike-effects probe's play ([[2026-11-11-fxprobe-play1]]), with no crash:
- parPosition 0 (F8): a large nuclear fireball and dust cloud on the launch's tag, not at the map's corner;
- parPosition the tag's world position (F9): the same, on its tag; the player: "big nuke effect";
- neither killed anything: the effect is visual, and the script kills by itself ([[detector-circles-only]]).
parRadiusPhysical was 60,000 world units (some 280 m); it sizes the effect's ground scorch and the scenery it destroys.
The build's script-effects gate holds each wrapper's call to bind every parameter its effect declares with no default,
and still refuses a direct launch of either name.

**Self-contained alternatives, and their cost.** `fx_HE_Mega_Bomb_ForScript`, the game's script-only mega bomb, is
about a 203 mm shell's size: dust some 47 m out, gone within 10 s. One of them on Twin Strike's 800 m zone, off screen
and in fog, read as small explosions ([[2026-11-11-twin-strike-strike-unseen]]). Massed with the 203 mm barrage, they
show as many scattered bursts that leave craters; black smoke beside them grew into huge lingering plumes and slowed the
game, worse with time (the probe's F4).

**Twin Strike's strike now** (built, not yet played; design 5.6 of its `docs/design.md`): the nuke once through its
wrapper on the zone's centre, at its world position, with a light accent of 18 self-contained launches and no black
smoke; the camera flown to the zone ([[camera-shot-from-current-position]]); half a second on, a share of battalion 2
killed and the rest damaged and stunned ([[changestress-damagetype-zero]]).

**Still open:** Q3, whether `KillAllUnit` with DeathCause Penetration leaves wrecks (in the probe, the smoke hid them),
where Vanished removes the units ([[vanished-removal]]); the nuke's sound and shake, and its cost to the frame rate on
its own.

**On build 210942: unverified in play.** The plays above were on 201602. On 210942 `fx_impact_sol_Tactical_Nuke` still
declares the same four parameters with no defaults, the wrapper binds them as before, and it now names itself with
`_NdfIdentifierName` (GameFx's own name property since 210942, [[script-effects-self-contained]]). Whether the wrapped
nuke still plays, and plays the same, is for the next play to show ([[2026-11-12-port-210942-survey]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-11-twin-strike-strike-unseen](../trials/2026-11-11-twin-strike-strike-unseen.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md)
- Gates: [`modkit.ops.gates.check_script_effects`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.bricks.fx_wrapper`](../../src/modkit/ops/bricks.py), [`modkit.ops.shapes.nuke_wrapper`](../../src/modkit/ops/shapes.py)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/fxprobe.py`](../../examples/probes/probes/fxprobe.py), [`components/ops/examples/probes/probes/nuke.py`](../../examples/probes/probes/nuke.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-11-twin-strike-strike-unseen](../trials/2026-11-11-twin-strike-strike-unseen.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md), [script-effects-self-contained](script-effects-self-contained.md)
<!-- referenced-by:end -->
