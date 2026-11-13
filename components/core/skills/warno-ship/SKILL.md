---
name: warno-ship
description: Use when sharing a finished WARNO mod with other players, uploading it to the Steam Workshop, writing or checking its Workshop page, or updating a shared mod after a game update.
---

# Shipping a mod

## Overview

Ship only what was played. Two routes: a one-click installer you send to friends, and the Steam Workshop through
the game's own upload. In both, the folder that leaves your machine must be exactly the build you tested, with
nothing personal in it.

`python` is your venv's interpreter (see `warno-setup`).

## Before either route

- Every gate passes (`warno-gates`), and the build was played to its end (`warno-probe-and-playtest`).
- The mod folder holds only what the mod needs: `Config.ini`, `Gen/Version.ndf`, `Scenarios/*.dat`, plus any loose
  files your mod really loads. No backups, no notes, no local installer's `.modinstall` bookkeeping file.
- Nothing personal: search every file, including the files inside the packs, for your user name and your local
  paths.

## Route 1: the share installer

```
python -m modkit.core.install <built_mod_dir> --title "<title in the game's menu>" [--out DIR]
```

It writes `Install <ModName>.cmd` (one file to send) and `<ModName>-share.zip` (the installer, the mod folder for a
manual install, and a README), by default into `share/` in your build folder (`build/` beside `modkit.local.toml`,
see `warno-setup`). The installer copies the mod into the player's
`Saved Games\EugenSystems\WARNO\mod\`, checks every file's SHA-256, and switches it on as the Mod Center would.

It refuses a folder with no `Config.ini`, a Gameplay mod (one that changes unit data), and a mod that requires other
mods. A component can add its own checks through its installer hook.

## Route 2: the Steam Workshop

The modder runs the upload, never Claude. Full checklist:
[references/workshop-publishing.md](references/workshop-publishing.md); the item page:
[references/workshop-page.md](references/workshop-page.md). In short:

1. **`Config.ini`:** `Name` equals the folder name. `ID = 0` for the first upload only, then the item's ID forever
   after ([[workshop-upload-folder]]): a rebuild that resets it publishes a duplicate item. `ModGenVersion` should
   be the current game build; it comes from the toolkit (see "After a game update"). `[Config]` stays empty for a
   scenario-only mod. `PreviewImagePath` names the main image, at a path without your user name (it is published),
   or is empty for the first upload.
2. **Install exactly the release** into your Saved Games `mod\` folder and compare it file by file with the build.
3. **Upload with the game's own tool,** with WARNO closed, Steam running and the game's online login working.
4. **Set the item Hidden at once** if it isn't ready: the tool has no visibility switch.
5. **Copy the new ID into your build** and commit it.
6. **Write the item page from files you commit:** `workshop/item.toml` (ID, mod name, title), the description,
   the main image and the gallery. The upload sets the main image; the item's web pages set the title, the
   description and the gallery ([[workshop-item-page]]). The page says: unofficial and not affiliated with Eugen
   Systems; contains modified Eugen game data; single-player; the game build it was made for; may break after game
   updates. No donation links.
7. **Write the change note:** the upload writes only `Game Version = <build>` / `Mod Version = <Version>`. Keep each
   upload's real note in `workshop/changes.toml` (item.toml's `changes`; one table per upload, newest first, the
   coming one `[next]`), paste it over the default on the item's Change Notes page (`python -m modkit.core.workshop
   note workshop/item.toml` prints it), then rename `[next]` to the note's id, which the check names.
8. **Check the live page:** `python -m modkit.core.workshop check workshop/item.toml`.

**Every later upload** resets the title to `Config.ini`'s `Name` and adds a default change note: write its note as
`[next]` in `changes.toml` before uploading, then set the title, paste the note and run the check. After a reinstall, set
`PreviewImagePath` again before uploading.

## After a game update

A scenario-only mod has an empty `[Config]`, so the game won't mark it outdated, but it can still break
([[mod-version-and-config-lines]]). Re-extract (`warno-setup`), rebuild, play it again, then re-share or re-upload to
the same ID.

The build number a mod ships, in `Gen/Version.ndf` and `ModGenVersion`, is not yours to set: it lives in
`modkit.core.packaging` (`VERSION_NDF`, `CONFIG_INI`), so a new game build needs a toolkit release that updates it.
Don't edit the installed core; until that release, the mod ships the build the toolkit names.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Uploading the build folder you didn't play | Upload exactly the installed, played release |
| `ID = 0` after the first upload | Keep the item's ID in the build |
| A preview image path under your user folder | It is published inside `Config.ini`; move it |
| Editing the page on Steam only | Change the `workshop/` files first, then the page, then run the check |
| Leaving the title as the upload reset it | Set it again after every upload |
| Leaving the game's default change note | Paste the release's note from `changes.toml` over it |
| Shipping a Gameplay file in an Operation mod | It makes the game relaunch with mods off ([[gameplay-mod-relaunch]]) |
