---
id: scripted-economy
title: A script sets the player's points, a zero income, one-time grants and a later income in stock's own nodes
status: STOCK
last_verified: 201602 2026-11-11
source: stock-data
topics: [operation-setup, script-flow]
shapes: [modkit.ops.bricks.g_income, modkit.ops.bricks.g_grant, modkit.ops.script.deploy_phase]
trials: [2026-11-11-twin-strike-play1]
stock_precedent: SetIncomeToTeam with no amount in RunningTheGauntlet (3/3 difficulties); 14 GiveRessourceToTeam in 4 Operations, 13 last in their container or in a Simultaneous; a mid-battle SetIncomeToTeam after a WaitCondition in TheWingedHussars (3)
---
**What stock does.** Under rules with scripted income only (`EnableOnlyScriptedIncome`, Survivors' among them),
points come only from the script:
- `SetRessourceForTeam` sets the bank (the start points: 250 to 2,500, [[deployment-phase-recipe]]);
- `SetIncomeToTeam` sets the income from then on. A zero income is written with no amount at all: RunningTheGauntlet
  #275/#286/#296 give the player a fixed start and no income, never an explicit 0 (a written 0 is the form to avoid);
  TheWingedHussars #318 turns an income on mid-battle, in a Sequential after the WaitCondition of its event;
- `GiveRessourceToTeam` grants points once: BlackHorsesLastStand #312 in a Simultaneous after a wait, RunningTheGauntlet
  #245-#249 as each roadblock falls, Marauders #1078 on an objective's success.

`GiveIncomeToTeam` (adds to the income) and `LockIncome` (freezes it while it lives) never finish
([[seteffect-never-finishes]]): a Competition[LockIncome, WaitCondition] is TheWingedHussars' "no income until X"
shape. `SetMaxMoneyForTeam` caps the bank in RunningTheGauntlet only, beside a larger start, so how it treats a start
above the cap is not known.

**Twin Strike** deploys on 2,000 with no income, then at the village's fall grants 4,000 in a Simultaneous and sets an
income of 250 ([[2026-11-11-twin-strike-play1]]: 4,000 at the start with an income of 150 ran short against the
first counter-attack). The toolkit writes a zero income as stock does (`bricks.g_income`), so only a content that asks
for one changes.

**Not seen in play:** a zero start income, a grant above stock's largest (1,200), and an income turned on mid-battle
for a player who had none. The income's period is read from the game's constants (60 s), not seen.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Shapes: [`modkit.ops.bricks.g_income`](../../src/modkit/ops/bricks.py), [`modkit.ops.bricks.g_grant`](../../src/modkit/ops/bricks.py), [`modkit.ops.script.deploy_phase`](../../src/modkit/ops/script.py)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md), [seteffect-never-finishes](seteffect-never-finishes.md)
<!-- referenced-by:end -->
