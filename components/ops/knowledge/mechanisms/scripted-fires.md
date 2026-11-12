---
id: scripted-fires
title: A battery created just before its ShootOnPosition fires; created where the player's units can reach, it must be in their alliance
status: PLAYED
last_verified: 201602 2026-11-11
source: play
topics: [units-and-orders]
gates: [modkit.ops.gates.check_fire_range]
trials: [2026-11-03-probe1-play1-worked, 2026-11-03-probe1-play2-soviet-freeze, 2026-11-11-twin-strike-play1, 2026-11-11-twin-strike-guns-on-the-edge]
stock_precedent: all 31 stock scripted artillery orders come from enemy-alliance camps under fog, 10,000-22,000 GRU from the player's deployment zone; no stock script empties artillery
---
**What the game does.** A battery created in a corner 20 s before its order, then ordered to `ShootOnPosition`
(OrderType 31), fired its barrage on time in the first probe's play (5:20).

**Stock's ShootOnPosition artillery** is TheWingedHussars #362 and Marauders #1341/#1352/#1353, each Blocking, on a
CommandPoints tag; Survivors #1231/#1232 order its bombers so onto Name tags. (BackhandBlow #283 is OrderType 29,
Shoot.) Every stock scripted battery, Shoot or ShootOnPosition, stands in a camp of the enemy alliance with an AI
strategy, so fog of war hides it; it is pre-placed far from the player's deployment zone, kept off its camp's AI with
`AddIgnoredUnitByScript` (TheDieburgSalient #143-#145 on its scripted 2S1s) and refilled with SetAmmo 100 before its
orders, never emptied.

**Seen in play: pre-placed allied guns drove toward the front.** Twin Strike's division guns stood pre-placed in the
player's allied camp, in view, emptied with SetAmmo at load and refilled for each ShootOnPosition on a detector circle;
in play they drove toward the front and died ([[2026-11-11-twin-strike-play1]]). The trigger is not settled from stock
data: every target's centre was inside the guns' bands, and the allied camp runs no AI. The shape departed from every
working precedent at once (pre-placed in the open for a long idle phase, emptied ammunition, an allied camp, circles).

**Seen in play: a battery created outside the playable zone stood on its edge, and the player's units killed it.**
The next build created each fire's battery at one spot 4,577 GRU north of the playable zone, past the longest ground
vision range of the player's units, in an enemy-alliance camp, to hide it. In play it stood on the zone's edge beside
the player's deployment, drawn blue, and the player's Ka-50s killed it ([[2026-11-11-twin-strike-guns-on-the-edge]]):
the game puts a unit created outside the zone on its edge ([[created-units-stand-in-zone]]). Its ShootOnPosition, on a
Name tag, still landed on the target: an enemy-alliance battery firing on its own alliance's units, by artillery on a
Name tag.

**The shape now.** No battery can hide: created inside the zone or outside it, it stands where the player's units
reach. So each fire creates its battery inside the playable zone in a camp of the player's alliance (Twin Strike: the
allied camp, in the cut's north-west corner, seen for about 2 minutes per fire), keeps it off that camp's AI, orders
ShootOnPosition non-blocking on a Name tag after probe 1's lead time, and removes it (Vanished [[vanished-removal]])
once the salvo has landed. A battery that lives 110 s cannot drive far, as the first play's pre-placed guns did. The
`fire-range` gate (`gates.check_fire_range`) holds each battery's camp to the player's alliance and every target
inside each battery's band from where it stands, from the shipped files and the unit database; gate 3
(`gates.check_created_in_zone`) holds where it is created.

**Not seen in play:** a battery of the player's allied camp created for its fire and removed after (the first play's
allied guns were pre-placed), and whether a created battery's removal after its fire shows.

**Not yet seen in play** (built into the first probe, but play 2 froze before they ran):
- stunning the rest with ChangeStress Stun ([[changestress-damagetype-zero]]; no stock use; the strike-effects
  probe's play showed no sign of it);
- `SetFuel` to starve a pocket.

**Since seen,** in the strike-effects probe's play ([[2026-11-11-fxprobe-play1]]): `LaunchFXFireAndForgetOnPosition`
impacts massed round a target (a script may launch only a self-contained effect, or its own wrapper:
[[script-effects-self-contained]]), and a share of a group destroyed with `TransferUnitToUnitGroup` (one unit at a
time, no CopyUnits) and `KillAllUnit` Penetration: 4 of 12 died.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-03-probe1-play2-soviet-freeze](../trials/2026-11-03-probe1-play2-soviet-freeze.md), [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-11-twin-strike-guns-on-the-edge](../trials/2026-11-11-twin-strike-guns-on-the-edge.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Gates: [`modkit.ops.gates.check_fire_range`](../../src/modkit/ops/gates.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md), [2026-11-11-twin-strike-guns-on-the-edge](../trials/2026-11-11-twin-strike-guns-on-the-edge.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md), [created-units-stand-in-zone](created-units-stand-in-zone.md)
<!-- referenced-by:end -->
