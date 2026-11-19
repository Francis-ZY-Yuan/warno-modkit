---
id: txn-tag-config-hash
title: The game loads a compiled .txn only when its .txn.tag holds the ConfigHash it computes for the transaction and lists every source with the hash the install holds now; anything else makes it compile the sources
status: RE
last_verified: 212400 2026-11-18
source: exe-analysis
topics: [files-and-formats, loading-and-crashes, game-updates]
gates: [modkit.ops.gates.check_config_hashes, modkit.ops.gates.check_tag_sources]
shapes: [modkit.core.txntag.config_hash]
trials: [2026-11-12-twin-strike-launch-config-hash, 2026-11-12-config-hash-stock-survey, 2026-11-12-twin-strike-210942-play1, 2026-11-13-twin-strike-210942-play2, 2026-11-18-twin-strike-211352-play4, 2026-11-18-twin-strike-212400-workshop-launch]
stock_precedent: every one of the 331 stock .txn.tag of a 210942 extraction whose transaction the data names (by a TNDFTransaction, or by a folder scan) holds exactly the computed ConfigHash, all 167 of the scenario packs' among them; in each of 211352 and 212400, the 1473 tags of the 357 stock scenario packs hold one source list per kind and one hash per source, the scenario's own folder aside
---
**What the game does.** Before it loads a compiled transaction, `<BaseName>.txn`, the game computes a ConfigHash from
the transaction that names it and compares it with the one in `<BaseName>.txn.tag`. When they differ it treats the
`.txn` as stale and compiles the transaction from its NDF sources instead; a mod ships none, so the game stops with
"NDF parsing error. Retry?" and "File not found" for the transaction's first source.

**What the source hashes cover.** The tag also lists the transaction's sources, each with its hash when the `.txn` was
compiled. The sources are the transaction's Files and the files under its Directories. The game holds the `.txn`
current only when the tag lists every one of them and each source the install holds has the same hash now. It skips a
source the install doesn't hold, which is how stock and mods load with none of a scenario's own files, and a tag source
outside the list. The scanned kinds (ScenarioInfo, MapConfiguration, TrophyDef) take their lists from the installed
game's scans; the ScenarioLoader and GDScript from the TNDFTransaction the scenario's own data names. Either way, the
templates' hashes are the install's.

So a game update that changes a scenario template, a source every scenario's tags list such as `ScenarioLoader.ndf`,
makes every built scenario stale until it is rebuilt from the new stock. A Workshop copy breaks for every player at
that update ([[2026-11-18-twin-strike-212400-workshop-launch]]). Gate 5's tag-sources holds each tag to the stock tags
of the newest installed build: for each kind, the same source list apart from the scenario's own folder (and
GDScript's own scripts), and stock's hash for each source stock lists. That is stricter than the game, which ignores
the order and extra sources. It runs in the build's gates and in `modkit.ops.coinstall` for every active mod.

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
which holds the computed hashes, loaded with no error and played ([[2026-11-12-twin-strike-210942-play1]]). The
source rule was read in 212400's executable after that update broke Twin Strike's Workshop copy, built for 211352
([[2026-11-18-twin-strike-212400-workshop-launch]]). Its gate is proven both ways: it fails that copy against 212400's
stock tags on all four of its tags and passes it against 211352's, and every stock scenario pack of both builds passes
against its own build.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-config-hash-stock-survey](../trials/2026-11-12-config-hash-stock-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [2026-11-12-twin-strike-launch-config-hash](../trials/2026-11-12-twin-strike-launch-config-hash.md), [2026-11-13-twin-strike-210942-play2](../trials/2026-11-13-twin-strike-210942-play2.md), [2026-11-18-twin-strike-211352-play4](../trials/2026-11-18-twin-strike-211352-play4.md), [2026-11-18-twin-strike-212400-workshop-launch](../trials/2026-11-18-twin-strike-212400-workshop-launch.md)
- Gates: [`modkit.ops.gates.check_config_hashes`](../../src/modkit/ops/gates.py), [`modkit.ops.gates.check_tag_sources`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.core.txntag.config_hash`](../../../core/src/modkit/core/txntag.py)
- Skills: [`components/core/skills/warno-ship/SKILL.md`](../../../core/skills/warno-ship/SKILL.md), [`components/core/skills/warno-ship/references/workshop-publishing.md`](../../../core/skills/warno-ship/references/workshop-publishing.md)
- Records: [2026-11-12-config-hash-stock-survey](../trials/2026-11-12-config-hash-stock-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [2026-11-12-twin-strike-launch-config-hash](../trials/2026-11-12-twin-strike-launch-config-hash.md), [2026-11-13-twin-strike-210942-play2](../trials/2026-11-13-twin-strike-210942-play2.md), [2026-11-18-build-212400-port](../../../core/knowledge/trials/2026-11-18-build-212400-port.md), [2026-11-18-twin-strike-211352-play4](../trials/2026-11-18-twin-strike-211352-play4.md), [2026-11-18-twin-strike-212400-workshop-launch](../trials/2026-11-18-twin-strike-212400-workshop-launch.md), [mod-version-and-config-lines](../../../core/knowledge/mechanisms/mod-version-and-config-lines.md), [scenario-definition-layout](scenario-definition-layout.md)
<!-- referenced-by:end -->
