---
id: 2026-11-12-twin-strike-workshop-upload
kind: launch
build: 2a9a0b6
game_version: 210942
mechanisms: [workshop-upload-folder, mod-version-and-config-lines]
outcome: pass
result: Twin Strike is Workshop item 3838528915 and its profile's WORKSHOP_ID holds that ID; packaging's Config.ini is unchanged, since whether the game lists a mod with no [Config] section is unseen
---
Twin Strike's first Workshop upload, of the installed build 2a9a0b6, run with build 210942's own `UploadMod.bat` line:
`WARNO.exe -headless -datapackonly -uploadmod "TwinStrike" CommonData:Clusters/Bootstrap/ClusterBootstrapUploadMod.ndf`.
It created item 3838528915. The installed folder, compared with the build afterwards:
- the 4 files other than `Config.ini`, `Gen/Version.ndf` and the 3 packs, stayed byte-identical: `-datapackonly` did
  not touch them ([[workshop-upload-folder]]);
- the upload rewrote the installed `Config.ini`: it set `ID = 3838528915` and `TagList = Scenarios`, and dropped the
  `Description =` line, the `CosmeticOnly` line, and the whole
  `[Config] ; Used for mod compatibility check, do not modify` header line, with nothing under it
  ([[mod-version-and-config-lines]]).

Not seen: whether the game still lists the installed mod with no `[Config]` section, and the item installed from a
subscription.
