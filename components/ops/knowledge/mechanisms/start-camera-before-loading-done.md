---
id: start-camera-before-loading-done
title: An Operation that opens in the deployment phase sets its opening camera after LoadingDone, a move then a snap to its last key
status: STOCK
last_verified: 201602 2026-11-11
source: stock-data
topics: [zones-and-map]
gates: [modkit.ops.maps.check_camera_paths]
shapes: [modkit.ops.bricks.g_camera, modkit.ops.maps.OpeningCamera, modkit.ops.mission.script_frame]
trials: [2026-11-02-kreide-op-playtest-1-camera, 2026-11-03-probe1-launch2-dialog-buttons, 2026-11-11-twin-strike-opening-camera, 2026-11-11-opening-camera-stock-survey]
stock_precedent: all 12 stock Operations that open in the deployment phase run a camera path after LoadingDone; DelayedRetribution (#64/#92 then #65/#79), GloryOrAttrition (#61/#96, #62/#74) and TheHydra (#72: #167, #168) open with a move, then a snap to its last key, before the HUD returns
---
**What stock does.** Twelve of the 16 stock Operations open in the deployment phase (GameRules `InitialGamePhase`
1), and every one runs a camera path after its `LoadingDone` ([[2026-11-11-opening-camera-stock-survey]]). None
relies on its deployment zones' `WarmupCamPath`: six name none, six name a path their camera paths file lacks. The
usual opening, with the HUD still hidden:
- an `EncapsuleCutscene` (`BlockPlayerActions`) flies a camera path of two keys or more in `TimeInSecond`, easing in
  and out (`AccelerationActivated`, `DecelerationActivated`; `BaseCamera`'s camera-path mover ramps 2 s each way),
  skippable with Escape: DelayedRetribution #92 (`camera_intro`, 2 keys in 20 s), GloryOrAttrition #96 (15 s),
  TheHydra #167 (20 s), RunningTheGauntlet #210 (5 keys in 20 s, easing in only);
- a second cutscene snaps to a one-key path at the move's last key, to within a world unit, so a skipped move ends
  there too: DelayedRetribution #65/#79, GloryOrAttrition #62/#74, TheHydra #168 (in the move's own cutscene),
  RunningTheGauntlet #95/#118. Then the HUD returns (DelayedRetribution #67, GloryOrAttrition #63, TheHydra #73);
- longer intros chain two-key paths of 5 to 17 s in a `CutsceneSequential`, beside their dialogs: Gotterdammerung,
  TheKitzingenRuse, Marauders, RedJuggernaut.

Eleven of the twelve hand the camera over 312,898 to 604,542 world units above the ground, 34.7 to 40 degrees down,
where their opening move ends; RunningTheGauntlet's, 119,565 up, is a close-up of its convoy.

Six stock challenges also start a camera path right before `LoadingDone`, in an `EncapsuleCutscene` beside their
full-screen intro video, which `LoadingDone` follows in the same Sequential: BackhandBlow (#74 with camera path #197,
then #75), BlackHorsesLastStand (#73/#145, then #74), Gotterdammerung (#92/#148, then #93), RedJuggernaut (#74/#127,
then #75), TheKitzingenRuse (#87/#143, then #88) and Sledgehammer (#180/#304, then #181). The first five open in the
deployment phase and run their opening move after `LoadingDone` too, starting where the snap put the camera
(RedJuggernaut's `CamStart` is `Elena_Dmitri`'s first key) or snapping again (BackhandBlow #158, Gotterdammerung
#133). Their keys stand 376,057 (BlackHorsesLastStand's `camera_start`) to 773,047 above the ground, 39.3 to 40
degrees down. Sledgehammer's, in an Operation that opens in the Command phase, stands at the ground: a shot its intro
climbs from. Survivors runs its camera paths (`intro` #880 among them) in its intro cutscene, after `LoadingDone`
(#122). The game reads the paths from the scenario's Details, `CamPaths_LevelDesign.ndfbin` (`BaseCamera`'s
`CameraPaths`), each path one unexported root of that file.

**Seen in play.**
- With no camera action, an Operation starts on the engine's default camera, in a map corner or on the ground
  ([[2026-11-02-kreide-op-playtest-1-camera]], [[2026-11-03-probe1-launch2-dialog-buttons]]).
- The Kreide Operation, which opened in the Command phase, opened over its town once its script snapped a one-key path
  right before `LoadingDone` (the play after [[2026-11-02-kreide-op-playtest-1-camera]]).
- Twin Strike, which opens in the deployment phase, made the same snap: a stock-shaped key 297,725 above the ground,
  37 degrees down over the village. Its opening view sat on the ground
  ([[2026-11-11-twin-strike-opening-camera]]). In a deployment-phase Operation, the phase's start at `LoadingDone`
  loses a camera set before it.

**What we build.** `modkit.ops.maps.OpeningCamera`: a move of two keys or more, then a snap to its last key, run
right after `LoadingDone` and before the HUD returns (`mission.script_frame`'s `opening`), each an `EncapsuleCutscene`
from `bricks.g_camera`. Its file is held to the camera gate (`maps.check_camera_paths`): stock's key shape, every eye
over the map, every key at least 376,057 above the ground, the last view inside the cut.

**Not seen in play:** Twin Strike's opening move; what the deployment phase reads when it sets the camera (the
deployment zones' `WarmupCamPath` is the likely field, unfilled in Twin Strike as in stock's challenges). The record's
ID keeps its first finding's name.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-playtest-1-camera](../trials/2026-11-02-kreide-op-playtest-1-camera.md), [2026-11-03-probe1-launch2-dialog-buttons](../trials/2026-11-03-probe1-launch2-dialog-buttons.md), [2026-11-11-opening-camera-stock-survey](../trials/2026-11-11-opening-camera-stock-survey.md), [2026-11-11-twin-strike-opening-camera](../trials/2026-11-11-twin-strike-opening-camera.md)
- Gates: [`modkit.ops.maps.check_camera_paths`](../../src/modkit/ops/maps.py)
- Shapes: [`modkit.ops.bricks.g_camera`](../../src/modkit/ops/bricks.py), [`modkit.ops.maps.OpeningCamera`](../../src/modkit/ops/maps.py), [`modkit.ops.mission.script_frame`](../../src/modkit/ops/mission.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-opening-camera](../trials/2026-11-11-twin-strike-opening-camera.md), [camera-shot-from-current-position](camera-shot-from-current-position.md), [custom-operation-from-stock-parts](custom-operation-from-stock-parts.md)
<!-- referenced-by:end -->
