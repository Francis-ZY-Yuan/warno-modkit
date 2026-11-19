---
id: 2026-11-18-twin-strike-212400-workshop-launch
kind: launch
# the Workshop copy of 2026-11-18: the installed build made for 211352, byte-identical to main's build at 7777a3d
build: 7777a3d
game_version: 212400
mechanisms: [txn-tag-config-hash]
outcome: fail
symptom: "NDF parsing error. Retry? @file:ScenariosData:/challenge_OperationTwinStrike/Scenario.ndf@(0:0): File not found : 'ScenariosData:/challenge_OperationTwinStrike/Scenario.ndf'"
cause: The 212400 update re-shipped the scenario templates, and the tags stayed 211352's. Four template sources every scenario's tags list took new hashes, and the ScenarioLoader, MapConfiguration and TrophyDef lists changed. So the game took the copy's compiled .txn files for stale and compiled the scenario's sources, which no mod ships. Scenario.ndf is first in the ScenarioInfo and ScenarioLoader lists
result: Gate 5's tag-sources (modkit.ops.gates.check_tag_sources) holds a mod's tags to the stock tags of the newest installed build. It runs in the build's gates and in coinstall for every active mod. It fails this copy against 212400's stock on all four tags, the ScenarioLoader among them, and passes it against 211352's. Every stock scenario pack of both builds passes against its own build
---
Twin Strike's Workshop copy was built for 211352 and uploaded on 2026-11-18
([[2026-11-18-twin-strike-workshop-update]]). WARNO had updated to 212400 nine minutes before the upload. A player reported an NDF error when launching the mission. A click at the PC reproduced it: the
Workshop copy was the only active mod, the local copy was moved aside, and the game stopped with the dialog above. The
symptom matches [[2026-11-12-twin-strike-launch-config-hash]], but the cause is new: the build was correct for the game
it was made for.

212400 re-shipped every stock scenario pack. The tags of the copy still held 211352's sources:
- `ScenarioLoader.ndf`, `ScenarioInfos.ndf`, `ScenarioGameplayConstants.ndf` and `UICommonEnum.ndf` hash differently
  on 212400;
- `CommonData:/System/Globals.ndf` left the ScenarioLoader list and the MapConfiguration and TrophyDef scans, and
  `CommonData:/Clusters/ReloadableType.ndf` joined the ScenarioLoader list.

Before it loads a compiled transaction, the game checks that the tag lists every source and that each source the
install holds has the hash it holds now ([[txn-tag-config-hash]]). On 212400, each of the copy's four tags fails that
check, so the game compiles their sources. A mod ships none, and the ScenarioInfo and ScenarioLoader name
`Scenario.ndf` first.

`python -m modkit.ops.packs check` on the Workshop folder, with `--stock` set to 212400's `Data/PC/<build>/Scenarios`,
now fails it on all four tags, naming each source and both hashes; with 211352's it passes. `python -m
modkit.ops.coinstall` flags it as stale while it is active. The fix is a rebuild from 212400's stock and a re-upload.
Every Workshop copy of a scenario breaks for every player at a game update that changes a scenario template.

**Re-upload.** The build the modder played on 212400, made from 212400's stock, was uploaded to the same item as update 1795053656 on 2026-11-19. The installed folder's packs and `Gen/Version.ndf` were unchanged by the upload; `Config.ini` was rewritten as before (TagList set; `Description`, `CosmeticOnly` and `[Config]` dropped; `ModGenVersion` 212400). No one has yet played the copy downloaded from the Workshop.
