---
id: 2026-11-11-twin-strike-guns-on-the-edge
kind: play
build: 893ba2f
game_version: 201602
mechanisms: [created-units-stand-in-zone, scripted-fires]
outcome: mixed
symptom: The division's batteries showed as blue units on the playable zone's north edge beside the player's deployment, and the player's Ka-50s killed them; their shells landed on the target
cause: A unit CreateUnitOnPosition makes outside the playable zone stands on the zone's edge; the batteries' camp, ordinateur_DDR, was of the enemy alliance (Alliance 1, BLUFOR style), so the player's units saw and engaged them
result: Each fire creates its battery in the player's allied camp at GUN_SPAWN, moved into the cut's north-west corner; gate 3 holds every created unit inside the playable zone, and the fire-range gate holds a fire's battery to the player's alliance and its targets in range from where it stands
---
Twin Strike's smoke play, built from 893ba2f (the installed mod hashed the same as that build). Each fire created its
battery (2S7M ×6, BM-27 ×6, or both) at `TS_GunSpawn`, (140, 14) px, 4,577 GRU north of the cut, in the unused NATO2
camp, to keep it out of the player's sight.

What was seen during the fire missions, with a screenshot:
- On the cut's north border, partly over the line, a tight block of about 8 blue unit icons, beside the player's red
  units and arrival arrow in the deployment box. The zone's point nearest the tag is (140, 145.6) px, 431 GRU north of
  the box, inside the 3,500 GRU ground vision of every player unit there.
- The player's own Ka-50s shot at the blue guns and killed them.
- The fire's shells landed on the target. From the edge point every target stays inside its band (the village 8,419
  GRU, BOX W 11,581, BOX C 10,851, ASSEMBLY 12,339).
- Not read: whether the batteries vanished after their fire.

The batteries' camp, `ordinateur_DDR`, is Alliance 1 with AllianceStyle 3 in the Soviet-player camp shape
([[soviet-player-camp]]): the player's enemy, drawn blue. The fire-range gate of 893ba2f measured the tag's distance
from the zone, not where the game puts the units, so it passed this build ([[created-units-stand-in-zone]],
[[scripted-fires]]).
