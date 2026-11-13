"""Twin Strike's forces: the player's deck, the force tables, the scale knob and the share thresholds (design 6).

Pure data and arithmetic, in Open Door's style. Nothing here reads the game or the map: a row's spawn is a point name
of twinstrike.map's POINTS, and its units are bare stock names (`T80BV_SOV` for `Descriptor_Unit_T80BV_SOV`). The row
type is modkit.ops.models' ForceRow; the arithmetic (rows_of, scaled, group_rows, group_total, share_count) is
modkit.ops.forces'.

The player's deck (design 6.1) is RedJuggernaut's, OP_BASE_RJ_Player [[soviet-player-camp]], which a script can only
add to [[add-unit-to-deck]]:
- START_TARGETS is what the deck must hold at the start, at least; START_ADDS is what AddUnitToDeck adds at load, only
  what RJ lacks or holds too few of (top_up of the targets over RJ's packs). The adds are pinned here, so the build
  reads no deck; a stock test re-derives them from the game's decks, so a game update that changes RJ's deck fails
  that test, not the build.
- SUPPLY is the Soviet player's supply (modkit.ops.profile.SOVIET_PLAYER_SUPPLY), its own add at load beside
  START_ADDS: RJ's deck has no supply helicopter, and its supply trucks sit only in its tank battalions' HQ groups. A
  stock test re-checks that reason.
- START_LOCKS are RJ's own defence-grade types, locked by type (LockDeckUnit) until the village falls.
- RESERVE is what the fall adds (TS4b's unlock), the heavy air defence among it.
Every infantry card rides in a carrier, as stock fields each of these squads.
The deck is not scaled: FORCE_SCALE sizes the battle the script makes.

ROWS is every scripted row of design 6.2 and 6.3 at 1x: the player's FOBs and the division artillery (6.2), the
garrison and both NATO battalions (6.3). `scaled()` turns it into the forces for another scale: each row not marked
`fixed` is multiplied and rounded per row (floor of 1). The FOBs (one per FOB point) and the guns (the player's fires,
not NATO's strength) are fixed. Thresholds are shares of a base count, turned into counts with `share_count()`
(design 6.4), so a resize can never push one past its base or down to 0. Rounding: floor(x + 0.5).

A ForceRow's camp is a side of modkit.ops.profile.SOVIET_PLAYER_SIDES: "Soviet" (the player), "NATO", or "SovietAlly"
(the player's allied camp: each fire's battery is created there, at GUN_SPAWN in the cut's north-west corner, so the
player's units never engage it, and removed after; design 5.4).
"""
from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping

from modkit.ops.forces import group_rows, group_total, rows_of, scaled, share_count
from modkit.ops.models import ForceRow
from modkit.ops.profile import RJ_PLAYER_DECK, SOVIET_PLAYER_SUPPLY

FORCE_SCALE = 1.0       # design 6.4: 1x at release

# --------------------------------------------------------------------------- the player's deck (design 6.1)

DECK_BASE = RJ_PLAYER_DECK            # a card is a ForceRow (unit, count, transport or None)

# The ATGM team (game build 201602; a stock test re-derives both): the Soviet ATGM infantry team whose missile has the
# highest AT penetration among the teams a Soviet division's rules field (DivisionRules.ndf), the longer range on a tie.
# It is the Konkurs-M team, its 9M113M (late) 23 AP at 2,625 GRU, which the 27th Guards Motor Rifle Division fields in
# a UAZ-469 or a BTR-80: the BTR-80 is its armoured carrier. Every other team's missile is 20 AP or less.
ATGM_TEAM, ATGM_CARRIER = "ATteam_KonkursM_TTsko_SOV", "BTR_80_SOV"
# The reserve's tank: the T-80U variant whose ATGM has 25 AP, the T-80U obr. 1989 (its 9M119M Invar; the T-80U, the
# T-80UD and the T-80U command tank fire the 21 AP 9M119M Refleks). No command variant has the Invar, so the command
# tank stays the T-80U's. A stock test re-checks the AP.
T80U_TANK = "T80U_Obr89_SOV"
# The start, at least: the forward detachment's tanks, command units (three, so the fall never hangs on one vehicle),
# motor rifles in their BMP-2s, two ATGM teams, flamethrower engineers, recon, air defence, the regiment's 2S1s and four
# bare Ka-29s. Every infantry card rides in a carrier, as stock fields these squads (no stock deck holds one bare): the
# engineers in MT-LBs (RJ's deck fields the MT-LB, the 2S12's tractor; 5 Army General pawns pair them so) and the
# scouts in UAZ-469s (RJ's deck fields them; the pairing of 170 of 198 pawns and of the 79th Guards Tank Division's own
# rule); the ATGM teams in their BTR-80s.
START_TARGETS: tuple[ForceRow, ...] = (
    ForceRow("T80BV_SOV", 10), ForceRow("T80BV_CMD_SOV", 2), ForceRow("BMP_2_CMD_SOV", 1),
    ForceRow("MotRifles_SOV", 8, "BMP_2_SOV"), ForceRow(ATGM_TEAM, 2, ATGM_CARRIER),
    ForceRow("Engineers_Flam_SOV", 2, "MTLB_transp_SOV"), ForceRow("BRM_1_SOV", 2),
    ForceRow("Scout_SOV", 2, "UAZ_469_SOV"), ForceRow("ZSU_23_Shilka_SOV", 2), ForceRow("MTLB_Strela10_SOV", 1),
    ForceRow("2S1_Gvozdika_SOV", 4), ForceRow("Ka_29_SOV", 4),
)
# top_up(START_TARGETS, RJ's packs), pinned (game build 201602). RJ already holds 16 T-80BV, 2 BRM-1 and 2 MT-LB
# Strela-10, so those add nothing; it holds 2 2S1, so 2 more. The stock test re-derives this.
START_ADDS: tuple[ForceRow, ...] = (
    ForceRow("T80BV_CMD_SOV", 2), ForceRow("BMP_2_CMD_SOV", 1), ForceRow("MotRifles_SOV", 8, "BMP_2_SOV"),
    ForceRow(ATGM_TEAM, 2, ATGM_CARRIER),
    ForceRow("Engineers_Flam_SOV", 2, "MTLB_transp_SOV"), ForceRow("Scout_SOV", 2, "UAZ_469_SOV"),
    ForceRow("ZSU_23_Shilka_SOV", 2), ForceRow("2S1_Gvozdika_SOV", 2), ForceRow("Ka_29_SOV", 4),
)
# The Soviet player's supply, added at load after START_ADDS: the shared constant, not a copy. RJ's deck has no supply
# helicopter, and its Ural-4320 trucks sit only in battlegroups 2 and 3's HQ groups (the tank battalions); a stock test
# re-checks both, pinned at game build 201602 [[soviet-player-camp]].
SUPPLY: tuple[ForceRow, ...] = SOVIET_PLAYER_SUPPLY
# RJ's own defence-grade types, locked by type until the village falls: its Tunguska, its Su-24M and its Mi-24P. None
# is a start target, so the lock never holds back a card the assault needs.
START_LOCKS: tuple[str, ...] = ("Tunguska_2K22_SOV", "Su_24M_SOV", "Mi_24P_SOV")
# The fall's cards: the division's reserve, added once the locks lift. The Metis teams ride in BMP-2s: none of RJ's
# carriers pairs with them anywhere in stock; 8 Army General pawns pair them with the BMP-2, the start adds already
# bring it, and "X in a BMP-2" is the transport card seen working in play. Four more Konkurs-M teams in their BTR-80s
# hold the village against the Abrams. The heavy air defence against NATO's fighter sweeps is the division's own SAM,
# the 2K12 Kub (in the 79th Guards Tank Division's multiplayer deck and pawn, and Survivors' Soviet deck), bare as every
# stock pack holds it. The counts are the balance's (design 6.5): the reserve holds more than the fall's points buy.
RESERVE: tuple[ForceRow, ...] = (
    ForceRow(T80U_TANK, 15), ForceRow("T80U_CMD_SOV", 1), ForceRow("Tunguska_2K22_SOV", 2),
    ForceRow("Osa_9K33M3_SOV", 2), ForceRow("Mi_24V_AT_SOV", 6), ForceRow("Ka_50_SOV", 4), ForceRow("Su_25T_SOV", 2),
    ForceRow("Su_24M_clu_SOV", 2), ForceRow("BRDM_2_Konkurs_SOV", 6), ForceRow("MotRifles_Metis_SOV", 8, "BMP_2_SOV"),
    ForceRow(ATGM_TEAM, 4, ATGM_CARRIER), ForceRow("2K12_KUB_SOV", 2),
)
# The Soviet command units the player can field: RJ's own (T-80B CMD, BMP-1 CMD, and DShV CMD in its Mi-8s), the start
# adds' and the reserve's. The village falls only with one of them inside (design 5.1) [[zone-capture-command-units]];
# a stock test holds this to every *_CMD_* unit of RJ's deck, START_ADDS and RESERVE.
COMMAND_UNITS: tuple[str, ...] = ("T80BV_CMD_SOV", "BMP_2_CMD_SOV", "T80B_CMD_SOV", "BMP_1_CMD_SOV", "DShV_CMD_SOV",
                                  "T80U_CMD_SOV")


def top_up(targets: Iterable[ForceRow], held: Mapping[str, int]) -> tuple[ForceRow, ...]:
    """The cards that bring a deck holding `held` (unit -> count, every pack of the unit summed, carried or not) up to
    each target's count: each target's unit, count less what is held, and transport, in target order; a target the
    deck already meets adds nothing."""
    out = []
    for t in targets:
        more = t.count - held.get(t.unit, 0)
        if more > 0:
            out.append(ForceRow(t.unit, more, t.transport))
    return tuple(out)


def deck_units(cards: Iterable[ForceRow]) -> Counter:
    """unit -> count over `cards` (a transport's carrier is not counted: it is not a card of its own)."""
    out: Counter = Counter()
    for c in cards:
        out[c.unit] += c.count
    return out


# --------------------------------------------------------------------------- the force tables (design 6.2, 6.3)

FOB_UNIT = "FOB_SOV"

ROWS: tuple[ForceRow, ...] = tuple(
    # --- the player's, not in the deck (design 6.2): two FOBs in the Soviet box, pre-placed in the player's camp
    rows_of("fob", "Soviet", "FOB_W", "forward detachment FOB", ForceRow(FOB_UNIT, 1), fixed=True)
    + rows_of("fob", "Soviet", "FOB_E", "forward detachment FOB", ForceRow(FOB_UNIT, 1), fixed=True)
    # the division artillery, no longer pre-placed: each fire creates its battery at GUN_SPAWN, the cut's north-west
    # corner, in the player's allied camp (SovietAlly: the player's units never engage it), and removes it after (5.4)
    + rows_of("guns_heavy", "SovietAlly", "GUN_SPAWN", "division artillery: 2S7M battery",
              ForceRow("2S7M_Malka_SOV", 6), fixed=True)
    + rows_of("guns_rockets", "SovietAlly", "GUN_SPAWN", "division artillery: BM-27 battery",
              ForceRow("BM27_Uragan_SOV", 6), fixed=True)
    # --- NATO (design 6.3). The garrison is pre-placed in and around the village; both battalions are created by
    # the script (TS4b): battalion 1 in waves at both lane entries (its rows' spawn is the west entry, nominally),
    # battalion 2 at ASSEMBLY.
    + rows_of("garrison", "NATO", "VILLAGE", "West German Panzergrenadier company (-)",
              ForceRow("Panzergrenadier_IFV_RFA", 4), ForceRow("Marder_1A3_RFA", 3), ForceRow("ATteam_Milan_2_RFA", 2),
              ForceRow("Leopard_1A5_RFA", 3), ForceRow("Gepard_1A2_RFA", 1), ForceRow("Fernspaher_RFA", 1))
    + rows_of("bn1", "NATO", "NATO_ENTRY_W", "US armoured task force",
              ForceRow("M1A1HA_Abrams_US", 30), ForceRow("M1A1HA_Abrams_CMD_US", 1),
              ForceRow("M2A2_Bradley_IFV_US", 10), ForceRow("Rifles_half_AT4_US", 9, "M2A2_Bradley_IFV_US"))
    + rows_of("bn1_recon", "NATO", "NATO_ENTRY_W", "the task force's recon screen",
              ForceRow("M3A2_Bradley_CFV_US", 3), ForceRow("Scout_US", 3), ForceRow("OH58D_Kiowa_Warrior_US", 2))
    + rows_of("bn1_ad", "NATO", "NATO_ENTRY_W", "the task force's air defence",
              ForceRow("M163_PIVADS_US", 2), ForceRow("M48_Chaparral_MIM72F_US", 2), ForceRow("M998_Avenger_US", 2),
              ForceRow("MANPAD_Stinger_C_US", 3))
    + rows_of("bn2", "NATO", "ASSEMBLY", "West German Panzer battalion",
              ForceRow("Leopard_2A4_RFA", 28), ForceRow("Leopard_2A3_CMD_RFA", 1), ForceRow("Marder_1A3_RFA", 8),
              ForceRow("Panzergrenadier_IFV_RFA", 8, "Marder_1A3_RFA"), ForceRow("Gepard_1A2_RFA", 3),
              ForceRow("Marder_Roland_2_RFA", 2), ForceRow("Luchs_A1_RFA", 2))
)
GROUPS = tuple(dict.fromkeys(r.group for r in ROWS))
# Each battalion's tanks: the base of its "broken" share and its B1 / B2 counter (design 4.1: "N / 31").
BN1_TANKS = ("M1A1HA_Abrams_US", "M1A1HA_Abrams_CMD_US")
BN2_TANKS = ("Leopard_2A4_RFA", "Leopard_2A3_CMD_RFA")
# NATO's infantry types. No category constraint exists, so the division fire plan counts a box's vehicles as every NATO
# unit there but these (design 5.4).
NATO_INFANTRY = ("Panzergrenadier_IFV_RFA", "ATteam_Milan_2_RFA", "Fernspaher_RFA", "Rifles_half_AT4_US", "Scout_US",
                 "MANPAD_Stinger_C_US")


def force_rows(group: str) -> list[ForceRow]:
    """The ROWS of `group` at FORCE_SCALE, in table order."""
    return group_rows(ROWS, group, FORCE_SCALE)


# --------------------------------------------------------------------------- thresholds (design 6.4)

# Shares, Medium. The village falls at 25 % of the garrison left; a battalion is broken at 30 % of its tanks left.
# Difficulty (design 5.7) moves the garrison's share; TS4b's knobs pass their own share to threshold().
SHARES = {"fall": 0.25, "bn1": 0.30, "bn2": 0.30}


def threshold(name: str, rows: Iterable[ForceRow] | None = None, share: float | None = None) -> int:
    """The count of objective `name` ("fall", "bn1" or "bn2") over `rows` (ROWS at FORCE_SCALE when None), at its
    SHARES share or at `share`: "fall" is the garrison left in the village at which it falls, "bn1" and "bn2" the
    battalion's tanks left at which it is broken."""
    if name not in SHARES:
        raise KeyError(f"unknown threshold {name!r}; expected one of {sorted(SHARES)}")
    rows = list(scaled(ROWS, FORCE_SCALE) if rows is None else rows)
    if name == "fall":
        base = group_total(rows, "garrison")
    else:
        tanks = BN1_TANKS if name == "bn1" else BN2_TANKS
        base = sum(r.count for r in rows if r.group == name and r.unit in tanks)
    return share_count(SHARES[name] if share is None else share, base)
