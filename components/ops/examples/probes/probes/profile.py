"""The probes' profile: Survivors re-keyed onto Geisa, under the probes' own identity.

Every probe is a clone of the stock challenge Survivors (modkit.ops.profile.SURVIVORS) moved onto the stock map Geisa
(modkit.ops.maps.GEISA): the Definition is re-keyed to the probe's scenario id and GUID, its map rows point at Geisa,
and the player's deck and menu tokens are swapped. Survivors' four camps stay (its CampList and SetDeck block), with
three sides in use: the player (NATO, camp joueur), an AI-controlled ally (Decoys, Allie) and the enemy (PACT,
ordinateur_SOV).

The values here are the probes' record: a probe changes only when it is meant to. The default identity is probe 1's
(challenge_OpenDoor in OpenDoorOps); a probe may carry its own (spike2 does). A probe outside the frozen group also
carries its own menu order (MENU_ORDER). Mod names never change.
"""
from __future__ import annotations

import os
from typing import Callable

from modkit.core import paths
from modkit.core.ndfbin import Value
from modkit.ops.gates import menu_order_gate, unit_gate
from modkit.ops.leveldesign import LD_FILE, ZONE_FILES
from modkit.ops.maps import GEISA
from modkit.ops.profile import SURVIVORS, SURVIVORS_PLAYER_DECK, Content, ExtraGate, OpProfile, Script
from modkit.ops.rekey import ScalarEdit
from modkit.ops.shapes import Ctx as ShapesCtx
from modkit.ops.shapes import camp_nodes
from modkit.ops.strings import Table
from probes.geisa import MAP

# --------------------------------------------------------------------------- identity

SCENARIO = "challenge_OpenDoor"
MOD_NAME = "OpenDoorOps"            # a folder another mod uses would replace it on install
GUID_NAMESPACE = "warno-opendoor"   # scenario and item GUIDs are uuid5 names under it (modkit.ops.leveldesign)
FOLDER = "$/GDScript/OD"            # the script's own exports (Main, Variables, the end funnel) live under it

# The sides as Survivors' camps (GDScript export names under $/GDScript/RootDescriptor). ordinateur_DDR is kept
# (Survivors' CampList and its SetDeck stay four) but unused.
CAMPS = {"NATO": "joueur", "Decoys": "Allie", "PACT": "ordinateur_SOV"}
PLAYER = "NATO"
PLAYER_DECK = "OP_BASE_BB_Player"
# Survivors' camps in CampList order: export name, TGDVariableCamp scalars before PlayerName (S#109-#112), SetDeck id
# (S#117-#120; the player gets PLAYER_DECK, the other three keep Survivors').
CAMP_ROWS = (
    ("joueur", (("AllianceStyle", 0x02, 3),), PLAYER_DECK),
    ("Allie", (("AllianceStyle", 0x02, 3),), "OP_NORTH_SURV_BEL"),
    ("ordinateur_DDR", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)), "OP_NORTH_SURV_DDR"),
    ("ordinateur_SOV", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)), "OP_NORTH_SURV_SOV"),
)
# Each camp's PlayerName (Scripting/Localization). Every probe's string table holds these four tokens.
CAMP_TOKENS = {"joueur": "od_cnato", "Allie": "od_cdecoy", "ordinateur_DDR": "od_cddr", "ordinateur_SOV": "od_csov"}

# Survivors' menu tokens (MapConfiguration Name and DescriptionTextElements), renamed. Every scenario's menu texts
# bind to one dictionary list, so two mods installed side by side need their own tokens.
LOC_RENAMES = {
    "op13_name": "od_name",
    "op13_order": "od_order",
    "op13_headr": "od_headr",
    "op13_cname": "od_cname",
    "op13_recap": "od_recap",
    "op13_vic": "od_vic",
    "op13_def": "od_def",
}
MENU_TOKENS = tuple(LOC_RENAMES.values())


def menu_renames(prefix: str) -> tuple[tuple[str, str], ...]:
    """LOC_RENAMES with another token prefix: op13_name -> <prefix>_name, ..."""
    return tuple((old, f"{prefix}_{new.split('_', 1)[1]}") for old, new in LOC_RENAMES.items())


# The Operations menu order (MapConfiguration's OrderToChainMission). Every Operation active at once needs its own, and
# two with one stop the game at start [[content-identity-unique]]. The frozen group, empty, spike, spike_safe and
# spike2, keeps MENU_ORDER (1001, Open Door's too) and its bytes: these builds are regression baselines, rebuilt and
# compared byte for byte, so their menu order never moves, and only one of them, or Open Door, is active at a time.
# They never ship: publishing one means moving it to its derived order (modkit.ops.leveldesign.derived_menu_order)
# first. Every other probe carries its derived order (content(menu_order=...)).
MENU_ORDER = 1001


def scalar_edits(order: int) -> tuple[ScalarEdit, ...]:
    """Survivors' MapConfiguration scalars as a probe changes them: the menu order (OrderToChainMission 130) to `order`,
    and the Duration 3 to 1."""
    return (
        ScalarEdit("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission", Value(0x03, 130),
                   Value(0x03, order)),
        ScalarEdit("MapConfiguration", "TChallengeMapInfo", "Duration", Value(0x02, 3), Value(0x02, 1)),
    )


SCALAR_EDITS = scalar_edits(MENU_ORDER)
MAP_SWAP_STRINGS = {"_3x3_Railway": GEISA.name}      # ScenarioInfo.RootDatapackName
MAP_SWAP_TRANS = {"Railway": GEISA.env_settings}     # import $/GraphicSettings/EnvironmentSettings/<map>
DECK_SWAP = {SURVIVORS_PLAYER_DECK: PLAYER_DECK}     # MapConfiguration LocalPlayerDeck

DICTIONARIES = ("SCENARIO_DEFINITION", "Scripting/Dialog", "Scripting/Localization")
SOURCE = SURVIVORS.source
# Survivors' Assets: what to do with each file (first matching fnmatch pattern wins).
ASSET_RULES = (
    (f"PC/Texture/{SOURCE}/MapPackAssets/Textures/*.tgv", "copy", "menu pictures (zero header checksum)"),
    ("AllPlatforms/*", "drop", "stale v2-era twin; every one has a newer prefix-less copy"),
    (f"Localisation/{SOURCE}/*", "drop", "replaced by the generated od_* dictionaries"),
    (f"Map/Scenario/{SOURCE}/*", "drop", "Survivors voice; the generated script uses silence_5s.ogg"),
    ("PC/Python/*", "drop", "effetmap.xyz is not executed in 201602"),
    (f"PC/Texture/{SOURCE}/*", "drop", "Survivors dialog portraits; not referenced"),
    (f"PC/Video/{SOURCE}/*", "drop", "Survivors videos; not referenced"),
)
SHAPE_SOURCES = {  # generated file -> stock files whose shapes it may use, relative to the extraction
    "GDScript": ("scenarios/challenge_*/NDF/Scenarios/GDScript/challenge_*.ndfbin",),
    LD_FILE: ("scenarios/challenge_*/out/LevelDesign.ndfbin", "kreide_op/*/out/LevelDesign.ndfbin"),
    **{inner: (f"scenarios/*/{inner}", f"kreide_op/*/{inner}") for inner in ZONE_FILES.values()},
}

# The script frame (modkit.ops.script): Survivors' templates and the probes' timings.
TEMPLATES = SURVIVORS.objects
START_DELAY_S = 1.0                  # RootDescriptor WaitDuration before Main
PLAYER_INCOME = 150                  # SetIncomeToTeam (DelayedRetribution #109)
REFRESH_S = 2.0                      # AddAllCampUnitsToUnitGroup(joueur) period (HoldUntilRelieved #99)
REFRESH_EXPORT = f"{FOLDER}/JoueurRefresh"
END_FUNNEL = f"{FOLDER}/EndFunnel"   # the one ending node (gates.check_end_funnel)
END_RACE = f"{FOLDER}/EndRace"       # probe 2's ending race, the only other TriggerEndGame pair


def default_out(name: str) -> str:
    """The default --out: probes/<name> in the build folder (modkit.core.paths.build_root, which is also where a
    rebuild may delete a previous output). Read when a build runs, never at import."""
    return os.path.join(os.path.abspath(paths.build_root()), "probes", name)


class Ctx(ShapesCtx):
    """modkit.ops.shapes.Ctx with the probes' camps, sides and GUID namespace, over `items` keyed to `scenario`."""

    def __init__(self, items, scenario: str = SCENARIO) -> None:
        super().__init__(camp_nodes(CAMP_ROWS, CAMP_TOKENS), CAMPS, PLAYER, items, scenario, GUID_NAMESPACE, FOLDER)


def content(name: str, items, script: Script | None, strings: Table, menu_tokens: tuple[str, ...], *,
            scenario: str = SCENARIO, mod_name: str = MOD_NAME,
            menu_renames: tuple[tuple[str, str], ...] = tuple(LOC_RENAMES.items()), menu_order: int | None = None,
            **kw) -> Content:
    """A probe's Content, with probe 1's identity unless it carries its own, and its own menu order `menu_order`
    (Content.scalar_edits) or else the profile's MENU_ORDER, the frozen group's."""
    return Content(name, tuple(items), script, strings, menu_tokens, scenario=scenario, mod_name=mod_name,
                   menu_renames=menu_renames, scalar_edits=None if menu_order is None else scalar_edits(menu_order),
                   **kw)


def profile() -> OpProfile:
    """The probes' profile: Survivors on Geisa under GUID_NAMESPACE, stock's trie import rule, the sides for the tier
    gate, the end funnel, the unit-database and menu-order gates and the review overlay (od_overlay.png)."""
    return OpProfile(
        template=SURVIVORS, guid_namespace=GUID_NAMESPACE,
        map_strings=MAP_SWAP_STRINGS, map_trans=MAP_SWAP_TRANS, map_details=GEISA.details, map_copies=GEISA.copies,
        ground_z=GEISA.ground_z, scalar_edits=SCALAR_EDITS, deck_swap=DECK_SWAP,
        dictionaries=DICTIONARIES, asset_rules=ASSET_RULES,
        import_rule="trie", shape_sources=SHAPE_SOURCES, player_camp=CAMPS["NATO"], enemy_camp=CAMPS["PACT"],
        end_exports=(END_FUNNEL, END_RACE),
        build_root=os.path.abspath(paths.build_root()), dumps=True, mod_id=0,
        extra_gates=(ExtraGate("units", unit_gate), ExtraGate("menu-order", menu_order_gate)),
        extra_outputs=(MAP.map.overlay_output("od_overlay.png"),),
    )


ContentFactory = Callable[[], Content]
