---
id: 2026-11-03-ndfrules-stock-sweep
kind: re
build: 927813a
game_version: 201602
mechanisms: [load-time-validation-rules, changestress-damagetype-zero]
outcome: pass
result: The load-time rules became a build gate, proven both ways
---
Read every class's load-time checks (3,870 rules on 1,565 classes) and applied them to stock: all 888 stock files of
the current build pass, and the unfixed probe fails with the game's exact message in about a second. Two calls came
out of it: a left-out "required" property fails only if no stock object of the class leaves it out, and checks the
gate cannot evaluate fail until reviewed.
