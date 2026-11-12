---
id: op-exported-deck
title: An Operation can export its own deck from its script and give it to a camp with SetDeck
status: UNTESTED
source: exe-analysis
topics: [units-and-orders, operation-setup]
gates: [modkit.ops.gates.check_decks]
shapes: [modkit.ops.shapes.player_deck, modkit.ops.shapes.DECK_SHAPE_SOURCES, modkit.ops.forces.deck_packs, modkit.ops.leveldesign.derived_deck_identifier]
stock_precedent: none: every stock scenario's SetDeck names a deck of the game's own deck file; the deck's shape is that file's
---
**What the game does** (game build 210942, read from the executable and checked against the game's own data). The
game registers every deck (`TDeckDescriptor`) a file loads under its `DeckIdentifier`, the scenario's script among
them, and drops it when the file unloads. A camp's `SetDeck` builds the camp's deck from the registered deck its
identifier names, page and platoon names included. So a deck exported from the op's own script can be a camp's deck:
the script loads before it launches, and a scenario file is not a Gameplay file.
- **At the launch,** every `SetDeck` must name a registered deck, or the mission fails with a GDBrick error naming
  `DeckIdentifier`.
- **At the load,** a second deck with a registered identifier stops the load. The game checks each deck before it
  registers it, every check fatal: each platoon's pack index names one of the deck's packs; a carried pack's unit can
  be carried (a transportable module), its carrier is a transport (a transporter module), and the two share a tag (the
  unit's tags and the tags the carrier takes). A pack with a carrier and no unit crashes.
- **The menu's deck** (`MapConfiguration`'s `LocalPlayerDeck`) is resolved before the script loads, so it must stay a
  deck of the game's; the camp's `SetDeck` replaces it at the load.
- **The buy menu pools cards by (unit, carrier, experience):** a pack's count joins every card of its key, whichever
  page or pack holds it. A key on a locked page and an open one is sold by the open one [[deck-page-lock]].

**The shape** (`modkit.ops.shapes.player_deck`): the game's own deck shape, exported under `$/GDScript/...`, its packs
inline, one pack per card key (`modkit.ops.forces.deck_packs`), a division of the game's (an Operation's
`_challenge` division) and an identifier derived from a hash (`derived_deck_identifier`)
[[derive-cross-mod-ids-from-a-hash]]. Its page and platoon names are tokens of the game's own lists
[[deck-names-from-op-dictionaries]]. A profile admits the deck's shapes from the game's deck file
(`DECK_SHAPE_SOURCES`).

**The gate** (`modkit.ops.gates.check_decks`, every build): every `SetDeck` names a deck of the game's or one the
script exports; an exported deck passes the game's checks above, read from the game's own unit file, and the op's
rules: a Challenge's group rules (5 pages, 6 platoons a page, 3 packs a platoon), a division of the game's, an
identifier no stock deck has, every pack drawn exactly by its platoons, page locks in range, and no card key on both
a locked page and an open one. Every one of the game's 2,486 decks passes the game's checks; most of its Operation
decks draw their packs unevenly, which only the op's rule refuses.

**Not yet seen in play:** the first launch, a mission restart (whether the old deck is gone before the new one
registers), and whether a platoon is bought whole or unit by unit. Twin Strike is the first content to use it.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-deck-gate-bad-builds](../trials/2026-11-12-deck-gate-bad-builds.md), [2026-11-12-deck-gate-stock-survey](../trials/2026-11-12-deck-gate-stock-survey.md)
- Gates: [`modkit.ops.gates.check_decks`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.shapes.player_deck`](../../src/modkit/ops/shapes.py), [`modkit.ops.shapes.DECK_SHAPE_SOURCES`](../../src/modkit/ops/shapes.py), [`modkit.ops.forces.deck_packs`](../../src/modkit/ops/forces.py), [`modkit.ops.leveldesign.derived_deck_identifier`](../../src/modkit/ops/leveldesign.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/forces.py`](../../examples/twin-strike/twinstrike/forces.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py), [`components/ops/examples/twin-strike/twinstrike/profile.py`](../../examples/twin-strike/twinstrike/profile.py)
- Records: [2026-11-12-deck-gate-bad-builds](../trials/2026-11-12-deck-gate-bad-builds.md), [2026-11-12-deck-gate-stock-survey](../trials/2026-11-12-deck-gate-stock-survey.md), [add-unit-to-deck](add-unit-to-deck.md), [deck-page-lock](deck-page-lock.md), [soviet-player-camp](soviet-player-camp.md)
<!-- referenced-by:end -->
