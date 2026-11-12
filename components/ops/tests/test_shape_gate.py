"""Tests for the 'only stock shapes' gate (modkit.ops.gates: survey_shapes, check_shapes)."""
import os
import tempfile
import unittest

from modkit.core import ndfbin, paths
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.bricks import (
    c_team, c_type, g_cmp, g_compete, g_count, g_create, g_detect, g_dialog, g_end_sequence, g_hint, g_seq, g_set,
    g_simul, g_until, g_wait, unit_path,
)
from modkit.ops.gates import check_shapes, object_shapes, survey_shapes
from modkit.ops.graph import Imp, Node, Str, build_graph, decode, encode, f32, i32
from modkit.ops.leveldesign import TAG_ID


def graph(*roots: Node) -> bytes:
    return encode(build_graph(list(roots), []), "test")


class ShapesTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        stock = Node("TA", [("X", i32(1)), ("Y", f32(1)), ("Ref", Node("TB")), ("Unit", Imp("$/GFX/Unit/U"))])
        for k in range(2):
            with open(os.path.join(self.tmp.name, f"stock{k}.ndfbin"), "wb") as fh:
                fh.write(graph(stock, Node("TC", [("Name", Str("n"))])))
        self.stock, self.n = survey_shapes((os.path.join(self.tmp.name, "stock*.ndfbin"),), 2)

    def tearDown(self):
        self.tmp.cleanup()

    def test_survey(self):
        self.assertEqual(self.n, 2)
        self.assertEqual(self.stock.classes, {"TA", "TB", "TC"})
        self.assertIn(("TA", "Ref", "TB"), self.stock.targets)
        self.assertIn(("TA", "Unit", "import $/GFX/Unit"), self.stock.targets)
        self.assertIn(("TA", "X", "Y"), self.stock.before)

    def test_survey_needs_enough_files(self):
        with self.assertRaisesRegex(CheckError, "expected 3"):
            survey_shapes((os.path.join(self.tmp.name, "stock*.ndfbin"),), 3)

    def test_stock_shapes_pass(self):
        self.assertEqual(check_shapes(graph(Node("TA", [("X", i32(2)), ("Ref", Node("TB"))])), self.stock, "t"), 2)

    def test_unknown_class(self):
        with self.assertRaisesRegex(CheckError, "class not in stock"):
            check_shapes(graph(Node("TZ")), self.stock, "t")

    def test_wrong_value_tag(self):
        with self.assertRaisesRegex(CheckError, "property/tag not in stock"):
            check_shapes(graph(Node("TA", [("X", f32(1))])), self.stock, "t")

    def test_wrong_target(self):
        with self.assertRaisesRegex(CheckError, "reference target not in stock"):
            check_shapes(graph(Node("TA", [("Ref", Node("TC"))])), self.stock, "t")

    def test_wrong_order(self):
        with self.assertRaisesRegex(CheckError, "property order differs"):
            check_shapes(graph(Node("TA", [("Y", f32(1)), ("X", i32(1))])), self.stock, "t")

    def test_object_shapes(self):
        nb, _, _ = decode(graph(Node("TA", [("X", i32(1)), ("Ref", Node("TB"))])))
        sh = object_shapes(nb, 0, {i: p for p, i in ndfbin.tree_paths(nb, nb.imports)})
        self.assertEqual(sh.props, {("TA", "X", 0x02), ("TA", "Ref", 0x09)})


class StockBricksTest(unittest.TestCase):
    @paths.skip_unless_extracted("scenarios")
    def test_bricks_use_stock_shapes(self):
        """A script built from the bricks passes the shape gate against the 16 stock Operation GDScripts (build
        210942: NDF/Scenarios/<scenario>/GDScript.txn; a GdItems tag holds one GUID, TAG_ID)."""
        stock, n = survey_shapes((os.path.join(paths.extracted_root(), "scenarios", "challenge_*", "NDF", "Scenarios",
                                               "challenge_*", "GDScript.txn"),), 16)
        camp = Node("TGDVariableCamp", [("AllianceStyle", i32(3))], export="$/GDScript/RootDescriptor/joueur")
        group = Node("TGDVariableUnitGroup", export="$/GDScript/Op/Variables/Group")
        count = Node("TGDVariableInteger", export="$/GDScript/Op/Variables/Count")
        zone = Node("TGDTagDetecteur", [(TAG_ID, Value(0x1A, bytes(range(16))))],
                    export="$/GDScript/GdItems/CircularZones/Ring")
        pos = Node("TGDTagPosition", [(TAG_ID, Value(0x1A, bytes(range(16, 32))))],
                   export="$/GDScript/GdItems/Tags/Point")
        main = g_seq([
            g_create(camp, group, 2, pos, unit_path("MotRifles_SOV")),
            g_simul([g_hint("op_h", 15.0, "shint"), g_dialog("op_d")]),
            g_compete([g_until(g_cmp(group, 1, 2)), g_wait(30)]),
            g_until(g_detect(zone, c_team(camp), 1, 2)),
            g_count(count, group), g_set(count, 1),
            g_end_sequence("op_end", 5, None, "$/GDScript/Op/Win"),
        ], export="$/GDScript/Op/Main")
        raw = encode(build_graph([main], [camp, zone, pos, main, group, count]), "GDScript")
        self.assertGreater(check_shapes(raw, stock, "bricks"), 10)
        self.assertGreaterEqual(n, 16)
        # the gate is not a formality: a combination no stock script uses fails
        with self.assertRaisesRegex(CheckError, "reference target not in stock"):
            check_shapes(graph(g_detect(Node("TGDTagDetecteur"), c_type("MotRifles_SOV"), 1, 2)), stock, "type")


if __name__ == "__main__":
    unittest.main()
