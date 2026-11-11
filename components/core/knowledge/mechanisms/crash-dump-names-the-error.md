---
id: crash-dump-names-the-error
title: The crash report's dump names the real error
status: RE
last_verified: 201602 2026-11-03
source: play
topics: [loading-and-crashes]
gates: [modkit.core.crashdump.in_flight]
trials: [2026-11-03-probe1-launch2-dialog-buttons]
---
**What the game does.** When WARNO crashes it shows a "WARNO has stopped working" crash-report box and leaves a
minidump (`crashdump.dmp`) in a `CrashRpt_<guid>` folder under your temp folder. The box says nothing useful, and
neither does the game's log folder. The fault you see is often a second crash, while the interface tears down
after an error; the error that started it is usually a game exception still in flight when the dump was written.

**How to use it.** The core crash-dump reader (`modkit.core.crashdump`) lists the exceptions in flight and their
messages. After the first probe's second launch it printed a dictionary error naming the exact token and
dictionary list that failed ([[dialog-button-ingame-dictionary]]), while the box only said the game had stopped.

**Gotchas.** The report's own data file next to the dump is not readable; use the dump.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-03-probe1-launch2-dialog-buttons](../../../ops/knowledge/trials/2026-11-03-probe1-launch2-dialog-buttons.md)
- Gates: [`modkit.core.crashdump.in_flight`](../../src/modkit/core/crashdump.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../skills/warno-launch-triage/SKILL.md), [`components/core/skills/warno-launch-triage/references/crash-dumps.md`](../../skills/warno-launch-triage/references/crash-dumps.md)
- Records: [2026-11-03-probe1-launch2-dialog-buttons](../../../ops/knowledge/trials/2026-11-03-probe1-launch2-dialog-buttons.md), [crash-box-hides-the-error](../lessons/crash-box-hides-the-error.md)
<!-- referenced-by:end -->
