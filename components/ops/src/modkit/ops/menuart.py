"""An Operation's own menu card: a stock MapTexture redrawn with the op's title and, optionally, the op's own map.

The Operations menu shows each scenario's MapTexture (``MapPackAssets/Textures/MapTexture.tgv`` in its Assets pack):
a paper map with a polaroid photo laid over one corner, the photo's caption handwritten with the Operation's name. An
op cloned from a stock scenario ships that scenario's card, name and all. ``build_card`` redraws the card at build
time from the user's own extraction; the toolkit ships no picture.

* **The caption.** The polaroid's caption strip (``CardLayout.band``, and ``clean``: what of the stock caption's
  decoration spills past it) is repainted in the polaroid's paper colour, and the title is drawn on it in dark ink
  with a built-in stroke font (``STROKES``), antialiased, turned to the photo's tilt and as large as the strip allows.
  Nothing of the stock caption is left inside the strip.
* **The map** (``MapView``, optional). The map inside the paper's border is replaced by a box of a map's Preview
  picture, greyed and toned to the stock map's look (``CardLayout.tone``), with the paper's fold creases and the
  polaroid's shadow. The paper, its border and the polaroid stay; the stock map's own markings go with the stock map.
  ``cut_view`` makes the view of an op's cut (``modkit.ops.maps.Cut``): the smallest box of the card map's shape that
  holds the cut, kept inside the picture.
* **Markings** (optional, on the swapped map). Zones (``draw_zones``): a polygon in the view's units, red or blue,
  drawn as stock draws its zones, a marker outline with diagonal hatching, the map showing through (a multiply by
  pure red or blue), and only on the map. Stickers (``draw_stickers``): the stock card's own badge stickers
  (``CardLayout.stickers``: Survivors' Soviet star and NATO badge), copied byte for byte and moved by whole pixels
  to a point in the view's units; one that would cross the map's border or the polaroid fails.

The result (``Card``) is a TGV in the stock card's exact format and size (``modkit.core.tgv.encode_tgv``), and a PNG
for review. An op ships ``build_card(TITLE, cut_view(CUT)).tgv`` (or ``build_card(TITLE).tgv``, the stock map kept) in
place of its template's ``MapTexture.tgv``, its markings passed as ``zones=[(polygon, "red" | "blue")]`` and
``stickers=[("SOV" | "NATO", (x, y))]`` in minimap px (none by default). ``card_picture`` wraps that for
``OpProfile.menu_art``: the build makes the card and names its sources in MANIFEST.tsv.

A card's geometry is measured off one stock picture (``CardLayout``) and pinned to it by SHA-256, so a different or
changed stock card fails rather than drawing in the wrong place. ``SURVIVORS`` is Survivors' card, the one an op
cloned from Survivors ships.

CLI, for review pictures (writes ``MapTexture.tgv`` and ``MapTexture.png`` into OUT)::

    python -m modkit.ops.menuart "TWIN STRIKE" --out OUT [--map TWIN_CITIES --box X0 Y0 X1 Y1]

``--box`` is in the map's minimap pixels, as a ``Cut``'s.
"""
from __future__ import annotations

import argparse
import bisect
import hashlib
import math
import os
import sys
import zlib
from collections.abc import Sequence
from dataclasses import dataclass

from modkit.core import paths, tgv
from modkit.core.gates import CheckError, check
from modkit.ops.profile import extracted

Point = tuple[float, float]
Box = tuple[float, float, float, float]


# --------------------------------------------------------------------------- the layout

@dataclass(frozen=True)
class Sticker:
    """A badge sticker on a stock card: a rounded square turned by atan(`slope`) (its top edge rising to the right),
    measured where its white edge crosses the map."""
    centre: Point
    size: tuple[float, float]   # width and height, along its own edges
    slope: float
    radius: float               # its corners'

    def coverage(self, x: float, y: float) -> float:
        """How much of the pixel centred at (x, y) the sticker covers (0-1)."""
        c, s = math.cos(math.atan(self.slope)), math.sin(math.atan(self.slope))
        dx, dy = x - self.centre[0], y - self.centre[1]
        qx = abs(dx * c - dy * s) - (self.size[0] / 2 - self.radius)
        qy = abs(dx * s + dy * c) - (self.size[1] / 2 - self.radius)
        d = math.hypot(max(qx, 0.0), max(qy, 0.0)) + min(max(qx, qy), 0.0) - self.radius
        return max(0.0, min(1.0, 0.5 - d))


@dataclass(frozen=True)
class CardLayout:
    """Where things are on one stock menu card, measured off its pixels (image px, x right, y down).

    The polaroid is a rectangle turned by ``tilt`` (radians; its top edge rises to the right): its own frame has
    ``origin`` at its top-left corner, u along its top edge and v down its left edge."""
    source: str                     # the stock card, relative to the extraction
    sha256: str                     # of the stock card's file: the picture the layout was measured on
    size: tuple[int, int]
    origin: Point                   # the polaroid's top-left corner
    tilt: float
    polaroid: tuple[float, float]   # its width and height, in its frame
    band: Box                       # the caption strip, repainted: (u0, v0, u1, v1) in the polaroid's frame
    clean: tuple[Box, ...]          # more of the polaroid repainted blank (the stock caption's decoration)
    paper: tuple[int, int, int]     # the polaroid paper's colour
    ink: tuple[int, int, int]
    map_corners: tuple[Point, Point, Point, Point]   # the map inside the paper's border: TL, TR, BR, BL
    map_paper: tuple[int, int, int]                  # the paper's border round the map
    tone: tuple[tuple[float, float], ...]            # (quantile, grey) of the stock map's plain ground
    creases: tuple[float, float]    # the paper's folds: at this fraction across the map, and down it
    margin: tuple[float, float] = (7.0, 5.0)         # the title's clearance inside the band, along u and v
    max_cap: float = 26.0                            # the tallest cap height drawn, px
    stickers: tuple[tuple[str, Sticker], ...] = ()   # the badge stickers markings may reuse, by name
    pen: float = 3.2                                 # a zone marker's half-width, px
    hatch: tuple[float, float] = (37.0, 30.0)        # a zone's hatching: its rise (degrees) and spacing (px)

    def to_frame(self, x: float, y: float) -> Point:
        """Image px to the polaroid's (u, v)."""
        c, s = math.cos(self.tilt), math.sin(self.tilt)
        dx, dy = x - self.origin[0], y - self.origin[1]
        return dx * c - dy * s, dx * s + dy * c

    def to_image(self, u: float, v: float) -> Point:
        c, s = math.cos(self.tilt), math.sin(self.tilt)
        return self.origin[0] + u * c + v * s, self.origin[1] - u * s + v * c

    def repainted(self, x: int, y: int) -> float:
        """How much of pixel (x, y) the band and the clean boxes cover (0-1): 1 when its centre lies half a pixel or
        more inside one."""
        u, v = self.to_frame(x + 0.5, y + 0.5)
        return max(max(0.0, min(1.0, min(u - u0, u1 - u, v - v0, v1 - v) + 0.5))
                   for u0, v0, u1, v1 in (self.band, *self.clean))

    def repainted_pixels(self) -> list[tuple[int, int]]:
        """(x, y) of every pixel the band and the clean boxes cover whole: the pixels no stock value survives in."""
        corners = [self.to_image(u, v)
                   for u0, v0, u1, v1 in (self.band, *self.clean) for u in (u0, u1) for v in (v0, v1)]
        return [(x, y) for y, x in _bbox_pixels(corners, self.size) if self.repainted(x, y) == 1]


SURVIVORS_CARD = "scenarios/challenge_Survivors/PC/Texture/challenge_Survivors/MapPackAssets/Textures/MapTexture.tgv"

# Survivors' card (537 x 598), measured on its pixels: each edge a least-squares line through sub-pixel crossings,
# residuals under half a pixel.
# - The polaroid: its left, top and bottom edges, and the right edge of its photo (all four lean 0.0835: a 4.77 degree
#   tilt). It is 174.95 x 211.55 px; the photo's bottom edge lies at v 168.5, so the caption strip is v 168.5-211.55.
#   The band runs from 0.4 px below the photo to the polaroid's edges. clean: the polaroid's left border beside the
#   photo, from v 140 down, where the stock caption's blue stamp spills over (it also stains the photo's corner,
#   which stays).
# - paper: the strip's clean paper (237-243 grey, neutral); ink: the stock caption's marker, 24-48 grey.
# - map_corners: the four edges of the map inside the paper's white border (it is turned 1.2 degrees, 492 px a side);
#   map_paper: that border (247-253 grey).
# - tone: quantiles of the stock map's neutral pixels (its hatching and badges left out, and its white badges capped
#   by stopping at the 90th).
# - creases: the dark fold lines, x 276 at the top to 269.5 at the bottom, y 279-285: the map's middle.
# - stickers: the Soviet star (the red zone's) and the NATO badge (the blue zone's), each edge a line through the
#   crossings of grey 180 between the sticker's white (233) and the map (residuals under 0.55 px); they lean 1.4 and
#   1.8 degrees. Their corners round off in 2-3 px along the diagonal: a radius of about 6.
# - pen and hatch: the zones' marker strokes are 6-7 px wide (outline and hatching alike); the hatching rises 35-38
#   degrees, drawn by hand 25-37 px apart. A stroke keeps the map's grey in its own channel (red R, blue B) and
#   zeroes the others: a multiply by pure red or blue.
SURVIVORS = CardLayout(
    source=SURVIVORS_CARD,
    sha256="575f60438c0cf6f156e3f53a59c01ff6854099ca8a91031a98140031583a7f62",
    size=(537, 598),
    origin=(4.655, 19.46),
    tilt=math.atan(0.0835),
    polaroid=(174.95, 211.55),
    band=(0.0, 168.9, 174.95, 211.55),
    clean=((0.0, 140.0, 10.3, 168.9),),
    paper=(240, 240, 240),
    ink=(30, 30, 34),
    map_corners=((27.09, 24.96), (519.14, 35.68), (508.91, 527.21), (18.13, 516.92)),
    map_paper=(250, 250, 250),
    tone=((0.02, 50.0), (0.25, 82.0), (0.5, 91.0), (0.75, 106.0), (0.9, 131.0)),
    creases=(0.507, 0.512),
    stickers=(("SOV", Sticker((259.17, 334.91), (72.71, 72.53), 0.0243, 6.0)),
              ("NATO", Sticker((66.48, 472.16), (63.37, 63.47), 0.032, 6.0))),
)


# --------------------------------------------------------------------------- the font

def _arc(cx: float, cy: float, rx: float, ry: float, a0: float, a1: float) -> list[Point]:
    """Points of an elliptic arc from angle a0 to a1 (degrees; 0 is right, 90 is down), every 15 degrees or less."""
    n = max(2, math.ceil(abs(a1 - a0) / 15))
    return [(cx + rx * math.cos(math.radians(a0 + (a1 - a0) * i / n)),
             cy + ry * math.sin(math.radians(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]


# The stroke font: each glyph is (width, strokes), a stroke a polyline in cap-height units (x right, y down, 0 the
# cap line, 1 the baseline). Plain single-stroke capitals, figures and a little punctuation; titles are upper-cased.
STROKES: dict[str, tuple[float, tuple[tuple[Point, ...], ...]]] = {
    "A": (0.62, (((0, 1), (0.31, 0), (0.62, 1)), ((0.1, 0.67), (0.52, 0.67)))),
    "B": (0.56, (((0, 0), (0, 1)),
                 ((0, 0), (0.3, 0), *_arc(0.3, 0.24, 0.22, 0.24, -90, 90), (0, 0.48)),
                 ((0, 0.48), (0.32, 0.48), *_arc(0.32, 0.74, 0.24, 0.26, -90, 90), (0, 1)))),
    "C": (0.58, (tuple(_arc(0.33, 0.5, 0.33, 0.5, -40, -320)),)),
    "D": (0.6, (((0, 0), (0, 1)), ((0, 0), (0.22, 0), *_arc(0.22, 0.5, 0.38, 0.5, -90, 90), (0, 1)))),
    "E": (0.52, (((0.52, 0), (0, 0), (0, 1), (0.52, 1)), ((0, 0.5), (0.42, 0.5)))),
    "F": (0.5, (((0.5, 0), (0, 0), (0, 1)), ((0, 0.5), (0.4, 0.5)))),
    "G": (0.62, ((*_arc(0.33, 0.5, 0.33, 0.5, -40, -360), (0.38, 0.5)),)),
    "H": (0.58, (((0, 0), (0, 1)), ((0.58, 0), (0.58, 1)), ((0, 0.5), (0.58, 0.5)))),
    "I": (0.0, (((0, 0), (0, 1)),)),
    "J": (0.46, (((0.46, 0), (0.46, 0.72), *_arc(0.23, 0.72, 0.23, 0.28, 0, 180)),)),
    "K": (0.56, (((0, 0), (0, 1)), ((0.56, 0), (0, 0.62)), ((0.2, 0.46), (0.58, 1)))),
    "L": (0.48, (((0, 0), (0, 1), (0.48, 1)),)),
    "M": (0.72, (((0, 1), (0, 0), (0.36, 0.62), (0.72, 0), (0.72, 1)),)),
    "N": (0.58, (((0, 1), (0, 0), (0.58, 1), (0.58, 0)),)),
    "O": (0.68, (tuple(_arc(0.34, 0.5, 0.34, 0.5, 0, 360)),)),
    "P": (0.54, (((0, 1), (0, 0), (0.3, 0), *_arc(0.3, 0.26, 0.24, 0.26, -90, 90), (0, 0.52)),)),
    "Q": (0.68, (tuple(_arc(0.34, 0.5, 0.34, 0.5, 0, 360)), ((0.4, 0.68), (0.7, 1.02)))),
    "R": (0.56, (((0, 1), (0, 0), (0.3, 0), *_arc(0.3, 0.26, 0.24, 0.26, -90, 90), (0, 0.52)),
                 ((0.26, 0.52), (0.58, 1)))),
    "S": (0.54, ((*_arc(0.27, 0.25, 0.26, 0.25, -25, -270), *_arc(0.27, 0.75, 0.27, 0.25, -90, 155)),)),
    "T": (0.6, (((0, 0), (0.6, 0)), ((0.3, 0), (0.3, 1)))),
    "U": (0.58, (((0, 0), (0, 0.68), *_arc(0.29, 0.68, 0.29, 0.32, 180, 0), (0.58, 0)),)),
    "V": (0.62, (((0, 0), (0.31, 1), (0.62, 0)),)),
    "W": (0.84, (((0, 0), (0.2, 1), (0.42, 0.3), (0.64, 1), (0.84, 0)),)),
    "X": (0.58, (((0, 0), (0.58, 1)), ((0.58, 0), (0, 1)))),
    "Y": (0.6, (((0, 0), (0.3, 0.5), (0.6, 0)), ((0.3, 0.5), (0.3, 1)))),
    "Z": (0.56, (((0, 0), (0.56, 0), (0, 1), (0.56, 1)),)),
    "0": (0.56, (tuple(_arc(0.28, 0.5, 0.28, 0.5, 0, 360)),)),
    "1": (0.3, (((0, 0.2), (0.24, 0), (0.24, 1)),)),
    "2": (0.54, ((*_arc(0.27, 0.27, 0.27, 0.27, -165, 25), (0, 1), (0.56, 1)),)),
    "3": (0.54, ((*_arc(0.26, 0.25, 0.25, 0.25, -150, 90), *_arc(0.26, 0.75, 0.28, 0.25, -90, 150)),)),
    "4": (0.58, (((0.44, 1), (0.44, 0), (0, 0.7), (0.58, 0.7)),)),
    "5": (0.54, (((0.52, 0), (0.08, 0), (0.04, 0.46), *_arc(0.27, 0.68, 0.28, 0.32, -140, 150)),)),
    "6": (0.56, (((0.46, 0), (0.12, 0.34), (0.01, 0.66)), tuple(_arc(0.28, 0.69, 0.27, 0.31, 0, 360)))),
    "7": (0.54, (((0, 0), (0.54, 0), (0.18, 1)),)),
    "8": (0.56, (tuple(_arc(0.28, 0.25, 0.24, 0.25, 0, 360)), tuple(_arc(0.28, 0.75, 0.28, 0.25, 0, 360)))),
    "9": (0.56, (tuple(_arc(0.28, 0.31, 0.27, 0.31, 0, 360)), ((0.55, 0.34), (0.44, 0.66), (0.1, 1)))),
    "-": (0.36, (((0, 0.55), (0.36, 0.55)),)),
    ".": (0.0, (((0, 0.97), (0, 1)),)),
    ",": (0.06, (((0.06, 0.92), (0, 1.12)),)),
    "'": (0.0, (((0, 0), (0, 0.26)),)),
    ":": (0.0, (((0, 0.3), (0, 0.33)), ((0, 0.97), (0, 1)))),
    "!": (0.0, (((0, 0), (0, 0.68)), ((0, 0.97), (0, 1)))),
    "/": (0.46, (((0, 1), (0.46, 0)),)),
    "&": (0.62, ((((0.62, 1), *_arc(0.24, 0.24, 0.17, 0.24, 30, -210), (0.38, 0.52), (0.52, 0.6)),
                  ((0.38, 0.52), *_arc(0.26, 0.75, 0.26, 0.25, -60, 160), (0.62, 0.5))))),
}
GAP = 0.22      # between glyphs, in cap heights
SPACE = 0.3     # a space's width (a gap on each side as well)
STROKE = 0.075  # the pen's radius, in cap heights (at least 1.1 px)
MIN_CAP = 12.0  # px: a smaller title is unreadable in the menu


def title_width(title: str) -> float:
    """The title's ink width in cap heights, the pen's radius left out."""
    widths = [SPACE if ch == " " else STROKES[ch][0] for ch in title]
    return sum(widths) + GAP * (len(widths) - 1)


def _segments(title: str, cap: float, u: float, v: float) -> list[tuple[Point, Point]]:
    """The title's strokes as segments in the polaroid's frame, its top-left at (u, v), `cap` px tall."""
    out: list[tuple[Point, Point]] = []
    for ch in title:
        width, strokes = (SPACE, ()) if ch == " " else STROKES[ch]
        for stroke in strokes:
            pts = [(u + x * cap, v + y * cap) for x, y in stroke]
            out += list(zip(pts, pts[1:]))
        u += (width + GAP) * cap
    return out


def _dist(p: Point, a: Point, b: Point) -> float:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = dx * dx + dy * dy
    t = 0.0 if n == 0 else max(0.0, min(1.0, ((p[0] - a[0]) * dx + (p[1] - a[1]) * dy) / n))
    return math.hypot(p[0] - a[0] - t * dx, p[1] - a[1] - t * dy)


# --------------------------------------------------------------------------- pixels

def _bbox_pixels(points: list[Point], size: tuple[int, int], pad: int = 1):
    """(y, x) of every pixel of the points' bounding box, grown by `pad`, inside the picture."""
    xs, ys = [p[0] for p in points], [p[1] for p in points]
    for y in range(max(0, int(min(ys)) - pad), min(size[1], int(max(ys)) + pad + 1)):
        for x in range(max(0, int(min(xs)) - pad), min(size[0], int(max(xs)) + pad + 1)):
            yield y, x


def _noise(x: int, y: int) -> int:
    """A fixed paper grain, -1, 0 or 1, from the pixel's position alone."""
    return zlib.crc32(x.to_bytes(2, "little") + y.to_bytes(2, "little")) % 3 - 1


def _blend(img: bytearray, i: int, rgb: tuple[float, float, float], k: float) -> None:
    """Paint `rgb` over the opaque pixel at byte `i` with coverage k (0-1)."""
    for c in range(3):
        img[i + c] = max(0, min(255, round(img[i + c] * (1 - k) + rgb[c] * k)))
    img[i + 3] = 255


def draw_caption(layout: CardLayout, img: bytearray, title: str) -> float:
    """Repaint the caption strip and the clean boxes of `img` (the card's RGBA, in place) and write `title` in the
    strip. Returns the cap height drawn. A title the font cannot write, or too long for a legible caption, fails
    (CheckError)."""
    title = " ".join(title.upper().split())
    missing = sorted({ch for ch in title if ch != " " and ch not in STROKES})
    check(bool(title), "menu card title: empty")
    check(not missing, f"menu card title {title!r}: the stroke font has no {', '.join(map(repr, missing))}")
    u0, v0, u1, v1 = layout.band
    mu, mv = layout.margin
    room_u, room_v = u1 - u0 - 2 * mu, v1 - v0 - 2 * mv
    cap = min(layout.max_cap, room_v / (1 + 2 * STROKE), room_u / (title_width(title) + 2 * STROKE))
    check(cap >= MIN_CAP, f"menu card title {title!r}: it fits the caption only {cap:.1f} px tall (under "
                          f"{MIN_CAP:g}, too small to read); shorten it")
    pen = max(1.1, STROKE * cap)
    left = (u0 + u1) / 2 - title_width(title) * cap / 2
    top = (v0 + v1) / 2 - cap / 2
    segs = _segments(title, cap, left, top)
    w = layout.size[0]
    boxes = (layout.band, *layout.clean)
    for y, x in _bbox_pixels([layout.to_image(a, b) for a0, b0, a1, b1 in boxes for a in (a0, a1) for b in (b0, b1)],
                             layout.size):
        k = layout.repainted(x, y)
        if k == 0:
            continue
        u, v = layout.to_frame(x + 0.5, y + 0.5)
        grain = _noise(x, y)
        col = [c + grain for c in layout.paper]
        near = [s for s in segs if min(s[0][0], s[1][0]) - pen - 1 <= u <= max(s[0][0], s[1][0]) + pen + 1
                and min(s[0][1], s[1][1]) - pen - 1 <= v <= max(s[0][1], s[1][1]) + pen + 1]
        if near:
            ink = max(0.0, min(1.0, pen + 0.5 - min(_dist((u, v), a, b) for a, b in near)))
            col = [p * (1 - ink) + q * ink for p, q in zip(col, layout.ink)]
        _blend(img, (y * w + x) * 4, col, k)
    return cap


# --------------------------------------------------------------------------- the map

@dataclass(frozen=True)
class MapView:
    """A box of a map picture (a Preview .tgv, relative to the extraction), in that picture's px: the map a card
    shows. Markings on it (zones, stickers) are given in units of `unit` picture px (a cut's view: minimap px)."""
    picture: str
    box: Box
    unit: float = 1.0

    def to_card(self, layout: CardLayout, p: Point) -> Point:
        """A point in the view's units to card px: where draw_map draws that spot of the picture."""
        x0, y0, x1, y1 = self.box
        s, t = (p[0] * self.unit - x0) / (x1 - x0), (p[1] * self.unit - y0) / (y1 - y0)
        tl, ea, eb = _map_frame(layout)
        return tl[0] + s * ea[0] + t * eb[0], tl[1] + s * ea[1] + t * eb[1]


def view_box(box: Box, aspect: float, bounds: tuple[int, int]) -> Box:
    """The smallest box of shape `aspect` (width / height) that holds `box`, centred on it and moved inside
    `bounds` (width, height); shrunk about its centre when the picture is too small."""
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    w, h = max(w, h * aspect), max(h, w / aspect)
    if w > bounds[0]:
        w, h = bounds[0], bounds[0] / aspect
    if h > bounds[1]:
        w, h = bounds[1] * aspect, bounds[1]
    cx = min(max((x0 + x1) / 2, w / 2), bounds[0] - w / 2)
    cy = min(max((y0 + y1) / 2, h / 2), bounds[1] - h / 2)
    return cx - w / 2, cy - h / 2, cx + w / 2, cy + h / 2


def _map_frame(layout: CardLayout) -> tuple[Point, Point, Point]:
    """The map's top-left corner and its two edge vectors (top edge, left edge)."""
    tl, tr, _, bl = layout.map_corners
    return tl, (tr[0] - tl[0], tr[1] - tl[1]), (bl[0] - tl[0], bl[1] - tl[1])


def map_aspect(layout: CardLayout) -> float:
    _, a, b = _map_frame(layout)
    return math.hypot(*a) / math.hypot(*b)


def cut_view(cut, layout: CardLayout = SURVIVORS) -> MapView:
    """The view of an op's cut (modkit.ops.maps.Cut): its map's Preview, the box holding the cut at the card map's
    shape."""
    picture = cut.map.picture("Preview")
    hdr = tgv.parse_header(_read(picture))
    k = hdr.width / cut.map.minimap_px[0]
    x0, y0, x1, y1 = cut.box_px
    return MapView(picture, view_box((x0 * k, y0 * k, x1 * k, y1 * k), map_aspect(layout), (hdr.width, hdr.height)),
                   unit=k)


def _grey_view(view: MapView, out_w: int, out_h: int) -> list[list[float]]:
    """The view's box of its picture, greyed (Rec. 601 luma) and area-resampled to out_w x out_h."""
    hdr, rgba = tgv.decode_tgv(_read(view.picture))
    x0, y0, x1, y1 = view.box
    check(0 <= x0 < x1 <= hdr.width and 0 <= y0 < y1 <= hdr.height,
          f"map view {view.box} lies outside {view.picture} ({hdr.width}x{hdr.height})")
    c0, c1, r0, r1 = int(x0), min(hdr.width, math.ceil(x1)), int(y0), min(hdr.height, math.ceil(y1))
    stride = hdr.width * 4
    rows = []
    for y in range(r0, r1):
        line = rgba[y * stride + c0 * 4:y * stride + c1 * 4]
        rows.append([0.299 * r + 0.587 * g + 0.114 * b for r, g, b in zip(line[0::4], line[1::4], line[2::4])])

    def weights(n_out: int, lo: float, hi: float, first: int, n_src: int):
        """For each output cell, the (source index, weight) pairs of the source cells it covers."""
        step = (hi - lo) / n_out
        out = []
        for i in range(n_out):
            a, b = lo + i * step, lo + (i + 1) * step
            ws = [(j - first, min(b, j + 1) - max(a, j)) for j in range(int(a), math.ceil(b))
                  if 0 <= j - first < n_src and min(b, j + 1) > max(a, j)]
            total = sum(wt for _, wt in ws)
            out.append([(j, wt / total) for j, wt in ws])
        return out
    wx = weights(out_w, x0, x1, c0, c1 - c0)
    wy = weights(out_h, y0, y1, r0, r1 - r0)
    across = [[sum(row[j] * wt for j, wt in cell) for cell in wx] for row in rows]
    return [[sum(across[j][i] * wt for j, wt in cell) for i in range(out_w)] for cell in wy]


def _tone_curve(values: list[float], tone: tuple[tuple[float, float], ...]):
    """A piecewise-linear map sending the quantiles of `values` named in `tone` to its greys (extended past the
    ends with the end slopes)."""
    ordered = sorted(values)
    src = [ordered[min(len(ordered) - 1, int(q * len(ordered)))] for q, _ in tone]
    for i in range(1, len(src)):  # flat stretches of the picture: keep the knots increasing
        src[i] = max(src[i], src[i - 1] + 1e-3)
    dst = [g for _, g in tone]

    def curve(v: float) -> float:
        i = min(max(bisect.bisect(src, v) - 1, 0), len(src) - 2)
        return dst[i] + (v - src[i]) * (dst[i + 1] - dst[i]) / (src[i + 1] - src[i])
    return curve


SHADOW = (1.5, 2.0, 7.0, 0.3)   # the polaroid's shadow: offset along u and v, fade length (px), depth at its edge
CREASE = (0.8, 0.28)            # a fold line's half-width (px, a Gaussian's sigma) and its depth at the centre


def draw_map(layout: CardLayout, img: bytearray, view: MapView) -> None:
    """Replace the map of `img` (the card's RGBA, in place) by `view`, toned like the stock map, under the polaroid's
    shadow and the paper's creases; the polaroid and the paper stay."""
    tl, ea, eb = _map_frame(layout)
    out_w, out_h = round(math.hypot(*ea)), round(math.hypot(*eb))
    grey = _grey_view(view, out_w, out_h)
    curve = _tone_curve([g for row in grey for g in row], layout.tone)
    det = ea[0] * eb[1] - ea[1] * eb[0]
    corners = layout.map_corners
    edges = []   # (a point on the edge, its inward unit normal): the corners run clockwise on screen
    for a, b in zip(corners, corners[1:] + corners[:1]):
        n = math.hypot(b[0] - a[0], b[1] - a[1])
        edges.append((a, (-(b[1] - a[1]) / n, (b[0] - a[0]) / n)))
    side_a, side_b = math.hypot(*ea), math.hypot(*eb)
    pw, ph = layout.polaroid
    su, sv, fade, depth = SHADOW
    sigma, crease_depth = CREASE
    w = layout.size[0]
    for y, x in _bbox_pixels(list(corners), layout.size):
        px, py = x + 0.5, y + 0.5
        # how much of the pixel the map covers: the signed distance inside its nearest edge, the map grown half a
        # pixel so its edge pixels hold none of the stock map
        inside = min((px - a[0]) * n[0] + (py - a[1]) * n[1] for a, n in edges)
        k = max(0.0, min(1.0, inside + 1.0))
        u, v = layout.to_frame(px, py)
        # how much of it the polaroid leaves bare: its pixels are kept, its edge pixels too (grown half a pixel)
        bare = max(0.0, min(1.0, -min(u, pw - u, v, ph - v)))
        if k == 0 or bare == 0:
            continue
        dx, dy = px - tl[0], py - tl[1]
        s, t = (dx * eb[1] - dy * eb[0]) / det, (ea[0] * dy - ea[1] * dx) / det
        gx, gy = min(max(s * out_w - 0.5, 0), out_w - 1.001), min(max(t * out_h - 0.5, 0), out_h - 1.001)
        ix, iy = int(gx), int(gy)
        fx, fy = gx - ix, gy - iy
        r0, r1 = grey[iy], grey[iy + 1]
        g = ((r0[ix] * (1 - fx) + r0[ix + 1] * fx) * (1 - fy) + (r1[ix] * (1 - fx) + r1[ix + 1] * fx) * fy)
        g = curve(g)
        # the paper's folds
        for d in ((s - layout.creases[0]) * side_a, (t - layout.creases[1]) * side_b):
            if abs(d) < 5 * sigma:
                g *= 1 - crease_depth * math.exp(-0.5 * (d / sigma) ** 2)
        # the polaroid's shadow: its rectangle moved down and right, faded over `fade` px
        out_d = max(-(u - su), u - su - pw, -(v - sv), v - sv - ph, 0.0)
        if out_d < fade:
            g *= 1 - depth * (1 - out_d / fade) ** 2
        # an edge pixel: the map over the paper's border (not over what the stock map left in it)
        col = [g * k + c * (1 - k) for c in layout.map_paper]
        _blend(img, (y * w + x) * 4, col, bare)


# --------------------------------------------------------------------------- the markings

# What a zone's marker keeps of each channel of the map under it (stock's strokes are a multiply by pure red or blue).
ZONE_INKS: dict[str, tuple[float, float, float]] = {"red": (1.0, 0.0, 0.0), "blue": (0.0, 0.0, 1.0)}


def _map_edges(layout: CardLayout) -> list[tuple[Point, Point]]:
    """Each edge of the map as (a point on it, its inward unit normal): the corners run clockwise on screen."""
    corners = layout.map_corners
    out = []
    for a, b in zip(corners, corners[1:] + corners[:1]):
        n = math.hypot(b[0] - a[0], b[1] - a[1])
        out.append((a, (-(b[1] - a[1]) / n, (b[0] - a[0]) / n)))
    return out


def _on_map(edges: list[tuple[Point, Point]], layout: CardLayout, x: float, y: float) -> float:
    """How much of the pixel centred at (x, y) is the map, inside its border and off the polaroid (0-1)."""
    inside = min((x - a[0]) * n[0] + (y - a[1]) * n[1] for a, n in edges)
    u, v = layout.to_frame(x, y)
    bare = max(0.0, min(1.0, -min(u, layout.polaroid[0] - u, v, layout.polaroid[1] - v)))
    return max(0.0, min(1.0, inside + 0.5)) * bare


def _inside(p: Point, poly: list[Point]) -> bool:
    """Even-odd test of `p` against the polygon."""
    hit = False
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > p[1]) != (by > p[1]) and p[0] < ax + (p[1] - ay) * (bx - ax) / (by - ay):
            hit = not hit
    return hit


def draw_zones(layout: CardLayout, img: bytearray, view: MapView,
               zones: Sequence[tuple[Sequence[Point], str]]) -> None:
    """Draw each zone (its polygon in the view's units, and 'red' or 'blue') on the card's map as stock draws its
    zones: a marker outline with diagonal hatching inside, the map showing through. Only the map is drawn on: not its
    border, not the polaroid."""
    edges = _map_edges(layout)
    rise = math.radians(layout.hatch[0])
    nx, ny, spacing, pen = math.sin(rise), math.cos(rise), layout.hatch[1], layout.pen
    w = layout.size[0]
    for points, colour in zones:
        check(colour in ZONE_INKS, f"menu card zone: colour {colour!r} is not one of {', '.join(ZONE_INKS)}")
        check(len(points) >= 3, f"menu card zone: {len(points)} points are not a polygon")
        ink = ZONE_INKS[colour]
        poly = [view.to_card(layout, p) for p in points]
        segs = list(zip(poly, poly[1:] + poly[:1]))
        for y, x in _bbox_pixels(poly, layout.size, pad=math.ceil(pen) + 1):
            px, py = x + 0.5, y + 0.5
            room = _on_map(edges, layout, px, py)
            if room == 0:
                continue
            d = min(_dist((px, py), a, b) for a, b in segs)
            fill = max(0.0, min(1.0, (d if _inside((px, py), poly) else -d) + 0.5))
            proj = (px * nx + py * ny) % spacing      # hatch lines where proj is a multiple of the spacing
            hatch = max(0.0, min(1.0, pen + 0.5 - min(proj, spacing - proj))) * fill
            k = max(max(0.0, min(1.0, pen + 0.5 - d)), hatch) * room
            if k > 0:
                i = (y * w + x) * 4
                for c in range(3):
                    img[i + c] = round(img[i + c] * (1 - k * (1 - ink[c])))


def _sticker_pixels(st: Sticker, size: tuple[int, int]) -> list[tuple[int, int, float]]:
    """(x, y, coverage) of every stock pixel the sticker covers."""
    r = math.hypot(*st.size) / 2 + 1
    corners = [(st.centre[0] + dx, st.centre[1] + dy) for dx in (-r, r) for dy in (-r, r)]
    out = []
    for y, x in _bbox_pixels(corners, size, pad=0):
        c = st.coverage(x + 0.5, y + 0.5)
        if c > 0:
            out.append((x, y, c))
    return out


def draw_stickers(layout: CardLayout, img: bytearray, stock: bytes, view: MapView,
                  stickers: Sequence[tuple[str, Point]]) -> None:
    """Paste each named sticker of the stock card (its pixels, byte for byte) with its centre at a point in the view's
    units, moved by whole pixels. A sticker that would cross the map's border or the polaroid fails (CheckError)."""
    named = dict(layout.stickers)
    edges = _map_edges(layout)
    w, h = layout.size
    for name, at in stickers:
        check(name in named, f"menu card sticker {name!r}: the card has {', '.join(named) or 'none'}")
        st = named[name]
        cx, cy = view.to_card(layout, at)
        dx, dy = round(cx - st.centre[0]), round(cy - st.centre[1])
        pixels = _sticker_pixels(st, layout.size)
        off = [(x, y) for x, y, _ in pixels if not (0 <= x + dx < w and 0 <= y + dy < h)
               or _on_map(edges, layout, x + dx + 0.5, y + dy + 0.5) < 1]
        check(not off, f"menu card sticker {name} at {at}: {len(off)} of its pixels would leave the map or lie "
                       "under the polaroid (move it)")
        for x, y, c in pixels:
            i, j = ((y + dy) * w + x + dx) * 4, (y * w + x) * 4
            if c == 1:
                img[i:i + 4] = stock[j:j + 4]
            else:
                _blend(img, i, tuple(stock[j:j + 3]), c)


# --------------------------------------------------------------------------- the card

@dataclass(frozen=True)
class Card:
    """A built menu card: the TGV bytes the op ships as its MapTexture, and its RGBA for review."""
    width: int
    height: int
    rgba: bytes
    tgv: bytes
    cap: float          # the title's cap height, px

    def write_png(self, path: str) -> None:
        os.makedirs(os.path.dirname(os.path.abspath(path)), exist_ok=True)
        tgv.write_png(path, self.width, self.height, self.rgba)


def _read(rel: str) -> bytes:
    with open(extracted(rel), "rb") as f:
        return f.read()


def render(layout: CardLayout, stock: bytes, title: str, view: MapView | None = None,
           zones: Sequence[tuple[Sequence[Point], str]] = (), stickers: Sequence[tuple[str, Point]] = ()) -> Card:
    """The card drawn over `stock` (the stock card's TGV bytes, the layout's picture): the title in its caption and,
    with a view, that map in place of the stock map, with the zones and stickers on it (draw_zones, draw_stickers)."""
    check(view is not None or not (zones or stickers), "menu card: zones and stickers need a map view")
    got = hashlib.sha256(stock).hexdigest()
    check(got == layout.sha256, f"{layout.source}: SHA-256 {got[:16]}... is not the {layout.sha256[:16]}... "
                                "the card layout was measured on (a changed game picture: re-measure the layout)")
    hdr, pixels = tgv.decode_tgv(stock)
    check((hdr.width, hdr.height) == layout.size and not tgv.unwritable(hdr),
          f"{layout.source}: {hdr.fmt} {hdr.width}x{hdr.height} is not a card the writer reproduces at "
          f"{layout.size[0]}x{layout.size[1]}")
    img = bytearray(pixels)
    if view is not None:
        draw_map(layout, img, view)
        draw_zones(layout, img, view, zones)
        draw_stickers(layout, img, pixels, view, stickers)
    cap = draw_caption(layout, img, title)
    return Card(hdr.width, hdr.height, bytes(img), tgv.encode_tgv(hdr.width, hdr.height, bytes(img), hdr.fmt), cap)


def build_card(title: str, view: MapView | None = None, zones: Sequence[tuple[Sequence[Point], str]] = (),
               stickers: Sequence[tuple[str, Point]] = (), layout: CardLayout = SURVIVORS) -> Card:
    """The op's menu card, read from the user's extraction: `layout`'s stock card with `title` in its caption and,
    with `view`, that map in place of the stock one, marked with `zones` ((polygon, 'red' or 'blue')) and `stickers`
    ((name, centre)), both in the view's units (a cut's view: minimap px)."""
    return render(layout, _read(layout.source), title, view, zones, stickers)


def card_picture(title: str, cut=None, zones: Sequence[tuple[Sequence[Point], str]] = (),
                 stickers: Sequence[tuple[str, Point]] = (), layout: CardLayout = SURVIVORS):
    """An op's MapTexture as OpProfile.menu_art takes a generated picture (modkit.ops.profile.MenuPicture): at build
    time, build_card(title, cut_view(cut), zones, stickers) (no cut: the stock map kept), and its MANIFEST source line
    naming the stock card, the title and the map. Nothing is read until the build calls it."""
    def make(content=None) -> tuple[bytes, str]:
        view = cut_view(cut, layout) if cut is not None else None
        card = build_card(title, view, zones, stickers, layout)
        where = ""
        if view is not None:
            x0, y0, x1, y1 = view.box
            where = (f"; the map {paths.rel_source(extracted(view.picture))} x {x0:.1f}..{x1:.1f}, "
                     f"y {y0:.1f}..{y1:.1f} px; {len(zones)} zones, {len(stickers)} stickers")
        return card.tgv, (f"generated (modkit.ops.menuart: {paths.rel_source(extracted(layout.source))} titled "
                          f"{title!r}{where})")
    return make


# --------------------------------------------------------------------------- CLI

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m modkit.ops.menuart", description=__doc__.split("\n")[0])
    ap.add_argument("title")
    ap.add_argument("--out", required=True, help="folder for MapTexture.tgv and MapTexture.png")
    ap.add_argument("--map", help="a stock map of modkit.ops.maps (GEISA, TWIN_CITIES) whose Preview the card shows")
    ap.add_argument("--box", nargs=4, type=float, metavar=("X0", "Y0", "X1", "Y1"),
                    help="the box of the map to show, in its minimap px (a Cut's box)")
    args = ap.parse_args(argv)
    if args.box and not args.map:
        ap.error("--box needs --map")
    try:
        view = None
        if args.map:
            from modkit.ops import maps
            stock_map = getattr(maps, args.map, None)
            if not isinstance(stock_map, maps.StockMap):
                ap.error(f"--map {args.map}: not a StockMap of modkit.ops.maps")
            view = cut_view(maps.Cut(stock_map, tuple(args.box or (0, 0, *stock_map.minimap_px))))
        card = build_card(args.title, view)
        os.makedirs(args.out, exist_ok=True)
        with open(os.path.join(args.out, "MapTexture.tgv"), "wb") as f:
            f.write(card.tgv)
        card.write_png(os.path.join(args.out, "MapTexture.png"))
    except (paths.NotConfigured, CheckError, tgv.TgvError, OSError) as e:
        print(f"FAILED: {e}", file=sys.stderr)
        return 1
    print(f"MapTexture.tgv and .png ({card.width}x{card.height}, caps {card.cap:.1f} px"
          f"{', map ' + view.picture if view else ''}) -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
