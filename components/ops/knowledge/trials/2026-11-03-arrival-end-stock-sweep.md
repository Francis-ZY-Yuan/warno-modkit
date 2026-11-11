---
id: 2026-11-03-arrival-end-stock-sweep
kind: survey
build: 4b99a5a
game_version: 201602
mechanisms: [arrival-end-in-zone]
outcome: pass
result: The arrivals gate reads the shipped zone polygons and fails any player End outside a player deployment zone or a command zone
---
Proven both ways: the old build fails on its 4 entries; the new build and stock (83 entries in 22 layouts) pass. A
stricter "same-side deployment zone only" rule would fail three stock Operations, so command zones count too.
