---
id: dialog-text-takes-no-variables
title: Dialog text cannot show live numbers; counts go in an objective counter or a hint
status: STOCK
last_verified: 201602 2026-11-04
source: stock-data
topics: [objectives-and-text]
gates: [modkit.ops.gates.check_dialog_text]
trials: [2026-11-04-lifecycle-survey]
---
**What the game does.** A dialog's text component has only a component name and a localized text; it takes no
variable list. A `%1` in a dialog token is printed as it is. Objective text and `LDHint` do take a variable list
([[objective-counters]]).

**So.** Keep dialog text fixed, and put a live count in the objective's counter or in a hint panel.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-lifecycle-survey](../trials/2026-11-04-lifecycle-survey.md)
- Gates: [`modkit.ops.gates.check_dialog_text`](../../src/modkit/ops/gates.py)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md)
<!-- referenced-by:end -->
