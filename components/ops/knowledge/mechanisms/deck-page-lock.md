---
id: deck-page-lock
title: LockCombatGroup locks a page of a camp's deck while it runs; stock holds the buy menu in its GROUPS view with the view switch hidden
status: STOCK
last_verified: 210942 2026-11-12
source: stock-data
topics: [units-and-orders, script-flow]
gates: [modkit.ops.gates.check_decks, modkit.ops.gates.check_never_finishing]
shapes: [modkit.ops.shapes.lock_page, modkit.ops.script.PRODUCTION_TYPE]
stock_precedent: three stock page locks, RunningTheGauntlet's pages 1 and 2 and Marauders' page 1, each a LockCombatGroup first in a Competition with a WaitCondition, each beside a buy menu held in GROUPS with the view switch force-hidden
---
**What stock does.** `LockCombatGroup(Camp, CombatGroupIndexes)` blocks buying from pages of the camp's deck. Each
index is a `TGDVariableInteger` holding a page's 0-based place in the deck's page list (pages marked `IsHQ` come
first). It never finishes and locks only while it runs [[seteffect-never-finishes]], so stock puts it first in a
Competition with a WaitCondition on what unlocks it, one node per page: RunningTheGauntlet #178/#179 lock its pages 1
and 2 on the player's camp until a zone is taken; Marauders #490 locks page 1.

**The menu.** Each scenario that locks a page holds the buy menu in its GROUPS view: `ChangeProductionType` Groups and a
hide-all `ForceDisplayUIElement` that force-hides the view switch, then the buy menu shown with the switch still
force-hidden (Marauders #107, #108, #162; RunningTheGauntlet #168, #169, #176). The other view lists the deck's
pooled cards, not its pages.

**The gate.** `gates.check_decks` holds every lock's index to the locked camp's deck (a stock deck's pages, or the
script's own deck) [[op-exported-deck]], and an op's own deck to no card key on both a locked page and an open one:
the game pools a deck's cards by (unit, carrier, experience), so the open page would sell what the lock holds back.

**Not yet seen in play:** what a locked page looks like (greyed, hidden or just unbuyable), and the pages unlocking.
Twin Strike locks its reserve's two pages until the village falls.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-deck-gate-stock-survey](../trials/2026-11-12-deck-gate-stock-survey.md)
- Gates: [`modkit.ops.gates.check_decks`](../../src/modkit/ops/gates.py), [`modkit.ops.gates.check_never_finishing`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.shapes.lock_page`](../../src/modkit/ops/shapes.py), [`modkit.ops.script.PRODUCTION_TYPE`](../../src/modkit/ops/script.py)
- Skills: [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/forces.py`](../../examples/twin-strike/twinstrike/forces.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py), [`components/ops/examples/twin-strike/twinstrike/profile.py`](../../examples/twin-strike/twinstrike/profile.py)
- Records: [2026-11-12-deck-gate-stock-survey](../trials/2026-11-12-deck-gate-stock-survey.md), [add-unit-to-deck](add-unit-to-deck.md), [op-exported-deck](op-exported-deck.md)
<!-- referenced-by:end -->
