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

The spec (``version`` 1) is read into ``Spec`` (``Spec.read``), its pydantic model, before anything else is read:
an unknown key or a bad value fails with its JSON path (``$.marks[2].kind``). Every coordinate is in minimap pixels of the full map (``WORLD_PER_MINIMAP_PX`` world
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
import functools
import html
import json
import math
import os
import re
import sys
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import (AfterValidator, BaseModel, BeforeValidator, ConfigDict, Discriminator, Field, PlainValidator,
                      StrictBool, StrictStr, Tag, ValidationError, ValidationInfo, field_validator, model_validator)
from pydantic_core import ErrorDetails, PydanticCustomError

from modkit.core import paths, tgv
from modkit.core.models import Box, Point
from modkit.ops.build import FAILURES, _utf8_streams
from modkit.ops.files import SETUP_FIX, read_file
from modkit.ops.gates import UNIT_PREFIX, unit_database
from modkit.ops.maps import WORLD_PER_MINIMAP_PX, picture_path
from modkit.ops.models import Zone
from modkit.ops.profile import extracted
from modkit.ops.zones import polygon_centroid, read_playable_polygon, read_zone_areas

VERSION = 1
PAGE, MINIMAP, SATELLITE = "index.html", "minimap.png", "satellite.png"
MAX_PAGE = 1024 * 1024              # the page itself; the pictures are published beside it
MAX_PICTURE = 3 * 1024 * 1024       # a satellite crop over this is halved
SPEC_NAME = "storyboard"            # an op keeps its spec as examples/<op>/docs/storyboard.json
MARKS = ("arrow", "ring", "units", "label", "arc", "burst")


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


# --------------------------------------------------------------------------- the spec

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


@dataclass
class _Refs:
    """What a value may name, filled in as the spec is read in its fields' order: the styles, then the phases."""
    styles: set[str] = field(default_factory=set)
    phases: list[str] = field(default_factory=list)


def _invalid(why: str, *loc: str | int) -> PydanticCustomError:
    """A value that breaks the schema, in the words SpecError prints. `loc` continues the value's path: a key of the
    object that is being read."""
    return PydanticCustomError("spec", why, {"loc": loc})


def _rule(ok: Callable[[Any], object], why: str) -> Callable[[Any], Any]:
    """A check: the value as it is when ok(value), else it fails with `why`."""
    def check(v: Any) -> Any:
        if not ok(v):
            raise _invalid(why)
        return v
    return check


def _whole(v: object) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _number(v: object) -> int | float:
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise _invalid(f"expected a number, got {_kind(v)}")
    return v


def _new_phase(v: str, info: ValidationInfo) -> str:
    if not _PHASE_ID.match(v) or v == "all":
        raise _invalid("expected a phase id: letters, digits, '.', '-' or '_', not 'all'")
    if v in info.context.phases:
        raise _invalid(f"phase {v!r} is listed twice")
    info.context.phases.append(v)
    return v


def _style(v: str, info: ValidationInfo) -> str:
    if v not in info.context.styles:
        raise _invalid(f"{v!r} names no style in $.styles")
    return v


def _phase(v: str, info: ValidationInfo) -> str:
    if v not in info.context.phases:
        raise _invalid(f"{v!r} names no phase in $.phases")
    return v


def _text(v: str, info: ValidationInfo) -> str:
    for m in _STYLE_REF.finditer(v):
        if m.group(1) not in info.context.styles:
            raise _invalid(f"{{{m.group(1)}:...}} names no style in $.styles")
    return v


def _unit(v: object) -> object:
    if not isinstance(v, list) or len(v) not in (2, 3):
        raise _invalid("expected [count, name, key] (the key may be left out)")
    return v if len(v) == 3 else [*v, ""]


def _shape(size: int, what: str) -> BeforeValidator:
    """A list of `size` items, else it fails with `expected what`."""
    return BeforeValidator(_rule(lambda v: isinstance(v, list) and len(v) == size, f"expected {what}"))


Str = StrictStr
Number = Annotated[int | float, PlainValidator(_number)]
Positive = Annotated[Number, AfterValidator(_rule(lambda v: v > 0, "expected a number above 0"))]
XY = Annotated[tuple[Number, Number], _shape(2, "a point [x, y] in minimap px")]
Polygon = Annotated[tuple[XY, ...], Field(min_length=3)]
Text = Annotated[Str, AfterValidator(_text)]                # prose: {style:text} must name a style
StyleRef = Annotated[Str, AfterValidator(_style)]
PhaseRef = Annotated[Str, AfterValidator(_phase)]
Chip = Annotated[tuple[Str, Text], _shape(2, "a chip [label, text]")]
# [count, name, key]: a key left out reads as "".
OobUnit = Annotated[tuple[Annotated[int, BeforeValidator(_rule(lambda v: _whole(v) and v >= 0,
                                                              "expected a count (a whole number)"))], Str, Str],
                    BeforeValidator(_unit)]
CropBox = Annotated[tuple[Number, Number, Number, Number],
                AfterValidator(_rule(lambda b: b[2] > b[0] and b[3] > b[1], "expected x1 > x0 and y1 > y0"))]
# A tag is the branch of a union a value is read as. Pydantic puts it in an error's location; the JSON path leaves it
# out. Tags are bracketed names, which no key of a spec is.
_TAGS = {f"<{tag}>" for tag in (*MARKS, "named crop", "box crop", "mark cell", "number cell", "text cell",
                                "stock zone", "own zone")}


def _tag(name: str) -> Tag:
    return Tag(f"<{name}>")


class _Object(BaseModel):
    """An object of the spec: an unknown key fails, naming the keys allowed there."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    @model_validator(mode="before")
    @classmethod
    def _known_keys(cls, v: object) -> object:
        if isinstance(v, dict):
            allowed = [f.alias or name for name, f in cls.model_fields.items()]
            for key in v:
                if key not in allowed:
                    raise _invalid(f"unknown key (allowed here: {', '.join(allowed)})", key)
        return v


class Label(_Object):
    """A mark's label."""
    text: Str
    at: XY


class _Mark(_Object):
    kind: str
    style: StyleRef
    phases: list[PhaseRef] = []     # none: every phase
    title: Str = ""                 # the hover title


class ArrowMark(_Mark):
    kind: Literal["arrow"]
    points: list[XY] = Field(min_length=2)
    dashed: StrictBool = False
    label: Label | None = None


class RingMark(_Mark):
    kind: Literal["ring"]
    at: XY
    r: Positive
    dashed: StrictBool = False
    label: Label | None = None


class UnitsMark(_Mark):
    kind: Literal["units"]
    at: XY
    count: Annotated[int, BeforeValidator(_rule(lambda v: _whole(v) and 1 <= v <= 60,
                                                "expected a whole number from 1 to 60"))]
    label: Label | None = None


class LabelMark(_Mark):
    kind: Literal["label"]
    at: XY
    text: Str
    size: Literal["small", "large"] = "small"


class ArcMark(_Mark):
    kind: Literal["arc"]
    from_: XY = Field(alias="from")
    to: XY
    bend: XY
    label: Label | None = None


class BurstMark(_Mark):
    kind: Literal["burst"]
    at: XY
    label: Label | None = None


def _mark_kind(v: object) -> str | None:
    if not isinstance(v, dict):
        return "<arrow>"        # read as an object, so it fails as not one
    return f"<{v['kind']}>" if v.get("kind") in MARKS else None


Mark = Annotated[Annotated[ArrowMark, _tag("arrow")] | Annotated[RingMark, _tag("ring")]
                 | Annotated[UnitsMark, _tag("units")] | Annotated[LabelMark, _tag("label")]
                 | Annotated[ArcMark, _tag("arc")] | Annotated[BurstMark, _tag("burst")],
                 Discriminator(_mark_kind, custom_error_type="spec",
                               custom_error_message=f"expected one of {', '.join(MARKS)}",
                               custom_error_context={"loc": ("kind",)})]


class MarkCell(_Object):
    mark: Literal["ok", "half", "open"]     # played; stock or built; not yet tested
    text: Text


def _cell_kind(v: object) -> str:
    if isinstance(v, dict):
        return "<mark cell>"
    return "<number cell>" if isinstance(v, (int, float)) and not isinstance(v, bool) else "<text cell>"


Cell = Annotated[Annotated[MarkCell, _tag("mark cell")] | Annotated[Number, _tag("number cell")]
                 | Annotated[Text, _tag("text cell")], Discriminator(_cell_kind)]


class Table(_Object):
    columns: list[Str] = Field(min_length=1)
    rows: list[list[Cell]]

    @model_validator(mode="after")
    def _one_cell_per_column(self) -> Table:
        for i, row in enumerate(self.rows):
            if len(row) != len(self.columns):
                raise _invalid(f"expected {len(self.columns)} cells, one per column, got {len(row)}", "rows", i)
        return self


class Group(_Object):
    name: Str
    when: Str = ""
    note: Text = ""
    units: list[OobUnit]


class Side(_Object):
    title: Str
    tag: Str = ""
    style: StyleRef = ""
    groups: list[Group]


class Section(_Object):
    heading: Str
    intro: Text = ""
    tables: list[Table] = []
    oob: list[Side] = []


class Phase(_Object):
    id: Annotated[Str, AfterValidator(_new_phase)]
    name: Str
    time: Str = ""
    summary: Text = ""
    details: list[Text] = []


class Deployment(_Object):
    style: StyleRef
    label: Str
    area: Polygon = ()      # drawn instead of the layout's zone of its alliance


class StockZone(_Object):
    """A command zone of the layout, by its stock Name."""
    stock: Str
    name: Str = ""

    @property
    def shown(self) -> str:
        """The name it is drawn with: its own name, if given, else its stock one."""
        return self.name if "name" in self.model_fields_set else self.stock


class OwnZone(_Object):
    """A command zone of the op's own."""
    name: Str
    area: Polygon
    points: Annotated[int, BeforeValidator(_rule(lambda v: _whole(v) and v >= 0, "expected a whole number, 0 or more"))]


def _zone_kind(v: object) -> str | None:
    if isinstance(v, dict) and "stock" in v:
        return "<stock zone>"
    return "<own zone>" if isinstance(v, dict) and ("area" in v or "points" in v) else None


CommandZone = Annotated[Annotated[StockZone, _tag("stock zone")] | Annotated[OwnZone, _tag("own zone")],
                        Discriminator(_zone_kind, custom_error_type="spec",
                                      custom_error_message="expected {stock, name?} or {name, area, points}")]
Crop = Annotated[Annotated[Literal["playable", "full"], _tag("named crop")] | Annotated[CropBox, _tag("box crop")],
                 Discriminator(lambda v: "<named crop>" if isinstance(v, str) else "<box crop>"),
                 BeforeValidator(_rule(lambda v: v in ("playable", "full") or isinstance(v, list) and len(v) == 4,
                                       "expected 'playable', 'full' or a box [x0, y0, x1, y1] in minimap px"))]


class Map(_Object):
    name: Annotated[Str, AfterValidator(_rule(_MAP_NAME.match, "expected a map datapack name (letters, digits and _)"))]
    layout: Annotated[Str, AfterValidator(_rule(lambda v: all(_PATH_PART.match(p) for p in v.split("/")),
                                                "expected a Details folder below the extraction, '/'-separated "
                                                "(no '..')"))]
    crop: Crop = "playable"
    deployments: dict[Annotated[str, AfterValidator(_rule(str.isdigit, "expected an alliance number as the key"))],
                      Deployment] = {}
    zone_names: dict[Annotated[str, AfterValidator(_rule(bool, "expected a stock zone name as the key"))], Str] = {}
    command_zones: list[CommandZone] = Field([], min_length=1)    # none: every zone of the layout
    mark_scale: Positive = 0        # 0: from the crop (map_scale)
    default_picture: Literal["minimap", "satellite"] = "minimap"

    @model_validator(mode="after")
    def _one_source_of_names(self) -> Map:
        if {"command_zones", "zone_names"} <= self.model_fields_set:
            raise _invalid("not allowed with command_zones: name a zone with command_zones' 'name' (one source of "
                           "truth)", "zone_names")
        return self


StyleName = Annotated[str, AfterValidator(_rule(lambda k: _STYLE_NAME.match(k) and k != "none",   # st-none: an
                                                "expected a style name (a letter, then letters, digits, - or _; "
                                                "not 'none') as the key"))]                         # unstyled alliance
Colour = Annotated[str, BeforeValidator(_rule(lambda c: isinstance(c, str) and _COLOUR.match(c),
                                              "expected a colour #rrggbb"))]


class Spec(_Object):
    """A storyboard spec (the module's docstring), read with ``Spec.read``. Its fields are read in this order: a
    style or phase is named only after ``styles`` and ``phases``."""
    version: Annotated[int, BeforeValidator(_rule(lambda v: v == VERSION and not isinstance(v, bool),
                                                  f"this generator reads version {VERSION}"))]
    title: Str
    eyebrow: Str = ""
    styles: dict[StyleName, Colour]
    chips: list[Chip] = []
    lede: Text = ""
    map: Map
    phases: list[Phase] = []
    start_phase: PhaseRef = ""      # none: the first phase
    marks: list[Mark] = []
    sections: list[Section] = []
    footer: list[Text] = []

    @field_validator("styles")
    @classmethod
    def _styles(cls, styles: dict[str, str], info: ValidationInfo) -> dict[str, str]:
        info.context.styles = set(styles)
        return styles

    @classmethod
    def read(cls, raw: object) -> Spec:
        """`raw` (a parsed JSON spec) validated. SpecError names the JSON path of the first value that breaks the
        schema."""
        try:
            return cls.model_validate(raw, context=_Refs())
        except ValidationError as exc:
            raise SpecError(_message(exc.errors()[0])) from None


def _message(error: ErrorDetails) -> str:
    """A validation error as '<JSON path>: <why>'."""
    kind, v, ctx = error["type"], error["input"], error.get("ctx", {})
    loc = [p for p in error["loc"] if p not in _TAGS and p != "[key]"] + list(ctx.get("loc", ()))
    if kind == "missing":
        why = f"missing key {loc.pop()!r}"
    elif kind in ("model_type", "dict_type"):
        why = f"expected an object, got {_kind(v)}"
    elif kind in ("list_type", "tuple_type"):
        why = f"expected a list, got {_kind(v)}"
    elif kind == "too_short":
        why = f"expected at least {ctx['min_length']} items, got {ctx['actual_length']}"
    elif kind == "string_type":
        why = f"expected a string, got {_kind(v)}"
    elif kind == "bool_type":
        why = f"expected true or false, got {_kind(v)}"
    elif kind == "literal_error":
        why = f"expected one of {', '.join(re.findall(r"'([^']*)'", ctx['expected']))}"
    else:
        why = error["msg"]      # the schema's own words (_invalid)
    return f"{functools.reduce(_at, loc, '$')}: {why}"


def unknown_units(spec: Spec, known: set[str]) -> list[tuple[str, str]]:
    """(JSON path, key) of every order-of-battle unit key (a unit's third item; keys may be joined by '·') whose
    descriptor is not in `known` (modkit.ops.gates.unit_database: every unit the game's unit database exports)."""
    out = []
    for i, s in enumerate(spec.sections):
        for j, side in enumerate(s.oob):
            for k, g in enumerate(side.groups):
                for n, u in enumerate(g.units):
                    for key in (p.strip() for p in u[2].split("·")):
                        if key and f"{UNIT_PREFIX}Descriptor_Unit_{key}" not in known:
                            out.append((f"$.sections[{i}].oob[{j}].groups[{k}].units[{n}][2]", key))
    return out


def load_spec(path: str | os.PathLike) -> dict:
    """The spec at `path`, parsed (not yet validated: ``Spec.read``). A file that is not UTF-8 JSON raises
    SpecError."""
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

    def crop(self, box: Box) -> Picture:
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
class Layout:
    """What the page draws exact from a Details folder's out/ files, in minimap px: the playable zone's ring, and the
    command and deployment zones (each named by its stock Name, AutoName_5)."""
    playable: tuple[Point, ...]
    command: tuple[Zone, ...]
    deployment: tuple[Zone, ...]


def _px(p: Sequence[float]) -> Point:
    return Point(p[0] / WORLD_PER_MINIMAP_PX, p[1] / WORLD_PER_MINIMAP_PX)


def _px_zone(zone: Zone) -> Zone:
    return replace(zone, polygon=tuple(_px(p) for p in zone.polygon))


class StockSource:
    """Reads a map's layout and pictures from the stock extraction (modkit.core.paths). A missing file fails naming
    the setup commands that fetch it (the warno-setup skill)."""

    def layout(self, rel: str) -> Layout:
        def zones(name: str) -> list:
            return read_zone_areas(read_file(extracted(f"{rel}/out/{name}.ndfbin")))

        ring = read_playable_polygon(read_file(extracted(f"{rel}/out/PlayableZone.ndfbin")))
        command = tuple(_px_zone(a.zone()) for a in zones("CommandZone"))
        deployment = tuple(_px_zone(a.zone()) for a in zones("DeploymentZone"))
        return Layout(tuple(_px(p) for p in ring), command, deployment)

    def picture(self, map_name: str, kind: str) -> Picture:
        """The map's `kind` picture ('Minimap' or 'Preview'), alpha dropped."""
        path = extracted(picture_path(map_name, kind))
        if not os.path.isfile(path):
            raise FileNotFoundError(f"missing stock file {paths.rel_source(path)}: the extraction lacks it; "
                                    f"{SETUP_FIX}")
        hdr, rgba = tgv.read_tgv(path)
        return Picture(hdr.width, hdr.height, tgv.drop_alpha(rgba))


def crop_box(crop: object, layout: Layout, width: int, height: int) -> Box:
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
    return Box(x0, y0, x1, y1)


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


def _label(label: Label | None) -> str:
    if not label:
        return ""
    x, y = label.at
    return f'<text class="sm" x="{_n(x)}" y="{_n(y)}">{esc(label.text)}</text>'


def map_scale(spec: Spec, box: Box) -> float:
    """How big the map's text, strokes and drawn shapes are: ``map.mark_scale``, else the crop's size against the
    432 x 622 px crop the look was tuned on. Rounded to 3 decimals."""
    given = spec.map.mark_scale
    return round(float(given or max((box[2] - box[0]) / 432, (box[3] - box[1]) / 622)), 3)


def mark_svg(mark: Mark, start: str | None, s: float = 1.0) -> str:
    """One mark as an SVG group in its style, with its label and its hover title. `s` (map_scale) sizes its drawn
    shapes."""
    kind, style = mark.kind, mark.style
    dashed = " dashed" if getattr(mark, "dashed", False) else ""     # arrows and rings
    if isinstance(mark, ArrowMark):
        d = " L".join(f"{_n(x)},{_n(y)}" for x, y in mark.points)
        body = f'<path class="arrow{dashed}" d="M{d}" marker-end="url(#ah-{style})"/>'
    elif isinstance(mark, RingMark):
        (x, y), r = mark.at, mark.r
        body = f'<circle class="ring{dashed}" cx="{_n(x)}" cy="{_n(y)}" r="{_n(r)}"/>'
    elif isinstance(mark, UnitsMark):
        (x, y), n = mark.at, mark.count
        cols = min(n, 4)
        rows = -(-n // cols)
        x0, y0 = x - (cols * 14 - 4) * s / 2, y - (rows * 12 - 4) * s / 2
        body = "".join(f'<rect class="unit" x="{_n(x0 + i % cols * 14 * s)}" y="{_n(y0 + i // cols * 12 * s)}" '
                       f'width="{_n(10 * s)}" height="{_n(8 * s)}"/>' for i in range(n))
    elif isinstance(mark, LabelMark):
        x, y = mark.at
        size = "lbl" if mark.size == "large" else "sm"
        body = f'<text class="{size}" x="{_n(x)}" y="{_n(y)}">{esc(mark.text)}</text>'
    elif isinstance(mark, ArcMark):
        (fx, fy), (bx, by), (tx, ty) = mark.from_, mark.bend, mark.to
        body = f'<path class="arc" d="M{_n(fx)},{_n(fy)} Q{_n(bx)},{_n(by)} {_n(tx)},{_n(ty)}"/>'
    else:  # burst: a cloud on its stem, the stem's foot at `at`
        x, y = mark.at
        body = (f'<rect class="burst" x="{_n(x - 5 * s)}" y="{_n(y - 22 * s)}" width="{_n(10 * s)}" '
                f'height="{_n(22 * s)}"/><circle class="burst" cx="{_n(x)}" cy="{_n(y - 38 * s)}" r="{_n(20 * s)}"/>')
    body += _label(getattr(mark, "label", None))     # a label mark is its own label
    if mark.title:
        body += f"<title>{esc(mark.title)}</title>"
    return f'<g {_phase_attrs(f"mark k-{kind} st-{style}", mark.phases, start)}>{body}</g>'


def _closed(area: Sequence[Sequence[float]]) -> tuple[Point, ...]:
    poly = tuple(Point(float(x), float(y)) for x, y in area)
    return poly if poly[0] == poly[-1] else poly + (poly[0],)


def command_zones(spec: Spec, layout: Layout) -> list[tuple[str, Zone, str | None]]:
    """The command zones to draw as (display name, zone, stock name or None for an op's own zone). With
    ``map.command_zones``, exactly those in order; else every zone of the layout, named by ``zone_names``."""
    m = spec.map
    if not m.command_zones:
        return [(m.zone_names.get(z.name, z.name), z, z.name) for z in layout.command]
    stock = {z.name: z for z in layout.command}
    out = []
    for i, item in enumerate(m.command_zones):
        if isinstance(item, StockZone):
            if item.stock not in stock:
                raise SpecError(f"$.map.command_zones[{i}].stock: the layout {m.layout} has no command zone "
                                f"{item.stock!r} (it has: {', '.join(stock) or 'none'})")
            out.append((item.shown, stock[item.stock], item.stock))
        else:
            out.append((item.name, Zone(item.name, _closed(item.area), points=item.points), None))
    return out


def zones_svg(spec: Spec, layout: Layout, s: float = 1.0) -> str:
    """The layout's deployment zones (dashed, in their alliance's style) and command zones (outline, name, points).
    A deployment's ``area`` replaces the layout's zone of its alliance (or is drawn alone when there is none); the
    command zones are those of ``command_zones`` when the spec has it. `s` (map_scale) offsets the command zone
    labels."""
    deployments = spec.map.deployments
    out, drawn = [], set()

    def deployment(poly: Sequence[Point], style: str, label: str, title: str) -> None:
        cx, cy = polygon_centroid(list(poly))
        out.append(f'<g class="dep st-{style}"><polygon points="{_pts(poly)}"/>'
                   f'<text class="deplbl" x="{_n(cx)}" y="{_n(cy + 4)}">{esc(label)}</text>'
                   f'<title>{esc(title)}</title></g>')

    for z in layout.deployment:
        d = deployments.get(str(z.alliance))
        if d and d.area:
            if z.alliance not in drawn:
                drawn.add(z.alliance)
                deployment(_closed(d.area), d.style, d.label, f"Deployment zone, alliance {z.alliance}: {d.label}")
            continue
        style, label = (d.style, d.label) if d else ("none", f"Deployment · alliance {z.alliance}")
        deployment(z.polygon, style, label, f"Deployment zone {z.name}, alliance {z.alliance}: {label}")
    for alliance, d in sorted(deployments.items(), key=lambda kv: int(kv[0])):
        if d.area and int(alliance) not in drawn:
            deployment(_closed(d.area), d.style, d.label, f"Deployment zone, alliance {int(alliance)}: {d.label}")
    for name, z, stock in command_zones(spec, layout):   # the name sits inside the zone's top, clear of the marks
        cx, top = polygon_centroid(list(z.polygon))[0], min(p[1] for p in z.polygon)
        title = f"Command zone {stock}" if stock else f"Command zone {name}"
        title += (f" ({name})" if stock and name != stock else "") + f": {z.points} points"
        out.append(f'<g class="cz"><polygon points="{_pts(z.polygon)}"/>'
                   f'<text x="{_n(cx)}" y="{_n(top + 14 * s)}">{esc(name)} · {z.points}</text>'
                   f'<title>{esc(title)}</title></g>')
    return "\n".join(out)


def map_svg(spec: Spec, layout: Layout, box: Box) -> str:
    """The map: both pictures at the crop box (viewBox), the zones, then the marks."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    marks = spec.marks
    start = start_phase(spec)
    arrows = list(dict.fromkeys(mk.style for mk in marks if mk.kind == "arrow"))
    defs = "".join(f'<marker id="ah-{s}" viewBox="0 0 10 10" refX="6" refY="5" markerWidth="4" markerHeight="4" '
                   f'orient="auto"><path d="M0,0 L10,5 L0,10 z" fill="{spec.styles[s]}"/></marker>' for s in arrows)
    picture = spec.map.default_picture
    k = map_scale(spec, box)
    at = f'x="{x0}" y="{y0}" width="{w}" height="{h}"'
    return "\n".join([
        f'<svg id="map" viewBox="{x0} {y0} {w} {h}" role="img" data-pic="{picture}" style="--s: {k:g}" '
        f'aria-label="{esc(spec.title)}: {esc(spec.map.name)}, the zones of the stock layout and the plan '
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


def start_phase(spec: Spec) -> str | None:
    return spec.start_phase or (spec.phases[0].id if spec.phases else None)


def _phases_html(spec: Spec) -> str:
    start = start_phase(spec)
    out = ['<div class="phases" id="phases">',
           '<button type="button" class="allbtn" id="v-all" aria-pressed="false">Show every phase</button>']
    for p in spec.phases:
        time = f'<span class="ph-time">{esc(p.time)}</span>' if p.time else ""
        summary = f'<span class="ph-sum">{text_html(p.summary)}</span>' if p.summary else ""
        details = "".join(f'<span class="ph-li">{text_html(d)}</span>' for d in p.details)
        details = f'<span class="ph-det">{details}</span>' if details else ""
        out.append(f'<button type="button" class="phase" data-p="{esc(p.id)}" '
                   f'aria-current="{str(p.id == start).lower()}">'
                   f'<span class="ph-head"><span class="ph-name">{esc(p.id)} · {esc(p.name)}</span>{time}</span>'
                   f'{summary}{details}</button>')
    out.append("</div>")
    return "\n".join(out)


def _legend_html(spec: Spec) -> str:
    items = [f'<span class="st-{esc(d.style)}"><i class="sw d"></i>{esc(d.label)}</span>'
             for _, d in sorted(spec.map.deployments.items(), key=lambda kv: int(kv[0]))]
    items.append('<span><i class="sw cz"></i>command zone (name · points)</span>')
    return '<div class="legend" aria-label="Legend">' + "".join(items) + "</div>"


def _cell(c: MarkCell | int | float | str) -> str:
    if isinstance(c, MarkCell):
        return f'<td><span class="mk {c.mark}">{text_html(c.text)}</span></td>'
    if isinstance(c, (int, float)):
        return f'<td class="n">{_n(c) if isinstance(c, float) else c}</td>'
    return f"<td>{text_html(c)}</td>"


def _table_html(t: Table) -> str:
    head = "".join(f"<th>{esc(c)}</th>" for c in t.columns)
    rows = "".join("<tr>" + "".join(_cell(c) for c in r) + "</tr>" for r in t.rows)
    return (f'<div class="tablewrap"><table><thead><tr>{head}</tr></thead>'
            f"<tbody>{rows}</tbody></table></div>")


def _oob_html(sides: Sequence[Side]) -> str:
    out = ['<div class="oob">']
    for s in sides:
        tag = f' <span class="tag">{esc(s.tag)}</span>' if s.tag else ""
        cls = f"side st-{s.style}" if s.style else "side"
        out.append(f'<div class="{cls}"><h3>{esc(s.title)}{tag}</h3>')
        for g in s.groups:
            when = f'<span>{esc(g.when)}</span>' if g.when else ""
            note = f'<div class="gn">{text_html(g.note)}</div>' if g.note else ""
            units = "".join(
                f'<li><span class="q">{count}</span><span class="nm">{esc(name)}'
                + (f' <span class="key">{esc(key)}</span>' if key else "") + "</span></li>"
                for count, name, key in g.units)
            out.append(f'<div class="grp"><div class="gh"><b>{esc(g.name)}</b>{when}</div>{note}'
                       f'<ul class="unitlist">{units}</ul></div>')
        out.append("</div>")
    out.append("</div>")
    return "\n".join(out)


def _sections_html(spec: Spec) -> str:
    out = []
    for i, s in enumerate(spec.sections, 1):
        part = [f'<section class="block" aria-labelledby="s{i}-h">', f'<h2 id="s{i}-h">{esc(s.heading)}</h2>']
        if s.intro:
            part.append(f"<p>{text_html(s.intro)}</p>")
        tables = [_table_html(t) for t in s.tables]
        if len(tables) > 1:
            part.append('<div class="cols2">' + "".join(tables) + "</div>")
        else:
            part += tables
        if s.oob:
            part.append(_oob_html(s.oob))
        part.append("</section>")
        out.append("\n".join(part))
    return "\n".join(out)


def _styles_css(styles: Mapping[str, str]) -> str:
    rules = [f".st-{n} {{ --c: {c}; --t: {_tint(c)}; }} .tx-{n} {{ color: {_tint(c)}; }}" for n, c in styles.items()]
    accent = next(iter(styles.values()), "#e7eae4")
    return f":root {{ --accent: {accent}; }}\n" + "\n".join(rules)


def render_page(spec: Spec, layout: Layout, box: Box) -> str:
    """The page for a spec: one HTML file referring to the two pictures beside it."""
    phases = spec.phases
    picture = spec.map.default_picture
    chips = "".join(f'<span class="chip">{esc(k)} <b>{text_html(v)}</b></span>' for k, v in spec.chips)
    header = [f'<div class="eyebrow">{esc(spec.eyebrow)}</div>' if spec.eyebrow else "",
              f"<h1>{esc(spec.title)}</h1>",
              f'<div class="status">{chips}</div>' if chips else "",
              f'<p class="lede">{text_html(spec.lede)}</p>' if spec.lede else ""]
    switch = "".join(f'<button type="button" id="{bid}" data-pic="{p}" aria-pressed="{str(p == picture).lower()}">'
                     f"{p.capitalize()}</button>" for bid, p in (("b-mini", "minimap"), ("b-sat", "satellite")))
    footer = "".join(f"<div>{text_html(line)}</div>" for line in spec.footer)
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
    return "\n".join([_HEAD.replace("PAGE_TITLE", esc(spec.title)), "<style>", _CSS, _styles_css(spec.styles),
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


def generate(spec: Spec, out_dir: str | os.PathLike, source: StockSource | None = None, *,
             units: set[str] | None = None) -> list[str]:
    """Reads the map of `spec` from `source` (the stock extraction by default) and writes the page and its two
    pictures into `out_dir`. With `units` (unit_database()), every order-of-battle unit key must name one of them.
    Returns the lines to print: one per file, then the Artifact publish line. Nothing is written unless every check
    passes."""
    checked = []
    if units is not None:
        bad = unknown_units(spec, units)
        if bad:
            raise SpecError(f"{bad[0][0]}: not in the game's unit database: {', '.join(k for _, k in bad)}")
        checked = ["unit keys: every one is in the game's unit database"]
    source = source or StockSource()
    m = spec.map
    layout = source.layout(m.layout)
    command_zones(spec, layout)     # a stock name the layout lacks fails before anything is written
    minimap, preview = source.picture(m.name, "Minimap"), source.picture(m.name, "Preview")
    k = _scale(minimap, preview)
    box = crop_box(m.crop, layout, minimap.width, minimap.height)
    page = render_page(spec, layout, box).encode("utf-8")
    if len(page) > MAX_PAGE:
        raise ValueError(f"{PAGE} would be {_size(len(page))}, over the {_size(MAX_PAGE)} a page may be: "
                         f"shorten the spec's text")
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    mini = minimap.crop(box)
    tgv.write_png(str(out / MINIMAP), mini.width, mini.height, mini.rgb, channels=3)
    sat = preview.crop(Box(*(c * k for c in box)))
    tgv.write_png(str(out / SATELLITE), sat.width, sat.height, sat.rgb, channels=3)
    halved = ""
    if (out / SATELLITE).stat().st_size > MAX_PICTURE:
        halved = f", halved: over {_size(MAX_PICTURE)} at the Preview's {sat.width}x{sat.height}"
        sat = sat.halved()
        tgv.write_png(str(out / SATELLITE), sat.width, sat.height, sat.rgb, channels=3)
    (out / PAGE).write_bytes(page)
    where = {name: (out / name).absolute().as_posix() for name in (PAGE, MINIMAP, SATELLITE)}
    marks, phases = len(spec.marks), len(spec.phases)
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
        raw = load_spec(args.spec)
        out = Path(args.out) if args.out else default_out(args.spec)
        lines = generate(Spec.read(raw), out, units=unit_database() if args.check_units else None)
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
