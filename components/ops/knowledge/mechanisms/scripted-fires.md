---
id: scripted-fires
title: A battery created just before its ShootOnPosition fires; pre-placed allied guns drove toward the front instead
status: PLAYED
last_verified: 201602 2026-11-11
source: play
topics: [units-and-orders]
gates: [modkit.ops.gates.check_fire_range]
trials: [2026-11-03-probe1-play1-worked, 2026-11-03-probe1-play2-soviet-freeze, 2026-11-11-twin-strike-play1]
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
working precedent at once (pre-placed in the open for a long idle phase, emptied ammunition, an allied camp, circles),
so the fix removes all of them: each fire creates its battery at one spot outside the playable zone, past the longest
ground vision range of the player's units, in an enemy-alliance camp the player cannot see, keeps it off that camp's
AI, orders ShootOnPosition non-blocking on a Name tag after probe 1's lead time, and removes it (Vanished
[[vanished-removal]]) once the salvo has landed. The `fire-range` gate (`gates.check_fire_range`) holds the spot to
those rules from the shipped Details and the unit database, every target inside each battery's band.

**Not seen in play:** a battery created outside the playable zone (no stock create stands outside a zone), a battery
of the enemy alliance firing on that alliance's units, and ShootOnPosition by artillery on a Name tag.

**Not yet seen in play** (built into the first probe, but play 2 froze before they ran):
- `LaunchFXFireAndForgetOnPosition` impacts across a box (a script may launch only a self-contained effect:
  [[script-effects-self-contained]]);
- destroying a share of a group with `TransferUnitToUnitGroup` and `KillAllUnit` Penetration (stock does this only
  in the campaign tutorials);
- stunning the rest with ChangeStress Stun ([[changestress-damagetype-zero]]; no stock use);
- `SetFuel` to starve a pocket.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-03-probe1-play2-soviet-freeze](../trials/2026-11-03-probe1-play2-soviet-freeze.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Gates: [`modkit.ops.gates.check_fire_range`](../../src/modkit/ops/gates.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
<!-- referenced-by:end -->
