# warno-modkit

WARNO modding components shipped as Claude Code plugins: the marketplace `warno-modkit` lists `warno-core`
(`components/core`) and `warno-ops` (`components/ops`). This is a public repository: everything committed here is
public, including its history. [README.md](README.md) is the overview; [knowledge/README.md](knowledge/README.md)
is the map of what the components know, by topic, over the one-fact-per-file records in `components/*/knowledge/`.

## The loop, and the skill for each step

| Step | Skill |
| --- | --- |
| Point the toolkit at the install, build the corpus, derive the rules | `warno-setup` |
| Before relying on anything unproven: the records, then stock | `warno-stock-precedent` |
| Build an Operation | `warno-new-operation` (ops) |
| Show an Operation's design as a review page | `warno-op-storyboard` (ops) |
| Run the gates, or add one | `warno-gates` |
| Design a probe, hand a build over, debrief the play | `warno-probe-and-playtest` |
| A launch or a play failed | `warno-launch-triage` |
| Record what a launch, play, probe or survey showed | `warno-record-finding` |
| Share a played mod | `warno-ship` |
| Add a component | `warno-new-component` |

Follow the skill rather than improvising its steps. The modder plays the game; Claude never launches or drives
WARNO.

## Working here

- **Python:** always `.venv/Scripts/python` (3.14 or newer, with editable installs of both components). A bare
  `python` may be older and fails on the game's zstd archives.
- **Tests:** `.venv/Scripts/python tools/run_tests.py` runs both suites as CI does (core in one process, ops one
  module per process) and prints the tests run and skipped per suite; name a suite (`core`, `ops`) to run only that.
  One module: `-m unittest discover -s components/<name>/tests -t components/<name>/tests -p test_<x>.py` from the
  repository root. Tests that need stock data skip when no extraction is configured; a skip proves nothing.
- **Local data** comes from the git-ignored `modkit.local.toml` or `MODKIT_GAME_DIR`, `MODKIT_EXTRACTED`,
  `MODKIT_DATA`, `MODKIT_BUILD` (`warno-setup`). `modkit.core.paths` is the only code that knows where it is.
- **Game build:** `python -m modkit.core.gamebuild` shows the installed build. When it is not in `VERIFIED_BUILDS`, say
  so before trusting a gate or a record. Add a build there only after the probes play clean on it, and only once
  packaging and the stock declarations have moved to it.
- **Before every commit**, with that interpreter: `-m modkit.core.knowledge render`, `-m modkit.core.knowledge
  check .`, `-m modkit.core.repocheck --history .`, `-m ruff check .` (the version CI pins in
  `.github/workflows/ci.yml`) and both test suites (`tools/run_tests.py`); `claude plugin validate .` after a
  manifest change. CI runs the
  same on every pull request (README, Develop). Commit the generated pages (the `knowledge/` folder, each
  `INDEX.md`, the "referenced by" footers) with the change that caused them; never edit them by hand.
- **Commits:** one task per commit, the message starting with the component (`core: ...`, `ops: ...`, `docs: ...`).
  Stage files by explicit path. Commit with `TZ=UTC` set and the neutral identity (`modkit.repo.toml`, `[identity]`;
  the history scan fails any other); don't sign commits with a personal key.
- **Pull requests:** `main` is protected. Changes reach it only through a pull request, with linear history and no
  force pushes. Branch from `origin/main`, push the branch, and open the PR with `gh pr create --base main`. Merge
  locally once the maintainer approves: on an up-to-date `main`, `git merge --ff-only <branch>`, then push `main`;
  GitHub marks the PR merged. Never use GitHub's merge button or edit in the web interface: a web merge commits under
  GitHub's identity and fails the history scan.

## Rules for the public tree

`repocheck` enforces most of these; the rest are on you.

- **No game data:** no extracted files, no `.ndfbin`, `.dat`, `.dic` or `.tgv`, no rules table, no game text, no
  golden outputs holding stock content. Short identifiers, file names, hashes and map coordinates are fine.
- **Nothing read out of the game's executable beyond the rule a mod must pass:** no addresses, offsets, byte
  signatures, disassembly or crash-dump contents. State the rule as a functional check, proven against stock.
- **Nothing personal:** no local paths, user names or emails; manifests name only the generic owner.
- **One copy of everything.** A component imports its declared dependencies and nothing else, and never copies
  their code. A skill reaches its own files through `${CLAUDE_PLUGIN_ROOT}`, never a relative path out of its
  component.
- **Cite, don't restate.** Name a knowledge record as `[[id]]`; every ID must exist (`knowledge check`).
- **The Gameplay-mod limitation** is stated in the README as it stands. Never describe a way around it.
- **Gates are never loosened** to make a build pass. A known failure under review goes in the mod's reviewed-pending
  list, word for word.
