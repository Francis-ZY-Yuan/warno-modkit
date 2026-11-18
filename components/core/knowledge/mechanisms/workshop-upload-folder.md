---
id: workshop-upload-folder
title: The Workshop upload sends the mod folder as it is; a scenario mod needs no generate step
status: PROBED
last_verified: 212400 2026-11-18
source: stock-data
topics: [mod-packaging, game-updates]
trials: [2026-11-02-workshop-publishing-survey, 2026-11-12-twin-strike-workshop-upload, 2026-11-12-twin-strike-workshop-page, 2026-11-18-twin-strike-211352-play4, 2026-11-18-twin-strike-workshop-update]
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
- Every upload also resets the item's title to `Config.ini`'s `Name`, and only the upload sets its main image
  ([[workshop-item-page]]).
- Calling the game with `-uploadmod` directly should need no write access to the install; only the official batch
  route wants a copy of the mod inside the install's `Mods` folder.
- A direct call is handed to Steam, which asks to confirm the game's arguments (its ShowGameArgs prompt): the
  upload waits for a click at the PC, so it cannot run unattended ([[2026-11-18-twin-strike-workshop-update]]).
- The upload stamps the running exe's build into `Config.ini`'s `ModGenVersion`, whatever build the mod was made for
  ([[mod-version-and-config-lines]], [[2026-11-18-twin-strike-workshop-update]]). Upload before a game update lands, or
  after a rebuild for it.
- The official update script merges NDF projects and deletes the mod's `Gen` folder. A scenario-only mod has nothing
  to merge; its update is a rebuild ([[mod-version-and-config-lines]]).
- Do a dry run (everything short of the upload) and a first upload as private or hidden.
- None of the Workshop items surveyed shipped an Operation. Twin Strike (item 3838528915) does; installing it from a
  subscription is untested.
- A local copy and a subscribed copy of the same ID: seen once, on build 211352, the local copy in the Saved Games
  `mod` folder loaded while the subscribed Workshop item, an older build, was active
  ([[2026-11-18-twin-strike-211352-play4]]). One sighting: not yet a rule.

**On build 210942: the first upload** ([[2026-11-12-twin-strike-workshop-upload]]). Twin Strike was uploaded with
210942's own `UploadMod.bat` line, `WARNO.exe -headless -datapackonly -uploadmod "<Name>"
CommonData:Clusters/Bootstrap/ClusterBootstrapUploadMod.ndf`, and no generate step:
- `Gen/Version.ndf` and the 3 packs stayed byte-identical to the build: `-datapackonly` did not touch them;
- the upload rewrote the installed `Config.ini`: it set `ID` and `TagList = Scenarios`, and dropped the
  `Description =` line, the `CosmeticOnly` line and the empty `[Config]` section's header line.

Open: whether the game still lists a mod with no `[Config]` section. Packaging keeps writing it
([[mod-version-and-config-lines]]).

**On build 212400: an update upload** ([[2026-11-18-twin-strike-workshop-update]]). WARNO updated to 212400 minutes
before Twin Strike's update upload, of its build made for 211352, ran with the same call:
- `Gen/Version.ndf` and the 3 packs again stayed byte-identical, and the item's file size equals the folder's bytes;
- `Config.ini` was rewritten with `ModGenVersion = 212400`, the running exe's build; `ID` and `TagList` were kept,
  and it still has no `[Config]` section.

This verifies the upload on 212400's exe, nothing else: Twin Strike has not been built or played on 212400.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-workshop-publishing-survey](../trials/2026-11-02-workshop-publishing-survey.md), [2026-11-12-twin-strike-workshop-page](../trials/2026-11-12-twin-strike-workshop-page.md), [2026-11-12-twin-strike-workshop-upload](../trials/2026-11-12-twin-strike-workshop-upload.md), [2026-11-18-twin-strike-211352-play4](../../../ops/knowledge/trials/2026-11-18-twin-strike-211352-play4.md), [2026-11-18-twin-strike-workshop-update](../trials/2026-11-18-twin-strike-workshop-update.md)
- Skills: [`components/core/skills/warno-ship/SKILL.md`](../../skills/warno-ship/SKILL.md), [`components/core/skills/warno-ship/references/workshop-publishing.md`](../../skills/warno-ship/references/workshop-publishing.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../../ops/examples/twin-strike/README.md)
- Records: [2026-11-12-twin-strike-workshop-upload](../trials/2026-11-12-twin-strike-workshop-upload.md), [2026-11-18-twin-strike-211352-play4](../../../ops/knowledge/trials/2026-11-18-twin-strike-211352-play4.md), [2026-11-18-twin-strike-workshop-update](../trials/2026-11-18-twin-strike-workshop-update.md)
<!-- referenced-by:end -->
