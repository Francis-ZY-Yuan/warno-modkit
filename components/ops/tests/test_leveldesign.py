"""Tests for modkit.ops.leveldesign and the GdItems binding gate (modkit.ops.gates.check_binding)."""
import glob
import os
import struct
import unittest
import uuid
from collections import namedtuple

from modkit.core import ndfbin, paths
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.gates import check_binding
from modkit.ops.graph import Node, Str, build_graph, decode, encode, f32, i32
from modkit.ops.leveldesign import (
    GD_TAG_CLASS, MENU_ORDER_BASE, MENU_ORDER_SPAN, LdItem, derived_menu_order, gd_tags, ld_guid, ld_key, ld_position,
    leveldesign_graph, read_ld_items, scenario_guid, zone_addon_extra, zone_area,
)
from modkit.ops.zones import polygon_centroid, read_zone_areas, rect_polygon, zone_areas_graph

Item = namedtuple("Item", "ranking name x y addon")
ITEMS = (Item("Tags", "Centre", 100.0, 200.0, "Name"), Item("CircularZones", "Ring", 300.0, 400.0, "CircularZone"),
         Item("Camp_0", "Rifles", 500.0, 600.0, "Spawn"))


def guid(it: Item) -> bytes:
    return uuid.uuid5(uuid.NAMESPACE_URL, f"test/{it.ranking}/{it.name}").bytes


def leveldesign(items=ITEMS) -> bytes:
    nodes = []
    for it in items:
        props = [("Name", Str(it.name)), ("Ranking", Str(it.ranking)), ("GUID", Value(0x1A, guid(it)))]
        if it.addon == "CircularZone":
            props.append(("RadiusGRU", f32(10)))
        nodes.append(Node("TGameDesignItem", [("Position", Value(0x21, (it.x, it.y))),
                                              ("AddOn", Node(f"TGameDesignAddOn_{it.addon}", props))]))
    return encode(build_graph([Node("TGameDesignDatabase", [("GameDesignItemList", nodes)])], [],
                              frozenset({"Name", "Ranking", "GUID"})), "LevelDesign")


def gdscript(items=ITEMS, cls=None, path=None) -> bytes:
    tags = [Node(cls or GD_TAG_CLASS[it.addon],
                 [(f"GUID{k + 1}", i32(w)) for k, w in enumerate(struct.unpack(">4i", guid(it)))],
                 export=path or f"$/GDScript/GdItems/{it.ranking}/{it.name}") for it in items]
    return encode(build_graph([Node("TGDDescriptorLaunchEffetStandard")], tags), "GDScript")


class ReadTest(unittest.TestCase):
    def test_read_ld_items(self):
        items = read_ld_items(leveldesign())
        self.assertEqual([(it["Ranking"], it["Name"], it["addon"]) for it in items],
                         [(it.ranking, it.name, it.addon) for it in ITEMS])
        self.assertEqual(items[0]["pos"], (100.0, 200.0))
        self.assertIsNone(items[0]["rot"])
        self.assertEqual(items[1]["RadiusGRU"], 10.0)
        self.assertEqual(items[2]["GUID"], guid(ITEMS[2]))

    def test_ld_position(self):
        self.assertEqual(ld_position("CircularZones/Ring", ITEMS), (300.0, 400.0))
        with self.assertRaises(StopIteration):
            ld_position("Tags/Missing", ITEMS)


class BindingTest(unittest.TestCase):
    def test_binds_one_to_one(self):
        self.assertEqual(check_binding(gdscript(), leveldesign()), 3)

    def test_item_without_a_tag(self):
        with self.assertRaisesRegex(CheckError, "without a GdItems tag"):
            check_binding(gdscript(ITEMS[:2]), leveldesign())

    def test_tag_without_an_item(self):
        with self.assertRaisesRegex(CheckError, "match no LevelDesign item"):
            check_binding(gdscript(), leveldesign(ITEMS[:2]))

    def test_tag_path_must_name_its_item(self):
        with self.assertRaisesRegex(CheckError, "binds Tags/Centre"):
            check_binding(gdscript(ITEMS[:1], path="$/GDScript/GdItems/Tags/Other"), leveldesign(ITEMS[:1]))

    def test_tag_class_must_match_the_add_on(self):
        with self.assertRaisesRegex(CheckError, "bound to a CircularZone add-on"):
            check_binding(gdscript(ITEMS[1:2], cls="TGDTagPosition"), leveldesign(ITEMS[1:2]))


NS = "test-mods"
SHARED = frozenset({"Name", "Ranking", "GUID"})


def addons(items, scenario="challenge_Test", namespace=NS) -> dict[str, Node]:
    """The add-on Node of each item of leveldesign_graph's output, keyed by Name, in file order."""
    (db,) = leveldesign_graph(items, scenario, namespace)
    return {dict(nd.props)["AddOn"].props[0][1].text: dict(nd.props)["AddOn"] for nd in db.props[0][1]}


def prop_names(node: Node) -> list[str]:
    return [name for name, _ in node.props]


class GuidTest(unittest.TestCase):
    def test_uuid5_of_namespace_scenario_ranking_and_name(self):
        it = LdItem("Tags", "A", 1.0, 2.0, "Name")
        self.assertEqual(ld_guid(it, "challenge_Test", "ns"),
                         uuid.uuid5(uuid.NAMESPACE_URL, "ns/challenge_Test/Tags/A").bytes)

    def test_namespace_and_scenario_both_change_it(self):
        it = LdItem("Tags", "A", 1.0, 2.0, "Name")
        guids = {ld_guid(it, s, ns) for s in ("challenge_A", "challenge_B") for ns in ("one", "two")}
        self.assertEqual(len(guids), 4)

    def test_key_sorts_by_ranking_then_name(self):
        items = [LdItem("Tags", "B", 0, 0, "Name"), LdItem("Camp_0", "Z", 0, 0, "Name"),
                 LdItem("Tags", "A", 0, 0, "Name")]
        self.assertEqual([it.name for it in sorted(items, key=ld_key)], ["Z", "A", "B"])


class DerivedMenuOrderTest(unittest.TestCase):
    """A published Operation's menu order: MENU_ORDER_BASE + its scenario GUID (big-endian) modulo MENU_ORDER_SPAN."""

    def test_the_formula_and_determinism(self):
        guid = uuid.uuid5(uuid.NAMESPACE_URL, "ns/challenge_Test").bytes
        self.assertEqual(scenario_guid("challenge_Test", "ns"), guid)
        want = MENU_ORDER_BASE + int.from_bytes(guid, "big") % MENU_ORDER_SPAN
        self.assertEqual([derived_menu_order("challenge_Test", "ns") for _ in range(3)], [want] * 3)

    def test_in_range_above_stock_and_hand_picks_and_a_uint32(self):
        """Every order lies in [BASE, BASE + SPAN): far above stock's (999 at most) and the hand picks just above it,
        and inside a uint32 (the field's type)."""
        orders = [derived_menu_order(f"challenge_Op{k}", ns) for k in range(500) for ns in ("one", "two")]
        self.assertTrue(all(MENU_ORDER_BASE <= o < MENU_ORDER_BASE + MENU_ORDER_SPAN for o in orders))
        self.assertGreater(MENU_ORDER_BASE, 999)
        self.assertLess(MENU_ORDER_BASE + MENU_ORDER_SPAN, 2 ** 32)

    def test_namespace_and_scenario_both_change_it(self):
        """The three examples' published contents (Twin Strike, the nuke probes) get three different orders."""
        three = {derived_menu_order("challenge_OperationTwinStrike", "warno-twinstrike"),
                 derived_menu_order("challenge_OpenDoorNuke", "warno-opendoor"),
                 derived_menu_order("challenge_OpenDoorNukeSov", "warno-opendoor")}
        self.assertEqual(len(three), 3)
        self.assertNotEqual(derived_menu_order("challenge_A", "one"), derived_menu_order("challenge_A", "two"))


class LevelDesignGraphTest(unittest.TestCase):
    """leveldesign_graph writes both item forms of the two generators it replaced: an item without Camp,
    DisableAutoSpawn or NumAlliance gives the plain form, and setting them adds them in stock order."""

    def test_items_sorted_and_guids_keyed(self):
        items = [LdItem("Tags", "B", 1, 2, "Name"), LdItem("Tags", "A", 3, 4, "Name")]
        self.assertEqual(list(addons(items)), ["A", "B"])
        a = addons(items, "challenge_X", "ns")["A"]
        self.assertEqual(dict(a.props)["GUID"].v, ld_guid(items[1], "challenge_X", "ns"))

    def test_plain_spawn(self):
        it = LdItem("Camp_0", "P", 1, 2, "Spawn", unit="Rifles_AT_UK", experience=1)
        a = addons([it])["P"]
        self.assertEqual(prop_names(a), ["Name", "Ranking", "GUID", "AutoNameBase", "ClassName", "ExperienceLevel"])
        self.assertEqual(dict(a.props)["ClassName"].text, "$/GFX/Unit/Descriptor_Unit_Rifles_AT_UK")
        self.assertEqual(prop_names(addons([LdItem("Camp_0", "P", 1, 2, "Spawn", unit="X")])["P"]),
                         ["Name", "Ranking", "GUID", "AutoNameBase", "ClassName"])

    def test_spawn_with_camp_and_hidden(self):
        it = LdItem("Camp_1", "E", 1, 2, "Spawn", unit="X", experience=2, camp=1, disable_auto_spawn=True)
        self.assertEqual(prop_names(addons([it])["E"]), ["Name", "Ranking", "GUID", "AutoNameBase", "Camp",
                                                        "ClassName", "ExperienceLevel", "DisableAutoSpawn"])
        self.assertNotIn("Camp", prop_names(addons([LdItem("Camp_0", "E", 1, 2, "Spawn", unit="X", camp=0)])["E"]))

    def test_arrivals_with_and_without_num_alliance(self):
        rl = LdItem("ReinforcementLocations", "R", 1, 2, "ReinforcementLocation", start=(0, 1), end=(2, 3))
        self.assertEqual(prop_names(addons([rl])["R"]), ["Name", "Ranking", "GUID", "StartPosition", "EndPosition"])
        self.assertEqual(dict(addons([rl])["R"].props)["EndPosition"].v, (2.0, 3.0, 0.0))
        ac = LdItem("AerialCorridors", "C", 1, 2, "AerialCorridor", start=(0, 1), end=(2, 3), num_alliance=1)
        self.assertEqual(prop_names(addons([ac])["C"]),
                         ["Name", "Ranking", "GUID", "NumAlliance", "StartPosition", "EndPosition"])

    def test_zones_rotation_and_circles(self):
        dz0 = LdItem("DeploymentZone", "D0", 1, 2, "DeploymentZone", polygon=rect_polygon((0, 0, 4, 4)))
        dz1 = LdItem("DeploymentZone", "D1", 1, 2, "DeploymentZone", alliance=1, rotation=0.5)
        cz = LdItem("CommandPoints", "Z", 1, 2, "CommandPoints", points=3)
        ring = LdItem("CircularZones", "O", 1, 2, "CircularZone", radius_gru=800.0)
        got = addons([dz0, dz1, cz, ring])
        self.assertEqual(prop_names(got["D0"]), ["Name", "Ranking", "GUID"])
        self.assertEqual(prop_names(got["D1"])[3:], ["AllianceNum"])
        self.assertEqual(dict(got["Z"].props)["Points"].v, 3)
        self.assertEqual(dict(got["O"].props)["RadiusGRU"].v, 800.0)
        self.assertEqual(zone_addon_extra(dz0), [])
        (db,) = leveldesign_graph([dz1], "s", NS)
        self.assertEqual(prop_names(db.props[0][1][0]), ["Position", "Rotation", "AddOn"])

    def test_unknown_add_on(self):
        with self.assertRaisesRegex(CheckError, "unknown add-on Bogus"):
            leveldesign_graph([LdItem("Tags", "A", 0, 0, "Bogus")], "s", NS)

    def test_reads_back(self):
        items = [LdItem("Camp_0", "P", 1, 2, "Spawn", unit="X", experience=1), LdItem("Tags", "T", 3, 4, "Name")]
        raw = encode(build_graph(leveldesign_graph(items, "s", NS), [], SHARED), "LevelDesign")
        back = read_ld_items(raw)
        self.assertEqual([(it["Name"], it["addon"], it["pos"]) for it in back],
                         [("P", "Spawn", (1.0, 2.0)), ("T", "Name", (3.0, 4.0))])
        self.assertEqual(back[0]["GUID"], ld_guid(items[0], "s", NS))


class ZoneAreaTest(unittest.TestCase):
    def test_details_copy_of_a_zone_item(self):
        poly = rect_polygon((0, 0, 40, 20))
        it = LdItem("CommandPoints", "Z", 10, 10, "CommandPoints", polygon=poly, points=2, rotation=0.25)
        ring, center, cls, props, rot = zone_area(it, "challenge_X", "ns", 123.5)
        self.assertEqual((ring, center, cls, rot), (list(poly), (*polygon_centroid(list(poly)), 123.5),
                                                    "TGameDesignAddOn_CommandPoints", 0.25))
        self.assertEqual([name for name, _ in props], ["Name", "Ranking", "GUID", "Points"])
        self.assertEqual(dict(props)["GUID"].v, ld_guid(it, "challenge_X", "ns"))
        raw = encode(build_graph(zone_areas_graph([zone_area(it, "challenge_X", "ns", 123.5)]), []), "CZ")
        (back,) = read_zone_areas(raw)
        self.assertEqual(back[2], "TGameDesignAddOn_CommandPoints")


class GdTagsTest(unittest.TestCase):
    ITEMS = [LdItem("Tags", "T", 1, 2, "Name"), LdItem("CircularZones", "O", 3, 4, "CircularZone", radius_gru=5.0),
             LdItem("Camp_0", "P", 5, 6, "Spawn", unit="X")]

    def test_keys_classes_and_exports(self):
        tags = gd_tags(self.ITEMS, "s", NS)
        self.assertEqual(list(tags), ["Camp_0/P", "CircularZones/O", "Tags/T"])
        self.assertEqual([nd.cls for nd in tags.values()], ["TGDTagUnitGroup", "TGDTagDetecteur", "TGDTagPosition"])
        self.assertEqual(tags["Tags/T"].export, "$/GDScript/GdItems/Tags/T")

    def test_tags_bind_to_their_leveldesign(self):
        ld = encode(build_graph(leveldesign_graph(self.ITEMS, "s", NS), [], SHARED), "LevelDesign")

        def script(scenario: str, namespace: str) -> bytes:
            tags = list(gd_tags(self.ITEMS, scenario, namespace).values())
            return encode(build_graph([Node("TGDDescriptorLaunchEffetStandard")], tags), "GDScript")

        self.assertEqual(check_binding(script("s", NS), ld), 3)
        for scenario, namespace in (("other", NS), ("s", "other")):
            with self.subTest(scenario=scenario, namespace=namespace), self.assertRaisesRegex(CheckError, "match no"):
                check_binding(script(scenario, namespace), ld)


class StockTest(unittest.TestCase):
    @paths.skip_unless_extracted("scenarios")
    def test_tag_classes_match_stock(self):
        """In every stock Operation, each GdItems tag of a kind in GD_TAG_CLASS has the class the table gives."""
        checked = 0
        for folder in sorted(glob.glob(os.path.join(paths.extracted_root(), "scenarios", "challenge_*"))):
            name = os.path.basename(folder)
            gd_path = os.path.join(folder, "NDF", "Scenarios", "GDScript", f"{name}.ndfbin")
            ld_path = os.path.join(folder, "out", "LevelDesign.ndfbin")
            if not (os.path.isfile(gd_path) and os.path.isfile(ld_path)):
                continue
            with open(ld_path, "rb") as fh:
                kinds = {it["GUID"]: it["addon"] for it in read_ld_items(fh.read())}
            with open(gd_path, "rb") as fh:
                gd, _, _ = decode(fh.read())
            for path, i in ndfbin.tree_paths(gd, gd.exports):
                ob = gd.objects[i]
                p = {gd.pname(pi): v for pi, v in ob.props}
                if not path.startswith("$/GDScript/GdItems/") or "GUID1" not in p:
                    continue
                kind = kinds.get(struct.pack(">4i", *(p[f"GUID{k}"].v for k in range(1, 5))))
                if kind in GD_TAG_CLASS:
                    self.assertEqual(gd.cname(ob.cls), GD_TAG_CLASS[kind], f"{name}: {path}")
                    checked += 1
        self.assertGreater(checked, 100)


if __name__ == "__main__":
    unittest.main()
