# Reading a WARNO crash dump

The record is [[crash-dump-names-the-error]].

## Where the dump is

When WARNO shows "WARNO has stopped working", its crash reporter writes a folder named `CrashRpt_<id>` under your
temp folder (`%TEMP%`). Take the newest one. It holds `crashdump.dmp`, a minidump. The reporter's other data file
is not readable, and the game's own log folder holds nothing useful about the crash.

Close the box without sending the report; the folder stays.

## Why the box is not the cause

The fault the box reports is often a second crash: the game hit an error, started tearing down the interface to
report it, and crashed while doing so. The error that started it is a game exception still in flight when the dump
was written, and its message is the game's own error text (a load error, a missing dictionary entry, and so on).

## Reading it

```
python -m modkit.core.crashdump <path to crashdump.dmp>
```

It finds the exceptions still in flight in the dump and prints each one's type and message, and nothing else from
the dump. It reads your own WARNO.exe, read-only, when it needs the type's name, and writes nothing. If the dump was
copied from another machine, pass `--exe <WARNO.exe>` for the same game build that crashed.

Example of what it gave once: after the first probe's second launch the box only said the game had stopped; the
dump named a dictionary error, with the exact button token and the in-game dictionary list it was looked up in
([[dialog-button-ingame-dictionary]]). The fix was a gate on that lookup, not a guess.

## When it prints nothing useful

- **No exception in flight:** the crash is the first fault, not a reported error. Look at what the build changed
  since the last build that loaded, one change at a time.
- **A message you don't recognise:** search the symptom index in each component's `knowledge/INDEX.md` (a clone's
  `knowledge/symptoms.md` holds them all) and the `symptom:` lines of your own trials, then the stock files for the
  names it mentions (`warno-stock-precedent`).

Keep the dump out of any repository: it holds data from your machine as well as the game's.
