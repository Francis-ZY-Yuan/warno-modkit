"""Operations (scenario) builder: engine and examples."""
from modkit.core.stock import Stock

_KREIDE = "_3x3_Kreide"
_GEISA = "_4x3_geisa"
_TWIN = "_3x3_TwinCities"
_SURVIVORS = "challenge_Survivors"


def _op(folder: str, *packs: str, why: str) -> tuple[Stock, ...]:
    """A merged copy of whole scenario packs under `folder`, one folder per pack, each with its provenance file.
    A `_Definition` pack is a full copy in each revision (the newest alone is current); a `_Details` pack is a delta."""
    return tuple(Stock(f"{folder}/{p}", packs=(p,), latest=p.endswith("_Definition"), provenance=True, why=why)
                 for p in packs)


# A scenario's menu pictures, inside its Assets pack (MapTexture.tgv, the card modkit.ops.menuart redraws, among them).
MENU_PICTURES = "PC/Texture/*/MapPackAssets/Textures/*.tgv"

# The game's own INTERFACE_INGAME dictionary of one language (format `lang`), relative to the extraction: where the
# game looks dialog button labels up (modkit.ops.gates.INGAME_PROPS). STOCK_PATHS declares its folder.
INGAME_DIC = "glad_201602/Localisation/Core/INTERFACE_INGAME-{lang}.dic"

# What ops' readers need from the stock extraction (see modkit.core.stock).
STOCK_PATHS = (
    # --- read by the engine's code and tests in this component
    Stock("scenarios/challenge_*", packs=("{}_Definition",), latest=True,
          why="the 16 stock challenge scenarios' NDF (GDScript, ScenarioInfo, ...): shape and key gates, rekey"),
    Stock("scenarios/challenge_*", packs=("{}_Details",),
          why="their zones, LevelDesign, Items and camera paths: the zone and LevelDesign readers' stock"),

    # --- read by the Open Door example and the probes (examples/open-door, examples/probes): the template, the map and
    # --- the probes' scripts. The tests scan the examples for their readers.
    Stock(f"scenarios/{_SURVIVORS}", packs=(f"{_SURVIVORS}_Assets",),
          why="Survivors' own localisation, voice lines and Python/Texture/Video files, which the op copies and re-keys"),
    *_op("kreide_op", f"{_SURVIVORS}_Definition", f"{_SURVIVORS}_Details",
         f"{_KREIDE}_3vs3_CONQ_Definition", f"{_KREIDE}_3vs3_CONQ_Details", f"{_KREIDE}_3vs3_DEST_Details",
         f"{_KREIDE}_1vs1_CONQ_DUEL_Definition", f"{_KREIDE}_1vs1_CONQ_DUEL_Details",
         f"{_KREIDE}_10vs10_CONQ_Details", f"{_KREIDE}_10vs10_DEST_Details",
         why="Survivors and Kreide's scenario packs: the base op's sources, Kreide's zones and AI grid, the LevelDesign survey"),
    *_op("geisa_op", f"{_GEISA}_10vs10_CONQ_Definition", f"{_GEISA}_10vs10_CONQ_Details",
         why="Geisa's scenario packs: the map data of Open Door and the probes"),
    Stock(f"basemaps/{_GEISA}", packs=(f"{_GEISA}_Assets",), include=(f"PC/Texture/{_GEISA}/Preview.tgv", f"PC/Texture/{_GEISA}/Minimap.tgv"),
          why="Geisa's Preview (the review overlay) and Minimap (the road pixels the lane and traffic tests read)"),
    Stock("glad_201602/Localisation/Core", packs=("ZZ_1",),
          rename=(r"Localisation/Localisation/Core/(INTERFACE_INGAME-[A-Za-z]+\.dic)", r"\1"),
          why="the game's INTERFACE_INGAME dictionaries (the glyph gate and the in-game key check)"),
    *(Stock(f"scenarios/{family}_*", packs=("{}_Assets",), include=("*-SC.dic", *more, MENU_PICTURES),
            why="every stock scenario's Chinese dictionaries: the characters the glyph gate admits (gates.check_strings)"
                + ("; the challenges' English menu texts: the stock lengths the title convention is measured against "
                   "(strings.check_titles)" if more else "")
                + "; its menu pictures: what the TGV writer round-trips byte for byte (core's test_tgv), and what a "
                  "profile's menu art ships in place of the template's (OpProfile.menu_art)")
      for family, more in (("challenge", ("Localisation/*/SCENARIO_DEFINITION-US.dic",)), ("CampagneStrat", ()))),
    Stock("moddata_base", archive="Mods/ModData/base.zip",
          include=("GameData/Generated/Gameplay/Effects/*", "GameData/Gameplay/Constantes/Enumerations/*",
                   "GameData/Generated/Gameplay/Decks/Decks.ndf", "GameData/Generated/Gameplay/Decks/DeckPacks.ndf"),
          why="the mod SDK's NDF text: the effect packs and enumerations the probes' tests pin, and the stock decks "
              "and their packs Twin Strike's deck test re-derives its start cards from"),

    # --- read by Twin Cities' map record (modkit.ops.maps.TWIN_CITIES and its cut), Twin Strike's map and design, and
    # --- its storyboard page (modkit.ops.storyboard draws a layout on its pictures)
    *_op("twincities_op", f"SM_SU{_TWIN}_03_Details",
         why="Twin Cities' stock small layout: playable x 0-432, y 146-768 minimap px, its AI grid on that box, three "
             "command zones and two deployment zones; Twin Strike's map and the storyboard's sample"),
    *_op("twincities_op", f"SM_SU{_TWIN}_03_Definition",
         why="the small layout's own Definition: the map name (ScenarioInfo) and EnvironmentSettings (MapConfiguration) "
             "modkit.ops.maps.TWIN_CITIES is read off"),
    *_op("twincities_op", f"{_TWIN}_10vs10_CONQ_Details",
         why="Twin Cities' 10vs10 conquest layout: the whole map's zones, which Twin Strike's design compares against"),
    Stock(f"basemaps/{_TWIN}", packs=(f"{_TWIN}_Assets",),
          include=(f"PC/Texture/{_TWIN}/Preview.tgv", f"PC/Texture/{_TWIN}/Minimap.tgv"),
          why="Twin Cities' Minimap and Preview: the storyboard page's two pictures"),
)
