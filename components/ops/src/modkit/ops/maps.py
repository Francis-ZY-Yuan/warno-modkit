"""Stock maps an op can move to: where their files lie in the extraction, their minimap frame, and the review overlay.

An op cloned from a template (``modkit.ops.profile.SURVIVORS``) keeps the template's script frame but plays on another
stock map: the profile swaps the map names into the Definition (``OpProfile.map_strings``, ``map_trans``) and ships
some of the map's own Details byte for byte (``map_details``, ``map_copies``). A ``StockMap`` holds those facts for one
map, read off the game's own scenario for it, plus the geometry content needs:

* positions are minimap pixels: one is ``world_per_px`` world units on both axes, with no flip (world x grows with
  the column, world y with the row);
* ``playable_polygon()`` is the ring of the map's playable zone, in world units;
* ``render_overlay()`` draws marks and rings on the map's Preview picture, a review file never shipped;
* ``west_arrivals`` are the map scenario's own player entries (reinforcement locations and aerial corridors) on its
  west edge, which an op whose player holds that edge copies (``player_arrivals``).

The maps: ``GEISA`` (its 10vs10 conquest layout, whole) and ``TWIN_CITIES`` (its small layout
``SM_SU_3x3_TwinCities_03``, for an op on a cut of it).

**A cut** (``Cut``) is an op's playable zone on a box of a stock layout, smaller than the layout's own zone: the box in
minimap px, each edge moved onto the nearest edge of the layout's AI tiles (``SNAP_PX``; a whole pixel cannot name an
edge that lies at 145.6 px exactly), and the AI grid cut to it. The game crashed loading a whole-map grid under a
smaller zone, so the grid must be the tiles inside the box and nothing else (the ops knowledge record
ai-grid-tiles-playable-zone):

* ``Cut.items`` is an ``OpProfile.extra_items`` entry: the Details files ``out/PlayableZone.ndfbin`` (the box's ring,
  its Center at the box's centre and the map's ``ground_z``) and ``out/IAStratZone.ndfbin`` and
  ``out/IAStrat_PathCache.ndfbin`` (``zones.ia_grid_subset`` of the layout's grid), each generated and dumped. The
  layout's grid is read, and the box held to ``gates.check_grid_subset`` (with the map's ``grid_seam``), when a build
  plans them: a box whose edges are not tile edges, or whose tiles leave a hole, fails the build with one FAILED line.
  The profile ships none of these three among its ``map_copies`` (``StockMap.copies`` names none of them), and names
  ``CUT_SHAPE_SOURCES`` among its ``shape_sources`` (gate 2 holds generated files to stock's shapes).
* ``Cut.gate()`` is the ``grid`` extra gate (``OpProfile.extra_gates``): read from the planned Details, the shipped
  playable zone is a rectangle, the layout's grid keeps ``gates.check_grid_subset`` under it, and the shipped AI grid
  is that cut, byte for byte. It replaces ``gates.grid_gate`` for an op on a cut.

**An opening camera** (``OpeningCamera``) is a camera move the script runs right after LoadingDone, then a snap to its
last key (``bricks.g_camera``), so a deployment phase opens on the op's own ground and not at the engine's default
camera: ``OpeningCamera.items`` ships the two paths as the Details file ``CamPaths_LevelDesign.ndfbin`` in place of the
map's own camera paths, held to the camera gate (``check_camera_paths``: stock's key shape, every eye over the map and
at least stock's lowest start camera above the ground, the last view inside the cut).

Named places are content, not map facts: each op keeps its own. The ones more than one example op uses on Geisa are
kept once here, read-only (``GEISA_POINTS``, ``GEISA_BOXES``).

Paths are relative to the stock extraction and resolved when used (``modkit.ops.profile.extracted``).
"""
from __future__ import annotations

import math
import os
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from types import MappingProxyType

from modkit.core import tgv
from modkit.core.gates import check
from modkit.core.ndfbin import encode_image
from modkit.ops.bricks import g_camera
from modkit.ops.files import read_file
from modkit.ops.gates import IA_GRID_FILES, PLAYABLE_FILE, check_grid_subset, shipped_details
from modkit.ops.graph import Node, build_graph, decode, encode
from modkit.ops.items import Item, mem_item
from modkit.ops.leveldesign import LdItem
from modkit.ops.profile import Content, ExtraGate, extracted
from modkit.ops.zones import (
    area_bbox, camera_paths_graph, ia_grid_subset, ia_zone_graph, path_cache_graph, playable_zone_graph,
    read_ia_grid, read_playable_polygon, rect_polygon,
)

# One player entry: (ranking, name suffix, add-on, position, rotation, start, end), world units.
Arrival = tuple[str, str, str, tuple[float, float], float, tuple[float, float], tuple[float, float]]

# World units per minimap pixel, on both axes, on every stock map the toolkit reads (Geisa; Twin Cities, whose small
# layout's playable zone lands on whole pixels with it). A Preview pixel is half that.
WORLD_PER_MINIMAP_PX = 2560.0


def picture_path(map_name: str, kind: str) -> str:
    """The stock map `map_name`'s `kind` picture ('Preview' or 'Minimap'), relative to the extraction."""
    return f"basemaps/{map_name}/PC/Texture/{map_name}/{kind}.tgv"


@dataclass(frozen=True)
class StockMap:
    """One stock map, as an op that moves onto it needs it."""
    name: str                          # the map datapack (ScenarioInfo.RootDatapackName) and its basemaps/ folder
    env_settings: str                  # the $/GraphicSettings/EnvironmentSettings/<name> its Definition imports
    details: str                       # the Details pack folder of its stock scenario, relative to the extraction
    copies: tuple[str, ...]            # the Details files an op ships byte for byte
    ground_z: float                    # Center z of its PlayableZone: the z of generated zone areas
    minimap_px: tuple[int, int]        # the minimap's size in pixels (width, height)
    world_per_px: float                # world units per minimap pixel, both axes
    west_arrivals: tuple[Arrival, ...] = ()
    # The widest gap or overlap between neighbouring tiles of the layout's AI grid, in world units: a cut of it
    # (Cut) holds its tiles to gates.check_grid_subset with this seam. 0: not measured (an op ships the grid whole).
    grid_seam: float = 0.0

    # ------------------------------------------------------------------ frame

    def px_to_world(self, p: tuple[float, float]) -> tuple[float, float]:
        """Minimap pixels to world units: both axes scaled by world_per_px, no flip."""
        return (p[0] * self.world_per_px, p[1] * self.world_per_px)

    def world_to_px(self, w: tuple[float, float]) -> tuple[float, float]:
        return (w[0] / self.world_per_px, w[1] / self.world_per_px)

    # ------------------------------------------------------------------ files

    def picture(self, kind: str) -> str:
        """The map's `kind` picture ('Preview' or 'Minimap'), relative to the extraction."""
        return picture_path(self.name, kind)

    def playable_polygon(self) -> list[tuple[float, float]]:
        """The PlayableZone ring of the map's Details in world units (closed: the first vertex is repeated last)."""
        return read_playable_polygon(read_file(extracted(f"{self.details}/out/PlayableZone.ndfbin")))

    def ia_grid(self) -> tuple[list, list]:
        """The AI grid of the map's Details: zones.read_ia_grid's (areas, entries) of its out/ files."""
        return read_ia_grid(*(extracted(f"{self.details}/{inner}") for inner in IA_GRID_FILES))

    def player_arrivals(self, prefix: str) -> list[LdItem]:
        """west_arrivals as LevelDesign items named `prefix` + suffix (NumAlliance left out: the player's side)."""
        return [LdItem(ranking, f"{prefix}{suffix}", *pos, addon, rotation=rot, start=start, end=end)
                for ranking, suffix, addon, pos, rot, start, end in self.west_arrivals]

    # ------------------------------------------------------------------ review picture

    def render_overlay(self, path: str, marks: Mapping[str, tuple[float, float]],
                       rings: Iterable[Sequence[tuple[float, float]]] = ()) -> str:
        """Writes `path`, a PNG not shipped: the map's Preview with each mark as a yellow cross-hair and its name,
        and each ring as a white line. Marks and ring vertices are in minimap px. Returns a line for the build log."""
        return render_overlay(extracted(self.picture("Preview")), self.minimap_px[0], path, marks, rings)

    def overlay_output(self, filename: str) -> Callable[[Content, str], str]:
        """A review output (OpProfile.extra_outputs) writing `filename` into the out folder: every item of the content
        as a mark, and the playable zone and every zone polygon as rings."""
        def write(content: Content, out_dir: str) -> str:
            marks = {it.name: self.world_to_px((it.x, it.y)) for it in content.items}
            rings = [[self.world_to_px(p) for p in self.playable_polygon()]]
            rings += [[self.world_to_px(p) for p in it.polygon] for it in content.items if it.polygon]
            return self.render_overlay(os.path.join(out_dir, filename), marks, rings)
        return write


# Geisa, the stock 4x3 map, as its 10vs10 conquest scenario lays it out. The Details folder also holds the legacy
# layout (CamPath/, IAStratZone/, ...), which is never shipped, so the copies are named. Its west-edge entries are the
# scenario's alliance-0 reinforcement locations and aerial corridors (LevelDesign P0_AutoName_4, _7, _22, _23:
# position, rotation, start and end verbatim). The game gives a corridor the side of the deployment or command zone
# its End lies in, so an op that copies them needs a player zone over the Ends (gates.check_arrivals).
GEISA = StockMap(
    name="_4x3_geisa",
    env_settings="Geisa",
    details="geisa_op/_4x3_geisa_10vs10_CONQ_Details",
    copies=("out/PlayableZone.ndfbin", "out/IAStratZone.ndfbin", "out/IAStrat_PathCache.ndfbin",
            "CamPaths_LevelDesign.ndfbin"),
    ground_z=49428.48828125,
    minimap_px=(768, 1024),
    world_per_px=WORLD_PER_MINIMAP_PX,
    west_arrivals=(
        ("ReinforcementLocations", "_RL_W1", "ReinforcementLocation", (40255.0, 965286.0), 0.14081824,
         (13809.0, 961541.0), (66701.0, 969031.0)),
        ("ReinforcementLocations", "_RL_W2", "ReinforcementLocation", (37863.496, 1514708.5), 0.012691067,
         (11677.0, 1514376.0), (64050.0, 1515041.0)),
        ("AerialCorridors", "_AC_W1", "AerialCorridor", (41418.996, 941874.5), 0.12718329,
         (15970.0, 938623.0), (66868.0, 945126.0)),
        ("AerialCorridors", "_AC_W2", "AerialCorridor", (36551.996, 1540616.0), 0.02010006,
         (11486.0, 1540112.0), (61618.0, 1541120.0)),
    ),
)

# Twin Cities, the stock 3x3 map, as its small layout SM_SU_3x3_TwinCities_03 lays it out (playable x 0.125-432.125,
# y 145.6-767.9 minimap px; its AI grid tiles that box). An op on it plays a cut of that layout (Cut). Read off:
# - name: ScenarioInfo.RootDatapackName of the layout's own Definition (SM_SU_3x3_TwinCities_03_Definition), as of
#   the 10vs10 conquest's;
# - env_settings: the base EnvironmentSettings every Twin Cities scenario imports (the 10vs10 conquest's first, as
#   Geisa's is Geisa; SM_SU_03's 'evening' entry), beside its _Night, _Morning, _Noon and _Afternoon variants;
# - copies: the newest CamPaths (revision 197351, 341 B; camp0 and camp1, the deployment zones' WarmupCamPath). An op
#   on a cut generates the PlayableZone and the AI grid (Cut.items); the fallback, the layout's whole zone, would also
#   copy out/PlayableZone.ndfbin, out/IAStratZone.ndfbin and out/IAStrat_PathCache.ndfbin;
# - ground_z: the Center z of the layout's out/PlayableZone.ndfbin;
# - minimap_px: Minimap.tgv's header (768 x 768; Preview.tgv is 1,536 x 1,536);
# - world_per_px: the 10vs10 conquest's playable zone spans the whole map, 0 to 1,966,080 world on both axes, which is
#   768 minimap px of 2,560;
# - grid_seam: the layout's tiles stand up to 320 world (1/8 px) off where their neighbours' edges are: rows start at
#   x 0 or 320, and one column edge lies at 138,240, 138,560 or 138,880 by row, a gap or an overlap;
# - west_arrivals: none (its entries, either side's, are on the north and south edges; an op on a cut lays out its
#   own).
TWIN_CITIES = StockMap(
    name="_3x3_TwinCities",
    env_settings="TwinCities",
    details="twincities_op/SM_SU_3x3_TwinCities_03_Details",
    copies=("CamPaths_LevelDesign.ndfbin",),
    ground_z=19662.5703125,
    minimap_px=(768, 768),
    world_per_px=WORLD_PER_MINIMAP_PX,
    grid_seam=320.0,
)

# Named places on Geisa that more than one example op uses (the probes and Open Door), in minimap px (768 x 1024;
# GEISA.px_to_world gives world units). An op's own places stay with the op; a place two ops use is kept here once,
# read-only. Each was checked on Geisa's Minimap and Preview, and moved at most 20 px onto a road or into a clearing
# where it was off one (the reason beside it).
_POINTS: dict[str, tuple[float, float]] = {
    "TOWN_NE": (658, 232), "VILLAGE_E": (700, 475), "TOWN_SE": (645, 590),
    "SHOULDER": (520, 281), "RESERVE_N": (352, 270),
    "NECK_MID": (395, 402), "LZ_MID": (386, 382), "NECK_S": (468, 600),
    "HIDE_S": (522, 740), "TOWN_SW": (116, 655),
    "ENTRY_N": (664, 38),        # on the E-W road nearest the north edge (y 36..39 here)
    "ENTRY_E": (756, 400),       # on the east-edge road (y 395..398)
    "ENTRY_NE": (756, 270),      # open farmland: no road reaches the east edge within 20 px
    "ENTRY_SE": (756.0, 585.0),  # on the east-edge road (y 583..586), which runs straight west into Town SE
    # NE-corner forest, inside a 2S3M battery's range of NECK MID (Ammunition.ndf MaximumRangeGRU 17,500, at
    # shapes.GRU_WORLD) and beyond the BM-27's 10,000 GRU minimum
    "CORNER_PACT": (734, 54),
    "TRACK_SE_IN": (622, 622),   # on the NW-SE road just SW of Town SE
    "EDGE_N": (386, 16),         # helicopter entry: forest, no road within 30 px (it flies in)
    "EDGE_W": (24, 593),         # on the E-W road at the west edge
    "HOLD_W": (60, 593),         # same road
    "SACK_MID": (340, 406),      # on the passage road (y 404..407)
    # about 1 km west of Village E, on the E-W road just south of a farmstead (road and yard pixels at y 486..494;
    # due west, (616, 475), is the farm's trees)
    "FARM_ROAD": (616, 488),
}
_POINTS["PL_BLUE"] = _POINTS["VILLAGE_E"]   # the phase line through the eastern towns, drawn at Village E
GEISA_POINTS: Mapping[str, tuple[float, float]] = MappingProxyType(_POINTS)
# Named areas on Geisa that more than one example op uses: minimap-px boxes (x0, y0, x1, y1).
GEISA_BOXES: Mapping[str, tuple[float, float, float, float]] = MappingProxyType({
    "TOWN_SW": (90, 610, 190, 700),          # over Town SW's buildings: a command zone in the probes and Open Door
})

# --------------------------------------------------------------------------- the cut

SNAP_PX = 0.5   # how far a cut's edge in minimap px may lie from the tile edge it names (a whole pixel names it)
# The stock files whose shapes a cut's generated files may use (OpProfile.shape_sources, relative to the extraction).
CUT_SHAPE_SOURCES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    inner: (f"scenarios/*/{inner}", f"kreide_op/*/{inner}") for inner in (PLAYABLE_FILE, *IA_GRID_FILES)})


def _grid_files(kept: list, costs: list) -> dict[str, bytes]:
    """The AI grid files of the tiles `kept` and their path `costs` (zones.ia_grid_subset's)."""
    return {IA_GRID_FILES[0]: encode(build_graph(ia_zone_graph(kept), []), IA_GRID_FILES[0]),
            IA_GRID_FILES[1]: encode(build_graph(path_cache_graph(costs), []), IA_GRID_FILES[1])}


@dataclass(frozen=True)
class Cut:
    """An op's playable zone on a box of a stock layout: `box_px` (x0, y0, x1, y1), minimap px of `map`, each edge
    naming an edge of the layout's AI tiles (the module docstring)."""
    map: StockMap
    box_px: tuple[float, float, float, float]

    def label(self) -> str:
        x0, y0, x1, y1 = self.box_px
        return f"x {x0:g}..{x1:g}, y {y0:g}..{y1:g} px of {self.map.details}"

    def box(self, areas: list | None = None) -> tuple[float, float, float, float]:
        """box_px in world units, each edge moved onto the nearest edge of the layout's tiles on its axis (`areas`: the
        layout's grid's, read when None). An edge with no tile edge within SNAP_PX fails."""
        areas = self.map.ia_grid()[0] if areas is None else areas
        edges = ({e for a in areas for e in area_bbox(a)[0::2]}, {e for a in areas for e in area_bbox(a)[1::2]})
        wpp, out = self.map.world_per_px, []
        for k, (v, side) in enumerate(zip(self.box_px, ("x0", "y0", "x1", "y1"))):
            edge = min(edges[k % 2], key=lambda e: (abs(e - v * wpp), e))
            off = abs(edge / wpp - v)
            check(off <= SNAP_PX, f"cut {self.label()}: its {side} edge lies {off:.2f} px from the nearest AI tile "
                                  f"edge ({edge / wpp:g} px); a cut's edges are tile edges, named to within "
                                  f"{SNAP_PX} px")
            out.append(edge)
        return out[0], out[1], out[2], out[3]

    def details(self) -> dict[str, bytes]:
        """The cut's Details files (inner path -> bytes): the PlayableZone, the box's ring with its Center at the box's
        centre and the map's ground_z, and the AI grid of the tiles inside it. The layout's grid is read here and the
        box held to gates.check_grid_subset (with the map's grid_seam) first."""
        areas, entries = self.map.ia_grid()
        box = self.box(areas)
        check_grid_subset(areas, entries, box, seam=self.map.grid_seam)
        x0, y0, x1, y1 = box
        zone = playable_zone_graph(list(rect_polygon(box)), ((x0 + x1) / 2, (y0 + y1) / 2, self.map.ground_z))
        return {PLAYABLE_FILE: encode(build_graph(zone, []), PLAYABLE_FILE),
                **_grid_files(*ia_grid_subset(areas, entries, box))}

    def items(self, content: Content | None = None) -> list[Item]:
        """The cut's Details files as planned items (an OpProfile.extra_items entry): generated, each dumped as
        <stem>.txt."""
        source = f"generated (cut {self.label()})"
        return [mem_item("Details", inner, raw, "generate", source,
                         fixture=inner.rsplit("/", 1)[-1].replace(".ndfbin", ".txt"))
                for inner, raw in self.details().items()]

    def gate(self) -> ExtraGate:
        """The `grid` extra gate of an op on this cut (OpProfile.extra_gates): check_shipped."""
        return ExtraGate("grid", self.check_shipped)

    def check_shipped(self, items: list[Item], content: object = None) -> str:
        """Read from the planned Details `items`: the shipped playable zone is a rectangle, the map's grid keeps
        gates.check_grid_subset under it (with the map's grid_seam), and the shipped AI grid is that cut, byte for
        byte. Returns the build log's line."""
        raw = shipped_details(items, PLAYABLE_FILE)
        check(raw is not None, f"the mod ships no {PLAYABLE_FILE}")
        ring = read_playable_polygon(raw)
        xs, ys = [p[0] for p in ring], [p[1] for p in ring]
        box = (min(xs), min(ys), max(xs), max(ys))
        check(ring == list(rect_polygon(box)), f"the shipped playable zone is not a rectangle: {ring}")
        areas, entries = self.map.ia_grid()
        tiles, costs = check_grid_subset(areas, entries, box, seam=self.map.grid_seam)
        x0, y0, x1, y1 = (v / self.map.world_per_px for v in box)
        where = f"the shipped playable zone x {x0:g}..{x1:g}, y {y0:g}..{y1:g} px"
        for inner, want in _grid_files(*ia_grid_subset(areas, entries, box)).items():
            got = shipped_details(items, inner)
            check(got is not None, f"the mod ships no {inner}")
            check(got == want,
                  f"{inner}: the shipped AI grid is not the cut of {self.map.details}'s grid under {where}")
        return (f"{tiles:,} AI tiles and {costs:,} path costs of {self.map.details}, cut on its tile edges to {where} "
                f"(seams up to {self.map.grid_seam:,.0f} world)")


# --------------------------------------------------------------------------- the opening camera

CAMPATHS_FILE = "CamPaths_LevelDesign.ndfbin"   # the Details file of a scenario's camera paths
# The stock files whose shapes a generated camera paths file may use (OpProfile.shape_sources).
CAMERA_SHAPE_SOURCES: Mapping[str, tuple[str, ...]] = MappingProxyType({
    CAMPATHS_FILE: (f"scenarios/*/{CAMPATHS_FILE}", f"kreide_op/*/{CAMPATHS_FILE}")})
# Stock's lowest start camera: BlackHorsesLastStand's camera_start (#145), its eye 376,057.125 world units above the
# Center z of its playable zone. Every key of the five start cameras stock snaps right before LoadingDone stands
# 376,057 to 773,047 above its ground (the ops knowledge record start-camera-before-loading-done). Every key of an
# opening camera stands at least this high (check_camera_paths).
START_CAMERA_MIN_HEIGHT = 376057.125
DIRECTION_TOLERANCE = 1e-3   # how far a key's direction may be from unit length (stock's are unit to float32 rounding)
PATH_PROPS = ["PositionKeyVector", "DirectionKeyVector", "Name"]   # a stock TCameraPath's properties, in order
Key = tuple[tuple[float, float, float], tuple[float, float, float]]   # (the eye's position, the unit view direction)


@dataclass(frozen=True)
class CameraKey:
    """One key of a camera path, by the view it gives: looking down `pitch_deg` at `at_px` (minimap px) from `height`
    world units above the map's ground_z, heading along `facing` (a minimap-px vector: (0, 1) faces south)."""
    at_px: tuple[float, float]
    facing: tuple[float, float]
    height: float
    pitch_deg: float

    def key(self, on: StockMap) -> Key:
        """The key on the map `on`, world units: the eye stands back from `at_px` along the view, so the view's centre
        line meets the ground (ground_z) there."""
        tx, ty = on.px_to_world(self.at_px)
        fx, fy = self.facing
        norm = math.hypot(fx, fy)
        check(norm > 0, f"camera key at {self.at_px}: facing {self.facing} has no heading")
        pitch = math.radians(self.pitch_deg)
        check(0 < pitch < math.pi / 2, f"camera key at {self.at_px}: pitch {self.pitch_deg} is not between 0 and 90")
        d = (math.cos(pitch) * fx / norm, math.cos(pitch) * fy / norm, -math.sin(pitch))
        reach = self.height / math.sin(pitch)
        return (tx - d[0] * reach, ty - d[1] * reach, on.ground_z + self.height), d


def view_centre(key: Key, ground_z: float) -> tuple[float, float]:
    """Where a key's view centre line meets the ground (ground_z), world units. The direction must look down."""
    (x, y, z), (dx, dy, dz) = key
    t = (ground_z - z) / dz
    return x + t * dx, y + t * dy


def read_camera_paths(raw: bytes) -> dict[str, list[Key]]:
    """The paths of a camera paths file, name -> its keys, held to stock's key shape first: every object a TCameraPath
    (PositionKeyVector, DirectionKeyVector and Name, in that order) or a TCameraPathKey (one vec3 Coord), each path's
    two key lists one key or more and of one length, and the file zones.camera_paths_graph's of its own values, byte
    for byte (as gates.check_details_generators rebuilds every stock one)."""
    nb, _, image = decode(raw)
    props = [{nb.pname(pi): v for pi, v in ob.props} for ob in nb.objects]
    paths: dict[str, list[Key]] = {}
    for i, (ob, p) in enumerate(zip(nb.objects, props)):
        cls = nb.cname(ob.cls)
        if cls == "TCameraPathKey":
            coord = p.get("Coord")
            check(list(p) == ["Coord"] and coord.tag == 0x0B and len(coord.v) == 3,
                  f"camera paths #{i}: a TCameraPathKey holds one vec3 Coord in stock, not {list(p)}")
            continue
        check(cls == "TCameraPath", f"camera paths #{i}: {cls} is no stock camera path object")
        check(list(p) == PATH_PROPS, f"camera paths #{i}: a stock TCameraPath holds {PATH_PROPS}, not {list(p)}")
        name = nb.strings[p["Name"].v].decode("latin-1")
        pos, dirs = ([props[k.v.index]["Coord"].v for k in p[vec].v] for vec in PATH_PROPS[:2])
        check(len(pos) == len(dirs) >= 1, f"camera path {name}: {len(pos)} position and {len(dirs)} direction keys; "
                                          f"stock's are one or more, as many of each")
        check(name not in paths, f"camera path {name} is named twice")
        paths[name] = list(zip(pos, dirs))
    graph = camera_paths_graph([(name, [e for e, _ in keys], [d for _, d in keys]) for name, keys in paths.items()])
    check(encode_image(build_graph(graph, [])) == image, "the camera paths file is not in stock's layout "
                                                         "(zones.camera_paths_graph does not rebuild it)")
    return paths


def check_camera_paths(raw: bytes, on: StockMap, box_px: tuple[float, float, float, float], move: str,
                       end: str) -> str:
    """The camera gate, on a camera paths file as it ships (the game reads it as the scenario's Details file
    CAMPATHS_FILE) for an opening camera on `on` that flies `move` and then snaps to `end`:
    - the file holds the two paths and nothing else, each in stock's key shape (read_camera_paths); `move` has two
      keys or more, and `end` is one key, the move's last, as stock ends an opening move (DelayedRetribution's
      camera_intro_end #79 is camera_intro #92's last key; GloryOrAttrition #74 and #96, TheHydra #168 and #167);
    - every key looks down, its direction a unit vector;
    - every key's eye stands over the map (0 to its minimap size on both axes), at least START_CAMERA_MIN_HEIGHT above
      its ground_z (stock's lowest start camera);
    - the last key's view centre lies inside `box_px` (minimap px: the op's cut).
    Returns the build log's line."""
    min_height = START_CAMERA_MIN_HEIGHT
    paths = read_camera_paths(raw)
    check(set(paths) == {move, end}, f"the camera paths file holds {sorted(paths)}, not the opening's {move} and {end}")
    check(len(paths[move]) >= 2, f"camera path {move}: one key is a snap, not a move")
    check(paths[end] == paths[move][-1:], f"camera path {end} is not the one key {move} ends on")
    w, h = (n * on.world_per_px for n in on.minimap_px)
    low = math.inf
    for name, keys in paths.items():
        for k, ((x, y, z), d) in enumerate(keys):
            where = f"camera path {name} key {k}"
            check(abs(math.hypot(*d) - 1.0) <= DIRECTION_TOLERANCE and d[2] < 0,
                  f"{where}: its direction {d} is not a unit vector looking down")
            check(0 <= x <= w and 0 <= y <= h, f"{where}: its eye at {on.world_to_px((x, y))} px is off the map")
            check(z - on.ground_z >= min_height,
                  f"{where}: its eye stands {z - on.ground_z:,.0f} above the ground, below stock's lowest start "
                  f"camera ({min_height:,.0f}, BlackHorsesLastStand's camera_start)")
            low = min(low, z - on.ground_z)
    cx, cy = on.world_to_px(view_centre(paths[move][-1], on.ground_z))
    x0, y0, x1, y1 = box_px
    check(x0 <= cx <= x1 and y0 <= cy <= y1, f"camera path {move}: its last view centres on ({cx:.1f}, {cy:.1f}) px, "
                                             f"outside the cut x {x0:g}..{x1:g}, y {y0:g}..{y1:g} px")
    return (f"{move} ({len(paths[move])} keys) then {end}, its last key: every eye over the map, at least {low:,.0f} "
            f"above the ground (stock's lowest start camera {min_height:,.0f}), the last view centred on "
            f"({cx:.1f}, {cy:.1f}) px, inside the cut")


@dataclass(frozen=True)
class OpeningCamera:
    """An op's opening camera on `cut`'s map, set where stock sets a deployment-phase Operation's opening view (the ops
    knowledge record start-camera-before-loading-done): right after LoadingDone the camera flies the path `move`
    through `keys` in `seconds`, easing in and out, the player's actions blocked and Escape skipping it; then it snaps
    to the one-key path `end`, the move's last key, so a skipped move ends there too (DelayedRetribution's #64/#92
    then #65/#79). The script then restores the HUD, and the deployment phase opens on the last key's view.

    * ``items`` is an ``OpProfile.extra_items`` entry: the Details file CAMPATHS_FILE holding the two paths
      (zones.camera_paths_graph), generated, held to check_camera_paths when a build plans it (a failure fails the
      build with one FAILED line) and dumped. The profile then ships no CAMPATHS_FILE among its ``map_copies``, and
      names CAMERA_SHAPE_SOURCES among its ``shape_sources``.
    * ``cutscenes`` are the script's two nodes, run right after LoadingDone (mission.script_frame's `opening`)."""
    cut: Cut
    move: str
    end: str
    keys: tuple[CameraKey, ...]
    seconds: float

    def path_keys(self) -> list[Key]:
        """The move's keys on the cut's map, world units."""
        return [k.key(self.cut.map) for k in self.keys]

    def paths(self) -> list[tuple[str, list, list]]:
        """zones.camera_paths_graph's input: the move, then the end, its last key."""
        keys = self.path_keys()
        return [(self.move, [e for e, _ in keys], [d for _, d in keys]), (self.end, [keys[-1][0]], [keys[-1][1]])]

    def details(self) -> bytes:
        """The camera paths file: the two paths."""
        return encode(build_graph(camera_paths_graph(self.paths()), []), CAMPATHS_FILE)

    def check(self, raw: bytes) -> str:
        """check_camera_paths of a camera paths file for this camera, inside the cut's box. Returns its line."""
        return check_camera_paths(raw, self.cut.map, self.cut.box_px, self.move, self.end)

    def cutscenes(self) -> tuple[Node, Node]:
        """The move (bricks.g_camera with `seconds`), then the snap to its last key (bricks.g_camera)."""
        return g_camera(self.move, self.seconds), g_camera(self.end)

    def items(self, content: Content | None = None) -> list[Item]:
        """The camera paths file as a planned item (an OpProfile.extra_items entry): generated, held to check first,
        dumped as CamPaths_LevelDesign.txt."""
        raw = self.details()
        self.check(raw)
        x, y = self.keys[-1].at_px
        return [mem_item("Details", CAMPATHS_FILE, raw, "generate",
                         f"generated (opening camera {self.move} then {self.end}, ending on x {x:g}, y {y:g} px)",
                         fixture=CAMPATHS_FILE.replace(".ndfbin", ".txt"))]

# --------------------------------------------------------------------------- the overlay

# 3x5 glyphs for the mark labels ('#' ink, '-' blank, rows separated by '/'); labels are upper-cased, other
# characters stay blank.
_GLYPHS = {
    "A": "-#-/#-#/###/#-#/#-#", "B": "##-/#-#/##-/#-#/##-", "C": "-##/#--/#--/#--/-##", "D": "##-/#-#/#-#/#-#/##-",
    "E": "###/#--/##-/#--/###", "F": "###/#--/##-/#--/#--", "G": "-##/#--/#-#/#-#/-##", "H": "#-#/#-#/###/#-#/#-#",
    "I": "###/-#-/-#-/-#-/###", "J": "--#/--#/--#/#-#/-#-", "K": "#-#/#-#/##-/#-#/#-#", "L": "#--/#--/#--/#--/###",
    "M": "#-#/###/###/#-#/#-#", "N": "###/#-#/#-#/#-#/#-#", "O": "-#-/#-#/#-#/#-#/-#-", "P": "##-/#-#/##-/#--/#--",
    "Q": "-#-/#-#/#-#/##-/-##", "R": "##-/#-#/##-/#-#/#-#", "S": "-##/#--/-#-/--#/##-", "T": "###/-#-/-#-/-#-/-#-",
    "U": "#-#/#-#/#-#/#-#/###", "V": "#-#/#-#/#-#/#-#/-#-", "W": "#-#/#-#/###/###/#-#", "X": "#-#/#-#/-#-/#-#/#-#",
    "Y": "#-#/#-#/-#-/-#-/-#-", "Z": "###/--#/-#-/#--/###",
    "0": "###/#-#/#-#/#-#/###", "1": "-#-/##-/-#-/-#-/###", "2": "##-/--#/-#-/#--/###", "3": "##-/--#/-#-/--#/##-",
    "4": "#-#/#-#/###/--#/--#", "5": "###/#--/##-/--#/##-", "6": "-##/#--/###/#-#/###", "7": "###/--#/-#-/-#-/-#-",
    "8": "###/#-#/###/#-#/###", "9": "###/#-#/###/--#/##-", "_": "---/---/---/---/###",
}
LABEL_SCALE = 3                                 # canvas px per glyph dot
MARK_COLOUR, RING_COLOUR = b"\xff\xe0\x00", b"\xff\xff\xff"


def render_overlay(preview: str, minimap_width: int, path: str, marks: Mapping[str, tuple[float, float]],
                   rings: Iterable[Sequence[tuple[float, float]]] = ()) -> str:
    """The review picture: the Preview at `preview` (a .tgv, any multiple of the minimap's `minimap_width`) with each
    mark as a yellow cross-hair and its name, and each ring as a white line, written to `path` as a PNG. Marks and
    ring vertices are in minimap px. Returns a line for the build log."""
    hdr, rgba = tgv.read_tgv(preview)
    w, h = hdr.width, hdr.height
    k = w / minimap_width       # canvas px per minimap px
    img = bytearray(tgv.drop_alpha(rgba))

    def put(x: float, y: float, col: bytes) -> None:
        xi, yi = int(x), int(y)
        if 0 <= xi < w and 0 <= yi < h:
            img[(yi * w + xi) * 3:(yi * w + xi) * 3 + 3] = col

    def rect(x0: int, y0: int, x1: int, y1: int, col: bytes) -> None:
        for yy in range(max(y0, 0), min(y1, h)):
            for xx in range(max(x0, 0), min(x1, w)):
                img[(yy * w + xx) * 3:(yy * w + xx) * 3 + 3] = col

    def line(a: tuple[float, float], b: tuple[float, float], col: bytes) -> None:
        n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1]))) + 1
        for s in range(n + 1):
            put(a[0] + (b[0] - a[0]) * s / n, a[1] + (b[1] - a[1]) * s / n, col)

    def label(x: int, y: int, text: str) -> None:
        """White text with its top-left at (x, y), on a black plate."""
        rect(x - LABEL_SCALE, y - LABEL_SCALE, x + len(text) * 4 * LABEL_SCALE, y + 6 * LABEL_SCALE, b"\x00\x00\x00")
        for i, ch in enumerate(text.upper()):
            for r, row in enumerate(_GLYPHS.get(ch, "").split("/")):
                for c, dot in enumerate(row):
                    if dot == "#":
                        rect(x + (i * 4 + c) * LABEL_SCALE, y + r * LABEL_SCALE,
                             x + (i * 4 + c + 1) * LABEL_SCALE, y + (r + 1) * LABEL_SCALE, b"\xff\xff\xff")

    n_rings = 0
    for ring in rings:
        pts = [(x * k, y * k) for x, y in ring]
        for a, b in zip(pts, pts[1:]):
            line(a, b, RING_COLOUR)
        n_rings += 1
    arm = 2 * LABEL_SCALE + 2
    for name, (mx, my) in marks.items():
        cx, cy = mx * k, my * k
        line((cx - arm, cy), (cx + arm, cy), MARK_COLOUR)
        line((cx, cy - arm), (cx, cy + arm), MARK_COLOUR)
        rect(int(cx) - 1, int(cy) - 1, int(cx) + 2, int(cy) + 2, MARK_COLOUR)
        tw = len(name) * 4 * LABEL_SCALE
        tx = int(cx) + arm + 2                  # the name sits right of the mark, or left of it at the right edge
        label(tx if tx + tw < w else int(cx) - arm - 2 - tw, int(cy) - 2 * LABEL_SCALE, name)
    os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
    tgv.write_png(path, w, h, bytes(img), channels=3)
    return f"{os.path.basename(path)} ({w}x{h}): {len(marks)} marks, {n_rings} rings on the Preview"
