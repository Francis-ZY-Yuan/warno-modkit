---
name: warno-localization
description: Use when a WARNO mod's player-facing text needs another language (an Operation's strings, a Workshop page, unit or deck text), when translated text is written, revised or reviewed, when a term table for a language is started or extended, or when a gate fails on a translated string (placeholder, markup, glyph, title length).
---

# Localization

## Overview

WARNO has eight dictionary languages: DEV, FR, GER, POL, RU, SC (Simplified Chinese), SPA and US. A mod localizes by
filling a lookup table, each text in each language, and the game's own texts answer in the same shape. A translation
goes wrong in two ways no English play shows:

- **Mechanically:** a `%1`, a `#bold{`, a brace or a line break is lost, or a character the language's font lacks
  shows as an empty box. Gate 1 catches these, every failure at once.
- **In its terms:** a word differs from what the game itself shows, or a reader of that language's military writing
  would never write it. Only this procedure and a native reader catch these.

**Two sources, by kind of term:**
- **A label the game shows on its own screens** (a button, an end-screen grade, a difficulty, a map, a unit card)
  has one right text per language: the game's own. Look it up; never translate it.
- **Domain wording in your own prose** (orders, fires, attacks, nuclear use) takes the register of that language's
  military writing, from its attachment. This holds even where the game's own briefings word it otherwise: they are
  prose, not labels.

`python` is your venv's interpreter (`warno-setup`).

## The tables

- **An Operation's text** is its `strings.py` table (`warno-new-operation`), one entry per token:
  `"ts_name": {"US": "Operation Twin Strike", "SC": "双重突击行动"}`. US is required; a language left out gets the US
  text. `(English, Chinese)` is shorthand for US and SC.
- **The game's own text:** `python -m modkit.core.glossary token <TOKEN> ... [--dic STEM]` and
  `glossary term "<English>"` print the stock rows as a table, one column per language, each row naming its
  dictionary (`MAPS`, `UNITS`, `INTERFACE_OUTGAME`); `--lang SC,FR` picks the columns.
- **The mod's term table:** each term, its text per language and the source (`TERMS` in an Operation's `strings.py`).

**To add a language:** a column in the op's table (its code as the key) and an attachment `references/<tag>.md` with
zh-Hans.md's sections: where the game draws the text, the domain register (pattern, term table, sources), style,
common mistakes. The stock lookup and the gates already cover all eight languages.

| Language | Game code | Attachment |
| --- | --- | --- |
| Simplified Chinese | SC | [references/zh-Hans.md](references/zh-Hans.md) |

Other text (a Workshop page with `warno-ship`, unit or deck text) follows the same procedure; its gate, where one
exists, is that text's own, and the native reader of step 5 is the Workshop page's.

## Procedure

1. **List the terms before any text:** labels the text names (buttons, grades, difficulty, the map and its places,
   units, a unit's status), sides, formations and ranks, domain terms, and the mod's own coinages.
2. **Fix each term with its source:**
   - **A label, by token:** `glossary token`. A dialog's buttons are the game's tokens, so the text names each by its
     exact label ([[dialog-button-ingame-dictionary]]).
   - **A label, by English:** `glossary term` finds candidates; the label is the one on the screen your text refers
     to, confirmed by its token in that screen's dictionary. Row counts decide nothing: the end screen's defeat is
     INTERFACE_INGAME's `DEFEAT!`; the difficulty picker's Medium is `AB_GM_1` (`token AB_GM_0 AB_GM_1 AB_GM_2 --dic
     INTERFACE_OUTGAME`), though another setting's "Medium" has more rows; an end-screen grade is not a help text's.
   - **A domain term:** the attachment's register and table.
   - **None of these:** your own wording, marked as yours.

   Keep the result in the mod's term table and reuse it in every text.
3. **Translate:** the title as its English reads; the attachment's style; every `%N`, `#name{`, `}` and line break
   kept. Where stock gives a text a length range per language (an Operation's briefing, background and outcomes),
   stay inside the target language's range: cut, never pad.
4. **Build** (`warno-gates`): gate 1 lists every failing token and language at once. Reword a glyph failure with
   stock characters, and put the natural word on the review sheet as an open choice. Never widen a gate to pass.
5. **Native review before it ships:** one sheet for the modder or a native reader: the open choices, then the terms
   with their sources, then every text beside its English. Apply their edits and build again.
6. **Play once in that language** (`warno-probe-and-playtest`): the menu, a dialog, an objective and the end screen.
   Record it with `warno-record-finding`.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| A game label translated instead of looked up | `token` or `term`, verbatim |
| The label with the most matching rows, not the one on the screen | Its token in that screen's dictionary |
| A faithful briefing over stock's range for the language | Cut to the range |
| A place name coined where the map list has one | `term "<map name>"` first |
| Domain terms copied from the game's own briefings or a plain dictionary | The attachment's register and table |
| A natural word swapped to dodge a gate, silently | An open choice on the review sheet |
| One coinage worded two ways in two texts | One term table, reused |
| A token left without the language | It shows the English: fill every token |
| Shipped because the gates pass | Gates prove glyphs and markup, not language: step 5 |
