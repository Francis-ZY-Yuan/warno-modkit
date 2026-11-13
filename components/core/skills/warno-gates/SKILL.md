---
name: warno-gates
description: Use before a WARNO build is installed or handed to a player, when a gate fails, or when adding or changing a build check.
---

# Gates

## Overview

A gate is a build check that fails before the game would. A failed launch costs the player minutes; a gate costs
seconds. A gate is only worth its name when it **checks the data where the game reads it**
([[gates-model-the-game-lookup]]) and is **proven both ways**: it fails the bad build with the game's own words,
and it passes every stock file ([[prove-each-gate-both-ways]]).

`python` is your venv's interpreter (see `warno-setup`).

## Running the gates

- **Every build runs its gates on its own output, before anything is installed.** A build that exits 0 passed
  every gate of every component it uses. Never install a build that failed one. Each component's build skill names
  its command (Operations: `warno-new-operation`).
- `REVIEW PENDING: <gate>: <message> (the rest of this gate did not run)` is a known failure under review, matched
  word for word. It is not a pass: that gate stopped at the reviewed failure and checked nothing after it. List it
  for whoever plays the build.
- **Check the gates themselves** after setup and after every game update:
  - `python -m modkit.core.ndfrules verify` must end with `0 violations`;
  - each installed component's tests: `python -m unittest discover -s <component>/tests -t <component>/tests`, where
    `<component>` is `${CLAUDE_PLUGIN_ROOT}` (this plugin's folder, two levels above this skill's base directory), an
    `installPath` from `claude plugin list --json`, or `components/<name>` in a clone. The stock sweeps skip when no
    extraction is configured, and a skipped sweep proves nothing: read the skip lines.

## Adding a gate

1. **Find where the game reads the value.** Its load-time rule (`python -m modkit.core.ndfrules show <class>`), the
   dictionary it resolves a token in, the container a node runs in. "The value is a valid integer" and "the token is
   in some dictionary" both passed builds that then failed at launch.
2. **Write it as a function that raises `modkit.core.gates.CheckError`** (use `check(cond, msg)`), in the gates
   module of the component the behaviour belongs to. Say what the game will do, in its own words when it has some.
3. **Prove it fails the bad build.** Rebuild the build that failed (its commit, or a test fixture of it) and see the
   gate fail with that message.
4. **Prove it passes all stock.** Run it over every stock file of that kind in the extraction, and keep that as a
   test (decorate it with `modkit.core.paths.skip_unless_extracted()` so a fresh clone skips instead of erroring).
   Pin any hand-made table to stock the same way, so a game update that changes stock fails a test.
5. **Fail what it cannot evaluate** until someone reviews it, with the reason in a reviewed list in the code
   ([[unevaluable-check-fails-until-reviewed]]).
6. **Make every part of a recorded recipe a check.** A recipe written in research and only partly ported loses a
   part ([[recorded-recipe-becomes-a-gate]]).
7. **Wire it into the build, and record it:** name the gate in the mechanism's `gates:` field, and add the trials
   that prove it both ways (`warno-record-finding`).

## A known failure you can't fix yet

Add `{gate name: (exact message,)}` to the mod's own pending map, a plain dict (a gate that runs once per file may
hold several messages), and run the gate through `modkit.core.gates.run_gate`. An Operation's map is
`OpProfile.reviewed_pending`, and its build already runs every gate that way. Never loosen the gate itself.

An entry covers the first failure its gate call raised, word for word, and nothing after it: most gates stop at their
first violation, so while the entry fires **the rest of that gate does not run**, and a later fault it would have
caught (a second bad token, another file) goes unchecked. Keep an entry only as long as it takes to fix, and re-run
the build without it before a release.

## Red flags

- "The check is too strict; relax it so this build passes."
- "It passes, so it works" (has it ever failed the bad build?).
- "Skip that class, nothing in stock uses it."
- "It can't tell, so let it through."

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Checking that a value exists or is well-formed | Check it where the game consumes it |
| Flagging every property stock leaves out | Stock leaves required properties out and still loads; only an explicit zero is sure to fail ([[explicit-zero-is-the-sure-failure]]) |
| Counting a recipe's parts | Check each part ([[counting-parts-is-not-checking]]) |
| A gate with no stock sweep | It will fail good mods after an update, or pass bad ones |

## References

- [references/load-time-rules.md](references/load-time-rules.md): what the game validates at load, how the rules
  table is made, and what the `ndfrules` gate covers and misses ([[load-time-validation-rules]]).
- `${CLAUDE_PLUGIN_ROOT}/knowledge/lessons/`: the general rules, one file each, with the trials that taught them
  (listed in `${CLAUDE_PLUGIN_ROOT}/knowledge/INDEX.md`).
