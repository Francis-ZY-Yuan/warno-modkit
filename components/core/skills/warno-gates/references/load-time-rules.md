# Load-time rules: what WARNO validates when it loads a file

The record is [[load-time-validation-rules]]. This page says how the rules are found, how the gate applies them,
and where it stops.

## What the game does

When a pack loads, every object is checked by its class's validation, which first runs its parent class's. The
first broken rule is a fatal error at load that names the file, the class and the property:

```
Can't load '<file>': Invalid property in object '<anonymous> (<class>)': Property 'DamageType' must be defined
```

The rules come in a few kinds, each with its own message:

| kind | the game's message | the gate evaluates it |
| --- | --- | --- |
| defined | `Property '%1' must be defined` | yes |
| ge, gt (le, lt, eq exist but no rule uses them) | `Property '%1' must be greater or egal than '%2' ...` | yes, against a constant |
| range, lt_prop, le_prop | `Property '%1' must be in range ...`, `... less than property '%2' ...` | no rule uses them |
| cond | `Failed condition for property '%1': '%2'` | only once reviewed |
| custom | any other text | only once reviewed |

**"Must be defined" means "is not zero."** The check tests the stored value against zero: a null reference, an
empty list or string, a 0 integer or enum, a 0.0 float. So an explicit `0` fails even though the file sets the
property. The first probe Operation stopped at load on exactly this: a script action set `DamageType = 0`, a valid
value of its enum, and the game called it undefined ([[changestress-damagetype-zero]]).

## Making the table: `python -m modkit.core.ndfrules extract`

The extraction reads your own WARNO.exe, read-only, and finds every class's checks by their message text, so it
re-finds them after a game update. It writes the table (`ndfrules.tsv`) into your data folder, never into a
repository, and records the exe's size. With a previous table present it lists the rules that changed: review them
before trusting the gate.

It then counts stock: for each `defined` rule, how many stock objects of the class there are, and how many leave
the property out.

On build 201602 it found 3,870 rules on 1,565 classes. `show <class>` prints one class's rows.

## Testing the table against stock: `python -m modkit.core.ndfrules verify`

Verify applies the evaluated rules to every stock file of the current build in your extraction. Every one of them
loads in the game, so the expected result is `0 violations`.

The first pass of this sweep found 3,363 violations, every one a property left out and none an explicit zero. A
property left out keeps a built-in default, which can be non-zero and pass. That gave the gate its rule:

- a zero value always fails;
- a missing value fails only when **no** stock object of the class leaves it out.

With that rule, all 888 stock files of 201602 pass, and the unfixed probe fails with the game's own message.

## The gate: `modkit.core.ndfrules.check_file`

A build runs it on every generated ndfbin. It:

- evaluates `defined` and the comparisons against constants;
- fails any `cond` or `custom` check, or a comparison without a constant, until the toolkit's `ndfrules.REVIEWED`
  says how to evaluate it (`nonzero`: as a defined check; `holds`: trust the stated reason)
  ([[unevaluable-check-fails-until-reviewed]]);
- on a class listed in the toolkit's `ndfrules.PROPERTIES`, fails any property no rule names until it is reviewed
  there, with what the validation does with it and what stock does: a class a generator sets in a way stock never
  does;
- fails when the installed WARNO.exe is not the one the table was read from, so a game update asks for a fresh
  `extract` instead of trusting stale rules.

`REVIEWED` and `PROPERTIES` are part of the installed core, and an update replaces them: never edit them there. When
the gate fails your build on a check you have reviewed and believe is wrong, put its exact message in your build's
`reviewed_pending` (`warno-gates`: "A known failure you can't fix yet"), and send the review upstream as a
contribution, with the stock evidence, so the next toolkit release carries it.

## What it does not cover

- **Checks made later than validation:** binding to other files, initialisation after load, run-time lookups. The
  second probe launch passed this gate and crashed at run time on a dialog button token that resolves only in the
  in-game interface dictionary ([[dialog-button-ingame-dictionary]]); that needed a gate of its own.
- **The loader's own type and name checks**: a component's shape gate admits only class, property and value-type
  combinations stock uses.
- **Meaning**: a reference that resolves, but to the wrong kind of object, passes.
