---
id: workshop-upload-folder
title: The Workshop upload sends the mod folder as it is; a scenario mod needs no generate step
status: UNTESTED
source: stock-data
topics: [mod-packaging]
trials: [2026-11-02-workshop-publishing-survey]
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
- No Workshop item has shipped an Operation so far, so installing one from a subscription is untested.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-workshop-publishing-survey](../trials/2026-11-02-workshop-publishing-survey.md)
- Skills: [`components/core/skills/warno-ship/SKILL.md`](../../skills/warno-ship/SKILL.md), [`components/core/skills/warno-ship/references/workshop-publishing.md`](../../skills/warno-ship/references/workshop-publishing.md)
<!-- referenced-by:end -->
