"""Zones and other Details files: graph builders for the playable zone, deployment and command zones, camera paths
and the AI strategic grid, their readers, and plane geometry.

Every builder emits the stock shape: the shape gate re-checks it against every stock file of its kind, and
``modkit.ops.gates.check_details_generators`` rebuilds stock files from their own values, image for image.
"""
from __future__ import annotations

import math

from modkit.core.gates import check
from modkit.core.ndfbin import Value, as_f32  # noqa: F401 - as_f32 is core's, re-exported here
from modkit.ops.files import read_file
from modkit.ops.graph import Node, Str, decode, f32

ZoneArea = tuple[list, tuple, str, list, "float | None"]  # (polygon, Center, add-on class, add-on props, Rotation)

# --------------------------------------------------------------------------- geometry


def lerp(a: tuple[int, int], b: tuple[int, int], t: float) -> tuple[int, int]:
    return round(a[0] + (b[0] - a[0]) * t), round(a[1] + (b[1] - a[1]) * t)


def rect_polygon(box: tuple[float, float, float, float]) -> tuple[tuple[float, float], ...]:
    x0, y0, x1, y1 = box
    return (x0, y0), (x1, y0), (x1, y1), (x0, y1), (x0, y0)  # closed, in Kreide's PlayableZone vertex order


def heading(a: tuple[float, float], b: tuple[float, float]) -> float:
    return math.atan2(b[1] - a[1], b[0] - a[0])


def polygon_centroid(poly: list[tuple[float, float]]) -> tuple[float, float]:
    """Area centroid of a closed polygon; every non-empty stock zone's Center x/y equals it (float32)."""
    a = cx = cy = 0.0
    for (x0, y0), (x1, y1) in zip(poly, poly[1:]):
        cr = x0 * y1 - x1 * y0
        a, cx, cy = a + cr, cx + (x0 + x1) * cr, cy + (y0 + y1) * cr
    return cx / (3 * a), cy / (3 * a)


def point_in_polygon(x: float, y: float, poly: list) -> bool:
    inside = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        if (ay > y) != (by > y) and x < ax + (y - ay) * (bx - ax) / (by - ay):
            inside = not inside
    return inside


# --------------------------------------------------------------------------- deployment and command zones

def read_zone_areas(raw: bytes) -> list[ZoneArea]:
    """The TMapAreas of a DeploymentZone/CommandZone ndfbin as zone_areas_graph inputs (strings as Str)."""
    nb, _, _ = decode(raw)
    out = []
    for ob in nb.objects:
        if nb.cname(ob.cls) != "TMapArea":
            continue
        d = {nb.pname(pi): v for pi, v in ob.props}
        check(list(d) in (["BasePolygon2D", "Center", "AddOn"], ["BasePolygon2D", "Center", "AddOn", "Rotation"]),
              f"zone file: unexpected TMapArea props {list(d)}")
        addon = nb.objects[d["AddOn"].v.index]
        props = [(nb.pname(pi), Str(nb.strings[v.v].decode("latin-1"), v.tag) if v.tag in (0x07, 0x1C) else v)
                 for pi, v in addon.props]
        out.append(([x.v for x in d["BasePolygon2D"].v], d["Center"].v, nb.cname(addon.cls), props,
                    d["Rotation"].v if "Rotation" in d else None))
    return out


def zone_prop(area: ZoneArea, name: str) -> object:
    return next((v.text if isinstance(v, Str) else v.v for k, v in area[3] if k == name), None)


def zone_areas_graph(areas: list[ZoneArea]) -> list[Node]:
    """DeploymentZone / CommandZone file (HUR's out/ files): a TMapAreaSet, one TMapArea per zone with a closed
    BasePolygon2D, its Center (vec3), the zone add-on (Name, Ranking, GUID, AllianceNum | Points ...) and an
    optional Rotation."""
    return [Node("TMapAreaSet", [("Areas", [Node("TMapArea", [
        ("BasePolygon2D", [Value(0x21, (float(x), float(y))) for x, y in poly]),
        ("Center", Value(0x0B, tuple(float(c) for c in center))),
        ("AddOn", Node(cls, addon)),
        *([("Rotation", f32(rot))] if rot is not None else [])]) for poly, center, cls, addon, rot in areas])])]


# --------------------------------------------------------------------------- playable zone and camera paths

def playable_zone_graph(polygon: list[tuple[float, float]], center: tuple[float, float, float]) -> list[Node]:
    """TMapAreaSet with one TMapArea: a closed BasePolygon2D (float2 list) and its Center (vec3)."""
    return [Node("TMapAreaSet", [("Areas", [Node("TMapArea", [
        ("BasePolygon2D", [Value(0x21, (float(x), float(y))) for x, y in polygon]),
        ("Center", Value(0x0B, tuple(float(c) for c in center)))])])])]


def read_playable_polygon(raw: bytes) -> list[tuple[float, float]]:
    """The ring of a PlayableZone file's one area, in world units (closed: the first vertex is repeated last)."""
    nb, _, _ = decode(raw)
    (area,) = [{nb.pname(pi): v for pi, v in ob.props} for ob in nb.objects if nb.cname(ob.cls) == "TMapArea"]
    return [(float(x), float(y)) for x, y in (v.v for v in area["BasePolygon2D"].v)]


def camera_paths_graph(paths: list[tuple[str, list, list]]) -> list[Node]:
    """One TCameraPath per (name, position keys, direction keys); each key is a TCameraPathKey vec3 Coord."""
    def keys(coords: list) -> list[Node]:
        return [Node("TCameraPathKey", [("Coord", Value(0x0B, tuple(float(c) for c in xyz)))]) for xyz in coords]
    return [Node("TCameraPath", [("PositionKeyVector", keys(pos)), ("DirectionKeyVector", keys(dirs)),
                                 ("Name", Str(name))]) for name, pos, dirs in paths]


# --------------------------------------------------------------------------- AI strategic grid

def ia_zone_graph(areas: list[tuple[list[Value], Value, list[tuple[str, object]]]]) -> list[Node]:
    """TMapAreaSet of AI strategic zones: per area its BasePolygon2D points (float2 Values), Center (vec3 Value)
    and the props of its TGameDesignAddOn_IAStratZoneInfos (Name, Ranking as Str; GUID as is)."""
    return [Node("TMapAreaSet", [("Areas", [Node("TMapArea", [
        ("BasePolygon2D", list(poly)), ("Center", center),
        ("AddOn", Node("TGameDesignAddOn_IAStratZoneInfos", addon))]) for poly, center, addon in areas])])]


def path_cache_graph(entries: list[tuple[Value | None, str, str, Value, Value, Value]]) -> list[Node]:
    """TIAStratZoneCostCacheMetadataHolder over one TZoneToZoneCost per (NavGraph or None, start name, end name,
    StartCenter, EndCenter, Cost); zones are named by their IAStratZoneInfos Name (a STRG entry). Stock caches
    hold one table per navigation graph (NavGraph absent, then e.g. 3), each with every unordered pair once."""
    return [Node("TIAStratZoneCostCacheMetadataHolder", [("Metadata", [Node("TZoneToZoneCost", [
        *([("NavGraph", nav)] if nav is not None else []),
        ("ZoneStartTag", Str(a)), ("ZoneEndTag", Str(b)), ("StartCenter", sc), ("EndCenter", ec), ("Cost", cost)])
        for nav, a, b, sc, ec, cost in entries])])]


def read_ia_grid(zone_file: str, cache_file: str):
    """A stock IAStratZone + IAStrat_PathCache pair as generator inputs: (areas, entries), see the two above."""
    return ia_grid(read_file(zone_file), read_file(cache_file), zone_file, cache_file)


def ia_grid(zone_raw: bytes, cache_raw: bytes, zone_file: str = "IAStratZone",
            cache_file: str = "IAStrat_PathCache"):
    """read_ia_grid of the two files' bytes (named in errors as `zone_file` and `cache_file`)."""
    nb, _, _ = decode(zone_raw)
    p = [{nb.pname(pi): v for pi, v in ob.props} for ob in nb.objects]

    def plain(v: Value) -> object:
        return Str(nb.strings[v.v].decode("latin-1"), v.tag) if v.tag in (0x07, 0x1C) else v

    areas = []
    for ob, d in zip(nb.objects, p):
        if nb.cname(ob.cls) == "TMapArea":
            addon = nb.objects[d["AddOn"].v.index]
            check(nb.cname(addon.cls) == "TGameDesignAddOn_IAStratZoneInfos", f"{zone_file}: unexpected add-on")
            areas.append((d["BasePolygon2D"].v, d["Center"],
                          [(nb.pname(pi), plain(v)) for pi, v in addon.props]))
    cb, _, _ = decode(cache_raw)
    entries = []
    for ob in cb.objects:
        if cb.cname(ob.cls) == "TZoneToZoneCost":
            d = {cb.pname(pi): v for pi, v in ob.props}
            check(set(d) <= {"NavGraph", "ZoneStartTag", "ZoneEndTag", "StartCenter", "EndCenter", "Cost"},
                  f"{cache_file}: unexpected TZoneToZoneCost props {sorted(d)}")
            entries.append((d.get("NavGraph"), cb.strings[d["ZoneStartTag"].v].decode("latin-1"),
                            cb.strings[d["ZoneEndTag"].v].decode("latin-1"),
                            d["StartCenter"], d["EndCenter"], d["Cost"]))
    return areas, entries


def area_name(area) -> str:
    return next(v.text for k, v in area[2] if k == "Name")


def area_bbox(area) -> tuple[float, float, float, float]:
    xs, ys = [pt.v[0] for pt in area[0]], [pt.v[1] for pt in area[0]]
    return min(xs), min(ys), max(xs), max(ys)


def ia_grid_subset(areas: list, entries: list, box: tuple[float, float, float, float]) -> tuple[list, list]:
    """The part of a map's AI grid (read_ia_grid's areas and entries) under a rectangular playable zone `box`
    (x0, y0, x1, y1): the areas whose tile lies inside it, and the path-cache entries between two of them, in their
    order. These are the ia_zone_graph and path_cache_graph inputs of a playable zone smaller than the map
    (gates.check_grid_subset holds the cut to the tile-aligned convention, and the kept grid to stock's rule)."""
    x0, y0, x1, y1 = box
    kept = [a for a in areas if x0 <= area_bbox(a)[0] and area_bbox(a)[2] <= x1
            and y0 <= area_bbox(a)[1] and area_bbox(a)[3] <= y1]
    names = {area_name(a) for a in kept}
    return kept, [e for e in entries if e[1] in names and e[2] in names]
