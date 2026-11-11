---
id: 2026-11-02-edat-inventory
kind: re
build: e094396
game_version: 201602
mechanisms: [edat-revision-chain]
outcome: pass
result: modkit.core.edat reads both archive versions, checks entries and writes version 3
---
An inventory of every edat archive in one install: header versions, the per-revision folders, counts by extension,
and where GDScript, LevelDesign and `Items.sav` live. Every archive's index was read and its entries checked
against their stored checksums.
