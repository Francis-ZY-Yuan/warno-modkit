---
id: 2026-11-11-opening-camera-stock-survey
kind: survey
build: 964e803
game_version: 201602
mechanisms: [start-camera-before-loading-done]
outcome: pass
result: Stock sets a deployment-phase Operation's opening camera after LoadingDone, a move then a snap to its last key; its start cameras stand 376,057 or more above the ground
---
Read every camera path of the 16 stock challenges (their `CamPaths_LevelDesign.ndfbin`, the 35 camera paths files of
the shape gate's sources), every `CutsceneStartCameraPath` of their GDScripts with its place against `LoadingDone`,
their GameRules and their deployment zones' `WarmupCamPath`, and `BaseCamera`'s camera-path mover:
- Twelve open in the deployment phase, and each runs a camera path after `LoadingDone`. None relies on a
  `WarmupCamPath`: six name none, six name a path their file lacks.
- An opening move is a path of two keys or more with `TimeInSecond` (5 to 60 s a path, most 5 to 20), easing in, out
  or both, in an `EncapsuleCutscene` that blocks the player's actions; all 69 stock `CutsceneStartCameraPath` nodes
  are skippable with Escape, and 27 of the 52 with a time ease both ways. DelayedRetribution,
  GloryOrAttrition, TheHydra and RunningTheGauntlet then snap to a one-key path at the move's last key, to within a
  world unit, before the HUD returns.
- Eleven of the twelve hand the camera over 312,898 to 604,542 world units above the ground, 34.7 to 40 degrees down;
  RunningTheGauntlet's convoy close-up stands 119,565 up.
- Six start a camera path right before `LoadingDone`, beside an intro video: the start cameras of BackhandBlow,
  BlackHorsesLastStand, Gotterdammerung, RedJuggernaut and TheKitzingenRuse (every key 376,057 to 773,047 up, 39.3 to
  40 degrees down; the lowest BlackHorsesLastStand's `camera_start`), and Sledgehammer's ground-level shot.
- Every key is a `TCameraPathKey` holding one vec3 `Coord`, positions and directions in two lists of one length, each
  direction a unit vector; every file holds two paths or more, each path an unexported root.
