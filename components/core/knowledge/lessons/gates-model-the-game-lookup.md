---
id: gates-model-the-game-lookup
title: A gate checks the data where the game reads it, not just that it exists somewhere
trials: [2026-11-03-probe1-launch1-damagetype, 2026-11-03-probe1-launch2-dialog-buttons]
---
DamageType 0 was a valid integer, and the button tokens were in a shipped dictionary. Both checks passed, and both
launches failed. Trace the consumer: the game's own validation or lookup, or stock usage per class and property.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-probe1-launch1-damagetype](../trials/2026-11-03-probe1-launch1-damagetype.md), [2026-11-03-probe1-launch2-dialog-buttons](../../../ops/knowledge/trials/2026-11-03-probe1-launch2-dialog-buttons.md)
- Skills: [`components/core/skills/warno-gates/SKILL.md`](../../skills/warno-gates/SKILL.md)
<!-- referenced-by:end -->
