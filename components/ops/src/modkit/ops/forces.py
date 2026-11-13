"""Force tables: rows of units a script creates or reveals, the scale knob, share thresholds and spawn formations.

Pure data and arithmetic. A force table's ``ForceRow`` (``modkit.ops.models``, placed by ``rows_of``) names its spawn
by a point of the content's map (``shapes.Minimap.points``) and its units by their bare stock names (``T80BV_SOV`` for
``Descriptor_Unit_T80BV_SOV``). ``scaled()`` turns a table at 1x into the forces for another scale: every row not
marked ``fixed`` is multiplied and rounded per row, never below 1. Thresholds are shares of a base count, turned into
counts with ``share_count()``, so a resize can never push one past its base or down to 0.

Rounding: floor(x + 0.5), never Python's round() (which takes 10.5 to 10).

A force table is content: each op keeps its own. The Soviet groups more than one example op on Geisa creates are kept
once here (``GEISA_SOVIET_ROWS``).
"""
from __future__ import annotations

import math
from dataclasses import replace
from typing import Iterable

from modkit.ops.models import ForceRow


def rows_of(group: str, camp: str, spawn: str, echelon: str, *rows: ForceRow, fixed: bool = False) -> list[ForceRow]:
    """One group of a force table: each of `rows` (a bare ForceRow: unit, count, transport) placed in `group`, created
    in `camp` at `spawn`, labelled `echelon`, and `fixed` or not."""
    return [replace(r, group=group, camp=camp, spawn=spawn, echelon=echelon, fixed=fixed) for r in rows]


def _round_half_up(x: float) -> int:
    return math.floor(x + 0.5)


def share_count(share: float, base: int) -> int:
    """A count from a share of `base`: floor(share * base + 0.5), clamped to [1, base] when both are positive."""
    if share <= 0 or base <= 0:
        return 0
    return min(base, max(1, _round_half_up(share * base)))


def scaled(rows: Iterable[ForceRow], force_scale: float) -> list[ForceRow]:
    """`rows` with each non-fixed count multiplied by `force_scale` and rounded half-up, floor 1. Fixed rows and the
    order of rows are kept; the input is not modified."""
    if force_scale <= 0:
        raise ValueError(f"force_scale must be positive, got {force_scale!r}")
    return [r if r.fixed else replace(r, count=max(1, _round_half_up(r.count * force_scale))) for r in rows]


def group_total(rows: Iterable[ForceRow], group: str) -> int:
    return sum(r.count for r in rows if r.group == group)


def group_rows(rows: Iterable[ForceRow], group: str, force_scale: float) -> list[ForceRow]:
    """The rows of `group` at `force_scale`, in table order."""
    return [r for r in scaled(rows, force_scale) if r.group == group]


def formation(anchor: tuple[float, float], n: int, spacing: float, cols: int) -> list[tuple[float, float]]:
    """`n` points of a row-major grid, `spacing` apart, `cols` to a row (the last row may be short), with the grid's
    bounding box centred on `anchor`. Row 0 has the smallest y."""
    if cols < 1:
        raise ValueError(f"cols must be at least 1, got {cols!r}")
    used_cols, rows = min(n, cols), -(-n // cols)
    ax, ay = anchor
    return [(ax + (i % cols - (used_cols - 1) / 2) * spacing, ay + (i // cols - (rows - 1) / 2) * spacing)
            for i in range(n)]


# --------------------------------------------------------------------------- the shared Soviet force on Geisa

# The Soviet groups more than one example op on Geisa creates (the probes and Open Door), at 1x, camp "PACT", each
# spawning at a modkit.ops.maps.GEISA_POINTS name: the lead division's forward detachment (its main body and its air
# defence), the follow-on division's detachment, an army artillery battery and a recon patrol. An op's other rows stay
# with the op.
GEISA_SOVIET_ROWS: tuple[ForceRow, ...] = tuple(
    rows_of("main_body", "PACT", "ENTRY_N", "5th GTA lead division forward detachment",
            ForceRow("T80BV_SOV", 30), ForceRow("T80BV_CMD_SOV", 1), ForceRow("BMP_2_SOV", 10),
            ForceRow("MotRifles_SOV", 9, "BMP_2_SOV"), ForceRow("BRDM_2_Konkurs_SOV", 3),
            ForceRow("2S3M_Akatsiya_SOV", 6), ForceRow("BMP_1_CMD_SOV", 1), ForceRow("MTLB_supply_SOV", 3))
    + rows_of("pocket_ad", "PACT", "ENTRY_N", "forward detachment air defence",
              ForceRow("Tunguska_2K22_SOV", 2), ForceRow("Osa_9K33M3_SOV", 2), ForceRow("MTLB_Strela10_SOV", 2))
    + rows_of("relief", "PACT", "ENTRY_NE", "follow-on division forward detachment",
              ForceRow("T80U_SOV", 30), ForceRow("T80U_CMD_SOV", 1), ForceRow("BMP_2_SOV", 10),
              ForceRow("MotRifles_SOV", 9, "BMP_2_SOV"), ForceRow("Tunguska_2K22_SOV", 3),
              ForceRow("MTLB_Strela10_SOV", 2))
    + rows_of("opener_battery", "PACT", "CORNER_PACT", "8th Guards Army artillery",
              ForceRow("BM27_Uragan_SOV", 2), ForceRow("2S3M_Akatsiya_SOV", 4))
    + rows_of("probe", "PACT", "TRACK_SE_IN", "recon patrol",
              ForceRow("BRM_1_SOV", 1), ForceRow("BRDM_2_SOV", 2), ForceRow("Scout_SOV", 1))
)
