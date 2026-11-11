---
id: 2026-11-03-play2-stock-survey
kind: re
build: 4b99a5a
game_version: 201602
mechanisms: [seteffect-never-finishes, script-container-semantics, arrival-end-in-zone, helicopter-boarding, add-unit-to-deck]
outcome: pass
result: The never-finishing and arrival gates, and the loaded-helicopter attempt
---
A read-only analysis of how SetEffect and the other lasting actions run and end, checked against every stock
placement (334 nodes); of how the game decides where a bought unit may come from, checked against every stock
player entry; and of the creation nodes that take a transporter.
