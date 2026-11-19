---
id: 2026-11-18-twin-strike-workshop-update
kind: launch
# the installed Twin Strike, byte-identical to main's build at 7777a3d (the copy played in 2026-11-18-twin-strike-211352-play4)
build: 7777a3d
# the build of the exe that ran the upload: WARNO updated to 212400 minutes before it ran
game_version: 212400
mechanisms: [workshop-upload-folder, mod-version-and-config-lines]
outcome: pass
result: Workshop item 3838528915 updated (update 1795010309) with the 211352 build; the upload rewrote Config.ini's ModGenVersion to 212400, the running exe's build, so the Workshop copy pairs Gen/Version.ndf 211352 with ModGenVersion 212400
---
Twin Strike's Workshop update, of the installed build made for 211352, run with the same direct call as the first
upload ([[2026-11-12-twin-strike-workshop-upload]]): `WARNO.exe -headless -datapackonly -uploadmod "TwinStrike" ...`.
- Steam took the call over (`steam://run/1611600//<args>`), answered its launch-option prompt on its own, then waited
  on its game-arguments confirmation (ShowGameArgs) until a click at the PC answered it. The game then ran headless
  for 58 s, and the item's update is 1795010309 ([[workshop-upload-folder]]).
- WARNO's update to build 212400 came 9 minutes before that click, so the upload ran on 212400's exe.
- The installed folder, compared with before the upload: `Gen/Version.ndf` (still 211352) and the 3 packs stayed
  byte-identical, so `-datapackonly` left them alone. Only `Config.ini` changed: its `ModGenVersion` went from 211352
  to 212400, the running exe's build, not the build the mod was made for. `ID` and `TagList = Scenarios` were kept,
  and it still has no `[Config]` section ([[mod-version-and-config-lines]]).
- The item's file size equals the folder's bytes, and its title was reset to the folder name, `TwinStrike`.

Nothing about 212400 has been surveyed, built or played: this upload shows only that 212400's exe uploads a folder,
not that Twin Strike, or any record, holds on 212400. Not seen: what the game makes of a Workshop copy whose two build
lines differ.

Launched on 212400, the copy this upload published stops with "NDF parsing error. Retry?"
([[2026-11-18-twin-strike-212400-workshop-launch]]).
