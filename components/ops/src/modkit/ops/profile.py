"""What one Operation mod is, for the build driver (``modkit.ops.build``): its profile and its content.

* A ``Template`` is the stock scenario an op is cloned from (``SURVIVORS``): where its packs lie in the extraction,
  its GUID and menu-token prefix, the Definition kinds re-keyed and dropped, and the script objects a generated
  script copies.
* An ``OpProfile`` holds everything that differs between two ops built from one template: the GUID namespace, the map
  the op moves to, the re-keying edits, the dictionaries, asset rules and menu art, the gates' settings, how the mod
  folder is written, and the extension points (extra packs, loose files, Config.ini and manifest rows, gates and
  review outputs), plus the reviewed-pending gate failures.
* A ``Content`` is one build of an op: its LevelDesign items, its script, its string table and its identity (scenario
  id and mod folder).
* A clone of Survivors whose player is Soviet takes the stock Soviet-player camp shape: ``SOVIET_PLAYER_CAMP_ROWS``,
  ``SOVIET_PLAYER_SIDES`` and ``SOVIET_PLAYER_DECK_SWAP`` (on ``RJ_PLAYER_DECK``, in place of
  ``SURVIVORS_PLAYER_DECK``), and adds ``SOVIET_PLAYER_SUPPLY`` to the player's deck at load (``ForceRow`` cards, the
  AddUnitToDeck card shape).

Nothing here reads a module setting: two profiles build side by side in one process. Paths are relative to the stock
extraction (``modkit.core.paths.extracted_root``) and resolved when a build runs.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Callable, Iterable, Mapping, NamedTuple

from modkit.core import ndfbin, paths
from modkit.core.gates import check
from modkit.core.models import Pending, StringTable
from modkit.core.packaging import check_mod_id
from modkit.ops.graph import Node
from modkit.ops.items import Item
from modkit.ops.leveldesign import LdItem
from modkit.ops.models import CampRow, ForceRow
from modkit.ops.rekey import TXN, ScalarEdit, def_path
from modkit.ops.script import BRICK_FORCE_HIDE, Templates

PACKS = ("Definition", "Details", "Assets")   # the scenario packs every build writes, in this order
STOCK_ASSETS = "scenarios/{}"   # a stock challenge's Assets folder in the extraction, by scenario id (STOCK_PATHS)


def extracted(rel: str) -> str:
    """`rel` ('/'-separated, relative to the stock extraction) as a path; raises paths.NotConfigured without one."""
    return os.path.join(str(paths.extracted_root()), *rel.split("/"))


@dataclass(frozen=True)
class Template:
    """The stock scenario an op is cloned from, and what of it the clone keeps."""
    source: str                        # its scenario id
    guid: bytes                        # its scenario GUID (MapConfiguration, ScenarioInfo)
    token_prefix: str                  # its menu tokens' prefix: every such token must be renamed
    definition: str                    # its Definition pack folder, relative to the extraction
    details: str                       # its Details pack folder
    assets: str                        # its Assets pack folder
    kinds: tuple[str, ...]             # the Definition kinds shipped (re-keyed, or the generated GDScript)
    dropped: tuple[tuple[str, str], ...]  # the Definition kinds dropped (.txn, .txn.tag, .dbg), with the manifest's why
    global_tokens: tuple[str, ...]     # stock loc tokens its files use that a mod uses without shipping them
    objects: Templates                 # the script objects a generated script copies scalars from
    asset_subtrees: tuple[str, ...]    # the Assets folder's top-level folders
    # Its MapConfiguration's menu order (TChallengeMapInfo.OrderToChainMission). A content whose scalar edits move none
    # gets its derived order in its place (modkit.ops.leveldesign.derived_menu_order); None: no default.
    menu_order: int | None = None

    def path(self, which: str) -> str:
        """The `which` ('definition', 'details' or 'assets') folder in the extraction."""
        return extracted(getattr(self, which))

    def gdscript(self) -> str:
        """The template's GDScript, the input of a content's script."""
        return os.path.join(self.path("definition"), *def_path("GDScript", TXN, self.source).split("/"))


# Survivors, the stock challenge both example ops start from: a four-camp scenario whose Definition, Details and
# Assets the extraction holds whole (modkit.ops.STOCK_PATHS). Object indices of its 210942 GDScript: #116 the game
# rules, #123 the HUD hide before LoadingDone, #298 the HUD restore (minus ShowMinimap: the minimap stays visible);
# 201602's S#114, S#121 and S#296, two places on since 210942 put a SplashSoundDescriptor and its stream at #108.
# Its Trophy (TrophyDef) is dropped: a clone earns no stock trophy.
SURVIVORS = Template(
    source="challenge_Survivors",
    guid=bytes.fromhex("24e6ba7d1b026372ad74e66f87ba611d"),
    token_prefix="op13_",
    definition="kreide_op/challenge_Survivors_Definition",
    details="kreide_op/challenge_Survivors_Details",
    assets="scenarios/challenge_Survivors",
    kinds=("GDScript", "MapConfiguration", "ScenarioInfo", "ScenarioLoader"),
    dropped=(("TrophyDef", "Trophy is dropped (C.1)"),),
    global_tokens=("SI_NEXT", "GRL_ATTP", "GRL_ATTPB", "GRL_ATTPE"),
    objects=Templates((116, "TGDSpecificTacticalGameRules", ()), (123, "TGDDescriptorForceDisplayUIElement", ()),
                      (298, "TGDDescriptorForceDisplayUIElement", ("ShowMinimap",))),
    asset_subtrees=("AllPlatforms", "Localisation", "Map", "PC"),
    menu_order=130,
)

# Survivors' player deck: MapConfiguration's LocalPlayerDeck, and the joueur camp's SetDeck (S#117). A clone whose
# player has another deck swaps it (OpProfile.deck_swap, Content.deck_swap) and sets the camp's SetDeck to match.
SURVIVORS_PLAYER_DECK = "OP_NORTH_SURV_PLAYER"
"""Survivors' own player deck: the LocalPlayerDeck a clone's deck swap replaces."""

# --------------------------------------------------------------------------- a Soviet player in a clone of Survivors

# The stock Soviet-player camp shape [[soviet-player-camp]]. RedJuggernaut and Gotterdammerung put the player in
# Alliance 0, AllianceStyle 4 (REDFOR) and Nationalite 1 (PACT), on OP_BASE_RJ_Player (or OP_BASE_GOT_Player), and the
# enemy camps in Alliance 1, AllianceStyle 3 (BLUFOR) and NATO (Nationalite 0, the default). A clone of Survivors
# keeps its four camps in CampList order, flipped to that shape; probe 3's nuke_sov built it first.
RJ_PLAYER_DECK = "OP_BASE_RJ_Player"
"""RedJuggernaut's player deck (79th Guards Tank Division): a Soviet player's stock deck [[soviet-player-camp]]."""

# Survivors' camps as CampRow rows (export name, TGDVariableCamp scalars before PlayerName, SetDeck id), in CampList
# order. The two Alliance 0 camps are REDFOR and PACT: the player on RJ_PLAYER_DECK and its AI ally
# on Survivors' own Soviet deck. The two Alliance 1 camps are BLUFOR and NATO, on RedJuggernaut's NATO AI deck and
# Survivors' Belgian deck. Nationalite 0 (NATO) is left out, as Survivors' rows leave it; so is Alliance 0 (the
# player's alliance, so the deployment zones and arrivals stay where they are), while Alliance 1 is written
# [[soviet-player-camp]].
SOVIET_PLAYER_CAMP_ROWS: tuple[CampRow, ...] = (
    CampRow("joueur", (("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)), RJ_PLAYER_DECK),
    CampRow("Allie", (("AllianceStyle", 0x02, 4), ("Nationalite", 0x02, 1)), "OP_NORTH_SURV_SOV"),
    CampRow("ordinateur_DDR", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 3)), "OP_BASE_RJ_IA"),
    CampRow("ordinateur_SOV", (("Alliance", 0x03, 1), ("AllianceStyle", 0x02, 3)), "OP_NORTH_SURV_BEL"),
)
"""Survivors' four camps with a Soviet player, in CampList order (CampRow rows) [[soviet-player-camp]]."""

# The sides of SOVIET_PLAYER_CAMP_ROWS (a side's name -> its camp's export name, shapes.Ctx's sides): the player,
# Soviet, and its AI ally in Alliance 0; the two NATO camps in Alliance 1 [[soviet-player-camp]].
SOVIET_PLAYER_SIDES: Mapping[str, str] = MappingProxyType(
    {"Soviet": "joueur", "SovietAlly": "Allie", "NATO": "ordinateur_SOV", "NATO2": "ordinateur_DDR"})
"""The sides of a Soviet-player clone of Survivors, by camp export name [[soviet-player-camp]]."""

# MapConfiguration's LocalPlayerDeck swap that goes with SOVIET_PLAYER_CAMP_ROWS: the menu's player deck follows the
# player camp's SetDeck (OpProfile.deck_swap, or Content.deck_swap for one content of several) [[soviet-player-camp]].
SOVIET_PLAYER_DECK_SWAP: Mapping[str, str] = MappingProxyType({SURVIVORS_PLAYER_DECK: RJ_PLAYER_DECK})
"""The LocalPlayerDeck swap of a Soviet-player clone of Survivors: Survivors' deck -> RJ's [[soviet-player-camp]]."""

# RJ_PLAYER_DECK has no supply helicopter, and its supply trucks sit only in its two tank battalions' HQ groups
# [[soviet-player-camp]]. A Soviet player on it gets these at load (AddUnitToDeck [[add-unit-to-deck]]; ForceRow
# cards for modkit.ops.shapes.add_card): the stock Soviet supply truck and the medium supply helicopter.
SOVIET_PLAYER_SUPPLY: tuple[ForceRow, ...] = (ForceRow("Ural_4320_SOV", 4), ForceRow("Mi_8TZ_SOV", 2))
"""The Soviet player's supply, added at load: Ural-4320 trucks x4, Mi-8TZ helicopters x2 [[soviet-player-camp]]."""

Script =Callable[[ndfbin.NdfBin], tuple[list[Node], list[Node]]]  # the template's GDScript in, (roots, exports) out


@dataclass(frozen=True)
class Sources:
    """How a build names what it generates: the source column of MANIFEST.tsv and the review dump (fixture) of each
    generated ndfbin. Keys are 'GDScript' (the content's script) or a Details inner path (LevelDesign, a zone file);
    a key left out gets the driver's wording ('generated (content script)', 'generated (content items)', 'generated
    (content zone items)') and the fixture '<file stem>.txt'. `dictionary` names each packed dictionary, formatted
    with {name} (the dictionary), {lang} and {column} ('Chinese' for SC, else 'English')."""
    labels: Mapping[str, str] = field(default_factory=dict)
    fixtures: Mapping[str, str] = field(default_factory=dict)
    dictionary: str = "strings[{name!r}] {column}"

    def label(self, key: str) -> str:
        label = self.labels.get(key)
        if label is not None:
            return label
        return ("generated (content script)" if key == "GDScript" else
                "generated (content items)" if key.endswith("LevelDesign.ndfbin") else "generated (content zone items)")

    def fixture(self, key: str) -> str:
        fixture = self.fixtures.get(key)
        return fixture if fixture is not None else key.rsplit("/", 1)[-1].replace(".ndfbin", "") + ".txt"

    def dic(self, name: str, lang: str) -> str:
        return self.dictionary.format(name=name, lang=lang, column="Chinese" if lang == "SC" else "English")


@dataclass(frozen=True)
class Content:
    """One build of an op: what it is made of, and the identity it installs under."""
    name: str
    items: tuple[LdItem, ...]          # every LevelDesign item, deployment and command zones included
    script: Script | None              # None: ship the template's GDScript re-keyed (the gates read it decoded)
    strings: StringTable               # exactly the profile's dictionaries
    menu_tokens: tuple[str, ...]       # SCENARIO_DEFINITION tokens held to the 30-unit title limit (a convention)
    # GDScript shapes gate 2 admits although no stock file uses them: a property the native class has that the content
    # exercises on purpose, as (class, property, value tag, reference target|None). The class is admitted too.
    extra_shapes: tuple[tuple[str, str, int, str | None], ...] = ()
    scenario: str = field(kw_only=True)    # the scenario id: Definition paths, Assets folder, pack names, GUIDs
    mod_name: str = field(kw_only=True)    # the mod folder (Config.ini name); two contents with one replace each other
    # Objectives (gates.objective_name) reviewed to hold up the Sequential they sit in until they resolve (gate 3).
    blocking_objectives: tuple[str, ...] = ()
    # The template's menu tokens -> the content's (MapConfiguration). Every scenario's menu texts bind to one
    # dictionary list, so two mods installed side by side need their own tokens or they show one title.
    menu_renames: tuple[tuple[str, str], ...] = field(kw_only=True)
    # Player reinforcement locations that end in a command zone only, on purpose: tiers the script opens and closes
    # by the zone's owner (gate 3 tiers, gates.check_tiers).
    tiered_arrivals: tuple[str, ...] = ()
    # The buy menu's switch at the script's HUD restore (script.PROD_MENU_SWITCH; gate 3 checks the script ships it).
    prod_menu_switch: int = BRICK_FORCE_HIDE
    sources: Sources = Sources()       # how the manifest and the dumps name the generated files
    # MapConfiguration STRG entries swapped (LocalPlayerDeck) in place of the profile's deck_swap; None: the profile's.
    # For a content whose player has another deck than its siblings' (a camp flipped to the other coalition).
    deck_swap: Mapping[str, str] | None = field(kw_only=True, default=None)
    # Definition scalar edits in place of the profile's scalar_edits; None: the profile's. For a content whose
    # MapConfiguration differs from its siblings': its own Operations menu order (OrderToChainMission), which every
    # Operation active at once needs [[content-identity-unique]].
    scalar_edits: tuple[ScalarEdit, ...] | None = field(kw_only=True, default=None)


class ExtraPack(NamedTuple):
    """A pack beyond the profile's own: <scenario>_<name>.dat, holding the items `plan(content)` gives (each with
    Item.pack == name). It is written after the profile's packs and listed in the manifest in that order."""
    name: str
    plan: Callable[[Content], Iterable[Item]]


class ExtraGate(NamedTuple):
    """A gate beyond the driver's own, run on the planned items after gate 3: `check(items, content)` raises
    CheckError on a broken rule and returns a line for the build log. `name` keys reviewed_pending."""
    name: str
    check: Callable[[list[Item], Content], str]


LooseFiles = Callable[[Content], Iterable[Item]]   # loose files under the mod folder (each with Item.pack == 'Loose')
ExtraItems = Callable[[Content], Iterable[Item]]   # more entries for the profile's own packs (Item.pack one of them)
ReviewOutput = Callable[[Content, str], str]       # writes a review file into the out folder; returns a log line
MenuPicture = Callable[[Content], tuple[bytes, str]]   # a generated menu picture: its bytes and its MANIFEST source


@dataclass(frozen=True)
class OpProfile:
    """Everything that differs between two Operation mods built from one template (see the module docstring)."""
    template: Template
    guid_namespace: str                     # scenario and item GUIDs are uuid5 names under it (leveldesign)
    # --- the map the op moves to (all empty/the template's own to keep the template's map)
    map_strings: Mapping[str, str]          # whole STRG entries swapped (ScenarioInfo.RootDatapackName)
    map_trans: Mapping[str, str]            # whole TRAN entries swapped (the EnvironmentSettings import)
    map_details: str                        # the map's Details pack folder, relative to the extraction
    map_copies: tuple[str, ...]             # its Details files shipped byte for byte (PlayableZone, AI zones, ...)
    ground_z: float                         # the z of generated zone areas (the map's playable-zone Center z)
    # --- re-keying
    scalar_edits: tuple[ScalarEdit, ...]    # Definition scalars changed (MapConfiguration's mission order, ...)
    deck_swap: Mapping[str, str]            # MapConfiguration STRG entries swapped (LocalPlayerDeck)
    # --- the Assets pack
    dictionaries: tuple[str, ...]           # the dictionaries a content's string table holds, packed per language
    asset_rules: tuple[tuple[str, str, str], ...]  # the template's Assets: (fnmatch, copy|drop, why), first wins
    # --- the gates
    import_rule: str                        # gates.check_canonical's import tree rule: 'trie' (stock) or 'preorder'
    shape_sources: Mapping[str, tuple[str, ...]]  # generated inner path ('GDScript': the script) -> stock globs
    player_camp: str                        # the camp (export name) whose zones open a tier (gate 3 tiers)
    enemy_camp: str                         # the camp handed a tier's zone to close it
    end_exports: tuple[str, ...]            # the end funnel's export paths (gates.check_end_funnel); () for none
    # --- writing
    build_root: str                         # the folder a rebuild may delete a previous output in (and nothing else)
    dumps: bool                             # write dumps/<file>.txt, the typed dump of each generated ndfbin
    packs: tuple[str, ...] = PACKS          # always PACKS (checked): a build plans all three; extra_packs adds more
    # Ship the template's Details whole, byte for byte, instead of a generated LevelDesign, its zone files and the map
    # copies (the content then has no LevelDesign items): a clone that keeps the template's map and layout.
    details_from_template: bool = False
    # Config.ini's ID, the mod's Steam Workshop ID: 0 until its first upload (the bytes are then the template's), then the
    # item's ID, so a rebuild keeps it (packaging.check_mod_id: a non-negative integer that fits in a uint64).
    mod_id: int = 0
    # The menu pictures taken from another stock Operation, or generated: a picture's name (MapConfiguration's
    # DescriptionTextureElements: CornerLogo, MissionCountry, EndgameBlazon, MapTexture) -> the stock scenario whose
    # file ships in its place, or a MenuPicture making the file at build time (modkit.ops.menuart.card_picture), at
    # the path the re-keyed MapConfiguration names (modkit.ops.items.menu_art; a scenario's Assets folder is
    # STOCK_ASSETS). Empty: the template's own pictures, as the asset rules copy them.
    menu_art: Mapping[str, str | MenuPicture] = field(default_factory=dict)
    # --- extension points
    extra_config_rows: tuple[str, ...] = ()                     # whole lines under Config.ini's [Config]
    extra_manifest_rows: tuple[tuple[str, str, str], ...] = ()  # (name, action, source) rows of MANIFEST.tsv
    extra_packs: tuple[ExtraPack, ...] = ()
    extra_items: tuple[ExtraItems, ...] = ()   # files added to the profile's own packs (a generated Details file, ...)
    extra_loose_files: tuple[LooseFiles, ...] = ()
    extra_gates: tuple[ExtraGate, ...] = ()
    extra_outputs: tuple[ReviewOutput, ...] = ()
    # Gate failures under review, {gate name: (its exact message, ...)}, several for a gate run once per file
    # (modkit.core.gates.run_gate): reported, not raised; an entry that no longer fires is logged.
    reviewed_pending: Pending = field(default_factory=dict)

    def __post_init__(self):
        check_mod_id(self.mod_id)
        check(tuple(self.packs) == PACKS,
              f"OpProfile.packs is {list(self.packs)}, but a build always plans and writes the packs {list(PACKS)}, "
              f"in that order: leave packs out (a new pack goes in extra_packs)")

    def shape_globs(self, inner: str) -> tuple[str, ...]:
        """The stock files whose shapes the generated `inner` may use, as absolute globs."""
        check(inner in self.shape_sources, f"{inner} is generated (it has a fixture), but the profile names no stock "
                                           f"files for its shapes (shape_sources)")
        return tuple(extracted(g) for g in self.shape_sources[inner])
