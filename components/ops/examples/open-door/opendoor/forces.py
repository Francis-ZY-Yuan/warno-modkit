"""Open Door's forces: the force table, the scale knob and the share thresholds (design 6.2-6.4).

Pure data and arithmetic. Nothing here reads the game or the map: a row's spawn is a point name of opendoor.map's
POINTS, and its units are bare stock names (`T80BV_SOV` for `Descriptor_Unit_T80BV_SOV`). The row type and the
arithmetic (ForceRow, scaled, share_count, group_total, formation, the table builder rows_of) are modkit.ops.forces'.

ROWS is every row of design 6.2 and 6.3 at 1x, Medium: Open Door's own groups below, and the Soviet groups the probes
create too, read from the shared table (modkit.ops.forces.GEISA_SOVIET_ROWS). `scaled()` turns it into the forces for
another scale: every Soviet row and every scripted NATO row is multiplied and rounded per row (floor of 1), and rows
marked `fixed` do not scale (the decoys, the Apache companies and the air-assault lift). Thresholds are shares of a
base count, turned into counts at build time with `share_count()`, so a resize can never push one past its base or
down to 0. Rounding: floor(x + 0.5), never Python's round() (which takes 10.5 to 10).

A ForceRow's camp is "PACT", "NATO" or "Decoys" (opendoor.profile.CAMPS).
"""
from __future__ import annotations

from typing import Iterable

from modkit.ops.forces import GEISA_SOVIET_ROWS, ForceRow, group_rows, group_total, rows_of, share_count

FORCE_SCALE = 1.0       # design 6.4: 1x at release

ROWS: tuple[ForceRow, ...] = tuple(
    # --- Pact (design 6.2): the first echelon and the relief's helicopters are Open Door's; the main body, its air
    # defence, the relief, the opening battery and the recon probe are the shared table's
    rows_of("first_echelon", "PACT", "ENTRY_E", "39th GMRD MR battalion (-)",
            ("T80B_SOV", 10), ("BMP_2_SOV", 8), ("MotRifles_SOV", 8, "BMP_2_SOV"), ("BMP_1_CMD_SOV", 1),
            ("BRDM_2_SOV", 2), ("BRDM_2_Konkurs_SOV", 2), ("Scout_SOV", 2), ("ZSU_23_Shilka_SOV", 2),
            ("BRDM_Strela_1_SOV", 1))
    + list(GEISA_SOVIET_ROWS)
    + rows_of("relief_helo", "PACT", "ENTRY_NE", "army aviation",
              ("Mi_24V_AT_SOV", 4))
    # --- NATO (design 6.3)
    + rows_of("decoys", "Decoys", "PL_BLUE", "8th ID, broken down",
              ("M1_Abrams_US", 8), fixed=True)
    + rows_of("north_jaw", "NATO", "RESERVE_N", "3rd AD M1A1HA company team",
              ("M1A1HA_Abrams_US", 10), ("M1A1HA_Abrams_CMD_US", 1), ("M2A2_Bradley_IFV_US", 4),
              ("Rifles_half_AT4_US", 4, "M2A2_Bradley_IFV_US"), ("M3A1_Bradley_CFV_US", 2), ("M163_PIVADS_US", 1),
              ("M981_FISTV_US", 1))
    + rows_of("south_jaw", "NATO", "HIDE_S", "5. Pz reinforced Panzer company",
              ("Leopard_2A4_RFA", 7), ("Leopard_2A4_CMD_RFA", 1), ("Marder_1A2_RFA", 3),
              ("Panzergrenadier_IFV_RFA", 3, "Marder_1A2_RFA"), ("Gepard_1A2_RFA", 1), ("Luchs_A1_RFA", 1))
    + rows_of("air_assault", "NATO", "EDGE_N", "3rd AD air cav platoon",
              ("UH60A_Black_Hawk_US", 4), ("AeroRifles_US", 4, "UH60A_Black_Hawk_US"), ("AH64_Apache_emp1_US", 2),
              fixed=True)
    + rows_of("apaches", "NATO", "EDGE_W", "AH-64A company",
              ("AH64_Apache_emp1_US", 4), fixed=True)
    + rows_of("strike_fallback", "NATO", "CORNER_NATO", "V Corps MLRS",
              ("M270_MLRS_cluster_US", 2))
)


def force_rows(group: str) -> list[ForceRow]:
    """The ROWS of `group` at FORCE_SCALE, in table order."""
    return group_rows(ROWS, group, FORCE_SCALE)


# --------------------------------------------------------------------------- thresholds

THRESHOLDS = {"B1": (0.28, 0.42, 0.55), "B5": (0.35, 0.50, 0.65)}      # shares, ordered easy, medium, hard
_DIFFICULTIES = ("easy", "medium", "hard")
_RELIEF_TANKS = ("T80U_SOV", "T80U_CMD_SOV")


def threshold(name: str, difficulty: str, rows: Iterable[ForceRow]) -> int:
    """The unit count that triggers objective `name` ("B1" or "B5") at `difficulty` ("easy", "medium" or "hard").
    The base for B1 is the first echelon; for B5 it is the relief's T-80U tanks (T80U_SOV plus T80U_CMD_SOV)."""
    shares = THRESHOLDS[name]
    if difficulty not in _DIFFICULTIES:
        raise KeyError(f"unknown difficulty {difficulty!r}; expected one of {_DIFFICULTIES}")
    share = shares[_DIFFICULTIES.index(difficulty)]
    rows = list(rows)
    if name == "B1":
        base = group_total(rows, "first_echelon")
    else:
        base = sum(r.count for r in rows if r.group == "relief" and r.descriptor in _RELIEF_TANKS)
    return share_count(share, base)
