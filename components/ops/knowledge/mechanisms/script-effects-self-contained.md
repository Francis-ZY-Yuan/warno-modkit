---
id: script-effects-self-contained
title: A script launches a GameFx effect that takes no parameters, or a parameterised one through a wrapper of its own that binds them
status: PLAYED
last_verified: 210942 2026-11-12
source: play
topics: [units-and-orders, script-flow, game-updates]
gates: [modkit.ops.gates.check_script_effects]
shapes: [modkit.ops.bricks.fx_wrapper]
trials: [2026-11-10-probe3-play1-effect-crash, 2026-11-11-twin-strike-strike-unseen, 2026-11-11-fxprobe-play1, 2026-11-12-port-210942-survey, 2026-11-12-twin-strike-210942-play1]
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

**The exported wrapper.** A parameterised effect is reached as stock reaches one: `fx_FumeeNoire_ForScript_RandomPosition`
is a `TSimultaneousAction` whose `TActionCall` binds the parameter its burning-wreck effect has no default for. A
script may export such a wrapper of its own (`bricks.fx_wrapper`) and launch it by its export path. Played: the
tactical-nuke impact effect, its four parameters bound, played on its tag with no crash ([[scripted-nuke-effect]],
[[2026-11-11-fxprobe-play1]]).

**The gate.** `check_script_effects` (gate 3, `script-effects`) reads the shipped GDScript and fails the build when
it launches an effect that is not a GameFx export or one of the script's own exports, a GameFx effect whose
declaration takes parameters, or a wrapper whose call leaves a parameter with no default unbound.

**Seen in play.** Our own script launched the mega bomb, `feu_fx_script` and the black smoke in Twin Strike's smoke
play ([[2026-11-11-twin-strike-strike-unseen]]), and in the strike-effects probe's play the mega bomb, the 203 mm
barrage, the white and the black smoke, massed at stock's scale, with no crash ([[2026-11-11-fxprobe-play1]]).

**The cost.** In that probe, black smoke at 4 tags beside 10 mega bombs and 50 impacts of the 203 mm barrage grew
into huge plumes that lingered for minutes, and the game became slow, worse with time. Twin Strike's strike launches
no black smoke, yet its 210942 play slowed markedly after the strike, under huge dark plumes: black smoke is neither the
only cause nor the lasting one. An analysis of 210942's GameFx puts the lasting cost on the white smoke,
`fx_FumeeBlanche_ForScript_RandomPosition`, which the probe launched beside the black at the same 4 tags and Twin
Strike's strike at 2 spots ([[2026-11-12-twin-strike-210942-play1]]):
- read from the data: each launch's emitters (8 on its Big variant, 4 on Medium or Small) live 666 s, each spraying
  1 to 4 dark-grey puffs a second that grow to some 280 m and live up to 320 to 400 s, pushed 12.5 to 40 times by
  the map's wind; the black smoke is over in about 4 minutes; the tactical-nuke effect's particles (about 5,600 at
  the strike shot's camera) are gone within about 60 s, a mega bomb's (about 760) by 12.8 s and a 203 mm impact's
  (about 330) by 15 s;
- inferred: two white-smoke launches keep about 1,800 puffs alive from 2 to 11 minutes after the launch (some 3,800
  if both pick Big), the count rising for about 6 minutes, all gone 12 to 18 minutes on.

So the nuke's own cost is short-lived; the white smoke's lasts minutes. Not yet measured in play.

**On build 210942.** Twin Strike's strike launched the wrapped nuke and its accents of self-contained effects with no
crash ([[2026-11-12-twin-strike-210942-play1]]); the other plays above were on 201602. On 210942 the game reads its
GameFx from `NDF/GFX/GameFx.txn` in Transactions.dat (the gate reads that file: `gates.gamefx_file`), and every GameFx object
names itself with `_NdfIdentifierName` where 201602 wrote `_ShortDatabaseName`, so the wrapper writes the new name
(`bricks.NAME_PROP`). The stock launches are unchanged: 75 in 7 stock scripts, the same three self-contained effects,
each a `LaunchFXFireAndForgetOnPosition` of `DatabaseName` and `Position`. The script's root, which holds every launch,
is now `TGDDescriptorLaunchEffetMap` ([[scenario-definition-layout]], [[2026-11-12-port-210942-survey]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-11-twin-strike-strike-unseen](../trials/2026-11-11-twin-strike-strike-unseen.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md)
- Gates: [`modkit.ops.gates.check_script_effects`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.bricks.fx_wrapper`](../../src/modkit/ops/bricks.py)
- Skills: [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/fxprobe.py`](../../examples/probes/probes/fxprobe.py), [`components/ops/examples/probes/probes/nuke.py`](../../examples/probes/probes/nuke.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-11-twin-strike-strike-unseen](../trials/2026-11-11-twin-strike-strike-unseen.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [game-build-classes](game-build-classes.md), [scripted-fires](scripted-fires.md), [scripted-nuke-effect](scripted-nuke-effect.md)
<!-- referenced-by:end -->
