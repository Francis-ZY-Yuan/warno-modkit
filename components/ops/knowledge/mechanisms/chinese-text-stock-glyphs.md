---
id: chinese-text-stock-glyphs
title: Simplified Chinese text must stay within the characters stock text already uses
status: PROBED
last_verified: 210942 2026-11-12
source: stock-data
topics: [objectives-and-text]
gates: [modkit.ops.gates.check_strings, modkit.ops.strings.check_glyphs]
shapes: [modkit.ops.strings.stock_chars, modkit.core.glossary.stock_dictionaries]
trials: [2026-11-03-sc-glyph-survey, 2026-11-12-sc-glyph-every-dictionary]
---
**What the game does.** The Simplified Chinese interface draws its text from a fixed font. A character that no stock
text uses may be missing from it.

**How we know.** A sweep of the stock Simplified Chinese dictionaries collects every character they use, and a
mod's text is checked against that set before the build. The first probe's text needed seven characters the stock
scenarios' dictionaries never use (眩, 晕, 倍, 徽, 履, 诱, 饵), so it was reworded; "stunned" became 击昏 instead of 眩晕.

**The set.** From 210942 the sweep takes every stock dictionary the game ships, not only the scenarios': its own
menus, options, maps, units and unit names too (the extraction's `localisation` folder), 2,185 characters instead of
1,700. Only the game's own dictionaries use 核 (nuclear), so a mod's text may now use it. Five of the seven above are
in the wider set; 诱 and 饵 are still outside it, and a character no stock text uses, such as 龘, still fails.

**Other languages.** The gate holds every language a mod writes to its own stock dictionaries the same way (US: 187
characters in 45 dictionaries; the other six: 185 to 248 in 38 each). For the Latin and Cyrillic fonts this is a
precaution, not an observed gap.

**Status.** The checked text shipped in the first probe, but no play has looked at it in Chinese yet, nor at any
character only the game's own dictionaries use.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-sc-glyph-survey](../trials/2026-11-03-sc-glyph-survey.md), [2026-11-12-sc-glyph-every-dictionary](../trials/2026-11-12-sc-glyph-every-dictionary.md)
- Gates: [`modkit.ops.gates.check_strings`](../../src/modkit/ops/gates.py), [`modkit.ops.strings.check_glyphs`](../../src/modkit/ops/strings.py)
- Shapes: [`modkit.ops.strings.stock_chars`](../../src/modkit/ops/strings.py), [`modkit.core.glossary.stock_dictionaries`](../../../core/src/modkit/core/glossary.py)
- Skills: [`components/core/skills/warno-localization/references/zh-Hans.md`](../../../core/skills/warno-localization/references/zh-Hans.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
- Records: [2026-11-13-twin-strike-210942-play2](../trials/2026-11-13-twin-strike-210942-play2.md)
<!-- referenced-by:end -->
