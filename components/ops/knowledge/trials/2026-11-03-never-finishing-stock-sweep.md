---
id: 2026-11-03-never-finishing-stock-sweep
kind: survey
build: 4b99a5a
game_version: 201602
mechanisms: [seteffect-never-finishes]
outcome: pass
result: A gate fails any node after a never-finishing action in a Sequential, such an action in a loop beside other nodes, and ModifyUnit in a Sequential
---
Proven both ways: the old probe fails it 42 times, the fixed probe and all 31 stock GDScripts (267 never-finishing
actions) pass. Two exemptions match stock: TriggerEndGame, and a loop whose only child is the action (the
tutorials' label loops).
