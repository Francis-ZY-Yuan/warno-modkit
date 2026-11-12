---
id: 2026-11-11-twin-strike-strike-unseen
kind: play
build: 893ba2f
game_version: 201602
mechanisms: [scripted-nuke-effect, script-effects-self-contained]
outcome: mixed
symptom: Not seeing the massive nuke effect, just a scripted effect of all units dead, while they were not detected; small explosions seen
cause: One mega bomb, about a 203 mm shell's size, at one point of an 800 m zone 1.8 km from the player's view, in fog, with no camera on it; the kill 3 s later on units the player never saw, and the strike's lone 2S7M round 36 to 46 s after it
result: The strike masses 97 self-contained effects at the flash, flies the camera to the zone and holds it there, and kills only a share of battalion 2 inside the blasts, damaging and stunning the rest for the Soviets to finish
---
Twin Strike's smoke play, built from 893ba2f, answered the release with Yes. The game launched the strike's effects
from our own script without a crash: the mega bomb `fx_HE_Mega_Bomb_ForScript`, then the dressing's `feu_fx_script`
and `fx_FumeeNoire_ForScript_RandomPosition` ([[script-effects-self-contained]]). The panel showed the strike zone done
and battalion 2 dead.

The player's report: no massive effect, only all the units dead, unseen in fog, and small explosions. The look is one
explosion about a 203 mm shell's size (its dust some 47 m out, gone within 10 s) in an 800 m zone, off screen
([[scripted-nuke-effect]]).

Not read: whether the Penetration kill left wrecks (the victims were in fog).
