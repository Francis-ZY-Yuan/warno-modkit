---
id: zone-capture-command-units
title: Only command units capture a zone, and an enemy command unit inside makes it neutral at once
status: PLAYED
last_verified: 201602 2026-11-06
source: exe-analysis
topics: [zones-and-map]
trials: [2026-11-04-zone-capture-survey, 2026-11-06-probe2-play-run-a]
stock_precedent: every stock "AI controls zone" test belongs to a camp that also runs the skirmish AI (62 nodes in 11 Operations)
---
**What the game does.** In the Command phase, each tick, a command zone's owner is updated from the units inside it.
Only units with a commander module capture (every unit with `TCommanderModuleDescriptor`, scripted spawns included).
- No command unit inside: the owner is kept, after the capturer leaves too.
- A command unit of another side inside: the zone turns neutral at once (contested).
- Otherwise the zone goes to the side of the command unit inside.
- A capturer killed mid-capture leaves the zone neutral, and it stays neutral.

The update ignores the skirmish AI and the combat rule. `SetCommandZoneOwnerAndForceConvergence` sets an owner and
fills the zone so it holds ([[count-race-forced-owner]]).

**How we know.** The second probe: a scripted enemy command tank captured a zone, a player command tank won it
back, and a capturer killed mid-capture left its zone neutral for good.

**Gotchas.**
- How long a capture takes is unknown.
- A camp with no skirmish AI never brings command units on its own; a capture test for it needs scripted command
  units or a forced owner. A dead or contested command unit never captures, so do not hang a mission on it.
- No stock script orders a unit again after a `LaunchSmartOrder` Seize; remove or replace the unit instead.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-04-zone-capture-survey](../trials/2026-11-04-zone-capture-survey.md), [2026-11-06-probe2-play-run-a](../trials/2026-11-06-probe2-play-run-a.md)
- Skills: [`components/ops/skills/warno-new-operation/references/script-recipes.md`](../../skills/warno-new-operation/references/script-recipes.md)
- Examples: [`components/ops/examples/open-door/README.md`](../../examples/open-door/README.md), [`components/ops/examples/open-door/docs/design.md`](../../examples/open-door/docs/design.md), [`components/ops/examples/open-door/opendoor/op.py`](../../examples/open-door/opendoor/op.py), [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/forces.py`](../../examples/twin-strike/twinstrike/forces.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py)
<!-- referenced-by:end -->
