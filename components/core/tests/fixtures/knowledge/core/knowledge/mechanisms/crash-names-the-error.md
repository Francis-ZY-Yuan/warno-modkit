---
id: crash-names-the-error
title: The crash report names the real error
status: PLAYED
last_verified: 201602 2026-01-10
source: play
topics: [loading-and-crashes]
gates: [modkit.core.fakegates.check_names]
shapes:
  - modkit.core.fakegates.NameShape
trials: [2026-01-10-crash-report-play]
stock_precedent: 3/3 reports name the error
---
The game writes the message of the in-flight exception into its crash report.

It matters because the message tells you which rule your data broke.
