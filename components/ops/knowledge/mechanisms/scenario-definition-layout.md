---
id: scenario-definition-layout
title: Build 210942 reads a scenario's Definition files as NDF/Scenarios/<scenario>/<Kind>.txn, each beside its .txn.tag and .dbg
status: STOCK
last_verified: 210942 2026-11-12
source: stock-data
topics: [operation-setup, game-updates]
gates: [modkit.ops.gates.check_definition_layout, modkit.ops.gates.check_config_hashes, modkit.ops.gates.check_references]
shapes: [modkit.ops.rekey.def_path, modkit.ops.rekey.rekey_tag, modkit.ops.rekey.rekey_dbg, modkit.ops.rekey.generated_dbg]
trials: [2026-11-12-port-210942-survey, 2026-11-12-twin-strike-launch-config-hash, 2026-11-12-twin-strike-210942-play1]
stock_precedent: every .txn of a scenario, map or decor-set pack in a 210942 install ships beside its .txn.tag and its .dbg; 167 of 167 extracted .dbg hold one line per object of their .txn; 35 of 35 stock Definition folders pass the layout gate
---
**What the game does.** Since build 210942 a scenario's Definition pack holds, for each kind of file, three entries
under `NDF/Scenarios/<scenario>/`: `<Kind>.txn` (the compiled NDF, the format a 201602 `.ndfbin` had), `<Kind>.txn.tag`
(one `TNDFTagFile`: a ConfigHash and the source files it was cooked from, by game path, with their hashes) and
`<Kind>.dbg` (a source map: one line per object, `<name>;<source file>;<line>;<column>`, zstd-compressed). The kinds
are GDScript, MapConfiguration, ScenarioInfo, ScenarioLoader and TrophyDef. Build 201602 had
`NDF/Scenarios/<Kind>/<scenario>.ndfbin` and `.tag`, which 210942 never reads.

**How the game finds them.** The kind names are the game's data, not its exe's. Its own transactions (Transactions.dat:
`ClusterInitialisationData` and `ClusterMainScenario`) scan every `NDF/Scenarios/` folder for `MapConfiguration.txn`
(the Operations menu), `TrophyDef.txn` and `ScenarioInfo.txn` (the scenario list), each a `TClusterMultipleNdfTransactions`
with DirName `Scenarios` (`gates.SCANNED_KINDS`, pinned to that data by a test). The ScenarioInfo, a
`TScenarioDefinition` (`TScenarioLoadInfo` on 201602), names `Scenarios/<scenario>/ScenarioLoader.txn` as its
transaction's BaseName, and the ScenarioLoader names `Scenarios/<scenario>/GDScript.txn`; the mod SDK's
`CommonData/Map/Template/ScenarioInfos.ndf` and `ScenarioLoader.ndf` build both names from the scenario folder.

**What a build ships.** The template's three entries re-keyed for each kind it keeps: the id in the .txn, in the tag's
source paths and in the source map; the tag's ConfigHash is the one the game computes for the re-keyed
transaction ([[txn-tag-config-hash]]), and its source hashes stay the cook's. A generated GDScript gets a source map of its
own, one line per object, each exported object named by its export path's last component as stock names it.

**Why a .dbg at all.** The game's own transactions in Transactions.dat ship no .dbg, so the loader does not need one
for every .txn; but no scenario, map or decor-set pack ships a .txn without one, and the mod SDK's manual and scripts
say nothing of them, and no Workshop mod was rebuilt for 210942 on the day it shipped. A build ships what every stock
scenario pack ships. Seen in play: a build so laid out, each `.txn` with its tag and source map, loaded and
played on 210942 ([[2026-11-12-twin-strike-210942-play1]]); whether the game needs the `.dbg` is not known.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [2026-11-12-twin-strike-launch-config-hash](../trials/2026-11-12-twin-strike-launch-config-hash.md)
- Gates: [`modkit.ops.gates.check_definition_layout`](../../src/modkit/ops/gates.py), [`modkit.ops.gates.check_config_hashes`](../../src/modkit/ops/gates.py), [`modkit.ops.gates.check_references`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.rekey.def_path`](../../src/modkit/ops/rekey.py), [`modkit.ops.rekey.rekey_tag`](../../src/modkit/ops/rekey.py), [`modkit.ops.rekey.rekey_dbg`](../../src/modkit/ops/rekey.py), [`modkit.ops.rekey.generated_dbg`](../../src/modkit/ops/rekey.py)
- Skills: [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Records: [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md), [2026-11-12-twin-strike-210942-play1](../trials/2026-11-12-twin-strike-210942-play1.md), [custom-operation-from-stock-parts](custom-operation-from-stock-parts.md), [gdscript-is-what-loads](gdscript-is-what-loads.md), [operation-menu-registration](operation-menu-registration.md), [script-effects-self-contained](script-effects-self-contained.md)
<!-- referenced-by:end -->
