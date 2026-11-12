# The stock corpus: how the install stores its data, and what setup builds from it

Measured on game build 201602, with what build 210942 changed noted where it applies. Everything here was read
from an install; nothing was written to it.

## The archives

Game data lives in edat archives (`.dat`) under the install's `Data/PC` folder, one folder per game build
(revision). See [[edat-revision-chain]] for the record.

- **The oldest revision folder is the full base install.** Each later revision adds a nested `<previous>/<revision>/`
  folder of **delta archives**: the same archive names, holding only the inner files that changed in that revision.
  Many deltas are empty 8 KiB stubs.
- **The game's own NDF** is `Transactions.dat` from build 210942 (`.txn` files in the newest delta folder). Up to
  201602 it was `Glad.dat` (`.ndfbin`), which 210942 still installs but no longer loads.
- **Each top-level `<revision>/` folder holds full copies of the small packs**: `Glad.dat`, and the
  `*_Definition.dat` packs of scenarios, maps and decor sets.
- **The content of an inner path is the newest revision's copy.** Overlay the base, then every delta up to the
  current build in ascending order. Small packs come from the current build's own folder.
- **Nothing marks a deleted file.** Files dropped or renamed upstream stay in older layers. Older archives used an
  `AllPlatforms/` root (`AllPlatforms/NDF/...`, `AllPlatforms/Localisation/<LANG>/<scenario>/X.dic`); newer ones
  ship the same files without it (`NDF/...`, `Localisation/<scenario>/X-<LANG>.dic`). Treat an `AllPlatforms/` file
  with a newer twin as stale.

Two archive versions exist. Version 2 covers every archive before build 201602, version 3 everything shipped with
it. Both use the same path dictionary; version 3 has a new header, checks entries with CRC32 instead of MD5, and
writes `/` instead of `\`. Older community tools read version 2 only. `python -m modkit.core.edat list|extract`
reads both and checks every entry against its stored checksum (`--verify`).

## What a scenario is made of

A scenario named `<S>` ships as up to four packs under `Scenarios/`:

| pack | holds |
| --- | --- |
| `<S>_Definition.dat` | from build 210942, `NDF/Scenarios/<S>/{GDScript,MapConfiguration,ScenarioInfo,ScenarioLoader,TrophyDef}.{txn,txn.tag,dbg}`; up to 201602, `NDF/Scenarios/{GDScript,MapConfiguration,ScenarioInfo,ScenarioLoader,Trophy}/<S>.{ndfbin,tag}` |
| `<S>_Details.dat` | `out/LevelDesign.ndfbin` (map items with GUIDs), the zone files under `out/`, `Items.sav`, `AIZones.sav`, camera paths |
| `<S>_Assets.dat` | voiced dialog (`.ess`), textures, the scenario's compiled Python (`.xyz`), dictionaries |
| `<S>_GameData.dat` | videos (`.webm`) |

- Script text resolves in the scenario's own `Localisation/<S>/Scripting/{Dialog,Localization}-<LANG>.dic`
  ([[localisation-tokens-packed]]).
- `GDScript/<S>.ndfbin` exists only from build 201602, and it is what the game runs
  ([[gdscript-is-what-loads]]).
- Compiled NDF files (`.ndfbin`, `.txn`, `.tag`, `.sav`) are CNDF containers with a raw, LZ4 or zstd body. Current files are
  zstd. `python -m modkit.core.ndfbin dump|info|roundtrip` reads them ([[ndfbin-round-trip]]).
- Localisation dictionaries (`.dic`) are TRAD files: `python -m modkit.core.trad dump`.

## What `setup extract` builds

Each component declares the stock paths it reads (`STOCK_PATHS` in its package). `python -m modkit.core.setup
extract --into DIR` builds exactly those, from your install, with the newest-revision rule above, and records the
game build it used. `setup check` compares that record and the rules table with the installed game. A component
that starts reading a new stock path declares it, so a fresh extraction always covers every reader.

Never commit anything from the corpus. Files, bulk tables and game text are Eugen's data; the toolkit regenerates
them on each machine.

## Map pictures (TGV)

`.tgv` files are textures. `python -m modkit.core.tgv info|topng` reads the uncompressed RGBA format that map
pictures use, and refuses any other format rather than guess. `frompng` writes that format the way stock menu
pictures are written; `roundtrip` proves it, re-encoding every scenario's `MapPackAssets/Textures/*.tgv` byte for byte.

| picture | where | pixels per map grid unit |
| --- | --- | --- |
| `Preview.tgv` (top-down colour render) | `PC/Texture/<map>/` in the map's `<map>_Assets.dat` | 512 |
| `Minimap.tgv` (flat map: built-up light, water darkest) | same | 256 |
| `MapTexture.tgv` (the Operation's menu picture) | the scenario's `MapPackAssets/Textures/` | not a map: often a regional overview, cropped or rotated |

**World to picture.** One grid unit is 655,360 world units. On the Preview, `px = X / 1280` and `py = Y / 1280`; on
the Minimap, divide by 2560. The origin is the top-left corner, +X runs right and +Y runs down. This was checked two
ways: playable-zone extents match the Preview's size in grid units on several maps, and tag positions classified
against the Minimap's land classes fit best with +Y down. The Operation's MapTexture cannot be used for this.
