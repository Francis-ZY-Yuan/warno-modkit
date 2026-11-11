"""The storyboard: an Operation's design as one review page (map, plot, phases, objectives, order of battle), made
from one JSON spec.

    python -m modkit.ops.storyboard SPEC.json [--out DIR] [--check-units]

It writes ``DIR/index.html``, ``DIR/minimap.png`` and ``DIR/satellite.png``: the map's own Minimap and Preview (its
satellite picture), cropped, under an SVG overlay of the layout's zones and the design's marks, with a phase stepper,
a Minimap/Satellite switch, and the spec's tables and order of battle below. ``DIR`` defaults to
``storyboard/<name>`` in the build folder (``modkit.core.paths.build_root``): ``<name>`` is the spec's stem, or the
op's folder for an op's ``examples/<op>/docs/storyboard.json``. It prints a line per file, then the Artifact publish
line. Any failure prints one ``FAILED:`` line and exits 1. ``--check-units`` also holds every order-of-battle unit
key to the game's unit database (``modkit.ops.gates.unit_database``). The pictures are the game's own: the page is a
private review page, never committed (the warno-op-storyboard skill).

The spec (``version`` 1) is validated before anything is read: an unknown key or a bad value fails with its JSON
path (``$.marks[2].kind``). Every coordinate is in minimap pixels of the full map (``WORLD_PER_MINIMAP_PX`` world
units each); the SVG's viewBox is the crop box, so a crop never moves a mark. Prose is plain text, HTML-escaped,
except ``{style:text}`` (``text`` in that style's colour) and ``**bold**``; map text (labels, hover titles) is plain.

Keys (``?`` optional):

* ``version`` 1, ``title``, ``eyebrow?``, ``chips?`` ([label, text] pairs), ``lede?``, ``footer?`` (texts)
* ``styles``: name -> ``#rrggbb``; marks, deployments and OOB sides are drawn in one by name
* ``map``: ``name`` (the map datapack), ``layout`` (a Details folder below the extraction; its ``out/`` zones are
  drawn exact), ``crop?`` (``playable``, the default, ``full`` or [x0, y0, x1, y1]), ``deployments?`` (alliance ->
  {style, label, area?}; an ``area`` polygon [[x, y], ...] of 3 or more points is drawn instead of the layout's
  zone, or on its own when the layout has none for that alliance), ``zone_names?`` (stock command zone name ->
  name), ``command_zones?`` (1 or more; when present, exactly these are drawn, in order, and ``zone_names`` is not
  allowed: each is {stock, name?}, the layout's own zone, or {name, area, points}, an op's own zone, for an op on a
  cut of a stock layout), ``mark_scale?`` (a number above 0: the size of the map's text, strokes and drawn shapes
  against the look tuned on a 432 x 622 px crop; by default max(w / 432, h / 622) for the crop's w x h),
  ``default_picture?`` (minimap | satellite)
* ``phases?``: {id, name, time?, summary?, details?}; ``start_phase?`` (default the first)
* ``marks?``: each {kind, style, phases?, title?, ...}; ``phases`` absent or [] shows it in every phase:
  ``arrow`` (points, dashed?, label?), ``ring`` (at, r, dashed?, label?), ``units`` (at, count, label?),
  ``label`` (at, text, size? small | large), ``arc`` (from, to, bend, label?), ``burst`` (at, label?);
  a ``label`` is null or {text, at}
* ``sections?``: {heading, intro?, tables?, oob?}; a table is {columns, rows}, a cell a text, a number or
  {mark: ok | half | open, text}; an OOB side is {title, tag?, style?, groups: [{name, when?, note?,
  units: [[count, name, key?]]}]}
"""
from __future__ import annotations

import argparse
import html
import json
import math
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path

from modkit.core import paths, tgv
from modkit.ops.build import FAILURES, _utf8_streams
from modkit.ops.files import SETUP_FIX, read_file
from modkit.ops.gates import UNIT_PREFIX, unit_database
from modkit.ops.maps import WORLD_PER_MINIMAP_PX, picture_path
from modkit.ops.profile import extracted
from modkit.ops.zones import polygon_centroid, read_playable_polygon, read_zone_areas, zone_prop

VERSION = 1
PAGE, MINIMAP, SATELLITE = "index.html", "minimap.png", "satellite.png"
MAX_PAGE = 1024 * 1024              # the page itself; the pictures are published beside it
MAX_PICTURE = 3 * 1024 * 1024       # a satellite crop over this is halved
SPEC_NAME = "storyboard"            # an op keeps its spec as examples/<op>/docs/storyboard.json
MARKS = ("arrow", "ring", "units", "label", "arc", "burst")
MARK_CELLS = ("ok", "half", "open")
PICTURES = ("minimap", "satellite")

Point = tuple[float, float]


class SpecError(ValueError):
    """The spec breaks the schema. The message starts with the JSON path of the bad value."""


# --------------------------------------------------------------------------- text

_STYLE_REF = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*):[^{}]*\}")
_SPAN = re.compile(r"\{([A-Za-z][A-Za-z0-9_-]*):([^{}]*)\}|\*\*(.+?)\*\*")


def esc(text: str) -> str:
    """Plain text as HTML (element content or a quoted attribute)."""
    return html.escape(str(text), quote=True)


def text_html(text: str) -> str:
    """Spec prose as HTML: escaped, with ``{style:text}`` as a span in that style's colour and ``**bold**`` bold."""
    out, pos = [], 0
    for m in _SPAN.finditer(text):
        out.append(esc(text[pos:m.start()]))
        if m.group(1) is not None:
            out.append(f'<span class="tx tx-{m.group(1)}">{text_html(m.group(2))}</span>')
        else:
            out.append(f"<b>{text_html(m.group(3))}</b>")
        pos = m.end()
    out.append(esc(text[pos:]))
    return "".join(out)


# --------------------------------------------------------------------------- the schema

_STYLE_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]*\Z")
_COLOUR = re.compile(r"#[0-9A-Fa-f]{6}\Z")
_PHASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*\Z")
_MAP_NAME = re.compile(r"[A-Za-z0-9_]+\Z")
_PATH_PART = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.-]*\Z")
_PLAIN_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def _at(where: str, key: str | int) -> str:
    if isinstance(key, int):
        return f"{where}[{key}]"
    return f"{where}.{key}" if _PLAIN_KEY.match(key) else f"{where}[{json.dumps(key)}]"


def _kind(v: object) -> str:
    return {dict: "an object", list: "a list", str: "a string", bool: "a boolean", type(None): "null",
            int: "a number", float: "a number"}.get(type(v), type(v).__name__)


Checker = Callable[[object, str], None]


class _Validator:
    """Checks a spec against the schema; style and phase references against the spec's own lists."""

    def __init__(self) -> None:
        self.styles: set[str] = set()
        self.phases: list[str] = []

    @staticmethod
    def fail(where: str, why: str):
        raise SpecError(f"{where}: {why}")

    # ---- shapes

    def obj(self, v: object, where: str, fields: Mapping[str, tuple[bool, Checker]]) -> None:
        if not isinstance(v, dict):
            self.fail(where, f"expected an object, got {_kind(v)}")
        for key in v:
            if key not in fields:
                self.fail(_at(where, key), f"unknown key (allowed here: {', '.join(fields)})")
        for key, (required, check) in fields.items():
            if key in v:
                check(v[key], _at(where, key))
            elif required:
                self.fail(where, f"missing key {key!r}")

    def items(self, check: Checker, *, least: int = 0) -> Checker:
        def run(v: object, where: str) -> None:
            if not isinstance(v, list):
                self.fail(where, f"expected a list, got {_kind(v)}")
            if len(v) < least:
                self.fail(where, f"expected at least {least} items, got {len(v)}")
            for i, item in enumerate(v):
                check(item, _at(where, i))
        return run

    def mapping(self, key_ok: Callable[[str], bool], key_what: str, check: Checker) -> Checker:
        def run(v: object, where: str) -> None:
            if not isinstance(v, dict):
                self.fail(where, f"expected an object, got {_kind(v)}")
            for key, item in v.items():
                if not key_ok(key):
                    self.fail(_at(where, key), f"expected {key_what} as the key")
                check(item, _at(where, key))
        return run

    # ---- values

    def string(self, v: object, where: str) -> None:
        if not isinstance(v, str):
            self.fail(where, f"expected a string, got {_kind(v)}")

    def text(self, v: object, where: str) -> None:
        self.string(v, where)
        for m in _STYLE_REF.finditer(v):
            if m.group(1) not in self.styles:
                self.fail(where, f"{{{m.group(1)}:...}} names no style in $.styles")

    def boolean(self, v: object, where: str) -> None:
        if not isinstance(v, bool):
            self.fail(where, f"expected true or false, got {_kind(v)}")

    def number(self, v: object, where: str) -> None:
        if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
            self.fail(where, f"expected a number, got {_kind(v)}")

    def positive(self, v: object, where: str) -> None:
        self.number(v, where)
        if v <= 0:
            self.fail(where, "expected a number above 0")

    def count(self, v: object, where: str) -> None:
        if isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= 60:
            self.fail(where, "expected a whole number from 1 to 60")

    def point(self, v: object, where: str) -> None:
        if not isinstance(v, list) or len(v) != 2:
            self.fail(where, "expected a point [x, y] in minimap px")
        for i, c in enumerate(v):
            self.number(c, _at(where, i))

    def one_of(self, *values: str) -> Checker:
        def run(v: object, where: str) -> None:
            if v not in values:
                self.fail(where, f"expected one of {', '.join(values)}")
        return run

    def style(self, v: object, where: str) -> None:
        self.string(v, where)
        if v not in self.styles:
            self.fail(where, f"{v!r} names no style in $.styles")

    def phase(self, v: object, where: str) -> None:
        self.string(v, where)
        if v not in self.phases:
            self.fail(where, f"{v!r} names no phase in $.phases")

    # ---- the spec

    def spec(self, spec: object) -> None:
        self.obj(spec, "$", {
            "version": (True, self.version),
            "title": (True, self.string),
            "eyebrow": (False, self.string),
            "styles": (True, self.styles_table),
            "chips": (False, self.items(self.chip)),
            "lede": (False, self.text),
            "map": (True, self.map),
            "phases": (False, self.phase_list),
            "start_phase": (False, self.phase),
            "marks": (False, self.items(self.mark)),
            "sections": (False, self.items(self.section)),
            "footer": (False, self.items(self.text)),
        })

    def version(self, v: object, where: str) -> None:
        if v != VERSION or isinstance(v, bool):
            self.fail(where, f"this generator reads version {VERSION}")

    def styles_table(self, v: object, where: str) -> None:
        def colour(c: object, at: str) -> None:
            if not isinstance(c, str) or not _COLOUR.match(c):
                self.fail(at, "expected a colour #rrggbb")
        self.mapping(lambda k: bool(_STYLE_NAME.match(k)) and k != "none",   # st-none: an alliance with no style
                     "a style name (a letter, then letters, digits, - or _; not 'none')", colour)(v, where)
        self.styles = set(v)

    def chip(self, v: object, where: str) -> None:
        if not isinstance(v, list) or len(v) != 2:
            self.fail(where, "expected a chip [label, text]")
        self.string(v[0], _at(where, 0))
        self.text(v[1], _at(where, 1))

    def map(self, v: object, where: str) -> None:
        self.obj(v, where, {
            "name": (True, self.map_name),
            "layout": (True, self.layout),
            "crop": (False, self.crop),
            "deployments": (False, self.mapping(str.isdigit, "an alliance number", lambda d, at: self.obj(d, at, {
                "style": (True, self.style), "label": (True, self.string),
                "area": (False, self.polygon)}))),
            "zone_names": (False, self.mapping(bool, "a stock zone name", self.string)),
            "command_zones": (False, self.items(self.command_zone, least=1)),
            "mark_scale": (False, self.positive),
            "default_picture": (False, self.one_of(*PICTURES)),
        })
        if "command_zones" in v and "zone_names" in v:
            self.fail(_at(where, "zone_names"), "not allowed with command_zones: name a zone with command_zones' "
                                                "'name' (one source of truth)")

    def polygon(self, v: object, where: str) -> None:
        self.items(self.point, least=3)(v, where)

    def command_zone(self, v: object, where: str) -> None:
        if isinstance(v, dict) and "stock" in v:
            self.obj(v, where, {"stock": (True, self.string), "name": (False, self.string)})
        elif isinstance(v, dict) and ("area" in v or "points" in v):
            self.obj(v, where, {"name": (True, self.string), "area": (True, self.polygon),
                                "points": (True, self.points)})
        else:
            self.fail(where, "expected {stock, name?} or {name, area, points}")

    def points(self, v: object, where: str) -> None:
        if isinstance(v, bool) or not isinstance(v, int) or v < 0:
            self.fail(where, "expected a whole number, 0 or more")

    def map_name(self, v: object, where: str) -> None:
        self.string(v, where)
        if not _MAP_NAME.match(v):
            self.fail(where, "expected a map datapack name (letters, digits and _)")

    def layout(self, v: object, where: str) -> None:
        self.string(v, where)
        if not all(_PATH_PART.match(p) for p in v.split("/")):
            self.fail(where, "expected a Details folder below the extraction, '/'-separated (no '..')")

    def crop(self, v: object, where: str) -> None:
        if v in ("playable", "full"):
            return
        if not isinstance(v, list) or len(v) != 4:
            self.fail(where, "expected 'playable', 'full' or a box [x0, y0, x1, y1] in minimap px")
        for i, c in enumerate(v):
            self.number(c, _at(where, i))
        if not (v[2] > v[0] and v[3] > v[1]):
            self.fail(where, "expected x1 > x0 and y1 > y0")

    def phase_list(self, v: object, where: str) -> None:
        self.items(lambda p, at: self.obj(p, at, {
            "id": (True, self.phase_id),
            "name": (True, self.string),
            "time": (False, self.string),
            "summary": (False, self.text),
            "details": (False, self.items(self.text)),
        }))(v, where)

    def phase_id(self, v: object, where: str) -> None:
        self.string(v, where)
        if not _PHASE_ID.match(v) or v == "all":
            self.fail(where, "expected a phase id: letters, digits, '.', '-' or '_', not 'all'")
        if v in self.phases:
            self.fail(where, f"phase {v!r} is listed twice")
        self.phases.append(v)

    def label(self, v: object, where: str) -> None:
        if v is not None:
            self.obj(v, where, {"text": (True, self.string), "at": (True, self.point)})

    def mark(self, v: object, where: str) -> None:
        if not isinstance(v, dict):
            self.fail(where, f"expected an object, got {_kind(v)}")
        kind = v.get("kind")
        if kind not in MARKS:
            self.fail(_at(where, "kind"), f"expected one of {', '.join(MARKS)}")
        common = {"kind": (True, self.string), "style": (True, self.style),
                  "phases": (False, self.items(self.phase)), "title": (False, self.string)}
        own = {
            "arrow": {"points": (True, self.items(self.point, least=2)), "dashed": (False, self.boolean),
                      "label": (False, self.label)},
            "ring": {"at": (True, self.point), "r": (True, self.positive), "dashed": (False, self.boolean),
                     "label": (False, self.label)},
            "units": {"at": (True, self.point), "count": (True, self.count), "label": (False, self.label)},
            "label": {"at": (True, self.point), "text": (True, self.string),
                      "size": (False, self.one_of("small", "large"))},
            "arc": {"from": (True, self.point), "to": (True, self.point), "bend": (True, self.point),
                    "label": (False, self.label)},
            "burst": {"at": (True, self.point), "label": (False, self.label)},
        }[kind]
        self.obj(v, where, {**common, **own})

    def section(self, v: object, where: str) -> None:
        self.obj(v, where, {
            "heading": (True, self.string),
            "intro": (False, self.text),
            "tables": (False, self.items(self.table)),
            "oob": (False, self.items(self.side)),
        })

    def table(self, v: object, where: str) -> None:
        width = len(v["columns"]) if isinstance(v, dict) and isinstance(v.get("columns"), list) else 0

        def row(r: object, at: str) -> None:   # run after the columns passed (obj checks keys in this order)
            self.items(self.cell)(r, at)
            if len(r) != width:
                self.fail(at, f"expected {width} cells, one per column, got {len(r)}")
        self.obj(v, where, {"columns": (True, self.items(self.string, least=1)), "rows": (True, self.items(row))})

    def cell(self, v: object, where: str) -> None:
        if isinstance(v, dict):
            self.obj(v, where, {"mark": (True, self.one_of(*MARK_CELLS)), "text": (True, self.text)})
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            self.number(v, where)
        else:
            self.text(v, where)

    def side(self, v: object, where: str) -> None:
        self.obj(v, where, {
            "title": (True, self.string),
            "tag": (False, self.string),
            "style": (False, self.style),
            "groups": (True, self.items(self.group)),
        })

    def group(self, v: object, where: str) -> None:
        self.obj(v, where, {
            "name": (True, self.string),
            "when": (False, self.string),
            "note": (False, self.text),
            "units": (True, self.items(self.unit)),
        })

    def unit(self, v: object, where: str) -> None:
        if not isinstance(v, list) or len(v) not in (2, 3):
            self.fail(where, "expected [count, name, key] (the key may be left out)")
        if isinstance(v[0], bool) or not isinstance(v[0], int) or v[0] < 0:
            self.fail(_at(where, 0), "expected a count (a whole number)")
        for i in range(1, len(v)):
            self.string(v[i], _at(where, i))


def validate(spec: object) -> None:
    """Raises SpecError naming the JSON path of the first value that breaks the schema."""
    _Validator().spec(spec)


def unknown_units(spec: Mapping, known: set[str]) -> list[tuple[str, str]]:
    """(JSON path, key) of every order-of-battle unit key (a unit's third item; keys may be joined by '·') whose
    descriptor is not in `known` (modkit.ops.gates.unit_database: every unit the game's unit database exports)."""
    out = []
    for i, s in enumerate(spec.get("sections", [])):
        for j, side in enumerate(s.get("oob", [])):
            for k, g in enumerate(side["groups"]):
                for n, u in enumerate(g["units"]):
                    for key in (p.strip() for p in (u[2] if len(u) > 2 else "").split("·")):
                        if key and f"{UNIT_PREFIX}Descriptor_Unit_{key}" not in known:
                            out.append((f"$.sections[{i}].oob[{j}].groups[{k}].units[{n}][2]", key))
    return out


def load_spec(path: str | os.PathLike) -> dict:
    """The spec at `path`, parsed (not yet validated). A file that is not UTF-8 JSON raises SpecError."""
    with open(path, "rb") as fh:
        raw = fh.read()
    try:
        return json.loads(raw.decode("utf-8"))
    except UnicodeDecodeError:
        raise SpecError("$: not UTF-8 text") from None
    except json.JSONDecodeError as exc:
        raise SpecError(f"$: not JSON ({exc})") from None


# --------------------------------------------------------------------------- the map

@dataclass(frozen=True)
class Picture:
    """8-bit RGB pixels, rows top-down."""
    width: int
    height: int
    rgb: bytes

    def crop(self, box: tuple[int, int, int, int]) -> Picture:
        x0, y0, x1, y1 = box
        stride = self.width * 3
        rows = [self.rgb[y * stride + x0 * 3:y * stride + x1 * 3] for y in range(y0, y1)]
        return Picture(x1 - x0, y1 - y0, b"".join(rows))

    def halved(self) -> Picture:
        """Half the size on both axes, each pixel the mean of a 2x2 block."""
        w, h, stride = self.width // 2, self.height // 2, self.width * 3
        out = bytearray()
        for y in range(h):
            a = self.rgb[2 * y * stride:2 * y * stride + w * 6]
            b = self.rgb[(2 * y + 1) * stride:(2 * y + 1) * stride + w * 6]
            row = bytearray(w * 3)
            for c in range(3):
                row[c::3] = bytes((p + q + r + s + 2) >> 2
                                  for p, q, r, s in zip(a[c::6], a[c + 3::6], b[c::6], b[c + 3::6]))
            out += row
        return Picture(w, h, bytes(out))


@dataclass(frozen=True)
class Zone:
    """A command or deployment zone of a layout, in minimap px."""
    name: str                       # its stock Name (AutoName_5)
    polygon: tuple[Point, ...]      # closed: the first vertex is repeated last
    points: int | None = None       # a command zone's Points
    alliance: int | None = None     # a deployment zone's AllianceNum (0 when the file leaves it out)


@dataclass(frozen=True)
class Layout:
    """What the page draws exact from a Details folder's out/ files, in minimap px."""
    playable: tuple[Point, ...]
    command: tuple[Zone, ...]
    deployment: tuple[Zone, ...]


def _px(p: Sequence[float]) -> Point:
    return (p[0] / WORLD_PER_MINIMAP_PX, p[1] / WORLD_PER_MINIMAP_PX)


class StockSource:
    """Reads a map's layout and pictures from the stock extraction (modkit.core.paths). A missing file fails naming
    the setup commands that fetch it (the warno-setup skill)."""

    def layout(self, rel: str) -> Layout:
        def zones(name: str) -> list:
            return read_zone_areas(read_file(extracted(f"{rel}/out/{name}.ndfbin")))

        ring = read_playable_polygon(read_file(extracted(f"{rel}/out/PlayableZone.ndfbin")))
        command = tuple(Zone(str(zone_prop(a, "Name")), tuple(_px(p) for p in a[0]), points=zone_prop(a, "Points"))
                        for a in zones("CommandZone"))
        deployment = tuple(Zone(str(zone_prop(a, "Name")), tuple(_px(p) for p in a[0]),
                                alliance=zone_prop(a, "AllianceNum") or 0) for a in zones("DeploymentZone"))
        return Layout(tuple(_px(p) for p in ring), command, deployment)

    def picture(self, map_name: str, kind: str) -> Picture:
        """The map's `kind` picture ('Minimap' or 'Preview'), alpha dropped."""
        path = extracted(picture_path(map_name, kind))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"missing stock file {paths.rel_source(path)}: the extraction lacks it; "
                                    f"{SETUP_FIX}")
        hdr, rgba = tgv.read_tgv(path)
        return Picture(hdr.width, hdr.height, tgv.drop_alpha(rgba))


def crop_box(crop: object, layout: Layout, width: int, height: int) -> tuple[int, int, int, int]:
    """The crop in whole minimap px, inside the minimap (`width` x `height`): the playable zone's bounding box
    ('playable'), the whole minimap ('full') or a box [x0, y0, x1, y1], each rounded to the nearest pixel."""
    if crop == "full":
        return 0, 0, width, height
    if crop == "playable":
        xs, ys = [p[0] for p in layout.playable], [p[1] for p in layout.playable]
        box = (min(xs), min(ys), max(xs), max(ys))
    else:
        box = tuple(crop)
    x0, y0, x1, y1 = (round(c) for c in box)
    x0, x1 = max(0, min(x0, width)), max(0, min(x1, width))
    y0, y1 = max(0, min(y0, height)), max(0, min(y1, height))
    if x1 <= x0 or y1 <= y0:
        raise SpecError(f"$.map.crop: the box {list(box)} lies outside the {width}x{height} minimap")
    return x0, y0, x1, y1


# --------------------------------------------------------------------------- the page

def _n(v: float) -> str:
    """A coordinate: whole when it is, else at most two decimals."""
    return f"{round(float(v), 2):.2f}".rstrip("0").rstrip(".")


def _pts(poly: Sequence[Sequence[float]]) -> str:
    return " ".join(f"{_n(x)},{_n(y)}" for x, y in poly)


def _tint(colour: str, k: float = 0.35) -> str:
    """`colour` mixed k of the way to white: text on the dark map."""
    return "#" + "".join(f"{round(c + (255 - c) * k):02x}" for c in (int(colour[i:i + 2], 16) for i in (1, 3, 5)))


def _phase_attrs(classes: str, phases: Sequence[str], start: str | None) -> str:
    """class and data-ph of a mark: data-ph lists its phases (none: every phase), 'off' hides it at the start."""
    if not phases:
        return f'class="{classes}"'
    off = " off" if start is not None and start not in phases else ""
    return f'class="{classes}{off}" data-ph="{esc(",".join(phases))}"'


def _label(label: Mapping | None) -> str:
    if not label:
        return ""
    x, y = label["at"]
    return f'<text class="sm" x="{_n(x)}" y="{_n(y)}">{esc(label["text"])}</text>'


def map_scale(spec: Mapping, box: tuple[int, int, int, int]) -> float:
    """How big the map's text, strokes and drawn shapes are: ``map.mark_scale``, else the crop's size against the
    432 x 622 px crop the look was tuned on. Rounded to 3 decimals."""
    given = spec["map"].get("mark_scale")
    return round(float(given if given is not None else max((box[2] - box[0]) / 432, (box[3] - box[1]) / 622)), 3)


def mark_svg(mark: Mapping, start: str | None, s: float = 1.0) -> str:
    """One mark as an SVG group in its style, with its label and its hover title. `s` (map_scale) sizes its drawn
    shapes."""
    kind, style = mark["kind"], mark["style"]
    dashed = " dashed" if mark.get("dashed") else ""
    if kind == "arrow":
        d = " L".join(f"{_n(x)},{_n(y)}" for x, y in mark["points"])
        body = f'<path class="arrow{dashed}" d="M{d}" marker-end="url(#ah-{style})"/>'
    elif kind == "ring":
        (x, y), r = mark["at"], mark["r"]
        body = f'<circle class="ring{dashed}" cx="{_n(x)}" cy="{_n(y)}" r="{_n(r)}"/>'
    elif kind == "units":
        (x, y), n = mark["at"], mark["count"]
        cols = min(n, 4)
        rows = -(-n // cols)
        x0, y0 = x - (cols * 14 - 4) * s / 2, y - (rows * 12 - 4) * s / 2
        body = "".join(f'<rect class="unit" x="{_n(x0 + i % cols * 14 * s)}" y="{_n(y0 + i // cols * 12 * s)}" '
                       f'width="{_n(10 * s)}" height="{_n(8 * s)}"/>' for i in range(n))
    elif kind == "label":
        x, y = mark["at"]
        size = "lbl" if mark.get("size") == "large" else "sm"
        body = f'<text class="{size}" x="{_n(x)}" y="{_n(y)}">{esc(mark["text"])}</text>'
    elif kind == "arc":
        (fx, fy), (bx, by), (tx, ty) = mark["from"], mark["bend"], mark["to"]
        body = f'<path class="arc" d="M{_n(fx)},{_n(fy)} Q{_n(bx)},{_n(by)} {_n(tx)},{_n(ty)}"/>'
    else:  # burst: a cloud on its stem, the stem's foot at `at`
        x, y = mark["at"]
        body = (f'<rect class="burst" x="{_n(x - 5 * s)}" y="{_n(y - 22 * s)}" width="{_n(10 * s)}" '
                f'height="{_n(22 * s)}"/><circle class="burst" cx="{_n(x)}" cy="{_n(y - 38 * s)}" r="{_n(20 * s)}"/>')
    body += _label(mark.get("label"))
    if mark.get("title"):
        body += f"<title>{esc(mark['title'])}</title>"
    return f'<g {_phase_attrs(f"mark k-{kind} st-{style}", mark.get("phases") or [], start)}>{body}</g>'


def _closed(area: Sequence[Sequence[float]]) -> tuple[Point, ...]:
    poly = tuple((float(x), float(y)) for x, y in area)
    return poly if poly[0] == poly[-1] else poly + (poly[0],)


def command_zones(spec: Mapping, layout: Layout) -> list[tuple[str, Zone, str | None]]:
    """The command zones to draw as (display name, zone, stock name or None for an op's own zone). With
    ``map.command_zones``, exactly those in order; else every zone of the layout, named by ``zone_names``."""
    m = spec["map"]
    if "command_zones" not in m:
        names = m.get("zone_names", {})
        return [(names.get(z.name, z.name), z, z.name) for z in layout.command]
    stock = {z.name: z for z in layout.command}
    out = []
    for i, item in enumerate(m["command_zones"]):
        if "stock" in item:
            if item["stock"] not in stock:
                raise SpecError(f"$.map.command_zones[{i}].stock: the layout {m['layout']} has no command zone "
                                f"{item['stock']!r} (it has: {', '.join(stock) or 'none'})")
            out.append((item.get("name", item["stock"]), stock[item["stock"]], item["stock"]))
        else:
            out.append((item["name"], Zone(item["name"], _closed(item["area"]), points=item["points"]), None))
    return out


def zones_svg(spec: Mapping, layout: Layout, s: float = 1.0) -> str:
    """The layout's deployment zones (dashed, in their alliance's style) and command zones (outline, name, points).
    A deployment's ``area`` replaces the layout's zone of its alliance (or is drawn alone when there is none); the
    command zones are those of ``command_zones`` when the spec has it. `s` (map_scale) offsets the command zone
    labels."""
    deployments = spec["map"].get("deployments", {})
    out, drawn = [], set()

    def deployment(poly: Sequence[Point], style: str, label: str, title: str) -> None:
        cx, cy = polygon_centroid(list(poly))
        out.append(f'<g class="dep st-{style}"><polygon points="{_pts(poly)}"/>'
                   f'<text class="deplbl" x="{_n(cx)}" y="{_n(cy + 4)}">{esc(label)}</text>'
                   f'<title>{esc(title)}</title></g>')

    for z in layout.deployment:
        d = deployments.get(str(z.alliance))
        if d and "area" in d:
            if z.alliance not in drawn:
                drawn.add(z.alliance)
                deployment(_closed(d["area"]), d["style"], d["label"],
                           f"Deployment zone, alliance {z.alliance}: {d['label']}")
            continue
        style, label = (d["style"], d["label"]) if d else ("none", f"Deployment · alliance {z.alliance}")
        deployment(z.polygon, style, label, f"Deployment zone {z.name}, alliance {z.alliance}: {label}")
    for alliance, d in sorted(deployments.items(), key=lambda kv: int(kv[0])):
        if "area" in d and int(alliance) not in drawn:
            deployment(_closed(d["area"]), d["style"], d["label"],
                       f"Deployment zone, alliance {int(alliance)}: {d['label']}")
    for name, z, stock in command_zones(spec, layout):   # the name sits inside the zone's top, clear of the marks
        cx, top = polygon_centroid(list(z.polygon))[0], min(p[1] for p in z.polygon)
        title = f"Command zone {stock}" if stock else f"Command zone {name}"
        title += (f" ({name})" if stock and name != stock else "") + f": {z.points} points"
        out.append(f'<g class="cz"><polygon points="{_pts(z.polygon)}"/>'
                   f'<text x="{_n(cx)}" y="{_n(top + 14 * s)}">{esc(name)} · {z.points}</text>'
                   f'<title>{esc(title)}</title></g>')
    return "\n".join(out)


def map_svg(spec: Mapping, layout: Layout, box: tuple[int, int, int, int]) -> str:
    """The map: both pictures at the crop box (viewBox), the zones, then the marks."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    marks = spec.get("marks", [])
    start = start_phase(spec)
    arrows = list(dict.fromkeys(mk["style"] for mk in marks if mk["kind"] == "arrow"))
    defs = "".join(f'<marker id="ah-{s}" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="4" markerHeight="4" '
                   f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{spec["styles"][s]}"/></marker>' for s in arrows)
    picture = spec["map"].get("default_picture", "minimap")
    k = map_scale(spec, box)
    at = f'x="{x0}" y="{y0}" width="{w}" height="{h}"'
    return "\n".join([
        f'<svg id="map" viewBox="{x0} {y0} {w} {h}" role="img" data-pic="{picture}" style="--s: {k:g}" '
        f'aria-label="{esc(spec["title"])}: {esc(spec["map"]["name"])}, the zones of the stock layout and the plan '
        f'for the selected phase">',
        f"<defs>{defs}</defs>",
        f'<rect class="ground" {at}/>',
        f'<image id="base-mini" class="base" href="{MINIMAP}" {at} preserveAspectRatio="none"/>',
        f'<image id="base-sat" class="base" href="{SATELLITE}" {at} preserveAspectRatio="none"/>',
        f'<rect class="dim" {at}/>',
        f'<g class="zones">\n{zones_svg(spec, layout, k)}\n</g>',
        '<g class="marks">\n' + "\n".join(mark_svg(mk, start, k) for mk in marks) + "\n</g>",
        "</svg>",
    ])


def start_phase(spec: Mapping) -> str | None:
    phases = spec.get("phases", [])
    return spec.get("start_phase", phases[0]["id"] if phases else None)


def _phases_html(spec: Mapping) -> str:
    start = start_phase(spec)
    out = ['<div class="phases" id="phases">',
           '<button type="button" class="allbtn" id="v-all" aria-pressed="false">Show every phase</button>']
    for p in spec.get("phases", []):
        time = f'<span class="ph-time">{esc(p["time"])}</span>' if p.get("time") else ""
        summary = f'<span class="ph-sum">{text_html(p["summary"])}</span>' if p.get("summary") else ""
        details = "".join(f'<span class="ph-li">{text_html(d)}</span>' for d in p.get("details", []))
        details = f'<span class="ph-det">{details}</span>' if details else ""
        out.append(f'<button type="button" class="phase" data-p="{esc(p["id"])}" '
                   f'aria-current="{str(p["id"] == start).lower()}">'
                   f'<span class="ph-head"><span class="ph-name">{esc(p["id"])} · {esc(p["name"])}</span>{time}</span>'
                   f'{summary}{details}</button>')
    out.append("</div>")
    return "\n".join(out)


def _legend_html(spec: Mapping) -> str:
    items = [f'<span class="st-{esc(d["style"])}"><i class="sw d"></i>{esc(d["label"])}</span>'
             for _, d in sorted(spec["map"].get("deployments", {}).items(), key=lambda kv: int(kv[0]))]
    items.append('<span><i class="sw cz"></i>command zone (name · points)</span>')
    return '<div class="legend" aria-label="Legend">' + "".join(items) + "</div>"


def _cell(c: object) -> str:
    if isinstance(c, dict):
        return f'<td><span class="mk {c["mark"]}">{text_html(c["text"])}</span></td>'
    if isinstance(c, (int, float)):
        return f'<td class="n">{_n(c) if isinstance(c, float) else c}</td>'
    return f"<td>{text_html(c)}</td>"


def _table_html(t: Mapping) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in t["columns"])
    rows = "".join("<tr>" + "".join(_cell(c) for c in r) + "</tr>" for r in t["rows"])
    return (f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def _oob_html(sides: Sequence[Mapping]) -> str:
    out = ['<div class="oob">']
    for s in sides:
        tag = f' <span class="tag">{esc(s["tag"])}</span>' if s.get("tag") else ""
        cls = f"side st-{s['style']}" if s.get("style") else "side"
        out.append(f'<div class="{cls}"><h3>{esc(s["title"])}{tag}</h3>')
        for g in s["groups"]:
            when = f'<span>{esc(g["when"])}</span>' if g.get("when") else ""
            note = f'<div class="gn">{text_html(g["note"])}</div>' if g.get("note") else ""
            units = "".join(
                f'<li><span class="q">{u[0]}</span><span class="nm">{esc(u[1])}'
                + (f' <span class="key">{esc(u[2])}</span>' if len(u) > 2 and u[2] else "") + "</span></li>"
                for u in g["units"])
            out.append(f'<div class="grp"><div class="gh"><b>{esc(g["name"])}</b>{when}</div>{note}'
                       f'<ul class="unitlist">{units}</ul></div>')
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def _sections_html(spec: Mapping) -> str:
    out = []
    for i, s in enumerate(spec.get("sections", []), 1):
        part = [f'<section class="block" aria-labelledby="s{i}-h">', f'<h2 id="s{i}-h">{esc(s["heading"])}</h2>']
        if s.get("intro"):
            part.append(f"<p>{text_html(s['intro'])}</p>")
        tables = [_table_html(t) for t in s.get("tables", [])]
        if len(tables) > 1:
            part.append('<div class="cols2">' + "".join(tables) + "</div>")
        else:
            part += tables
        if s.get("oob"):
            part.append(_oob_html(s["oob"]))
        part.append("</section>")
        out.append("\n".join(part))
    return "\n".join(out)


def _styles_css(styles: Mapping[str, str]) -> str:
    rules = [f".st-{n} {{ --c: {c}; --t: {_tint(c)}; }} .tx-{n} {{ color: {_tint(c)}; }}" for n, c in styles.items()]
    accent = next(iter(styles.values()), "#e7eae4")
    return f":root {{ --accent: {accent}; }}\n" + "\n".join(rules)


def render_page(spec: Mapping, layout: Layout, box: tuple[int, int, int, int]) -> str:
    """The page for a validated spec: one HTML file referring to the two pictures beside it."""
    phases = spec.get("phases", [])
    picture = spec["map"].get("default_picture", "minimap")
    chips = "".join(f'<span class="chip">{esc(k)} <b>{text_html(v)}</b></span>' for k, v in spec.get("chips", []))
    header = [f'<div class="eyebrow">{esc(spec["eyebrow"])}</div>' if spec.get("eyebrow") else "",
              f"<h1>{esc(spec['title'])}</h1>",
              f'<div class="status">{chips}</div>' if chips else "",
              f'<p class="lede">{text_html(spec["lede"])}</p>' if spec.get("lede") else ""]
    switch = "".join(f'<button type="button" id="{bid}" data-pic="{p}" aria-pressed="{str(p == picture).lower()}">'
                     f"{p.capitalize()}</button>" for bid, p in (("b-mini", "minimap"), ("b-sat", "satellite")))
    footer = "".join(f"<div>{text_html(line)}</div>" for line in spec.get("footer", []))
    body = "\n".join([
        '<div class="wrap">',
        "<header>" + "".join(header) + "</header>",
        f'<div class="board{"" if phases else " solo"}">',
        '<div class="mapcol">',
        '<div class="mapbox">', map_svg(spec, layout, box), "</div>",
        '<div class="controls"><span class="ctl-label">Picture</span>'
        f'<div class="seg" role="group" aria-label="Base picture">{switch}</div></div>',
        _legend_html(spec),
        "</div>",
        _phases_html(spec) if phases else "",
        "</div>",
        _sections_html(spec),
        f"<footer>{footer}</footer>" if footer else "",
        "</div>",
    ])
    script = _SCRIPT.replace("START_PHASE", json.dumps(start_phase(spec) or "all"))
    return "\n".join([_HEAD.replace("PAGE_TITLE", esc(spec["title"])), "<style>", _CSS, _styles_css(spec["styles"]),
                      "</style>", body, "<script>", script, "</script>", ""])


_HEAD = """<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PAGE_TITLE</title>
<meta name="claude:viewport-fit-sides" content="cover">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="FONTS">""".replace(
    "FONTS", "https://fonts.googleapis.com/css2?family=Barlow+Condensed:wght@500;600;700"
             "&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap")

# The look of the hand-made Twin Strike page: an operations-room planning overlay, one deliberate dark theme (a lit
# map table). The map on the left, the phase order on the right; it stacks at phone width.
_CSS = """:root {
  color-scheme: dark;
  --bg: #12171a; --panel: #1a2125; --ground: #222b2f; --line: #2f3a3f;
  --ink: #e7eae4; --muted: #98a5a9; --zone: #d6c35a; --halo: #0b0f11;
  --f-display: "Barlow Condensed", "Arial Narrow", "Roboto Condensed", sans-serif;
  --f-body: "IBM Plex Sans", "Segoe UI", system-ui, sans-serif;
  --f-mono: "IBM Plex Mono", ui-monospace, "Cascadia Mono", Consolas, monospace;
}
* { box-sizing: border-box; }
html, body { background: var(--bg); }
body { color: var(--ink); font: 15px/1.5 var(--f-body); margin: 0; }
.wrap { max-width: 1240px; margin: 0 auto; padding-block: 24px 48px;
  padding-left: max(16px, env(safe-area-inset-left, 0px)); padding-right: max(16px, env(safe-area-inset-right, 0px));
  }
h1, h2, h3 { font-family: var(--f-display); font-weight: 600; letter-spacing: .02em; text-wrap: balance; margin: 0; }
h1 { font-size: clamp(30px, 5vw, 46px); line-height: 1.05; text-transform: uppercase; }
h2 { font-size: 24px; text-transform: uppercase; margin-bottom: 10px; }
h3 { font-size: 18px; margin: 18px 0 6px; color: var(--t, var(--ink)); }
p { margin: 0 0 10px; max-width: 68ch; }
.eyebrow { font: 500 12px/1 var(--f-mono); letter-spacing: .12em; text-transform: uppercase; color: var(--muted); }
header { display: grid; gap: 10px; margin-bottom: 22px; }
.status { display: flex; flex-wrap: wrap; gap: 8px; }
.chip { font: 500 12px/1.3 var(--f-mono); padding: 6px 9px; border: 1px solid var(--line); border-radius: 3px;
  color: var(--muted); }
.chip b { color: var(--ink); font-weight: 500; }
.lede { font-size: 16px; color: var(--ink); }
.tx { font-weight: 600; }

.board { display: grid; grid-template-columns: minmax(0, 1.15fr) minmax(0, 1fr); gap: 20px; align-items: start; }
.board.solo { grid-template-columns: minmax(0, 1fr); }
@media (max-width: 860px) { .board { grid-template-columns: minmax(0, 1fr); } }
.mapcol { display: grid; gap: 10px; min-width: 0; }
.mapbox { background: var(--ground); border: 1px solid var(--line); border-radius: 4px; overflow: hidden; }
svg#map { display: block; width: 100%; height: auto; max-width: 100%; max-height: 88vh; margin: 0 auto; }
.controls { display: flex; flex-wrap: wrap; gap: 10px; align-items: center; font-size: 13px; color: var(--muted); }
.ctl-label { font: 500 12px var(--f-mono); color: var(--muted); text-transform: uppercase; letter-spacing: .06em; }
.seg { display: inline-flex; flex-wrap: wrap; border: 1px solid var(--line); border-radius: 4px; overflow: hidden; }
.seg button { font: 600 15px var(--f-display); letter-spacing: .04em; text-transform: uppercase;
  background: transparent;
  color: var(--muted); border: 0; border-right: 1px solid var(--line); padding: 6px 12px; cursor: pointer; }
.seg button:last-child { border-right: 0; }
.seg button[aria-pressed="true"] { background: var(--ink); color: var(--bg); }
.seg button:focus-visible { outline: 2px solid var(--ink); outline-offset: -2px; }

#map .ground { fill: var(--ground); }
#map .dim { fill: rgba(11, 15, 17, .22); pointer-events: none; }
#map[data-pic="minimap"] #base-sat, #map[data-pic="satellite"] #base-mini { display: none; }
#map .cz polygon { fill: rgba(214, 195, 90, .08); stroke: var(--zone); stroke-width: calc(1.4 * var(--s)); }
#map .cz text { font: 500 calc(11px * var(--s)) var(--f-mono); fill: var(--zone); text-anchor: middle;
  paint-order: stroke;
  stroke: var(--halo); stroke-width: calc(3px * var(--s)); }
#map .st-none { --c: var(--muted); --t: var(--ink); }
#map .dep polygon { fill: var(--c); fill-opacity: .06; stroke: var(--c); stroke-width: calc(2 * var(--s));
  stroke-dasharray: calc(7 * var(--s)) calc(5 * var(--s)); }
#map .deplbl { font: 600 calc(13px * var(--s)) var(--f-display); letter-spacing: .06em; text-transform: uppercase;
  text-anchor: middle;
  fill: var(--t); paint-order: stroke; stroke: var(--halo); stroke-width: calc(4px * var(--s)); }
#map .lbl { font: 600 calc(14px * var(--s)) var(--f-display); letter-spacing: .04em; fill: var(--t); paint-order: stroke;
  stroke: var(--halo); stroke-width: calc(4px * var(--s)); }
#map .sm { font: 500 calc(11.5px * var(--s)) var(--f-mono); fill: var(--t); paint-order: stroke; stroke: var(--halo);
  stroke-width: calc(3.5px * var(--s)); }
#map .arrow { fill: none; stroke: var(--c); stroke-width: calc(6 * var(--s)); stroke-linecap: round;
  stroke-linejoin: round; }
#map .arrow.dashed { stroke-dasharray: calc(10 * var(--s)) calc(8 * var(--s)); stroke-width: calc(4 * var(--s)); }
#map .ring { fill: var(--c); fill-opacity: .14; stroke: var(--c); stroke-width: calc(2.5 * var(--s)); }
#map .ring.dashed { stroke-dasharray: calc(6 * var(--s)) calc(4 * var(--s)); }
#map .unit { fill: var(--c); stroke: var(--halo); stroke-width: calc(1.2 * var(--s)); }
#map .arc { fill: none; stroke: var(--c); stroke-width: calc(2.5 * var(--s));
  stroke-dasharray: calc(3 * var(--s)) calc(6 * var(--s)); stroke-linecap: round; }
#map .burst { fill: var(--c); fill-opacity: .55; stroke: var(--t); stroke-width: calc(2 * var(--s)); }
#map .mark { transition: opacity .25s ease; }
#map .mark.off { opacity: 0; pointer-events: none; }
@media (prefers-reduced-motion: reduce) { #map .mark { transition: none; } }

.phases { display: grid; gap: 8px; min-width: 0; }
.phase { text-align: left; width: 100%; font: inherit; color: var(--muted); background: var(--panel);
  border: 1px solid var(--line);
  border-radius: 4px; padding: 12px 14px; cursor: pointer; display: grid; gap: 4px; }
.phase:hover { border-color: #46545a; }
.phase:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }
.phase[aria-current="true"] { color: var(--ink); border-color: var(--ink); box-shadow: inset 3px 0 0 var(--accent); }
.phase .ph-head { display: flex; justify-content: space-between; gap: 10px; align-items: baseline; }
.phase .ph-name { font: 600 19px/1.1 var(--f-display); letter-spacing: .03em; text-transform: uppercase;
  color: var(--ink); }
.phase .ph-time { font: 500 12px var(--f-mono); color: var(--muted); white-space: nowrap;
  font-variant-numeric: tabular-nums; }
.phase .ph-sum { display: block; font-size: 14px; }
.phase .ph-det { display: none; margin-top: 4px; font-size: 13.5px; }
.phase[aria-current="true"] .ph-det { display: grid; gap: 2px; }
.phase .ph-li { display: block; padding-left: 16px; position: relative; }
.phase .ph-li::before { content: "•"; position: absolute; left: 3px; }
.allbtn { justify-self: start; font: 500 12px var(--f-mono); color: var(--ink); background: transparent;
  border: 1px solid var(--line); border-radius: 3px; padding: 7px 10px; cursor: pointer; }
.allbtn[aria-pressed="true"] { border-color: var(--ink); }
.allbtn:focus-visible { outline: 2px solid var(--ink); outline-offset: 2px; }

section.block { margin-top: 34px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px 18px; font-size: 13px; color: var(--muted); }
.legend span { display: inline-flex; align-items: center; gap: 7px; }
.sw { width: 22px; height: 0; border-top: 2px solid var(--c, var(--muted)); display: inline-block; }
.sw.d { border-top-style: dashed; }
.sw.cz { border-color: var(--zone); }

.tablewrap { overflow-x: auto; border: 1px solid var(--line); border-radius: 4px; background: var(--panel);
  margin-bottom: 12px; }
table { border-collapse: collapse; width: 100%; font-size: 14px; }
th, td { text-align: left; padding: 8px 12px; border-bottom: 1px solid var(--line); vertical-align: top; }
th { font: 600 13px var(--f-display); letter-spacing: .06em; text-transform: uppercase; color: var(--muted);
  background: #161c20; }
tr:last-child td { border-bottom: 0; }
td.n { font-variant-numeric: tabular-nums; text-align: right; white-space: nowrap; }
code, .key { font: 12px var(--f-mono); color: var(--muted); }
.oob { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 18px; }
@media (max-width: 860px) { .oob { grid-template-columns: minmax(0, 1fr); } }
.side { min-width: 0; }
.side h3 .tag { font: 500 12px var(--f-mono); color: var(--muted); letter-spacing: 0; text-transform: none;
  margin-left: 6px; }
.unitlist { list-style: none; margin: 0; padding: 0; display: grid; }
.unitlist li { display: grid; grid-template-columns: 2.6em minmax(0, 1fr); gap: 8px; padding: 5px 12px;
  border-bottom: 1px solid var(--line); }
.unitlist li:last-child { border-bottom: 0; }
.unitlist .q { font: 500 14px var(--f-mono); text-align: right; font-variant-numeric: tabular-nums; color: var(--ink);
  }
.unitlist .nm { min-width: 0; }
.unitlist .key { display: block; overflow-wrap: anywhere; }
.grp { background: var(--panel); border: 1px solid var(--line); border-radius: 4px; margin-bottom: 12px;
  overflow: hidden; }
.grp > .gh { display: flex; flex-wrap: wrap; justify-content: space-between; gap: 4px 10px; padding: 9px 12px;
  background: #161c20; border-bottom: 1px solid var(--line); }
.grp > .gh b { font: 600 15px var(--f-display); letter-spacing: .04em; text-transform: uppercase; }
.grp > .gh span { font: 500 12px var(--f-mono); color: var(--muted); }
.grp > .gn { padding: 8px 12px; font-size: 13px; color: var(--muted); border-bottom: 1px solid var(--line); }
.cols2 { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 0 18px; }
@media (max-width: 860px) { .cols2 { grid-template-columns: minmax(0, 1fr); } }
.mk { font: 500 12px var(--f-mono); padding: 1px 6px; border-radius: 3px; border: 1px solid var(--line);
  white-space: nowrap; }
.mk.ok { color: #9fd49a; border-color: #3f5b3d; }
.mk.half { color: #f3c06e; border-color: #5e4c2a; }
.mk.open { color: #d3b4f8; border-color: #4e3d66; }
footer { margin-top: 40px; font-size: 13px; color: var(--muted); display: grid; gap: 6px; }"""

# The phase stepper (click a phase, or step with the arrow keys; "Show every phase") and the picture switch.
_SCRIPT = """(function () {
  var map = document.getElementById('map');
  var layers = map.querySelectorAll('[data-ph]');
  var buttons = Array.prototype.slice.call(document.querySelectorAll('.phase'));
  var allBtn = document.getElementById('v-all');
  var picBtns = Array.prototype.slice.call(document.querySelectorAll('button[data-pic]'));
  function show(p) {
    layers.forEach(function (el) {
      var on = p === 'all' || el.getAttribute('data-ph').split(',').indexOf(p) !== -1;
      el.classList.toggle('off', !on);
    });
    buttons.forEach(function (b) { b.setAttribute('aria-current', String(b.getAttribute('data-p') === p)); });
    if (allBtn) allBtn.setAttribute('aria-pressed', String(p === 'all'));
  }
  function step(d, focus) {
    if (!buttons.length) return;
    var cur = buttons.findIndex(function (b) { return b.getAttribute('aria-current') === 'true'; });
    var next = cur < 0 ? (d > 0 ? 0 : buttons.length - 1) : Math.max(0, Math.min(buttons.length - 1, cur + d));
    if (focus) buttons[next].focus();
    show(buttons[next].getAttribute('data-p'));
  }
  buttons.forEach(function (b) { b.addEventListener('click', function () { show(b.getAttribute('data-p')); }); });
  if (allBtn) allBtn.addEventListener('click', function () { show('all'); });
  document.addEventListener('keydown', function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var t = e.target;
    var inList = !!(t && t.closest && t.closest('#phases'));
    if (!inList && t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) return;
    var d = 0;
    if (e.key === 'ArrowRight' || (inList && e.key === 'ArrowDown')) d = 1;
    else if (e.key === 'ArrowLeft' || (inList && e.key === 'ArrowUp')) d = -1;
    if (!d) return;
    step(d, inList);
    e.preventDefault();
  });
  function setPic(which) {
    map.setAttribute('data-pic', which);
    picBtns.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-pic') === which)); });
  }
  picBtns.forEach(function (b) { b.addEventListener('click', function () { setPic(b.getAttribute('data-pic')); }); });
  show(START_PHASE);
})();"""


# --------------------------------------------------------------------------- the files

def _scale(minimap: Picture, preview: Picture) -> int:
    """Preview px per minimap px: a whole number on both axes (2 on every stock map)."""
    k = preview.width // minimap.width if minimap.width else 0
    if k < 1 or (preview.width, preview.height) != (k * minimap.width, k * minimap.height):
        raise ValueError(f"the Preview ({preview.width}x{preview.height}) is not a whole multiple of the Minimap "
                         f"({minimap.width}x{minimap.height})")
    return k


def _size(n: int) -> str:
    return f"{n / 1024 / 1024:.2f} MB" if n >= 1024 * 1024 else f"{n / 1024:.1f} KB"


def generate(spec: Mapping, out_dir: str | os.PathLike, source: StockSource | None = None, *,
             units: set[str] | None = None) -> list[str]:
    """Validates `spec`, reads its map from `source` (the stock extraction by default) and writes the page and its two
    pictures into `out_dir`. With `units` (unit_database()), every order-of-battle unit key must name one of them.
    Returns the lines to print: one per file, then the Artifact publish line. Nothing is written unless every check
    passes."""
    validate(spec)
    checked = []
    if units is not None:
        bad = unknown_units(spec, units)
        if bad:
            raise SpecError(f"{bad[0][0]}: not in the game's unit database: {', '.join(k for _, k in bad)}")
        checked = ["unit keys: every one is in the game's unit database"]
    source = source or StockSource()
    m = spec["map"]
    layout = source.layout(m["layout"])
    command_zones(spec, layout)     # a stock name the layout lacks fails before anything is written
    minimap, preview = source.picture(m["name"], "Minimap"), source.picture(m["name"], "Preview")
    k = _scale(minimap, preview)
    box = crop_box(m.get("crop", "playable"), layout, minimap.width, minimap.height)
    page = render_page(spec, layout, box).encode("utf-8")
    if len(page) > MAX_PAGE:
        raise ValueError(f"{PAGE} would be {_size(len(page))}, over the {_size(MAX_PAGE)} a page may be: "
                         f"shorten the spec's text")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mini = minimap.crop(box)
    tgv.write_png(str(out / MINIMAP), mini.width, mini.height, mini.rgb, channels=3)
    sat = preview.crop(tuple(c * k for c in box))
    tgv.write_png(str(out / SATELLITE), sat.width, sat.height, sat.rgb, channels=3)
    halved = ""
    if (out / SATELLITE).stat().st_size > MAX_PICTURE:
        halved = f", halved: over {_size(MAX_PICTURE)} at the Preview's {sat.width}x{sat.height}"
        sat = sat.halved()
        tgv.write_png(str(out / SATELLITE), sat.width, sat.height, sat.rgb, channels=3)
    (out / PAGE).write_bytes(page)
    where = {name: (out / name).absolute().as_posix() for name in (PAGE, MINIMAP, SATELLITE)}
    marks, phases = len(spec.get("marks", [])), len(spec.get("phases", []))
    return [
        *checked,
        f"{where[PAGE]}: {_size(len(page))}; {len(layout.command)} command zones, {len(layout.deployment)} "
        f"deployment zones, {marks} marks, {phases} phases; viewBox {box[0]} {box[1]} {box[2] - box[0]} "
        f"{box[3] - box[1]}",
        f"{where[MINIMAP]}: {mini.width}x{mini.height}, {_size((out / MINIMAP).stat().st_size)}",
        f"{where[SATELLITE]}: {sat.width}x{sat.height}, {_size((out / SATELLITE).stat().st_size)}{halved}",
        f"Artifact publish: file_path={where[PAGE]} "
        f"files={json.dumps({MINIMAP: where[MINIMAP], SATELLITE: where[SATELLITE]})}",
    ]


def default_out(spec_path: str | os.PathLike) -> Path:
    """storyboard/<name> in the build folder: <name> is the spec's stem, or for a spec named storyboard.json the op's
    folder (the one holding its docs/ folder, else the spec's own folder)."""
    p = Path(os.path.abspath(spec_path))
    name = p.stem
    if name == SPEC_NAME:
        name = (p.parent.parent if p.parent.name == "docs" else p.parent).name
    return paths.build_root() / "storyboard" / name


def main(argv: Sequence[str] | None = None) -> int:
    _utf8_streams()
    ap = argparse.ArgumentParser(prog="python -m modkit.ops.storyboard", description=__doc__.split("\n")[0])
    ap.add_argument("spec", help="the storyboard spec (JSON)")
    ap.add_argument("--out", help="output folder (default: storyboard/<name> in the build folder)")
    ap.add_argument("--check-units", action="store_true",
                    help="also check every order-of-battle unit key against the game's unit database (reads the "
                         "game install)")
    args = ap.parse_args(argv)
    try:
        spec = load_spec(args.spec)
        out = Path(args.out) if args.out else default_out(args.spec)
        lines = generate(spec, out, units=unit_database() if args.check_units else None)
    except SpecError as exc:
        print(f"FAILED: {args.spec}: {exc}", file=sys.stderr)
        return 1
    except FAILURES as exc:
        print(f"FAILED: {exc}", file=sys.stderr)
        return 1
    for line in lines:
        print(line)
    return 0


if __name__ == "__main__":
    sys.exit(main())
