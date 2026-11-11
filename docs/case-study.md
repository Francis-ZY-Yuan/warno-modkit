# Case study: building a custom Operation with a foreman and subagents

This is how the toolkit's worked example, the Open Door Operation on the stock map Geisa, was built: three rounds
of work by Claude Code, each played by the modder before the next began. It is written for a modder who wants to
run the same kind of build. The findings themselves are in the knowledge records, cited by ID in backticks; the
symptom index in `knowledge/symptoms.md` maps each launch failure to its record.

| Round | Built | Tasks | Played |
| --- | --- | --- | --- |
| First probe | A test Operation with one beat per open question: deck cards, scripted fires, decoys, a helicopter landing, objectives, a timed race | 7, then a final fix wave | Three failed launches, then two plays |
| Second probe | Zone capture, objectives that resolve, a re-asked dialog, difficulty, counters, the ending, each beat in its own branch | 3 (one split in two) | One play, no crash, no stall |
| First mission milestone | The full mission frame: identity, tiered arrivals, endings through one funnel, four phases | 5, then a final fix | Handed over with its play sheet |

## The method

**One session orchestrates; subagents do the work.** The orchestrating session (the foreman) holds the plan and
makes every decision. It never writes the bulk of the code. For each task it dispatches one implementer subagent
with a brief: the plan's section for that task, the interface it must produce and the one it consumes, and the
shared constraints. Briefs point at files rather than pasting them.

**The foreman judges by cheap evidence.** After each task it ran the test suite, built every content and ran every
gate on the output, and rebuilt every earlier content to check it was still byte-identical to its recorded hashes.
It read only the load-bearing parts of the diff. One task was one commit.

**Every task got an independent review,** by a fresh subagent given the diff and the plan, not the implementer's
account of it: spec compliance first, then code quality. Findings came back ranked Critical, Important or Minor.
Fixes went back to the same implementer as a fix round, followed by a scoped re-review of just the fix. Each round
ended with a whole-branch review, then a final fix wave and its own re-review.

**Before the first dispatch, a pre-flight scan.** The foreman walked every producer-to-consumer pair between tasks
(this task's output against the next task's tests) and every task's tests against its own plan. In the first round
that found six conflicts before any code was written: a test that wanted one check number where the plan put two
on the same beat, a test that counted decoy nodes differently from the plan's timeline, a content one task
registered that only a later task created. Each became a ruling.

**Rulings are recorded with what each would cost if wrong.** When the plan was silent, ambiguous or wrong, the
foreman decided, and wrote the decision, the reason and the price of a reversal into the build ledger. That made
every decision cheap to revisit and visible to the modder.

## Rulings, and what each would cost if wrong

| Round | Ruling | Why | Cost if wrong |
| --- | --- | --- | --- |
| First probe | Every build ships all three dictionaries in all eight languages, even nearly empty | An empty dictionary had never been tried | One unused token per dictionary |
| First probe | Keep a new value on a stock property (a deck card's transporter) | The probe existed to test it | The whole script might fail to load; covered by the next ruling |
| First probe | Add a fallback build: the same probe minus the two shapes no stock file had ever used | One unknown property could stop the script loading and waste the launch | A few unused lines |
| First probe | Race the helicopter boarding against a 60-second wait | A helicopter that couldn't land would otherwise block the flight and every later check | The flight might leave without its passengers; the play sheet asked |
| First probe | Move the decoy beat from 0:05 to 0:20 | Its hint collided with another 15-second hint | The check starts 15 seconds later |
| First probe | The final fix wave takes only what matters before the launch; the rest becomes the next round's first task | The next round is planned after the play | The next round starts with known trip-wires, all listed |
| Second probe | The quick-run ending race waits for the start dialog's answer, not a fixed time | A slow click would turn a quick run into a full one | A misrouted run |
| Second probe | Give the probe its own deployment zone, ending short of the count-race zone | One deployed unit there would break the count | A corrupted readout |
| Second probe | The traffic column's route avoids every capture and count zone | Enemy vehicles in a capture circle corrupt that readout | Two beats lost |
| Milestone | Byte identity stays a foreman hash check, not a unit test | It took about 50 seconds per suite run | A regression caught one task later |
| Milestone | Count kills by unit type, not survivors by group | Per-type kills were proven in play; whether embarked riflemen count as alive was never read | None known |
| Milestone | No `Multiply`, and `MoreOrEqual` with the operands swapped instead of `LessOrEqual` against a variable | Stock never writes those forms (`stock-value-forms-only`); the swapped form has 45 stock uses | None: same arithmetic |
| Milestone | An objective that can no longer be completed shows as failed, though the spec said it never fails | A row open forever reads as a bug | A red row after an early ending of that phase |

## The review rounds

**First probe.** All seven tasks came back reviewed clean, most with minors. The foreman deferred those into a named
list and carried each one to the task that next touched the same code, instead of fixing everything at once. The
whole-branch review found no Critical issue and seven Important ones, among them an enemy spawn about 650 m from a
landing zone while the helicopter might still be inbound, and a check whose time window missed the clash it was
meant to see. The fix wave took only what mattered before the launch (two script fixes, one stock ordering, and
the play-sheet edits) and parked the rest as the next round's first task. Its scoped re-review confirmed all fifteen
findings in the wave addressed.

Then the launches. The first stopped at load on a value the game treats as undefined (`changestress-damagetype-zero`).
The second crashed when the start dialog opened; the crash dump named a button token the game looks up in only one
dictionary (`dialog-button-ingame-dictionary`). The third loaded, but nothing could be called in after the battle
started: the deployment phase had been rebuilt from a stock Operation that never buys, and lost a part an earlier
build had already recorded (`deployment-phase-recipe`, `recorded-recipe-becomes-a-gate`). Each became a gate before
the next launch, proven to fail the bad build and pass all stock: the load-time rules table
(`load-time-validation-rules`), the in-game dictionary check, and a check for the player's arrival entries. That last
one only counted the entries, and the second play found land units that still never arrived: every entry ended
outside any zone. The gate now reads the zone polygons (`arrival-end-in-zone`, `counting-parts-is-not-checking`).
The two plays also found: decoys under a "weapons jammed" effect still fired (`weapons-jammed-effect`),
the scripted helicopter boarding never happened (`helicopter-boarding`), objective labels pinned the map corner
(`objective-label-needs-position`), and one misplaced action froze every later enemy beat (`seteffect-never-finishes`).

**Second probe.** Before the play, an independent review traced the built script node by node against the stock
files and against the play sheet. It found ten problems, and **no existing gate caught any of them**: the gates did
not model when a counter stops updating, who owns a unit after a scripted order hands it to the AI, run timing, or
how the sheet told the player to read a result. Two examples: a bonus objective's counter would freeze one poll
before the final kill, so the sheet would have recorded a false failure; and an enemy tank was ordered to move after
a hand-over that no stock script ever follows with a move, so it might never leave the zone it was meant to vacate.
The fix replaced the move with removing the tank. Two fix rounds addressed all ten. The play then ran to its end
with no crash and no stall.

**First mission milestone.** Every task followed the same loop: the implementer reported done with concerns, the
foreman ruled on each concern, a reviewer approved (none found a Critical or Important issue), and a fix round with
a scoped re-review closed the minors that mattered. One fix round was an audit: every variable operation in the
mission was checked against the forms stock uses, and the one form stock never writes was replaced. The
whole-branch review found one Important issue, that a withdrawal from several towns at once fired two or three hints
within fifteen seconds. A hint sequencer fixed it, and the re-review approved.

## What to copy

- **Spend the player's time last.** Gates, stock counts and reviews cost seconds to minutes. A launch costs the
  player much more, so every probe shipped with a fallback build, a hash-checked install and a play sheet with the
  readings decided in advance.
- **A failed launch ends in a gate, and the gate checks every part.** None of the three launch failures came
  back as a failed launch. One came back in play, because its first gate counted the parts instead of checking them.
- **Put each probe beat in its own branch.** The first probe's single stall hid several results; the second probe's
  independent beats answered most of its questions in one play (`one-stall-hides-the-rest`).
- **Have someone trace the built output against stock and against the play sheet.** Gates check rules you already
  know; a reader finds the ones you don't.
- **Record each ruling with its cost if wrong,** and defer minors to a named list carried to the next task that
  touches that code.
