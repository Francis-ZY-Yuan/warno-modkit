"""Shared WARNO formats, local-path configuration, the gate framework, packaging and the share installer.

The read-only analysis modules (``ndfrules`` with ``pexref`` and ``pedis``, and ``crashdump``) read your own
WARNO.exe, read-only, to find the load-time checks your mod must pass, and read the error message in your own crash
dumps. They write nothing to the exe and do nothing else with it.
"""
from modkit.core.stock import Stock

# What core's readers need from the stock extraction (see modkit.core.stock; `python -m modkit.core.setup extract`
# builds it from your install). The folder names are the extraction's layout, which the builders print in their
# provenance strings (`extracted/glad_201602/...`), so they do not follow the game build.
STOCK_PATHS = (
    Stock("index_all.tsv", index=True,
          why="every archive of the install and the inner paths it holds: the lookup the other entries use"),
    Stock("glad_201602", packs=("Glad",), latest=True, corpus=False,
          why="Glad.dat: the game's own NDF up to build 201602. Build 210942 loads it from Transactions.dat instead "
              "(below); kept for the readers that still name it"),
    Stock("transactions", packs=("Transactions",),
          why="the game's own NDF from build 210942 on (Transactions.dat: Glad's files re-shipped as .txn, some "
              "renamed; ModManager's tag lists): the stock corpus ndfrules checks its table against"),

    # The rest of the stock corpus of ndfrules: it reads every compiled NDF file of the extraction (`.ndfbin`, and
    # `.txn` from build 210942 on; the table's stock counts and the "reviewed" evidence are taken over them), so these
    # are the scenario and map NDF files of the install.
    *(Stock(f"scenarios/{family}_*", packs=(pack,), latest=pack.endswith("_Definition"),
            why="every stock scenario's NDF and zone files: ndfrules' corpus")
      for family in ("challenge", "CampagneStrat") for pack in ("{}_Definition", "{}_Details")),
    *(Stock(f"skirmish/{name}", packs=(f"{name}_Details",), include=("out/*.ndfbin",),
            why="three skirmish scenarios' zone files: ndfrules' corpus")
      for name in ("_2x2_Hesse_2vs2_CONQ", "_3x3_Kreide_10vs10_CONQ", "_3x3_UrbanFrontlines_10vs10_CONQ")),
    Stock("basemaps/_4x2_Isura/data", packs=("_4x2_Isura_Definition",), latest=True, include=("NDF/Maps/*.txn",),
          why="one stock map's own NDF files (MapConstante, MapDefinition, MapLoader): ndfrules' corpus"),
)
