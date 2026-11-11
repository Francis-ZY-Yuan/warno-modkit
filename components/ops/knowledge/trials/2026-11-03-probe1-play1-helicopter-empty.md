---
id: 2026-11-03-probe1-play1-helicopter-empty
kind: play
build: 46dccf8
game_version: 201602
mechanisms: [helicopter-boarding]
outcome: fail
symptom: The helicopter spawned without its infantry and flew off by script
cause: Most likely the hovering helicopter never landed for the scripted boarding; no stock script boards a helicopter
result: A blocking Land order was added before the boarding (it failed in turn)
---
