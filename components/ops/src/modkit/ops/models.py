"""The op-domain records more than one module or example shares, in one place.

``ForceRow`` is a row of units: a deck card (``shapes.add_card``), a wave's or a company's row
(``mission.create_rows``), a stock deck's pack (``gates.deck_packs``) or a row of a force table (``forces.rows_of``),
which also says where and in which group it spawns. ``CampRow`` is one camp of a template's CampList
(``shapes.camp_nodes``), ``Ending`` one row of an end funnel (``mission.end_funnel``), ``Knobs`` a difficulty knob's
three values (``mission.difficulty``) and ``Buttons`` a two-button dialog's buttons (``mission.reask_loop``).

A profile's and a content's settings: ``AssetRule`` (what a build does with a template Assets file),
``ExtraShape`` (a GDScript shape a content admits, ``profile.Content.extra_shapes``) and ``MenuEntry`` (an Operations
menu entry: a mod's, read by ``coinstall``, or a stock Operation's, ``gates.stock_operations``).

Rows are frozen pydantic dataclasses, so a table stays positional and terse: ``ForceRow("T80BV_SOV", 4)``. Each field
is checked against its type when a row is made.
"""
from __future__ import annotations

from dataclasses import field
from typing import Literal

from pydantic import ConfigDict
from pydantic.dataclasses import dataclass

_ROW = ConfigDict(extra="forbid")


@dataclass(frozen=True, config=_ROW)
class ForceRow:
    """`count` units of `unit` (its bare stock name, ``T80BV_SOV`` for ``Descriptor_Unit_T80BV_SOV``), riding in
    `transport` (the carrier's bare name) or None. A force table's row (``forces.rows_of``) also names its scripted
    `group`, the side it is created in (`camp`, a key of the content's sides), its `spawn` (a point of the content's
    map), its `echelon` (the order-of-battle label for the briefing), and whether it is `fixed` (not multiplied by the
    scale knob); a bare row leaves them empty."""
    unit: str
    count: int
    transport: str | None = None
    group: str = field(default="", kw_only=True)
    camp: str = field(default="", kw_only=True)
    spawn: str = field(default="", kw_only=True)
    echelon: str = field(default="", kw_only=True)
    fixed: bool = field(default=False, kw_only=True)


@dataclass(frozen=True, config=_ROW)
class CampRow:
    """One camp of a template's CampList: its export `name`, its TGDVariableCamp scalars before PlayerName as
    (property, value tag, value), and its SetDeck id (`deck`)."""
    name: str
    scalars: tuple[tuple[str, int, int], ...]
    deck: str


@dataclass(frozen=True, config=_ROW)
class Ending:
    """An end funnel's row (``mission.end_funnel``): the dialog `token` it shows, the TriggerEndGame's EVictoryType
    (`kind`), and whether the player `loses`."""
    token: str
    kind: int
    loses: bool


@dataclass(frozen=True, config=_ROW)
class Knobs:
    """A difficulty knob's values (``mission.difficulty``): Easy's, Medium's and Hard's."""
    easy: int
    medium: int
    hard: int

    def at(self, level: int) -> int:
        """The value at `level`, an EGameDifficulty (``shapes.EASY``, ``MEDIUM`` or ``HARD``: 0, 1, 2)."""
        return (self.easy, self.medium, self.hard)[level]


@dataclass(frozen=True, config=_ROW)
class Buttons:
    """A two-button dialog's buttons, stock INTERFACE_INGAME tokens (``bricks.g_choice``): button 0 (`yes`, the "now"
    answer) and button 1 (`no`)."""
    yes: str
    no: str


@dataclass(frozen=True, config=_ROW)
class AssetRule:
    """What a build does with a template Assets file (``items.plan_assets``): the first rule whose fnmatch `pattern`
    matches decides; `action` is 'copy' (re-pathed to the new id) or 'drop', listed in the manifest with `why`."""
    pattern: str
    action: Literal["copy", "drop"]
    why: str


@dataclass(frozen=True, config=_ROW)
class ExtraShape:
    """A GDScript shape gate 2 admits although no stock file uses it (``profile.Content.extra_shapes``): a property
    `prop` of the native class `cls` with value tag `tag`, and its reference `target` (None: not a reference). The
    class is admitted too."""
    cls: str
    prop: str
    tag: int
    target: str | None


@dataclass(frozen=True, config=_ROW)
class MenuEntry:
    """An Operations menu entry: its `scenario`, its menu order (MapConfiguration's OrderToChainMission; None: the
    object holds none) and its MapConfiguration `guid` (None: it holds none)."""
    scenario: str
    order: int | None
    guid: bytes | None
