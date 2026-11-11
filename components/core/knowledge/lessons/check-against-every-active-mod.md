---
id: check-against-every-active-mod
title: A build's gates see that build alone; check what must stay unique across every mod active beside it
trials: [2026-11-11-twin-strike-launch1-duplicate-menu-order]
---
Two Operations that each passed every gate stopped the game at start together: both held one menu order. Before a mod
goes active beside others, check what each must keep unique (the scenario id, its GUIDs, the menu order, the text
tokens) across all of them, not only against stock. The ops co-install check does it, read only: `python -m
modkit.ops.coinstall` reads every active mod (local folders and Workshop items, as the mods folder's `Config.ini`
lists them) and the stock Operations, fails a shared menu order, MapConfiguration GUID, scenario id or mod folder, and
warns on shared text tokens; `--build DIR` adds a build as if it were installed, and `--all` checks every installed
mod. A build's own gates stay partial: the `menu-order` gate holds it to stock's menu orders, and the examples' test
(`test_example_contents`) keeps the examples apart. For what no check can see, a mod you will never run beside
yours, derive the value from a hash ([[derive-cross-mod-ids-from-a-hash]]).

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-twin-strike-launch1-duplicate-menu-order](../../../ops/knowledge/trials/2026-11-11-twin-strike-launch1-duplicate-menu-order.md)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../skills/warno-launch-triage/SKILL.md)
- Records: [derive-cross-mod-ids-from-a-hash](derive-cross-mod-ids-from-a-hash.md)
<!-- referenced-by:end -->
