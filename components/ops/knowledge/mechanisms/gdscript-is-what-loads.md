---
id: gdscript-is-what-loads
title: Build 201602 runs an Operation from its GDScript ndfbin, a compiled form of the stock Python
status: PLAYED
last_verified: 201602 2026-11-06
source: stock-data
topics: [script-flow, files-and-formats, game-updates]
trials: [2026-11-02-gdscript-format-survey, 2026-11-02-leveldesign-api-survey, 2026-11-02-kreide-op-playtest-1, 2026-11-06-probe2-play-run-a]
stock_precedent: 27,151 of 27,151 Python constructor calls in 29 scenarios map to exactly one GDScript object
---
**What the game does.** For Operations and campaigns, build 201602 loads `NDF/Scenarios/GDScript/<scenario>.ndfbin`
from the Definition pack. The game's level-launch table switched from the Python mission module to the GDScript in
this build, and no 201602 data names the Python module. The compiled Python (`effetmap.xyz`) still ships but is not
what runs. No Python runs during a battle: the graph is built once and native code runs it.

**The mapping.** GDScript is a 1:1 compiled form of the stock Python graph: each constructor call is one object
of the wrapper's native class, property names are the Python keyword-argument names (not the setter names), and
arguments at their default are left out. So the shipped Python form of a stock script, once read, is a readable reference for writing GDScript.

**Gotchas.**
- A GDScript holds exported editor nodes that no Python call makes, plus merged dialog, sound, video and texture
  resources. Both forms come from a common editor source; clone stock objects rather than re-deriving them.
- Cutscene resources are found through the GDScript, so it must load even for a film.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-gdscript-format-survey](../trials/2026-11-02-gdscript-format-survey.md), [2026-11-02-kreide-op-playtest-1](../trials/2026-11-02-kreide-op-playtest-1.md), [2026-11-02-leveldesign-api-survey](../trials/2026-11-02-leveldesign-api-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Skills: [`components/core/skills/warno-setup/references/scenario-python-and-prior-art.md`](../../../core/skills/warno-setup/references/scenario-python-and-prior-art.md), [`components/core/skills/warno-setup/references/stock-corpus.md`](../../../core/skills/warno-setup/references/stock-corpus.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
- Records: [edat-revision-chain](../../../core/knowledge/mechanisms/edat-revision-chain.md)
<!-- referenced-by:end -->
