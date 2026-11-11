---
id: soviet-player-camp
title: A clone of Survivors loads and plays with a Soviet player in the stock PACT-player camp shape
status: PROBED
last_verified: 201602 2026-11-11
source: stock-data
topics: [operation-setup]
shapes: [modkit.ops.profile.SOVIET_PLAYER_CAMP_ROWS, modkit.ops.profile.SOVIET_PLAYER_SIDES, modkit.ops.profile.SOVIET_PLAYER_DECK_SWAP, modkit.ops.profile.SOVIET_PLAYER_SUPPLY]
trials: [2026-11-10-probe3-play1-effect-crash, 2026-11-11-probe3b-play1-no-supply, 2026-11-11-twin-strike-play1]
stock_precedent: three stock Operations have a PACT player, two on a Soviet deck (RedJuggernaut, Sledgehammer) and one on an East German deck (Gotterdammerung)
---
**Stock precedent.** Three stock Operations have a PACT player. In each the player's camp is Alliance 0,
AllianceStyle REDFOR (4) and Nationalite PACT (1), and the enemy camps are Alliance 1, BLUFOR and NATO, on NATO AI
decks:
- RedJuggernaut: the deck `OP_BASE_RJ_Player`, the 79th Guards Tank Division, a Soviet deck; enemy `OP_BASE_RJ_IA`;
- Sledgehammer: the deck `OP_BASE_SH_Player`, from the division `SOV_57_GMRD_challenge`, a Soviet deck. Its two
  allied camps, `ally_TNK` and `ally_VDV`, are REDFOR and PACT in Alliance 0 too, so an allied camp of the player's
  nationality is stock;
- Gotterdammerung: the deck `OP_BASE_GOT_Player`, from `RDA_11MSD_challenge`, an East German (PACT) deck, not a
  Soviet one; enemy `OP_BASE_GOT_IA1` to `IA3`.
Survivors has two PACT camps at Alliance 1 and two NATO camps at Alliance 0, one of them the player.

**What our build changes** (the `nuke_sov` content of the third probe, [[content-identity-unique]] for its own identity):
- the player's camp row: AllianceStyle 4 (REDFOR), Nationalite 1 (PACT), Alliance 0 kept, so the deployment zones and
  arrivals stay where they are; its `SetDeck` is `OP_BASE_RJ_Player`, and the menu's LocalPlayerDeck follows
  (`modkit.ops.profile.Content.deck_swap`);
- the other Alliance 0 camp: REDFOR and PACT, deck `OP_NORTH_SURV_SOV` (Survivors' own Soviet deck);
- the two Alliance 1 camps: BLUFOR and NATO (the default), decks `OP_BASE_RJ_IA` and `OP_NORTH_SURV_BEL`;
- the victims are NATO tanks in one of the Alliance 1 camps.

**What a probe build showed** (two plays of `nuke_sov`, both ended by an unrelated effect crash,
[[2026-11-10-probe3-play1-effect-crash]]): the build loads and reaches the deploy phase with the player's camp
Soviet. Its deploy screen lacked the button that switches between the groups and battlegroup views, which Open Door's
NATO player has. The probe build ran with the buy menu's view switch force-hidden (the probes' default); Twin Strike,
on the same camp shape with the switch left at Default, showed both views ([[2026-11-11-twin-strike-play1]]), so the
missing view was the probe's HUD setting, not the camp.

**What a play showed.** Twin Strike, a clone of Survivors on this shape (its allied camp Soviet too), loaded and
played well past the deploy phase with the player's camp Soviet: the player's cards, RedJuggernaut's and the ones the
script adds, were bought and deployed, and the battle against the NATO camps ran on to the second counter-attack
([[2026-11-11-twin-strike-play1]]).

**The stock deck's supply.** `OP_BASE_RJ_Player` has no supply helicopter. Its only supply unit is the Ural-4320
truck, and the buy menu offers it only in the HQ groups of its two tank battalions (battlegroups 2 and 3); its recon,
air defence and artillery group and its air groups hold none. A Soviet player on it found no supply to buy
([[2026-11-11-probe3b-play1-no-supply]]), and with the buy menu's view switch hidden those groups may never show. So
the toolkit adds the shared supply at load, `modkit.ops.profile.SOVIET_PLAYER_SUPPLY` (Ural-4320 trucks x4, Mi-8TZ
supply helicopters x2), with AddUnitToDeck [[add-unit-to-deck]]: `nuke_sov` and Twin Strike both do. A stock test
re-checks the gap ([[stock-deck-fits-its-own-mission]]).

**Not yet seen in play:**
- whether the menu and the briefing show a Soviet player (their pictures are Survivors' own);
- whether a strike's victims show as enemies.

<!-- referenced-by:start -->
## Referenced by

- Trials: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-probe3b-play1-no-supply](../trials/2026-11-11-probe3b-play1-no-supply.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
- Shapes: [`modkit.ops.profile.SOVIET_PLAYER_CAMP_ROWS`](../../src/modkit/ops/profile.py), [`modkit.ops.profile.SOVIET_PLAYER_SIDES`](../../src/modkit/ops/profile.py), [`modkit.ops.profile.SOVIET_PLAYER_DECK_SWAP`](../../src/modkit/ops/profile.py), [`modkit.ops.profile.SOVIET_PLAYER_SUPPLY`](../../src/modkit/ops/profile.py)
- Examples: [`components/ops/examples/probes/README.md`](../../examples/probes/README.md), [`components/ops/examples/probes/probes/nuke.py`](../../examples/probes/probes/nuke.py), [`components/ops/examples/twin-strike/README.md`](../../examples/twin-strike/README.md), [`components/ops/examples/twin-strike/docs/design.md`](../../examples/twin-strike/docs/design.md), [`components/ops/examples/twin-strike/twinstrike/forces.py`](../../examples/twin-strike/twinstrike/forces.py), [`components/ops/examples/twin-strike/twinstrike/op.py`](../../examples/twin-strike/twinstrike/op.py), [`components/ops/examples/twin-strike/twinstrike/profile.py`](../../examples/twin-strike/twinstrike/profile.py)
- Records: [2026-11-10-probe3-play1-effect-crash](../trials/2026-11-10-probe3-play1-effect-crash.md), [2026-11-11-probe3b-play1-no-supply](../trials/2026-11-11-probe3b-play1-no-supply.md), [2026-11-11-twin-strike-play1](../trials/2026-11-11-twin-strike-play1.md)
<!-- referenced-by:end -->
