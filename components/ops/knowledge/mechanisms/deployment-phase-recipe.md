---
id: deployment-phase-recipe
title: A deployment phase needs six parts, and buying after the launch needs player arrival entries
status: PLAYED
last_verified: 201602 2026-11-03
source: stock-data
topics: [operation-setup, zones-and-map]
gates: [modkit.ops.gates.check_arrivals]
shapes: [modkit.ops.script.deploy_phase, modkit.ops.script.hud_restore]
trials: [2026-11-03-probe1-launch3-no-arrivals, 2026-11-03-probe1-play1-worked, 2026-11-03-probe1-play2-land-buys]
stock_precedent: every stock Operation with a deployment phase has 2 to 8 player reinforcement locations; all but one also have an aerial corridor
---
**What the game does.** A stock deployment phase comes from:
1. `InitialGamePhase = 1` in the rules;
2. a `TGameDesignAddOn_DeploymentZone` polygon per side in `out/DeploymentZone.ndfbin`, with a matching LevelDesign
   item;
3. a scripted `SetRessourceForTeam` (start points: 250 to 2,500, usually 1,000 to 1,500);
4. `SetIncomeToTeam` when the rules set `EnableOnlyScriptedIncome`;
5. `ForceDisplayUIElement` with the production menu shown (and usually the "Launch battle" button);
6. player `ReinforcementLocation` and `AerialCorridor` entries, where units bought after the launch arrive
   ([[arrival-end-in-zone]]).

**Gotchas.**
- Survivors, the usual template, starts in the Command phase with none of this, because its player never buys.
  Cloning it and adding a deployment phase drops part 6 unless it is checked; that is exactly what happened.
- Gate every post-launch beat on `ConditionPhase(Command)`, as stock does: whether script time runs during the
  deployment phase is not known.
- No deck that `SetDeck` can address holds a FOB. A FOB reaches the player only pre-placed in LevelDesign or created
  by script.
- No stock deck mixes NATO and PACT units ([[add-unit-to-deck]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-arrivals](../trials/2026-11-02-kreide-op-arrivals.md), [2026-11-03-probe1-launch3-no-arrivals](../trials/2026-11-03-probe1-launch3-no-arrivals.md), [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-03-probe1-play2-land-buys](../trials/2026-11-03-probe1-play2-land-buys.md)
- Gates: [`modkit.ops.gates.check_arrivals`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.script.deploy_phase`](../../src/modkit/ops/script.py), [`modkit.ops.script.hud_restore`](../../src/modkit/ops/script.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [custom-operation-from-stock-parts](custom-operation-from-stock-parts.md), [scripted-economy](scripted-economy.md)
<!-- referenced-by:end -->
