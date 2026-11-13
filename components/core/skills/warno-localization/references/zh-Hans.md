# Simplified Chinese (zh-Hans, game code SC)

The attachment for Simplified Chinese: what limits the text, the register its military wording takes, and the term
table. Extend the table as mods need more terms, each with its source and confidence.

## Where the game draws it

- The game draws all its Chinese text in one font. A character no stock text uses may be missing from it and show
  as an empty box ([[chinese-text-stock-glyphs]]). Gate 1 admits every character of every stock SC dictionary:
  menus, maps, units and scenarios. Reword what is outside (诱饵 "decoy" has neither character), and put the natural
  word on the review sheet.
- An Operation's table holds the text under `SC`; a token without it shows the English.

## The register: PRC military writing

Chinese military writing about the Soviet Army, and PLA terminology generally, maps each Russian root to one term.
Press style, and the game's own Chinese briefings, use other words, and those read wrong to a reader of military
texts.

| Russian | Doctrinal | Not |
| --- | --- | --- |
| удар (blow, strike) | 突击 | 打击 |
| атака (assault) | 冲击 | 进攻 (the whole offensive) |
| бой (battle, tactical) | 战斗 | 作战 |
| операция (operational) | 战役 | 行动 (but an operation's name is X行动) |
| командир (commander) | 指挥员 | 指挥官 |

The NATO side keeps the same register (反冲击 for a NATO battalion's counter-attack), with NATO's own unit words
(特遣队, 装甲掷弹兵).

## Style

- Full-width ：，？。 punctuation; `%1`, `#bold{…}` and line breaks exactly as in English.
- 您 in hints addressed to the player; 指挥员同志 as the address in an order or a dialog from a Soviet superior.
- An order heading: 战斗命令第N号, under the date line (1989年7月4日 04:30 UTC).
- Formations: honorific, then arm, then number: 近卫坦克第79师.
- Zone code names stay in Latin (占领ALPHA区).
- Vehicles and weapons: the game's own Chinese name where `term` finds one (Leopard is 豹: 豹2A4), without
  quotation marks. Otherwise the Latin designation with a class word (T-80BV坦克, 2S7M自行火炮). A Western
  nickname beside a designation (Abrams, Bradley) can go when the designation says it all.
- The title as its English reads: "Operation X" is X行动; stock titles without "Operation" carry no 行动.
- English capitals for emphasis (the VILLAGE) have no Chinese form; keep `#bold{}` where the English has it.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| 作战命令, 指挥官同志, 核打击, copied from the game's own briefings | 战斗命令, 指挥员同志, 核突击 |
| 前进支队 or 先遣队 for the Soviet forward detachment | 先遣支队 (前卫 is the march vanguard) |
| 反击 or 反突击 for a battalion's counter-attack | 反冲击; 反突击 is army level and up |
| 机械化步兵 for Soviet motor rifles in BMPs | 摩托化步兵, 摩步 |
| 原子打击 put in for 核打击 because a draft failed the glyph gate | 核 is in stock text, so look first and reword only what no stock text has |
| 第79近卫坦克师, the game's own briefing order | 近卫坦克第79师 |

## Terms

Confidence: high = a PLA reference work or a military dictionary gives the term in this sense; med = dictionary or
secondary usage; low = no term of art found, descriptive wording.

| English | Russian | Chinese | Conf. | Note |
| --- | --- | --- | --- | --- |
| forward detachment | передовой отряд | 先遣支队 | high | 前卫 is the march vanguard, another thing |
| vanguard (on the march) | авангард | 前卫 | high | |
| Guards Tank Division, 79th | гвардейская танковая дивизия | 近卫坦克第79师 | high | 近卫 → arm → 第N, as in 近卫坦克第1集团军 |
| motor rifles | мотострелки | 摩托化步兵, 摩步 (摩步营) | high | never 机械化步兵 for Soviet troops |
| Front (army group) | фронт | 方面军 | high | never 前线 in this sense |
| combat order (written) | боевой приказ | 战斗命令; heading 战斗命令第N号 | high | 作战命令 is the PLA umbrella term |
| "Comrade commander" | товарищ командир | 指挥员同志; 首长同志 | high | or by rank: 上校同志 |
| artillery preparation of the attack | артподготовка атаки | 冲击炮火准备; 炮火准备 | high | 火力准备 covers every arm's fire |
| fire strike (all batteries, once) | огневой налёт | 火力急袭 | med–high | 集火射击 for concentrated fire |
| fire mission | огневая задача | 射击任务 | med | 火力任务 also seen |
| division artillery group | ДАГ | 师炮兵群; prose 师炮兵 | high | |
| salvo | залп | 齐射 | high | |
| doctrine (military) | доктрина; устав | 条令 | high | 当时的苏军条令 |
| decline to use a nuclear weapon (the player's choice) | — | 不使用核武器 | low | descriptive; 未获批准 is a refusal from above, another thing |
| battery; rocket battery | батарея; реактивная батарея | 炮兵连; 火箭炮连 | high | |
| reserve | резерв | 预备队; 师预备队 | high | not a second echelon |
| first / second echelon | эшелон | 第一梯队 / 第二梯队 | high | |
| commit to battle | ввод в бой | 投入战斗 | high | |
| exploit a success | развитие успеха | 发展胜利; 扩张战果 | med | |
| counter-attack (battalion, brigade) | контратака | 反冲击 | high | repel one: 打退反冲击 |
| counter-blow (army and up) | контрудар | 反突击 | high | |
| assembly area | район сосредоточения | 集结地域 | med–high | 集中地域 also seen |
| (forces) assemble | сосредоточиваться | 集结 | high | |
| nuclear strike | ядерный удар | 核突击; 战术核突击 | high | 核打击 is press style |
| authorise nuclear use | разрешение на применение ядерного оружия | 批准使用核武器 | low | descriptive; no term of art found |
| lose combat effectiveness ("breaks") | потерять боеспособность | 丧失战斗力 | med | 溃退 for the rout itself, in narrative |
| seize / hold | захватить / удерживать | 夺取 / 扼守, 坚守 | med | |
| road junction | узел дорог | 道路枢纽 | med | |
| reconnaissance; security screen | разведка; охранение | 侦察; 警戒 | med | |
| task force (US) | — | 特遣队; 营特遣队 | med | |
| engineers; scouts | сапёры; разведчики | 工兵; 侦察兵 | high | |

## Sources

- 《中国大百科全书·军事》, 中国大百科全书出版社, 2007 (entries 反突击, 作战命令, 预备队, 方面军, 集结地域).
- 《中国军事百科全书·战术学分册》, 军事科学出版社, 1992 (炮火准备).
- 熊武一、周家法主编《军事大辞海》, 长城出版社, 2000 (急袭射击).
- БКРС Russian–Chinese dictionary, military senses (bkrs.info): контрудар, контратака, боевой приказ, ядерный удар,
  огневой налёт, ДАГ, район сосредоточения, передовой отряд.
- Not read in full, the place to confirm a term: 《苏联军事百科全书》 (战士出版社, 1986), 列兹尼琴科《战术》
  (解放军出版社, 1986), 《中国人民解放军军语》 (2011).
