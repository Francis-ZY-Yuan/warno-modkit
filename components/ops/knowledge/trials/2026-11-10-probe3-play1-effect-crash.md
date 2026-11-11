---
id: 2026-11-10-probe3-play1-effect-crash
kind: play
build: 619a5a5
game_version: 201602
mechanisms: [scripted-nuke-effect, script-effects-self-contained, soviet-player-camp]
outcome: fail
symptom: The game crashed during the deploy phase, at the effect steps
cause: The nuke effects are parameterised impact actions, which a script launch cannot bind
result: A build gate refuses a script launch of any effect that is not self-contained, and the probe launches self-contained effects
---
The third probe's first play, its Soviet content (`nuke_sov`), built from commit 619a5a5: a fresh build of that tree is
byte-identical to the mod that was installed and played. Its steps run on the clock of LoadingDone, so they fire
during the deploy phase, and the game crashed there, at the effect steps: N2 (0:40) was the first launch of a
tactical-nuke impact effect ([[scripted-nuke-effect]]). No stock script launches such an effect; every effect a stock
script launches is self-contained ([[script-effects-self-contained]]).

A second play of the same build crashed the same way, in the deploy phase, close to the moment the battle was
launched; N2 falls about then. Afterwards the game's list of active mods was empty, so the next start had no mods.

The deploy screen lacked its button that switches between its two views (groups and battlegroup). Open Door's deploy
screen, on a NATO player, has it, so the Soviet player's camp loses it ([[soviet-player-camp]]); the crash does not
explain it.

Not read: the rest of the play sheet, and whether N1b's 203 mm effect (0:25) played before the crash.
