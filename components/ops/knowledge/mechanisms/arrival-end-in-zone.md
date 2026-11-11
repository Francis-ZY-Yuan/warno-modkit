---
id: arrival-end-in-zone
title: Every player arrival entry must end inside a deployment zone of its side or a command zone
status: STOCK
last_verified: 201602 2026-11-04
source: stock-data
topics: [zones-and-map, units-and-orders]
gates: [modkit.ops.gates.check_arrivals]
trials: [2026-11-02-kreide-op-arrivals, 2026-11-03-probe1-play2-land-buys, 2026-11-03-arrival-end-stock-sweep, 2026-11-03-play2-stock-survey, 2026-11-04-zone-capture-survey, 2026-11-06-spawns-and-deck-survey]
stock_precedent: 83/83 player arrival Ends (57 reinforcement locations, 26 aerial corridors) lie in a same-side deployment zone or a command zone; 48 of the 57 in a deployment zone
---
**What the game does.** A unit bought after the launch arrives along a `ReinforcementLocation` (land) or
`AerialCorridor` (air) entry. The game gives each entry to the side that owns the zone its End point lies in,
deployment zones first, then command zones, and a side can only produce from entries it holds. Every stock player
entry keeps its End inside a zone.

**How we know.** Twice an Operation of ours had its player Ends outside every zone, and both times nothing bought on
land ever arrived, while aircraft still did. Moving the Ends inside the player's deployment zone is the fix stock
supports 83 of 83 times; the exact land-only failure was not traced in the game's code.

**Gotchas.**
- An End inside a player deployment zone is the player's for the whole battle; a deployment zone's owner never
  changes.
- An End that lies only in a command zone changes hands with that zone. If the enemy takes or contests the zone, the
  player loses that entry. Keep at least one permanent entry in a player deployment zone.
- Counting the entries is not checking them: the arrivals gate must read the shipped zone polygons.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-arrivals](../trials/2026-11-02-kreide-op-arrivals.md), [2026-11-03-arrival-end-stock-sweep](../trials/2026-11-03-arrival-end-stock-sweep.md), [2026-11-03-play2-stock-survey](../trials/2026-11-03-play2-stock-survey.md), [2026-11-03-probe1-play2-land-buys](../trials/2026-11-03-probe1-play2-land-buys.md), [2026-11-04-zone-capture-survey](../trials/2026-11-04-zone-capture-survey.md), [2026-11-06-spawns-and-deck-survey](../trials/2026-11-06-spawns-and-deck-survey.md)
- Gates: [`modkit.ops.gates.check_arrivals`](../../src/modkit/ops/gates.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [deployment-phase-recipe](deployment-phase-recipe.md)
<!-- referenced-by:end -->
