---
id: deck-names-from-op-dictionaries
title: A deck's page and platoon names resolve in the game's COMPANIES and PLATOONS lists, to which an Operation can append its own dictionaries
status: UNTESTED
source: exe-analysis
topics: [objectives-and-text, units-and-orders]
gates: [modkit.ops.gates.check_tokens]
shapes: [modkit.ops.rekey.append_dico_resources, modkit.ops.profile.OpProfile.dictionary_lists, modkit.ops.profile.Content.list_tokens]
stock_precedent: every name token of the game's decks resolves in UNITS (127 deck names), COMPANIES (43 page names) or PLATOONS (79 platoon names); 13 stock MapConfigurations append their own file to the MAPS list; none appends to COMPANIES or PLATOONS
---
**What the game does** (game build 210942). A deck's names are looked up each in one fixed list of the game's
dictionaries: its `DeckName` in UNITS, a page's `Name` in COMPANIES and a platoon's `Name` in PLATOONS, never in the
scenario's own dictionaries. The lookup runs when a `SetDeck` builds the deck, in battle, not when the file loads: a
token no file of its list holds is the fatal "Dictionary error : No string found for token" naming the token and the
list [[crash-dump-names-the-error]]. A zero token (no name) is not looked up.

A `TLocalisationDicoResource` (`DicoToken`, `FileName`) appends its file to the list its `DicoToken` names, from
whatever file loads it. Stock MapConfigurations append their `SCENARIO_DEFINITION.csv` to MAPS so, and the game does
not tell the lists apart.

**The shape.** Ship the names in dictionaries of the op's own, one per list, and append each to its list from the
op's MapConfiguration, beside its MAPS resource, named as `SCENARIO_DEFINITION` is
(`ScenariosData:/<scenario>/<name>.csv`, shipped as `Localisation/<scenario>/<name>-<LANG>.dic` in every language).
A profile names them in `dictionary_lists`; the build appends the resources (`rekey.append_dico_resources`). The
fallback is the game's own words: any token of COMPANIES or PLATOONS resolves, declared in `Content.list_tokens`.

**The gate** (`modkit.ops.gates.check_tokens`): each deck name is in its list, counting the declared stock tokens and
every file a shipped MapConfiguration appends to that list, in every language; a file appended but not shipped in a
language fails. Each declared stock token is held to the game's own dictionary of its list, in every language
(`modkit.ops.LIST_DICS`, read from the extraction), so a wrong declaration fails the build, not the first SetDeck.

**Not yet seen in play:** a scenario file appending to COMPANIES or PLATOONS (no stock scenario does). If it fails,
the first `SetDeck` in battle shows the dictionary error naming a page or platoon token; the stock-names fallback is a
rebuild.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-12-deck-gate-bad-builds](../trials/2026-11-12-deck-gate-bad-builds.md), [2026-11-12-deck-gate-stock-survey](../trials/2026-11-12-deck-gate-stock-survey.md)
- Gates: [`modkit.ops.gates.check_tokens`](../../src/modkit/ops/gates.py)
- Shapes: [`modkit.ops.rekey.append_dico_resources`](../../src/modkit/ops/rekey.py), [`modkit.ops.profile.OpProfile.dictionary_lists`](../../src/modkit/ops/profile.py), [`modkit.ops.profile.Content.list_tokens`](../../src/modkit/ops/profile.py)
- Skills: [`components/core/skills/warno-launch-triage/SKILL.md`](../../../core/skills/warno-launch-triage/SKILL.md), [`components/ops/skills/warno-new-operation/references/op-anatomy.md`](../../skills/warno-new-operation/references/op-anatomy.md)
- Examples: [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/forces.py`](../../examples/twin-strike/twinstrike/forces.py), [`components/ops/examples/twin-strike/twinstrike/profile.py`](../../examples/twin-strike/twinstrike/profile.py), [`components/ops/examples/twin-strike/twinstrike/strings.py`](../../examples/twin-strike/twinstrike/strings.py)
- Records: [2026-11-12-deck-gate-bad-builds](../trials/2026-11-12-deck-gate-bad-builds.md), [2026-11-12-deck-gate-stock-survey](../trials/2026-11-12-deck-gate-stock-survey.md), [op-exported-deck](op-exported-deck.md)
<!-- referenced-by:end -->
