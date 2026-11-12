---
id: camera-shot-from-current-position
title: Mid-battle, a script flies the camera from wherever it is to a one-key path, in a cutscene that can hold the view
status: STOCK
last_verified: 201602 2026-11-11
source: stock-data
topics: [zones-and-map, script-flow]
gates: [modkit.ops.maps.check_camera_paths]
shapes: [modkit.ops.bricks.g_camera, modkit.ops.maps.CameraShot]
trials: [2026-11-11-strike-camera-stock-survey]
stock_precedent: 18 CutsceneStartCameraPath nodes in 5 challenges set StartFromCurrentCameraPosition, 10 in the order g_camera writes; 17 fly a one-key path, in 3 to 37 s; their keys stand 97,021 to 433,526 above the ground, 26.5 to 40 degrees down
---
**What stock does.** To show the player something mid-battle, stock flies the camera from wherever the player left it
to a one-key camera path: `CutsceneStartCameraPath` with `StartFromCurrentCameraPosition`, a `TimeInSecond`, easing
in and out, skippable with Escape, in an `EncapsuleCutscene` that blocks the player's actions
([[2026-11-11-strike-camera-stock-survey]]):
- SigurdsStrike's MLRS and COBRA shots (#1211, #1216: 3 s), beside the units they show moving, in one Simultaneous
  (#870): the battle runs on while the camera flies;
- Sledgehammer's camera_hades and camera_viper (#737, #739: 5 s), camera_Industrial (10 s);
- BlackHorsesLastStand's cam_01 and cam_02 (8 s and 6 s), TheDieburgSalient's cam_start (6 s).

The path is one key, the view the camera ends on; the eye and the direction come from the paths file
(`CamPaths_LevelDesign.ndfbin`), as an opening camera's do ([[start-camera-before-loading-done]]).

**Holding the view.** A cutscene runs its children in turn inside a `CutsceneSequential` (BackhandBlow #108 holds four
camera paths), and `CutsceneWaitDuree` waits inside one (HoldUntilRelieved #147/#185). So
`EncapsuleCutscene[CutsceneSequential[the path, CutsceneWaitDuree]]` flies the camera, then holds the view before
control returns. That pair is stock's shapes, not a stock sequence: no stock script holds a camera shot this way.

**The toolkit.** `maps.CameraShot` is such a shot: a name, a `CameraKey`, the move's seconds and the hold. It ships in
its `OpeningCamera`'s paths file, held to the camera gate (`check_camera_paths`): one key, its view inside the cut, its
eye over the map and above stock's lowest start camera (376,057), though stock's mid-battle shots go as low as
97,021. `CameraShot.cutscene` is `bricks.g_camera(name, seconds, from_current=True, hold=...)`.

**Not yet seen in play:** a shot of our own, whether Escape also ends the hold, and whether the player's camera stays
on the held view.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-strike-camera-stock-survey](../trials/2026-11-11-strike-camera-stock-survey.md)
- Gates: [`modkit.ops.maps.check_camera_paths`](../../src/modkit/ops/maps.py)
- Shapes: [`modkit.ops.bricks.g_camera`](../../src/modkit/ops/bricks.py), [`modkit.ops.maps.CameraShot`](../../src/modkit/ops/maps.py)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/map.py`](../../examples/twin-strike/twinstrike/map.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [scripted-nuke-effect](scripted-nuke-effect.md)
<!-- referenced-by:end -->
