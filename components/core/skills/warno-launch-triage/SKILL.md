---
name: warno-launch-triage
description: 'Use when a WARNO mod fails at load or in play, such as a fatal error at load, "WARNO has stopped working", a Relaunch Game prompt, mods switched off, an outdated mod, or a beat that never happened.'
---

# Launch triage

## Overview

Go from the game's own words to the cause, and end with a gate, so the same failure never reaches a player again.
Never guess from a crash box: it usually hides the real error ([[crash-box-hides-the-error]]).

`python` is your venv's interpreter (see `warno-setup`).

## Start at the symptom index

Each component's `knowledge/INDEX.md` has a symptom index of its own trials: the game's own words, the mechanism
behind them, and the gate that now catches them. Read it in every installed plugin's folder (`installPath` from
`claude plugin list --json`); a clone's `knowledge/symptoms.md` gathers them all. Your own trials are in your
project's `knowledge/symptoms.md` once you have run `python -m modkit.core.knowledge render .` there; otherwise search
their `symptom:` lines (`grep -r "symptom:" knowledge/trials` in your project). If the symptom is there, read the
mechanism, then ask why its gate didn't stop this build (was it run? was the rules table extracted from this exe?).

## By symptom

| The player saw | Do this |
| --- | --- |
| A fatal error at load: `Invalid property in object ... Property '<p>' must be defined` (or another `Property ...` rule) | A load-time rule ([[load-time-validation-rules]]). `python -m modkit.core.ndfrules show <class>` lists that class's rules. An explicit 0 counts as undefined ([[explicit-zero-is-the-sure-failure]]). The `ndfrules` gate should have caught it |
| "WARNO has stopped working" | Read the crash dump before anything else: `python -m modkit.core.crashdump <dump>` prints the game's own error ([[crash-dump-names-the-error]]). Method: [references/crash-dumps.md](references/crash-dumps.md) |
| "Relaunch Game" on starting an Operation, or every mod switched off after a launch | Operations and Gameplay mods don't mix ([[gameplay-mod-relaunch]]). Turn off every Gameplay mod in the Mod Center, and check the build ships none of `modkit.core.packaging.GAMEPLAY_FILES` |
| The mod is listed as outdated, or can't be switched on | [[mod-version-and-config-lines]]: `Gen/Version.ndf` and the `[Config]` lines |
| The Operation is missing from the menu, or shows the stock title | [[operation-menu-registration]]: a new scenario id, never a stock name |
| A fatal error at start: `Map pack configuration error : Duplicate OrderToChainMission <n> in map pack '{...}'` | Two active Operations hold the same menu order ([[content-identity-unique]]). Find the active mods whose MapConfiguration holds `<n>` and give each Operation its own `OrderToChainMission`. The ops `menu-order` gate catches a stock Operation's menu order; another mod's, the co-install check: `python -m modkit.ops.coinstall` names both mods and the value ([[check-against-every-active-mod]]) |
| It loads, but a beat never happened, or everything after a point stalled | Not a crash: a script that never moved on. Find the first beat that didn't happen and what sits before it ([[seteffect-never-finishes]], [[script-container-semantics]]). Then check the component's gates for that shape |
| A dialog the script should show never appears (a choice that gates the next beat) | Something the dialog waits on was left set. A re-ask loop raced against its answer can stop between its two writes and leave its "asking" flag at 1 ([[dialog-reask-loop]]): reset the flag right after the race, and bound any wait on such flags with a WaitDuration |
| Scripted guns drive toward the front and die instead of firing in place | Pre-placed guns in view, their ammunition emptied by script, broke every working precedent at once ([[scripted-fires]]). Create the battery for each fire out of the player's sight, keep it off its camp's AI, fire on a Name tag and remove it after; the ops `fire-range` gate holds where it stands |
| AI units drive their route, then stand idle at the last waypoint (or a garrison never moves to defend) | A camp with no AI does nothing after its last order. End each route with an Attack on the player's units ([[wave-ends-with-attack]]), and give a garrison its idle and shot ROE and a Hold ([[garrison-roe-and-hold]]) |

Ask the player for: the exact text of any error box (copied, not paraphrased), the `CrashRpt_...` folder path (close
the crash box without sending), the time from "Launch battle", and what was on screen.

## Then the fix loop

1. **Find the root cause** from the error text or the dump. Test the theory against every observation, the build
   that worked included, and check every input the code reads, not only the one you changed
   ([[test-the-theory-against-every-observation]]).
2. **Turn it into a gate** that fails this build with the game's words and passes all stock (`warno-gates`).
3. **Fix, rebuild,** and see every gate pass.
4. **Check the build beside every active mod** before handing it over: `python -m modkit.ops.coinstall --build
   <built mod folder>` reads the mods the player has active (local and Workshop), read only, and must end `ok`
   ([[check-against-every-active-mod]]).
5. **Reinstall hash-checked,** and update the play sheet so the player can just start the game
   (`warno-probe-and-playtest`).
6. **Record the trial** with the symptom in the game's own words (`warno-record-finding`). That row feeds the
   symptom index.

See [[fix-loop-after-a-failed-launch]].

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Guessing from the crash box | Read the dump; the visible crash is often a second fault |
| Fixing two suspects in one build | One cause per fix, or the next launch proves nothing |
| Explaining away an observation that doesn't fit | It is usually the one that points at the cause |
| Handing over a fix with no gate | The next generator brings the failure back |
| Paraphrasing the symptom in the record | Copy the game's words; the index matches on them |
