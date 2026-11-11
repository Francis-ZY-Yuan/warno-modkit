---
name: warno-record-finding
description: Use when a WARNO launch, play, probe, stock survey or analysis has an outcome worth keeping, or when the knowledge check fails.
---

# Recording a finding

## Overview

Every trial is recorded once, where it belongs, and linked to the mechanisms it touched. Skills and code cite the
record by ID instead of restating it, so one record improves everything that cites it. The full schema is
`${CLAUDE_PLUGIN_ROOT}/knowledge/README.md` (this plugin's folder is two levels above this skill's base directory).

`python` is your venv's interpreter (see `warno-setup`).

## Where it goes

| You are working | Write into |
| --- | --- |
| From installed plugins, in your own project | `knowledge/` in your project folder (`mechanisms/`, `trials/`, `lessons/`, and `topics.md` if you declare topics of your own). Never into an installed plugin: updates replace it |
| In a clone of the repository | The component the behaviour belongs to. core: file formats, load-time rules, crash triage, packaging. ops: scripts, zones, decks, Operations |

A public component's record never links a record that is not public.

## Steps

1. **Write the trial**, `trials/<YYYY-MM-DD>-<slug>.md`. One attempt, one outcome:

   ```
   ---
   id: 2026-01-10-my-op-launch1
   kind: launch
   build: 1a2b3c4
   game_version: 201602
   mechanisms: [load-time-validation-rules]
   outcome: fail
   symptom: Fatal error at load, Property 'X' must be defined (TSomeClass)
   cause: what was wrong
   result: the gate added or the change made
   ---
   Two or three lines: what was tried and what was seen, with links to the evidence.
   ```

   `kind` is `launch`, `play`, `probe-run`, `re` or `survey`; `build` is your own build or commit id (it need not
   resolve in any repository); `outcome` is `pass`, `fail` or `mixed`. Comments go on lines of their own, starting
   with `#`.

   Copy the `symptom` from the game, word for word: `warno-launch-triage` matches on it. `render` puts it in the
   symptom index: the component's `INDEX.md` and the map's `knowledge/symptoms.md` in a clone, your project's
   `knowledge/symptoms.md` in a project.
2. **Update each mechanism it touched,** in `mechanisms/<id>.md`: add the trial to `trials`, and set `status`,
   `last_verified` (`<game build> <date>`), `stock_precedent` and `gates` as the trial showed. A new behaviour gets a
   new mechanism, and every mechanism needs `topics`: one to three topic IDs, for example
   `topics: [zones-and-map, units-and-orders]`. Use the topics the components already declare (the map's README lists
   them); a topic is declared in a `topics.md` (`## <topic-id>: <title>`, then one sentence of scope), and a new one
   is added only when the mechanism truly fits none. Add `game-updates` when the body ties the fact to a particular
   game build. Status follows the evidence:
   - `PLAYED` needs a passing play trial; a probe build that loaded is `PROBED`;
   - `STOCK` means stock does it in the same position but we haven't;
   - `FAILED` names the alternative in the body;
   - a record from your own exe analysis (`source: exe-analysis`) needs a probe or play that didn't fail, or a gate
     proven both ways, before it can be public.
3. **Add a lesson** if the trial taught a rule: one file, `lessons/<lesson-id>.md`, with front matter and the
   reasoning as its body:

   ```
   ---
   id: check-each-part
   title: Counting the parts of a recipe is not checking them
   trials: [2026-01-10-my-op-launch1]
   ---
   One or two lines on why, and what to do instead.
   ```
4. **Cite, don't restate.** Anywhere else (a skill, an example, another record), write the record's ID in double
   square brackets, as this toolkit's skills cite [[prove-each-gate-both-ways]].
5. **Check:**
   - project folder: `python -m modkit.core.knowledge check .` must say `ok`; `render .` then writes your project's
     map into its `knowledge/` folder, beside your records;
   - clone: `python -m modkit.core.knowledge render`, then `check .`, then `python -m modkit.core.repocheck .`. All
     must exit 0, and the generated pages (the `knowledge/` map, each `INDEX.md`, the "referenced by" footers) go
     into the same commit.

## Rules the check enforces

IDs are lower-case kebab-case and unique across every component and project; a trial's ID starts with a real date.
Every ID a record or citation names must exist. A gate or shape must be a dotted path, `modkit.<component>.<module>.<name>`,
that exists in the record's component or one of its dependencies. A mechanism's topics must be declared in a
`topics.md` of its component or one of its dependencies, and topic IDs are unique (a citation never names a topic).
An unknown front-matter field is an error, and so is an old one-file `lessons.md`.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Writing into the installed plugin's folder | Your project's `knowledge/`; the plugin is replaced on update |
| Paraphrasing the symptom | The game's own words |
| `PLAYED` from a build that only loaded | `PROBED` until someone plays it |
| Restating a finding in a skill or a docstring | Cite its ID |
| Hand-editing `INDEX.md` or a page of the `knowledge/` map | They are generated; re-render |
| A new topic for one mechanism | File it under an existing topic |
| Dropping the unread beats of a play | Record them as not read, so the next play asks again |
