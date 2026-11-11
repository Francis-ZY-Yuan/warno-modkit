# Screenshots

These are in-game pictures of mods made with this toolkit. WARNO's art in them belongs to Eugen Systems; they are
here only to show what the toolkit makes. See [NOTICE](../../NOTICE).

The rule, enforced by the hygiene gate: each file is a JPEG, under 512 KiB, with no metadata (no Exif, XMP, IPTC or
comment segment), and is listed below with a one-line caption. Commit a picture and its line together.

To make one from a full-size capture, use ffmpeg. The bitexact flags stop ffmpeg writing its own comment segment:

```
ffmpeg -i capture.png -map_metadata -1 -flags +bitexact -fflags +bitexact -q:v 4 name.jpg
```

Raise `-q:v` (lower quality), or add `-vf scale=1600:-1`, if the file is over 512 KiB.

## Screenshots

