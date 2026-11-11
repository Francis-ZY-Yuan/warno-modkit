"""Tests for modkit.ops.storyboard: the spec schema and its JSON paths, the text, the frame (viewBox and crop), the
phase attributes, the zones drawn from a layout's files, the page's constraints, the CLI's FAILED lines and exit
codes, the default output folder, and (with the extraction) the sample spec on Twin Cities' stock small layout.

The synthetic map is a 64 x 64 minimap with its 128 x 128 Preview, stubbed (no TGV), over a layout written into a
temporary extraction with the toolkit's own zone builders."""
import contextlib
import copy
import io
import json
import os
import re
import struct
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from modkit.core import paths
from modkit.core.ndfbin import Value
from modkit.ops import storyboard as sb
from modkit.ops.graph import Str, build_graph, encode
from modkit.ops.maps import WORLD_PER_MINIMAP_PX
from modkit.ops.zones import playable_zone_graph, rect_polygon, zone_areas_graph

SAMPLE = Path(__file__).resolve().parent / "storyboard_sample.json"
MAP, LAYOUT = "_1x1_Tiny", "tiny_op/Tiny_Details"
PLAYABLE, CZ_A, CZ_B = (8, 16, 56, 60), (10, 20, 30, 40), (34, 20, 54, 40)
DZ_0, DZ_1 = (8, 16, 56, 19), (8, 56, 56, 60)


def spec(**over) -> dict:
    s = {
        "version": 1,
        "title": "Operation Test",
        "styles": {"sov": "#e2543e", "nato": "#4e92e3"},
        "map": {"name": MAP, "layout": LAYOUT, "deployments": {"0": {"style": "sov", "label": "Soviet deployment"}},
                "zone_names": {"CZ_A": "Village"}},
        "phases": [{"id": "1", "name": "Assault"}, {"id": "2", "name": "Hold"}],
        "marks": [
            {"kind": "ring", "style": "sov", "at": [20, 30], "r": 5, "phases": ["1"], "title": "the fire"},
            {"kind": "units", "style": "nato", "at": [30, 30], "count": 3},
        ],
    }
    s.update(over)
    return s


def zone(name: str, box, **kw) -> sb.Zone:
    return sb.Zone(name, tuple(rect_polygon(box)), **kw)


TINY = sb.Layout(tuple(rect_polygon(PLAYABLE)), (zone("CZ_A", CZ_A, points=2), zone("CZ_B", CZ_B, points=1)),
                 (zone("DZ_0", DZ_0, alliance=0), zone("DZ_1", DZ_1, alliance=1)))


def page(s: dict | None = None, box=PLAYABLE) -> str:
    s = s or spec()
    sb.validate(s)
    return sb.render_page(s, TINY, box)


def write_layout(root: Path) -> None:
    """The tiny layout's out/ files, in world units, as the stock files hold them."""
    out = root.joinpath(*LAYOUT.split("/"), "out")
    out.mkdir(parents=True)

    def world(box):
        return [(x * WORLD_PER_MINIMAP_PX, y * WORLD_PER_MINIMAP_PX) for x, y in rect_polygon(box)]

    def areas(*rows):
        return encode(build_graph(zone_areas_graph([(world(box), (0.0, 0.0, 0.0), cls, props, None)
                                                    for box, cls, props in rows]), []), "zones")
    (out / "PlayableZone.ndfbin").write_bytes(
        encode(build_graph(playable_zone_graph(world(PLAYABLE), (0.0, 0.0, 0.0)), []), "PlayableZone"))
    cp = "TGameDesignAddOn_CommandPoints"
    (out / "CommandZone.ndfbin").write_bytes(areas(
        (CZ_A, cp, [("Name", Str("CZ_A")), ("Ranking", Str("CommandPoints")), ("Points", Value(0x02, 2))]),
        (CZ_B, cp, [("Name", Str("CZ_B")), ("Ranking", Str("CommandPoints")), ("Points", Value(0x02, 1))])))
    dz = "TGameDesignAddOn_DeploymentZone"
    (out / "DeploymentZone.ndfbin").write_bytes(areas(
        (DZ_0, dz, [("Name", Str("DZ_0")), ("Ranking", Str("DeploymentZone"))]),
        (DZ_1, dz, [("Name", Str("DZ_1")), ("Ranking", Str("DeploymentZone")), ("AllianceNum", Value(0x02, 1))])))


def stub_picture(self, map_name: str, kind: str) -> sb.Picture:
    """A 64 x 64 minimap, or its 128 x 128 Preview: a gradient."""
    n = 64 if kind == "Minimap" else 128
    return sb.Picture(n, n, bytes(v for y in range(n) for x in range(n) for v in (x * 255 // n, y * 255 // n, 90)))


def png_size(path) -> tuple[int, int]:
    data = Path(path).read_bytes()
    assert data.startswith(b"\x89PNG\r\n\x1a\n")
    return struct.unpack(">II", data[16:24])


def mark_group(html: str, title: str) -> str:
    """The <g ...> opening tag of the mark whose hover title is `title`."""
    m = re.search(r"(<g [^>]*>)(?:(?!<g ).)*?<title>" + re.escape(title) + "</title>", html)
    assert m, title
    return m.group(1)


class ValidationTest(unittest.TestCase):
    def fails(self, s, where: str, why: str = ""):
        with self.assertRaises(sb.SpecError) as cm:
            sb.validate(s)
        msg = str(cm.exception)
        self.assertTrue(msg.startswith(where + ": "), msg)
        self.assertIn(why, msg)

    def test_a_good_spec_and_the_sample_pass(self):
        sb.validate(spec())
        sb.validate(sb.load_spec(SAMPLE))

    def test_unknown_keys_fail_with_their_path(self):
        self.fails(spec(colour="red"), "$.colour", "unknown key")
        s = spec()
        s["map"]["zoom"] = 2
        self.fails(s, "$.map.zoom", "unknown key")
        s = spec()
        s["marks"][0]["radius"] = 5
        self.fails(s, "$.marks[0].radius", "unknown key")
        s = spec()
        s["marks"][1]["dashed"] = True        # a units mark has no dash
        self.fails(s, "$.marks[1].dashed", "unknown key")
        s = spec(sections=[{"heading": "x", "tables": [{"columns": ["a"], "rows": [["b"]], "caption": "c"}]}])
        self.fails(s, "$.sections[0].tables[0].caption", "unknown key")
        s = spec()
        s["map"]["zone_names"]["Auto Name"] = 3
        self.fails(s, '$.map.zone_names["Auto Name"]', "expected a string")

    def test_bad_kinds_fail_with_their_path(self):
        s = spec()
        s["marks"][1]["kind"] = "blob"
        self.fails(s, "$.marks[1].kind", "expected one of arrow, ring, units, label, arc, burst")
        del s["marks"][1]["kind"]
        self.fails(s, "$.marks[1].kind")
        s = spec(sections=[{"heading": "x", "tables": [{"columns": ["a", "b"], "rows": [["P1", {"mark": "done",
                                                                                                "text": "x"}]]}]}])
        self.fails(s, "$.sections[0].tables[0].rows[0][1].mark", "expected one of ok, half, open")

    def test_bad_values_fail_with_their_path(self):
        self.fails(spec(version=2), "$.version")
        self.fails(spec(styles={"sov": "red", "nato": "#4e92e3"}), "$.styles.sov", "#rrggbb")
        self.fails(spec(styles={"sov": "#e2543e", "nato": "#4e92e3", "none": "#000000"}), "$.styles.none", "not 'none'")
        self.fails(spec(lede="the {nuke:strike}"), "$.lede", "names no style")
        self.fails(spec(start_phase="9"), "$.start_phase", "names no phase")
        self.fails(spec(phases=[{"id": "1", "name": "a"}, {"id": "1", "name": "b"}]), "$.phases[1].id", "twice")
        self.fails(spec(phases=[{"id": "all", "name": "a"}]), "$.phases[0].id")
        s = spec()
        del s["map"]["layout"]
        self.fails(s, "$.map", "missing key 'layout'")
        s = spec()
        for layout in ("tiny_op/..", "/abs", "tiny_op\\Tiny_Details"):
            s["map"]["layout"] = layout
            self.fails(s, "$.map.layout")
        s = spec()
        s["map"]["deployments"] = {"north": {"style": "sov", "label": "x"}}
        self.fails(s, "$.map.deployments.north", "alliance number")
        s = spec()
        s["marks"][0]["style"] = "fires"
        self.fails(s, "$.marks[0].style", "names no style")
        s = spec()
        s["marks"][0]["phases"] = ["3"]
        self.fails(s, "$.marks[0].phases[0]", "names no phase")
        s = spec()
        s["marks"][0]["at"] = [20]
        self.fails(s, "$.marks[0].at", "point")
        s = spec(sections=[{"heading": "x", "tables": [{"columns": ["a", "b"], "rows": [["only one"]]}]}])
        self.fails(s, "$.sections[0].tables[0].rows[0]", "expected 2 cells")
        self.fails(spec(chips=[["Map", "{x:y}"]]), "$.chips[0][1]", "names no style")
        self.fails([], "$", "expected an object")


def own_zones(**map_over) -> dict:
    """The tiny spec on a cut: its own command zones (no zone_names) and, optionally, deployment areas."""
    s = spec()
    del s["map"]["zone_names"]
    s["map"]["command_zones"] = [{"stock": "CZ_B", "name": "Ridge"},
                                 {"name": "Village", "area": [[12, 22], [20, 22], [20, 30]], "points": 2}]
    s["map"].update(map_over)
    return s


class OwnZonesValidationTest(unittest.TestCase):
    def fails(self, s, where: str, why: str = ""):
        with self.assertRaises(sb.SpecError) as cm:
            sb.validate(s)
        msg = str(cm.exception)
        self.assertTrue(msg.startswith(where + ": "), msg)
        self.assertIn(why, msg)

    def bad_item(self, item, where: str, why: str = ""):
        s = own_zones()
        s["map"]["command_zones"].append(item)
        self.fails(s, where, why)

    def test_good_own_zones_pass(self):
        sb.validate(own_zones())
        sb.validate(own_zones(deployments={"0": {"style": "sov", "label": "x", "area": [[1, 1], [5, 1], [5, 4]]}}))

    def test_zone_names_with_command_zones_fails_at_zone_names(self):
        self.fails(own_zones(zone_names={"CZ_A": "Village"}), "$.map.zone_names", "command_zones")

    def test_bad_items_fail_at_their_paths(self):
        area = [[1, 1], [5, 1], [5, 4]]
        self.bad_item({"stock": "CZ_A", "area": area}, "$.map.command_zones[2].area", "unknown key")
        self.bad_item({"stock": "CZ_A", "points": 1}, "$.map.command_zones[2].points", "unknown key")
        self.bad_item({"name": "x"}, "$.map.command_zones[2]")
        self.bad_item(5, "$.map.command_zones[2]")
        self.bad_item({"name": "x", "area": area[:2], "points": 1}, "$.map.command_zones[2].area", "at least 3")
        self.bad_item({"name": "x", "area": [[1, 1], [5, "a"], [5, 4]], "points": 1},
                      "$.map.command_zones[2].area[1][1]", "number")
        self.bad_item({"name": "x", "area": area, "points": -1}, "$.map.command_zones[2].points", "0 or more")
        self.bad_item({"name": "x", "area": area}, "$.map.command_zones[2]", "missing key 'points'")
        s = own_zones()
        s["map"]["command_zones"] = []
        self.fails(s, "$.map.command_zones", "at least 1")

    def test_a_deployment_area_needs_three_points(self):
        s = own_zones(deployments={"0": {"style": "sov", "label": "x", "area": [[1, 1], [5, 1]]}})
        self.fails(s, '$.map.deployments["0"].area', "at least 3")


class ScaleTest(unittest.TestCase):
    def test_the_scale_follows_the_crop_and_mark_scale_overrides_it(self):
        s = spec()
        self.assertEqual(sb.map_scale(s, (0, 0, 432, 622)), 1)
        self.assertEqual(sb.map_scale(s, (0, 146, 216, 524)), 0.608)
        s["map"]["mark_scale"] = 1.5
        self.assertEqual(sb.map_scale(s, (0, 146, 216, 524)), 1.5)
        s["map"]["mark_scale"] = 0
        with self.assertRaises(sb.SpecError) as cm:
            sb.validate(s)
        self.assertTrue(str(cm.exception).startswith("$.map.mark_scale: "))

    def test_the_svg_carries_s_and_the_map_css_uses_it(self):
        html = page(box=(0, 146, 216, 524))
        self.assertIn('style="--s: 0.608"', html)
        self.assertIn("stroke-width: calc(6 * var(--s))", html)
        self.assertIn("font: 500 calc(11.5px * var(--s))", html)
        self.assertIn('style="--s: 1"', page(box=(0, 0, 432, 622)))

    def test_drawn_shapes_follow_s(self):
        mark = {"kind": "units", "style": "nato", "at": [30, 30], "count": 1}
        self.assertIn('width="10" height="8"', sb.mark_svg(mark, None))
        self.assertIn('width="5" height="4"', sb.mark_svg(mark, None, 0.5))
        s = own_zones(mark_scale=0.5)
        self.assertIn('width="5" height="4"', page(s))
        self.assertIn('y="27">Ridge', page(s))      # the zone's top (20) plus 14 * s


class OwnZonesTest(unittest.TestCase):
    def test_a_custom_command_zone_has_its_outline_label_and_title(self):
        html = page(own_zones())
        self.assertIn('<g class="cz"><polygon points="12,22 20,22 20,30 12,22"/>', html)
        self.assertIn('>Village · 2</text><title>Command zone Village: 2 points</title>', html)

    def test_a_stock_subset_renames_and_leaves_the_unlisted_zone_out(self):
        html = page(own_zones())
        self.assertIn('>Ridge · 1</text><title>Command zone CZ_B (Ridge): 1 points</title>', html)
        self.assertNotIn("CZ_A", html)
        self.assertEqual(html.count('<g class="cz">'), 2)
        self.assertLess(html.index("Ridge"), html.index("Village"))     # in the spec's order

    def test_a_stock_zone_without_a_name_keeps_its_own(self):
        s = own_zones()
        s["map"]["command_zones"] = [{"stock": "CZ_A"}]
        self.assertIn('>CZ_A · 2</text><title>Command zone CZ_A: 2 points</title>', page(s))

    def test_a_deployment_area_replaces_the_stock_polygon(self):
        html = page(own_zones(deployments={"0": {"style": "sov", "label": "Soviet start",
                                                 "area": [[1, 1], [9, 1], [9, 4]]}}))
        self.assertIn('<g class="dep st-sov"><polygon points="1,1 9,1 9,4 1,1"/>', html)
        self.assertIn("<title>Deployment zone, alliance 0: Soviet start</title>", html)
        self.assertNotIn("8,16 56,16 56,19", html)          # the stock alliance 0 polygon
        self.assertIn("8,56 56,56 56,60", html)             # alliance 1, not in deployments, is as before

    def test_an_area_alliance_with_no_stock_zone_is_drawn(self):
        html = page(own_zones(deployments={"7": {"style": "nato", "label": "Allied start",
                                                 "area": [[1, 1], [9, 1], [9, 4], [1, 4]]}}))
        self.assertIn('<g class="dep st-nato"><polygon points="1,1 9,1 9,4 1,4 1,1"/>', html)
        self.assertIn("<title>Deployment zone, alliance 7: Allied start</title>", html)
        self.assertIn("8,16 56,16 56,19", html)             # the stock zones stay

    def test_generate_rejects_an_unknown_stock_name_at_its_path(self):
        s = own_zones()
        s["map"]["command_zones"][0]["stock"] = "CZ_Z"
        with tempfile.TemporaryDirectory() as tmp:
            with mock.patch.object(sb.StockSource, "layout", lambda self, rel: TINY):
                with self.assertRaises(sb.SpecError) as cm:
                    sb.generate(s, Path(tmp) / "out")
            self.assertFalse((Path(tmp) / "out").exists())
        self.assertTrue(str(cm.exception).startswith("$.map.command_zones[0].stock: "), str(cm.exception))


class TextTest(unittest.TestCase):
    def test_plain_text_is_escaped(self):
        self.assertEqual(sb.text_html('<b>&"x"'), "&lt;b&gt;&amp;&quot;x&quot;")
        self.assertEqual(sb.text_html("a {b and ** c"), "a {b and ** c")

    def test_style_spans_and_bold(self):
        self.assertEqual(sb.text_html("{sov:you} and **bold**"), '<span class="tx tx-sov">you</span> and <b>bold</b>')
        self.assertEqual(sb.text_html("**{nato:NATO}**"), '<b><span class="tx tx-nato">NATO</span></b>')
        self.assertEqual(sb.text_html("{sov:<x> **y**}"), '<span class="tx tx-sov">&lt;x&gt; <b>y</b></span>')

    def test_the_page_renders_prose_and_keeps_map_text_plain(self):
        s = spec(lede="{sov:you} <script>", footer=["**done**"])
        s["marks"].append({"kind": "label", "style": "nato", "at": [40, 50], "text": "{sov:x} <y>"})
        html = page(s)
        self.assertIn('<p class="lede"><span class="tx tx-sov">you</span> &lt;script&gt;</p>', html)
        self.assertIn("<div><b>done</b></div>", html)
        self.assertIn('<text class="sm" x="40" y="50">{sov:x} &lt;y&gt;</text>', html)
        self.assertRegex(html, r"\.tx-sov \{ color: #[0-9a-f]{6}; \}")
        self.assertIn("<title>Operation Test</title>", page(spec(title="Operation Test")))
        self.assertIn("<title>A &amp; B</title>", page(spec(title="A & B")))


class FrameTest(unittest.TestCase):
    def test_the_crop_box(self):
        self.assertEqual(sb.crop_box("playable", TINY, 64, 64), PLAYABLE)
        self.assertEqual(sb.crop_box("full", TINY, 64, 64), (0, 0, 64, 64))
        self.assertEqual(sb.crop_box([4.4, 5.6, 70, 30], TINY, 64, 64), (4, 6, 64, 30))   # rounded, clamped
        with self.assertRaisesRegex(sb.SpecError, r"^\$\.map\.crop: "):
            sb.crop_box([70, 0, 90, 10], TINY, 64, 64)

    def test_the_viewbox_is_the_crop_and_both_pictures_fill_it(self):
        html = page(box=PLAYABLE)
        self.assertIn('viewBox="8 16 48 44"', html)
        at = 'x="8" y="16" width="48" height="44"'
        self.assertIn(f'<image id="base-mini" class="base" href="minimap.png" {at}', html)
        self.assertIn(f'<image id="base-sat" class="base" href="satellite.png" {at}', html)

    def test_marks_keep_their_full_map_coordinates_under_any_crop(self):
        for box in (PLAYABLE, (0, 0, 64, 64)):
            self.assertIn('<circle class="ring" cx="20" cy="30" r="5"/>', page(box=box))

    def test_the_picture_switch(self):
        html = page()
        self.assertIn('data-pic="minimap"', html)
        self.assertIn('id="b-mini" data-pic="minimap" aria-pressed="true"', html)
        self.assertIn('id="b-sat" data-pic="satellite" aria-pressed="false"', html)
        s = spec()
        s["map"]["default_picture"] = "satellite"
        self.assertIn('id="b-sat" data-pic="satellite" aria-pressed="true"', page(s))


class PhaseTest(unittest.TestCase):
    def test_marks_list_their_phases_and_the_start_phase_shows(self):
        s = spec(start_phase="2")
        s["marks"].append({"kind": "arrow", "style": "nato", "points": [[1, 2], [3, 4]], "phases": ["1", "2"],
                           "title": "both"})
        s["marks"].append({"kind": "burst", "style": "sov", "at": [5, 6], "phases": [], "title": "always"})
        html = page(s)
        self.assertEqual(mark_group(html, "the fire"), '<g class="mark k-ring st-sov off" data-ph="1">')
        self.assertEqual(mark_group(html, "both"), '<g class="mark k-arrow st-nato" data-ph="1,2">')
        self.assertEqual(mark_group(html, "always"), '<g class="mark k-burst st-sov">')
        self.assertIn('<g class="mark k-units st-nato">', html)          # no phases: every phase
        self.assertIn('data-p="2" aria-current="true"', html)
        self.assertIn('data-p="1" aria-current="false"', html)
        self.assertIn('id="v-all" aria-pressed="false">Show every phase</button>', html)
        self.assertIn('show("2");', html)

    def test_the_first_phase_starts_by_default_and_arrow_keys_step(self):
        html = page()
        self.assertIn('data-p="1" aria-current="true"', html)
        self.assertEqual(mark_group(html, "the fire"), '<g class="mark k-ring st-sov" data-ph="1">')
        for key in ("ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"):
            self.assertIn(f"'{key}'", html)

    def test_no_phases_no_stepper(self):
        s = spec(phases=[])
        s["marks"][0]["phases"] = []
        html = page(s)
        self.assertIn('class="board solo"', html)
        self.assertNotIn('class="phase"', html)
        self.assertIn('show("all");', html)


class ZoneTest(unittest.TestCase):
    def test_the_layout_is_read_from_its_files_in_minimap_px(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MODKIT_EXTRACTED": tmp}):
            write_layout(Path(tmp))
            got = sb.StockSource().layout(LAYOUT)
        self.assertEqual(got, TINY)

    def test_zones_are_drawn_exact_with_names_points_and_alliance_styles(self):
        html = page()
        self.assertIn('<g class="cz"><polygon points="10,20 30,20 30,40 10,40 10,20"/>', html)
        self.assertIn('>Village · 2</text><title>Command zone CZ_A (Village): 2 points</title>', html)
        self.assertIn('>CZ_B · 1</text><title>Command zone CZ_B: 1 points</title>', html)
        self.assertIn('<g class="dep st-sov"><polygon points="8,16 56,16 56,19 8,19 8,16"/>', html)
        self.assertIn('>Soviet deployment</text>', html)
        self.assertIn('<g class="dep st-none">', html)        # alliance 1 has no deployments entry
        self.assertIn('>Deployment · alliance 1</text>', html)
        self.assertIn("stroke-dasharray: calc(7 * var(--s)) calc(5 * var(--s))", html)          # deployment zones are dashed


class PageTest(unittest.TestCase):
    def test_one_dark_page_with_google_fonts_only(self):
        s = sb.load_spec(SAMPLE)
        sb.validate(s)
        html = sb.render_page(s, TINY, PLAYABLE)
        self.assertLess(len(html.encode()), sb.MAX_PAGE)
        self.assertIn("color-scheme: dark;", html)
        self.assertIn('<meta name="claude:viewport-fit-sides" content="cover">', html)
        self.assertIn("padding-left: max(16px, env(safe-area-inset-left, 0px)); "
                      "padding-right: max(16px, env(safe-area-inset-right, 0px));", html)
        self.assertIn("<title>Storyboard sample</title>", html)
        refs = re.findall(r'(?:href|src)="([^"]*)"', html)
        external = [r for r in refs if "//" in r]
        self.assertTrue(external)
        self.assertTrue(all(r.startswith(("https://fonts.googleapis.com", "https://fonts.gstatic.com"))
                            for r in external), external)
        self.assertEqual(sorted(set(refs) - set(external)), ["minimap.png", "satellite.png"])
        self.assertEqual(re.findall(r"url\(([^)]*)\)", html), ["#ah-sov", "#ah-nato"])
        self.assertNotIn("<script src", html)
        self.assertNotIn("@import", html)

    def test_mark_cells_tables_and_the_order_of_battle(self):
        html = sb.render_page(sb.load_spec(SAMPLE), TINY, PLAYABLE)
        for mark, text in (("ok", "tested"), ("half", "built"), ("open", "open")):
            self.assertIn(f'<td><span class="mk {mark}">{text}</span></td>', html)
        self.assertIn('<td class="n">31</td>', html)
        self.assertIn('<div class="side st-sov"><h3>Player <span class="tag">Alliance 1</span></h3>', html)
        self.assertIn('<li><span class="q">10</span><span class="nm">T-80BV <span class="key">T80BV_SOV</span>'
                      '</span></li>', html)
        self.assertIn('<li><span class="q">2</span><span class="nm">Scouts</span></li>', html)
        self.assertIn('<div class="gn">Stock units only.</div>', html)


class CliTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.extraction = self.root / "extracted"
        self.extraction.mkdir()
        self.spec_path = self.root / "op.json"
        self.spec_path.write_text(json.dumps(spec()), encoding="utf-8")
        self.out = self.root / "out"

    def run_main(self, *argv: str, pictures: bool = True, **env: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        env = {"MODKIT_EXTRACTED": str(self.extraction), **env}
        with contextlib.ExitStack() as stack:
            stack.enter_context(mock.patch.dict(os.environ, env))
            if pictures:
                stack.enter_context(mock.patch.object(sb.StockSource, "picture", stub_picture))
            stack.enter_context(contextlib.redirect_stdout(out))
            stack.enter_context(contextlib.redirect_stderr(err))
            code = sb.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def failed_line(self, err: str) -> str:
        (line,) = err.splitlines()
        self.assertTrue(line.startswith("FAILED: "), line)
        self.assertNotIn("Traceback", err)
        self.assertFalse(self.out.exists(), "nothing is written on a failure")
        return line

    def test_success_prints_a_line_per_file_then_the_publish_line(self):
        write_layout(self.extraction)
        code, out, err = self.run_main(str(self.spec_path), "--out", str(self.out))
        self.assertEqual((code, err), (0, ""))
        lines = out.splitlines()
        self.assertEqual(len(lines), 4, out)
        where = {name: (self.out / name).absolute().as_posix() for name in (sb.PAGE, sb.MINIMAP, sb.SATELLITE)}
        for line, name in zip(lines, (sb.PAGE, sb.MINIMAP, sb.SATELLITE)):
            self.assertTrue(line.startswith(where[name] + ": "), line)
        self.assertIn("2 command zones, 2 deployment zones, 2 marks, 2 phases; viewBox 8 16 48 44", lines[0])
        self.assertEqual(lines[3], f"Artifact publish: file_path={where[sb.PAGE]} files="
                                   + json.dumps({"minimap.png": where[sb.MINIMAP],
                                                 "satellite.png": where[sb.SATELLITE]}))
        self.assertEqual(png_size(self.out / sb.MINIMAP), (48, 44))
        self.assertEqual(png_size(self.out / sb.SATELLITE), (96, 88))     # the Preview keeps its resolution
        self.assertIn('viewBox="8 16 48 44"', (self.out / sb.PAGE).read_text(encoding="utf-8"))

    def test_a_satellite_crop_over_the_limit_is_halved(self):
        write_layout(self.extraction)
        with mock.patch.object(sb, "MAX_PICTURE", 100):
            code, out, _ = self.run_main(str(self.spec_path), "--out", str(self.out))
        self.assertEqual(code, 0)
        self.assertEqual(png_size(self.out / sb.SATELLITE), (48, 44))
        self.assertIn("halved", out.splitlines()[2])

    def test_a_spec_error_names_the_file_and_the_json_path(self):
        bad = spec()
        bad["marks"][0]["kind"] = "blob"
        self.spec_path.write_text(json.dumps(bad), encoding="utf-8")
        code, out, err = self.run_main(str(self.spec_path), "--out", str(self.out))
        self.assertEqual((code, out), (1, ""))
        line = self.failed_line(err)
        self.assertTrue(line.startswith(f"FAILED: {self.spec_path}: $.marks[0].kind: "), line)

    def test_an_unknown_stock_zone_name_fails_with_the_usual_line(self):
        write_layout(self.extraction)
        bad = own_zones()
        bad["map"]["command_zones"][0]["stock"] = "CZ_Z"
        self.spec_path.write_text(json.dumps(bad), encoding="utf-8")
        code, out, err = self.run_main(str(self.spec_path), "--out", str(self.out))
        self.assertEqual((code, out), (1, ""))
        line = self.failed_line(err)
        self.assertTrue(line.startswith(f"FAILED: {self.spec_path}: $.map.command_zones[0].stock: "), line)

    def test_a_file_that_is_not_json_fails(self):
        self.spec_path.write_text("{version: 1", encoding="utf-8")
        code, _, err = self.run_main(str(self.spec_path), "--out", str(self.out))
        self.assertEqual(code, 1)
        self.assertIn(": $: not JSON", self.failed_line(err))

    def test_unconfigured_fails_naming_setup(self):
        env = {k: v for k, v in os.environ.items() if not k.startswith("MODKIT_")}
        with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(paths, "_find_config", return_value=None):
            out, err = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = sb.main([str(self.spec_path), "--out", str(self.out)])
        self.assertEqual(code, 1)
        self.assertIn("warno-setup", self.failed_line(err.getvalue()))

    def test_a_missing_stock_file_fails_naming_setup(self):
        code, _, err = self.run_main(str(self.spec_path), "--out", str(self.out))      # an empty extraction
        self.assertEqual(code, 1)
        line = self.failed_line(err)
        self.assertTrue(line.startswith(f"FAILED: missing stock file extracted/{LAYOUT}/out/PlayableZone.ndfbin"), line)
        self.assertIn("warno-setup", line)
        write_layout(self.extraction)                                                    # the layout, no pictures
        code, _, err = self.run_main(str(self.spec_path), "--out", str(self.out), pictures=False)
        self.assertEqual(code, 1)
        line = self.failed_line(err)
        self.assertTrue(line.startswith(f"FAILED: missing stock file extracted/basemaps/{MAP}/PC/Texture/{MAP}/"
                                        "Minimap.tgv"), line)
        self.assertIn("warno-setup", line)

    def test_a_page_over_the_limit_fails_before_writing(self):
        write_layout(self.extraction)
        with mock.patch.object(sb, "MAX_PAGE", 1000):
            code, _, err = self.run_main(str(self.spec_path), "--out", str(self.out))
        self.assertEqual(code, 1)
        self.assertIn("index.html would be", self.failed_line(err))


class UnitKeyTest(unittest.TestCase):
    KNOWN = {"$/GFX/Unit/Descriptor_Unit_T80BV_SOV", "$/GFX/Unit/Descriptor_Unit_BMP_2_SOV",
             "$/GFX/Unit/Descriptor_Unit_MotRifles_SOV"}

    def oob(self, *keys: str) -> dict:
        return spec(sections=[{"heading": "OOB", "oob": [{"title": "x", "groups": [
            {"name": "g", "units": [[1, "unit", k] for k in keys] + [[2, "no key"]]}]}]}])

    def test_unknown_keys_are_listed_with_their_path(self):
        self.assertEqual(sb.unknown_units(self.oob("T80BV_SOV", "BMP_2_SOV · MotRifles_SOV"), self.KNOWN), [])
        self.assertEqual(sb.unknown_units(self.oob("T80BV_SOV", "BMP_2_SOV · Nope_SOV", "T80_SOV"), self.KNOWN),
                         [("$.sections[0].oob[0].groups[0].units[1][2]", "Nope_SOV"),
                          ("$.sections[0].oob[0].groups[0].units[2][2]", "T80_SOV")])

    def test_generate_with_units_fails_before_reading_the_map(self):
        with self.assertRaisesRegex(sb.SpecError, r"^\$\.sections\[0\]\.oob\[0\]\.groups\[0\]\.units\[0\]\[2\]: "
                                                  r"not in the game's unit database: T80_SOV$"):
            sb.generate(self.oob("T80_SOV"), "unused", source=object(), units=self.KNOWN)

    @paths.skip_unless_game_dir("Mods", "ModData", "base.zip")
    def test_the_samples_keys_are_stock_units(self):
        from modkit.ops.gates import unit_database
        self.assertEqual(sb.unknown_units(sb.load_spec(SAMPLE), unit_database()), [])


class DefaultOutTest(unittest.TestCase):
    def test_the_build_folder_and_the_spec_name(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.dict(os.environ, {"MODKIT_BUILD": tmp}):
            self.assertEqual(sb.default_out(os.path.join("x", "sample.json")), Path(tmp) / "storyboard" / "sample")
            op_spec = os.path.join("examples", "twin-strike", "docs", "storyboard.json")
            self.assertEqual(sb.default_out(op_spec), Path(tmp) / "storyboard" / "twin-strike")
            self.assertEqual(sb.default_out(os.path.join("my-op", "storyboard.json")),
                             Path(tmp) / "storyboard" / "my-op")

    def test_the_cli_writes_there_without_out(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_layout(root / "extracted")
            spec_path = root / "op.json"
            spec_path.write_text(json.dumps(spec()), encoding="utf-8")
            env = {"MODKIT_EXTRACTED": str(root / "extracted"), "MODKIT_BUILD": str(root / "build")}
            with mock.patch.dict(os.environ, env), mock.patch.object(sb.StockSource, "picture", stub_picture), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(sb.main([str(spec_path)]), 0)
            self.assertEqual(sorted(p.name for p in (root / "build" / "storyboard" / "op").iterdir()),
                             ["index.html", "minimap.png", "satellite.png"])


@paths.skip_unless_extracted("twincities_op", "SM_SU_3x3_TwinCities_03_Details", "out")
@paths.skip_unless_extracted("basemaps", "_3x3_TwinCities")
class TwinCitiesSampleTest(unittest.TestCase):
    """The two-phase sample spec on the real stock small layout of Twin Cities (playable x 0-432, y 146-768)."""

    def test_the_sample_renders_on_the_stock_layout(self):
        s = sb.load_spec(SAMPLE)
        with tempfile.TemporaryDirectory() as tmp:
            sb.generate(copy.deepcopy(s), tmp)
            html = Path(tmp, sb.PAGE).read_text(encoding="utf-8")
            self.assertEqual(png_size(Path(tmp, sb.MINIMAP)), (432, 622))
            self.assertIn(png_size(Path(tmp, sb.SATELLITE)), ((864, 1244), (432, 622)))
            self.assertLess(Path(tmp, sb.SATELLITE).stat().st_size, sb.MAX_PICTURE)
        self.assertIn('viewBox="0 146 432 622"', html)
        self.assertEqual(html.count('<g class="cz">'), 3)
        for stock, name in (("AutoName_5", "Village"), ("AutoName_8", "Crossroads"), ("AutoName_6", "Left twin")):
            self.assertIn(f"<title>Command zone {stock} ({name}): ", html)
        self.assertIn('<g class="dep st-nato">', html)
        self.assertIn('<g class="dep st-sov">', html)


if __name__ == "__main__":
    unittest.main()
