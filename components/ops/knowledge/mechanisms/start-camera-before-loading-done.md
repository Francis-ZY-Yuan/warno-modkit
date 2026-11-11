---
id: start-camera-before-loading-done
title: Snap a start camera before LoadingDone, or the camera starts in a map corner
status: STOCK
last_verified: 201602 2026-11-11
source: stock-data
topics: [zones-and-map]
shapes: [modkit.ops.bricks.g_camera, modkit.ops.maps.StartCamera]
trials: [2026-11-02-kreide-op-playtest-1-camera, 2026-11-03-probe1-launch2-dialog-buttons]
---
**What stock does.** Five stock challenges start a camera path right before `LoadingDone`, each in an
`EncapsuleCutscene` that `LoadingDone` follows in the same Sequential: BackhandBlow (#74 with camera path #197, then
#75), BlackHorsesLastStand (#73/#145, then #74), Gotterdammerung (#92/#148, then #93), RedJuggernaut (#74/#127, then
#75) and TheKitzingenRuse (#87/#143, then #88). Survivors does not: its camera paths (`intro` #880 among them) run in
its intro cutscene, after `LoadingDone` (#122). An Operation that starts no camera starts with it fixed in one map
corner, as the first probe did. Camera paths cloned from the map's own layout, or one-key camera paths, give the
opening view.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-playtest-1-camera](../trials/2026-11-02-kreide-op-playtest-1-camera.md), [2026-11-03-probe1-launch2-dialog-buttons](../trials/2026-11-03-probe1-launch2-dialog-buttons.md)
- Shapes: [`modkit.ops.bricks.g_camera`](../../src/modkit/ops/bricks.py), [`modkit.ops.maps.StartCamera`](../../src/modkit/ops/maps.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py)
- Records: [custom-operation-from-stock-parts](custom-operation-from-stock-parts.md)
<!-- referenced-by:end -->
