---
id: workshop-upload-folder
title: The Workshop upload sends the mod folder as it is; a scenario mod needs no generate step
status: PROBED
last_verified: 210942 2026-11-12
source: stock-data
topics: [mod-packaging, game-updates]
trials: [2026-11-02-workshop-publishing-survey, 2026-11-12-twin-strike-workshop-upload]
---
**What the game does.** The official upload (`WARNO.exe -uploadmod <Name>`) uploads your Saved Games
`mod\<Name>\` folder, the same folder a local install fills. A scenario mod made of `Config.ini`,
`Gen/Version.ndf` and `Scenarios/*.dat` packs matches what the map editor's official route produces for scenarios.
The extra files the official generate step writes matter only to mods that replace game clusters.

**Gotchas.**
- Everything in the folder is uploaded. Remove a local installer's bookkeeping file first; it can hold a local path.
- The upload writes the item's ID into `Config.ini`. A rebuild that resets `ID = 0` would publish a second item on
  the next upload, so keep the ID across rebuilds. The toolkit does: a build writes the ID its profile names
  (`mod_id`, 0 until the first upload), and the share installer carries an installed non-zero ID over a build's 0.
- Calling the game with `-uploadmod` directly should need no write access to the install; only the official batch
  route wants a copy of the mod inside the install's `Mods` folder.
- The official update script merges NDF projects and deletes the mod's `Gen` folder. A scenario-only mod has nothing
  to merge; its update is a rebuild ([[mod-version-and-config-lines]]).
- Do a dry run (everything short of the upload) and a first upload as private or hidden.
- None of the Workshop items surveyed shipped an Operation. Twin Strike (item 3838528915) does; installing it from a
  subscription is untested.

**On build 210942: the first upload** ([[2026-11-12-twin-strike-workshop-upload]]). Twin Strike was uploaded with
210942's own `UploadMod.bat` line, `WARNO.exe -headless -datapackonly -uploadmod "<Name>"
CommonData:Clusters/Bootstrap/ClusterBootstrapUploadMod.ndf`, and no generate step:
- `Gen/Version.ndf` and the 3 packs stayed byte-identical to the build: `-datapackonly` did not touch them;
- the upload rewrote the installed `Config.ini`: it set `ID` and `TagList = Scenarios`, and dropped the
  `Description =` line, the `CosmeticOnly` line and the empty `[Config]` section's header line.

Open: whether the game still lists a mod with no `[Config]` section. Packaging keeps writing it
([[mod-version-and-config-lines]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-workshop-publishing-survey](../trials/2026-11-02-workshop-publishing-survey.md), [2026-11-12-twin-strike-workshop-upload](../trials/2026-11-12-twin-strike-workshop-upload.md)
- Skills: [`components/core/skills/warno-ship/SKILL.md`](../../skills/warno-ship/SKILL.md), [`components/core/skills/warno-ship/references/workshop-publishing.md`](../../skills/warno-ship/references/workshop-publishing.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../../ops/examples/twin-strike/README.md)
- Records: [2026-11-12-twin-strike-workshop-upload](../trials/2026-11-12-twin-strike-workshop-upload.md)
<!-- referenced-by:end -->
