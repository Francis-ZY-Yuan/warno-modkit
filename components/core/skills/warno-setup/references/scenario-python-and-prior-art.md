# The shipped scenario Python, and the prior community tools

## The scenario Python is a reading aid, not something to ship

The game ships its level-design scripting layer as compiled Python 2.5 modules in `.xyz` envelopes: a library
(`Eugen/leveldesign`, `EugenSolo/leveldesignsolo` and their `_specific` parts) in the large data archives, and one
`effetmap.xyz` per scenario in `<S>_Assets.dat`, under `PC/Python/F0/` and `PC/Python/F1/` (the two flavours of the
same module; F0 also carries editor names).

A scenario module is flat: it creates handles for map items (by the four words of each item's GUID), then hundreds
of keyword-argument constructor calls, then one root descriptor. **The keyword arguments are the native property
names** (`Condition`, `ActionsReussi`, `ObjectiveText`, `DureePause`, ...), which makes the decompiled source a
readable index of what each script action takes.

Since build 201602 the game runs the scenario from its GDScript ndfbin, the compiled form of that same graph, and
no longer imports the Python ([[gdscript-is-what-loads]]). So:

- **Read** `.xyz` when you want the stock graph with its names: `python -m modkit.core.xyz decompile <xyz or folder>
  <out>`. It needs `uncompyle6` and `xdis` in your venv (`python -m pip install uncompyle6 xdis`). The decompiled
  code is game data: keep it in your build or scratch folder, never commit it, never run it.
- **Ship** GDScript. A mod that carries an `.xyz` gives the game two script sources for one scenario; no working
  mod does that.

The two forms match class for class. In one stock Operation compared in full, every action and tag class had the
same count in both, except Sequential (109 against 111). Count in GDScript when the number matters; use the
Python for the names.

## Prior community tools

Read these before building something they already do. None of them ships game data.

| tool | licence | what it covers |
| --- | --- | --- |
| murmax / WarnoArmyGeneralFramework | MIT | Compiles YAML into an Army General campaign mod by cloning stock script graphs; readers and writers for CNDF, edat and dictionaries; readers for TGV, `.xyz` and Python 2 marshal; installs and activates its builds; renames every cloned identity. The closest prior art. It stops at the Army General layer: no scripted tactical Operations |
| sneadtristen6 / R.U.S.E-2.0-Project | GPL-3.0 | Authors Operation mission scripts for Eugen's older game R.U.S.E. (goals, events, reinforcements, strikes) and checks them before a test launch; the same idea one game back, built with an AI agent |
| PiggiesAndBear's ndfbin editors | Apache-2.0 | Edit WARNO's compiled unit and deck data (ndfbin) directly; the same author publishes an agent skill for WARNO NDF modding |
| dary1337 / YSM_Installer | Apache-2.0 | One-click installer that activates a WARNO mod in the Mod Center's list |
| Ulibos / ndf-parse | MIT | Parses and edits NDF **text** in mod folders; no ndfbin, GDScript or scenario support |
| moddingSuite (the kilivan4iK fork) | MIT | .NET viewer and editor for ndfbin in older builds; documents the value tags; version-2 archives only |

Two lessons from them that this toolkit follows:

- **Clone to a new identity; never override a stock scenario in place.** A pack with a stock scenario's name in a
  mod does not replace the stock pack ([[operation-menu-registration]]).
- **Pin your inputs.** murmax refuses to build from anything but the exact stock files it was written against. The
  gates here do the same job: a stock sweep in the tests fails when an update changes what a gate relies on.
