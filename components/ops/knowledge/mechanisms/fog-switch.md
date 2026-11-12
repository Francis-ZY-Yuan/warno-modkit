---
id: fog-switch
title: A script can switch the fog of war off with TGDDescriptorFow; whether it is map-wide and comes back on is unseen
status: PLAYED
last_verified: 201602 2026-11-11
source: play
topics: [zones-and-map, script-flow]
shapes: [modkit.ops.bricks.g_fow, modkit.ops.shapes.FOW_SHAPES]
trials: [2026-11-11-fxprobe-play1]
stock_precedent: no stock script switches the fog (0 of the 31 stock GDScripts holds a TGDDescriptorFow)
---
**What the game does.** `TGDDescriptorFow`, the scenario API's fog switch, takes one bool, `Fow`: off with False, on
with True (the game rules' default, which every Operation starts with). The strike-effects probe switched it off
mid-battle, and 12 NATO vehicles that no unit of the player's could see showed on the map
([[2026-11-11-fxprobe-play1]], F3).

**Not seen in play:**
- whether the switch reaches the whole map (every enemy unit shown) or only some of it;
- whether `Fow` True brings the fog back (the probe's last step; not read).

**Use.** `bricks.g_fow(on)`. No stock file serialises the class, so a content that writes it admits
`shapes.FOW_SHAPES` (the class and its place in a Sequential). Twin Strike can lift the fog for its strike's window
(`STRIKE_FOG_LIFT`), off by default until the fog's return is seen.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md)
- Shapes: [`modkit.ops.bricks.g_fow`](../../src/modkit/ops/bricks.py), [`modkit.ops.shapes.FOW_SHAPES`](../../src/modkit/ops/shapes.py)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
- Records: [2026-11-11-fxprobe-play1](../trials/2026-11-11-fxprobe-play1.md)
<!-- referenced-by:end -->
