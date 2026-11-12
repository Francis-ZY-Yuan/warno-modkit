---
id: 2026-11-12-twin-strike-launch-config-hash
kind: launch
build: 79640b3
game_version: 210942
mechanisms: [txn-tag-config-hash, scenario-definition-layout]
outcome: fail
symptom: "NDF parsing error. Retry? @file:ScenariosData:/challenge_OperationTwinStrike/Scenario.ndf@(0:0): File not found : 'ScenariosData:/challenge_OperationTwinStrike/Scenario.ndf'"
cause: Every .txn.tag of the clone kept its template's ConfigHash (Survivors'), so the game took each compiled .txn for stale and compiled the scenario's sources, which no mod ships; the first, at game load, was the scenario list's ScenarioInfo, whose first source is Scenario.ndf
result: The builder writes each tag's ConfigHash computed from its transaction (modkit.core.txntag); gate 5's config-hash fails that build on all four tags and passes every stock tag
---
The first build of Twin Strike for build 210942, the only active mod, stopped at load with the dialog above, with no
crash dump. Its four tags held Survivors' ConfigHashes; the game computes others for the clone's transactions, whose
BaseName and files name `challenge_OperationTwinStrike` ([[txn-tag-config-hash]]). The ScenarioInfo and
ScenarioLoader name `Scenario.ndf` first, the MapConfiguration `MapPack.ndf`; the scenario list loads every
ScenarioInfo at game load, before any Operation starts. `python -m modkit.ops.packs check` now fails that build
(config-hash) and passes the rebuilt one.
