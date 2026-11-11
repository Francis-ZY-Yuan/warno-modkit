---
id: 2026-11-03-probe1-play2-land-buys
kind: play
build: 4b99a5a
game_version: 201602
mechanisms: [arrival-end-in-zone, deployment-phase-recipe]
outcome: fail
symptom: Aircraft bought in battle arrived; land units never found a destination and never arrived
cause: All four player arrival Ends lay about 164,000 world units west of the player's deployment zone, inside no zone
result: The deployment zone reaches the map's west edge, and the arrivals gate reads the shipped zone polygons
---
The arrivals gate added after the third launch only counted the entries. The same fault had been found and gated
for an earlier Operation ([[2026-11-02-kreide-op-arrivals]]).
