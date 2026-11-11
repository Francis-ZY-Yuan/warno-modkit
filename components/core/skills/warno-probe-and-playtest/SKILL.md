---
name: warno-probe-and-playtest
description: Use when a WARNO mechanism is UNTESTED and needs a probe build, or when a WARNO build is ready for someone to play and report back.
---

# Probes and playtests

## Overview

A play is the most expensive test there is: minutes of a person's time per launch, and they play for fun, not to
read numbers. So the modder plays and Claude does not drive the game. Everything else is designed to make each
launch count: results that show on the map, beats that can't block each other, a play sheet that needs no
explaining, an install checked file by file, and a short interview afterwards.

## Designing a probe

A probe is a small mod whose only job is to answer questions, one per beat.

- **One question per beat, each beat in its own parallel branch.** One stalled beat must not hide the rest
  ([[one-stall-hides-the-rest]]).
- **Make the answer visible on the map:** a zone's colour, units vanishing, the route a column takes, a hint, the
  end screen. Players miss about a third of objective-panel readouts but remember what the map showed
  ([[debrief-by-what-the-map-shows]]).
- **Decisive unknowns first,** both in time and on the sheet.
- **For each beat, write the readings in advance:** what the player may see, and what each sight means.
- **Make test cards hard to miss:** a distinct unit, named in a hint. Plain-looking test cards go unbought.
- **Give the riskiest shape a fallback build:** the same probe minus every shape stock has never used
  (`warno-stock-precedent`), so one unknown can't waste the launch.
- **Sequence the hints;** overlapping hints hide each other.

The Operations component's probes are worked examples of all of this (`warno-new-operation`).

## Before handing a build over

1. Every gate passes (`warno-gates`), and every test.
2. **Install it hash-checked**, with WARNO closed. The share installer (`python -m modkit.core.install
   <built_mod_dir> --title "<menu title>"`, see `warno-ship`) copies the mod, checks the SHA-256 of every installed
   file against the build, and switches it on. Or copy the folder into
   `%USERPROFILE%\Saved Games\EugenSystems\WARNO\mod\` and compare hashes yourself.
3. **Write the play sheet** from [references/play-sheet-template.md](references/play-sheet-template.md): the build
   commit, what is installed, how to tell it failed, the runs, a timeline counted from "Launch battle", and each beat
   with its readings.

## Debrief

If the player fills in the sheet, read it beat by beat. If they say "ask me questions":

- Ask in rounds of up to four numbered multiple-choice questions, in plain chat, one beat per question. Wait for the
  answers; a question dialog that times out loses them.
- Put the decisive unknowns first, and ask about what was visible on the map, not about row numbers.
- Always offer "didn't watch" or "didn't notice". An honest blank is data; a guess is noise.

Then record one trial per outcome, and leave unread beats open for the next play (`warno-record-finding`). A
failure goes to `warno-launch-triage`.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Asking the player to read objective rows | Show the answer on the map |
| All beats in one Sequential | One stall swallows the rest; branch them |
| "Play it and tell me what happened" | Give readings per beat, and ask multiple-choice questions |
| Installing by hand without a hash check | A stale file wastes the launch; check every file |
| Driving the game yourself | Slower than the player, and it keeps them from playing |
