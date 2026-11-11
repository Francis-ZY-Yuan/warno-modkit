---
id: weapons-jammed-effect
title: The "weapons jammed" effect only zeroes weapon ranges; to keep a unit silent, empty its ammunition
status: STOCK
last_verified: 201602 2026-11-03
source: stock-data
topics: [units-and-orders]
shapes: [modkit.ops.bricks.g_ammo]
trials: [2026-11-03-probe1-play1-decoys-fired, 2026-11-03-probe1-play2-soviet-freeze, 2026-11-03-play1-stock-survey]
stock_precedent: Survivors empties a captured tank with SetAmmo at spawn; the jammed effect is wired only to aircraft and helicopter criticals
---
**What the game does.** `UnitEffect_Critic_Stop_Armes` replaces the four weapon range values with 0, multiplies
turret rotation by 0 and raises a tag; it is not a hold-fire, and weapons outside those ranges may be unaffected.
`UnitEffect_Critic_Chenille_Detruite` only stops movement, so applied by script it shows no broken-tracks icon. No
stock script applies either.

**The stock lever.** `SetAmmo` with only `Units` (MaxAmmoRatio left at 0) right after the unit appears, as Survivors
does. It is instantaneous. Stock loops SetAmmo only to refill.

**Gotchas.** The first probe's "decoys fired under weapons jammed" proves nothing: that beat stalled at its first
SetEffect, so the effect never reached a decoy ([[seteffect-never-finishes]]). The SetAmmo fix has not been seen in
play yet. A script hold-fire also exists, `UnitGroupDeactivateWeapons` (1 stock use, permanence unknown).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-play1-stock-survey](../trials/2026-11-03-play1-stock-survey.md), [2026-11-03-probe1-play1-decoys-fired](../trials/2026-11-03-probe1-play1-decoys-fired.md), [2026-11-03-probe1-play2-soviet-freeze](../trials/2026-11-03-probe1-play2-soviet-freeze.md)
- Shapes: [`modkit.ops.bricks.g_ammo`](../../src/modkit/ops/bricks.py)
- Skills: [`components/core/skills/warno-stock-precedent/SKILL.md`](../../../core/skills/warno-stock-precedent/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
<!-- referenced-by:end -->
