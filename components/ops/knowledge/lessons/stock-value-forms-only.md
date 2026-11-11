---
id: stock-value-forms-only
title: Use only value forms stock serialises; a form stock never writes is a crash risk
trials: [2026-11-03-probe1-launch1-damagetype]
---
Pin every variable form to stock with a test, and replace any operator or comparison stock never uses with one it
does (for example `MoreOrEqual` with the operands swapped instead of `LessOrEqual` against a variable).

Gate 2 (`modkit.ops.gates.check_shapes`) admits only the class, property and value-type shapes the stock scripts
serialise. It does not read operator or modification values, so each op pins those itself, as the Open Door
example's `Phase34.test_modifications_are_stock_forms` does.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-probe1-launch1-damagetype](../../../core/knowledge/trials/2026-11-03-probe1-launch1-damagetype.md)
- Skills: [`components/core/skills/warno-stock-precedent/SKILL.md`](../../../core/skills/warno-stock-precedent/SKILL.md)
<!-- referenced-by:end -->
