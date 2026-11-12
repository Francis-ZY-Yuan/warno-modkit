---
id: 2026-11-12-deck-gate-bad-builds
kind: survey
build: twin-strike-own-deck
game_version: 210942
mechanisms: [op-exported-deck, deck-names-from-op-dictionaries]
outcome: fail
cause: decks the game refuses, or names it cannot find, built on purpose
result: Each bad deck fails its gate with the rule's line: motor rifles riding a Ka-29 (no transporter module), a card key on a locked page and an open one, a page or platoon token in no list, a SetDeck naming no deck, a page lock past the deck's pages, a pack index past the packs
---
Decks built with one fault at a time ([[op-exported-deck]]), each failing the decks or the tokens gate
(`test_deck_gate`): motor rifles in a Ka-29, which has no transporter module, so the game would refuse the deck at its
load; a card key on a locked page and on an open one, so the open page would sell what the lock holds back; a page
name in the scenario's own dictionary and a platoon name in the COMPANIES file, neither in the list the game looks it
up in, which the game would meet as a dictionary error at the first SetDeck [[deck-names-from-op-dictionaries]]; a
SetDeck on an unknown identifier; a lock past the pages; a pack index past the packs; a carrier with no unit; a unit
that cannot be carried; a carrier and a unit with no shared tag; the group rules; the identifier and the division.
Twin Strike's own deck rebuilt with the first three faults (`test_twin_strike_frame.Build`: its Ka-29 platoon carrying
motor rifles, its reserve's Konkurs-M teams at the start's experience, a tank platoon named `ts_pl_none`) fails the
build with the gate's line, before anything is written.
