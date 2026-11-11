---
id: 2026-11-11-twin-strike-launch1-duplicate-menu-order
kind: play
build: e23335e
game_version: 201602
mechanisms: [content-identity-unique, operation-menu-registration]
outcome: fail
symptom: Map pack configuration error : Duplicate OrderToChainMission 1001 in map pack '{the Operations pack's GUID}'.
cause: Two active Operations, Twin Strike and probe 3's nuke_sov, held the same menu order (OrderToChainMission 1001), each copied from Open Door's profile
result: Each Operation keeps its own menu order (Twin Strike 1002, the nuke probes 1003 and 1004); the menu-order gate fails a stock Operation's menu order, and a test keeps the examples' menu orders apart
---
Twin Strike's first launch, built from e23335e, with probe 3's `nuke_sov` content active beside it. Two active
Operations with the same menu order number stopped the game while it was starting, with a fatal error box naming
that number and the Operations menu's map pack by its GUID ([[operation-menu-registration]]). Both mods'
MapConfiguration carried `OrderToChainMission` 1001; their scenario ids, GUIDs, mod folders and menu tokens all
differ, and the only text token they share is the blank key, which every stock challenge dictionary holds too
([[content-identity-unique]]).
