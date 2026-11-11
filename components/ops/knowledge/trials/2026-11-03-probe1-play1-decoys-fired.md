---
id: 2026-11-03-probe1-play1-decoys-fired
kind: play
build: 46dccf8
game_version: 201602
mechanisms: [weapons-jammed-effect, seteffect-never-finishes]
outcome: fail
symptom: The friendly decoy tanks fired and killed, and showed no broken-tracks icon
cause: Confounded. The beat stalled at its first SetEffect, so the jammed effect never reached a decoy; and that effect only zeroes ranges anyway
result: Decoys are emptied with SetAmmo, the stock lever, and keep only the tracks effect
---
The stall was found only after the second play ([[2026-11-03-probe1-play2-soviet-freeze]]).
