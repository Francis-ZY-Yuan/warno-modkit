---
id: 2026-11-12-sc-glyph-every-dictionary
kind: survey
build: twin-strike-chinese
game_version: 210942
mechanisms: [chinese-text-stock-glyphs]
outcome: pass
result: The glyph set takes every stock Simplified Chinese dictionary of the install, the game's own with the scenarios', 2,185 characters in 224 dictionaries (1,700 in 195 before); 核 passes, 龘 still fails, and Open Door's and Twin Strike's tables still pass
---
The install's archive index puts every dictionary outside the scenarios' packs in ZZ_1 (menus, options, maps, units,
unit names), in all eight languages, so core's `STOCK_PATHS` declares them as `localisation`, the newest copy of each.
The older archives' `AllPlatforms/` copies are left out: each has a newer twin, and they would add two characters.
`test_strings` (`test_stock_chars_real`) proves the wider SC set both ways on the extraction.
