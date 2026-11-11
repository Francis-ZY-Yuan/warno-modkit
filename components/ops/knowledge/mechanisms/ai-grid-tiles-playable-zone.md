---
id: ai-grid-tiles-playable-zone
title: The AI strategic grid must tile the playable zone
status: PLAYED
last_verified: 201602 2026-11-03
source: play
topics: [zones-and-map, loading-and-crashes]
gates: [modkit.ops.gates.check_details_generators]
shapes: [modkit.ops.zones.read_ia_grid, modkit.ops.zones.ia_grid_subset, modkit.ops.zones.ia_zone_graph, modkit.ops.zones.playable_zone_graph, modkit.ops.maps.Cut]
trials: [2026-11-02-kreide-op-playtest-1-camera, 2026-11-02-kreide-op-ai-grid-crash, 2026-11-03-probe1-play1-worked]
---
**What the game does.** In stock, the AI strategic grid (`out/IAStratZone`, `out/IAStrat_PathCache`) tiles the
PlayableZone. In all 18 stock layouts with a playable zone, the tiles' extent matches the zone's bbox to within 5,792
world units, against tiles 30,960 to 491,520 a side, and the path cache holds every pair of tiles once per navigation
graph. A whole-map grid under a smaller playable zone crashed the game while loading the Operation, at the same place
every time.

**The shape.** Build the grid as the subset of the map's own grid that lies in the playable zone (`ia_grid_subset`),
with every edge of the zone on a tile edge, so that the kept tiles cover it exactly. That tile-aligned cut is the
builders' convention, not stock's: most stock zones sit a little off their tiles. The Details generators are proven
by rebuilding stock files byte for byte from their own values (`check_details_generators`). `maps.Cut` ships such a
cut of a stock layout and holds it.

**Gotcha: stock grids have seams.** Twin Cities' small layout `SM_SU_3x3_TwinCities_03` puts its tiles up to 320
world (1/8 minimap px) off their neighbours' edges, as gaps and as overlaps, so no box covers its tiles exactly.
`check_grid_subset`'s `seam` (the map's `StockMap.grid_seam`) counts edges that close as one edge. It never fills a
missing tile, and the box's own edges stay exact tile edges.

**The checks.** `check_grid` holds a shipped grid to stock's rule, and `check_grid_subset` holds a tile-aligned cut to
it with no tolerance beyond the grid's own seam. Like `check_details_generators`, they are extra gates: the build driver runs one only when an
op's profile names it (`OpProfile.extra_gates`).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-ai-grid-crash](../trials/2026-11-02-kreide-op-ai-grid-crash.md), [2026-11-02-kreide-op-playtest-1-camera](../trials/2026-11-02-kreide-op-playtest-1-camera.md), [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md)
- Gates: [`modkit.ops.gates.check_details_generators`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.zones.read_ia_grid`](../../src/modkit/ops/zones.py), [`modkit.ops.zones.ia_grid_subset`](../../src/modkit/ops/zones.py), [`modkit.ops.zones.ia_zone_graph`](../../src/modkit/ops/zones.py), [`modkit.ops.zones.playable_zone_graph`](../../src/modkit/ops/zones.py), [`modkit.ops.maps.Cut`](../../src/modkit/ops/maps.py)
- Skills: [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py), [`components/ops/examples/twin-strike/twinstrike/profile.py`](../../examples/twin-strike/twinstrike/profile.py)
- Records: [custom-operation-from-stock-parts](custom-operation-from-stock-parts.md)
<!-- referenced-by:end -->
