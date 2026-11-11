---
id: seteffect-never-finishes
title: A set-effect action never finishes by itself
status: RE
last_verified: 201602 2026-02-01
source: exe-analysis
topics: [script-flow, loading-and-crashes]
gates: [modkit.ops.fakegates.gate_finishes]
shapes: [modkit.core.fakegates.NameShape]
trials: [2026-02-01-probe-seteffect]
stock_precedent: 12/12 uses sit under a parent that moves on
---
The action stays active until something else ends it. See also [[crash-names-the-error]].
