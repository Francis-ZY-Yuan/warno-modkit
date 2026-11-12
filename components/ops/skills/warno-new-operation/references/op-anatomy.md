# Anatomy of an Operation build

What `modkit.ops.build` takes in, what it writes, and what it checks on the way. The module docstrings of
`modkit.ops.build` and `modkit.ops.profile` are the full statement; this is the map.

## In: a profile and its contents

An op is one **profile** (`OpProfile`: what every build of the op shares) and one or more **contents** (`Content`:
one build each). The example's `build.py` hands both to `modkit.ops.build.cli`, which adds `--content NAME` (a key
of the package's `CONTENTS`) and `--out DIR`. `modkit.ops.build.run(profile_factory, content_factory, out_dir)` is
the same build for any other front end. Both turn every failure into one `FAILED:` line and exit code 1.

Nothing reads a module setting, so two profiles build side by side in one process. Paths are relative to the stock
extraction and resolved only when a build runs.

## Out: what a build writes

```
<out>/<mod folder>/Config.ini, Gen/Version.ndf
<out>/<mod folder>/Scenarios/<scenario>_Definition.dat, _Details.dat, _Assets.dat   (and any extra packs)
<out>/MANIFEST.tsv        every packed entry and where it came from, then each dropped template file and why
<out>/dumps/<file>.txt    a typed dump of each generated file, for review (never shipped)
<out>/od_overlay.png      the examples' review picture: every item on the map's Preview (never shipped)
```

- **Definition:** the template's MapConfiguration, ScenarioInfo and ScenarioLoader re-keyed to the new scenario id
  and GUID, the content's GDScript (or, with `Content.script = None`, the template's own, re-keyed), and no Trophy.
- **Details:** the generated LevelDesign; the deployment and command zone files, generated when the content has zone
  items and the template's otherwise; and the map's own playable zone, AI grid, path cache and camera paths, byte for
  byte (`map_copies`). With `details_from_template` the template's Details ship whole instead.
- **Assets:** the string table as one dictionary per language (the Chinese column for SC, English for the other
  seven), and the template's files kept by `asset_rules` (its menu pictures; its voice, Python, video and portraits
  are dropped). `menu_art` swaps a menu picture for another stock Operation's, or for one generated at build time,
  at the same path.

## The profile

The examples' `profile.py` holds Survivors on Geisa (`modkit.ops.profile.SURVIVORS`, `modkit.ops.maps.GEISA`). For a
new op on Geisa, change the identity and leave the rest until you know why.

| Fields | What they are | For a new op |
| --- | --- | --- |
| `template` | the stock challenge cloned (`SURVIVORS`) | keep |
| `guid_namespace` | scenario and item GUIDs are uuid5 names under it | your own string |
| `map_strings`, `map_trans`, `map_details`, `map_copies`, `ground_z` | the map moved to, from a `StockMap` | from `GEISA` |
| `scalar_edits` | Definition scalars changed: the menu order (`OrderToChainMission`) and the duration | the menu order `derived_menu_order(SCENARIO, GUID_NAMESPACE)` ([[content-identity-unique]]); keep the rest. Left out, the build derives it |
| `deck_swap` | MapConfiguration's player deck | change with the player's `CAMP_ROWS` deck |
| `dictionaries`, `asset_rules` | the three dictionaries; what to do with each template asset | keep |
| `menu_art` | menu pictures from another stock Operation, or generated: `{picture name: stock scenario or a MenuPicture}`, shipped in place of the template's at the path MapConfiguration names | empty keeps the template's; Twin Strike takes RedJuggernaut's three emblems and makes its own map card (`modkit.ops.menuart.card_picture`) |
| `import_rule`, `shape_sources` | the canonical-layout rule; the stock files each generated file's shapes are held to | keep |
| `player_camp`, `enemy_camp` | the camps the tier gate reads | keep (the examples' NATO and PACT camps) |
| `end_exports` | the end funnel's export paths; `()` for none | your `FOLDER`'s funnel |
| `build_root`, `dumps`, `packs`, `details_from_template` | where a rebuild may delete; review dumps; pack list; Details whole | your `build/` |
| `mod_id` | `Config.ini`'s ID | 0 until the first Workshop upload (`warno-ship`) |
| `extra_*`, `reviewed_pending` | extension points, below | `extra_gates` |

**The player's deck** is a stock deck id, set twice: `deck_swap` (MapConfiguration's `LocalPlayerDeck`) and the
player's row of `CAMP_ROWS` (the SetDeck at load). Change both together. Cards added during the battle come from the
script ([[add-unit-to-deck]]).

**The camps** are Survivors' four (its CampList and SetDeck block stay four). The examples use three: the player, an
AI-controlled ally and the enemy ([[custom-operation-from-stock-parts]]).

## The content

| Field | What it is |
| --- | --- |
| `name` | the `--content` key |
| `items` | every LevelDesign item (`LdItem`), zones and arrivals included |
| `script` | the template's GDScript in, `(roots, exports)` out; `None` ships the template's own |
| `strings` | `{dictionary: {token: (English, Chinese)}}`, exactly the profile's dictionaries |
| `menu_tokens` | the SCENARIO_DEFINITION tokens held to the 30-unit title limit (a toolkit convention: stock's briefings run past 1,000 units), so the titles only |
| `scenario`, `mod_name`, `menu_renames` | the identity ([[content-identity-unique]]) |
| `extra_shapes` | shapes no stock file uses but this content uses on purpose, each a reviewed decision |
| `blocking_objectives` | objectives reviewed to hold up their Sequential until they resolve |
| `tiered_arrivals` | player arrivals that end in a command zone only, opened and closed by the script |
| `prod_menu_switch` | the buy menu's switch at the HUD restore |
| `deck_swap`, `scalar_edits` | the profile's, replaced for this content: another player deck, or its own derived menu order when one profile builds several Operations |

Two contents with the same scenario id or mod folder replace each other on install.

## The gates, in order

Each runs through `modkit.core.gates.run_gate` under its name, which is also its key in `reviewed_pending`.

| Gate | Name | Holds |
| --- | --- | --- |
| 1 | `strings` | every token in both columns, markup and placeholders matched, Chinese within stock's characters, titles short |
| 2 | `canonical`, `shapes`, `ndfrules` | each generated file in canonical layout, made only of shapes the stock files use, passing the game's load-time property rules ([[load-time-validation-rules]]) |
| 3 | `binding`, `tokens`, `references` | script tags bind 1:1 to LevelDesign items; every text token resolves in all eight languages, dialog buttons in the game's in-game dictionary; new-id references resolve |
| 3 | `arrivals`, `tiers` | player arrivals end in a player zone, or are tiered ([[arrival-end-in-zone]]) |
| 3 | `objective-pins`, `never-finishing`, `end-funnel`, `empty-group-guard` | objective labels on a place; nothing after a never-finishing action; every ending through the funnel; no defeat on an empty group before it held a unit |
| 3 | `zone-tags`, `dialog-text`, `rules`, `smart-orders`, `prod-menu-switch` | zone lookups in exactly one polygon, detectors on circles; no `%1` in dialogs; no CheckEndGame, GameTime or ModeFixedRandomSeed; no order after a smart order; the buy-menu switch as declared |
| 3 | `script-effects` | every effect the script launches is a stock GameFx effect that takes no parameters ([[script-effects-self-contained]]) |
| 3 | the profile's `extra_gates` | below |
| 4 | `dump-diff`, `dump-rows` | each re-keyed file differs from stock only by the re-keying rows, and every row changed something |
| 5 | `package` | every entry lies under the scenario; no Gameplay file ([[gameplay-mod-relaunch]]) |
| 6 | `read-back` | every written pack reads back to the planned bytes |

**Ready-made extra gates** (`modkit.ops.gates`), all five used by Open Door:
`ExtraGate("units", unit_gate)` (every unit named exists in the game's unit database),
`ExtraGate("no-template-name", template_name_gate("Survivors"))`, `ExtraGate("grid", grid_gate)` (the shipped AI
grid spans the shipped playable zone: [[ai-grid-tiles-playable-zone]]), `ExtraGate("zone-layout",
zone_layout_gate)` (zones and arrivals keep stock's layout rules) and `ExtraGate("menu-order", menu_order_gate)` (the
menu order is no stock Operation's: [[content-identity-unique]]). Use at least the first two and `menu-order`; add
`grid` and `zone-layout` once the op ships zones of its own.

## Extension points

All on `OpProfile`, all optional:

- `extra_packs` (another `<scenario>_<name>.dat`), `extra_items` (more files in the profile's own packs),
  `extra_loose_files` (files beside the packs in the mod folder);
- `extra_config_rows` (lines under `Config.ini`'s `[Config]`) and `extra_manifest_rows`;
- `extra_gates` (`ExtraGate(name, check)`, `check(items, content)` raising `CheckError` or returning a log line) and
  `extra_outputs` (review files such as the overlay);
- `reviewed_pending`: `{gate name: exact message}` for a failure under review. The build reports it as `REVIEW
  PENDING` and goes on, and logs an entry that no longer fires. List each one for whoever plays the build.

## Another stock map

Geisa is the only `StockMap` today, and every played op so far ran on Geisa or Kreide. Moving to another map is
untested beyond that: plan a probe (`warno-probe-and-playtest`) before a mission.

1. **Declare the map's stock files.** The extraction holds only what an installed component declares in
   `STOCK_PATHS` (`modkit.core.stock`): the map scenario's Definition and Details packs, and its Preview and Minimap.
   Ops declares Geisa's. For another map, make your op a component of its own (`warno-new-component`) that declares
   them, then re-run `setup extract` (`warno-setup`).
2. **Read its facts off the game's own scenario for it** into a `StockMap`: the datapack name, the
   EnvironmentSettings import, the Details folder, the files to copy (playable zone, AI grid, path cache, camera
   paths), the playable zone's Center z (`ground_z`), the Minimap's size, and the player-side arrivals.
   `python -m modkit.core.ndfbin dump` reads each of those files. A Minimap pixel is 2,560 world units (the map
   pictures section of `warno-setup`'s stock-corpus reference).
3. **Keep the map's own AI grid with its own playable zone.** A grid that does not tile the playable zone crashed the
   game on load ([[ai-grid-tiles-playable-zone]]); `grid_gate` checks it.
