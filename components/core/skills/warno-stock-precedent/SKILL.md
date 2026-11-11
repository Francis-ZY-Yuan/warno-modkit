---
name: warno-stock-precedent
description: Use before a WARNO mod relies on a script action, effect, property value or file shape you have not seen work in game.
---

# Stock precedent first

## Overview

The game's API accepts far more than the game supports. What the stock files do, in the same place, is the only
cheap evidence that something works. **No stock precedent means UNTESTED, whatever the API allows**
([[no-stock-precedent-is-untested]]). A precedent is the same action, on the same kind of unit, in the same
position: what follows it and which container holds it ([[precedent-includes-the-position]]).

`python` is your venv's interpreter (see `warno-setup`).

## Steps

1. **Check the knowledge first.** Look the behaviour up under its topic: in a clone, `knowledge/README.md` leads to
   one page per topic; otherwise the installed components' `knowledge/INDEX.md` (mechanisms by topic) and your own
   project's `knowledge/`. The status decides what comes next:
   - `PLAYED`: worked in a real play. Copy the shape the record names.
   - `STOCK`, `PROBED`, `RE`: evidence short of play. Use it, and add it to the next play sheet.
   - `FAILED`: don't retry it. The record names the alternative (for example [[helicopter-boarding]]).
   - `UNTESTED`, or no record: go on to step 2.
2. **Search stock for the same thing in the same place.** Dump every stock file of that kind from your extraction
   and search the dumps (recipe below). Match all of:
   - the same action or property, with the same **value form** (stock leaves defaults out; an explicit value it
     never writes is a risk: [[stock-value-forms-only]], [[explicit-zero-is-the-sure-failure]]);
   - the same **kind of target** (a helicopter is not a ground vehicle);
   - the same **position**: what comes after the node, and inside which container.
3. **Read the stock definition of anything you use by name.** An effect's name is not its behaviour
   ([[effect-name-is-not-behaviour]]).
4. **Count it, and write the count down** as `matching / total`, for example "37/37 stock SetEffects sit last in
   their container". Put it in the mechanism's `stock_precedent` field (`warno-record-finding`) and in the docstring
   of the code that relies on it.
5. **No precedent: mark it UNTESTED and plan a probe** (`warno-probe-and-playtest`) **and a fallback** that uses
   only stock-proven parts, so one unknown can't cost the whole launch.

## Search recipe

```python
# Dump every stock GDScript of the extraction, then search the text dumps.
from pathlib import Path
from modkit.core import ndfbin, paths

out = Path("build/stock-dumps"); out.mkdir(parents=True, exist_ok=True)
for f in sorted(paths.extracted_root().rglob("*.ndfbin")):
    if "GDScript" in f.parts:
        ndfbin.main(["dump", str(f), "-o", str(out / f"{f.stem}.txt")])
```

Search the dumps with your usual tools, and read each hit in its container before you count it. For names rather
than numbers, decompile the scenario Python (`warno-setup`, scenario Python reference). Component-specific recipes
(which files hold which kind of data, and how to read them) live in that component's skill references: for
Operations, `warno-new-operation`.

## Red flags

Stop and search stock when you catch yourself thinking:

- "The class has the property, so it works."
- "Stock uses this action" (did you check what follows it, and where it sits?).
- "Close enough: stock does it to tanks, I'm doing it to helicopters."
- "It's only a value change." (A value stock never writes is a new shape.)
- "We'll see in the play." (A play costs the player minutes; a search costs seconds.)

## Common mistakes

| Mistake | What it cost | Fix |
| --- | --- | --- |
| Citing a stock use that sat last in its container | One action froze every later beat of a play ([[seteffect-never-finishes]]) | Record the position with the count |
| Trusting the API over stock | Scripted helicopter boarding failed twice | No precedent: probe it and keep a fallback |
| Trusting an effect's name | "Weapons jammed" units still fired ([[weapons-jammed-effect]]) | Read the definition |
| Counting a recipe's parts instead of checking each one | Bought land units never arrived ([[counting-parts-is-not-checking]]) | Check every part against stock |
