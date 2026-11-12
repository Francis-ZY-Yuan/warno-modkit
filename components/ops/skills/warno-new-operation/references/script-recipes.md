# Mission recipes, and how to search stock Operations

Each row names the block that builds a shape, the record that says how far it is proven, and where an example uses
it. Blocks live in `modkit.ops.bricks` (`g_*` actions and conditions, `c_*` unit constraints), `modkit.ops.shapes`
(mission blocks over a `Ctx`), `modkit.ops.mission` (composed pieces more than one op uses: the beat frame, lanes and
waves, the re-ask loop, the zone race, the end funnel, the difficulty branches) and `modkit.ops.script` (the
deployment phase and the HUD). Read the record's status before you rely on a row: `PLAYED` worked in a play,
anything else is short of that ([[no-stock-precedent-is-untested]]). Example paths are under
`${CLAUDE_PLUGIN_ROOT}/examples/`.

## The frame

- **Main.** SetDeck per camp, hide the HUD, LoadingDone, restore the HUD, then one Simultaneous of the load beats,
  the player group's refresh loop and the battle (wait for "Launch battle", then every timed beat).
  `mission.script_frame` builds it around your beats; `open-door/opendoor/op.py`'s `script` shows the call.
  `hold_script` (`probes/empty.py`) is the smallest working frame.
- **Beats.** `shapes.Beat(t, check, build)`: `t=None` runs at load, beside the deployment phase; a number runs that
  many seconds after the launch, as the last node of its own `Sequential[wait t, beat]`. One stalled beat then can't
  hold up another ([[one-stall-hides-the-rest]]). Open a timed beat with `shapes.beat_hint`.
- **Containers.** What finishes when, and what a Sequential, Simultaneous or Competition waits for:
  [[script-container-semantics]]. Know whether an action finishes before anything follows it
  ([[know-whether-an-action-finishes]]).
- **Variables.** `ctx.group(name)`, `ctx.int_var(name)`: made once per name and exported under the op's folder. Flags
  that several beats read are declared at load (`script_frame`'s `flags`).
- **The silent voice.** Every dialog token needs a cutscene entry; `script.silent_cutscenes(shapes.dialog_tokens(...))`
  gives each the stock silent clip.

## Recipes

| To | Use | Record | Example |
| --- | --- | --- | --- |
| Let the player deploy and buy | `script.deploy_phase`, `hud_restore(deploy=True)`, a player deployment zone, arrivals | [[deployment-phase-recipe]], [[arrival-end-in-zone]] | `open-door` `profile.deploy_phase`, `op.items` |
| Open and close arrival tiers with a zone | arrivals ending in a command zone only, `Content.tiered_arrivals`, `mission.zone_handover` | [[arrival-end-in-zone]] | `open-door` `op.pl_green` |
| Add or lock deck cards | `shapes.add_card`, `shapes.lock_card` (the lock goes last) | [[add-unit-to-deck]] | `open-door` `op.load_deck` |
| Reveal pre-placed hidden units | `mission.hidden_units` (Spawn items with `disable_auto_spawn`), then `g_spawn` | [[spawn-and-create-units]] | `probes/spike.py` `reserves` |
| Create units at a place | `shapes.create` (`mission.create_rows` for riflemen and their carriers), ending with `shapes.reveal` for enemy units | [[spawn-and-create-units]] | `open-door` `op.first_echelon` |
| March by road | `shapes.order(group, FAST_MOVE_AND_ATTACK, tag)`; by waypoints, each leg raced against a timeout, `mission.lane_route` | [[fast-move-and-attack-keeps-roads]] | `open-door` `op.lane_route` |
| Send waves down lanes | `mission.Lane`, `mission.Wave`, `mission.wave` (riflemen board with `mission.board` first) | [[spawn-and-create-units]], [[fast-move-and-attack-keeps-roads]] | `open-door` `op.main_body` |
| Take a town | `g_seize` (a command unit in the group); give it no order after | [[zone-capture-command-units]] | `probes/spike2.py` `capture` |
| Decide a zone by presence | `mission.zone_race`, then `mission.zone_handover` forces the owner | [[count-race-forced-owner]], [[decide-zones-by-count]] | `open-door` `op.pl_blue` |
| Count units in an area | a circular zone (`Minimap.ring_item`), `g_detect`; several circles into a variable, `mission.ring_round` | [[detector-circles-only]] | `open-door` `op.rear_exit`, `op.sack` |
| Count kills or losses | `g_kills` by unit type, `g_losses`; or count a group's survivors | [[kill-counts-by-type]] | `probes/spike2.py` `counters` |
| Remove units at once | `g_vanish` (`g_kill` with a death cause), after reading every count | [[vanished-removal]] | `open-door` `op.catch` |
| Show an objective | `shapes.objective`, last in its Sequential, pinned on a place | [[objective-waits-until-resolved]], [[objective-label-needs-position]] | `open-door` `op.p2` |
| Show live numbers | an objective's counters, or a hint; never dialog text | [[objective-counters]], [[dialog-text-takes-no-variables]] | `open-door` `op.p6` |
| Ask the player | `g_choice` with stock in-game button tokens | [[dialog-button-ingame-dictionary]] | `probes/spike.py` `start_dialog` |
| Ask until answered | `mission.reask_loop` (reset the choice, then ask, in a loop), raced against its exits | [[dialog-reask-loop]] | `open-door` `op.spring` |
| Branch on difficulty | `mission.difficulty`: three `g_difficulty` branches over a Medium baseline | [[difficulty-branches]] | `open-door` `op.difficulty` |
| Fire on a place | a hidden battery, revealed, `order(group, SHOOT_ON_POSITION, tag)` | [[scripted-fires]] | `probes/spike.py` `battery` |
| Hold a unit's fire | `TGDDescriptorSetAmmo` to empty its ammunition; "weapons jammed" doesn't | [[weapons-jammed-effect]], [[effect-name-is-not-behaviour]] | `probes/spike.py` `decoys` |
| End the battle | `shapes.set_end` into one funnel (`mission.end_funnel`), its export in `end_exports` | [[mission-ends-only-by-script]] | `open-door` `op.end_funnel` |
| Lose when the force is gone | a defeat armed only after the player's group held a unit | [[mission-ends-only-by-script]] | `open-door` `op.p2` |

**Not available:** scripted infantry boarding a helicopter ([[helicopter-boarding]]); suppression by script
(`ChangeStress` takes no DamageType 0: [[changestress-damagetype-zero]]). How large a script and a battle can grow is
untested beyond the probes ([[script-and-battle-scale]]).

## Searching stock Operations

Use this with `warno-stock-precedent` for anything the table doesn't cover.

| What | Where in the extraction | Read it with |
| --- | --- | --- |
| A stock Operation's script | `scenarios/challenge_*/NDF/Scenarios/challenge_*/GDScript.txn` | `python -m modkit.core.ndfbin dump FILE -o OUT` |
| Its map items | `scenarios/challenge_*/out/LevelDesign.ndfbin` | the same |
| Its zones | `scenarios/challenge_*/out/DeploymentZone.ndfbin`, `CommandZone.ndfbin` | the same |
| Its texts | `scenarios/challenge_*/Localisation/challenge_*/` (the Chinese `-SC.dic` files; every language for Survivors) | `python -m modkit.core.trad dump FILE` |
| The template's Definition and Details | `kreide_op/challenge_Survivors_Definition`, `kreide_op/challenge_Survivors_Details` | `ndfbin dump` |

- A dump numbers every object (`// #296`). The code cites stock shapes that way: `S#296` is object 296 of Survivors'
  GDScript dump; the other letters are named at the top of `modkit.ops.bricks`. The numbers are build 201602's: build
  210942 put two objects ahead of each script's root, so from there on a stock object sits two places later
  (`S#296` is `#298` in a 210942 dump; `modkit.ops.script`).
- Dump every stock challenge script once and search the text (`warno-stock-precedent`'s recipe). Read each hit in its
  container: what follows it, and in which Sequential, Simultaneous or Competition
  ([[precedent-includes-the-position]]).
- For property names in plain words, decompile the scenario Python (`warno-setup`'s scenario Python reference). For
  counts, use GDScript: it is what the game runs ([[gdscript-is-what-loads]]).
- The surveys behind the table: [[2026-11-02-gdscript-format-survey]], [[2026-11-02-leveldesign-api-survey]],
  [[2026-11-04-lifecycle-survey]], [[2026-11-04-zone-capture-survey]], [[2026-11-06-spawns-and-deck-survey]].
