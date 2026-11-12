---
id: custom-operation-from-stock-parts
title: A custom Operation can be built entirely from cloned stock files plus a generated LevelDesign and GDScript
status: PLAYED
last_verified: 201602 2026-11-06
source: play
topics: [operation-setup]
trials: [2026-11-02-new-scenario-id-loads, 2026-11-02-kreide-op-playtest-1, 2026-11-03-probe1-play1-worked, 2026-11-06-probe2-play-run-a]
---
**What we built.** A custom Operation on Kreide and two probe Operations on Geisa, none made in Eugen's editor:
- **Definition:** Survivors' runtime files cloned, with a new GDScript, the Trophy file (TrophyDef on 210942) dropped,
  and about 20 identity fields changed; on 210942 each file ships with its tag and source map
  ([[scenario-definition-layout]]).
- **Details:** zones and camera paths cloned from the map's own multiplayer layout, then a generated LevelDesign,
  playable zone, AI grid and zone files.
- **Assets:** small dictionaries and the menu textures; no voice, video or Python is needed.
- **GDScript:** every object cloned from a named stock template.

**Gotchas.**
- Survivors is the usual template because the script alone decides its outcome, but it has no deployment phase and
  its player never buys ([[deployment-phase-recipe]]).
- The AI grid must match the playable zone ([[ai-grid-tiles-playable-zone]]), and the opening camera needs a script,
  run after `LoadingDone` in an Operation that opens in the deployment phase ([[start-camera-before-loading-done]]).
- A fourth camp, AI-controlled, on the player's side works (the first probe's decoys).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-playtest-1](../trials/2026-11-02-kreide-op-playtest-1.md), [2026-11-02-new-scenario-id-loads](../trials/2026-11-02-new-scenario-id-loads.md), [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md)
<!-- referenced-by:end -->
