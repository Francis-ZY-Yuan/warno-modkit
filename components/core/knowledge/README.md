# Writing knowledge records

Every component keeps what it has learned in its `knowledge/` folder, as one file per record. There are three
kinds: **mechanisms** (what the game does that a mod relies on), **trials** (one attempt, with its outcome) and
**lessons** (rules the trials taught). Each mechanism is filed under one to three **topics**, which the component
declares in `topics.md`. A script reads the front matter, checks the records against each other and the code, and
generates the navigation. You write records; you never edit the generated parts.

```
components/<name>/knowledge/
  mechanisms/<id>.md      one behaviour of the game
  trials/<date>-<slug>.md one attempt
  lessons/<id>.md         one rule a trial taught
  topics.md               the topics this component declares (hand-written, small)
  evidence/               survey and RE notes the trials link to (optional)
  INDEX.md                generated
```

Every folder exists in a component; an empty one holds a `.gitkeep`.

A modder's own findings go in `knowledge/` under their project folder, with the same record folders (and a
`topics.md` if they declare topics of their own). Run the tooling from the project folder
(`python -m modkit.core.knowledge check .`, then `render .`). Nothing is written into installed plugins.

## IDs

Kebab-case: lower-case letters, digits and single dashes. IDs are **global** across every component and your
project, and shared by all three record kinds. A trial's ID is `YYYY-MM-DD-slug` (a real
date), and a record's file is named `<id>.md`. Topic IDs are a namespace of their own (see below).

## Front matter

A restricted YAML block at the top of every record, between two `---` lines:

```
key: value                scalar, plain or in "double" or 'single' quotes (always read as text)
key: [a, b, c]            inline list; [] is the empty list
key:                      block list: the items follow as "- item" lines
  - a
  - b
# a comment line          comments and blank lines are skipped
```

No nesting, no repeated keys, no other YAML. An unknown field is an error, so a typo does not go unnoticed.

### Mechanism

| field | |
| --- | --- |
| `id`, `title` | required |
| `status` | `PLAYED` worked in a real play; `PROBED` in a probe build, not yet confirmed in play; `RE` proven by exe analysis or static analysis; `STOCK` stock does it in the same graph position, we have not; `FAILED` tried and does not work (the body names the alternative); `UNTESTED` |
| `last_verified` | `<game build> <YYYY-MM-DD>`, for example `201602 2026-01-10`. Only `UNTESTED` may leave it out |
| `source` | `play`, `stock-data` or `exe-analysis` |
| `topics` | required: a list of 1 to 3 topic IDs, each declared in the `topics.md` of the record's component or of one of its dependencies |
| `gates`, `shapes` | lists of dotted names `modkit.<component>.<module>.<name>` (or `...<module>.<Class>.<method>`) of the gate or shape that enforces it |
| `trials` | list of trial IDs |
| `stock_precedent` | counts, such as `83/83 arrivals end inside a zone` |

The body says what the game does, how we know, the gotchas, and the stock definition when an effect's name misleads.

### Trial

| field | |
| --- | --- |
| `id` | `YYYY-MM-DD-slug` |
| `kind` | `launch`, `play`, `probe-run`, `re` or `survey` |
| `build` | the author's own build or commit id; it need not resolve in this repository |
| `game_version` | the game build |
| `mechanisms` | list of the mechanism IDs it touched |
| `outcome` | `pass`, `fail` or `mixed` |
| `symptom` | in the game's own words. Feeds the component's symptom index (and the map's `symptoms.md`) |
| `cause`, `result` | what was wrong; the gate added or change made |

The body is short and links to the evidence.

### Lesson

One file per lesson, `lessons/<id>.md`:

| field | |
| --- | --- |
| `id` | required |
| `title` | required: the rule itself, in one sentence |
| `trials` | required: the IDs of the trials that taught it |

The body is the reasoning, in a few lines; it may be empty.

```
---
id: prove-each-gate-both-ways
title: A gate is proven when it fails the bad build and passes stock
trials: [2026-01-10-example-play, 2026-01-12-example-launch]
---
Rebuild the failing build and see it fail; run the gate over every stock file and see them pass.
```

## Topics

`topics.md` declares the component's topics, one `## <topic-id>: <title>` heading each, followed by one sentence of
scope:

```
## zones-and-map: Zones and map
The map side of an Operation: LevelDesign items and tags, zones and their owners, the playable zone and the camera.
```

Topic IDs are kebab-case and unique across every visible component and your project; they are a namespace of their
own, and a `[[id]]` never cites a topic. A mechanism may use a topic of its own component or of one of its
dependencies; a project's mechanisms may use any topic they can see. Keep the list short: add a topic only when a
mechanism truly fits none. `game-updates` (in core) is for what changed between game builds: tag a mechanism with it
when its body ties it to a particular build.

## Citing a record

A skill or an example cites a record by writing `[[<id>]]` instead of restating it. So can the body of a record.
The citation shows up in the record's "referenced by" footer.

## Links, and the rules the check enforces

`python -m modkit.core.knowledge check` (also part of `python -m modkit.core.repocheck`) fails on:

- a record that breaks the schema, a mechanism with no `topics`, a file whose name is not its ID, a duplicate ID;
- a topic that no `topics.md` declares, a topic of a component outside the record's dependencies, a duplicate topic
  ID;
- a leftover `lessons.md` in the old one-file form (split it into `lessons/<id>.md`);
- a stale generated page: one that starts with the generated header but `render` no longer writes;
- an unknown ID, or an ID of the wrong kind, in `trials`, `mechanisms` or a `[[id]]`;
- a `PLAYED` mechanism with no passing `play` trial (a trial counts when the mechanism lists it or the trial lists
  the mechanism);
- a gate or shape that is not a dotted path to something defined in the record's component or one of its
  dependencies (found by reading the source, never by importing it);
- a **public record, skill or example that names the ID of a private record**. Public components may link each other
  freely; private components and project folders may link public records;
- a public `exe-analysis` mechanism that has neither a `probe-run` or `play` trial that did not fail, nor a gate
  proven both ways. In this check "proven both ways" means the record lists a gate and has both a passing and a
  failing trial.

It only warns when a mechanism's `last_verified` names a game build other than the installed one (read from the
game folder set in `modkit.local.toml`; the warning is skipped when no game folder is configured).

## Generated navigation

`python -m modkit.core.knowledge render` writes, for the repository in the current folder, a map in `knowledge/` at
its root:

- `knowledge/README.md`: the page to read first. Where each kind of question starts, the topics with their
  mechanism counts (and how many are `PLAYED`), and the components;
- `knowledge/topics/<topic>.md`: one per topic in use. Its mechanisms by status, the lessons its trials taught, and
  its trials;
- `knowledge/symptoms.md` (the game's words, the mechanism, the gate that catches it), `status.md` (the mechanisms
  by status), `trials.md` (newest first), `lessons.md` (one line per lesson) and `builds.md` (each game build with
  the mechanisms last verified on it and the trials run on it).

Beside the map it writes:

- `components/<name>/knowledge/INDEX.md`: the component's mechanisms under each topic they carry, the symptom index
  of its own trials, its trials by date, its lessons. It links nothing outside the component's knowledge folder, so
  an installed plugin carries a working index of its own;
- the block between `<!-- referenced-by:start -->` and `<!-- referenced-by:end -->` at the end of each mechanism and
  lesson page: the trials, gates, shapes, skills, examples and records that cite it.

In a modder's project folder the map pages go into the project's own `knowledge/` folder, next to `mechanisms/`,
`trials/` and `lessons/`. No separate `INDEX.md` is written there: the map's README covers the project's records.

Every generated page starts with a `<!-- Generated by ... -->` line. `render` deletes a page with that line that it
no longer writes (a topic nobody uses any more, or the one-page `KNOWLEDGE.md` the map replaced), and never touches
a file without it. It refuses to render while the records have errors. `render --stale` lists the files that are
out of date without writing them. A public repository's pages are rendered from its public records only.

To add a finding: write the trial file, update `status`, `trials`, `topics` and `last_verified` on each mechanism
it touched, add a lesson file if it taught a rule, then check and render.
