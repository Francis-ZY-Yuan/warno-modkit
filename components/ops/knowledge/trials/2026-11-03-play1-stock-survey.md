---
id: 2026-11-03-play1-stock-survey
kind: survey
build: 46dccf8
game_version: 201602
mechanisms: [objective-label-needs-position, weapons-jammed-effect, helicopter-boarding, fast-move-and-attack-keeps-roads]
outcome: pass
result: The fixes for the first play's failures, each matched to a stock shape
---
Read the 30 stock GDScripts and the effect and order data behind the first play's failures: every objective's
label and anchor (89 nodes by the survey's count; a recount of the same 30 files finds 104), the two effects and
every SetAmmo, every LoadIntoTransporter (57), every order type and road flag (150 GiveOrderStandard nodes, 58
MoveUnitGroup, 65 Attack), and the reveal effect (no stock script applies it).
