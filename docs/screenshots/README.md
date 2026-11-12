# Screenshots

These are pictures of mods made with this toolkit: in-game pictures, and the example Operations' authoring pages
(design schematics drawn over the game's own map pictures). WARNO's art in them belongs to Eugen Systems; they are
here only to show what the toolkit makes. See [NOTICE](../../NOTICE).

The rule, enforced by the hygiene gate: each file is a JPEG, under 512 KiB, with no metadata (no Exif, XMP, IPTC or
comment segment), and is listed below with a one-line caption. Commit a picture and its line together.

To make one from a full-size capture, use ffmpeg. The bitexact flags stop ffmpeg writing its own comment segment:

```
ffmpeg -i capture.png -map_metadata -1 -flags +bitexact -fflags +bitexact -q:v 4 name.jpg
```

Raise `-q:v` (lower quality), or add `-vf scale=1600:-1`, if the file is over 512 KiB.

## Screenshots

Map imagery in the four authoring-page pictures: from WARNO, (c) Eugen Systems, shown for non-commercial
illustration; not affiliated with or endorsed by Eugen Systems.

- `open-door-map.jpg`: Operation Open Door's authoring page, its map: the plan in APP-6 symbols over Geisa's minimap. A schematic, not gameplay.
- `open-door-authoring-page.jpg`: the whole of Operation Open Door's authoring page (`components/ops/examples/open-door/docs/authoring-page.html`), scaled down.
- `twin-strike-map.jpg`: Operation Twin Strike's authoring page, its map: the plan in APP-6 symbols over the game's satellite picture of the cut. A schematic, not gameplay.
- `twin-strike-authoring-page.jpg`: the whole of Operation Twin Strike's authoring page (`components/ops/examples/twin-strike/docs/authoring-page.html`), scaled down.
