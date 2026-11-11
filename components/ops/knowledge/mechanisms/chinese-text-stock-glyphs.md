---
id: chinese-text-stock-glyphs
title: Simplified Chinese text must stay within the characters stock text already uses
status: PROBED
last_verified: 201602 2026-11-03
source: stock-data
topics: [objectives-and-text]
gates: [modkit.ops.gates.check_strings, modkit.ops.strings.check_glyphs]
shapes: [modkit.ops.strings.stock_sc_chars]
trials: [2026-11-03-sc-glyph-survey]
---
**What the game does.** The Simplified Chinese interface draws its text from a fixed font. A character that no stock
text uses may be missing from it.

**How we know.** A sweep of the stock Simplified Chinese dictionaries collects every character they use, and a
mod's text is checked against that set before the build. The first probe's text needed seven characters stock
never uses (眩, 晕, 倍, 徽, 履, 诱, 饵), so it was reworded; "stunned" became 击昏 instead of 眩晕.

**Status.** The checked text shipped in the first probe, but no play has looked at it in Chinese yet.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-sc-glyph-survey](../trials/2026-11-03-sc-glyph-survey.md)
- Gates: [`modkit.ops.gates.check_strings`](../../src/modkit/ops/gates.py), [`modkit.ops.strings.check_glyphs`](../../src/modkit/ops/strings.py)
- Shapes: [`modkit.ops.strings.stock_sc_chars`](../../src/modkit/ops/strings.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md)
<!-- referenced-by:end -->
