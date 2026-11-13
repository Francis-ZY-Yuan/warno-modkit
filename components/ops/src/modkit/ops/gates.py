"""The Operation gates: checks a build runs on its own output before anything is installed.

Each gate raises ``modkit.core.gates.CheckError`` on a broken rule and returns a count or a line for the build log;
``modkit.ops.build`` runs them in order, each through ``modkit.core.gates.run_gate`` so a profile can hold a
reviewed-pending entry for one:

1. strings: ``check_strings``;
2. every generated ndfbin: ``check_canonical``, ``check_shapes`` and the game's load-time property rules
   (``modkit.core.ndfrules.check_file``);
3. the bindings and the script: ``check_binding``, ``check_tokens`` (the dialog-button INGAME dictionary included),
   ``check_references``, the arrivals and tiers (``check_arrivals``, ``check_tiers``), ``check_objective_pins``,
   ``check_never_finishing``, ``check_end_funnel``, ``check_empty_group_guard``, ``check_dialog_text``,
   ``check_rules``, ``check_zone_tags``, ``check_smart_orders``, ``check_prod_menu_switch``, ``check_script_effects``
   (every effect the script launches is a self-contained GameFx effect), ``check_created_in_zone`` (every unit the
   script creates stands inside the playable zone);
4. every re-keyed file differs from stock only by its dump rows: ``check_dump_diff``;
5. the package is scenario-only and ships no Gameplay file: ``check_package``; the Definition pack is in build
   210942's layout, every .txn with its .txn.tag and a .dbg of one line per object (``check_definition_layout``),
   every tag holding the ConfigHash the game computes for its transaction (``check_config_hashes``); and
   every class and property the build ships is one the stock files of its kind hold (``check_stock_classes``);
6. every written pack reads back (``modkit.ops.packs.verify_packs``).

A profile's extra gates (``modkit.ops.profile.ExtraGate``) hold what only some ops generate; the driver runs none of
these unless a profile names them: the Details generators against stock (``check_details_generators``), the AI grid
under the playable zone (``check_grid``: stock's rule; ``check_grid_subset``: a generator's tile-aligned cut), the
zones and arrivals (``check_zone_layout``: stock's clauses, plus the generator conventions a profile asks for), no
leftover template name in a re-keyed or generated file (``check_no_template_name``), every named unit against the
unit database (``check_units`` over ``unit_database``), the Operation's menu order against stock's
(``check_menu_order`` over ``stock_menu_orders``), and the batteries a script creates for the player's fires
(``check_fire_range``: in the player's alliance, every target in range from where they stand). ``grid_gate``,
``zone_layout_gate``, ``template_name_gate``, ``unit_gate``, ``menu_order_gate`` and ``fire_range_gate`` are
ready-made extra gates: they read the Details and other files the build plans to ship.

Stock counts and object numbers in this module's comments are build 201602's unless they name 210942 (build 210942
added one stock scenario, CampagneStrat_Invasion_of_Cuba, and two objects ahead of each stock script's root: see
modkit.ops.script); the stock tests hold every gate to the extraction's own stock.
"""
from __future__ import annotations

import functools
import glob
import hashlib
import math
import os
import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Iterable, Mapping, NamedTuple, Sequence

from modkit.core import dbg, ndfbin, ndfrules, paths, trad, txntag
from modkit.core.gates import CheckError, check, check_fixture_text
from modkit.core.models import LANGS, StringTable
from modkit.core.names import unit_path
from modkit.core.ndfbin import Value
from modkit.core.packaging import is_gameplay_file
from modkit.ops.files import SETUP_FIX, read_file
from modkit.ops.bricks import NAME_PROP
from modkit.ops.graph import TRUE, Imp, Node, all_values, build_graph, decode, nodes_of, prop_nodes, walk
from modkit.ops.items import Item
from modkit.ops.leveldesign import GD_TAG_CLASS, LD_FILE, TAG_ID, ZONE_FILES, LdItem, read_ld_items
from modkit.ops.rekey import DBG, DEF_EXTS, TAG, TAG_CLASS, TXN, DumpRow, def_entry, def_path
from modkit.ops.script import BRICK_DEFAULT, BRICK_FORCE_HIDE, PROD_MENU_SWITCH
from modkit.ops.strings import StringError, check_glyphs, check_parity, check_titles, stock_chars
from modkit.ops.zones import (
    area_bbox, as_f32, camera_paths_graph, heading, ia_grid, ia_grid_subset, ia_zone_graph, path_cache_graph,
    playable_zone_graph, point_in_polygon, polygon_centroid, read_ia_grid, read_playable_polygon, read_zone_areas,
    zone_areas_graph, zone_prop,
)

if TYPE_CHECKING:
    from modkit.ops.profile import Content

# --------------------------------------------------------------------------- strings (gate 1)

def check_strings(name: str, table: StringTable, dictionaries: Sequence[str], menu_tokens: Iterable[str],
                  stock: Callable[[str], Sequence[str]]) -> str:
    """Gate 1, every failure at once. The content `name`'s string table holds exactly `dictionaries`
    (modkit.ops.strings.payloads does not check names, and an empty .dic is unproven); then the parity, glyph and title
    gates of modkit.ops.strings. Each language with text is held to the characters of its stock dictionaries,
    `stock(lang)` (modkit.core.glossary.stock_dictionaries: the game's font has them), and fails without any; the
    title gate holds `menu_tokens` to 30 UTF-16 units in every language (a toolkit convention: strings.check_titles).
    """
    names, problems = set(table), []
    extra, missing = sorted(names - set(dictionaries)), sorted(set(dictionaries) - names)
    if extra or missing:
        problems.append(f"the table must hold exactly {list(dictionaries)}; unknown {extra}, missing {missing}")
    used = {lang for tokens in table.values() for texts in tokens.values() for lang, _ in texts.items()}
    langs = [lang for lang in LANGS if lang in used]
    dics = {lang: stock(lang) for lang in langs}
    problems += [f"no stock *-{lang}.dic in the extraction: the glyph gate has nothing to hold {lang} text to; "
                 f"{SETUP_FIX}" for lang in langs if not dics[lang]]
    chars = {lang: stock_chars(dics[lang]) for lang in langs if dics[lang]}
    menu_tokens = tuple(menu_tokens)
    for gate, *args in ((check_parity,), (check_glyphs, chars), (check_titles, menu_tokens)):
        try:
            gate(table, *args)
        except StringError as exc:
            problems.append(str(exc))
    if problems:
        raise StringError(f"{name}: the string table fails gate 1:" + "".join(
            f"\n  {line}" for problem in problems for line in problem.splitlines()))
    tokens = sum(len(t) for t in table.values())
    return (f"{tokens} tokens in {len(dictionaries)} dictionaries: parity OK; "
            + ", ".join(f"{lang} within the {len(chars[lang]):,} characters of {len(dics[lang])} stock {lang} "
                        "dictionaries" for lang in langs) + f"; {len(menu_tokens)} titles <= 30 UTF-16 units")


# --------------------------------------------------------------------------- LevelDesign binding


def check_binding(gd_raw: bytes, ld_raw: bytes) -> int:
    """Every GdItems tag's TAG_ID (its GUID) names exactly one LevelDesign item with the same Ranking/Name and a
    matching add-on type; every item has exactly one tag."""
    ld, _, _ = decode(ld_raw)
    items: dict[bytes, tuple[str, str, str]] = {}
    for ob in ld.objects:
        cls = ld.cname(ob.cls)
        if not cls.startswith("TGameDesignAddOn_"):
            continue
        p = {ld.pname(pi): v for pi, v in ob.props}
        guid = p["GUID"].v
        check(guid not in items, f"LevelDesign: duplicate GUID {ndfbin.fmt_guid(guid)}")
        items[guid] = (ld.strings[p["Ranking"].v].decode("latin-1"), ld.strings[p["Name"].v].decode("latin-1"),
                       cls[len("TGameDesignAddOn_"):])
    gd, _, _ = decode(gd_raw)
    exported = {i: path for path, i in ndfbin.tree_paths(gd, gd.exports)}
    bound: set[bytes] = set()
    for i, ob in enumerate(gd.objects):
        cls = gd.cname(ob.cls)
        if cls not in GD_TAG_CLASS.values():
            continue
        path = exported.get(i, f"#{i}")
        p = {gd.pname(pi): v for pi, v in ob.props}
        tag = p.get(TAG_ID)
        check(tag is not None and tag.tag == 0x1A, f"{path}: no {TAG_ID} GUID (build 210942's tag shape)")
        guid = tag.v
        check(guid in items, f"{path}: its {TAG_ID} matches no LevelDesign item")
        ranking, name, addon = items[guid]
        check(path == f"$/GDScript/GdItems/{ranking}/{name}", f"{path}: binds {ranking}/{name}")
        check(GD_TAG_CLASS[addon] == cls, f"{path}: {cls} bound to a {addon} add-on")
        check(guid not in bound, f"{path}: a second tag binds {ranking}/{name}")
        bound.add(guid)
    missing = sorted(f"{r}/{n}" for g, (r, n, _) in items.items() if g not in bound)
    check(not missing, f"LevelDesign items without a GdItems tag: {missing}")
    return len(bound)


# --------------------------------------------------------------------------- Details generators


def check_details_generators(zones: list[str], cams: list[str], grids: list[str], deploy: list[str]) -> int:
    """Each Details generator, fed a stock file's own values, rebuilds its image exactly: playable_zone_graph the
    PlayableZone files `zones`, camera_paths_graph the CamPaths files `cams`, ia_zone_graph and path_cache_graph the
    out/IAStratZone and out/IAStrat_PathCache files of each folder in `grids`, zone_areas_graph the DeploymentZone
    and CommandZone files `deploy`. Returns the number of files rebuilt."""
    for path in zones + cams:
        nb, _, image = decode(read_file(path))
        p = [{nb.pname(pi): v for pi, v in ob.props} for ob in nb.objects]
        if path in zones:
            check(len(p[0]["Areas"].v) == 1, f"{path}: expected one TMapArea")
            graph = playable_zone_graph([x.v for x in p[1]["BasePolygon2D"].v], p[1]["Center"].v)
        else:
            def coords(v: Value) -> list:
                return [p[x.v.index]["Coord"].v for x in v.v]
            graph = camera_paths_graph([(nb.strings[d["Name"].v].decode("latin-1"), coords(d["PositionKeyVector"]),
                                         coords(d["DirectionKeyVector"]))
                                        for ob, d in zip(nb.objects, p) if nb.cname(ob.cls) == "TCameraPath"])
        check(ndfbin.encode_image(build_graph(graph, [])) == image, f"{path}: the generator does not rebuild it")
    for d in grids:
        zone_file, cache_file = (os.path.join(d, "out", f) for f in ("IAStratZone.ndfbin", "IAStrat_PathCache.ndfbin"))
        areas, entries = read_ia_grid(zone_file, cache_file)
        for path, graph in ((zone_file, ia_zone_graph(areas)), (cache_file, path_cache_graph(entries))):
            check(ndfbin.encode_image(build_graph(graph, [])) == decode(read_file(path))[2],
                  f"{path}: the generator does not rebuild it")
    for path in deploy:
        raw = read_file(path)
        check(ndfbin.encode_image(build_graph(zone_areas_graph(read_zone_areas(raw)), [])) == decode(raw)[2],
              f"{path}: the generator does not rebuild it")
    return len(zones) + len(cams) + 2 * len(grids) + len(deploy)


# Stock grids span their playable zone's bbox, but not to the unit: the tiles' extent overruns or falls short of it by
# up to 5,792 world units (TheKitzingenRuse), against stock tiles of 30,960 to 491,520 a side.
GRID_TOLERANCE = 6000.0


def _grid_extent(areas: list) -> tuple[float, float, float, float]:
    boxes = [area_bbox(a) for a in areas]
    return (min(b[0] for b in boxes), min(b[1] for b in boxes), max(b[2] for b in boxes), max(b[3] for b in boxes))


def check_grid(areas: list, entries: list, box: tuple[float, float, float, float], *,
               tolerance: float = GRID_TOLERANCE) -> tuple[int, int]:
    """Stock's rule for a shipped AI strategic grid (read_ia_grid's areas and path-cache entries) under a playable zone
    whose bbox is `box` (x0, y0, x1, y1): the tiles span the zone (the bbox of their union lies within `tolerance` of
    `box` on every side), and the path cache holds every unordered pair of the tiles once per navigation graph, and
    nothing else. Every stock challenge and Kreide layout with a playable zone passes (test_gates_stock); a whole-map
    grid under a smaller zone, which crashed a game while loading, does not. Returns (tiles, path costs)."""
    check(bool(areas), f"playable zone {box}: the AI grid has no tiles")
    extent = _grid_extent(areas)
    off = max(abs(e - b) for e, b in zip(extent, box))
    check(off <= tolerance, f"playable zone {box}: the AI grid spans {extent}, {off:,.0f} world off on one side "
                            f"(at most {tolerance:,.0f})")
    graphs = Counter(None if e[0] is None else e[0].v for e in entries)
    pairs = {(None if e[0] is None else e[0].v, *sorted(e[1:3])) for e in entries}
    check(len(pairs) == len(entries) and all(n == len(areas) * (len(areas) - 1) // 2 for n in graphs.values()),
          f"path cache: {dict(graphs)} entries per NavGraph for {len(areas)} tiles, want every unordered pair once")
    return len(areas), len(entries)


def check_grid_subset(areas: list, entries: list, box: tuple[float, float, float, float], *,
                      seam: float = 0.0) -> tuple[int, int]:
    """A generator's cut of a map's whole AI grid (read_ia_grid's areas and entries) for a smaller rectangular playable
    zone `box` (x0, y0, x1, y1): zones.ia_grid_subset keeps the tiles inside it and their path costs. The cut is the
    generators' convention, not stock's (most stock challenges put their playable zone's edges off the tile edges, or
    their tiles overlap or overrun it; test_gates_stock pins which): each edge of `box` is an edge of the grid's tiles,
    and the kept tiles cover `box` exactly. The kept grid must then keep stock's rule with no tolerance (check_grid).
    Returns (tiles, path costs) kept.

    `seam` is for a grid whose own tiles do not quite meet (StockMap.grid_seam: Twin Cities' small layout leaves gaps
    and overlaps of 320 world, 1/8 minimap px, between neighbours): tile edges that lie a chain of steps of at most
    `seam` apart count as one edge (seam_edges), and the tiles so moved must cover `box` exactly with no two
    overlapping; check_grid then allows `seam`. The edges of `box` itself stay exact tile edges. 0 (the default) is the
    exact rule above."""
    x0, y0, x1, y1 = box
    edges_x = {e for a in areas for e in area_bbox(a)[0::2]}
    edges_y = {e for a in areas for e in area_bbox(a)[1::2]}
    check({x0, x1} <= edges_x and {y0, y1} <= edges_y,
          f"playable zone {box}: its edges are not edges of the AI grid's tiles")
    kept, costs = ia_grid_subset(areas, entries, box)
    if not seam:
        covered = sum((b[2] - b[0]) * (b[3] - b[1]) for b in map(area_bbox, kept))
        check(covered == (x1 - x0) * (y1 - y0),
              f"playable zone {box}: the {len(kept)} AI tiles inside it do not cover it exactly")
        return check_grid(kept, costs, box, tolerance=0.0)
    boxes = [area_bbox(a) for a in kept]
    sx = seam_edges([e for b in boxes for e in b[0::2]], (x0, x1), seam)
    sy = seam_edges([e for b in boxes for e in b[1::2]], (y0, y1), seam)
    tiles = [(sx[b[0]], sy[b[1]], sx[b[2]], sy[b[3]]) for b in boxes]
    covered = sum((t[2] - t[0]) * (t[3] - t[1]) for t in tiles)
    overlap = any(min(a[2], b[2]) > max(a[0], b[0]) and min(a[3], b[3]) > max(a[1], b[1])
                  for i, a in enumerate(tiles) for b in tiles[i + 1:])
    check(covered == (x1 - x0) * (y1 - y0) and not overlap,
          f"playable zone {box}: the {len(kept)} AI tiles inside it do not cover it exactly (seams of up to "
          f"{seam:,.0f} world aside)")
    return check_grid(kept, costs, box, tolerance=seam)


def seam_edges(values: Iterable[float], fixed: Iterable[float], seam: float) -> dict[float, float]:
    """Tile edges on one axis -> the edge each stands for (check_grid_subset's `seam`): `values` and `fixed` (the box's
    edges) that lie a chain of steps of at most `seam` apart are one edge, the `fixed` value among them, else their
    least."""
    fixed = set(fixed)
    out: dict[float, float] = {}
    chain: list[float] = []
    for v in [*sorted(set(values) | fixed), None]:
        if chain and (v is None or v - chain[-1] > seam):
            edge = next((e for e in chain if e in fixed), chain[0])
            out.update(dict.fromkeys(chain, edge))
            chain = []
        if v is not None:
            chain.append(v)
    return out


# --------------------------------------------------------------------------- deployment and command zones, arrivals

# How close stock comes to the formulas a generator writes exactly, over the 18 stock layouts with a playable zone
# (test_gates_stock pins these): a zone's Center x/y to its polygon's area centroid (largest gap 0.075 world, 132
# zones), an arrival's Rotation to its Start -> End heading (0.0093 rad; 141 arrivals have a Rotation, 4 none) and its
# Position to the midpoint (0.53 % of the length, HoldUntilRelieved; all but 3 of 145 within a millionth of the
# length).
CENTROID_TOLERANCE = 0.1
HEADING_TOLERANCE = 0.01
MIDPOINT_TOLERANCE = 0.01


@dataclass
class ZoneLayout:
    """What check_zone_layout read back from the shipped files, for a mod's own rules on top."""
    items: list[dict]                              # every LevelDesign item (leveldesign.read_ld_items)
    deployment: dict[int, list[tuple[str, list]]]  # alliance -> its deployment zones' (Name, polygon)
    margins: list[tuple[float, str]]               # per zone: how far its bbox lies inside the box, '<add-on>/<Name>'
    arrivals: list[dict]                           # the reinforcement locations and aerial corridors


def check_zone_layout(ld_raw: bytes, dz_raw: bytes | None, cz_raw: bytes | None,
                      box: tuple[float, float, float, float], *, margin: float = 0.0, ground_z: float | None = None,
                      sides: Iterable[int] | None = None, exact: bool = False, dz_only: bool = False) -> ZoneLayout:
    """The deployment and command zones and the arrivals, read back from the shipped LevelDesign and zone files (None:
    no such file), under a playable zone whose bbox is `box` (x0, y0, x1, y1). Returns what it read.

    Stock's clauses, always checked; every stock challenge and Kreide layout with a playable zone passes them
    (test_gates_stock):
    - copies: each zone item has one area with its GUID and back, and the two agree on Name/Ranking, Rotation and
      AllianceNum/Points;
    - each area's polygon is a closed ring holding its item's Position, and its Center x/y lies within
      CENTROID_TOLERANCE of the polygon's area centroid;
    - every zone's bbox, and every arrival's Start and End, lie inside `box`;
    - an arrival's Rotation, when it has one, lies within HEADING_TOLERANCE of its Start -> End heading, and its
      Position within MIDPOINT_TOLERANCE of that length from the midpoint;
    - every player arrival ends in a player deployment zone or a command zone (arrival_violations).

    A generator's conventions, each checked only when asked for; test_gates_stock pins which stock layouts break each:
    - `margin`: every zone's bbox lies at least this far inside `box` (stock's closest zone: 2,199 world inside);
    - `ground_z`: every Center z equals it (stock zones sit at their own terrain height: 14 of 18 layouts differ from
      their playable zone's);
    - `sides`: deployment zones exist for exactly these alliances (Sledgehammer has none for the player);
    - `exact`: Center x/y, an arrival's Position and its Rotation are exactly the float32 area centroid, midpoint and
      heading a generator writes (no stock layout is exact);
    - `dz_only`: every arrival ends in a deployment zone of its own side, a command zone never being enough
      (arrival_violations without command zones, per side: 7 stock layouts end an entry in a command zone only, or
      give a side arrivals but no deployment zone)."""
    items = read_ld_items(ld_raw)
    x0, y0, x1, y1 = box
    deployment: dict[int, list[tuple[str, list]]] = {}
    margins: list[tuple[float, str]] = []
    for raw, addon, field_ in ((dz_raw, "DeploymentZone", "AllianceNum"), (cz_raw, "CommandPoints", "Points")):
        areas, lds = read_zone_areas(raw) if raw else [], [it for it in items if it["addon"] == addon]
        check(sorted(it["GUID"] for it in lds) == sorted(zone_prop(a, "GUID") for a in areas),
              f"{addon}: the LevelDesign items and the Details areas differ (by GUID)")
        for a in areas:
            poly, center, cls, _, rot = a
            it = next(i for i in lds if i["GUID"] == zone_prop(a, "GUID"))
            where = f"{addon}/{it['Name']}"
            check(cls == f"TGameDesignAddOn_{addon}", f"{where}: area add-on {cls}")
            check((it["Name"], it["Ranking"]) == (zone_prop(a, "Name"), zone_prop(a, "Ranking")),
                  f"{where}: Name/Ranking differ between the two copies")
            check(it["rot"] == rot, f"{where}: Rotation {it['rot']} in LevelDesign, {rot} in the area")
            check(it.get(field_) == zone_prop(a, field_), f"{where}: {field_} differs between the two copies")
            check(len(poly) >= 4 and poly[0] == poly[-1], f"{where}: the polygon is not a closed ring")
            check(point_in_polygon(*it["pos"], poly), f"{where}: item Position {it['pos']} lies outside its polygon")
            centroid = polygon_centroid(poly)
            check(max(abs(c - k) for c, k in zip(center[:2], centroid)) <= CENTROID_TOLERANCE,
                  f"{where}: Center {center} is not the polygon's centroid {centroid}")
            check(not exact or tuple(center[:2]) == as_f32(*centroid),
                  f"{where}: Center {center} is not exactly the float32 centroid (exact)")
            check(ground_z is None or center[2] == as_f32(ground_z)[0],
                  f"{where}: Center {center} is not the centroid at z {ground_z} (ground_z)")
            xs, ys = [q[0] for q in poly], [q[1] for q in poly]
            margins.append((min(min(xs) - x0, x1 - max(xs), min(ys) - y0, y1 - max(ys)), where))
            check(margins[-1][0] >= 0, f"{where}: bbox leaves the playable zone by {-margins[-1][0]:,.0f} world")
            check(margins[-1][0] >= margin,
                  f"{where}: bbox {margins[-1][0]:,.0f} world inside the playable zone, need {margin:,} (margin)")
            if addon == "DeploymentZone":
                deployment.setdefault(it.get(field_) or 0, []).append((it["Name"], poly))
    if sides is not None:
        want = sorted(set(sides))
        check(sorted(deployment) == want, f"deployment zones for alliances {sorted(deployment)}, want one or more for "
                                          f"{' and '.join(map(str, want))} and no other (sides)")
    arrivals = [it for it in items if it["addon"] in ARRIVALS]
    for it in arrivals:
        (sx, sy, _), (ex, ey, _) = it["StartPosition"], it["EndPosition"]
        where = f"{it['Ranking']}/{it['Name']}"
        check(all(x0 < x < x1 and y0 < y < y1 for x, y in ((sx, sy), (ex, ey))),
              f"{where}: Start or End outside the playable zone")
        mid, aim = ((sx + ex) / 2, (sy + ey) / 2), heading((sx, sy), (ex, ey))
        turn = None if it["rot"] is None else abs((it["rot"] - aim + math.pi) % (2 * math.pi) - math.pi)
        check(turn is None or turn <= HEADING_TOLERANCE,
              f"{where}: Rotation {it['rot']} is {turn} rad off the Start -> End heading {aim}")
        check(math.dist(it["pos"][:2], mid) <= MIDPOINT_TOLERANCE * math.dist((sx, sy), (ex, ey)),
              f"{where}: Position {it['pos']} is off the Start -> End midpoint {mid}")
        check(not exact or (it["pos"] == as_f32(*mid) and it["rot"] == as_f32(aim)[0]),
              f"{where}: Position/Rotation are not the midpoint/heading of Start -> End (exact)")
    _, bad = arrival_violations(ld_raw, dz_raw, cz_raw)
    check(not bad, f"{len(bad)} player arrivals end outside every player deployment zone and command zone:\n  "
                   + "\n  ".join(bad))
    if dz_only:
        others = {it.get("NumAlliance") for it in arrivals if (it.get("NumAlliance") or 0) > 0}
        for side in (0, *sorted(others)):
            _, bad = arrival_violations(ld_raw, dz_raw, None, command_zones=False, side=side)
            check(not bad, f"{len(bad)} alliance-{side} arrivals end outside every deployment zone of their side "
                           f"(dz_only):\n  " + "\n  ".join(bad))
    return ZoneLayout(items, deployment, margins, arrivals)


PLAYABLE_FILE = "out/PlayableZone.ndfbin"
IA_GRID_FILES = ("out/IAStratZone.ndfbin", "out/IAStrat_PathCache.ndfbin")


def shipped_details(items: Iterable[Item], inner: str) -> bytes | None:
    """The bytes the build plans to ship as the Details file `inner` (None: it ships none)."""
    hits = [it for it in items if it.pack == "Details" and it.path == inner]
    return b"".join(hits[0].chunks()) if hits else None


def _shipped_playable_box(items: list[Item]) -> tuple[float, float, float, float]:
    raw = shipped_details(items, PLAYABLE_FILE)
    check(raw is not None, f"the mod ships no {PLAYABLE_FILE}")
    ring = read_playable_polygon(raw)
    xs, ys = [p[0] for p in ring], [p[1] for p in ring]
    return min(xs), min(ys), max(xs), max(ys)


def _fmt_box(box: tuple[float, float, float, float]) -> str:
    x0, y0, x1, y1 = box
    return f"({x0:,.0f}, {y0:,.0f})..({x1:,.0f}, {y1:,.0f})"


def grid_gate(items: list[Item], content: object) -> str:
    """An extra gate (profile.ExtraGate): stock's rule for the AI grid the mod ships (check_grid), under the playable
    zone it ships, both read from the planned Details bytes."""
    box = _shipped_playable_box(items)
    raws = [shipped_details(items, inner) for inner in IA_GRID_FILES]
    for inner, raw in zip(IA_GRID_FILES, raws):
        check(raw is not None, f"the mod ships no {inner}")
    tiles, costs = check_grid(*ia_grid(*raws, *IA_GRID_FILES), box)
    return f"{tiles:,} AI tiles and {costs:,} path costs under the shipped playable zone {_fmt_box(box)}"


def zone_layout_gate(items: list[Item], content: object) -> str:
    """An extra gate (profile.ExtraGate): check_zone_layout's stock clauses, no generator convention, on the
    LevelDesign and zone files the mod ships, under the playable zone it ships."""
    box = _shipped_playable_box(items)
    ld = shipped_details(items, LD_FILE)
    check(ld is not None, f"the mod ships no {LD_FILE}")
    layout = check_zone_layout(ld, shipped_details(items, ZONE_FILES["DeploymentZone"]),
                               shipped_details(items, ZONE_FILES["CommandPoints"]), box)
    closest = (f"closest: {min(layout.margins)[1]}, {min(layout.margins)[0]:,.0f} world inside" if layout.margins
               else "no zones")
    return (f"{len(layout.margins)} zones and {len(layout.arrivals)} arrivals laid out by stock's rules under the "
            f"shipped playable zone ({closest})")


# --------------------------------------------------------------------------- typed dumps: the re-keying and fixture gates

def typed_dump(raw: bytes, title: str) -> list[str]:
    """The typed dump of a CNDF file, or, for a .dbg source map (`title` ends in .dbg), its title then its text, one
    line per object (modkit.core.dbg)."""
    if title.endswith(f".{DBG}"):
        return [f"// {title}", *dbg.read_text(raw).splitlines()]
    nb, _, _ = decode(raw)
    return ndfbin.Dumper(nb, typed=True).dump(title, None).splitlines()


def dump_kind(inner: str) -> str:
    """The name a DumpRow's kinds give a Definition entry: '<Kind>' for its .txn, '<Kind>.txn.tag' and '<Kind>.dbg'
    (modkit.ops.rekey.dump_rows)."""
    entry = def_entry(inner)
    check(entry is not None, f"{inner}: not a Definition entry (NDF/Scenarios/<scenario>/<Kind>.<ext>)")
    _, kind, ext = entry
    return kind if ext == TXN else f"{kind}.{ext}"


def check_no_template_name(items: Iterable[Item], name: str, allow: Iterable[str] = ()) -> tuple[int, int]:
    """No re-keyed or generated file of a clone (an item with stock bytes or a fixture) still names its template: the
    typed dump, title line aside, holds `name` in no letter case, outside the `allow` names (the template's own
    resource names a clone keeps on purpose). Gate 4 (check_dump_diff) explains every line a re-keying changed; this
    catches a line it left unchanged that still points at the template's files. Byte copies are the template's files
    as they are and are not read. Returns (files read, allow-listed hits)."""
    allow, files, hits = tuple(allow), 0, 0
    for it in items:
        if it.stock is None and it.fixture is None:
            continue
        files += 1
        for line in typed_dump(b"".join(it.chunks()), it.path)[1:]:  # line 0 is the title
            stripped = line
            for kept in allow:
                hits += stripped.count(kept)
                stripped = stripped.replace(kept, "")
            check(name.lower() not in stripped.lower(), f"{it.path}: leftover {name}: {line.strip()}")
    return files, hits


def template_name_gate(name: str, allow: Iterable[str] = ()) -> Callable[[list[Item], object], str]:
    """check_no_template_name as a profile's extra gate (profile.ExtraGate's callable): no re-keyed or generated file
    names the template `name` outside the `allow` names. Returns the build log's line."""
    allow = tuple(allow)

    def gate(items: list[Item], content: object) -> str:
        files, kept = check_no_template_name(items, name, allow)
        return (f"{files} re-keyed or generated dumps without {name}"
                + (f" ({kept} allow-listed resource-name hits: {', '.join(allow)})" if kept else ""))
    return gate


def check_dump_diff(item: Item, rows: list[DumpRow]) -> tuple[list[str], set[str]]:
    """Every new dump line must equal the stock line with the applicable rows applied.

    `item` is a re-keyed Definition entry (path 'NDF/Scenarios/<scenario>/<Kind>.<ext>', chunks() and stock bytes);
    a .dbg is compared by its text. Returns (changed line pairs for the report, labels of the rows that fired).
    """
    kind = dump_kind(item.path)
    applicable = [r for r in rows if r.kinds is None or kind in r.kinds]
    new = typed_dump(b"".join(item.chunks()), item.path)
    old = typed_dump(item.stock, item.path)
    check(len(old) == len(new), f"{item.path}: dump has {len(new)} lines, stock {len(old)}")
    report, fired = [], set()
    for a, b in zip(old, new):
        want = a
        for r in applicable:
            want, n = re.subn(r.pattern, r.repl, want)
            if n:
                fired.add(r.label)
        check(want == b, f"{item.path}: unexplained dump change\n  stock: {a.strip()}\n"
                         f"  want:  {want.strip()}\n  got:   {b.strip()}")
        if a != b:
            report.append(f"    -{a.strip()}\n    +{b.strip()}")
    return report, fired


def check_fixture(item: Item, path: str, *, bless: bool, summary: bool, root: str) -> str:
    """The typed dump of a generated entry must equal the expected text in `path`, kept next to the generator.

    `item` is a planned entry (path, chunks()). With `summary` (a file of thousands of entries) the expected text is
    the dump's head, an object census, the STRG table and the full dump's SHA-256. With `bless` the text is written
    to `path` instead of compared. The comparison is modkit.core.gates.check_fixture_text; its messages name `path`
    relative to `root`."""
    nb, hdr, _ = decode(b"".join(item.chunks()))
    text = ndfbin.Dumper(nb, typed=True).dump(item.path, hdr)
    if summary:
        lines = text.split("\n")
        head = lines[:lines.index("// ---- objects") + 1] if "// ---- objects" in lines else lines[:8]
        text = "\n".join(head + [
            f"// {len(nb.objects)} objects: {dict(Counter(nb.cname(o.cls) for o in nb.objects))}",
            f"// STRG ({len(nb.strings)}): " + ", ".join(s.decode("latin-1") for s in nb.strings),
            f"// SHA-256 of the full typed dump: {hashlib.sha256(text.encode('utf-8')).hexdigest()}", ""])
    return check_fixture_text(path, text, bless=bless, label=os.path.relpath(path, root), subject=f"{item.path}: dump")


# --------------------------------------------------------------------------- the generated files' table layout

IMPORT_RULES = ("trie", "preorder")
CAMERA_PATH = "TCameraPath"   # a camera paths file's path object: each one an unexported root (check_canonical)


def check_canonical(raw: bytes, shared: frozenset[str], what: str, *, import_rule: str) -> None:
    """Table layout of a generated file read back: CLAS/PROP/STRG and import indices in first-use order, TRAN = IMPR
    then EXPR preorder, PROP owners (one per (name, class) except `shared` names, owned by their first class), ref
    classes, TOPO = exported + unreferenced, one CHNK, a single unexported root (#0). A camera paths file is the one
    stock layout with more: one unexported root per path, every root a TCameraPath and #0 the first (all 35 stock
    CamPaths_LevelDesign files hold two paths or more, each its own root).

    `import_rule` is the IMPR tree's rule. 'trie', stock's: the tree is the trie of the import paths inserted in index
    order, so when first uses interleave two folders, later imports join the earlier folder's node (TheWingedHussars
    lists #7-#11 under GFX/Unit beside #1-#2, after #3-#6 in GFX/EffectCapacity; all 29 stock GDScripts keep the trie
    rule); graph.build_graph builds that trie. 'preorder': the tree's preorder is the index order, which holds only
    while first uses never interleave folders. Neither rule implies the other: 'preorder' rejects interleaved
    folders, which stock writes, and admits a folder written twice, which 'trie' rejects."""
    check(import_rule in IMPORT_RULES, f"import_rule {import_rule!r}: one of {IMPORT_RULES}")
    nb, _, _ = decode(raw)
    seen: dict[str, list[int]] = {"CLAS": [], "PROP": [], "STRG": [], "IMPR": [], "TRAN": []}

    def use(table: str, k: int) -> None:
        if k not in seen[table]:
            seen[table].append(k)

    first_owner: dict[bytes, int] = {}
    for ob in nb.objects:
        use("CLAS", ob.cls)
        for pi, v in ob.props:
            use("PROP", pi)
            name, owner = nb.props[pi]
            want = first_owner.setdefault(name, ob.cls) if name.decode("latin-1") in shared else ob.cls
            check(owner == want, f"{what}: PROP {name!r} owned by {nb.cname(owner)}, expected {nb.cname(want)}")
            for x in ndfbin.iter_values(v):
                if x.tag in (0x07, 0x1C):
                    use("STRG", x.v)
                elif x.tag == 0x09 and x.v.kind == ndfbin.REF_IMPORT:
                    use("IMPR", x.v.index)
                elif x.tag == 0x09:
                    check(x.v.cls == nb.objects[x.v.index].cls, f"{what}: ref to #{x.v.index} has a wrong class")

    def walk_tree(nd: ndfbin.Node | None, out: list[int]) -> None:
        if nd is not None:
            use("TRAN", nd.tran)
            if nd.obj != ndfbin.NONE_IDX:
                out.append(nd.obj)
            for kid in nd.children:
                walk_tree(kid, out)

    import_order: list[int] = []
    walk_tree(nb.imports, import_order)
    walk_tree(nb.exports, [])
    paths = {i: path for path, i in ndfbin.tree_paths(nb, nb.imports)}
    sizes = {"CLAS": len(nb.classes), "PROP": len(nb.props), "STRG": len(nb.strings),
             "IMPR": len(import_order) if import_rule == "preorder" else len(paths), "TRAN": len(nb.trans)}
    for table, order in seen.items():
        check(order == list(range(sizes[table])), f"{what}: {table} is not in first-use order")
    if import_rule == "preorder":
        check(import_order == list(range(len(import_order))), f"{what}: IMPR tree is not in index order")
    else:
        trie: dict[str, list] = {}  # name -> [import index or NONE_IDX, children], filled in index order
        for k in sorted(paths):
            cur, parts = trie, paths[k].split("/")[1:]
            for j, part in enumerate(parts):
                node = cur.setdefault(part, [ndfbin.NONE_IDX, {}])
                node[0] = k if j == len(parts) - 1 else node[0]
                cur = node[1]

        def want_shape(name: str, node: list) -> tuple:
            return name, node[0], [want_shape(n, kid) for n, kid in node[1].items()]

        def shape(nd: ndfbin.Node) -> tuple:
            return nb.tname(nd.tran), nd.obj, [shape(kid) for kid in nd.children]

        if nb.imports is not None:
            check(shape(nb.imports) == ("$", ndfbin.NONE_IDX, [want_shape(n, kid) for n, kid in trie.items()]),
                  f"{what}: IMPR tree is not the trie of the import paths in index order")
    referenced = {x.v.index for _, _, x in all_values(nb) if x.tag == 0x09 and x.v.kind == ndfbin.REF_OBJECT}
    exported = {i for _, i in ndfbin.tree_paths(nb, nb.exports)}
    free = set(range(len(nb.objects))) - referenced
    check(nb.topo == sorted(exported | free), f"{what}: TOPO is not exported + unreferenced")
    roots = sorted(free - exported)
    if not (roots and roots[0] == 0 and all(nb.cname(nb.objects[i].cls) == CAMERA_PATH for i in roots)):
        check(roots == [0], f"{what}: unexported roots {roots}, expected only #0")
    check(nb.chnk == [(0, len(nb.objects))], f"{what}: CHNK {nb.chnk}")


# --------------------------------------------------------------------------- references and loc tokens


def ref_targets(text: str, scenario: str, langs: Iterable[str]) -> list[str] | None:
    """The shipped entries ('Pack:inner/path') a Definition string naming `scenario` must resolve to. [] = known to
    need no file; None = unknown pattern (a gate failure). A .csv names one dictionary per language of `langs`."""
    s = re.escape(scenario)
    rules: list[tuple[str, Callable[[re.Match], list[str]]]] = [
        (rf"GameData:/Map/Scenario/{s}/(.+)\.ogg", lambda m: [f"Assets:Map/Scenario/{scenario}/{m[1]}.ess"]),
        (rf"ScenariosData:/{s}/(.+)\.png", lambda m: [f"Assets:PC/Texture/{scenario}/{m[1]}.tgv"]),
        (rf"ScenariosData:/{s}/(.+)\.webm", lambda m: [f"Assets:PC/Video/{scenario}/{m[1]}.vid",
                                                        f"GameData:Map/Scenario/{scenario}/{m[1]}.webm"]),
        (rf"ScenariosData:/{s}/(.+)\.csv",
         lambda m: [f"Assets:Localisation/{scenario}/{m[1]}-{lang}.dic" for lang in langs]),
        (rf"Scenarios/{s}_Details\.dat", lambda m: ["Details:*"]),
        # a transaction's BaseName: ScenarioInfo names its ScenarioLoader, the ScenarioLoader its GDScript
        (rf"Scenarios/{s}/(\w+)\.txn", lambda m: [f"Definition:{def_path(m[1], TXN, scenario)}"]),
        (rf"ScenariosData:/{s}/(Scenario|MapPack|Trophy)\.ndf", lambda m: []),  # cook-source names only
        (rf"ScenariosData:/{s}", lambda m: []),               # Details mount directory
        (rf"ScenariosData:/{s}/Scripting", lambda m: []),     # the GDScript transaction's source directory
        (rf"\$/ClusterMap/{s}/Load", lambda m: []),           # export inside the ScenarioLoader itself
        (s, lambda m: []),                                     # ScenarioInfo Name/Path, export names
    ]
    for pat, fn in rules:
        m = re.fullmatch(pat, text)
        if m:
            return fn(m)
    return None


def check_references(items: list[Item], scenario: str, langs: Iterable[str]) -> int:
    """Every Definition string naming `scenario` resolves to a shipped entry (ref_targets). A GameData .webm may ship
    as a loose file instead: it matches by file name. Returns the number of references resolved."""
    shipped = {f"{it.pack}:{it.path}" for it in items}
    packs = {it.pack for it in items}
    shipped |= {f"GameData:Map/Scenario/{scenario}/Scripting/Videos/{it.path.rsplit('/', 1)[-1]}"
                for it in items if it.pack == "Loose" and it.path.endswith(".webm")}
    langs = tuple(langs)
    n = 0
    for it in items:
        if it.pack != "Definition" or not it.path.endswith(f".{TXN}"):
            continue
        nb, _, _ = decode(b"".join(it.chunks()))
        for text in (s.decode("latin-1") for s in nb.strings + nb.trans):
            if scenario not in text:
                continue
            targets = ref_targets(text, scenario, langs)
            check(targets is not None, f"{it.path}: no resolution rule for {text!r}")
            for t in targets:
                ok = t[:-2] in packs if t.endswith(":*") else t in shipped
                check(ok, f"{it.path}: {text!r} needs {t}, which is not shipped")
                n += 1
    return n


# Dialog button labels resolve in the game's dictionary list INGAME (stock INTERFACE_INGAME), never in the scenario's
# dictionaries: all 1,027 stock uses hold INTERFACE_INGAME tokens (build 210942; 974 on 201602). A scenario token there throws a dictionary error
# naming the token and the in-game list when the dialog opens.
INGAME_PROPS = frozenset({("TGDDescriptorCutsceneDialog", "TokenBoutonChoix0"),
                          ("TGDDescriptorCutsceneDialogWithMultipleChoice", "TokenBoutonChoix0"),
                          ("TGDDescriptorCutsceneDialogWithMultipleChoice", "TokenBoutonChoix1")})
# The scenario dictionaries each Definition kind's loc tokens resolve in.
DICTIONARY_USES = {"MapConfiguration": ("SCENARIO_DEFINITION",),
                   "GDScript": ("Scripting/Dialog", "Scripting/Localization")}


def split_tokens(nb: ndfbin.NdfBin) -> tuple[set[int], set[int]]:
    """(tokens the scenario's dictionaries must hold, tokens the game looks up in INGAME: INGAME_PROPS)."""
    ours, ingame = set(), set()
    for ob, pi, x in all_values(nb):
        if x.tag == 0x1D and nb.pname(pi) != "DicoToken":  # DicoToken names the dictionary
            key = (nb.cname(ob.cls), nb.pname(pi))
            (ingame if key in INGAME_PROPS else ours).add(int.from_bytes(x.v, "little"))
    return ours - {0}, ingame - {0}


@functools.cache
def ingame_keys(path: str) -> frozenset[int]:
    """The token hashes of the game's own INTERFACE_INGAME dictionary at `path` (one language)."""
    check(os.path.isfile(path), f"missing {paths.rel_source(path)}, the game's INTERFACE_INGAME dictionary: "
                                f"{SETUP_FIX}")
    with open(path, "rb") as fh:
        return frozenset(k for k, _ in trad.read_dic(fh.read()))


def ingame_misses(nb: ndfbin.NdfBin, path: str) -> list[str]:
    """The INGAME_PROPS tokens of `nb` that the game's INGAME dictionary at `path` lacks."""
    return sorted(ndfbin.token_unhash(t) or hex(t) for t in split_tokens(nb)[1] - ingame_keys(path))


def check_tokens(items: list[Item], scenario: str, langs: Iterable[str], *, global_tokens: Iterable[str],
                 ingame_dic: str) -> tuple[int, int]:
    """Each loc token a Definition ndfbin uses exists in every language of `langs` of its scenario dictionaries
    (DICTIONARY_USES), or is one of `global_tokens` (stock tokens a mod uses without shipping them). A dialog button's
    token must instead be in the game's INGAME dictionary (INGAME_PROPS; `ingame_dic`: its path with '{lang}'),
    which the scenario's own dictionaries cannot extend. Returns (tokens, of which button tokens)."""
    by_path = {it.path: it for it in items if it.pack == "Assets" and it.path.endswith(".dic")}

    def keys(name: str, lang: str) -> set[int]:
        it = by_path.get(f"Localisation/{scenario}/{name}-{lang}.dic")
        check(it is not None, f"missing dictionary {name}-{lang}")
        return {k for k, _ in trad.read_dic(b"".join(it.chunks()))}

    global_keys = {ndfbin.token_hash(t) for t in global_tokens}
    langs = tuple(langs)
    n = buttons = 0
    for it in items:
        entry = def_entry(it.path) if it.pack == "Definition" else None
        if entry is None or entry[1] not in DICTIONARY_USES or entry[2] != TXN:
            continue
        kind = entry[1]
        nb, _, _ = decode(b"".join(it.chunks()))
        toks, ingame = split_tokens(nb)
        for lang in langs:
            have = set().union(*(keys(name, lang) for name in DICTIONARY_USES[kind])) | global_keys
            missing = sorted(ndfbin.token_unhash(t) or hex(t) for t in toks - have)
            check(not missing, f"{it.path}: tokens missing from {lang} dictionaries: {missing}")
            missing = ingame_misses(nb, ingame_dic.format(lang=lang))
            check(not missing, f"{it.path}: dialog button tokens missing from the game's {lang} INGAME dictionary: "
                               f"{missing} (the game looks button labels up there, not in the scenario's "
                               f"dictionaries: INGAME_PROPS)")
        n, buttons = n + len(toks) + len(ingame), buttons + len(ingame)
    return n, buttons


# --------------------------------------------------------------------------- the 'only stock shapes' gate

@dataclass
class Shapes:
    """What stock files contain, for the 'only stock shapes' gate."""
    classes: set[str] = field(default_factory=set)
    props: set[tuple[str, str, int]] = field(default_factory=set)       # (class, property, value tag)
    targets: set[tuple[str, str, str]] = field(default_factory=set)     # (class, property, target)
    before: set[tuple[str, str, str]] = field(default_factory=set)      # (class, a, b): a precedes b


def _ref_target(nb: ndfbin.NdfBin, ref: ndfbin.Ref, imports: dict[int, str]) -> str:
    if ref.kind == ndfbin.REF_IMPORT:
        return "import " + imports[ref.index].rsplit("/", 1)[0]
    return nb.cname(nb.objects[ref.index].cls)


def object_shapes(nb: ndfbin.NdfBin, i: int, imports: dict[int, str]) -> Shapes:
    ob, sh = nb.objects[i], Shapes()
    cls = nb.cname(ob.cls)
    names = [nb.pname(pi) for pi, _ in ob.props]
    sh.classes.add(cls)
    sh.before.update((cls, a, b) for k, a in enumerate(names) for b in names[k + 1:])
    for name, (_, v) in zip(names, ob.props):
        sh.props.add((cls, name, v.tag))
        sh.targets.update((cls, name, _ref_target(nb, x.v, imports))
                          for x in ndfbin.iter_values(v) if x.tag == 0x09)
    return sh


def survey_shapes(patterns: tuple[str, ...], minimum: int) -> tuple[Shapes, int]:
    """Union of object shapes over the stock files matching `patterns` (at least `minimum` files)."""
    paths = sorted({p for pat in patterns for p in glob.glob(pat)})
    check(len(paths) >= minimum, f"shape gate: {len(paths)} stock files match {patterns}, expected {minimum}+")
    total = Shapes()
    for p in paths:
        nb, _, _ = decode(read_file(p))
        imports = {i: path for path, i in ndfbin.tree_paths(nb, nb.imports)}
        for i in range(len(nb.objects)):
            sh = object_shapes(nb, i, imports)
            for f in ("classes", "props", "targets", "before"):
                getattr(total, f).update(getattr(sh, f))
    return total, len(paths)


def check_shapes(raw: bytes, stock: Shapes, what: str) -> int:
    """Every class, (class, property, tag), reference target and property order occurs in stock."""
    nb, _, _ = decode(raw)
    imports = {i: path for path, i in ndfbin.tree_paths(nb, nb.imports)}
    for i in range(len(nb.objects)):
        sh = object_shapes(nb, i, imports)
        where = f"{what} #{i} {nb.cname(nb.objects[i].cls)}"
        check(sh.classes <= stock.classes, f"{where}: class not in stock files")
        check(sh.props <= stock.props, f"{where}: property/tag not in stock: {sorted(sh.props - stock.props)}")
        check(sh.targets <= stock.targets,
              f"{where}: reference target not in stock: {sorted(sh.targets - stock.targets)}")
        bad = [(a, b) for c, a, b in sh.before if (c, b, a) in stock.before and (c, a, b) not in stock.before]
        check(not bad, f"{where}: property order differs from stock: {bad}")
    return len(nb.objects)

# --------------------------------------------------------------------------- arrivals, tiers and zones (gate 3)
# A content's player arrivals and zones, read from the shipped Details files where the game reads them.

ARRIVALS = ("ReinforcementLocation", "AerialCorridor")
STOCK_ARRIVALS = ("Every stock player RL/AC End lies in one (83/83: 57 RL and 26 AC in the 16 challenges and 6 "
                  "multiplayer layouts); an op whose Ends did not saw nothing bought arrive")


def zone_polygons(raw: bytes | None) -> list[tuple[str, int, list]]:
    """(Name, alliance, polygon) of every area of a shipped DeploymentZone or CommandZone ndfbin (read_zone_areas):
    the polygons the game's zone managers load and test. The alliance is the AllianceNum (absent: 0)."""
    return [(zone_prop(a, "Name"), zone_prop(a, "AllianceNum") or 0, a[0]) for a in read_zone_areas(raw)] if raw else []


def nearest_on_polygon(x: float, y: float, poly: Sequence) -> tuple[float, tuple[float, float]]:
    """(distance, point) from (x, y) to the nearest point of the ring `poly` (closed: first vertex repeated)."""
    best = (float("inf"), (x, y))
    for (ax, ay), (bx, by) in zip(poly, poly[1:]):
        dx, dy = bx - ax, by - ay
        t = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / (dx * dx + dy * dy))) if dx or dy else 0.0
        q = (ax + t * dx, ay + t * dy)
        best = min(best, (((x - q[0]) ** 2 + (y - q[1]) ** 2) ** 0.5, q))
    return best


def compass(dx: float, dy: float) -> str:
    """The 8-point direction of (dx, dy) in world units, where y grows southward (no axis flip)."""
    return ("E", "SE", "S", "SW", "W", "NW", "N", "NE")[round(math.atan2(dy, dx) / (math.pi / 4)) % 8]


def arrival_violations(ld_raw: bytes, dz_raw: bytes | None, cz_raw: bytes | None, command_zones: bool = True,
                       skip: Iterable[str] = (), side: int = 0) -> tuple[dict[str, int], list[str]]:
    """({add-on: entries checked}, one line per ReinforcementLocation or AerialCorridor of alliance `side` (0, the
    default: the player's) whose End lies in no DeploymentZone of that side and no CommandPoints zone), read from
    shipped bytes: the RL/AC items from out/LevelDesign.ndfbin (`ld_raw`), the zone polygons from
    out/DeploymentZone.ndfbin and out/CommandZone.ndfbin (None: no such file), which is what the game loads. With
    `command_zones` False, a command zone does not count (check_arrivals' stricter rule). Entries named in `skip` are
    neither counted nor checked (check_arrivals skips the content's tiered arrivals in its command-zone-only rule:
    gate 3 tiers holds them to the tier rule).

    Why: every tick the game gives each corridor whose End lies inside a deployment- or command-zone polygon the
    alliance of that zone's owner, and a team produces only from corridors of its alliance. Stock: all 83 player
    entries of the 16 challenges and 6 multiplayer layouts end in a player DZ (72) or a CZ (11: BlackHorsesLastStand,
    Marauders AutoName_2, TheWingedHussars, six Kreide RLs), so a CZ counts too. In play, ops whose Ends lay far
    outside every player deployment zone got no land unit bought in battle, though their aircraft arrived.

    An entry's side is its NumAlliance (absent: 0, the player's). -1 (stock multiplayer, either side) is the player's
    unless the End lies only in other alliances' DZs: the tick update then gives the entry that alliance (55 stock -1
    entries), and it counts as theirs."""
    dz, cz = zone_polygons(dz_raw), zone_polygons(cz_raw) if command_zones else []
    own_dz = [(name, poly) for name, s, poly in dz if s == side]
    whose = "player" if side == 0 else f"alliance-{side}"
    counts, bad, skip = dict.fromkeys(ARRIVALS, 0), [], frozenset(skip)
    for it in read_ld_items(ld_raw):
        alliance = it.get("NumAlliance")
        if it["addon"] not in ARRIVALS or it["Name"] in skip:
            continue
        x, y = it["EndPosition"][:2]
        sides = {s for _, s, poly in dz if point_in_polygon(x, y, poly)}
        if alliance == -1:
            mine = side in sides if sides and 0 not in sides else side == 0
        else:
            mine = (alliance or 0) == side
        if not mine:
            continue
        counts[it["addon"]] += 1
        if side in sides or any(point_in_polygon(x, y, poly) for _, _, poly in cz):
            continue
        where = (f"{it['Name']}: End ({x:,.0f}, {y:,.0f}) lies in no {whose} deployment zone"
                 + (" and no command zone" if command_zones else ""))
        if own_dz:
            (dist, (qx, qy)), name = min((nearest_on_polygon(x, y, poly), name) for name, poly in own_dz)
            where += f", {dist:,.0f} {compass(x - qx, y - qy)} of {name}"
        else:
            where += f" (there is no {whose} deployment zone)"
        bad.append(where + (f" (only in a DZ of alliance {', '.join(map(str, sorted(sides)))})" if sides else ""))
    return counts, bad


def has_deployment_phase(items: Sequence[LdItem]) -> bool:
    """Whether the content has a deployment phase: a player (alliance 0) deployment zone among its items."""
    return any(it.addon == "DeploymentZone" and not it.alliance for it in items)


def check_arrivals(items: Sequence[LdItem], details: Mapping[str, bytes] | None = None,
                   tiered: Iterable[str] = ()) -> tuple[int, int]:
    """Gate 3: with a player deployment zone, the player has a reinforcement location (ground units bought after the
    launch arrive there) and an aerial corridor (aircraft). Given the shipped Details files (`details`: inner path ->
    bytes), each player entry's End must also lie in a player deployment zone or a command zone (arrival_violations,
    stock's rule), and in a player deployment zone only (arrival_violations without the command zones): the corridor
    takes the alliance of the zone's owner every tick, so a command zone the enemy takes or contests gives it to the
    enemy, or to nobody (11 of stock's 83 entries rely on a command zone the player holds). The entries named in
    `tiered` (Content.tiered_arrivals) are exempt from that last rule only: they end in a command zone on purpose,
    and gate 3 tiers (check_tiers) holds them to the tier rule instead. Returns the player's (locations, corridors);
    (0, 0) without a deployment phase."""
    if not has_deployment_phase(items):
        return 0, 0
    mine = [it.addon for it in items if it.num_alliance in (None, 0, -1)]
    rl, ac = mine.count("ReinforcementLocation"), mine.count("AerialCorridor")
    check(rl > 0, "a player deployment zone but no player reinforcement location: units bought after the launch "
                  "have nowhere to arrive (every stock Operation with a deployment phase has one)")
    check(ac > 0, "a player deployment zone but no player aerial corridor: aircraft bought after the launch have "
                  "nowhere to arrive (every stock Operation but Marauders has one)")
    if details is not None:
        _, bad = arrival_violations(details[LD_FILE], details.get(ZONE_FILES["DeploymentZone"]),
                                    details.get(ZONE_FILES["CommandPoints"]))
        check(not bad, f"{len(bad)} player arrivals end outside every player deployment zone and command zone, so "
                       f"the game never gives them to the player:\n  " + "\n  ".join(bad)
              + f"\n{STOCK_ARRIVALS}. Widen or add a player deployment zone over each End.")
        _, cz_only = arrival_violations(details[LD_FILE], details.get(ZONE_FILES["DeploymentZone"]), None,
                                        command_zones=False, skip=tiered)
        check(not cz_only, f"{len(cz_only)} player arrivals end in a command zone only, which gives them to whoever "
                           f"owns the zone, or to nobody while it is contested:\n  "
                           + "\n  ".join(cz_only) + "\nCover each End with a player deployment zone too, "
                           "or, for a tier that should close, name the entry in "
                           "Content.tiered_arrivals (gate 3 tiers).")
    return rl, ac


# Gate 3 tiers, the tier rule. A tier is a set of player reinforcement locations whose Ends lie in a command zone only.
# Every tick the game gives each corridor the alliance of the owner of the first zone holding its End, deployment
# zones first (a DZ's owner is set once at load and never changes; a neutral zone gives the corridor to nobody), and
# a bought unit spawns at the usable Start nearest the click. So the script opens a tier by forcing its zone to the
# player's camp at load and closes it by handing the zone to the enemy's (SetCommandZoneOwnerAndForceConvergence,
# HoldUntilRelieved #107, Marauders #1134).
LOADING_DONE = "TGDDescriptorLoadingDone"
ZONE_OWNER = "TGDDescriptorSetCommandZoneOwnerAndForceConvergence"
TIER_RULE_FIX = ("A tiered entry is a ReinforcementLocation (NumAlliance omitted or 0) whose End lies in exactly one "
                 "command zone and no deployment zone; the zone is forced to the player's camp before LoadingDone "
                 "(deploy_phase's command_zones) and handed to the enemy's camp by a later "
                 "SetCommandZoneOwnerAndForceConvergence. "
                 "Every other player arrival ends in a player deployment zone, every aerial corridor included, and "
                 "at least one reinforcement location does (the permanent tier).")


def camp_of(nd: Node) -> str | None:
    """The export name (joueur, ordinateur_SOV, ...) of the camp an action names in its Camp property."""
    camp = dict(nd.props).get("Camp")
    return camp.export.rsplit("/", 1)[-1] if isinstance(camp, Node) and camp.export else None


def zone_owner_actions(roots: Iterable[Node], player: str, enemy: str) -> tuple[list[Node], list[Node]]:
    """(the load-time SetCommandZoneOwnerAndForceConvergence actions for the camp `player`, every later one for the
    camp `enemy`; camps by export name, as camp_of gives them). Load-time means placed before LoadingDone in the same
    Sequential, as deploy_phase's setup is in Main (HoldUntilRelieved #107 before #102's LoadingDone). An enemy
    forcing at load (anywhere under a child before LoadingDone) is not a hand-over: it would start the tier closed, so
    it counts for neither list."""
    load: list[Node] = []
    early: set[int] = set()
    for nd in walk(roots):
        if nd.cls == SEQ:
            kids = sub_actions(nd)
            done = next((k for k, kid in enumerate(kids) if kid.cls == LOADING_DONE), None)
            load += [kid for kid in kids[:done or 0] if kid.cls == ZONE_OWNER and camp_of(kid) == player]
            early |= {id(n) for n in walk(kids[:done or 0]) if n.cls == ZONE_OWNER}
    return load, [nd for nd in walk(roots) if nd.cls == ZONE_OWNER and camp_of(nd) == enemy
                  and id(nd) not in early]


def tier_violations(tiered: Iterable[str], roots: Iterable[Node], details: Mapping[str, bytes], player: str,
                    enemy: str) -> tuple[dict[str, int], list[str]]:
    """({what: count}, one line per breach of the tier rule, each tagged with its clause), from the script `roots` and
    the shipped Details files (`details`: inner path -> bytes), where the game reads them:
      tiers.1 every player ReinforcementLocation's End lies in a player deployment zone, or the entry is tiered;
      tiers.2 a tiered entry (named in `tiered`, Content.tiered_arrivals) is one ReinforcementLocation with NumAlliance
           omitted or 0, whose End lies in exactly one command zone and in no deployment zone of any side: a DZ is
           checked first and its owner never changes, so the tier would never close, and with NumAlliance -1 a zone
           the enemy holds would give it to the enemy;
      tiers.3 that command zone holds a tag of a load-time SetCommandZoneOwnerAndForceConvergence(`player`)
           (zone_owner_actions), or the tier starts closed;
      tiers.4 it also holds a tag of some SetCommandZoneOwnerAndForceConvergence(`enemy`) that runs after loading
           (zone_owner_actions: not one before LoadingDone), or the tier never closes;
      tiers.5 at least one player ReinforcementLocation, and every player AerialCorridor, ends in a player deployment
           zone: the permanent tier, and aircraft only there.
    Player entries are arrival_violations': NumAlliance omitted, 0 or -1, a -1 entry that ends only in another
    alliance's DZ excepted. Stock has no tier rule; its 11 entries that end in a command zone only
    each end in exactly one command zone and no deployment zone, as tiers.2 asks, but 10 of them have NumAlliance
    -1, and BlackHorsesLastStand and TheWingedHussars have no permanent tier (their aircraft arrive through a command
    zone)."""
    items = read_ld_items(details[LD_FILE])
    dz, cz = (zone_polygons(details.get(ZONE_FILES[k])) for k in ("DeploymentZone", "CommandPoints"))
    by_guid = {it["GUID"]: it for it in items}

    def zones_at(zones: list, x: float, y: float) -> list[tuple[str, int]]:
        return [(name, side) for name, side, poly in zones if point_in_polygon(x, y, poly)]

    def owned(actions: list[Node]) -> set[str]:
        out: set[str] = set()
        for nd in actions:
            for tag in prop_nodes(dict(nd.props).get("Positions")):
                it = by_guid.get(tag_guid(tag))
                if it is not None:
                    out |= {name for name, _ in zones_at(cz, *it["pos"][:2])}
        return out

    load, later = zone_owner_actions(roots, player, enemy)
    forced_at_load, handed_over = owned(load), owned(later)
    tiered, bad = frozenset(tiered), []
    arrivals = [it for it in items if it["addon"] in ARRIVALS]
    for name in sorted(tiered):
        hits = [it for it in arrivals if it["Name"] == name]
        if len(hits) != 1:
            bad.append(f"[tiers.2] {name}: tiered, but {len(hits)} reinforcement locations or aerial corridors carry "
                       f"the name, not one")
            continue
        it, (x, y) = hits[0], hits[0]["EndPosition"][:2]
        where = f"{name}: tiered, but"
        if it["addon"] != "ReinforcementLocation":
            bad.append(f"[tiers.2] {where} it is an {it['addon']}: aircraft arrive only in the permanent tier")
        if it.get("NumAlliance") not in (None, 0):
            bad.append(f"[tiers.2] {where} its NumAlliance is {it['NumAlliance']}: omit it or write 0, so a zone the "
                       f"enemy holds closes it for both sides")
        zones, deploy = zones_at(cz, x, y), zones_at(dz, x, y)
        if len(zones) != 1:
            bad.append(f"[tiers.2] {where} its End ({x:,.0f}, {y:,.0f}) lies in {len(zones)} command zones"
                       + (f" ({', '.join(n for n, _ in zones)})" if zones else "") + ", not exactly one")
        if deploy:
            bad.append(f"[tiers.2] {where} its End ({x:,.0f}, {y:,.0f}) lies in deployment zone "
                       f"{', '.join(n for n, _ in deploy)}, whose owner never changes: the tier would never close")
        if len(zones) == 1:
            zone = zones[0][0]
            if zone not in forced_at_load:
                bad.append(f"[tiers.3] {name}: its command zone {zone} is not forced to {player} at load (no "
                           f"SetCommandZoneOwnerAndForceConvergence({player}) before LoadingDone holds a tag in it), "
                           f"so the tier starts closed")
            if zone not in handed_over:
                bad.append(f"[tiers.4] {name}: its command zone {zone} is never handed to {enemy} (no "
                           f"SetCommandZoneOwnerAndForceConvergence({enemy}) holds a tag in it), so the tier never "
                           f"closes")
    permanent = 0
    for it in arrivals:
        side, (x, y) = it.get("NumAlliance"), it["EndPosition"][:2]
        sides = {s for _, s in zones_at(dz, x, y)}
        if side not in (None, 0, -1) or side == -1 and sides and 0 not in sides or it["Name"] in tiered:
            continue
        if 0 in sides:
            permanent += it["addon"] == "ReinforcementLocation"
        elif it["addon"] == "ReinforcementLocation":
            bad.append(f"[tiers.1] {it['Name']}: its End ({x:,.0f}, {y:,.0f}) lies in no player deployment zone, and "
                       f"the entry is not tiered (Content.tiered_arrivals)")
        else:
            bad.append(f"[tiers.5] {it['Name']}: an aerial corridor whose End ({x:,.0f}, {y:,.0f}) lies in no player "
                       f"deployment zone: aircraft arrive only in the permanent tier")
    if not permanent:
        bad.append("[tiers.5] no player reinforcement location ends in a player deployment zone: once every tier "
                   "closes, nothing bought arrives (the permanent tier)")
    counts = {"tiered": len(tiered), "permanent": permanent, "forced to the player at load": len(forced_at_load),
              "handed to the enemy": len(handed_over)}
    return counts, bad


def check_tiers(content: Content, roots: Iterable[Node], details: Mapping[str, bytes], player: str, enemy: str
                ) -> int:
    """Gate 3 tiers: with a deployment phase, tier_violations finds nothing for the content's tiered arrivals
    (Content.tiered_arrivals) in its script `roots` and shipped Details files (`details`), the camps `player` and
    `enemy` opening and closing the tiers. Without one, nothing arrives after the launch, and a content may name no
    tiered entry. Returns the number of tiered entries."""
    if not has_deployment_phase(content.items):
        check(not content.tiered_arrivals, f"tiered arrivals {list(content.tiered_arrivals)} but no deployment phase")
        return 0
    _, bad = tier_violations(content.tiered_arrivals, roots, details, player, enemy)
    check(not bad, f"{len(bad)} arrivals break the tier rule (gate 3 tiers):\n  " + "\n  ".join(bad)
          + f"\n{TIER_RULE_FIX}")
    return len(content.tiered_arrivals)


def polygons_overlap(a: Sequence, b: Sequence, eps: float = 1.0) -> bool:
    """Whether two closed rings share area: some stretch of one's boundary, or its centroid, lies inside the other
    more than `eps` world units from its edge. Each edge is cut where it meets the other ring (crossings, and the other
    ring's vertices on it), so every stretch is wholly inside, outside or on the other ring, and its midpoint says
    which; the centroids catch two equal rings. Rings that only share an edge or a vertex (BlackHorsesLastStand
    AutoName_2 beside AutoName_1 and zone_renfort_HQ) do not overlap."""
    def inside(pt: Sequence, poly: Sequence) -> bool:
        return point_in_polygon(pt[0], pt[1], list(poly)) and nearest_on_polygon(pt[0], pt[1], poly)[0] > eps

    def cuts(p: Sequence, q: Sequence, poly: Sequence) -> list[float]:
        dx, dy = q[0] - p[0], q[1] - p[1]
        ts = {0.0, 1.0}
        if not dx and not dy:
            return sorted(ts)
        for v in poly[:-1]:  # the other ring's vertices on this edge
            t = ((v[0] - p[0]) * dx + (v[1] - p[1]) * dy) / (dx * dx + dy * dy)
            if 0 < t < 1 and math.hypot(p[0] + t * dx - v[0], p[1] + t * dy - v[1]) <= eps:
                ts.add(t)
        for r, s in zip(poly, poly[1:]):  # its edges crossing this one
            ex, ey = s[0] - r[0], s[1] - r[1]
            den = dx * ey - dy * ex
            if den:
                t = ((r[0] - p[0]) * ey - (r[1] - p[1]) * ex) / den
                u = ((r[0] - p[0]) * dy - (r[1] - p[1]) * dx) / den
                if 0 < t < 1 and 0 <= u <= 1:
                    ts.add(t)
        return sorted(ts)

    def boundary_inside(ring: Sequence, other: Sequence) -> bool:
        for p, q in zip(ring, ring[1:]):
            ts = cuts(p, q, other)
            if any(inside((p[0] + (t0 + t1) / 2 * (q[0] - p[0]), p[1] + (t0 + t1) / 2 * (q[1] - p[1])), other)
                   for t0, t1 in zip(ts, ts[1:])):
                return True
        return False

    return (boundary_inside(a, b) or boundary_inside(b, a) or inside(polygon_centroid(list(a)), b)
            or inside(polygon_centroid(list(b)), a))


# The zone file each ZoneType's manager loads (0 Deploiement, 1 Commandement). TeamControleZone and UnitDansZone
# look their tags up in the ZoneType's file.
ZONE_TYPE_FILES = {0: ZONE_FILES["DeploymentZone"], 1: ZONE_FILES["CommandPoints"]}
ZONE_ADDONS = {"DeploymentZone": ZONE_FILES["DeploymentZone"], "CommandPoints": ZONE_FILES["CommandPoints"]}


def tag_guid(tag: object) -> bytes | None:
    """The LevelDesign GUID a GdItems tag names (its TAG_ID, as check_binding reads it)."""
    props = dict(tag.props) if isinstance(tag, Node) else {}
    guid = props.get(TAG_ID)
    return guid.v if isinstance(guid, Value) and guid.tag == 0x1A else None


def zone_tag_violations(roots: Iterable[Node], details: Mapping[str, bytes]) -> tuple[dict[str, int], list[str]]:
    """({check: cases}, one line per violation) of the zone tags of a script and its shipped Details files (`details`:
    inner path -> bytes; out/LevelDesign.ndfbin and the zone files), read where the game reads them:
      - every TeamControleZone Position, UnitDansZone Detecteurs entry and SetCommandZoneOwnerAndForceConvergence
        position names a LevelDesign item whose point lies inside exactly one polygon of its ZoneType's zone file
        (command zones for SetCommandZoneOwner). The game finds the zone by point-in-polygon and, when none holds the
        point, TeamControleZone stays false forever, SetCommandZoneOwner does nothing, and UnitDansZone counts every
        unit outside all zones, all without an error;
      - every DetectUnitDansDetecteur Detecteur is a CircularZone item with a radius: the query reads a radius, which
        only a CircularZone item has;
      - every zone item's own point lies inside its own polygon (the same-GUID area of its zone file): the zone
        conditions look the zone up by that point;
      - no two command-zone polygons share area: a unit's zone is one point-in-polygon result, so it counts
        for one of two overlapping zones only.
    Stock: in the 16 challenges, the 130 TeamControleZone, 4 UnitDansZone and 35
    SetCommandZoneOwner positions each lie in exactly one polygon and the 72 detectors are circles; in the 22 layouts
    (the challenges, Geisa 10vs10, Kreide's five), the 166 zone items lie in their own polygons and no two of the 111
    command zones overlap (BlackHorsesLastStand's three only share edges). The one stock miss is a strategic-campaign
    tag, CampagneStrat_Airborne Tags/tagzonepara, in no command zone."""
    items = {it["GUID"]: it for it in read_ld_items(details[LD_FILE])}
    areas = {inner: read_zone_areas(details[inner]) if details.get(inner) else [] for inner in ZONE_ADDONS.values()}
    counts, bad = dict.fromkeys(("zone lookups", "detectors", "zone items", "command zones"), 0), []

    def item_of(tag: object, what: str) -> dict | None:
        it = items.get(tag_guid(tag))
        if it is None:
            bad.append(f"{what} {getattr(tag, 'export', None) or tag!r} names no LevelDesign item")
        return it

    def resolve(tag: object, zone_type: int, what: str) -> None:
        counts["zone lookups"] += 1
        it = item_of(tag, what)
        if it is None:
            return
        where = f"{what} {it['Ranking']}/{it['Name']}"
        if zone_type not in ZONE_TYPE_FILES:
            bad.append(f"{where}: ZoneType {zone_type} has no zone file here (stock uses 1; 0 = deployment zones)")
            return
        inner, (x, y) = ZONE_TYPE_FILES[zone_type], it["pos"][:2]
        hits = [zone_prop(a, "Name") for a in areas[inner] if point_in_polygon(x, y, a[0])]
        if len(hits) != 1:
            bad.append(f"{where} at ({x:,.0f}, {y:,.0f}) lies in {len(hits)} polygons of {inner}"
                       + (f" ({', '.join(hits)})" if hits else "") + ", not exactly one")

    for nd in walk(roots):
        props = dict(nd.props)
        zone_type = props.get("ZoneType")
        zone_type = zone_type.v if isinstance(zone_type, Value) else 0
        if nd.cls == "TGDConditionTeamControleZone":
            resolve(props.get("Position"), zone_type, "TeamControleZone.Position")
        elif nd.cls == "TGDConditionUnitDansZone":
            for tag in prop_nodes(props.get("Detecteurs")):
                resolve(tag, zone_type, "UnitDansZone.Detecteurs")
        elif nd.cls == "TGDDescriptorSetCommandZoneOwnerAndForceConvergence":
            for tag in prop_nodes(props.get("Positions")):
                resolve(tag, 1, "SetCommandZoneOwnerAndForceConvergence.Positions")
        elif nd.cls == "TGDConditionDetectUnitDansDetecteur":
            counts["detectors"] += 1
            it = item_of(props.get("Detecteur"), "DetectUnitDansDetecteur.Detecteur")
            if it is not None and (it["addon"] != "CircularZone" or not it.get("RadiusGRU")):
                bad.append(f"DetectUnitDansDetecteur.Detecteur {it['Ranking']}/{it['Name']} is a {it['addon']} item, "
                           f"not a CircularZone with a radius")
    for it in items.values():
        if it["addon"] not in ZONE_ADDONS:
            continue
        counts["zone items"] += 1
        inner = ZONE_ADDONS[it["addon"]]
        mine = [a for a in areas[inner] if zone_prop(a, "GUID") == it["GUID"]]
        if len(mine) != 1:
            bad.append(f"{it['Ranking']}/{it['Name']}: {len(mine)} areas of {inner} carry its GUID, not one")
        elif not point_in_polygon(*it["pos"][:2], mine[0][0]):
            bad.append(f"{it['Ranking']}/{it['Name']}: its point ({it['pos'][0]:,.0f}, {it['pos'][1]:,.0f}) lies "
                       f"outside its own polygon")
    zones = areas[ZONE_ADDONS["CommandPoints"]]
    counts["command zones"] = len(zones)
    bad += [f"command zones {zone_prop(a, 'Name')} and {zone_prop(b, 'Name')} overlap"
            for k, a in enumerate(zones) for b in zones[k + 1:] if polygons_overlap(a[0], b[0])]
    return counts, bad


def check_zone_tags(roots: Iterable[Node], details: Mapping[str, bytes]) -> dict[str, int]:
    """Gate 3: zone_tag_violations finds nothing. Returns its counts."""
    counts, bad = zone_tag_violations(roots, details)
    check(not bad, f"{len(bad)} zone tags or zones the game would look up wrong, silently:\n  " + "\n  ".join(bad)
          + "\nPut each tag inside exactly one zone polygon (at its centre, say), use CircularZone items as "
          "detectors, and keep command zones apart.")
    return counts


# --------------------------------------------------------------------------- the script gates (gate 3)

def objective_pin_violations(roots: Iterable[Node]) -> tuple[int, list[Node]]:
    """(The GereObjectifs that show their map label (ShowEtiquette), those of them with neither a Position nor a
    non-empty UnitGroupPositionList to put it on): check_objective_pins' rule, without raising."""
    pinned, bad = 0, []
    for nd in walk(roots):
        if nd.cls != "TGDDescriptorGereObjectif":
            continue
        props = dict(nd.props)
        if props.get("ShowEtiquette") != TRUE:
            continue
        if props.get("Position") is None and not props.get("UnitGroupPositionList"):
            bad.append(nd)
        pinned += 1
    return pinned, bad


def check_objective_pins(roots: Iterable[Node]) -> int:
    """Gate 3: a GereObjectif that shows its map label (ShowEtiquette) has a Position or a non-empty
    UnitGroupPositionList to put it on. Without one the pin sits in the map corner (in play, both positionless
    counters of a probe did).

    A toolkit convention, stricter than stock: map-visible objectives are the house rule. In the 30 stock GDScripts,
    47 of the 52 positionless GereObjectifs leave ShowEtiquette out, counters included, but the other 5 fail this
    gate: 3 in DelayedRetribution and 2 in HoldUntilRelieved (test_gates_stock.ObjectivePins). Returns the number of
    objectives that show a pin."""
    pinned, bad = objective_pin_violations(roots)
    check(not bad, f"objectives show a map pin with no Position or UnitGroupPositionList, so it sits in the map corner: "
                   f"{[nd.export or f'<{nd.cls}>' for nd in bad]} (leave ShowEtiquette out, as stock does on "
                   f"positionless objectives)")
    return pinned


# Script actions that never finish by themselves: the game never reports them finished [[seteffect-never-finishes]].
# A SetEffect, a card, income or combat-group lock or a label holds only while its action lives: it ends when an
# ancestor finishes (a Competition's race), and its end takes the effect off again.
NEVER_FINISH = frozenset({"TGDDescriptorSetEffect", "TGDDescriptorDrawLabelOnPosition", "TGDDescriptorGiveIncomeToTeam",
                          "TGDDescriptorWaitForEver", "TGDDescriptorLockDeckUnit", "TGDDescriptorTriggerEndGame",
                          "TGDDescriptorLockIncome", "TGDDescriptorLockCombatGroup"})
MODIFY_UNIT = "TGDDescriptorModifyUnit"  # ModifyUnitSpeed and kin: finish once their whole group is gone
END_GAME = "TGDDescriptorTriggerEndGame"
SEQ, SIMUL, COMPETE = "TGDDescriptorSequential", "TGDDescriptorSimultaneous", "TGDDescriptorCompetition"
# Objectives finish only once they resolve and the chosen ActionsReussi/ActionsEchec has finished (an absent action
# finishes at once). Unresolved, they never finish.
OBJECTIVES = ("TGDDescriptorGereObjectif", "TGDDescriptorGereObjectifWithVariableOwner")
OBJECTIVE_ACTIONS = ("ActionsReussi", "ActionsEchec")
# The stock objectives that hold up the Sequential they sit in (never_finishing_violations, without this table: these
# two of the 168 stock objectives in the 31 GDScripts). Both are a phase gate, reviewed:
STOCK_BLOCKING_OBJECTIVES = frozenset({
    "odvaMtR9hm",  # Sledgehammer #373 Partie0/scripts/Objectives/Main_Lohra, Sequential#324 [1/3] before Simultaneous
    #                #374; both of its actions finish
    "CVcFybf9To",  # TheKitzingenRuse #339 in Simultaneous#326, Partie2's Launch_Main_Script_Sequence [1/3], before
    #                Simultaneous#327 (the AI's income); ActionsReussi is Partie3's sequence, which holds a LockIncome
    #                (#410), so it never finishes; ActionsEchec ends the game
})


def objective_name(nd: Node) -> str:
    """An objective's name for gate messages and the reviewed lists: its ObjectiveName token (58 stock
    GereObjectifWithVariableOwner set one), else its ObjectiveText token (every stock GereObjectif), else its
    export path."""
    props = dict(nd.props)
    for key in ("ObjectiveName", "ObjectiveText"):
        v = props.get(key)
        if isinstance(v, Value) and v.tag == 0x1D:
            return ndfbin.token_unhash(int.from_bytes(v.v, "little")) or v.v.hex()
    return nd.export or "?"


def node_label(nd: Node) -> str:
    """A node for a gate message: its class without TGDDescriptor, then an objective's name (GereObjectif(od_o1)), or
    its export's last part, or else the effect and the exported groups it names (SetEffect(UnitEffect_revealUnit,
    od_t80))."""
    short = nd.cls.removeprefix("TGDDescriptor")
    if nd.cls in OBJECTIVES:
        return f"{short}({objective_name(nd)})"
    if nd.export:
        return f"{short} {nd.export.rsplit('/', 1)[-1]}"
    props = dict(nd.props)
    bits = [props["Effet"].path.rsplit("/", 1)[-1]] if isinstance(props.get("Effet"), Imp) else []
    for key in ("Group", "UnitGroup", "Units", "GroupList"):
        spec = props.get(key)
        bits += [g.export.rsplit("/", 1)[-1] for g in (spec if isinstance(spec, list) else [spec])
                 if isinstance(g, Node) and g.export]
    return f"{short}({', '.join(bits)})" if bits else short


IF_THEN_ELSE, BRANCHES = "TGDDescriptorIfThenElse", ("EffetIfTrue", "EffetIfFalse")
FINISHES, STALLS, ENDS, WAITS = "finishes", "stalls", "ends the game", "waits on an objective"


def sub_actions(nd: Node) -> list[Node]:
    return [k for k in dict(nd.props).get("SubActions") or [] if isinstance(k, Node)]


def action_kids(nd: Node) -> list[Node]:
    """The actions `nd` may run: an IfThenElse's branches, an objective's ActionsReussi/ActionsEchec, else its
    SubActions."""
    if nd.cls == IF_THEN_ELSE or nd.cls in OBJECTIVES:
        props = dict(nd.props)
        return [b for name in (BRANCHES if nd.cls == IF_THEN_ELSE else OBJECTIVE_ACTIONS)
                if isinstance(b := props.get(name), Node)]
    return sub_actions(nd)


def finish_status(nd: Node, memo: dict[int, str], reviewed: frozenset[str] = frozenset()) -> str:
    """Whether `nd` FINISHES, never finishes (STALLS), never finishes because the game ends inside it (ENDS), or
    finishes only once an objective resolves (WAITS), from the runtime's rules (never_finishing_violations):
      - a NEVER_FINISH action stalls, but a TriggerEndGame ends;
      - an objective waits if an action it may choose (ActionsReussi/ActionsEchec; an absent one finishes at once)
        finishes or waits, else stalls if one stalls, else ends (both end the game: Gotterdammerung #138); one whose
        name (objective_name) is `reviewed` finishes;
      - a Sequential is its first child that does not finish (the rest never start), or finishes;
      - a Simultaneous stalls if any child stalls, else ends if any child ends, else waits if any child waits, else
        finishes;
      - a Competition finishes if any child does (it finishes with its first), else waits if any child waits, else
        ends if any child ends, else stalls (every child stalls);
      - an IfThenElse waits if either branch waits, else finishes if either branch does (an absent branch does at
        once), else stalls if either stalls (only one runs, and it may be that one), else ends;
      - anything else finishes: EncapsuleCutscene and the Cutscene* containers are not looked into.
    `memo` (by node id, for one `reviewed`) keeps shared nodes cheap; a cycle, which no script has, counts as
    finishing."""
    if id(nd) in memo:
        return memo[id(nd)]
    memo[id(nd)] = FINISHES
    if nd.cls in NEVER_FINISH:
        st = ENDS if nd.cls == END_GAME else STALLS
    elif nd.cls in OBJECTIVES:
        props = dict(nd.props)
        kids = [finish_status(b, memo, reviewed) if isinstance(b := props.get(name), Node) else FINISHES
                for name in OBJECTIVE_ACTIONS]
        st = (FINISHES if objective_name(nd) in reviewed else WAITS if FINISHES in kids or WAITS in kids
              else STALLS if STALLS in kids else ENDS)
    elif nd.cls in (SEQ, SIMUL, COMPETE):
        kids = [finish_status(k, memo, reviewed) for k in sub_actions(nd)]
        if nd.cls == SEQ:
            st = next((k for k in kids if k != FINISHES), FINISHES)
        elif nd.cls == SIMUL:
            st = next((k for k in (STALLS, ENDS, WAITS) if k in kids), FINISHES)
        else:
            st = FINISHES if not kids or FINISHES in kids else next((k for k in (WAITS, ENDS) if k in kids), STALLS)
    elif nd.cls == IF_THEN_ELSE:
        props = dict(nd.props)
        kids = [finish_status(b, memo, reviewed) if isinstance(b := props.get(name), Node) else FINISHES
                for name in BRANCHES]
        st = next((k for k in (WAITS, FINISHES, STALLS) if k in kids), ENDS)
    else:
        st = FINISHES
    memo[id(nd)] = st
    return st


def status_path(nd: Node, memo: dict[int, str], reviewed: frozenset[str] = frozenset()) -> str:
    """Why a container never finishes or waits: the chain of nodes with its status down to a NEVER_FINISH action
    (Simultaneous > SetEffect(UnitEffect_revealUnit, od_t80)) or to the objective it waits on
    (Simultaneous > GereObjectif(od_o1))."""
    st, chain = finish_status(nd, memo, reviewed), []
    while nd.cls not in NEVER_FINISH and not (st == WAITS and nd.cls in OBJECTIVES):
        chain.append(node_label(nd) if nd.cls in OBJECTIVES else nd.cls.removeprefix("TGDDescriptor"))
        nd = next(k for k in action_kids(nd) if finish_status(k, memo, reviewed) == st)
    return " > ".join([*chain, node_label(nd)])


def never_finishing_violations(roots: Iterable[Node], reviewed: Iterable[str] = STOCK_BLOCKING_OBJECTIVES
                               ) -> tuple[int, list[str]]:
    """(the NEVER_FINISH actions placed in a Sequential, Simultaneous or Competition, one line per misplaced node or
    ModifyUnit*). The script runtime moves a Sequential on only when its current child
    finishes; a Simultaneous finishes once all of its children have, and a Competition with its first. So an action
    that never finishes is misplaced:
      - with any node after it in a Sequential: that node never runs (seen in play: every enemy beat stopped at a
        reveal SetEffect after its first create);
      - inside a looping container (NbExecutions != 1) beside other nodes: the loop never comes round, so they never
        repeat (a loop of [WaitDuration 30, SetEffect, SetAmmo] forever);
    and a ModifyUnit* placed in a Sequential holds it until the unit group is gone (its end hook then undoes the
    modifier). The same holds for a container that never finishes (finish_status: a Sequential or Simultaneous with
    such a child, a Competition or IfThenElse whose every child or branch is one), so a node after a Simultaneous
    holding a SetEffect fails as a node after the SetEffect does. Two exemptions, both stock's:
      - nodes after a TriggerEndGame are not checked, since the game ends there (stock's one case, GloryOrAttrition
        #154, which an EncapsuleCutscene follows); likewise after a container that never finishes only because the
        game ends in it (Gotterdammerung Simultaneous#72, whose objective #138 ends the game either way, before the
        EncapsuleCutscene #73);
      - an action alone in its loop leaves nothing to repeat (the strategic-campaign tutorials' 25 pawn labels,
        Sequential(NbExecutions -1)[DrawLabelOnPosition], each raced in a Competition); a container alone in its
        loop likewise (no stock case).
    An objective, and a container that waits on one (finish_status WAITS), is misplaced the same way: what follows it
    in a Sequential, or beside it in a loop, waits until the objective resolves, if ever, and its chosen action
    finishes. An objective named in `reviewed` (the content's
    Content.blocking_objectives and STOCK_BLOCKING_OBJECTIVES) holds its Sequential on purpose and counts as
    finishing.
    With the stock table, all 31 stock GDScripts pass (304 such actions, 34 LockIncome and 3 LockCombatGroup among
    them, and 152 containers that never finish: 70 Sequential, 80 Simultaneous, 2 IfThenElse, none with a node after
    it; 168 objectives: 150 wait, 15 end the game and 3 stall, and 2 hold their Sequential, both in the table),
    and no stock ModifyUnit* (48) is in a Sequential. Not counted as never finishing: a forever loop (NbExecutions
    -1) of finishing nodes, and EncapsuleCutscene and Cutscene* contents (finish_status)."""
    found, bad, memo, reviewed = 0, [], {}, frozenset(reviewed)
    for nd in walk(roots):
        if nd.cls not in (SEQ, SIMUL, COMPETE):
            continue
        kids = sub_actions(nd)
        runs = dict(nd.props).get("NbExecutions")
        runs = 1 if runs is None else runs.v
        for k, kid in enumerate(kids):
            if nd.cls == SEQ and kid.cls.startswith(MODIFY_UNIT):
                bad.append(f"{node_label(kid)} is in a Sequential, which it holds until its whole group is gone")
            st, leaf = finish_status(kid, memo, reviewed), kid.cls in NEVER_FINISH
            found += leaf
            if st == FINISHES or not leaf and st == ENDS:
                continue
            why, after = [], kids[k + 1:]
            names = [node_label(a) for a in after[:3]] + ([f"{len(after) - 3} more"] if len(after) > 3 else [])
            if nd.cls == SEQ and after and st == STALLS:
                why.append(f"what follows it in its Sequential never runs ({len(after)}: {', '.join(names)})")
            if nd.cls == SEQ and after and st == WAITS:
                why.append(f"what follows it in its Sequential waits until the objective resolves and its chosen "
                           f"action finishes ({len(after)}: {', '.join(names)})")
            if runs != 1 and len(kids) > 1:
                why.append(f"it sits in a looping {nd.cls.removeprefix('TGDDescriptor')} (NbExecutions {runs:#x}) "
                           f"beside {len(kids) - 1} other nodes, which "
                           + ("repeat only once the objective resolves" if st == WAITS else "never repeat"))
            if why:
                head = (node_label(kid) if leaf else f"{status_path(kid, memo, reviewed)} "
                        + ("(waits on an objective)" if st == WAITS else "(never finishes)"))
                bad.append(f"{head}: {'; '.join(why)}")
    return found, bad


def check_never_finishing(roots: Iterable[Node], reviewed: Iterable[str] = ()) -> int:
    """Gate 3: never_finishing_violations finds nothing; `reviewed` is the content's Content.blocking_objectives,
    added to STOCK_BLOCKING_OBJECTIVES. Returns the number of NEVER_FINISH actions checked."""
    found, bad = never_finishing_violations(roots, STOCK_BLOCKING_OBJECTIVES | frozenset(reviewed))
    fix = ("\nMove each into a Simultaneous beside the rest of its beat, as the beat's last node (stock: "
           "BlackHorsesLastStand Sequential#185 = [CreateUnitOnPosition, Simultaneous[ModifyUnitSpeed, "
           "LaunchSmartOrder]]), and keep it out of loops.")
    if any("(waits on an objective)" in b for b in bad):
        fix += (" Objectives likewise: show objectives that appear together in one Simultaneous (Survivors "
                "Simultaneous#724), chain the next one through ActionsReussi (BlackHorsesLastStand #141), or, for a "
                "phase gate held on purpose, name the objective in Content.blocking_objectives (Sledgehammer #373).")
    check(not bad, f"{len(bad)} script actions or containers that never finish by themselves stall the script:\n  "
                   + "\n  ".join(bad) + fix)
    return found


def stalling_containers(roots: Iterable[Node], reviewed: Iterable[str] = STOCK_BLOCKING_OBJECTIVES) -> int:
    """The Sequential, Simultaneous, Competition and IfThenElse nodes under `roots` that never finish (finish_status
    STALLS), for the gate 3 report."""
    memo: dict[int, str] = {}
    reviewed = frozenset(reviewed)
    return sum(finish_status(nd, memo, reviewed) == STALLS for nd in walk(roots)
               if nd.cls in (SEQ, SIMUL, COMPETE, IF_THEN_ELSE))


# --------------------------------------------------------------------------- the mission gates (gate 3)
# How a script ends, and when its objectives may fail.


def end_game_label(nd: Node) -> str:
    """A TriggerEndGame for a gate message, with the fields it sets: TriggerEndGame(VictoryReason 6, VictoryType 5)."""
    bits = [f"{k} {v.v}" for k, v in nd.props if isinstance(v, Value) and isinstance(v.v, int)]
    return f"{node_label(nd)}({', '.join(bits)})" if bits else node_label(nd)


def end_funnel_violations(roots: Iterable[Node], heads: Sequence[str]) -> tuple[int, bool, list[str]]:
    """(TriggerEndGame nodes, whether the script uses an end funnel, one line per violation). The first
    TriggerEndGame wins and every later one is ignored (the game keeps the first ending), so two endings that fire in
    one tick race, and the screen shows whichever ran first. An end funnel routes every ending through latched nodes
    exported at the paths `heads` (a profile's end_exports): in a script that exports any of them, every
    TriggerEndGame has one of them as an ancestor (by every path from the roots), and each path names at most one
    node. A script that exports none is not checked: one whose two endings are the two actions of one objective (it
    resolves once, so only one runs) needs no funnel."""
    nodes = list(walk(roots))
    ends = [nd for nd in nodes if nd.cls == END_GAME]
    named = tuple(heads)
    heads = {path: [nd for nd in nodes if nd.export == path] for path in named}
    bad = [f"{len(v)} nodes are exported as {path}; a funnel has one" for path, v in heads.items() if len(v) > 1]
    if not any(heads.values()):
        return len(ends), False, bad
    stop, seen, stack = {id(nd) for v in heads.values() for nd in v}, set(), list(roots)
    while stack:
        nd = stack.pop()
        if id(nd) in seen or id(nd) in stop:
            continue
        seen.add(id(nd))
        if nd.cls == END_GAME:
            bad.append(f"{end_game_label(nd)} is under neither {' nor '.join(named)}")
        stack += [k for _, spec in nd.props for k in prop_nodes(spec)]
    return len(ends), True, bad


def check_end_funnel(roots: Iterable[Node], heads: Sequence[str]) -> tuple[int, bool]:
    """Gate 3: end_funnel_violations finds nothing for the funnel exports `heads`. Returns (TriggerEndGame nodes,
    whether the funnel is used)."""
    n, used, bad = end_funnel_violations(roots, heads)
    check(not bad, "the end funnel does not hold every ending (the first TriggerEndGame wins):\n  "
                   + "\n  ".join(bad) + "\nSet the ending's variable while it is still 0 instead, and let the one "
                   "funnel node call TriggerEndGame.")
    return n, used


# EGDOperator (CommonData/Gameplay/Constantes/Enumerations/GDOperator.ndf): the count <op> the constant.
INT_OPERATORS: dict[int, Callable[[int, int], bool]] = {
    0: lambda a, b: a == b, 1: lambda a, b: a != b, 2: lambda a, b: a >= b,
    3: lambda a, b: a <= b, 4: lambda a, b: a > b, 5: lambda a, b: a < b}
UNIT_GROUPS = ("TGDVariableUnitGroup", "TGDTagUnitGroup")  # a script variable group, a LevelDesign Spawn's tag
COUNT_TESTS = ("TGDConditionVariable", "TGDConditionUnitGroupWithFilter")  # Variable = the group, Operator = the test


def group_count_test(cond: Node) -> tuple[Node, bool] | None:
    """(the unit group, whether the test holds while the group is empty) of a condition that compares a unit group's
    count with a constant (modkit.ops.bricks.g_cmp's shape: Survivors #728 Groupe_Joueur == 0), else None."""
    props = dict(cond.props)
    group, op = props.get("Variable"), props.get("Operator")
    if cond.cls not in COUNT_TESTS or not isinstance(group, Node) or group.cls not in UNIT_GROUPS \
            or not isinstance(op, Node):
        return None
    test = dict(op.props)
    if test.get("Variable") is not None:  # compared with another variable, not a constant
        return None
    kind, value = test.get("OperatorType"), test.get("Value")
    return group, INT_OPERATORS[kind.v if kind is not None else 0](0, value.v if value is not None else 0)


def empty_group_tests(cond: Node) -> list[Node]:
    """The unit groups whose emptiness makes `cond` (a ConditionEchec) true or may: each count test in its And/Or tree
    that holds for an empty group (== 0, <= 0, < 1, ...), but not under a ConditionNone."""
    out, stack = [], [cond]
    while stack:
        nd = stack.pop()
        if nd.cls == "TGDConditionNone":
            continue
        test = group_count_test(nd)
        if test is not None:
            out += [test[0]] if test[1] and test[0] not in out else []
            continue
        stack += [k for _, spec in nd.props for k in prop_nodes(spec) if k.cls.startswith("TGDCondition")]
    return out


def guarded_groups(nd: Node) -> frozenset[int]:
    """The unit groups (by node id) a WaitCondition proves non-empty once it finishes: each count test false for an
    empty group (>= 1, > 0, ...) in its Condition or in an And of it (g_until(g_cmp(group, 1, 2)))."""
    if nd.cls != "TGDDescriptorWaitCondition":
        return frozenset()
    out, stack = set(), [dict(nd.props).get("Condition")]
    while stack:
        cond = stack.pop()
        if not isinstance(cond, Node):
            continue
        test = group_count_test(cond)
        if test is not None and not test[1]:
            out.add(id(test[0]))
        elif cond.cls == "TGDConditionAnd":
            stack += list(prop_nodes(dict(cond.props).get("SousConditions")))
    return frozenset(out)


def empty_group_violations(roots: Iterable[Node]) -> tuple[int, list[str]]:
    """(objectives whose ConditionEchec holds while a unit group is empty, one line per one reachable without a guard).
    An objective resolves at once if a condition already holds at its Start, so `Groupe_Joueur == 0` as
    ConditionEchec fails it on the first frame while the player has bought nothing (the deployment phase). The
    objective must be reachable only after a WaitCondition that the same group has a unit (guarded_groups), a sibling
    before it in an ancestor Sequential, on every path from the roots (an objective's actions and the other
    containers pass the guards down; only a Sequential adds them). The hold skeleton (modkit.ops.script.hold_script)
    has that shape: Sequential[..., WaitCondition(Groupe_Joueur >= 1), StartTimer, Simultaneous[objective]]. Stock
    has no such guard: its 16 tests (7 challenges) count groups filled before the objective starts, such as
    BlackHorsesLastStand's LevelDesign spawn group P0_C0_M577_US_1, so the gate is the toolkit's own."""
    found, bad, seen = set(), {}, set()
    stack: list[tuple[Node, frozenset[int]]] = [(nd, frozenset()) for nd in roots]
    while stack:
        nd, guards = stack.pop()
        if (id(nd), guards) in seen:
            continue
        seen.add((id(nd), guards))
        echec = dict(nd.props).get("ConditionEchec") if nd.cls in OBJECTIVES else None
        for group in empty_group_tests(echec) if isinstance(echec, Node) else []:
            found.add((id(nd), id(group)))
            if id(group) not in guards:
                name = group.export.rsplit("/", 1)[-1] if group.export else group.cls
                bad.setdefault((id(nd), id(group)), f"{node_label(nd)}: its ConditionEchec holds while {name} is "
                                                    f"empty, and no WaitCondition({name} >= 1) comes before it in "
                                                    f"an ancestor Sequential")
        if nd.cls == SEQ:
            for kid in sub_actions(nd):
                stack.append((kid, guards))
                guards = guards | guarded_groups(kid)
            continue
        stack += [(k, guards) for _, spec in nd.props for k in prop_nodes(spec)]
    return len(found), list(bad.values())


def check_empty_group_guard(roots: Iterable[Node]) -> int:
    """Gate 3, for a content with a deployment phase: empty_group_violations finds nothing. Returns the number of
    (objective, group) failure tests checked."""
    n, bad = empty_group_violations(roots)
    check(not bad, f"{len(bad)} objectives fail on the first frame while their unit group is still empty (an "
                   f"objective resolves at its Start if a condition already holds):\n  " + "\n  ".join(bad)
          + "\nStart each only after Sequential[WaitCondition(group >= 1), ...] (as hold_script does).")
    return n


DIALOG_TEXT = ("TGDDescriptorCutsceneTextComponent", "LocalizedText")  # every dialog's text (1,219 stock uses)
PLACEHOLDER = re.compile(r"%[1-9]")


def dialog_text_violations(roots: Iterable[Node], texts: Mapping[int, Sequence[str]]) -> tuple[int, list[str]]:
    """(dialog text tokens, one line per text that holds a %1..%9 placeholder). A dialog's text component has only
    UIComponentName and LocalizedText, no variable list (DescriptorCutsceneTextComponent), so a placeholder shows as
    is. Numbers go in an objective's or a hint's ListVariables. `texts` maps a
    token hash to its texts (every language checked)."""
    tokens: list[int] = []
    for nd in walk(roots):
        v = dict(nd.props).get(DIALOG_TEXT[1]) if nd.cls == DIALOG_TEXT[0] else None
        if isinstance(v, Value) and (key := int.from_bytes(v.v, "little")) not in tokens:
            tokens.append(key)
    bad = [f"{ndfbin.token_unhash(key) or hex(key)}: {text!r}" for key in tokens for text in texts.get(key, ())
           if PLACEHOLDER.search(text)]
    return len(tokens), bad


def check_dialog_text(roots: Iterable[Node], strings: StringTable) -> int:
    """Gate 3: dialog_text_violations finds nothing in the content's string table (every language). Returns the
    number of dialog text tokens checked."""
    texts = {ndfbin.token_hash(tok): tuple(by_lang.values()) for table in strings.values()
             for tok, by_lang in table.items()}
    n, bad = dialog_text_violations(roots, texts)
    check(not bad, f"{len(bad)} dialog texts hold a %1..%9 placeholder, which a dialog shows as is (it takes no "
                   f"variables):\n  " + "\n  ".join(bad) + "\nPut the number in an objective's or a hint's "
                   "ListVariables.")
    return n


# Game-rules fields the generated rules must leave out (their zero/false), so that only the script ends the battle:
# the engine's end check does nothing while CheckEndGame is false, and ends the game on time once GameTime is
# set. ModeFixedRandomSeed would make every play's random rolls the same. None is
# emitted today (Survivors #116 omits all three). Stock: HoldUntilRelieved #93 sets CheckEndGame (with MaxScore
# 999999), 7 challenges set ModeFixedRandomSeed, none sets GameTime.
RULES_OMITTED = ("CheckEndGame", "GameTime", "ModeFixedRandomSeed")


def check_rules(roots: Iterable[Node]) -> int:
    """Gate 3: no TGDSpecificTacticalGameRules sets a RULES_OMITTED field. Returns the number of rules checked."""
    rules = [nd for nd in walk(roots) if nd.cls == "TGDSpecificTacticalGameRules"]
    bad = [f"{node_label(nd)} sets {', '.join(k for k, _ in nd.props if k in RULES_OMITTED)}" for nd in rules
           if any(k in RULES_OMITTED for k, _ in nd.props)]
    check(not bad, f"game rules let the engine end or fix the battle: {bad}. Leave {', '.join(RULES_OMITTED)} out "
                   f"(Survivors #116, the template, omits all three).")
    return len(rules)


# Orders that name a unit group, and the property naming it. LaunchSmartOrder hands the group to the strategic AI as a
# mission (Seize: TheDieburgSalient #519); a later order on it in the same Sequential has no stock precedent, so what
# the AI then does with the group (keep it on its mission, bring it back) is unknown.
SMART_ORDER = "TGDDescriptorLaunchSmartOrder"
ORDER_GROUPS = {"TGDDescriptorGiveOrderStandard": "Group", "TGDDescriptorMoveUnitGroup": "Group",
                SMART_ORDER: "UnitGroup"}
GROUP_UNION = "TGDDescriptorAddUnitGroupListToUnitGroup"


def group_name(group: object) -> str:
    """A unit group for a gate message: its export's last part (od_fe_n, a GdItems tag's item name), or its class."""
    return group.export.rsplit("/", 1)[-1] if isinstance(group, Node) and group.export else getattr(group, "cls", "?")


def smart_order_violations(roots: Iterable[Node]) -> tuple[int, list[str]]:
    """(the unit groups some LaunchSmartOrder names, one line per order that re-orders one of them). An order
    (GiveOrderStandard, MoveUnitGroup or LaunchSmartOrder: ORDER_GROUPS) re-orders a smart-ordered group when it sits
    after a LaunchSmartOrder in the same Sequential (anywhere under a later child than the one holding the smart order)
    and names a group that shares units with the smart-ordered one: the same group, or one that holds it or that it
    holds through AddUnitGroupListToUnitGroup anywhere in the script (Survivors #1331: GroupDestination takes the
    units of ListGroupSource), so a union of a smart-ordered group cannot re-order it either. A known gap: a loop is
    read once, so a looping Sequential (NbExecutions other than 1) whose round holds a LaunchSmartOrder and an order on
    its group before it, which re-orders the group on the next round, passes. No content loops a smart order today. The
    one stock case is a smart order after a smart order: TheHydra's five forever loops #301-#305 each refresh a camp's
    group (AddAllCampUnitsToUnitGroup) and re-issue its LaunchSmartOrder every round, between two waits.
    Stock: the 44 smart orders of the 16 challenges name 44 groups, and none is ordered again after its smart
    order in a Sequential, with or without the unions (2,776 union edges). The one stock group
    ordered elsewhere is Marauders' artillery Event_Art_POL: its smart order sits in Simultaneous #515 (Misc_Events),
    its ShootOnPosition (OrderType 31) fire orders #1341, #1352 and #1353 in another branch (Sequential #1108 >
    IfThenElse #1300, #1342)."""
    nodes = list(walk(roots))
    held_by: dict[int, set[int]] = {}               # a group -> the groups its units were added to
    for nd in nodes:
        if nd.cls == GROUP_UNION:
            props = dict(nd.props)
            for src in prop_nodes(props.get("ListGroupSource")):
                held_by.setdefault(id(src), set()).add(id(props.get("GroupDestination")))

    def holders(group: Node) -> set[int]:
        out, stack = {id(group)}, [id(group)]
        while stack:
            for up in held_by.get(stack.pop(), ()):
                if up not in out:
                    out.add(up)
                    stack.append(up)
        return out

    def shared(a: Node, b: Node) -> bool:
        return id(b) in holders(a) or id(a) in holders(b)

    def group_of(nd: Node) -> Node | None:
        g = dict(nd.props).get(ORDER_GROUPS[nd.cls])
        return g if isinstance(g, Node) else None

    smart = {id(g): g for nd in nodes if nd.cls == SMART_ORDER and (g := group_of(nd)) is not None}
    bad: dict[tuple[int, int], str] = {}
    for nd in nodes:
        if nd.cls != SEQ:
            continue
        before: list[tuple[Node, Node]] = []         # (smart order, its group) under an earlier child
        for kid in sub_actions(nd):
            inside = list(walk([kid]))
            for order in (o for o in inside if o.cls in ORDER_GROUPS and group_of(o) is not None):
                group = group_of(order)
                for so, sg in before:
                    if shared(group, sg):
                        via = "" if group is sg else f" ({group_name(group)} and {group_name(sg)} share units)"
                        bad.setdefault((id(order), id(so)), f"{node_label(order)} comes after {node_label(so)} in one "
                                                            f"Sequential{via}")
                        break
            before += [(o, group_of(o)) for o in inside if o.cls == SMART_ORDER and group_of(o) is not None]
    return len(smart), list(bad.values())


def check_smart_orders(roots: Iterable[Node]) -> int:
    """Gate 3: smart_order_violations finds nothing. Returns the number of smart-ordered groups."""
    n, bad = smart_order_violations(roots)
    check(not bad, f"{len(bad)} orders re-order a group after its smart order (LaunchSmartOrder hands the group to "
                   f"the AI; no stock script orders a smart-ordered group again in the same Sequential: 44 groups):\n  "
                   + "\n  ".join(bad) + "\nGive the group its route first and the smart order last "
                   "(a blocking GiveOrderStandard, then the Seize), or remove the group instead of re-ordering it "
                   "(KillAllUnit, Vanished).")
    return n


# --------------------------------------------------------------------------- the buy-menu switch (gate 3)

def prod_menu_switches(roots: Iterable[Node]) -> list[int]:
    """The buy menu's switch (PROD_MENU_SWITCH; left out: BRICK_DEFAULT) at each HUD restore of a script: every
    ForceDisplayUIElement that does not hide all (stock's hide-all nodes carry no Default switch)."""
    out = []
    for nd in walk(roots):
        props = dict(nd.props)
        if nd.cls == "TGDDescriptorForceDisplayUIElement" and not getattr(props.get("ForceHideAll"), "v", 0):
            out.append(props[PROD_MENU_SWITCH].v if PROD_MENU_SWITCH in props else BRICK_DEFAULT)
    return out


def check_prod_menu_switch(content: Content, roots: Iterable[Node]) -> int:
    """The script's every HUD restore (prod_menu_switches) sets the buy menu's switch to the content's
    (Content.prod_menu_switch): the field is what ships. A script with no HUD restore passes while the content keeps
    the default (ForceHide, nothing asked); a content that asks for another switch needs a restore to carry it.
    Returns the number of restores."""
    found = prod_menu_switches(roots)
    check(found or content.prod_menu_switch == BRICK_FORCE_HIDE,
          f"{content.name}: the content asks for {PROD_MENU_SWITCH} {content.prod_menu_switch} "
          f"(Content.prod_menu_switch), but the script has no HUD restore to carry it")
    check(all(v == content.prod_menu_switch for v in found),
          f"{content.name}: the HUD restores set {PROD_MENU_SWITCH} to {found}, but the content asks for "
          f"{content.prod_menu_switch} (Content.prod_menu_switch; hud_restore's prod_menu_switch)")
    return len(found)


# --------------------------------------------------------------------------- script effects (gate 3)
# A script's effect launch carries an effect's name (its DatabaseName, '$/GFX/GameFx/...') and a position, nothing
# more. The game looks the name up among the exports of its GameFx namespace, the stock file gamefx_file(). An effect
# whose declaration takes parameters (FX_PARAMS: the NDF Params block, each parameter a TActionAlias, which is also
# what a Template_Param_* compiles to) waits for its caller to bind them, as the impact system does for a shell's
# impact; a script launch binds nothing. An Operation cannot add a GameFx export (gate 5). It can export an effect
# wrapper from its own script (bricks.fx_wrapper), launched by its export path: a TSimultaneousAction whose TActionCall
# binds the parameters, the shape of stock's script-launched fx_FumeeNoire_ForScript_RandomPosition, whose
# FX_Vehicule_Dest_Fire_FireAndForget binds FX_Vehicule_Dest_Fire's parDuration (no default) and leaves parScaleFactor
# to its default. Such a launch is held to that shape: every call binds each parameter its target declares with no
# default, and a group never lists a parameterised effect directly (the game's load check on TSimultaneousAction).

LAUNCH_FX = "TGDDescriptorLaunchFXFireAndForgetOnPosition"
FX_PARAMS = "InputParameters"
# The only effects stock scripts launch, all self-contained: 75 launches in 7 of the stock GDScripts (45, 27, 3), the
# same on build 210942 as on 201602.
STOCK_SCRIPT_EFFECTS = ("$/GFX/GameFx/fx_FumeeBlanche_ForScript_RandomPosition",
                        "$/GFX/GameFx/fx_HE_Artillery_203mm_ForScript_RandomPosition",
                        "$/GFX/GameFx/fx_FumeeNoire_ForScript_RandomPosition")


def gamefx_file() -> str:
    """The game's GameFx namespace file in the stock extraction (core's STOCK_PATHS entry transactions, the
    Transactions pack): where the game looks up the effect a script launches. Build 210942 ships the game's own NDF
    there as .txn; the Glad pack's GameFx.ndfbin is 201602's, which 210942 no longer reads. Raises
    paths.NotConfigured without an extraction."""
    return str(paths.extracted_root() / "transactions" / "NDF" / "GFX" / "GameFx.txn")


def _props(nb: ndfbin.NdfBin, i: int) -> dict[str, Value]:
    return {nb.pname(pi): v for pi, v in nb.objects[i].props}


def _text(nb: ndfbin.NdfBin, v: Value | None) -> str:
    """A string value's text ('' for any other value)."""
    return nb.strings[v.v].decode("latin-1") if v is not None and v.tag in (0x07, 0x1C) else ""


def effect_launches(nb: ndfbin.NdfBin) -> list[str]:
    """The effect each LaunchFXFireAndForgetOnPosition of the decoded script `nb` names (its DatabaseName), in object
    order."""
    return [_text(nb, _props(nb, i).get("DatabaseName")) for i, ob in enumerate(nb.objects)
            if nb.cname(ob.cls) == LAUNCH_FX]


@functools.cache
def gamefx_declarations(path: str) -> dict[str, tuple[str, ...]]:
    """Each export of the GameFx file at `path`, by its path ('$/GFX/GameFx/...'), with the parameters its
    declaration takes: the names (NAME_PROP) of its FX_PARAMS, () for a self-contained effect."""
    nb, _, _ = decode(read_file(path))
    out = {}
    for name, i in ndfbin.tree_paths(nb, nb.exports):
        params = _props(nb, i).get(FX_PARAMS)
        refs = params.v if params is not None and params.tag == 0x11 else []
        out[name] = tuple((_text(nb, _props(nb, p.v.index).get(NAME_PROP)) or "?")
                          if p.tag == 0x09 and p.v.kind == ndfbin.REF_OBJECT else "?" for p in refs)
    return out


@functools.cache
def gamefx_required(path: str) -> dict[str, tuple[str, ...]]:
    """Each export of the GameFx file at `path` with the parameters its declaration takes with no DefaultValue: the
    ones a call must bind."""
    nb, _, _ = decode(read_file(path))
    out = {}
    for name, i in ndfbin.tree_paths(nb, nb.exports):
        params = _props(nb, i).get(FX_PARAMS)
        refs = params.v if params is not None and params.tag == 0x11 else []
        out[name] = tuple(_text(nb, _props(nb, p.v.index).get(NAME_PROP)) or "?" for p in refs
                          if p.tag == 0x09 and p.v.kind == ndfbin.REF_OBJECT
                          and "DefaultValue" not in _props(nb, p.v.index))
    return out


FX_GROUP, FX_CALL = "TSimultaneousAction", "TActionCall"
FX_WRAPPER_ROOTS = (FX_GROUP, FX_CALL)


def own_effect_violations(nb: ndfbin.NdfBin, names: Iterable[str], declared: Mapping[str, tuple[str, ...]],
                          required: Mapping[str, tuple[str, ...]]) -> list[str]:
    """One line per break of the wrapper rule in the decoded script `nb`, for the launched `names` that are its own
    exports: the export is a TSimultaneousAction or a TActionCall; every TActionCall in its tree names a GameFx export
    (`declared`) and binds (NamedParams) each parameter `required` lists for it, and nothing it does not declare; no
    TSimultaneousAction of the script lists a parameterised GameFx effect directly."""
    exports = {p: i for p, i in ndfbin.tree_paths(nb, nb.exports)}
    imports = {i: p for p, i in ndfbin.tree_paths(nb, nb.imports)}
    bad: list[str] = []

    def target(v: Value | None) -> str | None:
        ok = v is not None and v.tag == 0x09 and v.v.kind == ndfbin.REF_IMPORT
        return imports.get(v.v.index) if ok else None

    for i, ob in enumerate(nb.objects):   # the load check holds every group of the file, launched or not
        if nb.cname(ob.cls) != FX_GROUP:
            continue
        actions = _props(nb, i).get("Actions")
        for x in (ndfbin.iter_values(actions) if actions is not None else ()):
            t = target(x)
            if t is not None and declared.get(t):
                bad.append(f"#{i} {FX_GROUP} lists {t}, which declares {len(declared[t])} parameters: call it "
                           f"through a {FX_CALL} that binds them")
    for name in sorted(set(names)):
        root = exports[name]
        cls = nb.cname(nb.objects[root].cls)
        if cls not in FX_WRAPPER_ROOTS:
            bad.append(f"{name} is a {cls}, not an effect ({' or '.join(FX_WRAPPER_ROOTS)})")
            continue
        seen, stack = set(), [root]
        while stack:
            i = stack.pop()
            if i in seen:
                continue
            seen.add(i)
            props = _props(nb, i)
            if nb.cname(nb.objects[i].cls) == FX_CALL:
                t = target(props.get("Action"))
                if t is None or t not in declared:
                    bad.append(f"{name}: its {FX_CALL} #{i} calls {t or 'nothing imported'}, not a GameFx export")
                else:
                    pairs = props.get("NamedParams")
                    bound = {_text(nb, k) for k, _ in (pairs.v if pairs is not None and pairs.tag == 0x12 else [])}
                    missing = [q for q in required[t] if q not in bound]
                    unknown = sorted(bound - set(declared[t]))
                    if missing:
                        bad.append(f"{name}: its call to {t} leaves {', '.join(missing)} unbound (no default)")
                    if unknown:
                        bad.append(f"{name}: its call to {t} binds {', '.join(unknown)}, which it does not declare")
            for _, v in nb.objects[i].props:
                stack += [x.v.index for x in ndfbin.iter_values(v) if x.tag == 0x09 and x.v.kind == ndfbin.REF_OBJECT]
    return bad


def effect_violations(names: Iterable[str], declared: Mapping[str, tuple[str, ...]]) -> list[str]:
    """One line per distinct effect of `names` that a script may not launch: not an export of `declared`
    (gamefx_declarations), or one whose declaration takes parameters."""
    bad = []
    for name in sorted(set(names)):
        if name not in declared:
            bad.append(f"{name or '(no DatabaseName)'} is not a GameFx export")
        elif declared[name]:
            bad.append(f"{name} declares {len(declared[name])} parameters ({', '.join(declared[name])})")
    return bad


def check_script_effects(raw: bytes, gamefx: str | None = None) -> int:
    """Gate 3: every effect the script `raw` (the shipped GDScript) launches is a self-contained export of the game's
    GameFx file `gamefx` (gamefx_file() by default, read only when the script launches an effect): effect_violations
    finds nothing. This is the game's own lookup, by name among GameFx's exports. Stock: every launch of the 31 stock
    GDScripts passes (STOCK_SCRIPT_EFFECTS), and both tactical-nuke impact effects fail (fx_impact_sol_Tactical_Nuke
    declares 4 parameters, fx_impact_Tactical_Nuke 5). A launch that names an export of the script itself is an
    effect wrapper (bricks.fx_wrapper), held to the call rule instead (own_effect_violations). Returns the number of
    launches."""
    nb = decode(raw)[0]
    names = effect_launches(nb)
    if names:
        path = gamefx or gamefx_file()
        own = {p for p, _ in ndfbin.tree_paths(nb, nb.exports)}
        bad = effect_violations([n for n in names if n not in own], gamefx_declarations(path))
        check(not bad, f"the script launches effects a script may not launch: {'; '.join(bad)}. A script launch "
                       f"carries only the effect's name and a position, and binds no parameters: launch a GameFx "
                       f"effect that declares none, as every stock script launch does "
                       f"({', '.join(n.rsplit('/', 1)[-1] for n in STOCK_SCRIPT_EFFECTS)})")
        bad = own_effect_violations(nb, [n for n in names if n in own], gamefx_declarations(path),
                                    gamefx_required(path))
        check(not bad, f"the script's own effect wrappers break the call rule: {'; '.join(bad)}. A script launch "
                       f"binds no parameters, so a parameterised effect is reached through a {FX_CALL} that binds "
                       f"every parameter it declares with no default, as stock's "
                       f"fx_FumeeNoire_ForScript_RandomPosition does (bricks.fx_wrapper)")
    return len(names)


# --------------------------------------------------------------------------- scenario-only (gate 5)

def check_package(items: list[Item], scenario: str) -> int:
    """Gate 5, scenario-only: every entry lies under the scenario, and none is a Gameplay file. A path lies under the
    scenario when one of its '/' components is the scenario id, alone or with a file extension (the Definition files
    are NDF/Scenarios/<scenario>/<Kind>.<ext>). A Details entry is checked at the path the game mounts it on,
    ScenariosData:/<scenario>/<inner path> (the ScenarioLoader's TClusterMountAdditionalDatapack), since Details inner
    paths (out/LevelDesign.ndfbin, ...) carry no id. A Gameplay file (modkit.core.packaging.is_gameplay_file: under
    Gen/, ending with one of the 16 GAMEPLAY_FILES, the game's own lookup) fails even under the scenario
    (Gen/<scenario>/GFX/Unit.txn): the game tags the mod Gameplay by that lookup alone. Returns the number of
    entries."""
    for it in items:
        path = f"ScenariosData:/{scenario}/{it.path}" if it.pack == "Details" else it.path
        check(any(part.split(".", 1)[0] == scenario for part in path.split("/")),
              f"{it.pack}:{it.path}: not under {scenario}; the package must stay scenario-only")
        check(not is_gameplay_file(it.path),
              f"{it.pack}:{it.path}: a Gameplay file (under Gen/, ending with one of "
              f"modkit.core.packaging.GAMEPLAY_FILES): the game would tag the mod Gameplay, and no Operation starts "
              f"while a Gameplay mod is active")
    return len(items)


# --------------------------------------------------------------------------- the Definition layout (gate 5)
# Build 210942 reads a scenario's Definition files by name in NDF/Scenarios/<scenario>/ (modkit.ops.rekey.def_path),
# and the kind names are the game's data, not its exe's. Its own transactions hold a SCAN_CLASS with DirName
# 'Scenarios' for each kind it looks for in every scenario folder (SCANNED_KINDS, in SCAN_FILES: the Operations menu's
# MapConfiguration, the trophies' TrophyDef and the scenario list's ScenarioInfo); the others are named by a
# transaction's BaseName: the ScenarioInfo names its ScenarioLoader.txn, and the ScenarioLoader its GDScript.txn
# (check_references resolves both). Every stock .txn of a scenario, map or decor-set pack ships beside its .txn.tag and
# its .dbg (all of them in a 210942 install's index), and every stock .dbg holds one line per object of its .txn.

SCAN_CLASS = "TClusterMultipleNdfTransactions"
SCAN_FILES = ("NDF/ClusterInitialisationData.txn", "NDF/ClusterMainScenario.txn")  # in the Transactions pack
SCANNED_KINDS = ("MapConfiguration", "ScenarioInfo", "TrophyDef")
REQUIRED_KINDS = ("MapConfiguration", "ScenarioInfo")   # an Operation's menu entry, and its load


def scanned_kinds(files: Iterable[str]) -> tuple[str, ...]:
    """The kinds the game's own transactions `files` look for in every scenario folder: the BaseName, minus .txn, of
    each SCAN_CLASS whose DirName is 'Scenarios', sorted."""
    out: set[str] = set()
    for f in files:
        nb, _, _ = decode(read_file(f))
        for i, ob in enumerate(nb.objects):
            props = _props(nb, i)
            if nb.cname(ob.cls) == SCAN_CLASS and _text(nb, props.get("DirName")) == "Scenarios":
                out.add(_text(nb, props.get("BaseName")).removesuffix(f".{TXN}"))
    return tuple(sorted(out))


def stock_scans() -> dict[str, txntag.Scan]:
    """The game's folder scans of NDF/Scenarios (SCAN_FILES in the extraction's Transactions pack), by the BaseName
    of the transaction each makes ('MapConfiguration.txn', ...). Raises paths.NotConfigured without an extraction."""
    return _stock_scans(str(paths.extracted_root()))


@functools.cache
def _stock_scans(root: str) -> dict[str, txntag.Scan]:
    out = {}
    for rel in SCAN_FILES:
        nb, _, _ = decode(read_file(os.path.join(root, "transactions", *rel.split("/"))))
        out.update({s.base_name: s for s in txntag.scans(nb) if s.dir_name == "Scenarios"})
    check(sorted(b.removesuffix(f".{TXN}") for b in out) == sorted(SCANNED_KINDS),
          f"the game's scenario scans name {sorted(out)}, not {list(SCANNED_KINDS)}: re-read the Transactions pack")
    return out


def definition_transactions(entries: Mapping[str, bytes], scenario: str,
                            scans: Mapping[str, txntag.Scan]) -> dict[str, txntag.Transaction]:
    """{kind: the transaction the game loads it by} for every kind of the Definition `entries`: a scanned kind's from
    the game's scan of the scenario folder (`scans`: stock_scans()), every other kind's from the TNDFTransaction a
    shipped .txn names it by (BaseName Scenarios/<scenario>/<Kind>.txn: ScenarioInfo names its ScenarioLoader, the
    ScenarioLoader its GDScript). A kind no data names is left out."""
    named: dict[str, txntag.Transaction] = {}
    for inner, raw in entries.items():
        if inner.endswith(f".{TXN}") and is_cndf(raw):
            for t in txntag.transactions(decode(raw)[0]):
                named.setdefault(t.base_name, t)
    out = {}
    for inner in entries:
        entry = def_entry(inner)
        if entry is None or entry[2] != TXN:
            continue
        kind = entry[1]
        scan = scans.get(f"{kind}.{TXN}")
        t = txntag.scan_transaction(scan, scenario) if scan is not None else named.get(f"Scenarios/{scenario}/{kind}.{TXN}")
        if t is not None:
            out[kind] = t
    return out


def check_config_hashes(entries: Mapping[str, bytes], scenario: str, scans: Mapping[str, txntag.Scan]) -> int:
    """Gate 5: every .txn.tag of the Definition `entries` holds the ConfigHash the game computes for its transaction
    (definition_transactions, modkit.core.txntag). With any other, the game treats the .txn as stale and compiles the
    transaction from its NDF sources, which a mod does not ship: "NDF parsing error. Retry?", "File not found" for its
    first source. A tag whose transaction no data names fails, unevaluated. Returns the number of tags."""
    transactions = definition_transactions(entries, scenario, scans)
    tags = 0
    for inner, raw in entries.items():
        entry = def_entry(inner)
        if entry is None or entry[2] != TAG:
            continue
        kind = entry[1]
        t = transactions.get(kind)
        check(t is not None, f"Definition:{inner}: no data names the transaction of {kind}.{TXN} (neither the game's "
                             f"scans of NDF/Scenarios nor a shipped TNDFTransaction), so its ConfigHash cannot be checked")
        held, want = txntag.read_tag(raw)[0], txntag.config_hash(t)
        check(held == want, f"Definition:{inner}: ConfigHash {held}, but the game computes {want} for "
                            f"{t.base_name} (NameSpace {t.namespace}, {len(t.files)} files): it would compile the "
                            f"transaction from sources the mod does not ship and stop with \"NDF parsing error. "
                            f"Retry?\" and \"File not found : '{t.files[0] if t.files else t.base_name}'\"")
        tags += 1
    return tags


def check_definition_layout(entries: Mapping[str, bytes], scenario: str) -> int:
    """Gate 5, the Definition pack's entries (`entries`: inner path -> bytes) in build 210942's layout: each is
    NDF/Scenarios/`scenario`/<Kind>.txn, .txn.tag or .dbg; REQUIRED_KINDS ship; every kind ships all three; each
    .txn.tag holds one TNDFTagFile; each .dbg reads, holds one line per object of its .txn, and names each exported
    object as stock does (its export path's last component). Returns the number of kinds."""
    kinds: dict[str, set[str]] = {}
    for inner in entries:
        entry = def_entry(inner)
        check(entry is not None and entry[0] == scenario,
              f"Definition:{inner}: not NDF/Scenarios/{scenario}/<Kind>.txn, .txn.tag or .dbg, the only place build "
              f"210942 reads a scenario's Definition files (a build for 201602 had NDF/Scenarios/<Kind>/"
              f"<scenario>.ndfbin): rebuild it with this toolkit")
        kinds.setdefault(entry[1], set()).add(entry[2])
    for kind in REQUIRED_KINDS:
        check(kind in kinds, f"Definition: no {def_path(kind, TXN, scenario)}: the game looks for it in every "
                             f"scenario folder ({', '.join(SCANNED_KINDS)})")
    for kind, exts in sorted(kinds.items()):
        missing = [ext for ext in DEF_EXTS if ext not in exts]
        check(not missing, f"Definition: {kind} ships without its .{', .'.join(missing)}: every stock .txn of a "
                           f"scenario pack ships beside its .{TAG} and its .{DBG}")
        nb, _, _ = decode(entries[def_path(kind, TXN, scenario)])
        tag, _, _ = decode(entries[def_path(kind, TAG, scenario)])
        classes = [tag.cname(ob.cls) for ob in tag.objects]
        check(classes == [TAG_CLASS], f"Definition: {kind}.{TAG} holds {classes}, not one {TAG_CLASS}")
        try:
            lines = dbg.read(entries[def_path(kind, DBG, scenario)])
        except dbg.DbgError as exc:
            raise CheckError(f"Definition: {kind}.{DBG} does not read: {exc}") from None
        check(len(lines) == len(nb.objects), f"Definition: {kind}.{DBG} holds {len(lines)} lines for the "
                                             f"{len(nb.objects)} objects of its .{TXN}: a source map holds one line "
                                             f"per object, in object order")
        named = {i: p.rsplit("/", 1)[-1] for p, i in ndfbin.tree_paths(nb, nb.exports)}
        wrong = [f"#{i} {name} as {lines[i].name or '(unnamed)'}" for i, name in sorted(named.items())
                 if lines[i].name != name]
        check(not wrong, f"Definition: {kind}.{DBG} names exported objects otherwise than their exports: "
                         f"{', '.join(wrong[:5])}")
    return len(kinds)


# --------------------------------------------------------------------------- every class and property in stock (gate 5)
# The game knows the classes and properties its build was made with, and no others: a build for 201602 ships
# TScenarioLoadInfo, TClusterAddPythonPath, TGDDescriptorLaunchEffetStandard, GdItems tags with GUID1..GUID4 and
# TSimultaneousAction._ShortDatabaseName, none of which 210942 has. check_stock_classes holds every CNDF entry a build
# ships, re-keyed, copied or generated, to the classes and (class, property) pairs of the stock files of its kind: every
# scenario pack's Definition and Details in the extraction, and the game's GameFx (the effect wrapper's shapes). An
# admitted shape (Content.extra_shapes: a native property no stock file writes, reviewed) passes too.

STOCK_CLASS_SOURCES = tuple(f"{folder}/{rel}" for folder in ("scenarios/*", "kreide_op/*", "geisa_op/*",
                                                             "twincities_op/*")
                            for rel in (f"NDF/Scenarios/*/*.{TXN}", f"NDF/Scenarios/*/*.{TAG}", "*.ndfbin",
                                        "out/*.ndfbin")) + ("transactions/NDF/GFX/GameFx.txn",)
STOCK_CLASS_MINIMUM = 400   # fewer stock files means the extraction was not read right


class StockClasses(NamedTuple):
    """The classes and (class, property) pairs of the stock files read, and how many files that was."""
    classes: frozenset[str]
    props: frozenset[tuple[str, str]]
    files: int


@functools.cache
def _stock_classes(root: str, minimum: int) -> StockClasses:
    files = sorted({p for pat in STOCK_CLASS_SOURCES for p in glob.glob(os.path.join(root, *pat.split("/")))})
    check(len(files) >= minimum, f"stock-classes gate: {len(files)} stock files under {root}, expected {minimum}+: "
                                 f"re-run the extraction (the warno-setup skill)")
    check(os.path.join(root, *STOCK_CLASS_SOURCES[-1].split("/")) in files,
          f"stock-classes gate: the extraction lacks {STOCK_CLASS_SOURCES[-1]}; {SETUP_FIX}")
    classes: set[str] = set()
    props: set[tuple[str, str]] = set()
    for f in files:
        nb, _, _ = decode(read_file(f))
        for ob in nb.objects:
            cls = nb.cname(ob.cls)
            classes.add(cls)
            props.update((cls, nb.pname(pi)) for pi, _ in ob.props)
    return StockClasses(frozenset(classes), frozenset(props), len(files))


def stock_classes(minimum: int = STOCK_CLASS_MINIMUM) -> StockClasses:
    """The classes and properties of the stock files STOCK_CLASS_SOURCES names in the extraction (at least `minimum`
    files, GameFx among them). Raises paths.NotConfigured without an extraction."""
    return _stock_classes(str(paths.extracted_root()), minimum)


def is_cndf(raw: bytes) -> bool:
    """Whether `raw` is a CNDF file (an .ndfbin, .txn or .txn.tag)."""
    return raw[:4] == b"EUG0" and raw[8:12] == b"CNDF"


def check_stock_classes(entries: Iterable[tuple[str, bytes]], stock: StockClasses,
                        admitted: Iterable[tuple[str, str]] = ()) -> tuple[int, int]:
    """Gate 5: every class and every (class, property) of each CNDF entry of `entries` ((name, bytes): every entry a
    build ships; other formats are left out) is in `stock` (stock_classes()) or `admitted` ((class, property) pairs;
    an admitted pair's class passes too). Returns (CNDF files, objects) read."""
    admitted = set(admitted)
    admitted_classes = {cls for cls, _ in admitted}
    unknown: dict[str, str] = {}
    files = objects = 0
    for name, raw in entries:
        if not is_cndf(raw):
            continue
        nb, _, _ = decode(raw)
        files, objects = files + 1, objects + len(nb.objects)
        for ob in nb.objects:
            cls = nb.cname(ob.cls)
            if cls not in stock.classes and cls not in admitted_classes:
                unknown.setdefault(f"class {cls}", name)
            for pi, _ in ob.props:
                pair = (cls, nb.pname(pi))
                if pair not in stock.props and pair not in admitted:
                    unknown.setdefault(f"{cls}.{pair[1]}", name)
    shown = [f"{what} ({where})" for what, where in list(unknown.items())[:12]]
    check(not unknown, f"{len(unknown)} classes or properties no stock file of this game build holds: "
                       f"{'; '.join(shown)}{'; ...' if len(unknown) > len(shown) else ''}. The game knows only its "
                       f"own build's classes and properties, and one gone from it fails the load: rebuild the mod with "
                       f"this toolkit for the installed build, or admit a native shape no stock file writes once it is "
                       f"reviewed (Content.extra_shapes)")
    return files, objects


# --------------------------------------------------------------------------- the unit database

UNIT_PREFIX = "$/GFX/Unit/"
# The mod SDK's unit database, in the game install: its unit and its building descriptors (FOBs share the namespace).
# Build 210942's SDK renamed the units' file to TacticalUnits.ndf (3,341 units; 201602's Gfx/UniteDescriptor.ndf held
# 1,052), the file the modding manual names for unit descriptors.
UNIT_ARCHIVE = "Mods/ModData/base.zip"
UNIT_DATABASE = ("GameData/Generated/Gameplay/TacticalUnits.ndf",
                 "GameData/Generated/Gameplay/Gfx/BuildingDescriptors.ndf")


def unit_database(archive: str | None = None, *, minimum: int = 1001) -> set[str]:
    """The `$/GFX/Unit/Descriptor_Unit_*` names the unit database exports (UNIT_DATABASE in `archive`, by default the
    game's UNIT_ARCHIVE): every unit a script or a LevelDesign may name. Fewer than `minimum` means the files were not
    read right (stock has thousands)."""
    archive = archive or os.path.join(str(paths.game_dir()), *UNIT_ARCHIVE.split("/"))
    with zipfile.ZipFile(archive) as z:
        text = "".join(z.read(name).decode("utf-8", "replace") for name in UNIT_DATABASE)
    known = {UNIT_PREFIX + m for m in re.findall(r"export (Descriptor_Unit_\w+) is TEntityDescriptor", text)}
    check(len(known) >= minimum, f"{archive}: only {len(known)} unit descriptors found, want at least {minimum}")
    return known


def check_units(items: Iterable[Item], known: set[str]) -> int:
    """Every unit descriptor a generated ndfbin (an item with a fixture) names, as an import or a string (a Spawn's
    ClassName), is in `known` (unit_database, plus any units a mod the build requires exports). Returns how many
    distinct units are named."""
    used: set[str] = set()
    for it in items:
        if it.fixture is None:
            continue
        nb, _, _ = decode(b"".join(it.chunks()))
        used |= {p for p, _ in ndfbin.tree_paths(nb, nb.imports) if p.startswith(UNIT_PREFIX)}
        used |= {s.decode("latin-1") for s in nb.strings if s.startswith(UNIT_PREFIX.encode())}
    missing = sorted(used - known)
    check(not missing, f"unit descriptors not in the unit database: {missing}")
    return len(used)


def unit_gate(items: list[Item], content: object) -> str:
    """An extra gate (profile.ExtraGate) for a mod that uses stock units only: every unit descriptor its generated
    files name exists in the game's unit database (check_units over unit_database)."""
    return f"{check_units(items, unit_database())} unit descriptors exist"


# --------------------------------------------------------------------------- what the unit database says of a unit
# The rest of the mod SDK's database, beside UNIT_DATABASE in UNIT_ARCHIVE: the weapons, their ammunition and the
# decks. Each reader takes the archive (by default the game's) and reads the text the game ships.

WEAPON_DATABASE = "GameData/Generated/Gameplay/Gfx/WeaponDescriptor.ndf"
AMMO_DATABASE = ("GameData/Generated/Gameplay/Gfx/Ammunition.ndf",
                 "GameData/Generated/Gameplay/Gfx/AmmunitionMissiles.ndf")
DECK_DATABASE = ("GameData/Generated/Gameplay/Decks/Decks.ndf", "GameData/Generated/Gameplay/Decks/DeckPacks.ndf")
_HEAD = re.compile(r"(?m)^(?:export )?(\w+) is \w+")


def unit_archive(archive: str | None = None) -> str:
    """`archive`, or the game's UNIT_ARCHIVE (raises paths.NotConfigured without a game folder)."""
    return archive or os.path.join(str(paths.game_dir()), *UNIT_ARCHIVE.split("/"))


@functools.cache
def database_text(archive: str, inner: str) -> str:
    """The text of the file `inner` of the database archive `archive`."""
    with zipfile.ZipFile(archive) as z:
        return z.read(inner).decode("utf-8", "replace")


def top_blocks(text: str) -> Iterable[tuple[str, str]]:
    """(name, text) of each top-level `<name> is <class>` object of an NDF text, exported or not."""
    heads = list(_HEAD.finditer(text))
    for head, after in zip(heads, [*heads[1:], None]):
        yield head.group(1), text[head.start():after.start() if after else len(text)]


def shoot_on_position_bands(archive: str | None = None) -> dict[str, tuple[float, float]]:
    """{unit path: (min, max) GRU}: the ground range band a ShootOnPosition order of the unit can fire in, over the
    unit database: every ammunition of the unit's weapons (its WeaponDescriptor's mounted weapons) that can shoot on a
    position (CanShootOnPosition True) reaches it, so the largest MinimumRangeGRU and the smallest MaximumRangeGRU of
    them. A unit with no such ammunition is left out."""
    archive = unit_archive(archive)
    ammo: dict[str, tuple[float, float]] = {}
    for inner in AMMO_DATABASE:
        for name, body in top_blocks(database_text(archive, inner)):
            lo, hi = (re.search(rf"\b{key}\s*=\s*([\d.]+)", body) for key in ("MinimumRangeGRU", "MaximumRangeGRU"))
            if re.search(r"\bCanShootOnPosition\s*=\s*True", body) and lo and hi:
                ammo[name] = (float(lo.group(1)), float(hi.group(1)))
    weapons = {name: [ammo[a] for a in re.findall(r"\bAmmunition\s*=\s*\$/GFX/Weapon/(\w+)", body) if a in ammo]
               for name, body in top_blocks(database_text(archive, WEAPON_DATABASE))}
    out = {}
    for name, body in top_blocks(database_text(archive, UNIT_DATABASE[0])):
        bands = [b for w in re.findall(r"\$/GFX/Weapon/(WeaponDescriptor_\w+)", body) for b in weapons.get(w, ())]
        if name.startswith("Descriptor_Unit_") and bands:
            out[UNIT_PREFIX + name] = (max(lo for lo, _ in bands), min(hi for _, hi in bands))
    return out


def deck_packs(decks: str, packs: str, identifier: str) -> list[tuple[str, int, str | None]]:
    """The packs of the deck `identifier` as (unit, number, transport or None), bare stock names, in its DeckPackList
    order: from the SDK's Decks.ndf text `decks` (the TDeckDescriptor whose DeckIdentifier it is) and DeckPacks.ndf
    text `packs` (each pack's Unit, Number and Transport)."""
    blocks = [b for b in re.split(r"(?m)^export ", decks) if f'DeckIdentifier = "{identifier}"' in b]
    check(len(blocks) == 1, f"{len(blocks)} stock decks are named {identifier}")
    bodies = {m.group(1): m.group(2) for m in re.finditer(
        r"(?m)^(Descriptor_Deck_Pack_\w+) is DeckPackDescriptor\s*\((.*?)\)", packs, re.S)}
    listed = re.search(r"DeckPackList\s*=\s*\[(.*?)\]", blocks[0], re.S)
    out = []
    for name in re.findall(r"~/(Descriptor_Deck_Pack_\w+)", listed.group(1) if listed else ""):
        body = bodies[name]
        carrier = re.search(r"Transport = \$/GFX/Unit/Descriptor_Unit_(\w+)", body)
        out.append((re.search(r"\bUnit = \$/GFX/Unit/Descriptor_Unit_(\w+)", body).group(1),
                    int(re.search(r"\bNumber = (\d+)", body).group(1)), carrier.group(1) if carrier else None))
    return out


def stock_deck_packs(identifier: str, archive: str | None = None) -> list[tuple[str, int, str | None]]:
    """deck_packs of the stock deck `identifier`, from DECK_DATABASE in the unit database archive."""
    archive = unit_archive(archive)
    return deck_packs(*(database_text(archive, inner) for inner in DECK_DATABASE), identifier)


# --------------------------------------------------------------------------- units a script creates, and its fires
# A unit CreateUnitOnPosition makes outside the playable zone stands on the zone's edge, at the point nearest its
# position, where the player's units see and engage it [[created-units-stand-in-zone]]; stock creates every unit inside
# the zone. check_created_in_zone (gate 3, every op) holds a script to that. A create-fire-vanish battery
# [[scripted-fires]] is created for each fire, ordered to ShootOnPosition and removed after: check_fire_range holds it
# to the player's alliance, so the player's units never engage it, and every target to its range band from where it
# stands, read where the game reads them (the shipped script, LevelDesign and playable zone) and from the unit
# database.

FIRE_ORDER = 31   # EOrderType ShootOnPosition (shapes.SHOOT_ON_POSITION: shapes imports maps, which imports this module)
CREATE = "TGDDescriptorCreateUnitOnPosition"


def _bare(unit: str) -> str:
    """A unit path's bare stock name: `T80BV_SOV` for `$/GFX/Unit/Descriptor_Unit_T80BV_SOV`."""
    return unit.removeprefix(UNIT_PREFIX).removeprefix("Descriptor_Unit_")


def playable_ring(raw: bytes) -> list[tuple[float, float]] | None:
    """The ring of a PlayableZone file's one area (world units, closed), or None when the file holds no area: the
    whole map is then playable (stock: Survivors, RedJuggernaut, Gotterdammerung and ClosingTheTrap ship such a file).
    The game refuses a file with more than one."""
    nb, _, _ = decode(raw)
    areas = sum(nb.cname(ob.cls) == "TMapArea" for ob in nb.objects)
    check(areas <= 1, f"{areas} playable zones in one PlayableZone file; the game takes one")
    return read_playable_polygon(raw) if areas else None


def stands_at(at: tuple[float, float], ring: Sequence | None) -> tuple[float, float]:
    """Where a unit created at `at` (world units) stands: at `at` inside the playable zone `ring` (anywhere when
    `ring` is None, a whole-map zone), else at the zone's point nearest `at` [[created-units-stand-in-zone]]."""
    if ring is None or point_in_polygon(*at, ring):
        return at
    return nearest_on_polygon(*at, ring)[1]


def created_violations(roots: Iterable[Node], ld_raw: bytes | None,
                       ring: Sequence | None) -> tuple[int, list[str]]:
    """(The CreateUnitOnPosition nodes reachable from `roots`, one line per one whose Position names no item of the
    LevelDesign `ld_raw` or an item outside the playable zone `ring`): check_created_in_zone's rule, without
    raising."""
    from modkit.ops.shapes import GRU_WORLD   # shapes imports maps, which imports this module
    by_guid = {it["GUID"]: it for it in read_ld_items(ld_raw)} if ld_raw else {}
    count, bad = 0, []
    for nd in walk(roots):
        if nd.cls != CREATE:
            continue
        count += 1
        props = dict(nd.props)
        unit = _bare(props["TypeUnit"].path) if isinstance(props.get("TypeUnit"), Imp) else "a unit"
        it = by_guid.get(tag_guid(props.get("Position")))
        if it is None:
            bad.append(f"a CreateUnitOnPosition of {unit} names no LevelDesign item")
            continue
        at = it["pos"][:2]
        stand = stands_at(at, ring)
        if stand != at:
            bad.append(f"{unit} is created at {it['Name']}, {math.dist(at, stand) / GRU_WORLD:,.0f} GRU "
                       f"{compass(at[0] - stand[0], at[1] - stand[1])} of the playable zone: it stands on the zone's "
                       f"edge, where the player's units see and engage it")
    return count, bad


def check_created_in_zone(roots: Iterable[Node], details: Mapping[str, bytes]) -> int:
    """Gate 3: every CreateUnitOnPosition of the script (reachable from `roots`) names an item of the shipped
    out/LevelDesign whose point lies inside the shipped playable zone (out/PlayableZone; a file with no area makes the
    whole map playable). A unit created outside stands on the zone's edge, seen and engaged by the player's units
    [[created-units-stand-in-zone]]; stock's 313 CreateUnitOnPosition (build 210942) all stand inside. `details`: inner path -> the
    Details bytes the build ships. Returns the number of CreateUnitOnPosition."""
    roots = list(roots)
    if not any(nd.cls == CREATE for nd in walk(roots)):
        return 0
    playable = details.get(PLAYABLE_FILE)
    check(playable is not None, f"the script creates units but the mod ships no {PLAYABLE_FILE}")
    count, bad = created_violations(roots, details.get(LD_FILE), playable_ring(playable))
    check(not bad, f"{len(bad)} of {count} CreateUnitOnPosition create units outside the playable zone:\n  "
          + "\n  ".join(dict.fromkeys(bad)) + "\nCreate each inside the zone: the game puts it on the zone's edge.")
    return count


class FireRange(NamedTuple):
    """What check_fire_range found: the spawn's point and where its batteries stand (world units: the same point
    inside the playable zone), the alliance and each battery camp's export name, and each fire as (battery unit,
    target, distance GRU from where the battery stands, band min, band max)."""
    at: tuple[float, float]
    stand: tuple[float, float]
    alliance: int
    camps: tuple[str, ...]
    fires: tuple[tuple[str, str, float, float, float], ...]


def camp_alliance(camp: Node) -> int:
    """A TGDVariableCamp's Alliance (absent: 0, as stock leaves the first alliance's out)."""
    value = dict(camp.props).get("Alliance")
    return value.v if isinstance(value, Value) else 0


def check_fire_range(gd_raw: bytes, ld_raw: bytes, playable_raw: bytes, spawn: str, player_camp: str, *,
                     bands: Mapping[str, tuple[float, float]]) -> FireRange:
    """Gate: the batteries the script `gd_raw` creates at the Name tag `spawn` are the player's fires
    [[scripted-fires]], read from the shipped LevelDesign `ld_raw` and playable zone `playable_raw`:
      - at least one battery is created there (CreateUnitOnPosition), and each is ordered to ShootOnPosition;
      - each battery's camp is in the alliance of the player's camp `player_camp` (its export name), so the player's
        units never engage it: a battery stands inside the playable zone or on its edge, where they see it
        [[created-units-stand-in-zone]];
      - every target of its orders lies inside the ShootOnPosition band (`bands`: unit path -> (min, max) GRU) of
        every unit type created into that battery's group, measured from where the battery stands (stands_at).
    check_created_in_zone, gate 3, holds the spawn inside the zone. Distances in GRU are world units over the
    circles' GRU_WORLD."""
    from modkit.ops.shapes import GRU_WORLD   # shapes imports maps, which imports this module
    nb, _, _ = decode(gd_raw)
    nodes = nodes_of(nb)
    items = read_ld_items(ld_raw)
    named = [it for it in items if it["Name"] == spawn]
    check(len(named) == 1, f"fire range: {len(named)} LevelDesign items are named {spawn}, expected 1")
    at, guid = named[0]["pos"][:2], named[0]["GUID"]
    stand = stands_at(at, playable_ring(playable_raw))
    players = [nd for nd in nodes if nd.export == f"$/GDScript/RootDescriptor/{player_camp}"]
    check(len(players) == 1, f"fire range: the script exports {len(players)} camps named {player_camp}")
    alliance = camp_alliance(players[0])
    by_guid = {it["GUID"]: it for it in items}
    bad: list[str] = []
    created: dict[int, tuple[Node, list[str]]] = {}
    camps: dict[str, Node] = {}
    for nd in nodes:
        props = dict(nd.props)
        if nd.cls == CREATE and tag_guid(props.get("Position")) == guid:
            created.setdefault(id(props["Group"]), (props["Group"], []))[1].append(props["TypeUnit"].path)
            camp = props.get("Camp")
            name = (camp.export or "a camp").rsplit("/", 1)[-1] if isinstance(camp, Node) else "no camp"
            if not isinstance(camp, Node) or camp_alliance(camp) != alliance:
                bad.append(f"{_bare(props['TypeUnit'].path)} is created at {spawn} in {name}, outside the player's "
                           f"alliance ({alliance}): the player's units engage it; create it in a camp of that alliance")
            camps[name] = camp
    if not created:
        bad.append(f"no battery is created at {spawn} (CreateUnitOnPosition)")
    fires, fired = [], set()
    for nd in nodes:
        props = dict(nd.props)
        kind = props.get("OrderType")
        if nd.cls != "TGDDescriptorGiveOrderStandard" or getattr(kind, "v", None) != FIRE_ORDER \
                or id(props.get("Group")) not in created:
            continue
        group, types = created[id(props["Group"])]
        fired.add(id(group))
        target = by_guid.get(tag_guid(props.get("Position")))
        if target is None:
            bad.append(f"a ShootOnPosition of {group.export or 'a battery'} names no LevelDesign item")
            continue
        d = math.dist(stand, target["pos"][:2]) / GRU_WORLD
        for unit in sorted(set(types)):
            band = bands.get(unit)
            short = _bare(unit)
            if band is None:
                bad.append(f"{short} has no weapon that can ShootOnPosition in the unit database")
                continue
            fires.append((short, target["Name"], d, *band))
            if not band[0] <= d <= band[1]:
                bad.append(f"{target['Name']} is {d:,.0f} GRU from where {short} stands at {spawn}, outside its "
                           f"ShootOnPosition band ({band[0]:,.0f}-{band[1]:,.0f} GRU): move the spawn")
    bad += [f"{g.export or 'a battery'} is created at {spawn} but never ordered to ShootOnPosition"
            for key, (g, _) in created.items() if key not in fired]
    check(not bad, "fire range:\n  " + "\n  ".join(dict.fromkeys(bad)))
    return FireRange(at, stand, alliance, tuple(sorted(camps)), tuple(fires))


def fire_range_gate(spawn: str, player_camp: str) -> Callable[[list[Item], Content], str]:
    """An extra gate (profile.ExtraGate) for an op whose fires come from batteries created at the Name tag `spawn`
    [[scripted-fires]]: check_fire_range over the script, LevelDesign and playable zone the build plans to ship, with
    the unit database's ShootOnPosition bands; `player_camp` is the player's camp (its export name)."""
    def gate(items: list[Item], content: Content) -> str:
        inner = def_path("GDScript", TXN, content.scenario)
        gd = [it for it in items if it.pack == "Definition" and it.path == inner]
        check(len(gd) == 1, f"the mod ships {len(gd)} {inner}, expected 1")
        ld, playable = shipped_details(items, LD_FILE), shipped_details(items, PLAYABLE_FILE)
        check(ld is not None and playable is not None, f"the mod ships no {LD_FILE} or no {PLAYABLE_FILE}")
        r = check_fire_range(b"".join(gd[0].chunks()), ld, playable, spawn, player_camp,
                             bands=shoot_on_position_bands())
        where = "inside the playable zone" if r.stand == r.at else "on the playable zone's edge"
        margin, what = min((min(d - lo, hi - d), f"{target} from {unit}") for unit, target, d, lo, hi in r.fires)
        targets = len({target for _, target, *_ in r.fires})
        return (f"{spawn}'s batteries in {', '.join(r.camps)}, the player's alliance ({r.alliance}), standing {where}; "
                f"{len(r.fires)} battery-target pairs on {targets} targets, each inside its band (closest: {what}, "
                f"{margin:,.0f} GRU inside)")
    return gate


# --------------------------------------------------------------------------- the Operations menu order
# The game lists an Operation for every mounted MapConfiguration whose ChapterPack is MENU_PACK, at its menu order,
# OrderToChainMission [[operation-menu-registration]], and stops at start when two Operations hold one menu order: a
# map pack configuration error, "Duplicate OrderToChainMission <order>". Every Operation active at once needs its own
# [[content-identity-unique]]. A build sees only its own mod and stock, so menu_order_gate holds a build to a menu
# order no stock Operation holds; the order derived from the scenario's GUID (DERIVED_FIX) keeps mods apart from each
# other, and the examples' test holds every example to its derived order.

MENU_PACK = "$/MapPacks/Challenges"   # a MapConfiguration's ChapterPack that lists it in the Operations menu
MENU_ORDER = "OrderToChainMission"    # its place in that menu, one per Operation
STOCK_OPERATIONS = 16                 # fewer stock Operations found means the extraction was not read right
# The fix a failure names: the order derived from the scenario's GUID [[content-identity-unique]].
DERIVED_FIX = "modkit.ops.leveldesign.derived_menu_order(scenario, namespace)"


class MenuEntry(NamedTuple):
    """An Operations menu entry of a MapConfiguration: its MENU_ORDER and its GUID (None: the object holds none)."""
    order: int | None
    guid: bytes | None


def menu_entries(nb: ndfbin.NdfBin) -> list[MenuEntry]:
    """Each object of the decoded MapConfiguration `nb` whose ChapterPack is MENU_PACK (an Operations menu entry), in
    object order, with its MENU_ORDER and its GUID."""
    imports = {i: path for path, i in ndfbin.tree_paths(nb, nb.imports)}
    out = []
    for i in range(len(nb.objects)):
        props = _props(nb, i)
        pack = props.get("ChapterPack")
        if pack is None or pack.tag != 0x09 or pack.v.kind != ndfbin.REF_IMPORT:
            continue
        if imports.get(pack.v.index) == MENU_PACK:
            order, guid = props.get(MENU_ORDER), props.get("GUID")
            out.append(MenuEntry(order.v if order is not None and isinstance(order.v, int) else None,
                                 guid.v if guid is not None and guid.tag == 0x1A else None))
    return out


def menu_orders(nb: ndfbin.NdfBin) -> list[int | None]:
    """The MENU_ORDER of each Operations menu entry of the decoded MapConfiguration `nb` (menu_entries), in object
    order; None for one that holds no MENU_ORDER."""
    return [entry.order for entry in menu_entries(nb)]


def stock_menu_files(root: str) -> list[str]:
    """Every MapConfiguration of the extraction at `root` (NDF/Scenarios/<scenario>/MapConfiguration.txn): the files
    the game scans every Definition pack for (SCANNED_KINDS), where it reads ChapterPack and MENU_ORDER."""
    return sorted(glob.glob(os.path.join(root, "**", "NDF", "Scenarios", "*", f"MapConfiguration.{TXN}"),
                            recursive=True))


class StockOperation(NamedTuple):
    """A stock Operation: its scenario id, its MENU_ORDER and its MapConfiguration GUID."""
    scenario: str
    order: int
    guid: bytes | None


@functools.cache
def _stock_operations(root: str, minimum: int) -> tuple[StockOperation, ...]:
    found: set[StockOperation] = set()
    unread: list[str] = []
    for nb in ndfrules.stock_files(stock_menu_files(root), unread):
        scenario = os.path.basename(os.path.dirname(nb.path))
        for entry in menu_entries(nb):
            check(entry.order is not None, f"{os.path.relpath(nb.path, root)}: a stock Operation without {MENU_ORDER}")
            found.add(StockOperation(scenario, entry.order, entry.guid))
    check(not unread, f"stock MapConfigurations that do not read: {[os.path.relpath(p, root) for p in unread]}")
    names = {op.scenario for op in found}
    check(len(names) >= minimum, f"menu-order gate: {len(names)} stock Operations found under {root}, expected "
                                 f"{minimum}+: re-run the extraction (the warno-setup skill)")
    return tuple(sorted(found, key=lambda op: (op.order, op.scenario)))


def stock_operations(minimum: int = STOCK_OPERATIONS) -> tuple[StockOperation, ...]:
    """Every stock Operation, by menu order: each stock MapConfiguration of the extraction (its older/ builds left
    out, as modkit.core.ndfrules.stock_files leaves them) whose ChapterPack is MENU_PACK, read where the game reads it.
    A scenario's copies count once. Fails when a file does not read or fewer than `minimum` Operations are found;
    raises paths.NotConfigured without an extraction."""
    return _stock_operations(str(paths.extracted_root()), minimum)


def stock_menu_orders(minimum: int = STOCK_OPERATIONS) -> Mapping[int, tuple[str, ...]]:
    """{MENU_ORDER: the stock scenario ids holding it} over stock_operations(minimum): the orders the game's Operations
    menu holds."""
    held: dict[int, set[str]] = {}
    for op in stock_operations(minimum):
        held.setdefault(op.order, set()).add(op.scenario)
    return {order: tuple(sorted(names)) for order, names in sorted(held.items())}


def check_menu_order(raw: bytes, what: str, stock: Mapping[int, Sequence[str]]) -> int:
    """Gate: the MapConfiguration `raw` lists one Operation (one object whose ChapterPack is MENU_PACK), and its
    MENU_ORDER is no stock Operation's (`stock`: stock_menu_orders()). Returns the order."""
    orders = menu_orders(decode(raw)[0])
    check(len(orders) == 1, f"{what}: {len(orders)} objects list an Operation (ChapterPack {MENU_PACK}), expected 1")
    order = orders[0]
    check(order is not None, f"{what}: the Operation has no {MENU_ORDER}: give it its derived menu order "
                             f"({DERIVED_FIX})")
    taken = stock.get(order, ())
    check(not taken, f"{what}: {MENU_ORDER} {order} is the menu order of the stock Operation {', '.join(taken)}. Two "
                     f"Operations with one menu order stop the game at start with a map pack configuration error, "
                     f"\"Duplicate {MENU_ORDER} {order}\": give this Operation its derived menu order ({DERIVED_FIX}), "
                     f"a hash of its scenario GUID that no stock Operation holds and no other mod is likely to")
    return order


def menu_order_gate(items: list[Item], content: Content) -> str:
    """An extra gate (profile.ExtraGate) for an Operation: the MapConfiguration the build plans to ship holds a menu
    order no stock Operation holds (check_menu_order over stock_menu_orders)."""
    inner = def_path("MapConfiguration", TXN, content.scenario)
    hits = [it for it in items if it.pack == "Definition" and it.path == inner]
    check(len(hits) == 1, f"the mod ships {len(hits)} {inner}, expected 1")
    stock = stock_menu_orders()
    order = check_menu_order(b"".join(hits[0].chunks()), inner, stock)
    operations = len({name for names in stock.values() for name in names})
    return f"{MENU_ORDER} {order}, the menu order of none of the {operations} stock Operations"
