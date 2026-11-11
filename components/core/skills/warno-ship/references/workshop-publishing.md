# Publishing a scenario mod to the Steam Workshop

Read from the official upload scripts, the game's mod-manager data and installed Workshop items, on build 201602.
No upload was made while writing this, so the upload itself is still [[workshop-upload-folder]]'s open question.

## What the upload sends

The game's own upload (`WARNO.exe -uploadmod <Name>`) takes the folder
`%USERPROFILE%\Saved Games\EugenSystems\WARNO\mod\<Name>\`, the same folder a local install fills, and sends
**every file in it**. It creates the Workshop item through Steam the first time and updates it after that, and also
sends a copy to Eugen's own mod server. It needs Steam running, logged in to the account that will own the item,
and a working connection to the game's online services.

The upload rewrites `Config.ini`: it fills `TagList`, `ID` and `ModGenVersion`. A scenario-only mod comes out tagged
Scenarios.

## A scenario mod needs no generate step

The official mod tools generate a large `Gen/` tree (resource registry, compiled NDF, cluster hashes). That tree
matters only to mods that replace game clusters. A scenario mod made of `Config.ini`, `Gen/Version.ndf` and its
`Scenarios/*.dat` packs is already active in the Mod Center, and it is what the map editor's own scenario route
produces too ([[mod-version-and-config-lines]]).

## The two ways to run it

- **Official:** the mod tools' upload batch file, run from a mod project inside the game folder. It needs write
  access to the game install, and it also writes a backup there.
- **Direct:** call the game's executable by its full path from any folder:
  `"<game folder>\WARNO.exe" -headless -uploadmod "<Name>" CommonData:Clusters/Bootstrap/ClusterBootstrapUploadMod.ndf`.
  Nothing is written to the install by you; the game itself writes its usual log files on every launch. The only
  file the upload changes is your mod's `Config.ini`.

## Checklist

**Freeze the release**
1. Build the release, and write a manifest of path, size and SHA-256 for every file.
2. Expect only `Config.ini`, `Gen/Version.ndf`, `Scenarios/*.dat` and the loose files your mod loads. No
   `.modinstall`, no `*.bak`, no `Config - Copy.ini`. Workshop items have shipped all of these by accident.

**`Config.ini`**
3. `Name` equals the folder name (it is also the item's first title).
4. `ID` is `0` for the first upload, and the recorded item ID for every later one. A non-zero ID updates that item,
   which must belong to the uploading account. Reset it to 0 and the next upload creates a duplicate item.
5. `ModGenVersion` equals the current game build (the newest numeric folder under the install's `Data/PC`). The
   toolkit writes it (`modkit.core.packaging`); if it names an older build, the toolkit needs a release for this game
   build (see "After a game update"). Don't edit it.
6. `[Config]` is present and empty. A `cluster=md5` line belongs only to a mod that replaces that cluster.
7. `PreviewImagePath` is empty, or names an image of about 1 MB or less at a path without your user name. The path
   itself is published inside `Config.ini`, and an image placed inside the mod folder ships too.

**Content**
8. `Gen/Version.ndf` is exactly `version is '<current build>'` and a newline. The toolkit writes it too
   (`modkit.core.packaging.VERSION_NDF`), with the same caveat as item 5.
9. Every pack extracts with `python -m modkit.core.edat extract <pack> <scratch dir> --verify` (0 checksum
   mismatches), and the build's own gates pass.
10. No file, including the decompressed files inside the packs, holds your user name or a local path.

**Install and play**
11. Install exactly the release into your Saved Games `mod\` folder and compare it with the manifest.
12. Start the game normally: the mod is listed once, active, not greyed out, with no "outdated mods" message; the
    Operation appears, starts and reaches its end.

**Upload**
13. The upload tool has no visibility setting. Expect the new item to be visible until you change it on its page,
    and set it Hidden at once if it isn't ready.
14. Read the new `ID` back from the installed `Config.ini`, put it into your build, and commit.
15. Test as a subscriber from a second Steam account or machine. Subscribing on the machine that uploaded shows the
    mod twice: remove the local copy first and put it back afterwards.

**The item page**
16. Say: unofficial and not affiliated with or endorsed by Eugen Systems; contains modified Eugen game data;
    single-player; the game build it was made for; may break after game updates. No donation links.

## After a game update

The game marks a mod outdated, and switches it off, when its `Gen/Version.ndf` is missing or a `[Config]` cluster
hash no longer matches the game. A scenario-only mod has no cluster lines, so an update rarely makes it outdated, but
it can still break: its packs depend on the stock class schemas, map item GUIDs, dictionary tokens and the files it
cloned. After each update: re-extract, rebuild, play it again, then upload to the same ID.

The build number in `Gen/Version.ndf` and `ModGenVersion` is not the modder's to set: both live in
`modkit.core.packaging` (`VERSION_NDF` and `CONFIG_INI`), and a new game build needs a toolkit release that updates
them. Never edit them in an installed core: an update replaces it.

Whether the value in `Gen/Version.ndf` must equal the running build is not known yet.
