---
id: edat-revision-chain
title: Game data is a chain of edat archives, read newest revision first
status: RE
last_verified: 201602 2026-11-02
source: stock-data
topics: [files-and-formats, game-updates]
gates: [modkit.core.edat.verify_entry]
trials: [2026-11-02-edat-inventory]
stock_precedent: 13,947 version-2 and 1,434 version-3 archives in one install
---
**What the game does.** The install's `Data/PC` folder holds edat archives per revision. The oldest revision folder
is the full base install. Each `<previous>/<revision>/` folder holds delta archives with only the inner files that
changed in that revision, under the same archive names (thousands of them are empty 8 KiB stubs). Each top-level
`<revision>/` folder holds full copies of the small `*_Definition.dat` scenario packs and of `Glad.dat`. The
content of an inner path is the newest revision's copy.

Two archive versions exist. Version 2 covers everything up to the revision before 201602; version 3 covers
everything shipped with 201602. Both use the same path dictionary. Version 3 has a new header, checks entries with
CRC32 where version 2 used MD5, and writes `/` where version 2 wrote `\`. Older community tools stop at version 2.

**Gotchas.**
- Current GDScript, LevelDesign and other CNDF files are zstd-compressed, so an extraction needs a zstd decoder.
- Scenario scripts still ship as compiled Python (`.xyz`), but build 201602 runs the GDScript instead
  ([[gdscript-is-what-loads]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-edat-inventory](../trials/2026-11-02-edat-inventory.md)
- Gates: [`modkit.core.edat.verify_entry`](../../src/modkit/core/edat.py)
- Skills: [`components/core/skills/warno-setup/references/stock-corpus.md`](../../skills/warno-setup/references/stock-corpus.md)
<!-- referenced-by:end -->
