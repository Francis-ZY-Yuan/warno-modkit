---
id: 2026-11-12-config-hash-stock-survey
kind: survey
build: port-210942-scen
game_version: 210942
mechanisms: [txn-tag-config-hash]
outcome: pass
result: The ConfigHash computed from each transaction equals every stock tag whose transaction the data names (331 of a 210942 extraction's 336, all 167 of the scenario packs'); gate 5's config-hash passes all 35 stock Definition folders and fails the first 210942 Twin Strike build on its four tags
---
Every `.txn.tag` of a 210942 extraction read against the transaction the stock data names for it
([[txn-tag-config-hash]]): the 231 named by a TNDFTransaction's BaseName and the 100 made by a folder scan of
scenarios, maps, decor sets, dictionaries and resource packs, `modkit.core.txntag`'s test. The five tags left are the
game's own bootstrap transactions, which no stock data names. The ops test sweep runs the gate over every stock
Definition folder; a Survivors clone keeping Survivors' tags fails it, as Twin Strike's build did
([[2026-11-12-twin-strike-launch-config-hash]]).
