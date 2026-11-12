"""Twin Strike's profile: Survivors re-keyed onto a cut of Twin Cities, with a Soviet player, under its own identity.

Twin Strike is a clone of the stock challenge Survivors (modkit.ops.profile.SURVIVORS), the template Open Door and the
probes clone too, moved onto the stock map Twin Cities (modkit.ops.maps.TWIN_CITIES): the Definition is re-keyed to
challenge_OperationTwinStrike and its own GUID, its map rows point at Twin Cities, and the menu tokens are renamed to
ts_*. Survivors' four camps stay (its CampList and SetDeck block), flipped to the stock Soviet-player shape
[[soviet-player-camp]] (modkit.ops.profile.SOVIET_PLAYER_CAMP_ROWS), with the player's row on the op's own deck
(CAMP_ROWS: its SetDeck names DECK_ID, the deck the op's script exports [[op-exported-deck]]): the player Soviet, its
AI ally (the division artillery's camp) Soviet, the two Alliance 1 camps NATO. The menu's player deck, which the game
resolves before the op's script loads, stays a stock Soviet deck, RedJuggernaut's (SOVIET_PLAYER_DECK_SWAP), and so do
its emblems: RedJuggernaut's, in place of Survivors' (MENU_ART). The deck's page and platoon names ship in two
dictionaries of the op's own that the game reads as part of its COMPANIES and PLATOONS lists (DECK_LISTS)
[[deck-names-from-op-dictionaries]]. Its map picture is its own card, generated at build time (CARD_TITLE,
CARD_ZONES, CARD_STICKERS).

The op plays on a cut of the stock layout SM_SU_3x3_TwinCities_03 (twinstrike.map.CUT): the cut ships its own
playable zone and AI grid [[ai-grid-tiles-playable-zone]], and the op its own start camera (twinstrike.map.CAMERA) in
place of the layout's camera paths, so the profile copies none of the map's Details. Its extra gates: the unit
database, no leftover template name, the cut's grid gate, the zone layout, the menu order against stock's and the
fire range of the batteries each fire creates in the allied camp. Nothing here resolves a path at import: the
extraction and the game folder are read when a build runs.
"""
from __future__ import annotations

import math
import os
from typing import Sequence

from modkit.core import paths
from modkit.core.ndfbin import Value
from modkit.ops import menuart
from modkit.ops.gates import fire_range_gate, menu_order_gate, template_name_gate, unit_gate, zone_layout_gate
from modkit.ops.leveldesign import LD_FILE, ZONE_FILES, LdItem, derived_deck_identifier, derived_menu_order
from modkit.ops.maps import CAMERA_SHAPE_SOURCES, CUT_SHAPE_SOURCES, TWIN_CITIES
from modkit.ops.models import AssetRule
from modkit.ops.profile import (
    SOVIET_PLAYER_CAMP_ROWS, SOVIET_PLAYER_DECK_SWAP, SOVIET_PLAYER_SIDES, SURVIVORS, Content, ExtraGate, OpProfile,
)
from modkit.ops.rekey import ScalarEdit
from modkit.ops.script import BRICK_FORCE_HIDE
from modkit.ops.script import PRODUCTION_TYPE as GROUPS_VIEW
from modkit.ops.shapes import Ctx as ShapesCtx
from modkit.ops.shapes import DECK_SHAPE_SOURCES, GRU_WORLD, camp_nodes, with_deck
from modkit.ops.zones import rect_polygon
from twinstrike import forces
from twinstrike.map import CAMERA, CUT, NATO_DZ, POINTS, SOV_DZ, VILLAGE_CZ

# --------------------------------------------------------------------------- identity

SCENARIO = "challenge_OperationTwinStrike"
MOD_NAME = "TwinStrike"             # a folder another mod uses would replace it on install
GUID_NAMESPACE = "warno-twinstrike"  # scenario and item GUIDs are uuid5 names under it (modkit.ops.leveldesign)
FOLDER = "$/GDScript/TS"            # the script's own exports (Main, Variables, the end funnel) live under it
# Survivors' menu tokens (MapConfiguration Name and DescriptionTextElements), renamed. Every scenario's menu texts
# bind to one dictionary list, so a mod installed beside another needs its own tokens [[content-identity-unique]].
MENU_RENAMES = {"op13_name": "ts_name", "op13_order": "ts_order", "op13_headr": "ts_headr", "op13_cname": "ts_cname",
                "op13_recap": "ts_recap", "op13_vic": "ts_vic", "op13_def": "ts_def"}
MENU_TOKENS = tuple(MENU_RENAMES.values())
# The menu's titles (MissionName and TitreObjectifs), the only tokens gate 1's 30-unit title convention holds
# (Content.menu_tokens). The other five take stock's form and lengths, the briefing over 1,000 units
# (strings.toml).
TITLE_TOKENS = ("ts_name", "ts_cname")

# The player's deck, the op's own [[op-exported-deck]]: its DeckIdentifier, hash-derived so no stock deck or other
# mod's has it [[derive-cross-mod-ids-from-a-hash]], and where the script exports it (twinstrike.op.player_deck).
DECK_ID = derived_deck_identifier(SCENARIO, GUID_NAMESPACE, "TS", "Player")
DECK_EXPORT = f"{FOLDER}/PlayerDeck"

# The sides as Survivors' camps, flipped to the Soviet-player shape: Soviet (joueur, the player), SovietAlly (Allie,
# the division artillery), NATO (ordinateur_SOV: the garrison and both battalions) and NATO2 (ordinateur_DDR, unused).
# The camp rows are the shared Soviet-player rows with the player's SetDeck on the op's own deck (DECK_ID), every other
# row as it is (NATO2's stock AI deck OP_BASE_RJ_IA among them).
CAMPS = SOVIET_PLAYER_SIDES
PLAYER = "Soviet"
CAMP_ROWS = with_deck(SOVIET_PLAYER_CAMP_ROWS, CAMPS[PLAYER], DECK_ID)
# Each camp's PlayerName (Scripting/Localization). The string table holds these four tokens.
CAMP_TOKENS = {"joueur": "ts_csov", "Allie": "ts_cart", "ordinateur_DDR": "ts_cnato2", "ordinateur_SOV": "ts_cnato"}


def camp_index(side: str) -> int:
    """The CampList index of side `side`'s camp: a pre-placed unit's Camp (LevelDesign Spawn) and its Camp_<n>."""
    return [row.name for row in CAMP_ROWS].index(CAMPS[side])


# --------------------------------------------------------------------------- re-keying and packs

# Twin Strike's menu order (OrderToChainMission), derived from its scenario GUID: every Operation active at once needs
# its own, Workshop mods included, and two with one stop the game at start [[content-identity-unique]].
MENU_ORDER = derived_menu_order(SCENARIO, GUID_NAMESPACE)
SCALAR_EDITS = (
    ScalarEdit("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission", Value(0x03, 130),
               Value(0x03, MENU_ORDER)),
    ScalarEdit("MapConfiguration", "TChallengeMapInfo", "Duration", Value(0x02, 3), Value(0x02, 1)),
)
# Twin Strike's Steam Workshop item ID, written to Config.ini's ID: the item its first upload (2026-11-12) created. The
# upload writes the item's ID into the installed Config.ini only, so it is set here: a rebuild keeps it, and the next
# upload updates the same item instead of creating a second one.
WORKSHOP_ID = 3838528915
MAP_SWAP_STRINGS = {"_3x3_Railway": TWIN_CITIES.name}     # ScenarioInfo.RootDatapackName
MAP_SWAP_TRANS = {"Railway": TWIN_CITIES.env_settings}    # import $/GraphicSettings/EnvironmentSettings/<map>
# MapConfiguration's LocalPlayerDeck: the out-game screens resolve it before the op's script loads, so it stays a stock
# Soviet deck (RedJuggernaut's); the player camp's SetDeck replaces it at load (CAMP_ROWS) [[soviet-player-camp]].
DECK_SWAP = SOVIET_PLAYER_DECK_SWAP

# The scenario's three dictionaries, and the deck's two (twinstrike.strings), which the game reads as part of its own
# COMPANIES and PLATOONS lists: MapConfiguration appends each to its list (OpProfile.dictionary_lists)
# [[deck-names-from-op-dictionaries]]. The stock-names fallback (forces.STOCK_NAMES) ships neither.
SCENARIO_DICTIONARIES = ("SCENARIO_DEFINITION", "Scripting/Dialog", "Scripting/Localization")
DECK_LISTS = {"DECK_COMPANIES": "COMPANIES", "DECK_PLATOONS": "PLATOONS"}


def dictionaries(stock_names: bool) -> tuple[str, ...]:
    """The dictionaries a build packs: the scenario's, then the deck's unless the deck carries stock names."""
    return SCENARIO_DICTIONARIES + (() if stock_names else tuple(DECK_LISTS))
SOURCE = SURVIVORS.source
# Survivors' Assets: what to do with each file (first matching fnmatch pattern wins). The reasons are written into
# MANIFEST.tsv.
ASSET_RULES = (
    AssetRule(f"PC/Texture/{SOURCE}/MapPackAssets/Textures/*.tgv", "copy", "menu pictures (zero header checksum)"),
    AssetRule("AllPlatforms/*", "drop", "stale v2-era twin; every one has a newer prefix-less copy"),
    AssetRule(f"Localisation/{SOURCE}/*", "drop", "replaced by the generated ts_* dictionaries"),
    AssetRule(f"Map/Scenario/{SOURCE}/*", "drop", "Survivors voice; the generated script uses silence_5s.ogg"),
    AssetRule("PC/Python/*", "drop", "effetmap.xyz is not executed in 201602"),
    AssetRule(f"PC/Texture/{SOURCE}/*", "drop", "Survivors dialog portraits; not referenced"),
    AssetRule(f"PC/Video/{SOURCE}/*", "drop", "Survivors videos; not referenced"),
)
# The menu card (the MapTexture, modkit.ops.menuart): Survivors' card, its caption retitled, its map Twin Cities' cut
# (map.CUT), and on it the two sides' ground at the start as stock marks it, in minimap px from map.py:
# - red, the Soviet side: the deployment box (map.SOV_DZ) and the assault fields south of it, down to 6 px short of
#   the village's north edge (y 331.6) so the two outlines stay apart. The polaroid covers the box's west part; the
#   star stands where the red shows, east of the polaroid at the visible red's mid-height (its centroid, x 155, y 251,
#   moved 17 px east so the sticker clears the polaroid);
# - blue, the NATO side: the village's command zone (map.VILLAGE_CZ, x 6.125-132.125, y 331.6-421.6), the ground
#   south of it and NATO's deployment band (map.NATO_DZ), one area; the NATO badge on the village (POINTS["VILLAGE"]).
CARD_TITLE = "TWIN STRIKE"
_VILLAGE = [TWIN_CITIES.world_to_px(p) for p in VILLAGE_CZ]
_V_X0, _V_Y0 = min(x for x, _ in _VILLAGE), min(y for _, y in _VILLAGE)
_V_X1 = max(x for x, _ in _VILLAGE)
CARD_ZONES = (
    ([(SOV_DZ[0], SOV_DZ[1]), (SOV_DZ[2], SOV_DZ[1]), (SOV_DZ[2], _V_Y0 - 6), (SOV_DZ[0], _V_Y0 - 6)], "red"),
    ([(_V_X0, _V_Y0), (_V_X1, _V_Y0), (_V_X1, NATO_DZ[1]), (NATO_DZ[2], NATO_DZ[1]), (NATO_DZ[2], NATO_DZ[3]),
      (NATO_DZ[0], NATO_DZ[3])], "blue"),
)
CARD_STICKERS = (("SOV", (172, 251)), ("NATO", POINTS["VILLAGE"]))
# The menu's emblems from RedJuggernaut, the stock Operation of the 79th Guards Tank Division, the player's division
# [[soviet-player-camp]], in place of Survivors' British ones (OpProfile.menu_art): its corner logo (the red star), its
# country flag (the Soviet Union's) and its end-of-game blazon (the division's Guards badge). The map picture is the
# op's own card, generated at build time.
MENU_ART = {"CornerLogo": "challenge_RedJuggernaut", "MissionCountry": "challenge_RedJuggernaut",
            "EndgameBlazon": "challenge_RedJuggernaut",
            "MapTexture": menuart.card_picture(CARD_TITLE, CUT, CARD_ZONES, CARD_STICKERS)}
SHAPE_SOURCES = {  # generated file -> stock files whose shapes it may use, relative to the extraction
    # the stock scripts, and the game's own decks for the deck the script exports [[op-exported-deck]]
    "GDScript": ("scenarios/challenge_*/NDF/Scenarios/challenge_*/GDScript.txn", *DECK_SHAPE_SOURCES),
    LD_FILE: ("scenarios/challenge_*/out/LevelDesign.ndfbin", "kreide_op/*/out/LevelDesign.ndfbin"),
    **{inner: (f"scenarios/*/{inner}", f"kreide_op/*/{inner}") for inner in ZONE_FILES.values()},
    **CUT_SHAPE_SOURCES,     # the cut's playable zone and AI grid
    **CAMERA_SHAPE_SOURCES,  # the start camera's path
}

# --------------------------------------------------------------------------- the script frame

TEMPLATES = SURVIVORS.objects       # Survivors' game rules (#114) and HUD hide/restore (#121, #296)
START_DELAY_S = 1.0                 # RootDescriptor WaitDuration before Main
# The buy menu is held in its GROUPS view, the deck's pages, with the view switch force-hidden: stock's pairing
# wherever it locks a page (Marauders #107 ChangeProductionType Groups and #108 ForceDisplayUIElement hiding all with
# the switch force-hidden, then #162 showing the buy menu with the switch still force-hidden; RunningTheGauntlet #168,
# #169, #176). The frame writes that trio: ChangeProductionType PRODUCTION_TYPE in the setup, the template's hide-all
# (its switch ForceHide) and the HUD restore with PROD_MENU_SWITCH [[deck-page-lock]]. The deck view would pool the
# locked pages' cards with the rest.
PRODUCTION_TYPE = GROUPS_VIEW
PROD_MENU_SWITCH = BRICK_FORCE_HIDE
REFRESH_S = 2.0                    # AddAllCampUnitsToUnitGroup(joueur) period (HoldUntilRelieved #99)
REFRESH_EXPORT = f"{FOLDER}/JoueurRefresh"
END_FUNNEL = f"{FOLDER}/EndFunnel"  # the one ending node (gates.check_end_funnel), the mission's (TS4b)


def default_out(name: str) -> str:
    """The default --out: twin-strike/<name> in the build folder (modkit.core.paths.build_root, which is also where a
    rebuild may delete a previous output). Read when a build runs, never at import."""
    return os.path.join(os.path.abspath(paths.build_root()), "twin-strike", name)


class Ctx(ShapesCtx):
    """modkit.ops.shapes.Ctx with Twin Strike's camps, sides and GUID namespace, over `items` keyed to `scenario`
    (the content's: the binding gate fails tags made for another scenario)."""

    def __init__(self, items: Sequence[LdItem], scenario: str = SCENARIO) -> None:
        super().__init__(camp_nodes(CAMP_ROWS, CAMP_TOKENS), CAMPS, PLAYER, items, scenario, GUID_NAMESPACE, FOLDER)


# --------------------------------------------------------------------------- the review picture

OVERLAY = "ts_overlay.png"
RING_SIDES = 24     # a detector circle drawn as a polygon of this many sides


def overlay(content: Content, out_dir: str) -> str:
    """A review output (OpProfile.extra_outputs): Twin Cities' Preview with every item of the content as a mark, and
    as rings the cut, every zone polygon, every detector circle and each arrival's Start -> End. Never shipped."""
    to_px = TWIN_CITIES.world_to_px
    cut = list(map(to_px, rect_polygon(CUT.box())))
    rings = [cut]
    for it in content.items:
        if it.polygon:
            rings.append([to_px(p) for p in it.polygon])
        if it.radius_gru is not None:
            r = it.radius_gru * GRU_WORLD
            rings.append([to_px((it.x + r * math.cos(2 * math.pi * k / RING_SIDES),
                                 it.y + r * math.sin(2 * math.pi * k / RING_SIDES))) for k in range(RING_SIDES + 1)])
        if it.start is not None:
            rings.append([to_px(it.start), to_px(it.end)])
    marks = {it.name: to_px((it.x, it.y)) for it in content.items}
    return TWIN_CITIES.render_overlay(os.path.join(out_dir, OVERLAY), marks, rings)


def profile() -> OpProfile:
    """Twin Strike's profile: Survivors on the cut of Twin Cities under GUID_NAMESPACE, with the menu's stock Soviet
    deck, the deck's dictionaries appended to the game's COMPANIES and PLATOONS lists (none with the stock-names
    fallback, forces.STOCK_NAMES, read when it is called), stock's trie import rule, the sides for the tier gate, the
    end funnel's export, the extra gates and the review overlay (OVERLAY)."""
    stock_names = forces.STOCK_NAMES
    return OpProfile(
        template=SURVIVORS, guid_namespace=GUID_NAMESPACE,
        map_strings=MAP_SWAP_STRINGS, map_trans=MAP_SWAP_TRANS, map_details=TWIN_CITIES.details, map_copies=(),
        ground_z=TWIN_CITIES.ground_z, scalar_edits=SCALAR_EDITS, deck_swap=DECK_SWAP,
        dictionaries=dictionaries(stock_names), asset_rules=ASSET_RULES, menu_art=MENU_ART,
        dictionary_lists={} if stock_names else DECK_LISTS,
        import_rule="trie", shape_sources=SHAPE_SOURCES, player_camp=CAMPS[PLAYER], enemy_camp=CAMPS["NATO"],
        end_exports=(END_FUNNEL,),
        build_root=os.path.abspath(paths.build_root()), dumps=True, mod_id=WORKSHOP_ID,
        extra_items=(CUT.items, CAMERA.items), extra_gates=EXTRA_GATES, extra_outputs=(overlay,),
    )


# The Name tag where each fire's battery is created (twinstrike.map's GUN_SPAWN), the one the fire-range gate holds.
GUN_SPAWN_TAG = "TS_GunSpawn"

# The gates Twin Strike adds to the driver's (gates only check: a build's bytes are the same with or without them):
# every unit it names exists in the game's unit database; no file it re-keys or generates still names the template;
# the shipped playable zone and AI grid are the cut's (CUT.gate(), in place of gates.grid_gate); read from the
# Details it ships, the zones and arrivals keep stock's layout rules; its menu order is no stock Operation's; and the
# batteries created at GUN_SPAWN_TAG are in the player's alliance, so the player's units never engage them, with every
# target in range from where they stand (the driver's own gate 3 holds every created unit inside the playable zone).
EXTRA_GATES: tuple[ExtraGate, ...] = (
    ExtraGate("units", unit_gate),
    ExtraGate("no-template-name", template_name_gate(SURVIVORS.source.removeprefix("challenge_"))),
    CUT.gate(),
    ExtraGate("zone-layout", zone_layout_gate),
    ExtraGate("menu-order", menu_order_gate),
    ExtraGate("fire-range", fire_range_gate(GUN_SPAWN_TAG, CAMPS[PLAYER])),
)
