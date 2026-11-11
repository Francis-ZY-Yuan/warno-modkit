---
id: 2026-11-02-kreide-op-arrivals
kind: play
build: bd205d9
game_version: 201602
mechanisms: [arrival-end-in-zone, deployment-phase-recipe]
outcome: fail
symptom: Nothing bought after Launch battle arrived
cause: The player's reinforcement location ended about 230,000 world units west of the player's deployment zone, inside no zone
result: The End moved into the deployment zone, an aerial corridor was added, and the generator now fails any player End outside a same-side deployment zone
---
A custom Operation on Kreide with a deployment phase. The lesson was recorded and gated here, and still lost when a
later generator was written ([[2026-11-03-probe1-play2-land-buys]]).
