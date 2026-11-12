---
id: 2026-11-12-twin-strike-workshop-page
kind: launch
build: 2a9a0b6
game_version: 210942
mechanisms: [workshop-item-page, workshop-upload-folder]
outcome: pass
result: Twin Strike's Workshop page (title, description, main image, gallery) is kept in its example's workshop/ folder, and modkit.core.workshop check compares the live item with it
---
Twin Strike's item page, written after its first upload ([[2026-11-12-twin-strike-workshop-upload]]), with two
more uploads of the same installed build to the same ID:
- first re-upload, with `PreviewImagePath` set: the same item updated (40 bytes larger, the new line), and its main
  image appeared;
- the title and description were then set on "Edit title & description", and 5 gallery images added on "Add/edit
  images & videos", which offers no way to set the main image. The links in the description held the item for
  Steam's content check for a few minutes;
- second re-upload, with a new image at the same path: the main image was replaced (the served file is
  byte-identical to it), the title went back to `TwinStrike`, the `Name`, and the description and gallery stayed.
  `time_updated` did not move.
