---
id: operation-menu-registration
title: A new scenario id in a mod's Scenarios folder is listed and launches; a stock name is not overridden
status: PLAYED
last_verified: 201602 2026-11-11
source: play
topics: [operation-setup, game-updates]
trials: [2026-11-02-same-name-pack-override, 2026-11-02-new-scenario-id-loads, 2026-11-02-gdscript-format-survey, 2026-11-06-probe2-play-run-a, 2026-11-11-twin-strike-launch1-duplicate-menu-order, 2026-11-12-port-210942-survey]
---
**What the game does.** No central list of Operations exists. The menu is built from every mounted
`NDF/Scenarios/<scenario>/MapConfiguration.txn` (build 201602: `NDF/Scenarios/MapConfiguration/<scenario>.ndfbin`;
[[scenario-definition-layout]]) whose `TChallengeMapInfo.ChapterPack` is `$/MapPacks/Challenges`,
probably ordered by `OrderToChainMission`. The game scans each active mod's `Scenarios/` folder, so a mod that ships
`<scenario>_Definition.dat`, `_Details.dat` and `_Assets.dat` under a new scenario id gets a menu entry that
launches.

**Gotchas.**
- A pack with a stock scenario's name in a mod does not replace the stock pack. Use a new id.
- A new Operation needs a fresh GUID shared by `TChallengeMapInfo.GUID` and `TScenarioDefinition.GUID`
  (`TScenarioLoadInfo` on 201602), and every
  `$/ClusterMap/<scenario>`, `$/ScenarioInfo/<scenario>` and `ScenariosData:/<scenario>` path rewritten.
- A second mod cloned from the same template needs its own identity too ([[content-identity-unique]]).
- Every Operation needs its own `OrderToChainMission`. When two active mods' Operations hold the same one, the game
  stops at start with a map pack configuration error naming it
  ([[2026-11-11-twin-strike-launch1-duplicate-menu-order]]). The 16 stock Operations each hold their own, so a clone
  that keeps its template's fails too; the `menu-order` gate catches a stock Operation's. Give a published Operation
  its derived order (`modkit.ops.leveldesign.derived_menu_order`, a hash of its scenario GUID), never a hand pick
  ([[content-identity-unique]]).

**On build 210942: unverified in play.** The plays above were on 201602. Build 210942 reads the menu entry and the
scenario list from the new Definition layout, each kind by a name its own data gives ([[scenario-definition-layout]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-gdscript-format-survey](../trials/2026-11-02-gdscript-format-survey.md), [2026-11-02-new-scenario-id-loads](../trials/2026-11-02-new-scenario-id-loads.md), [2026-11-02-same-name-pack-override](../../../core/knowledge/trials/2026-11-02-same-name-pack-override.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md), [2026-11-11-twin-strike-launch1-duplicate-menu-order](../trials/2026-11-11-twin-strike-launch1-duplicate-menu-order.md), [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/core/skills/warno-setup/references/scenario-python-and-prior-art.md`](../../../core/skills/warno-setup/references/scenario-python-and-prior-art.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md)
- Records: [2026-11-11-twin-strike-launch1-duplicate-menu-order](../trials/2026-11-11-twin-strike-launch1-duplicate-menu-order.md)
<!-- referenced-by:end -->
