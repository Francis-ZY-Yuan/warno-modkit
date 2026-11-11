"""LevelDesign: the item type, the generated LevelDesign and zone areas, GdItems tags, and reading items back.

A LevelDesign (``out/LevelDesign.ndfbin`` in the Details pack) is a ``TGameDesignDatabase`` of ``TGameDesignItem``
objects, each with a Position, an optional Rotation and one ``TGameDesignAddOn_<kind>`` (Name, Ranking, GUID and the
kind's fields). A GDScript names an item through a ``GdItems`` tag whose four GUID words equal the item's GUID.

Item GUIDs are uuid5 names under a namespace string the mod chooses (``ld_guid``), so two mods cloning one stock
template never share a GUID. The scenario's GUID (``scenario_guid``) is hashed the same way, and a published
Operation's menu order (``derived_menu_order``) is derived from it.
"""
from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Iterable

from modkit.core.gates import check
from modkit.core.names import name_guid
from modkit.core.ndfbin import Value
from modkit.ops.bricks import unit_path
from modkit.ops.graph import TRUE, Node, Str, decode, f32, i32
from modkit.ops.zones import ZoneArea, polygon_centroid

# The generated LevelDesign in the Details pack, and the PROP entries its add-on classes share (stock layout).
LD_FILE = "out/LevelDesign.ndfbin"
LD_SHARED = frozenset({"Name", "Ranking", "GUID"})
# The zone file of each zone add-on: the polygons the game's zone managers load and test.
ZONE_FILES = {"DeploymentZone": "out/DeploymentZone.ndfbin", "CommandPoints": "out/CommandZone.ndfbin"}

# The GDScript tag class for each LevelDesign add-on kind (stock GdItems exports, HoldUntilRelieved's included).
GD_TAG_CLASS = {"Name": "TGDTagPosition", "CircularZone": "TGDTagDetecteur", "Spawn": "TGDTagUnitGroup",
                "DeploymentZone": "TGDTagPosition", "CommandPoints": "TGDTagPosition",   # HUR GdItems exports
                "ReinforcementLocation": "TGDTagPosition", "AerialCorridor": "TGDTagPosition"}


@dataclass(frozen=True)
class LdItem:
    """One LevelDesign item (world units). Each optional field belongs to some add-on kinds; left at its default it
    is omitted from the file."""
    ranking: str
    name: str
    x: float
    y: float
    addon: str                       # Name | CircularZone | Spawn | DeploymentZone | CommandPoints | ReinforcementLocation
    #                                  | AerialCorridor
    radius_gru: float | None = None  # CircularZone
    unit: str | None = None          # Spawn: descriptor suffix, e.g. 'Rifles_AT_UK'
    experience: int | None = None    # Spawn: ExperienceLevel (omitted when None)
    group: str = ""                  # free grouping label for the mod's own script (not written)
    rotation: float | None = None    # TGameDesignItem.Rotation (omitted when None); zones: equal to the area's
    polygon: tuple[tuple[float, float], ...] | None = None  # DeploymentZone/CommandPoints: closed ring (Details file)
    alliance: int | None = None      # DeploymentZone AllianceNum (omitted when None = alliance 0)
    points: int | None = None        # CommandPoints Points
    start: tuple[float, float] | None = None  # ReinforcementLocation/AerialCorridor StartPosition (z 0.0, as in stock)
    end: tuple[float, float] | None = None    # ReinforcementLocation/AerialCorridor EndPosition
    camp: int | None = None          # Spawn: Camp (omitted for None and 0, the player's)
    disable_auto_spawn: bool = False  # Spawn: DisableAutoSpawn (hidden until a script's SpawnUnits reveals it)
    num_alliance: int | None = None  # ReinforcementLocation/AerialCorridor NumAlliance (omitted when None, the player's)


def ld_key(it: LdItem) -> tuple[bytes, bytes]:
    """Stock LevelDesigns sort their items by (Ranking, Name)."""
    return it.ranking.encode("latin-1"), it.name.encode("latin-1")


def ld_guid(it: LdItem, scenario: str, namespace: str) -> bytes:
    """The item's GUID: uuid5(NAMESPACE_URL, '<namespace>/<scenario>/<Ranking>/<Name>') (modkit.core.names.name_guid
    of '<scenario>/<Ranking>/<Name>')."""
    return name_guid(namespace, f"{scenario}/{it.ranking}/{it.name}")


def scenario_guid(scenario: str, namespace: str) -> bytes:
    """The scenario's GUID (MapConfiguration, ScenarioInfo): uuid5(NAMESPACE_URL, '<namespace>/<scenario>'), the
    scenario-level name of ld_guid's scheme (modkit.core.names.name_guid of '<scenario>')."""
    return name_guid(namespace, scenario)


# The range of derived menu orders (MapConfiguration's TChallengeMapInfo.OrderToChainMission, a uint32): far above
# stock's Operations (10 to 999) and above the numbers a modder picks by hand (1000 and up).
MENU_ORDER_BASE = 1_000_000
MENU_ORDER_SPAN = 9_000_000


def derived_menu_order(scenario: str, namespace: str) -> int:
    """A published Operation's menu order (OrderToChainMission): MENU_ORDER_BASE + the scenario's GUID (scenario_guid,
    read big-endian) modulo MENU_ORDER_SPAN.

    A hash, because the order must be unique across every mod a player runs at once, Workshop mods included, which no
    build's gates can see: two active Operations with one order stop the game at start [[content-identity-unique]],
    and hand picks cluster just above stock's numbers. The scenario's GUID, because it already is the Operation's hashed
    identity (its own namespace and scenario id), so one identity drives both."""
    return MENU_ORDER_BASE + int.from_bytes(scenario_guid(scenario, namespace), "big") % MENU_ORDER_SPAN


def zone_addon_extra(it: LdItem) -> list[tuple[str, object]]:
    """The side or value field of a zone add-on, identical in LevelDesign and the Details file: DeploymentZone
    AllianceNum (absent = alliance 0, HUR #46 / #45), CommandPoints Points (HUR #42)."""
    if it.addon == "DeploymentZone":
        return [("AllianceNum", i32(it.alliance))] if it.alliance is not None else []
    return [("Points", i32(it.points))]


def leveldesign_graph(items: Iterable[LdItem], scenario: str, namespace: str) -> list[Node]:
    """The LevelDesign graph: TGameDesignDatabase #0, the items sorted by ld_key, their add-ons after them
    (breadth-first); each GUID is ld_guid(item, `scenario`, `namespace`). Add-on property order: Name, Ranking, GUID,
    then a Spawn's AutoNameBase, [Camp], ClassName, [ExperienceLevel], [DisableAutoSpawn] (Survivors' items), a
    CircularZone's RadiusGRU, a zone's zone_addon_extra, or an arrival's [NumAlliance], StartPosition, EndPosition
    (HUR #48 / #1)."""
    out = []
    for it in sorted(items, key=ld_key):
        props: list[tuple[str, object]] = [("Name", Str(it.name)), ("Ranking", Str(it.ranking)),
                                           ("GUID", Value(0x1A, ld_guid(it, scenario, namespace)))]
        if it.addon == "Spawn":
            props.append(("AutoNameBase", Str(it.unit)))
            if it.camp:
                props.append(("Camp", i32(it.camp)))
            props.append(("ClassName", Str(unit_path(it.unit))))
            if it.experience is not None:
                props.append(("ExperienceLevel", i32(it.experience)))
            if it.disable_auto_spawn:
                props.append(("DisableAutoSpawn", TRUE))
        elif it.addon == "CircularZone":
            props.append(("RadiusGRU", f32(it.radius_gru)))
        elif it.addon in ("DeploymentZone", "CommandPoints"):
            props += zone_addon_extra(it)
        elif it.addon in ("ReinforcementLocation", "AerialCorridor"):
            props += [("NumAlliance", i32(it.num_alliance))] if it.num_alliance is not None else []
            props += [("StartPosition", Value(0x0B, (float(it.start[0]), float(it.start[1]), 0.0))),
                      ("EndPosition", Value(0x0B, (float(it.end[0]), float(it.end[1]), 0.0)))]
        else:
            check(it.addon == "Name", f"{it.ranking}/{it.name}: unknown add-on {it.addon}")
        addon = Node(f"TGameDesignAddOn_{it.addon}", props)
        rotation = [("Rotation", f32(it.rotation))] if it.rotation is not None else []
        out.append(Node("TGameDesignItem", [("Position", Value(0x21, (float(it.x), float(it.y)))), *rotation,
                                            ("AddOn", addon)]))
    return [Node("TGameDesignDatabase", [("GameDesignItemList", out)])]


def zone_area(it: LdItem, scenario: str, namespace: str, ground_z: float) -> ZoneArea:
    """The Details copy of a zone item (a zone_areas_graph input): same Name, Ranking, GUID, AllianceNum/Points and
    Rotation; Center = the polygon centroid at height `ground_z` (stock: Center x/y = area centroid, 113 of 113
    zones)."""
    props = [("Name", Str(it.name)), ("Ranking", Str(it.ranking)),
             ("GUID", Value(0x1A, ld_guid(it, scenario, namespace))), *zone_addon_extra(it)]
    return (list(it.polygon), (*polygon_centroid(list(it.polygon)), ground_z), f"TGameDesignAddOn_{it.addon}",
            props, it.rotation)


def gd_tags(items: Iterable[LdItem], scenario: str, namespace: str) -> dict[str, Node]:
    """The GdItems tag of each item, keyed 'Ranking/Name' in ld_key order: GD_TAG_CLASS of its add-on, the four
    GUID words of ld_guid(item, `scenario`, `namespace`), exported as $/GDScript/GdItems/<Ranking>/<Name> (S#157,
    #1019, #730). Tags made for another scenario or namespace bind nothing (gates.check_binding)."""
    return {f"{it.ranking}/{it.name}": Node(
        GD_TAG_CLASS[it.addon],
        [(f"GUID{k + 1}", i32(w)) for k, w in enumerate(struct.unpack(">4i", ld_guid(it, scenario, namespace)))],
        export=f"$/GDScript/GdItems/{it.ranking}/{it.name}") for it in sorted(items, key=ld_key)}


def read_ld_items(raw: bytes) -> list[dict]:
    """LevelDesign items as dicts: pos, rot (None when absent), addon (class suffix) and the add-on's fields."""
    ld, _, _ = decode(raw)
    p = [{ld.pname(pi): v for pi, v in ob.props} for ob in ld.objects]
    out = []
    for ob, d in zip(ld.objects, p):
        if ld.cname(ob.cls) == "TGameDesignItem":
            k = d["AddOn"].v.index
            out.append({"pos": tuple(d["Position"].v), "rot": d["Rotation"].v if "Rotation" in d else None,
                        "addon": ld.cname(ld.objects[k].cls)[len("TGameDesignAddOn_"):],
                        **{n: ld.strings[v.v].decode("latin-1") if v.tag in (0x07, 0x1C) else v.v
                           for n, v in p[k].items()}})
    return out


def ld_position(key: str, ld_items: Iterable) -> tuple[float, float]:
    """(x, y) of the item named `key` ('Ranking/Name') among items with ranking, name, x and y fields."""
    return next((it.x, it.y) for it in ld_items if f"{it.ranking}/{it.name}" == key)
