---
id: 2026-11-11-twin-strike-opening-camera
kind: play
build: 964e803
game_version: 201602
mechanisms: [start-camera-before-loading-done]
outcome: fail
symptom: The opening camera sat on the ground somewhere
cause: The only camera action was a one-key snap right before LoadingDone; Twin Strike opens in the deployment phase, whose start at LoadingDone loses a camera set before it
result: The camera flies a stock-style opening move right after LoadingDone, then snaps to its last key before the HUD returns; the camera gate holds the paths file
---
Twin Strike as v0.1 ships it, built from 964e803 (the installed mod hashed the same as that build). The camera was
on the ground when the deployment phase opened. The built paths file held one path, `TS_Start`: one key, its eye at
(69, 222.7) px, 297,725 world units above the map's ground, 37 degrees down, facing south, its view centred on the
village; the same height and pitch as the layout's own `camp0`, the stock shape of a key. The script snapped to it in
an `EncapsuleCutscene` as the last node before `LoadingDone`, as five stock Operations snap theirs beside an intro
video. No stock Operation that opens in the deployment phase stops there: all twelve run a camera path after
`LoadingDone` ([[2026-11-11-opening-camera-stock-survey]]), and the Kreide Operation's snap held only while it opened
in the Command phase ([[start-camera-before-loading-done]]).
