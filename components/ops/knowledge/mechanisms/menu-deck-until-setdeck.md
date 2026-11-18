---
id: menu-deck-until-setdeck
title: The out-game screens show the menu's deck (LocalPlayerDeck) until SetDeck runs; the battle uses SetDeck's deck
status: PLAYED
last_verified: 211352 2026-11-18
source: play
topics: [units-and-orders, operation-setup]
trials: [2026-11-18-twin-strike-211352-play4, 2026-11-18-twin-strike-211352-play4-loading-screen-deck]
---
**What the game does.** A scenario's `MapConfiguration` names the menu's deck, `LocalPlayerDeck`. The out-game
screens, the loading screen among them, show that deck: it is resolved before the scenario's script loads
[[op-exported-deck]]. When the script's `SetDeck` gives the player's camp another deck, the battle uses that one: the
buy menu shows its pages, and the menu's deck does not show in battle.

**How we know.** Twin Strike on build 211352: its loading screen showed RedJuggernaut's groups, from its
`LocalPlayerDeck` `OP_BASE_RJ_Player`, and in battle the buy menu showed the op's own five pages by their own names
([[2026-11-18-twin-strike-211352-play4]]).

**Gotchas.**
- An Operation with its own deck shows a stock deck on its loading screen. That is by design, and no gate checks it:
  the build is not wrong. The menu's deck must still be one of the game's decks, since the script's own decks are not
  registered when the menu resolves it.
- Untried: a `LocalPlayerDeck` of the same division with no groups, such as `OP_BASE_SH_Ally_L` (the 79th Guards Tank
  Division's Operation division, as RedJuggernaut's player deck), would show less of a deck the player does not get.
  Whether the out-game screens take a deck with no groups is not known.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-18-twin-strike-211352-play4](../trials/2026-11-18-twin-strike-211352-play4.md), [2026-11-18-twin-strike-211352-play4-loading-screen-deck](../trials/2026-11-18-twin-strike-211352-play4-loading-screen-deck.md)
- Examples: [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md)
- Records: [2026-11-18-twin-strike-211352-play4](../trials/2026-11-18-twin-strike-211352-play4.md), [2026-11-18-twin-strike-211352-play4-loading-screen-deck](../trials/2026-11-18-twin-strike-211352-play4-loading-screen-deck.md), [op-exported-deck](op-exported-deck.md), [soviet-player-camp](soviet-player-camp.md)
<!-- referenced-by:end -->
