"""Tests for modkit.ops.menuart: the caption on synthetic cards (no stock pixel survives in the repainted strip,
whatever the card under it), the title's checks, the map view's box, and the card built from Survivors' stock card,
with and without Twin Cities' map: it parses, keeps the stock card's size and format, and is deterministic."""
import math
import random
import unittest

from modkit.core import paths, tgv
from modkit.core.gates import CheckError
from modkit.ops import menuart
from modkit.ops.maps import TWIN_CITIES, Cut
from modkit.ops.menuart import SURVIVORS

TWIN_STRIKE_CUT = (0, 146, 216, 524)   # Twin Strike's cut (examples/twin-strike, twinstrike.map.CUT_PX)
CARD_DATA = paths.skip_unless_extracted("scenarios", "challenge_Survivors", "PC", "Texture")
PREVIEW_DATA = paths.skip_unless_extracted("basemaps", "_3x3_TwinCities", "PC", "Texture")


def noise_card(seed: int) -> bytearray:
    """An opaque card of SURVIVORS' size, every pixel random: stands in for any stock picture."""
    rng = random.Random(seed)
    w, h = SURVIVORS.size
    img = bytearray(rng.randbytes(w * h * 4))
    img[3::4] = b"\xff" * (w * h)
    return img


def pixel(img: bytes, x: int, y: int) -> bytes:
    i = (y * SURVIVORS.size[0] + x) * 4
    return bytes(img[i:i + 4])


def on_polaroid(x: int, y: int) -> bool:
    """The pixel's centre lies on the polaroid (its edge included)."""
    u, v = SURVIVORS.to_frame(x + 0.5, y + 0.5)
    return min(u, SURVIVORS.polaroid[0] - u, v, SURVIVORS.polaroid[1] - v) >= 0


class CaptionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cards = [noise_card(seed) for seed in (1, 2)]
        cls.caps = [menuart.draw_caption(SURVIVORS, card, "Twin Strike") for card in cls.cards]
        cls.repainted = SURVIVORS.repainted_pixels()

    def test_the_repainted_strip_holds_no_stock_pixel(self):
        """Two different cards under it, the same strip: nothing of the card shows through."""
        self.assertGreater(len(self.repainted), 7000)
        differ = [(x, y) for x, y in self.repainted if pixel(self.cards[0], x, y) != pixel(self.cards[1], x, y)]
        self.assertEqual(differ, [])

    def test_the_strip_is_paper_and_ink(self):
        """Every repainted pixel is a grey between the ink and the paper (with its grain), and both are there."""
        greys = set()
        for x, y in self.repainted:
            r, g, b, a = pixel(self.cards[0], x, y)
            self.assertEqual(a, 255)
            self.assertLessEqual(max(r, g, b) - min(r, g, b), 4, (x, y))
            greys.add(g)
        self.assertLessEqual(max(greys), SURVIVORS.paper[1] + 1)
        self.assertLessEqual(min(greys), SURVIVORS.ink[1] + 1)
        dark = sum(1 for x, y in self.repainted if pixel(self.cards[0], x, y)[1] < 100)
        self.assertGreater(dark, 400, "the title's ink")

    def test_nothing_else_changes(self):
        fresh = noise_card(1)
        w, h = SURVIVORS.size
        changed = {(i // 4 % w, i // 4 // w) for i in range(0, w * h * 4, 4) if fresh[i:i + 4] != self.cards[0][i:i + 4]}
        self.assertTrue(changed)
        self.assertEqual([p for p in changed if SURVIVORS.repainted(*p) == 0], [])

    def test_the_title_is_large_and_upper_cased(self):
        self.assertEqual(self.caps[0], self.caps[1])
        self.assertGreater(self.caps[0], 18)
        again = noise_card(1)
        menuart.draw_caption(SURVIVORS, again, "  TWIN   STRIKE ")
        self.assertEqual(again, self.cards[0])

    def test_titles_it_cannot_write_fail(self):
        for title, why in (("", "empty"), ("TWIN STRIKE?", "has no '?'"), ("Ä", "has no 'Ä'"),
                           ("OPERATION TWIN STRIKE NORTH", "too small to read")):
            with self.subTest(title=title), self.assertRaisesRegex(CheckError, why):
                menuart.draw_caption(SURVIVORS, noise_card(3), title)

    def test_every_glyph_stays_in_its_box(self):
        """Each glyph's strokes lie within its width and between the cap line and the baseline (a comma's tail
        and Q's tail may drop a little)."""
        for ch, (width, strokes) in menuart.STROKES.items():
            for stroke in strokes:
                for x, y in stroke:
                    self.assertTrue(-0.01 <= x <= width + 0.09 and -0.01 <= y <= 1.13, (ch, x, y))


class ViewBoxTest(unittest.TestCase):
    def test_holds_the_box_at_the_aspect_inside_the_picture(self):
        got = menuart.view_box((0, 292, 432, 1048), 1.0, (1536, 1536))
        self.assertEqual(got, (0, 292, 756, 1048))
        self.assertEqual(menuart.view_box((100, 100, 200, 120), 2.0, (1000, 1000)), (100, 85, 200, 135))

    def test_too_big_a_box_shrinks_into_the_picture(self):
        self.assertEqual(menuart.view_box((0, 0, 100, 400), 1.0, (300, 300)), (0, 0, 300, 300))


@CARD_DATA
class StockCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.stock = menuart._read(SURVIVORS.source)
        cls.card = menuart.build_card("TWIN STRIKE")

    def test_it_parses_with_the_stock_card_size_and_format(self):
        hdr, pixels = tgv.decode_tgv(self.card.tgv)
        stock_hdr, _ = tgv.decode_tgv(self.stock)
        fields = ("version", "flags", "width", "height", "width2", "height2", "mip_count", "fmt", "checksum",
                  "mip_offset")
        self.assertEqual([getattr(hdr, f) for f in fields], [getattr(stock_hdr, f) for f in fields])
        self.assertEqual(pixels, self.card.rgba)
        self.assertEqual(tgv.roundtrip(self.card.tgv), "")

    def test_the_caption_strip_holds_no_stock_pixel(self):
        """The strip is what draw_caption paints over any card; the stock's own caption was ink there."""
        other = noise_card(4)
        menuart.draw_caption(SURVIVORS, other, "TWIN STRIKE")
        repainted = SURVIVORS.repainted_pixels()
        self.assertEqual([p for p in repainted if pixel(self.card.rgba, *p) != pixel(other, *p)], [])
        _, stock = tgv.decode_tgv(self.stock)
        self.assertGreater(sum(1 for p in repainted if pixel(stock, *p)[1] < 80), 300, "the stock caption's ink")

    def test_the_strip_covers_the_stock_caption_and_stamp(self):
        """Read off the stock picture: every dark (the caption's ink) or blue (its stamp) pixel of the polaroid below
        its photo, a pixel or more inside the polaroid, is repainted whole."""
        _, stock = tgv.decode_tgv(self.stock)
        pw, ph = SURVIVORS.polaroid
        marked = []
        for y in range(150, 240):
            for x in range(0, 210):
                u, v = SURVIVORS.to_frame(x + 0.5, y + 0.5)
                r, g, b, _ = pixel(stock, x, y)
                if 1 <= u <= pw - 1 and 170 <= v <= ph - 1 and ((r + g + b) / 3 < 160 or b - r > 40):
                    marked.append((x, y))
        self.assertGreater(len(marked), 800)
        self.assertEqual([p for p in marked if SURVIVORS.repainted(*p) < 1], [])

    def test_the_rest_of_the_card_is_stock(self):
        _, stock = tgv.decode_tgv(self.stock)
        w, h = SURVIVORS.size
        changed = [(x, y) for y in range(h) for x in range(w) if pixel(stock, x, y) != pixel(self.card.rgba, x, y)]
        self.assertEqual([p for p in changed if SURVIVORS.repainted(*p) == 0], [])

    def test_it_is_deterministic(self):
        self.assertEqual(menuart.build_card("TWIN STRIKE").tgv, self.card.tgv)

    def test_another_stock_card_fails(self):
        with self.assertRaisesRegex(CheckError, "SHA-256"):
            menuart.render(SURVIVORS, tgv.encode_tgv(2, 1, bytes(8)), "TWIN STRIKE")


@CARD_DATA
@PREVIEW_DATA
class MapSwapTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = menuart.cut_view(Cut(TWIN_CITIES, TWIN_STRIKE_CUT))
        cls.card = menuart.build_card("TWIN STRIKE", cls.view)
        cls.plain = menuart.build_card("TWIN STRIKE")

    def test_the_view_holds_the_cut(self):
        self.assertEqual(self.view.picture, TWIN_CITIES.picture("Preview"))
        x0, y0, x1, y1 = self.view.box
        self.assertTrue(x0 <= 0 and y0 <= 292 and x1 >= 432 and y1 >= 1048, self.view.box)
        self.assertAlmostEqual((x1 - x0) / (y1 - y0), menuart.map_aspect(SURVIVORS), places=6)

    def test_it_parses_keeps_the_format_and_is_deterministic(self):
        hdr, pixels = tgv.decode_tgv(self.card.tgv)
        self.assertEqual((hdr.width, hdr.height, hdr.fmt), (*SURVIVORS.size, "A8B8G8R8_LIN"))
        self.assertEqual(tgv.unwritable(hdr), "")
        self.assertEqual(menuart.build_card("TWIN STRIKE", self.view).tgv, self.card.tgv)

    def test_the_map_changes_and_the_polaroid_and_border_stay(self):
        w, h = SURVIVORS.size
        changed = {(x, y) for y in range(h) for x in range(w)
                   if pixel(self.plain.rgba, x, y) != pixel(self.card.rgba, x, y)}
        self.assertGreater(len(changed), 200_000)
        self.assertEqual([p for p in changed if on_polaroid(*p)], [])
        for x, y in ((5, 300), (530, 300), (270, 540), (270, 10)):   # the paper's border, the margins
            self.assertNotIn((x, y), changed)
        for x, y in ((270, 300), (400, 100), (100, 450)):            # the map
            self.assertIn((x, y), changed)

    def test_the_map_is_grey(self):
        for x, y in ((270, 300), (400, 100), (100, 450), (480, 480)):
            r, g, b, a = pixel(self.card.rgba, x, y)
            self.assertEqual((r, a), (b, 255))
            self.assertEqual(r, g)


# Twin Strike's markings, in minimap px (examples/twin-strike, twinstrike.map): the Soviet deployment box SOV_DZ and
# the village's command zone VILLAGE_CZ (world units / 2,560); the star at the Soviet box's east end, the NATO badge
# on the village (POINTS["VILLAGE"]).
SOV_ZONE = [(40, 158), (210, 158), (210, 212), (40, 212)]
VILLAGE_ZONE = [(6.125, 331.603), (132.125, 331.603), (132.125, 421.603), (6.125, 421.603)]
ZONES = [(SOV_ZONE, "red"), (VILLAGE_ZONE, "blue")]
STICKERS = [("SOV", (179, 185)), ("NATO", (69, 377))]
VIEW = menuart.MapView("synthetic", (0, 0, 100, 100))   # the whole map is 100 x 100 units


def on_map(x: int, y: int) -> bool:
    """The pixel's centre lies on the map, less than half a pixel outside its edges, and off the polaroid."""
    px, py = x + 0.5, y + 0.5
    corners = SURVIVORS.map_corners
    for (ax, ay), (bx, by) in zip(corners, corners[1:] + corners[:1]):   # clockwise on screen: inside is right
        if ((bx - ax) * (py - ay) - (by - ay) * (px - ax)) / math.hypot(bx - ax, by - ay) <= -0.5:
            return False
    u, v = SURVIVORS.to_frame(px, py)
    return min(u, SURVIVORS.polaroid[0] - u, v, SURVIVORS.polaroid[1] - v) < 0


def changed_pixels(a: bytes, b: bytes) -> list[tuple[int, int]]:
    w = SURVIVORS.size[0]
    return [(i // 4 % w, i // 4 // w) for i in range(0, len(a), 4) if a[i:i + 4] != b[i:i + 4]]


def grey_card(level: int) -> bytearray:
    img = noise_card(0)
    n = len(img) // 4
    img[0::4], img[1::4], img[2::4] = bytes([level]) * n, bytes([level]) * n, bytes([level]) * n
    return img


class MarkingsTest(unittest.TestCase):
    """Zones and stickers on synthetic cards: no extraction needed."""

    def test_the_view_maps_its_box_onto_the_map(self):
        for p, corner in zip(((0, 0), (100, 0), (0, 100)), (0, 1, 3)):
            got = VIEW.to_card(SURVIVORS, p)
            self.assertAlmostEqual(got[0], SURVIVORS.map_corners[corner][0], places=9)
            self.assertAlmostEqual(got[1], SURVIVORS.map_corners[corner][1], places=9)

    def test_zones_draw_inside_the_map_only(self):
        """A zone larger than the whole map: every pixel it changes is map, off the polaroid; the border, the
        polaroid and the margins stay. The marker keeps its own channel and darkens the others."""
        for colour, kept in (("red", 0), ("blue", 2)):
            before, after = noise_card(5), noise_card(5)
            menuart.draw_zones(SURVIVORS, after, VIEW, [([(-20, -20), (120, -20), (120, 120), (-20, 120)], colour)])
            changed = changed_pixels(before, after)
            self.assertGreater(len(changed), 1000)
            self.assertEqual([p for p in changed if not on_map(*p)], [])
            for x, y in changed:
                old, new = pixel(before, x, y), pixel(after, x, y)
                self.assertEqual(new[kept], old[kept])
                self.assertTrue(all(new[c] <= old[c] for c in range(3)))

    def test_a_zone_is_an_outline_and_hatching(self):
        img = grey_card(0x80)
        menuart.draw_zones(SURVIVORS, img, VIEW, [([(50, 50), (90, 50), (90, 90), (50, 90)], "red")])
        x0, y0 = (round(c) for c in VIEW.to_card(SURVIVORS, (50, 70)))   # on the west outline
        self.assertEqual(pixel(img, x0, y0)[:3], b"\x80\x00\x00")
        inside = [pixel(img, x, y0)[1] for x in range(x0 + 8, x0 + 180)]
        self.assertIn(0, inside)                                           # the hatching
        self.assertIn(0x80, inside)                                        # and the map between its lines
        self.assertEqual(pixel(img, x0 - 10, y0)[:3], b"\x80\x80\x80")     # nothing outside the outline

    def test_stickers_are_byte_equal_crops_of_the_stock_card(self):
        stock, img = noise_card(7), noise_card(8)
        view = menuart.MapView("synthetic", (0, 0, 492, 492))
        named = dict(SURVIVORS.stickers)
        for name, at in (("SOV", (300, 300)), ("NATO", (400, 150))):
            menuart.draw_stickers(SURVIVORS, img, bytes(stock), view, [(name, at)])
            st = named[name]
            cx, cy = view.to_card(SURVIVORS, at)
            dx, dy = round(cx - st.centre[0]), round(cy - st.centre[1])
            whole = [(x, y) for x, y, c in menuart._sticker_pixels(st, SURVIVORS.size) if c == 1]
            self.assertGreater(len(whole), 3500)
            self.assertEqual([(x, y) for x, y in whole if pixel(img, x + dx, y + dy) != pixel(stock, x, y)], [])

    def test_a_sticker_off_the_map_or_on_the_polaroid_fails(self):
        for at in ((5, 5), (30, 30), (99, 50)):   # under the polaroid, across its edge, across the map's
            with self.subTest(at=at), self.assertRaisesRegex(CheckError, "leave the map or lie under the polaroid"):
                menuart.draw_stickers(SURVIVORS, noise_card(9), bytes(noise_card(10)), VIEW, [("SOV", at)])

    def test_bad_markings_fail(self):
        with self.assertRaisesRegex(CheckError, "colour 'green'"):
            menuart.draw_zones(SURVIVORS, noise_card(1), VIEW, [(SOV_ZONE, "green")])
        with self.assertRaisesRegex(CheckError, "2 points"):
            menuart.draw_zones(SURVIVORS, noise_card(1), VIEW, [([(1, 1), (2, 2)], "red")])
        with self.assertRaisesRegex(CheckError, "sticker 'UK'"):
            menuart.draw_stickers(SURVIVORS, noise_card(1), bytes(noise_card(2)), VIEW, [("UK", (50, 50))])

    def test_markings_need_a_view(self):
        with self.assertRaisesRegex(CheckError, "need a map view"):
            menuart.render(SURVIVORS, b"", "X", zones=ZONES)


@CARD_DATA
@PREVIEW_DATA
class MarkedCardTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.view = menuart.cut_view(Cut(TWIN_CITIES, TWIN_STRIKE_CUT))
        cls.mapped = menuart.build_card("TWIN STRIKE", cls.view)
        cls.card = menuart.build_card("TWIN STRIKE", cls.view, zones=ZONES, stickers=STICKERS)
        _, cls.stock = tgv.decode_tgv(menuart._read(SURVIVORS.source))

    def test_no_markings_is_the_plain_map_card(self):
        self.assertEqual(menuart.build_card("TWIN STRIKE", self.view, zones=(), stickers=()).tgv, self.mapped.tgv)

    def test_it_parses_and_is_deterministic(self):
        hdr, pixels = tgv.decode_tgv(self.card.tgv)
        self.assertEqual((hdr.width, hdr.height, hdr.fmt, tgv.unwritable(hdr)), (*SURVIVORS.size, "A8B8G8R8_LIN", ""))
        self.assertEqual(pixels, self.card.rgba)
        again = menuart.build_card("TWIN STRIKE", self.view, zones=ZONES, stickers=STICKERS)
        self.assertEqual(again.tgv, self.card.tgv)

    def test_the_markings_lie_on_the_map(self):
        changed = changed_pixels(self.mapped.rgba, self.card.rgba)
        self.assertGreater(len(changed), 10_000)
        self.assertEqual([p for p in changed if not on_map(*p)], [])

    def test_the_stickers_are_the_stock_cards_own_pixels(self):
        named = dict(SURVIVORS.stickers)
        for name, at in STICKERS:
            st = named[name]
            cx, cy = self.view.to_card(SURVIVORS, at)
            dx, dy = round(cx - st.centre[0]), round(cy - st.centre[1])
            whole = [(x, y) for x, y, c in menuart._sticker_pixels(st, SURVIVORS.size) if c == 1]
            self.assertEqual([p for p in whole if pixel(self.card.rgba, p[0] + dx, p[1] + dy) != pixel(self.stock, *p)],
                             [], name)
            # the crop is the sticker: its rim (the pixels within 3 px of its edge) is the sticker's white paper,
            # not the stock map round it
            rim = [pixel(self.stock, x, y) for x, y in whole
                   if min(st.coverage(x + 0.5 + ox, y + 0.5 + oy) for ox, oy in ((3, 0), (-3, 0), (0, 3), (0, -3))) < 1]
            self.assertGreater(sum(1 for r, g, b, _ in rim if min(r, g, b) > 180) / len(rim), 0.9, name)


if __name__ == "__main__":
    unittest.main()
