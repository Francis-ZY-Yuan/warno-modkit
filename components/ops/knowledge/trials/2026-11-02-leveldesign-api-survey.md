---
id: 2026-11-02-leveldesign-api-survey
kind: re
build: e094396
game_version: 201602
mechanisms: [leveldesign-guid-binding, spawn-and-create-units, mission-ends-only-by-script, script-container-semantics, gdscript-is-what-loads]
outcome: pass
result: A class catalogue of the 16 stock Operations' scripts, used to pick templates for every script node
---
Read the Python form of all 29 scenario scripts and the 128 library modules, catalogued every class the 16 Operations use, and
resolved every map handle (2,133) and text key (658). Found that the Python layer only forwards keyword arguments to
native setters and never runs during a battle.
