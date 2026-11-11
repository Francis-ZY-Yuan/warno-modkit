---
id: 2026-11-11-probe3b-play1-no-supply
kind: play
build: f16deb7
game_version: 201602
mechanisms: [soviet-player-camp]
outcome: fail
symptom: The Soviet player found no supply trucks or supply helicopters to buy
cause: RedJuggernaut's player deck, which the probe gives the Soviet player, has no supply helicopter, and its only supply trucks sit in its two tank battalions' HQ groups; the probe added no supply
result: The Soviet player's supply (Ural-4320 trucks x4, Mi-8TZ helicopters x2) is a shared constant that nuke_sov and Twin Strike add at load, and a stock test re-checks the deck's gap
---
The third probe's `nuke_sov` content after its effect swap (probe 3b), built from f16deb7, played once. The one
observation recorded so far: the Soviet player found no supply trucks or helicopters to buy. In the stock deck the
probe gives the player, supply comes only as trucks in the tank battalions' HQ groups, and no helicopter carries it
([[soviet-player-camp]]); the probe's buy menu also ran with its view switch force-hidden.

The rest of probe 3b's debrief is still to come.
