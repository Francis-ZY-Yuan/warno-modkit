---
name: warno-new-component
description: Use when adding a new component (a plugin of WARNO skills, scripts, examples and knowledge) to a modkit marketplace, or moving one from a private workspace into a public repository.
---

# New component

## Overview

A component is one folder and one Claude Code plugin: skills, the scripts they run, worked examples, and knowledge
that grows with every trial. Components build on components by declaring a dependency and importing, never by
copying. Every component has the same shape, so moving one between repositories is a folder move plus a review.

`python` is your venv's interpreter (see `warno-setup`).

## The shape

```
components/<name>/
  .claude-plugin/plugin.json   {"name": "warno-<name>", "version": ..., "description": ..., "dependencies": ["warno-core"]}
  pyproject.toml               distribution modkit-<name>, the same dependencies as modkit-<x>
  src/modkit/<name>/__init__.py   the package modkit.<name>; no src/modkit/__init__.py (a namespace package)
  skills/<skill>/SKILL.md      the procedures, each with its references/
  examples/                    worked examples a skill can build
  knowledge/                   mechanisms/, trials/, lessons/, topics.md, INDEX.md (generated)
  tests/
```

Every folder exists; an empty one (`lessons/` at first, say) holds a `.gitkeep`. Copy `pyproject.toml` from
`${CLAUDE_PLUGIN_ROOT}` (this plugin's folder, two levels above this skill's base directory) and change the name and
dependencies. `topics.md` declares the topics the component's mechanisms are filed under, one
`## <topic-id>: <title>` heading and a sentence of scope each (see `${CLAUDE_PLUGIN_ROOT}/knowledge/README.md`);
reuse a dependency's topic before declaring a new one. Register the plugin in the repository's
`.claude-plugin/marketplace.json` (`name`, `source: ./components/<name>`, `description`). Manifests name no person:
the owner is the generic contributors entry, with no email.

## Rules the repository check enforces

- `plugin.json` and `pyproject.toml` declare the same dependencies, with no cycle.
- Python imports stay inside the declared dependency closure. Code is shared only through installed packages, never
  through a relative path: an installed plugin holds only its own folder.
- A skill reaches its own component's files through `${CLAUDE_PLUGIN_ROOT}`, and other components only through
  their packages and knowledge IDs.
- Knowledge IDs are global across every component, repository and project.
- A public component never depends on, imports, names or links a private one.

## Extending, not copying

A component's skill extends another's by naming it and adding only its own steps; the gates skill runs whatever
the installed components' builds run. Where a private component needs to change shared behaviour, it plugs into a
named extension point of the shared code (the installer's hook, a build profile, extra packs, reviewed gate
exceptions); it never copies the code. If no extension point fits, add a generic one to the shared component.

## Steps

1. Scaffold the shape, and register it in the marketplace.
2. `python -m pip install -e components/<name>`.
3. `python -m modkit.core.repocheck .` (add `--history` in a public repository). Must exit 0.
4. `python -m modkit.core.knowledge render`, then `check`. Must exit 0.
5. `claude plugin validate components/<name>` and `claude plugin validate .` for the marketplace.

## Moving a private component into a public repository

1. **Sort its knowledge.** A record that must stay private moves to a private component first: exe-level detail a
   mod doesn't need in order to load or behave, anything about a private project, anything personal.
2. **Check it can go public.** Every dependency is public, its code and examples hold nothing private, and its
   skills exist.
3. **Move the folder with no history.** Copy the files through the public tree's checks; never bring the private
   commits along.
4. **Re-point the dependents.** Each private plugin that depends on it changes one line in its `plugin.json`, from
   a same-marketplace name to a cross-marketplace one. The private marketplace lists the public one in
   `allowCrossMarketplaceDependenciesOn`.
5. **Run the public checks** (`repocheck --history`, the knowledge check) over the public tree, and update the
   README's component list and limitations.

The public tree refuses: game data files and anything over 512 KiB, local paths, the deny-list words, long hex
literals and the words that name exe internals, names of components it does not hold, and personal data in
manifests. A finding is excused only by an exact path, text and reason entry in
`components/core/hygiene-allow.toml`.

## Common mistakes

| Mistake | Fix |
| --- | --- |
| Copying a function from another component | Import it, or add an extension point there |
| A relative path to another component | Install its package and import it |
| A dependency in `plugin.json` but not `pyproject.toml` | Declare it in both |
| Bringing private history along on a move | Fresh history: copy the files, not the commits |
