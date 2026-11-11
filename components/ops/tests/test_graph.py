"""Tests for modkit.ops.graph: the object-graph builder and its stock-layout rules."""
import unittest

from modkit.core import ndfbin
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.graph import (
    TRUE, Imp, Node, Str, all_values, build_graph, decode, encode, f32, i32, loc, template_scalars, u32, with_scalars,
)


def small_graph() -> tuple[list[Node], list[Node]]:
    """A root exporting a camp and a script folder: two imports, a shared string, a list of references."""
    camp = Node("TGDVariableCamp", [("AllianceStyle", i32(3)), ("PlayerName", loc("op_pl"))],
                export="$/GDScript/RootDescriptor/joueur")
    wait = Node("TGDDescriptorWaitDuration", [("Duree", f32(1.5))])
    main = Node("TGDDescriptorSequential", [("SubActions", [wait]), ("NbExecutions", u32(1))],
                export="$/GDScript/Op/Main")
    root = Node("TGDDescriptorLaunchEffetStandard", [
        ("CampList", [camp]),
        ("EffetMap", main),
        ("Unit", Imp("$/GFX/Unit/Descriptor_Unit_A")),
        ("Other", Imp("$/GFX/Unit/Descriptor_Unit_B")),
        ("Again", Imp("$/GFX/Unit/Descriptor_Unit_A")),
        ("Label", Str("Primary")),
        ("Path", Str("GameData:/x.ogg", 0x1C)),
        ("Flag", TRUE),
    ], export="$/GDScript/RootDescriptor")
    free = Node("TCutsceneDescriptorDatabase")
    return [free, root], [root, camp, main]


class ValueTest(unittest.TestCase):
    def test_scalar_builders(self):
        self.assertEqual(i32(-2), Value(0x02, -2))
        self.assertEqual(u32(7), Value(0x03, 7))
        self.assertEqual(f32(3), Value(0x05, 3.0))
        self.assertIsInstance(f32(3).v, float)
        self.assertEqual(TRUE, Value(0x00, 1))
        self.assertEqual(loc("op_pl"), ndfbin.loc_value("op_pl"))

    def test_str_defaults_to_a_plain_string(self):
        self.assertEqual(Str("a").tag, 0x07)
        self.assertEqual(Str("a", 0x1C).tag, 0x1C)


class BuildGraphTest(unittest.TestCase):
    def setUp(self):
        roots, exports = small_graph()
        self.nb = build_graph(roots, exports)

    def test_objects_breadth_first_from_each_root(self):
        names = [self.nb.cname(ob.cls) for ob in self.nb.objects]
        self.assertEqual(names[:5], ["TCutsceneDescriptorDatabase", "TGDDescriptorLaunchEffetStandard",
                                     "TGDVariableCamp", "TGDDescriptorSequential", "TGDDescriptorWaitDuration"])
        # a folder of the export tree without an object gets a property-less TBaseClass, except $ and $/GDScript
        self.assertEqual(names[5:], ["TBaseClass"])

    def test_export_folders(self):
        exported = dict(ndfbin.tree_paths(self.nb, self.nb.exports))
        self.assertEqual(sorted(exported), ["$/GDScript/Op", "$/GDScript/Op/Main", "$/GDScript/RootDescriptor",
                                            "$/GDScript/RootDescriptor/joueur"])
        self.assertNotIn("$", exported)
        self.assertNotIn("$/GDScript", exported)

    def test_imports_in_first_use_order_and_deduplicated(self):
        self.assertEqual(ndfbin.tree_paths(self.nb, self.nb.imports)[-2:],
                         [("$/GFX/Unit/Descriptor_Unit_A", 0), ("$/GFX/Unit/Descriptor_Unit_B", 1)])
        refs = [x.v for _, _, x in all_values(self.nb) if x.tag == 0x09 and x.v.kind == ndfbin.REF_IMPORT]
        self.assertEqual([r.index for r in refs], [0, 1, 0])

    def test_tran_lists_imports_before_exports(self):
        trans = [t.decode("latin-1") for t in self.nb.trans]
        self.assertLess(trans.index("Descriptor_Unit_A"), trans.index("RootDescriptor"))

    def test_topo_is_exported_plus_unreferenced(self):
        self.assertEqual(self.nb.topo, [0, 1, 2, 3, 5])  # #4 (the wait) is referenced and not exported
        self.assertEqual(self.nb.chnk, [(0, len(self.nb.objects))])

    def test_object_refs_carry_the_target_class(self):
        for _, _, x in all_values(self.nb):
            if x.tag == 0x09 and x.v.kind == ndfbin.REF_OBJECT:
                self.assertEqual(x.v.cls, self.nb.objects[x.v.index].cls)

    def test_strings_and_resource_paths(self):
        tags = {self.nb.strings[x.v].decode("latin-1"): x.tag for _, _, x in all_values(self.nb)
                if x.tag in (0x07, 0x1C)}
        self.assertEqual(tags, {"Primary": 0x07, "GameData:/x.ogg": 0x1C})

    def test_encode_round_trips(self):
        raw = encode(self.nb, "small")
        nb, _, image = decode(raw)
        self.assertEqual(ndfbin.encode_image(nb), image)
        self.assertEqual(image, ndfbin.encode_image(self.nb))

    def test_one_prop_per_class_unless_shared(self):
        a = Node("TA", [("Name", Str("a"))])
        b = Node("TB", [("Name", Str("b"))])
        root = Node("TRoot", [("Items", [a, b])])
        self.assertEqual(len(build_graph([root], []).props), 3)
        shared = build_graph([Node("TRoot", [("Items", [Node("TA", [("Name", Str("a"))]),
                                                         Node("TB", [("Name", Str("b"))])])])], [],
                             frozenset({"Name"}))
        self.assertEqual(len(shared.props), 2)
        self.assertEqual(shared.cname(shared.props[1][1]), "TA")

    def test_bad_exports_fail(self):
        with self.assertRaises(CheckError):
            build_graph([], [Node("TA", export="GDScript/A")])
        with self.assertRaises(CheckError):
            build_graph([], [Node("TA", export="$/A"), Node("TB", export="$/A")])

    def test_bad_value_spec(self):
        with self.assertRaises(TypeError):
            build_graph([Node("TA", [("X", 3)])], [])


class TemplateTest(unittest.TestCase):
    def setUp(self):
        self.tpl = build_graph([Node("TGDDescriptorForceDisplayUIElement", [
            ("ShowMinimap", i32(2)), ("ShowTopBar", i32(1)), ("ForceHideAll", TRUE)]),
            Node("TList", [("Items", [Node("TA")])])], [])

    def test_scalars_kept_in_order(self):
        props = template_scalars(self.tpl, (0, "TGDDescriptorForceDisplayUIElement", ("ShowMinimap",)))
        self.assertEqual(props, [("ShowTopBar", Value(0x02, 1)), ("ForceHideAll", Value(0x00, 1))])

    def test_template_checks(self):
        with self.assertRaises(CheckError):
            template_scalars(self.tpl, (0, "TOther", ()))
        with self.assertRaises(CheckError):
            template_scalars(self.tpl, (1, "TList", ()))
        with self.assertRaises(CheckError):
            template_scalars(self.tpl, (0, "TGDDescriptorForceDisplayUIElement", ("Missing",)))

    def test_with_scalars(self):
        props = [("ShowMinimap", i32(2)), ("ShowTopBar", i32(1))]
        order = ["ShowLaunchBattleButton", "ShowMinimap", "ShowProdMenu", "ShowTopBar"]
        out = with_scalars(props, (("ShowTopBar", 2), ("ShowProdMenu", 2), ("ShowLaunchBattleButton", 2)), order)
        self.assertEqual(out, [("ShowLaunchBattleButton", i32(2)), ("ShowMinimap", i32(2)),
                               ("ShowProdMenu", i32(2)), ("ShowTopBar", i32(2))])
        self.assertEqual(props[1], ("ShowTopBar", i32(1)))  # the input is not changed
        with self.assertRaises(CheckError):
            with_scalars(props, (("Unknown", 1),), order)
        with self.assertRaises(CheckError):
            with_scalars([("Flag", TRUE)], (("Flag", 1),))


if __name__ == "__main__":
    unittest.main()
