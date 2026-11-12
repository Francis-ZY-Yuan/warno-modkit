"""Twin Strike's forces: the player's deck, the force tables, the scale knob and the share thresholds (design 6).

Pure data and arithmetic, in Open Door's style. Nothing here reads the game or the map: a row's spawn is a point name
of twinstrike.map's POINTS, and its units are bare stock names (`T80BV_SOV` for `Descriptor_Unit_T80BV_SOV`). The row
type is modkit.ops.models' ForceRow, a deck card's too (with its experience); the arithmetic and the deck types
(rows_of, scaled, group_rows, group_total, share_count; Platoon, DeckPage, deck_packs) are modkit.ops.forces'.

The player's deck (design 6.1) is the op's own, exported from its script and named by the player camp's SetDeck
[[op-exported-deck]]: DECK_PAGES is its buy menu's GROUPS view, page by page and platoon by platoon, every card of it
(unit, count, transport, experience). It is the one source: the deck's packs are derived from it (one pack per distinct
card key, its count the sum over its platoons: modkit.ops.forces.deck_packs), and so are the start's and the
reserve's cards (start_cards, reserve_cards). RESERVE_PAGES, the division's reserve, are locked from the start until
the village falls (op.load_deck) [[deck-page-lock]]. Every infantry card rides in a carrier, as stock fields each of
these squads. The deck is not scaled: FORCE_SCALE sizes the battle the script makes.

The pages and platoons are named by tokens of the op's own dictionaries, DECK_COMPANIES and DECK_PLATOONS
(twinstrike.strings), which the game reads as part of its COMPANIES and PLATOONS lists
[[deck-names-from-op-dictionaries]]. STOCK_NAMES is the fallback switch: on, every own token gives way to a stock
token of the same list (STOCK_PICKS) and the build ships neither dictionary.

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

from collections.abc import Iterable

from modkit.ops.forces import DeckPage, Platoon, group_rows, group_total, rows_of, scaled, share_count
from modkit.ops.models import ForceRow

FORCE_SCALE = 1.0       # design 6.4: 1x at release

# --------------------------------------------------------------------------- the player's deck (design 6.1)

# The ATGM team (game build 201602; a stock test re-derives both): the Soviet ATGM infantry team whose missile has the
# highest AT penetration among the teams a Soviet division's rules field (DivisionRules.ndf), the longer range on a tie.
# It is the Konkurs-M team, its 9M113M (late) 23 AP at 2,625 GRU, which the 27th Guards Motor Rifle Division fields in
# a UAZ-469 or a BTR-80: the BTR-80 is its armoured carrier. Every other team's missile is 20 AP or less.
ATGM_TEAM, ATGM_CARRIER = "ATteam_KonkursM_TTsko_SOV", "BTR_80_SOV"
# The reserve's tank: the T-80U variant whose ATGM has 25 AP, the T-80U obr. 1989 (its 9M119M Invar; the T-80U, the
# T-80UD and the T-80U command tank fire the 21 AP 9M119M Refleks). No command variant has the Invar, so the command
# tank stays the T-80U's. A stock test re-checks the AP.
T80U_TANK = "T80U_Obr89_SOV"
# The experience level RedJuggernaut's player deck (OP_BASE_RJ_Player, the 79th Guards Tank Division's) gives the types
# the first play fielded from it: its T-80BV, BRM-1, MT-LB Strela-10 and 2S1 packs are all at 1 (game build 210942; a
# stock test re-reads it). Those four keep it; every other card is at 0 but the reserve's Konkurs-M teams (KONKURS_XP).
RJ_XP = 1
# The reserve's Konkurs-M teams in their BTR-80s are the motor rifle company's card at another level: the game pools a
# deck's cards by (unit, transport, experience), so at 0 an open page would sell the locked page's teams. At 1 they are a
# card of their own [[op-exported-deck]].
KONKURS_XP = 1

# The deck's names: each page's and platoon's token, one token per distinct text (twinstrike.strings DECK_COMPANIES and
# DECK_PLATOONS hold the texts).
PG_HQ, PG_TANK, PG_MR, PG_RES_TANK, PG_RES_SUP = "ts_pg_hq", "ts_pg_tank", "ts_pg_mr", "ts_pg_rtk", "ts_pg_rsp"

# The deck's five pages (design 6.1), the order of battle, every card on a page: the forward detachment's HQ and
# support, its tank battalion and its motor rifle company, then the division's reserve, tanks and support (locked until
# the fall: RESERVE_PAGES). A platoon holds at most three card keys and a page at most six platoons (the game's group
# rules for an Operation's deck: five pages). Each pack's count is split over the platoons that hold it (the T-80BVs
# 4/3/3, the motor rifles 3/3/2, the T-80Us 3/4/4/4, the Metis teams 4/4), so every card shows in one platoon.
# - The HQ platoon holds the six command vehicles the fall can rest on [[zone-capture-command-units]]: two T-80BV
#   command tanks, a BMP-2 command vehicle and the three MT-LB command vehicles kept on 2026-11-11.
# - The engineers ride MT-LBs (RJ's deck fields the MT-LB, the 2S12's tractor; 5 Army General pawns pair them so), the
#   scouts UAZ-469s (the pairing of 170 of 198 pawns and of the 79th Guards Tank Division's own rule), the motor rifles
#   and the Metis teams BMP-2s (8 Army General pawns pair the Metis teams with the BMP-2, the transport card seen
#   working in play), the Konkurs-M teams their BTR-80s.
# - The Ka-29s are gunship cards: the Ka-29 carries no troops in the game (it has no transporter module; the decks gate
#   would refuse it as a carrier). The deck has no airborne infantry.
# - The supply: the stock Soviet supply truck and the medium supply helicopter.
# - The reserve: T-80U obr. 1989 tanks and their command tank, Konkurs-armed BRDM-2s, Metis teams in BMP-2s, four more
#   Konkurs-M teams to hold the village against the Abrams, the division's air defence (the 2K12 Kub against NATO's
#   fighter sweeps: the 79th Guards Tank Division's own SAM, bare as every stock pack holds it), attack helicopters
#   and strike aircraft. The counts are the balance's (design 6.5): the reserve holds more than the fall's points buy.
DECK_PAGES: tuple[DeckPage, ...] = (
    DeckPage(PG_HQ, (
        Platoon("ts_pl_cmd", (ForceRow("T80BV_CMD_SOV", 2), ForceRow("BMP_2_CMD_SOV", 1), ForceRow("MTLB_CMD_SOV", 3))),
        Platoon("ts_pl_rec", (ForceRow("BRM_1_SOV", 2, xp=RJ_XP), ForceRow("Scout_SOV", 2, "UAZ_469_SOV"))),
        Platoon("ts_pl_adp", (ForceRow("ZSU_23_Shilka_SOV", 2), ForceRow("MTLB_Strela10_SOV", 1, xp=RJ_XP))),
        Platoon("ts_pl_art", (ForceRow("2S1_Gvozdika_SOV", 4, xp=RJ_XP),)),
        Platoon("ts_pl_sup", (ForceRow("Ural_4320_SOV", 4), ForceRow("Mi_8TZ_SOV", 2))),
        Platoon("ts_pl_hel", (ForceRow("Ka_29_SOV", 4),)),
    )),
    DeckPage(PG_TANK, (
        Platoon("ts_pl_t1", (ForceRow("T80BV_SOV", 4, xp=RJ_XP),)),
        Platoon("ts_pl_t2", (ForceRow("T80BV_SOV", 3, xp=RJ_XP),)),
        Platoon("ts_pl_t3", (ForceRow("T80BV_SOV", 3, xp=RJ_XP),)),
    )),
    DeckPage(PG_MR, (
        Platoon("ts_pl_mr1", (ForceRow("MotRifles_SOV", 3, "BMP_2_SOV"),)),
        Platoon("ts_pl_mr2", (ForceRow("MotRifles_SOV", 3, "BMP_2_SOV"),)),
        Platoon("ts_pl_mr3", (ForceRow("MotRifles_SOV", 2, "BMP_2_SOV"),)),
        Platoon("ts_pl_atgm", (ForceRow(ATGM_TEAM, 2, ATGM_CARRIER),)),
        Platoon("ts_pl_eng", (ForceRow("Engineers_Flam_SOV", 2, "MTLB_transp_SOV"),)),
    )),
    DeckPage(PG_RES_TANK, (
        Platoon("ts_pl_hq1", (ForceRow("T80U_CMD_SOV", 1), ForceRow(T80U_TANK, 3))),
        Platoon("ts_pl_t2", (ForceRow(T80U_TANK, 4),)),
        Platoon("ts_pl_t3", (ForceRow(T80U_TANK, 4),)),
        Platoon("ts_pl_t4", (ForceRow(T80U_TANK, 4),)),
        Platoon("ts_pl_at", (ForceRow("BRDM_2_Konkurs_SOV", 6),)),
    )),
    DeckPage(PG_RES_SUP, (
        Platoon("ts_pl_me1", (ForceRow("MotRifles_Metis_SOV", 4, "BMP_2_SOV"),)),
        Platoon("ts_pl_me2", (ForceRow("MotRifles_Metis_SOV", 4, "BMP_2_SOV"),)),
        Platoon("ts_pl_atgm", (ForceRow(ATGM_TEAM, 4, ATGM_CARRIER, xp=KONKURS_XP),)),
        Platoon("ts_pl_ad", (ForceRow("Tunguska_2K22_SOV", 2), ForceRow("Osa_9K33M3_SOV", 2),
                             ForceRow("2K12_KUB_SOV", 2))),
        Platoon("ts_pl_atk", (ForceRow("Mi_24V_AT_SOV", 6), ForceRow("Ka_50_SOV", 4))),
        Platoon("ts_pl_str", (ForceRow("Su_25T_SOV", 2), ForceRow("Su_24M_clu_SOV", 2))),
    )),
)
# The division's reserve: pages 3 and 4, by their 0-based place in DECK_PAGES (LockCombatGroup's index), locked from
# the start until the village falls; the fall adds no card [[deck-page-lock]].
RESERVE_PAGES: tuple[int, ...] = (3, 4)
# The Soviet command units the player can field: every *_CMD_* card of the deck (a test holds it so). The village falls
# only with one of them inside (design 5.1) [[zone-capture-command-units]].
COMMAND_UNITS: tuple[str, ...] = ("T80BV_CMD_SOV", "BMP_2_CMD_SOV", "MTLB_CMD_SOV", "T80U_CMD_SOV")

# The deck's own name, DeckName: a stock token of the game's UNITS list, the division's own name ("79-YA GV. TANK.
# DIV.", the DivisionName of SOV_79_Gds_Tank_challenge). The menu's deck stays RedJuggernaut's (profile.DECK_SWAP),
# so the battle probably never shows it.
DECK_NAME = "ABQKCQLERY"
# The deck's division: RedJuggernaut's, the 79th Guards Tank Division's Operation division (GFX/Division).
DECK_DIVISION = "Descriptor_Deck_Division_SOV_79_Gds_Tank_challenge"

# The fallback switch [[deck-names-from-op-dictionaries]]. Off (the default), the pages and platoons carry the op's own
# names. On, each own token gives way to its STOCK_PICKS token, one of the game's own COMPANIES or PLATOONS words, and
# the build ships neither of the op's deck dictionaries nor the resources that append them (profile.dictionary_lists):
# the retry if the first launch shows a dictionary error naming a ts_* token. build.py --stock-names sets it.
STOCK_NAMES = False
# The stock picks (game build 210942), each in every language the game ships: the closest English name of the same
# role in the game's COMPANIES or PLATOONS list. A page name in Russian (Rota Komandovaniya, Aviapodderzhka) gives way
# to the English one of its role; the two tank pages take RedJuggernaut's own two tank battalions (1-1-17-y GvTP,
# 2-1-17-y GvTP: no COMPANIES text says reserve); platoons take stock's numbered platoons where stock uses them in tank
# and infantry pages alike, and the English "Engineer Platoon" over the only stock deck's Polish one.
STOCK_PICKS: dict[str, str] = {
    PG_HQ: "IJOVDIJCWA",         # Company HQ
    PG_TANK: "YHHKVXFYTB",       # 1-1-17-y GvTP (RedJuggernaut's first tank battalion)
    PG_MR: "cha_5",              # Inf. Company
    PG_RES_TANK: "BIUSBBTLXM",   # 2-1-17-y GvTP (RedJuggernaut's second tank battalion)
    PG_RES_SUP: "cha_1",         # Air Support
    "ts_pl_cmd": "SUJBJHQBBH",   # Platoon HQ
    "ts_pl_rec": "EBAXRQFWNO",   # Recon Platoon
    "ts_pl_adp": "HBLUTIMQXB",   # AA Platoon
    "ts_pl_art": "KPNJIRFMVK",   # Artillery Platoon
    "ts_pl_sup": "SRHWTUYLYQ",   # Logistics Group
    "ts_pl_hel": "UQOOFMYADI",   # Aero platoon
    "ts_pl_t1": "AEHXPSCGSH",    # 1st Platoon
    "ts_pl_t2": "TXLIVWUPSM",    # 2nd Platoon
    "ts_pl_t3": "WAKIQBNMIP",    # 3rd Platoon
    "ts_pl_t4": "JFDLGUGPAH",    # 4th Platoon
    "ts_pl_hq1": "AEHXPSCGSH",   # 1st Platoon
    "ts_pl_mr1": "AEHXPSCGSH",   # 1st Platoon
    "ts_pl_mr2": "TXLIVWUPSM",   # 2nd Platoon
    "ts_pl_mr3": "WAKIQBNMIP",   # 3rd Platoon
    "ts_pl_me1": "AEHXPSCGSH",   # 1st Platoon
    "ts_pl_me2": "TXLIVWUPSM",   # 2nd Platoon
    "ts_pl_atgm": "MMISGNOMQO",  # AT Platoon
    "ts_pl_at": "MMISGNOMQO",    # AT Platoon
    "ts_pl_eng": "JXQPRZMRTN",   # Engineer Platoon
    "ts_pl_ad": "HBLUTIMQXB",    # AA Platoon
    "ts_pl_atk": "UQOOFMYADI",   # Aero platoon
    "ts_pl_str": "OBWKKGSZTP",   # 1st Flight
}


def deck_pages(stock_names: bool | None = None) -> tuple[DeckPage, ...]:
    """DECK_PAGES as the deck ships: with the op's own names, or with STOCK_PICKS' in their place when `stock_names`
    (STOCK_NAMES when None)."""
    if not (STOCK_NAMES if stock_names is None else stock_names):
        return DECK_PAGES
    return tuple(DeckPage(STOCK_PICKS[page.name], tuple(Platoon(STOCK_PICKS[p.name], p.cards) for p in page.platoons))
                 for page in DECK_PAGES)


def page_cards(pages: Iterable[int]) -> tuple[ForceRow, ...]:
    """Every card of DECK_PAGES' pages `pages` (0-based), in page and platoon order."""
    return tuple(card for k in pages for platoon in DECK_PAGES[k].platoons for card in platoon.cards)


def start_cards() -> tuple[ForceRow, ...]:
    """The cards on sale from the start: every card of the pages RESERVE_PAGES leaves open."""
    return page_cards(k for k in range(len(DECK_PAGES)) if k not in RESERVE_PAGES)


def reserve_cards() -> tuple[ForceRow, ...]:
    """The division's reserve: every card of RESERVE_PAGES, on sale once the village falls."""
    return page_cards(RESERVE_PAGES)


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
