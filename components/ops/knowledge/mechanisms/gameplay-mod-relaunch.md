---
id: gameplay-mod-relaunch
title: Operations and Gameplay mods don't mix; an Operation mod must ship none of the 16 Gameplay files
status: PLAYED
last_verified: 201602 2026-11-06
source: stock-data
topics: [mod-packaging, operation-setup]
gates: [modkit.ops.gates.check_package]
trials: [2026-11-02-kreide-op-relaunch-loop, 2026-11-03-probe1-play1-worked, 2026-11-06-probe2-play-run-a]
stock_precedent: 16 files tag a mod Gameplay, from the stock ModManager data
---
**What the player sees.** With any Gameplay mod active, starting an Operation (stock or modded) shows "Relaunch
Game". On Continue the game restarts with every mod switched off. Re-activating the mod brings the prompt back. It
applies to every Operation and every Gameplay mod, Workshop ones included.

**What makes a mod Gameplay.** Shipping, under the mod's `Gen` folder, any file whose path ends with one of the 16
entries of the Gameplay tag in the game's own mod-manager data: `GFX/` Constantes, Deck, Depiction, Division,
EffectCapacity, Pawn, Resources, Skirmish, TeamAlliance, Terrains, Unit, UnitConstantes, VisionRules, Weapon and
WorldInterface (each `.ndfbin`), plus `InitialisationGameDistanceUnits.ndfbin`. The list is
`modkit.core.packaging.GAMEPLAY_FILES`. A Gameplay tag also forces `DeckFormatVersion` to at least 1.

**So.** An Operation mod ships scenario packs only and uses stock units. No custom unit, weapon, depiction or deck
can come with it. A mod made only of `Config.ini`, `Gen/Version.ndf` and `Scenarios/` starts its Operation with no
prompt.

**Gotchas.** Neither giving the mod its own ID nor removing other mods changes anything.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-02-kreide-op-relaunch-loop](../trials/2026-11-02-kreide-op-relaunch-loop.md), [2026-11-03-probe1-play1-worked](../trials/2026-11-03-probe1-play1-worked.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Gates: [`modkit.ops.gates.check_package`](../../src/modkit/ops/gates.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/core/skills/warno-ship/SKILL.md`](../../../core/skills/warno-ship/SKILL.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/docs/play-sheet.md`](../../examples/open-door/docs/play-sheet.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md)
<!-- referenced-by:end -->
