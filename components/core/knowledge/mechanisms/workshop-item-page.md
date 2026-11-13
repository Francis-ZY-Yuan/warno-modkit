---
id: workshop-item-page
title: The upload sets a Workshop item's main image and resets its title; the item's own pages set its text and gallery
status: PROBED
last_verified: 210942 2026-11-12
source: play
topics: [mod-packaging]
trials: [2026-11-12-twin-strike-workshop-page]
---
**What Steam does.** A Workshop item's page has four parts, and two routes set them:
- **Main image** (the thumbnail in the Workshop lists): only the upload sets it, from `PreviewImagePath` in the
  installed `Config.ini`, an absolute path to an image outside the mod folder (forward slashes work). Each upload
  with the line set replaces it, and Steam serves the file byte for byte.
- **Title:** every upload sets it back to `Config.ini`'s `Name`, even an upload that changed nothing but the image.
  Set it again on the item's "Edit title & description" page after each upload.
- **Description:** "Edit title & description" (one text per language; English is the default). An upload leaves it.
- **Gallery:** "Add/edit images & videos", which adds images beside the main one and cannot replace it. An upload
  leaves the gallery.
- **Change notes:** every upload adds one, and WARNO's upload always writes `Game Version = <build>` and
  `Mod Version = <Config.ini's Version>`; no `Config.ini` line or upload flag sets
  other text. The item's public Change Notes page (`steamcommunity.com/sharedfiles/filedetails/changelog/<id>`)
  shows each note as `<p id="<update>">`, the update's Unix time. Other games' Workshop guides say the owner edits a
  note on that page; not yet tried here.

**Gotchas.**
- Saving a description with links to other sites put the item on hold for Steam's automated content check, hidden
  from other players until it passed. Within 15 minutes it was public again.
- `time_updated` moves only when the uploaded files change: an upload that changed only the image left it.
- Steam's public `ISteamRemoteStorage/GetPublishedFileDetails/v1/` reads the title, description, main image,
  visibility and counts with no key; the gallery, votes and comments need a Web API key. The toolkit's
  `modkit.core.workshop check` compares a live item with the page files kept in a repository.

**Open:** whether an upload with an empty `PreviewImagePath` keeps the main image or clears it. A toolkit build
writes the line empty, so a reinstall empties it in the installed `Config.ini`; set it again before uploading.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-twin-strike-workshop-page](../trials/2026-11-12-twin-strike-workshop-page.md)
- Skills: [`components/core/skills/warno-ship/SKILL.md`](../../skills/warno-ship/SKILL.md), [`components/core/skills/warno-ship/references/workshop-page.md`](../../skills/warno-ship/references/workshop-page.md), [`components/core/skills/warno-ship/references/workshop-publishing.md`](../../skills/warno-ship/references/workshop-publishing.md)
- Records: [workshop-upload-folder](workshop-upload-folder.md)
<!-- referenced-by:end -->
