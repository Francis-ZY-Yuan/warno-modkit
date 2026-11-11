---
id: 2026-11-03-probe1-launch1-damagetype
kind: launch
build: 46dccf8
game_version: 201602
mechanisms: [load-time-validation-rules, changestress-damagetype-zero]
outcome: fail
symptom: Fatal error at load, Property 'DamageType' must be defined (TGDDescriptorChangeStress)
cause: The script's ChangeStress set DamageType = 0 (Suppress), and load-time validation treats 0 as undefined
result: The stress became Stun (2); every generated file now passes modkit.core.ndfrules.check_file before a launch
---
The first launch of the first probe Operation (spike 1) on Geisa. The file did set the property; the value was the
problem. This launch is why the load-time rules were read out of the game and made a build gate
([[2026-11-03-ndfrules-stock-sweep]]).
