---
id: 2026-11-03-ingame-button-stock-sweep
kind: survey
build: 4b99a5a
game_version: 201602
mechanisms: [dialog-button-ingame-dictionary]
outcome: pass
result: A gate requires every button token to be in INTERFACE_INGAME in all 8 languages, with a test pinning the property set to stock
---
Proven both ways: stock's 974 button-token uses all resolve in the in-game dictionary, and the unfixed probe fails in
about 2 seconds.
