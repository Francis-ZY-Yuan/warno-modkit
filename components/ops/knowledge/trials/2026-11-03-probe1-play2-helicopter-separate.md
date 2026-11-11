---
id: 2026-11-03-probe1-play2-helicopter-separate
kind: play
build: 4b99a5a
game_version: 201602
mechanisms: [helicopter-boarding]
outcome: fail
symptom: The helicopter and its infantry stayed apart again
cause: Land (18) takes no target, so the given position was ignored; no stock script boards a helicopter
result: The probe tries ProductionUnites with a Transporter; the fallback drops the boarding
---
