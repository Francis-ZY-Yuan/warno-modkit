"""Open Door's profile: Survivors re-keyed onto Geisa, under Open Door's own identity.

Open Door is a clone of the stock challenge Survivors (modkit.ops.profile.SURVIVORS) moved onto the stock map Geisa
(modkit.ops.maps.GEISA): the Definition is re-keyed to challenge_OperationOpenDoor and its own GUID, its map rows
point at Geisa, the player's deck becomes the 3rd Armored Division's operation deck, and the menu tokens are renamed
to o3_*. Survivors' four camps stay (its CampList and SetDeck block), with three sides in use: the player (NATO,
camp joueur), an AI-controlled ally (Decoys, Allie) and the enemy (PACT, ordinateur_SOV).

The build (modkit.ops.build) runs every shared gate. Open Door's settings in them: stock's trie import rule, its
sides for the tier gate, its one end funnel, five extra gates (EXTRA_GATES: the unit database, no leftover template
name, Geisa's AI grid and the zone layout, both by stock's rules, and the menu order against stock's) and a review
picture of every item on Geisa (od_overlay.png). Nothing here resolves a path at import: the extraction and the game
folder are read when a build runs.
"""
from __future__ import annotations

import os
from typing import Sequence

from modkit.core import ndfbin, paths
from modkit.core.ndfbin import Value
from modkit.ops import script as ops_script
from modkit.ops.gates import grid_gate, menu_order_gate, template_name_gate, unit_gate, zone_layout_gate
from modkit.ops.graph import Node
from modkit.ops.leveldesign import LD_FILE, ZONE_FILES, LdItem
from modkit.ops.maps import GEISA
from modkit.ops.models import CampRow
from modkit.ops.profile import SURVIVORS, SURVIVORS_PLAYER_DECK, ExtraGate, OpProfile
from modkit.ops.rekey import ScalarEdit
from modkit.ops.shapes import Ctx as ShapesCtx
from modkit.ops.shapes import camp_nodes
from opendoor.map import MAP

# --------------------------------------------------------------------------- identity

SCENARIO = "challenge_OperationOpenDoor"
MOD_NAME = "OpenDoor"               # a folder another mod uses would replace it on install
GUID_NAMESPACE = "warno-opendoor"   # scenario and item GUIDs are uuid5 names under it (modkit.ops.leveldesign)
FOLDER = "$/GDScript/OD"            # the script's own exports (Main, Variables, the end funnel) live under it
VARIABLES = f"{FOLDER}/Variables"
# Survivors' menu tokens (MapConfiguration Name and DescriptionTextElements), renamed. Every scenario's menu texts
# bind to one dictionary list, so a mod installed beside another needs its own tokens.
MENU_RENAMES = (("op13_name", "o3_name"), ("op13_order", "o3_order"), ("op13_headr", "o3_headr"),
                ("op13_cname", "o3_cname"), ("op13_recap", "o3_recap"), ("op13_vic", "o3_vic"), ("op13_def", "o3_def"))
MENU_TOKENS = tuple(new for _, new in MENU_RENAMES)

# The sides as Survivors' camps (GDScript export names under $/GDScript/RootDescriptor). ordinateur_DDR is kept
# (Survivors' CampList and its SetDeck stay four) but unused.
CAMPS = {"NATO": "joueur", "Decoys": "Allie", "PACT": "ordinateur_SOV"}
PLAYER = "NATO"
PLAYER_DECK = "OP_BASE_BB_Player"
# Survivors' camps in CampList order: export name, TGDVariableCamp scalars before PlayerName (S#109-#112), SetDeck id
# (S#117-#120; the player gets PLAYER_DECK, the other three keep Survivors').
CAMP_ROWS: tuple[CampRow, ...] = (
    CampRow("joueur", (("AllianceStyle", 0x02, 3),), PLAYER_DECK),
    CampRow("Allie", (("AllianceStyle", 0x02, 3),), "OP_NORTH_SURV_BEL"),
    CampRow("ordinateur_DDR", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)),
            "OP_NORTH_SURV_DDR"),
    CampRow("ordinateur_SOV", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)),
            "OP_NORTH_SURV_SOV"),
)
# Each camp's PlayerName (Scripting/Localization). The string table holds these four tokens.
CAMP_TOKENS = {"joueur": "od_cnato", "Allie": "od_cdecoy", "ordinateur_DDR": "od_cddr", "ordinateur_SOV": "od_csov"}

# --------------------------------------------------------------------------- re-keying and packs

# OrderToChainMission 1001 is Open Door's menu order: every Operation active at once needs its own
# [[content-identity-unique]]. Open Door shares it with the probes' frozen group (probes.profile.MENU_ORDER), regression
# baselines whose builds never change, so it is never active beside one of them. Publishing Open Door means moving it to
# its derived order (modkit.ops.leveldesign.derived_menu_order) first.
SCALAR_EDITS = (
    ScalarEdit("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission", Value(0x03, 130), Value(0x03, 1001)),
    ScalarEdit("MapConfiguration", "TChallengeMapInfo", "Duration", Value(0x02, 3), Value(0x02, 1)),
)
MAP_SWAP_STRINGS = {"_3x3_Railway": GEISA.name}      # ScenarioInfo.RootDatapackName
MAP_SWAP_TRANS = {"Railway": GEISA.env_settings}     # import $/GraphicSettings/EnvironmentSettings/<map>
DECK_SWAP = {SURVIVORS_PLAYER_DECK: PLAYER_DECK}     # MapConfiguration LocalPlayerDeck

DICTIONARIES = ("SCENARIO_DEFINITION", "Scripting/Dialog", "Scripting/Localization")
SOURCE = SURVIVORS.source
# Survivors' Assets: what to do with each file (first matching fnmatch pattern wins). The reasons are written into
# MANIFEST.tsv.
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
    "GDScript": ("scenarios/challenge_*/NDF/Scenarios/challenge_*/GDScript.txn",),
    LD_FILE: ("scenarios/challenge_*/out/LevelDesign.ndfbin", "kreide_op/*/out/LevelDesign.ndfbin"),
    **{inner: (f"scenarios/*/{inner}", f"kreide_op/*/{inner}") for inner in ZONE_FILES.values()},
}

# --------------------------------------------------------------------------- the script frame

TEMPLATES = SURVIVORS.objects       # Survivors' game rules (#114) and HUD hide/restore (#121, #296)
START_DELAY_S = 1.0                 # RootDescriptor WaitDuration before Main
PLAYER_INCOME = 150                 # SetIncomeToTeam (DelayedRetribution #109)
REFRESH_S = 2.0                     # AddAllCampUnitsToUnitGroup(joueur) period (HoldUntilRelieved #99)
REFRESH_EXPORT = f"{FOLDER}/JoueurRefresh"
END_FUNNEL = f"{FOLDER}/EndFunnel"  # the one ending node (gates.check_end_funnel): every TriggerEndGame is under it
END_RACE = f"{FOLDER}/EndRace"      # an ending race the funnel may sit beside (Open Door has none)


def default_out(name: str) -> str:
    """The default --out: open-door/<name> in the build folder (modkit.core.paths.build_root, which is also where a
    rebuild may delete a previous output). Read when a build runs, never at import."""
    return os.path.join(os.path.abspath(paths.build_root()), "open-door", name)


class Ctx(ShapesCtx):
    """modkit.ops.shapes.Ctx with Open Door's camps, sides and GUID namespace, over `items` keyed to `scenario` (the
    content's: the binding gate fails tags made for another scenario)."""

    def __init__(self, items: Sequence[LdItem], scenario: str = SCENARIO) -> None:
        super().__init__(camp_nodes(CAMP_ROWS, CAMP_TOKENS), CAMPS, PLAYER, items, scenario, GUID_NAMESPACE, FOLDER)


def deploy_phase(tpl: ndfbin.NdfBin, joueur: Node, groupe_joueur: Node, command_zones: Sequence[Node], points: int,
                 hint: str | None = None) -> ops_script.DeployPhase:
    """modkit.ops.script.deploy_phase with Survivors' templates and Open Door's income and refresh loop: `points`, the
    GdItems tags of the command zones the player owns at start (`command_zones`) and the LDHint token shown until the
    battle is launched (`hint`). Pair it with hud_restore(tpl, deploy=True)."""
    return ops_script.deploy_phase(tpl, TEMPLATES, joueur, groupe_joueur, command_zones, points=points,
                                   income=PLAYER_INCOME, hint=hint, refresh_export=REFRESH_EXPORT, refresh_s=REFRESH_S)


def hud_restore(tpl: ndfbin.NdfBin, deploy: bool, prod_menu_switch: int = ops_script.BRICK_FORCE_HIDE
                ) -> list[tuple[str, Value]]:
    """modkit.ops.script.hud_restore with Survivors' templates: S#296 minus ShowMinimap; with the deployment phase
    (`deploy`), the launch button, buy menu and top bar. `prod_menu_switch`: BRICK_FORCE_HIDE keeps S#296's
    ShowProdMenuSwitchMenuTypeButtons; BRICK_DEFAULT leaves it out."""
    return ops_script.hud_restore(tpl, TEMPLATES, deploy, prod_menu_switch)


def profile() -> OpProfile:
    """Open Door's profile: Survivors on Geisa under GUID_NAMESPACE, stock's trie import rule, the sides for the tier
    gate, the end funnel, the unit-database and no-template-name gates and the review overlay (od_overlay.png)."""
    return OpProfile(
        template=SURVIVORS, guid_namespace=GUID_NAMESPACE,
        map_strings=MAP_SWAP_STRINGS, map_trans=MAP_SWAP_TRANS, map_details=GEISA.details, map_copies=GEISA.copies,
        ground_z=GEISA.ground_z, scalar_edits=SCALAR_EDITS, deck_swap=DECK_SWAP,
        dictionaries=DICTIONARIES, asset_rules=ASSET_RULES,
        import_rule="trie", shape_sources=SHAPE_SOURCES, player_camp=CAMPS["NATO"], enemy_camp=CAMPS["PACT"],
        end_exports=(END_FUNNEL, END_RACE),
        build_root=os.path.abspath(paths.build_root()), dumps=True, mod_id=0,
        extra_gates=EXTRA_GATES, extra_outputs=(MAP.map.overlay_output("od_overlay.png"),),
    )


# The gates Open Door adds to the driver's (gates only check: a build's bytes are the same with or without them):
# every unit it names exists in the game's unit database; no file it re-keys or generates still names the template;
# read from the Details it ships, Geisa's AI grid spans the playable zone and the zones and arrivals keep stock's
# layout rules; and its menu order is no stock Operation's.
EXTRA_GATES: tuple[ExtraGate, ...] = (
    ExtraGate("units", unit_gate),
    ExtraGate("no-template-name", template_name_gate(SURVIVORS.source.removeprefix("challenge_"))),
    ExtraGate("grid", grid_gate),
    ExtraGate("zone-layout", zone_layout_gate),
    ExtraGate("menu-order", menu_order_gate),
)
