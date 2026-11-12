---
id: 2026-11-12-deck-gate-stock-survey
kind: survey
build: twin-strike-own-deck
game_version: 210942
mechanisms: [op-exported-deck, deck-names-from-op-dictionaries, deck-page-lock]
outcome: pass
result: The decks gate passes the game's own data: all 2,486 decks of the game's deck file pass the load checks it models (2,873 of their 5,775 packs carried), every SetDeck of the 16 stock challenge scripts names a stock deck, and their 3 page locks are in range; every name token of the game's decks resolves in its list (UNITS, COMPANIES, PLATOONS)
---
The decks gate (`gates.check_decks`) read over a 210942 extraction ([[op-exported-deck]]): the game's deck file, its
unit file and every stock challenge script. A carried pack shares a tag with its carrier in every stock deck; 2,034 of
the 2,873 would fail if the carrier's whole tag set were required, so the gate asks for one shared tag. The 17
Operation decks with pages keep a Challenge's group rules (5 pages, 6 platoons, 3 packs); 16 of them draw their packs
unevenly, which only the op's own rule refuses. The three stock page locks (RunningTheGauntlet's two, Marauders' one)
lock pages of their camp's deck [[deck-page-lock]]. The ops tests `test_deck_gate.StockGate` hold all of it. The names
of the game's decks, read against the install's dictionaries, each resolve in the one list the game looks them up in
(127 deck names in UNITS, 43 page names in COMPANIES, 79 platoon names in PLATOONS)
[[deck-names-from-op-dictionaries]].
