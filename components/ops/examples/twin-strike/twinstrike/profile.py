"""Twin Strike's profile: Survivors re-keyed onto a cut of Twin Cities, with a Soviet player, under its own identity.

Twin Strike is a clone of the stock challenge Survivors (modkit.ops.profile.SURVIVORS), the template Open Door and the
probes clone too, moved onto the stock map Twin Cities (modkit.ops.maps.TWIN_CITIES): the Definition is re-keyed to
challenge_OperationTwinStrike and its own GUID, its map rows point at Twin Cities, and the menu tokens are renamed to
ts_*. Survivors' four camps stay (its CampList and SetDeck block), flipped to the stock Soviet-player shape
[[soviet-player-camp]] (modkit.ops.profile.SOVIET_PLAYER_CAMP_ROWS): the player Soviet on RedJuggernaut's deck, its AI
ally (the division artillery's camp) Soviet, the two Alliance 1 camps NATO. The menu's player deck follows
(SOVIET_PLAYER_DECK_SWAP).

The op plays on a cut of the stock layout SM_SU_3x3_TwinCities_03 (twinstrike.map.CUT): the cut ships its own
playable zone and AI grid [[ai-grid-tiles-playable-zone]], and the op its own start camera (twinstrike.map.CAMERA) in
place of the layout's camera paths, so the profile copies none of the map's Details. Its extra gates: the unit
database, no leftover template name, the cut's grid gate, the zone layout, the menu order against stock's and the
fire range of the batteries each fire creates north of the cut. Nothing
here resolves a path at import: the extraction and the game folder are read when a build runs.
"""
from __future__ import annotations

import math
import os
from typing import Sequence

from modkit.core import paths
from modkit.core.ndfbin import Value
from modkit.ops.gates import fire_range_gate, menu_order_gate, template_name_gate, unit_gate, zone_layout_gate
from modkit.ops.leveldesign import LD_FILE, ZONE_FILES, LdItem, derived_menu_order
from modkit.ops.maps import CAMERA_SHAPE_SOURCES, CUT_SHAPE_SOURCES, TWIN_CITIES
from modkit.ops.profile import (
    SOVIET_PLAYER_CAMP_ROWS, SOVIET_PLAYER_DECK_SWAP, SOVIET_PLAYER_SIDES, SURVIVORS, Content, ExtraGate, OpProfile,
)
from modkit.ops.rekey import ScalarEdit
from modkit.ops.script import PRODUCTION_DECK
from modkit.ops.shapes import Ctx as ShapesCtx
from modkit.ops.shapes import GRU_WORLD, camp_nodes
from modkit.ops.zones import rect_polygon
from twinstrike.map import CAMERA, CUT

# --------------------------------------------------------------------------- identity

SCENARIO = "challenge_OperationTwinStrike"
MOD_NAME = "TwinStrike"             # a folder another mod uses would replace it on install
GUID_NAMESPACE = "warno-twinstrike"  # scenario and item GUIDs are uuid5 names under it (modkit.ops.leveldesign)
FOLDER = "$/GDScript/TS"            # the script's own exports (Main, Variables, the end funnel) live under it
# Survivors' menu tokens (MapConfiguration Name and DescriptionTextElements), renamed. Every scenario's menu texts
# bind to one dictionary list, so a mod installed beside another needs its own tokens [[content-identity-unique]].
MENU_RENAMES = (("op13_name", "ts_name"), ("op13_order", "ts_order"), ("op13_headr", "ts_headr"),
                ("op13_cname", "ts_cname"), ("op13_recap", "ts_recap"), ("op13_vic", "ts_vic"), ("op13_def", "ts_def"))
MENU_TOKENS = tuple(new for _, new in MENU_RENAMES)

# The sides as Survivors' camps, flipped to the Soviet-player shape: Soviet (joueur, the player), SovietAlly (Allie,
# the division artillery), NATO (ordinateur_SOV: the garrison and both battalions) and NATO2 (ordinateur_DDR, unused).
CAMPS = SOVIET_PLAYER_SIDES
PLAYER = "Soviet"
CAMP_ROWS = SOVIET_PLAYER_CAMP_ROWS
# Each camp's PlayerName (Scripting/Localization). The string table holds these four tokens.
CAMP_TOKENS = {"joueur": "ts_csov", "Allie": "ts_cart", "ordinateur_DDR": "ts_cnato2", "ordinateur_SOV": "ts_cnato"}


def camp_index(side: str) -> int:
    """The CampList index of side `side`'s camp: a pre-placed unit's Camp (LevelDesign Spawn) and its Camp_<n>."""
    return [name for name, _, _ in CAMP_ROWS].index(CAMPS[side])


# --------------------------------------------------------------------------- re-keying and packs

# Twin Strike's menu order (OrderToChainMission), derived from its scenario GUID: every Operation active at once needs
# its own, Workshop mods included, and two with one stop the game at start [[content-identity-unique]].
MENU_ORDER = derived_menu_order(SCENARIO, GUID_NAMESPACE)
SCALAR_EDITS = (
    ScalarEdit("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission", Value(0x03, 130),
               Value(0x03, MENU_ORDER)),
    ScalarEdit("MapConfiguration", "TChallengeMapInfo", "Duration", Value(0x02, 3), Value(0x02, 1)),
)
MAP_SWAP_STRINGS = {"_3x3_Railway": TWIN_CITIES.name}     # ScenarioInfo.RootDatapackName
MAP_SWAP_TRANS = {"Railway": TWIN_CITIES.env_settings}    # import $/GraphicSettings/EnvironmentSettings/<map>
DECK_SWAP = SOVIET_PLAYER_DECK_SWAP                       # MapConfiguration LocalPlayerDeck

DICTIONARIES = ("SCENARIO_DEFINITION", "Scripting/Dialog", "Scripting/Localization")
SOURCE = SURVIVORS.source
# Survivors' Assets: what to do with each file (first matching fnmatch pattern wins). The reasons are written into
# MANIFEST.tsv.
ASSET_RULES = (
    (f"PC/Texture/{SOURCE}/MapPackAssets/Textures/*.tgv", "copy", "menu pictures (zero header checksum)"),
    ("AllPlatforms/*", "drop", "stale v2-era twin; every one has a newer prefix-less copy"),
    (f"Localisation/{SOURCE}/*", "drop", "replaced by the generated ts_* dictionaries"),
    (f"Map/Scenario/{SOURCE}/*", "drop", "Survivors voice; the generated script uses silence_5s.ogg"),
    ("PC/Python/*", "drop", "effetmap.xyz is not executed in 201602"),
    (f"PC/Texture/{SOURCE}/*", "drop", "Survivors dialog portraits; not referenced"),
    (f"PC/Video/{SOURCE}/*", "drop", "Survivors videos; not referenced"),
)
SHAPE_SOURCES = {  # generated file -> stock files whose shapes it may use, relative to the extraction
    "GDScript": ("scenarios/challenge_*/NDF/Scenarios/GDScript/challenge_*.ndfbin",),
    LD_FILE: ("scenarios/challenge_*/out/LevelDesign.ndfbin", "kreide_op/*/out/LevelDesign.ndfbin"),
    **{inner: (f"scenarios/*/{inner}", f"kreide_op/*/{inner}") for inner in ZONE_FILES.values()},
    **CUT_SHAPE_SOURCES,     # the cut's playable zone and AI grid
    **CAMERA_SHAPE_SOURCES,  # the start camera's path
}

# --------------------------------------------------------------------------- the script frame

TEMPLATES = SURVIVORS.objects       # Survivors' game rules (#114) and HUD hide/restore (#121, #296)
START_DELAY_S = 1.0                 # RootDescriptor WaitDuration before Main
# The buy menu opens on its BATTLEGROUP view (script.PRODUCTION_DECK), the one that showed the cards the script adds
# in the first play; every other content keeps stock's GROUPS view (script.PRODUCTION_TYPE) [[add-unit-to-deck]].
PRODUCTION_TYPE = PRODUCTION_DECK
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
    """Twin Strike's profile: Survivors on the cut of Twin Cities under GUID_NAMESPACE, with the Soviet player's deck,
    stock's trie import rule, the sides for the tier gate, the end funnel's export, the extra gates and the review
    overlay (OVERLAY)."""
    return OpProfile(
        template=SURVIVORS, guid_namespace=GUID_NAMESPACE,
        map_strings=MAP_SWAP_STRINGS, map_trans=MAP_SWAP_TRANS, map_details=TWIN_CITIES.details, map_copies=(),
        ground_z=TWIN_CITIES.ground_z, scalar_edits=SCALAR_EDITS, deck_swap=DECK_SWAP,
        dictionaries=DICTIONARIES, asset_rules=ASSET_RULES,
        import_rule="trie", shape_sources=SHAPE_SOURCES, player_camp=CAMPS[PLAYER], enemy_camp=CAMPS["NATO"],
        end_exports=(END_FUNNEL,),
        build_root=os.path.abspath(paths.build_root()), dumps=True, mod_id=0,
        extra_items=(CUT.items, CAMERA.items), extra_gates=EXTRA_GATES, extra_outputs=(overlay,),
    )


# The Name tag where each fire's battery is created (twinstrike.map's GUN_SPAWN), the one the fire-range gate holds.
GUN_SPAWN_TAG = "TS_GunSpawn"

# The gates Twin Strike adds to the driver's (gates only check: a build's bytes are the same with or without them):
# every unit it names exists in the game's unit database; no file it re-keys or generates still names the template;
# the shipped playable zone and AI grid are the cut's (CUT.gate(), in place of gates.grid_gate); read from the
# Details it ships, the zones and arrivals keep stock's layout rules; its menu order is no stock Operation's; and the
# batteries created at GUN_SPAWN_TAG stand outside the cut, out of the player's sight, with every target in range.
EXTRA_GATES: tuple[ExtraGate, ...] = (
    ExtraGate("units", unit_gate),
    ExtraGate("no-template-name", template_name_gate(SURVIVORS.source.removeprefix("challenge_"))),
    CUT.gate(),
    ExtraGate("zone-layout", zone_layout_gate),
    ExtraGate("menu-order", menu_order_gate),
    ExtraGate("fire-range", fire_range_gate(GUN_SPAWN_TAG, TWIN_CITIES, CAMPS[PLAYER])),
)
