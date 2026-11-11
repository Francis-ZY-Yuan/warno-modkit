---
id: 2026-11-02-ndfbin-round-trip
kind: re
build: e094396
game_version: 201602
mechanisms: [ndfbin-round-trip]
outcome: pass
result: modkit.core.ndfbin, with a round-trip test over every stock file
---
Decoded and re-encoded 763 scenario-pack CNDF files (raw, LZ4 and zstd bodies) and 710 `Glad.dat` NDF files from
two game builds. All 1,473 came back byte-identical, the 29 extracted GDScript files included.
