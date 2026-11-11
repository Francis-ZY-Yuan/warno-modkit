# Play sheet template

Copy this into your project (not into the plugin), fill in every `<...>`, and delete what doesn't apply. Write for
someone who wants to play, not to study: short lines, places named the way the map shows them, and every reading
decided in advance.

---

# <Mod title>: <what this play answers>

Build: commit `<sha>`, installed at `mod\<ModName>` on <date>, all <n> files hash-checked against the build.
Times count from "Launch battle". Distances are rough unless measured.

## If it won't load

It has failed if:
- "<menu title>" is missing from the <Operations> menu;
- the game stops with a "Fatal error" box (copy its text into the report);
- "WARNO has stopped working" appears (close it without sending, and put the `CrashRpt_...` folder path into the
  report);
- or it loads but <the first thing that should happen> doesn't.

A "Relaunch Game" prompt means a Gameplay mod is still on. Don't accept it: turn every Gameplay mod off in the Mod
Center and start again.

<Fallback build, if any: what to install instead, and when.> Report the failure and stop.

## Install

1. **Copy:** <already done, or the one installer to run>. WARNO must be closed.
2. **Activate:** open the Mod Center, switch on <ModName>, accept the restart if asked. <Other mods: on or off.>
3. **Check:** <the menu shows exactly this entry, with this title>.

To remove it: switch it off in the Mod Center, or delete `mod\<ModName>` with WARNO closed.

## Runs

| Run | Difficulty | Choice at 0:00 | Play to | Answers |
| --- | --- | --- | --- | --- |
| A | <Medium> | <button> | <time or end screen> | <which beats> |

Between runs: quit to the menu and start again.

## Where to deploy

<Where the player's units go, what to keep out of, and any one thing to do at a given time. Name places as the map
labels them.>

## Timeline

| Time | What happens | Hint starts with |
| --- | --- | --- |
| deployment | <...> | <...> |
| 0:00 | <...> | <...> |

## The beats

### <Beat name> (<time>) ☐ pass ☐ fail

- **Watch:** <what to look at, on the map first>.
- **Do:** <only if the player must act>.
- **Readings:**
  - <What they may see>: <what it means>.
  - <The other outcome>: <what it means>.
  - Nothing happened: <what it means, and whether to carry on>.

<One section per beat, decisive unknowns first.>

## Report

Answer what you saw; "didn't watch" is a fine answer. Or just say "ask me questions".

- Did it load? Any prompt or error (exact text)?
- One line per beat: pass, fail, or didn't watch, and anything odd.
