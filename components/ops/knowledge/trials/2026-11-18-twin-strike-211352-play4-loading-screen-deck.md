---
id: 2026-11-18-twin-strike-211352-play4-loading-screen-deck
kind: play
build: 7777a3d
game_version: 211352
mechanisms: [menu-deck-until-setdeck]
outcome: pass
symptom: The loading screen shows the stock deck, not the Operation's own
cause: by design: the out-game screens show the menu's deck, MapConfiguration's LocalPlayerDeck (RedJuggernaut's OP_BASE_RJ_Player), until the op's script runs SetDeck; in battle the buy menu was the op's own deck
result: kept for now, with no gate, as the build is not wrong; Twin Strike's README and design note it. The untried route is a LocalPlayerDeck of the same division with no groups (OP_BASE_SH_Ally_L)
---
One symptom of [[2026-11-18-twin-strike-211352-play4]], recorded on its own so the symptom index points at the
behaviour, not at the deck gates: the loading screen showed RedJuggernaut's groups, and in battle the buy menu showed
Twin Strike's own five pages [[menu-deck-until-setdeck]].
