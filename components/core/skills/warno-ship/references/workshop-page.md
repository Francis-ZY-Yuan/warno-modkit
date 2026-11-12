# The Workshop item page

The page (title, description, main image, gallery) lives in your repository as files, and Steam gets it from them.
Twin Strike's is the worked example: `components/ops/examples/twin-strike/workshop/`. What Steam does with each part
is [[workshop-item-page]].

## Keep the page as files

A `workshop/` folder beside the mod's sources, with the images wherever your project keeps pictures:

```
workshop/
  item.toml           the item: ID, mod name, title, and where the files below are
  description.bbcode  the description, in Steam's BBCode
the main image        square, about 1 MB or less
the gallery images    in page order
```

In this repository the images are in `docs/screenshots/`, the one folder where the hygiene gate admits pictures, each
listed in its README.

`item.toml`:

| Field | Holds |
| --- | --- |
| `id` | the item's ID, the same as the build's (a profile's `WORKSHOP_ID`); 0 is not allowed, so write the file after the first upload |
| `mod_name` | `Config.ini`'s `Name`, the folder name. Every upload resets the title to it |
| `title` | the page title, 128 characters at most |
| `description`, `preview`, `gallery` | paths relative to `item.toml`, or from the repository root when they start with `/` |
| `vars` | the placeholders the description uses, written `{{name}}` |

Anything personal in the description, such as your GitHub user name in a link, is a placeholder: its value goes in
your git-ignored `modkit.local.toml`, under `[workshop.vars]` (`repo = "github.com/<you>/<repo>"`).
`python -m modkit.core.workshop render workshop/item.toml` prints the description filled in, ready to paste.

## What sets each part

| Part | Set by | When |
| --- | --- | --- |
| Main image | the upload, from `PreviewImagePath` in the installed `Config.ini` | at every upload with the line set |
| Title | the item's "Edit title & description" page | after every upload, which resets it to `mod_name` |
| Description | the same page (English is the default language) | when it changes; uploads leave it |
| Gallery | the item's "Add/edit images & videos" page | once; uploads leave it |

The modder runs every upload. Claude can fill the two web pages in the modder's own browser, where they are signed in
to Steam, when asked; the modder can also paste the files' text themselves.

## After the first upload

1. **Record the ID** in the build (the profile's `WORKSHOP_ID`) and in `item.toml`, and commit both.
2. **Main image:** copy `preview.jpg` to a folder outside the mod folder whose path holds no user name (the path is
   published inside `Config.ini`). Set `PreviewImagePath = <that path>` in the installed `Config.ini`, with forward
   slashes, and upload again.
3. **Title and description:** on "Edit title & description", the title from `item.toml` and the `render` output.
4. **Gallery:** on "Add/edit images & videos", each image in order.
5. **Check:** `python -m modkit.core.workshop check workshop/item.toml` compares the live title, description and
   main image with the files and says what to fix. The gallery needs a Steam Web API key to read, so check it by eye.

## Every later upload

- **Before:** a reinstall writes `PreviewImagePath` empty. Set it again: whether an upload with an empty path keeps
  the main image is not known.
- **After:** set the title again, then run the check.
- **Changing the page:** change the files first, then the page, then run the check, and commit the files.

## Writing it

- **Say:** unofficial, not affiliated with or endorsed by Eugen Systems; contains modified Eugen game data;
  single-player; the game build it was made for; may break after game updates. No donation links.
- **Claims such as "the first":** make only one you have checked against the Workshop, keep "to our knowledge" in
  the description, and use the short form in the title and the image.
- **Links to other sites** put the item on hold for Steam's content check for a few minutes after each save.
- **Screenshots:** from your own play, with no profile names or local paths visible, and no metadata in the files.

## Tracking your items

`python -m modkit.core.workshop status <id> [<id> ...]` prints each item's title, visibility, dates, size,
subscriptions and views from Steam's public API, with no key.
