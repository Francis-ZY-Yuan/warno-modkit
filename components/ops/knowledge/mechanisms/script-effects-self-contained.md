---
id: script-effects-self-contained
title: A script may launch only a self-contained effect, one that takes no parameters
status: STOCK
last_verified: 201602 2026-11-10
source: stock-data
topics: [units-and-orders, script-flow]
gates: [modkit.ops.gates.check_script_effects]
trials: [2026-11-10-probe3-play1-effect-crash]
stock_precedent: stock scripts launch exactly three effects, all self-contained and all from FX_script.ndf: fx_FumeeBlanche_ForScript_RandomPosition (45 launches), fx_HE_Artillery_203mm_ForScript_RandomPosition (27) and fx_FumeeNoire_ForScript_RandomPosition (3)
---
**The rule.** A script's `LaunchFXFireAndForgetOnPosition` carries only an effect's name (`DatabaseName`,
`$/GFX/GameFx/...`) and a position. The game looks the name up among the exports of its GameFx namespace
(`NDF/GFX/GameFx.ndfbin`). An effect whose declaration takes parameters (a `Params` block of `TActionAlias` or
`Template_Param_*`, compiled as `InputParameters`) waits for its caller to bind them, as the impact system does when
a shell lands; a script launch binds nothing. So a script launches only an effect that declares none. A launch of
the tactical-nuke impact effect, which declares its position, direction and radii, crashed the game
([[scripted-nuke-effect]]).

**Stock.** The 31 stock GDScripts hold 75 effect launches, in seven challenges, and they name only the three effects
above. The game's script-only effects (the 14 named `*ForScript*`) take no parameters; 1,437 of GameFx's 1,656
exports do. `fx_HE_Mega_Bomb_ForScript` is self-contained and named for scripts, but no stock scenario launches it.

**The gate.** `check_script_effects` (gate 3, `script-effects`) reads the shipped GDScript and fails the build when
it launches an effect that is not a GameFx export, or one whose declaration takes parameters.

Not yet seen in play: a self-contained effect launched by our own script (the third probe's replay asks).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md)
- Gates: [`modkit.ops.gates.check_script_effects`](../../src/modkit/ops/gates.py)
- Skills: [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/nuke.py`](../../examples/probes/probes/nuke.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [scripted-fires](scripted-fires.md), [scripted-nuke-effect](scripted-nuke-effect.md)
<!-- referenced-by:end -->
