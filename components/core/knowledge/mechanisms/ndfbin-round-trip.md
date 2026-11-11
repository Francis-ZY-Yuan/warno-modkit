---
id: ndfbin-round-trip
title: Compiled NDF (CNDF ndfbin) decodes and re-encodes byte for byte
status: PLAYED
last_verified: 201602 2026-11-06
source: stock-data
topics: [files-and-formats]
shapes: [modkit.core.ndfbin.NdfBin]
trials: [2026-11-02-ndfbin-round-trip, 2026-11-06-probe2-play-run-a]
stock_precedent: 1,473 of 1,473 files round-trip byte-identical (763 scenario-pack files, 710 Glad.dat files)
---
**What the game does.** Scenario scripts (GDScript), LevelDesign, zone files, `.tag` and `.sav` files and the GFX
clusters are CNDF containers: a header, a body of tables (objects, topology, classes, properties, strings, imports,
exports) and a table of contents. The body is stored raw, LZ4 or zstd.

**How we know.** `modkit.core.ndfbin` decodes every file tried and re-encodes the decompressed image (header, body
and table of contents) byte-identically. Every generated mod file is a CNDF this code wrote, and the generated
Operations load and play.

**Gotchas.**
- An object reference carries the target's class index as well as its object index (17,280 of 17,280 stock
  references).
- Text values are packed tokens, not hashes ([[localisation-tokens-packed]]).
- The game's serialiser leaves out properties at their default value, and so does a dump: "absent" means "default".

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-ndfbin-round-trip](../trials/2026-11-02-ndfbin-round-trip.md), [2026-11-06-probe2-play-run-a](../../../ops/knowledge/trials/2026-11-06-probe2-play-run-a.md)
- Shapes: [`modkit.core.ndfbin.NdfBin`](../../src/modkit/core/ndfbin.py)
- Skills: [`components/core/skills/warno-setup/references/stock-corpus.md`](../../skills/warno-setup/references/stock-corpus.md)
<!-- referenced-by:end -->
