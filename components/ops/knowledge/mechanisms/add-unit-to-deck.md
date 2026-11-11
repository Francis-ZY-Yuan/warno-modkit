---
id: add-unit-to-deck
title: AddUnitToDeck adds a card at load or mid-battle, a transport card included; added cards show in the battlegroup view
status: PLAYED
last_verified: 201602 2026-11-11
source: stock-data
topics: [units-and-orders]
shapes: [modkit.ops.shapes.add_card, modkit.ops.shapes.lock_card, modkit.ops.script.PRODUCTION_DECK]
trials: [2026-11-03-probe1-play2-sead-card, 2026-11-03-play2-stock-survey, 2026-11-06-probe2-play-run-a, 2026-11-06-spawns-and-deck-survey, 2026-11-11-twin-strike-play1]
stock_precedent: 7 stock uses in 2 Operations, all aircraft, all mid-battle, none with a Transporter
---
**What stock does.** `AddUnitToDeck(Camp, TypeUnit, NbUnitsToAdd, Experience)` adds a card to a camp's deck.
HoldUntilRelieved adds a unit that is in none of the deck's packs, mid-battle, under `ChangeProductionType Groups`.
`Transporter` is a real property, but stock always leaves it out; `Experience` 0 is the default.

**What we saw.** Our probes added land cards at load (including a rifle squad in a transport and an experience-0
tank) and loaded and played without trouble, but the plain-looking cards were never bought. A SEAD card added at 8:00
was not seen in play, most likely because of when or where the player looked.

Twin Strike's first play settled two questions ([[2026-11-11-twin-strike-play1]]):
- **A transport card works:** motor rifles added with their BMP-2 as the Transporter were bought and deployed loaded.
  Infantry added with no carrier deployed on foot, so every infantry card now names a carrier stock pairs it with.
- **Added cards show in the buy menu's BATTLEGROUP view only,** not in its GROUPS view. A card added at load joins no
  battlegroup (no property or sibling node adds a pack to a group; the deck's groups are data of the Gameplay deck
  file). Every stock `ChangeProductionType` writes Groups (1); a content whose cards matter can open the menu on Deck
  (0, `script.PRODUCTION_DECK`, the BATTLEGROUP view) and leave the view switch at Default.

`LockDeckUnit` holds a card back until its action is retired, so stock puts it last in a Competition that ends at
the moment of the unlock ([[seteffect-never-finishes]]); our lock-then-unlock has not been reported in play.

**Gotchas.** No stock deck mixes NATO and PACT units. Make test cards hard to miss and look for them in the
deployment buy menu first, which separates "card missing" from "buy refused" from "never arrived".

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-play2-stock-survey](../trials/2026-11-03-play2-stock-survey.md), [2026-11-03-probe1-play2-sead-card](../trials/2026-11-03-probe1-play2-sead-card.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md), [2026-11-06-spawns-and-deck-survey](../trials/2026-11-06-spawns-and-deck-survey.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Shapes: [`modkit.ops.shapes.add_card`](../../src/modkit/ops/shapes.py), [`modkit.ops.shapes.lock_card`](../../src/modkit/ops/shapes.py), [`modkit.ops.script.PRODUCTION_DECK`](../../src/modkit/ops/script.py)
- Skills: [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/forces.py`](../../examples/twin-strike/twinstrike/forces.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py), [`components/ops/examples/twin-strike/twinstrike/profile.py`](../../examples/twin-strike/twinstrike/profile.py)
- Records: [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md), [deployment-phase-recipe](deployment-phase-recipe.md), [helicopter-boarding](helicopter-boarding.md), [soviet-player-camp](soviet-player-camp.md)
<!-- referenced-by:end -->
