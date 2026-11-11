---
name: warno-setup
description: Use when starting WARNO modding with warno-modkit, when a modkit command says a folder is not configured, or after a WARNO update.
---

# WARNO setup

## Overview

The toolkit ships no game data. Setup points it at your own WARNO install, installs the components' Python
packages, builds a stock corpus from your install, and derives the load-time rules from your own WARNO.exe. Every
other skill assumes this is done.

**What reads WARNO.exe, and why.** `ndfrules` reads your own WARNO.exe, read-only, to find the load-time checks
your mod must pass. `crashdump` reads the error message in your own crash dumps. Neither writes anything to the exe,
and neither does anything else with it.

`${CLAUDE_PLUGIN_ROOT}` below is this plugin's folder: two levels above this skill's base directory.

## Steps

Work from your own project folder (a contributor works from the repository clone).

1. **Python 3.14 or newer** (the game's archives need zstd, which arrived in 3.14):
   `py -3.14 -m venv .venv`. In every warno skill, `python` means this venv's interpreter
   (`.venv/Scripts/python` on Windows), never a system Python.
2. **Install the packages, core first.**
   - Installed plugins: `claude plugin list --json` gives each `warno-*` plugin's `installPath`. Run
     `python -m pip install "<installPath>"` for `warno-core` first, then
     `python -m pip install --no-deps "<installPath>"` for each other one: their `modkit-*` dependencies are the
     plugins you install yourself, never a download (`--no-deps` keeps pip from looking one up on PyPI). Re-run
     after a plugin update, since the update replaces that folder.
   - Clone: `python -m pip install -e components/core -e components/ops`.
   - If pip cannot fetch setuptools: install `setuptools>=69` once, then add `--no-build-isolation`.
3. **Write `modkit.local.toml`** in the project folder, and add it to `.gitignore` (it holds your paths):

   | key | value |
   | --- | --- |
   | `game_dir` | the WARNO folder under your Steam library's `steamapps/common` |
   | `extracted` | an empty folder outside the game folder, for the stock corpus (about 1.2 GB) |
   | `data_dir` | optional; derived data such as the rules table. Default: `modkit-data` beside `extracted` |
   | `build_dir` | optional; where builds write by default, and the only folder a rebuild may delete in. Default: `build` beside this file (in the working folder when there is no toml) |
   | `deny` | optional list of personal strings (your user name) the hygiene check refuses |

   The variables `MODKIT_GAME_DIR`, `MODKIT_EXTRACTED`, `MODKIT_DATA` and `MODKIT_BUILD` override the file.
4. **Build the corpus:** `python -m modkit.core.setup extract --into <extracted>`. It reads the
   install only, and builds every path the installed components declare they read.
5. **Derive the rules:** `python -m modkit.core.ndfrules extract`, then `python -m modkit.core.ndfrules verify`. Verify must
   end with `0 violations`; anything else means the table or the corpus is wrong. Stop and look.
6. **Check:** `python -m modkit.core.setup check`. Expect the game build, and "matches" for both the extraction and the
   rules table.
7. **Check the game build:** `python -m modkit.core.gamebuild`. It prints your installed build and the builds this
   toolkit was verified on. A `GAME BUILD:` warning means yours is another one: read `knowledge/builds.md` and
   `knowledge/topics/game-updates.md` before trusting a gate or a record. It is a warning, never a failure.
8. **Check the knowledge against your build:** `python -m modkit.core.knowledge check .` A `warning:` line names a
   mechanism last verified on another game build: treat it as unverified until a probe or play confirms it.

## After a game update

`setup check` reports STALE. Re-run steps 4 to 8, rebuild every mod, and play each again before sharing it: see
[[mod-version-and-config-lines]]. A rules diff from `ndfrules extract` lists the checks that changed. Review it
before trusting the gate.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| A system Python older than 3.14 | zstd fails; use the venv's interpreter |
| `extracted` inside the game folder or a repository | Keep it outside both; nothing is ever written to the install |
| An editable install from an installed plugin's folder | Plain install; the folder is replaced on update |
| Committing `modkit.local.toml` | Git-ignore it; the hygiene check fails a committed one |
| Skipping `ndfrules verify` | A table that fails stock fails your mods for the wrong reason |

## References

- [references/stock-corpus.md](references/stock-corpus.md): how the install stores its data, what the corpus
  holds, and the map-picture coordinates.
- [references/scenario-python-and-prior-art.md](references/scenario-python-and-prior-art.md): the shipped scenario
  Python, why mods ship GDScript instead, and the prior community tools.
