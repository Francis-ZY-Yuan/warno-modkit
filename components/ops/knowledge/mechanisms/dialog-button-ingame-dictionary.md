---
id: dialog-button-ingame-dictionary
title: Dialog button labels resolve only in the game's in-game interface dictionary
status: PLAYED
last_verified: 201602 2026-11-03
source: exe-analysis
topics: [objectives-and-text, loading-and-crashes]
gates: [modkit.ops.gates.check_tokens]
shapes: [modkit.ops.bricks.g_dialog]
trials: [2026-11-03-probe1-launch2-dialog-buttons, 2026-11-03-ingame-button-stock-sweep, 2026-11-03-probe1-play1-worked]
stock_precedent: 974/974 stock button-token uses resolve in INTERFACE_INGAME; no other script property is resolved there only
---
**What the game does.** When a dialog is built, its button labels (`TokenBoutonChoix0`, `TokenBoutonChoix1` and the
third button property) are looked up in one fixed list, the game's own `INTERFACE_INGAME` dictionary, never in the
scenario's dictionaries. A token missing there throws a dictionary error while the dialog is built; the crash the
player sees comes later, as the half-built dialog is torn down.

**The shape.** Use stock in-game tokens for the buttons (`SI_NEXT` for a single button; `CMP_EASY`/`CMP_HARD` for a
two-way choice) and let the dialog text, which does resolve in the scenario's dictionaries, say what each button
means. Check all 8 languages.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-ingame-button-stock-sweep](../trials/2026-11-03-ingame-button-stock-sweep.md), [2026-11-03-probe1-launch2-dialog-buttons](../trials/2026-11-03-probe1-launch2-dialog-buttons.md), [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md)
- Gates: [`modkit.ops.gates.check_tokens`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.bricks.g_dialog`](../../src/modkit/ops/bricks.py)
- Skills: [`components/core/skills/warno-gates/references/load-time-rules.md`](../../../core/skills/warno-gates/references/load-time-rules.md), [`components/core/skills/warno-launch-triage/references/crash-dumps.md`](../../../core/skills/warno-launch-triage/references/crash-dumps.md), [`components/core/skills/warno-localization/SKILL.md`](../../../core/skills/warno-localization/SKILL.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py), [`components/ops/examples/twin-strike/twinstrike/strings.py`](../../examples/twin-strike/twinstrike/strings.py)
- Records: [crash-dump-names-the-error](../../../core/knowledge/mechanisms/crash-dump-names-the-error.md), [localisation-tokens-packed](../../../core/knowledge/mechanisms/localisation-tokens-packed.md)
<!-- referenced-by:end -->
