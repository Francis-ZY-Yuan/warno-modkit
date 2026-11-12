---
id: game-build-classes
title: A game update removes and renames classes and properties; a mod's files may hold only those the installed build's stock holds
status: STOCK
last_verified: 210942 2026-11-12
source: stock-data
topics: [operation-setup, game-updates]
gates: [modkit.ops.gates.check_stock_classes]
trials: [2026-11-12-port-210942-survey]
stock_precedent: the 638 stock files the gate surveys on 210942 (every scenario pack's Definition and Details, and GameFx) hold none of the 34 classes and properties of a 201602 build of Twin Strike that 210942 dropped
---
**What changed in 210942, for an Operation.** The scenario's ScenarioInfo root `TScenarioLoadInfo` became
`TScenarioDefinition`; the script root `TGDDescriptorLaunchEffetStandard` became `TGDDescriptorLaunchEffetMap`, with
the same three properties; a GdItems tag's `GUID1`..`GUID4` became one `GameDesignAddonId` GUID
([[leveldesign-guid-binding]]); the ScenarioLoader lost `TClusterAddPythonPath`, and its datapack mount's `Name` became
`MountingPoint`; `TGDDescriptorGereObjectif.BonusScoreMission` and `TChallengeMapInfo.GameModeComponentTexture` are gone;
the .tag sidecar class `TGladNDFBinHandler_FileList` became `TNDFTagFile`; and GameFx names its objects with
`_NdfIdentifierName`, not `_ShortDatabaseName` ([[script-effects-self-contained]]). None of the old names is in any
210942 stock file the gate reads.

**The rule.** The game knows its own build's classes and properties. So every class and every (class, property) a
build ships must be one the stock files of its kind hold on the installed build: every scenario pack's Definition and
Details, and the game's GameFx for an effect wrapper's shapes. A native shape no stock file writes passes only as a
content's reviewed admission (`Content.extra_shapes`). The gate runs in every build (gate 5) and on any built mod
folder (`python -m modkit.ops.packs check DIR`): it fails the 201602 build of Twin Strike on 39 shapes (those 34, and
the 5 native shapes its content admits) and passes every stock scenario ([[2026-11-12-port-210942-survey]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md)
- Gates: [`modkit.ops.gates.check_stock_classes`](../../src/modkit/ops/gates.py)
- Skills: [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Records: [2026-11-12-port-210942-survey](../trials/2026-11-12-port-210942-survey.md)
<!-- referenced-by:end -->
