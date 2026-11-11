---
id: 2026-11-02-gdscript-format-survey
kind: re
build: e094396
game_version: 201602
mechanisms: [gdscript-is-what-loads, operation-menu-registration, localisation-tokens-packed]
outcome: pass
result: GDScript ndfbin became the authoring target; the Python is kept only as a readable reference
---
Mapped every Python constructor call of 29 stock scenario scripts onto the objects of their GDScript files
(27,151 objects, no conflict, no value mismatch), compared the game's level-launch table across three builds, and
read how the Operations menu is built from the MapConfiguration files.
