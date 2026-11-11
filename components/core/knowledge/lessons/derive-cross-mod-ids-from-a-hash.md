---
id: derive-cross-mod-ids-from-a-hash
title: A value that must be unique across every mod a player runs comes from a hash, never a hand pick
trials: [2026-11-11-twin-strike-launch1-duplicate-menu-order]
---
A value that must not repeat across every mod a player may run, Workshop mods you never see included, comes from a
hash of your own namespace and name, never from a hand pick. Hand picks cluster: stock's last Operation menu order is
999, so 1000 is everyone's first pick, and two of the toolkit's own Operations already met on 1001. A hash makes a
clash unlikely; the co-install check across the mods a player has active (`python -m modkit.ops.coinstall`) catches
the rest before a launch ([[check-against-every-active-mod]]). The checks today: that co-install check, the ops
examples' test (`test_example_contents`), which holds every published example to its derived menu order, and the ops
`menu-order` gate, which fails a stock Operation's.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-twin-strike-launch1-duplicate-menu-order](../../../ops/knowledge/trials/2026-11-11-twin-strike-launch1-duplicate-menu-order.md)
- Skills: [`components/ops/skills/warno-new-operation/SKILL.md`](../../../ops/skills/warno-new-operation/SKILL.md)
- Records: [check-against-every-active-mod](check-against-every-active-mod.md), [content-identity-unique](../../../ops/knowledge/mechanisms/content-identity-unique.md)
<!-- referenced-by:end -->
