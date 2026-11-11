"""Tests for modkit.ops.menuart: the caption on synthetic cards (no stock pixel survives in the repainted strip,
whatever the card under it), the title's checks, the map view's box, and the card built from Survivors' stock card,
with and without Twin Cities' map: it parses, keeps the stock card's size and format, and is deterministic."""
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


if __name__ == "__main__":
    unittest.main()
