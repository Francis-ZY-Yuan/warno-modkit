---
id: localisation-tokens-packed
title: Localisation keys are tokens of up to 10 characters, packed 6 bits each
status: PLAYED
last_verified: 201602 2026-11-06
source: stock-data
topics: [files-and-formats]
shapes: [modkit.core.trad.token_key, modkit.core.trad.build_dic]
trials: [2026-11-02-gdscript-format-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: 658 of 658 script text keys in the 16 Operations resolve in the scenario's own dictionaries
---
**What the game does.** A text value in a script, and every key of a `.dic` dictionary, is a 64-bit number that
packs a token of up to 10 characters from the alphabet space, `0-9`, `A-Z`, `_`, `a-z` (6 bits each, first
character most significant). Script text resolves in the scenario's own
`Localisation/<scenario>/Scripting/{Dialog,Localization}-<LANG>.dic`, and voice lines are bound by the same token.

**Gotchas.**
- Some properties resolve in a fixed game dictionary instead of the scenario's own. Dialog button labels resolve
  only in the game's in-game interface dictionary ([[dialog-button-ingame-dictionary]]).
- Give a mod's tokens a prefix no stock token uses, so they never collide with stock ones.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-gdscript-format-survey](../../../ops/knowledge/trials/2026-11-02-gdscript-format-survey.md), [2026-11-06-probe2-play-run-a](../../../ops/knowledge/trials/2026-11-06-probe2-play-run-a.md)
- Shapes: [`modkit.core.trad.token_key`](../../src/modkit/core/trad.py), [`modkit.core.trad.build_dic`](../../src/modkit/core/trad.py)
- Skills: [`components/core/skills/warno-setup/references/stock-corpus.md`](../../skills/warno-setup/references/stock-corpus.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../../ops/skills/warno-new-operation/SKILL.md)
- Records: [ndfbin-round-trip](ndfbin-round-trip.md)
<!-- referenced-by:end -->
