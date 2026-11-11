---
name: warno-op-storyboard
description: Use when the modder asks for an Operation's design page, or "the artifact" for an op (its map, plot, order of battle, phases), or wants that page updated after a design change.
---

# Op storyboard

## Overview

An op's design is reviewed as one page. The page shows:

- the map: the game's own Minimap and satellite picture (the map's Preview), with Minimap and Satellite buttons;
- over the map, the stock layout's command and deployment zones, drawn exact, and the design's marks;
- a phase stepper that shows each phase's marks;
- below the map, the objectives, the order of battle and what is proven.

`modkit.ops.storyboard` makes the page and its two pictures from one JSON spec. The Artifact tool publishes them as a
private page. `python` is your venv's interpreter (`warno-setup`).

## The spec

Each op keeps its spec at `examples/<op>/docs/storyboard.json` (`components/ops/examples/<op>/docs/` in a clone),
beside its `design.md`. Write it from the design:

- **`map`:** the stock map (`name`, the map datapack) and the layout the op plays on (`layout`, a Details folder below
  the extraction, which `STOCK_PATHS` declares). Also: the crop (`playable` by default), each alliance's deployment
  style and label, and names for the stock command zones.
- **An op on a cut of a stock layout:** set `crop` to the cut's box in minimap px, and draw the op's own zones
  instead of the layout's: `map.command_zones` lists exactly the command zones to draw (each `{stock, name?}` for a
  stock zone, or `{name, area, points}` for the op's own), and a deployment's `area` is its own polygon. Use these
  instead of `zone_names`, which `command_zones` replaces.
- **`phases`:** the design's mission flow, one entry per phase: id, name, time, a one-line summary and the details.
- **`marks`:** what each phase shows, each listing its `phases` (none means every phase). The kinds are `arrow`,
  `ring`, `units`, `label`, `arc` and `burst`; give each a hover `title`.
- **`sections`:**
  - the objectives and the end, as tables;
  - the order of battle (`oob`), one card per side, each unit as `[count, name, key]`;
  - the proof table, with `mark` cells: `ok` played, `half` stock or built, `open` not yet tested (the records'
    status, `warno-stock-precedent`).

The schema is the module's docstring (`python -m pydoc modkit.ops.storyboard`). A bad key or value fails with its JSON
path. `${CLAUDE_PLUGIN_ROOT}/tests/storyboard_sample.json` uses every mark kind. Twin Strike's spec
(`examples/twin-strike/docs/storyboard.json`) is the worked example.

## Steps

1. **Edit the spec** from the design. Run step 2 with no marks first: the page shows where the zones lie, and marks
   are placed against them.
2. **Run the module:** `python -m modkit.ops.storyboard <spec> --check-units`. `--check-units` holds every order of
   battle unit key to the game's unit database; keys joined by `·` are each checked. It prints a line per file, then
   the publish line. A `FAILED:` line names the JSON path to fix, or names `warno-setup` for a missing stock file.
   The output goes to `storyboard/<op>` in the build folder.
3. **Publish** with the Artifact tool, using the values the publish line prints: `file_path` set to `index.html`, and
   `files` set to `{"minimap.png": ..., "satellite.png": ...}`. On the first publish, add an `icon` (`map`) and a
   one-line `description`. If the tool refuses the build folder because it is outside the session's folders, copy
   the three files into the session's scratchpad and publish them from there.
4. **On later updates**, edit the spec, run the module again, read the published page (Artifact `read`, with its
   `url`), then republish to the same URL by passing `url`.

## Rules

- **The page embeds the game's own pictures.** It stays a private Artifact. Its output is never committed: it lands
  in the build folder. The spec holds no game data: only coordinates, short identifiers and the design's own text.
- **Marks are minimap px of the full map**, the same frame as the op's named points (one px is
  `modkit.ops.maps.WORLD_PER_MINIMAP_PX` world units). The viewBox is the crop, so changing the crop moves no mark.
- **Prose** may use `{style:text}` for a style's colour and `**bold**`. Map labels and hover titles are plain text.
- **Check the page once after publishing,** if a browser can view it: both pictures load, the stepper steps, and the
  page stacks at phone width.

## Open Door

Open Door's published page predates the generator and was written by hand. Converting it to a spec is optional.
