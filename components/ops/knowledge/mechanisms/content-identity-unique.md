---
id: content-identity-unique
title: Two mods cloned from one template must not share an identity
status: PLAYED
last_verified: 201602 2026-11-11
source: play
topics: [operation-setup, mod-packaging]
gates: [modkit.ops.gates.check_menu_order, modkit.ops.gates.menu_order_gate]
shapes: [modkit.ops.leveldesign.ld_guid, modkit.ops.leveldesign.scenario_guid, modkit.ops.leveldesign.derived_menu_order, modkit.ops.build.rekey_table]
trials: [2026-11-06-probe2-play-run-a, 2026-11-11-twin-strike-launch1-duplicate-menu-order]
---
**What to keep unique.** The scenario id and its GUID, every LevelDesign item GUID (generated under a namespace of
the mod's own), the menu tokens, the mod's name and folder, and the Operation's menu order number
(`OrderToChainMission`, its place in the Operations menu) among every Operation active at once: two active Operations
with one number stop the game at start ([[2026-11-11-twin-strike-launch1-duplicate-menu-order]]).

**The menu order is derived, as the GUIDs are hashed names.** A published Operation's order is
`derived_menu_order(scenario, namespace)`: a range far above stock's numbers plus its scenario GUID modulo the range's
span, so the one hashed identity drives both. A hand pick does not do: stock's Operations stop at 999, so hand picks
cluster just above it, and no build's gates can see the Workshop mods a player runs beside yours. A build whose scalar
edits set no order gets its derived one. The named exception is the examples' frozen group (Open Door's op and the
probes empty, spike, spike_safe and spike2): regression baselines that keep 1001 and never ship, so only one of them is
active at a time ([[derive-cross-mod-ids-from-a-hash]]).

**How we know.** The second probe was built from the same generator and template as the first, with its own
identity, installed beside it, and played. Twin Strike's first launch, beside a probe that held the same menu order
number and differed in everything else, stopped at start with a map pack configuration error naming the number.

**Gates.** The `menu-order` gate (`menu_order_gate`, run by every example's build) fails a build whose menu order
number a stock Operation holds, and names `derived_menu_order` as the fix. A build sees no other mod: the derived order
makes a clash with one unlikely, and the examples' test (`test_example_contents`) holds every published example to its
derived order and keeps them apart.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md), [2026-11-11-twin-strike-launch1-duplicate-menu-order](../trials/2026-11-11-twin-strike-launch1-duplicate-menu-order.md)
- Gates: [`modkit.ops.gates.check_menu_order`](../../src/modkit/ops/gates.py), [`modkit.ops.gates.menu_order_gate`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.leveldesign.ld_guid`](../../src/modkit/ops/leveldesign.py), [`modkit.ops.leveldesign.scenario_guid`](../../src/modkit/ops/leveldesign.py), [`modkit.ops.leveldesign.derived_menu_order`](../../src/modkit/ops/leveldesign.py), [`modkit.ops.build.rekey_table`](../../src/modkit/ops/build.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/SKILL.md`](../../skills/warno-new-operation/SKILL.md), [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/open-door/opendoor/profile.py`](../../examples/open-door/opendoor/profile.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/profile.py`](../../examples/probes/probes/profile.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py), [`components/ops/examples/twin-strike/twinstrike/profile.py`](../../examples/twin-strike/twinstrike/profile.py)
- Records: [2026-11-11-twin-strike-launch1-duplicate-menu-order](../trials/2026-11-11-twin-strike-launch1-duplicate-menu-order.md), [operation-menu-registration](operation-menu-registration.md), [soviet-player-camp](soviet-player-camp.md)
<!-- referenced-by:end -->
