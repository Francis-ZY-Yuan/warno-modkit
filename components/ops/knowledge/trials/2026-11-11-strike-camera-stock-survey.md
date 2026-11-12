---
id: 2026-11-11-strike-camera-stock-survey
kind: survey
build: f05687d
game_version: 201602
mechanisms: [camera-shot-from-current-position]
outcome: pass
result: Stock flies the camera mid-battle from the player's current view to a one-key path, mostly in 3 to 10 s, blocking the player's actions; Twin Strike's strike does the same with TS_Strike
---
Read every `CutsceneStartCameraPath` of the 16 stock challenges' GDScripts that sets `StartFromCurrentCameraPosition`,
the cutscene around it, and its path in the challenge's `CamPaths_LevelDesign.ndfbin`:
- 18 nodes in 5 challenges (BackhandBlow, BlackHorsesLastStand, SigurdsStrike, Sledgehammer, TheDieburgSalient); 10
  of them write `CameraPathName`, `TimeInSecond`, `AccelerationActivated`, `DecelerationActivated`,
  `StartFromCurrentCameraPosition`, `CanBeSkippedWithEscape`, `VisibleByAlliedOfSpecifiedCamp`, in that order.
- 17 fly a one-key path (BackhandBlow's camera_intro2 has two keys at one eye), in 3 to 37 s; SigurdsStrike's shots
  and Sledgehammer's camera_hades, camera_viper and camera_Industrial, beside the battle, take 3 to 10 s. Their keys stand 97,021 to 433,526 world units above the ground, 26.5 to 40 degrees down.
- SigurdsStrike's MLRS shot runs in a Simultaneous beside a blocking unit move: the battle goes on during the shot.
- `CutsceneWaitDuree` has one property, `WaitDuration`, and stands in a `CutsceneSequential` (9 nodes, HoldUntilRelieved,
  RedJuggernaut, Sledgehammer).

Pinned by `test_opening_camera.Stock.test_mid_battle_shots_fly_one_key_from_the_current_camera`.
