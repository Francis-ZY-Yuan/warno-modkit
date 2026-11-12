---
id: txn-tag-config-hash
title: Build 210942 loads a compiled .txn only when its .txn.tag holds the ConfigHash the game computes for the transaction; any other makes it compile the sources
status: RE
last_verified: 210942 2026-11-12
source: exe-analysis
topics: [files-and-formats, loading-and-crashes, game-updates]
gates: [modkit.ops.gates.check_config_hashes]
shapes: [modkit.core.txntag.config_hash]
trials: [2026-11-12-twin-strike-launch-config-hash, 2026-11-12-config-hash-stock-survey, 2026-11-12-twin-strike-210942-play1]
stock_precedent: every one of the 331 stock .txn.tag of a 210942 extraction whose transaction the data names (by a TNDFTransaction, or by a folder scan) holds exactly the computed ConfigHash, all 167 of the scenario packs' among them
---
**What the game does.** Before it loads a compiled transaction, `<BaseName>.txn`, the game computes a ConfigHash from
the transaction that names it and compares it with the one in `<BaseName>.txn.tag`. When they differ it treats the
`.txn` as stale and compiles the transaction from its NDF sources instead; a mod ships none, so the game stops with
"NDF parsing error. Retry?" and "File not found" for the transaction's first source. The tag's source hashes count
only for a source the install holds, which is how stock loads with none of its sources.

**What the hash covers.** The transaction's BaseName, NameSpace, UsingNamespaces and Files, in order; not its
Directories, Public or GenerateCRC, and not the files' contents. A file's path is hashed by its components after the
alias. `modkit.core.txntag` computes it; it reproduces every stock tag whose transaction the data names:
- a scenario's ScenarioLoader and GDScript, from the TNDFTransaction that names each (in the ScenarioInfo and in the
  ScenarioLoader);
- its ScenarioInfo, MapConfiguration and TrophyDef, from the game's scan of every scenario folder: BaseName
  `Scenarios/<scenario>/<Kind>.txn`, the scan's NameSpace, and the folder's found file
  (`ScenariosData:/<scenario>/Scenario.ndf`, `MapPack.ndf`, `Trophy.ndf`) ahead of the scan's own files.

So a clone that renames its scenario changes every one of its tags' ConfigHash, and must write the new ones.

**How it was found.** The first 210942 build of Twin Strike kept Survivors' ConfigHashes and stopped at load
([[2026-11-12-twin-strike-launch-config-hash]]). The rule was read in the game's executable and is held by a gate proven
both ways: it fails that build on all four of its tags and passes every stock tag. Seen in play: the next build,
which holds the computed hashes, loaded with no error and played ([[2026-11-12-twin-strike-210942-play1]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-config-hash-stock-survey](../trials/2026-11-12-config-hash-stock-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [2026-11-12-twin-strike-launch-config-hash](../trials/2026-11-12-twin-strike-launch-config-hash.md)
- Gates: [`modkit.ops.gates.check_config_hashes`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.core.txntag.config_hash`](../../../core/src/modkit/core/txntag.py)
- Records: [2026-11-12-config-hash-stock-survey](../trials/2026-11-12-config-hash-stock-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [2026-11-12-twin-strike-launch-config-hash](../trials/2026-11-12-twin-strike-launch-config-hash.md), [scenario-definition-layout](scenario-definition-layout.md)
<!-- referenced-by:end -->
