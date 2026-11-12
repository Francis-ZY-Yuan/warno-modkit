"""Tests for the build plan of a cloned scenario in modkit.ops.items: plan_definition, plan_details, plan_assets,
menu_art."""
import os
import tempfile
import unittest

from modkit.core import dbg, txntag
from modkit.core.gates import CheckError
from modkit.core.ndfbin import Value
from modkit.ops.graph import Map, Node, Str, build_graph, decode, encode
from modkit.ops.items import (
    GENERATED_SOURCE, MENU_ART, AssetRule, asset_rule, menu_art, payload, plan_assets, plan_definition, plan_details,
)
from modkit.ops.rekey import DBG, TAG, TAG_CLASS, TXN, Rekey, def_path

SOURCE, NEW = "challenge_A", "challenge_B"
G_OLD, G_NEW = bytes(range(16)), bytes(range(16, 32))


def table(kinds=("GDScript", "ScenarioInfo")) -> Rekey:
    return Rekey(SOURCE, NEW, G_OLD, G_NEW, {}, "ta_", (), {}, {}, {}, kinds)


def transactions(entries):
    """A stand-in for gates.definition_transactions: one transaction per planned kind, named by its BaseName."""
    return {kind: txntag.Transaction(f"Scenarios/{NEW}/{kind}.txn", kind, ())
            for kind in ("GDScript", "ScenarioInfo") if any(p.endswith(f"/{kind}.txn") for p in entries)}


def write(root: str, inner: str, raw: bytes) -> None:
    path = os.path.join(root, *inner.split("/"))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as fh:
        fh.write(raw)


def ndfbin_file(kind: str) -> bytes:
    props = [("Name", Str(SOURCE))] + ([("GUID", Value(0x1A, G_OLD))] if kind == "ScenarioInfo" else [])
    return encode(build_graph([Node("TInfo", props)], []), kind)


def tag_file(kind: str) -> bytes:
    pairs = ((Str(f"ScenariosData:/{SOURCE}/Scenario.ndf", 0x1C), Value(0x13, 3)),)
    return encode(build_graph([Node(TAG_CLASS, [("ConfigHash", Value(0x13, 1)), ("SourceFileHashes", Map(pairs))])],
                              []), f"{kind}.{TAG}")


def dbg_file(kind: str) -> bytes:
    return dbg.write([dbg.Line("", f"ScenariosData:/{SOURCE}/Scenario.ndf", 1, 1)])


class TempDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = self.tmp.name

    def tearDown(self):
        self.tmp.cleanup()


class PlanDefinitionTest(TempDirTest):
    def setUp(self):
        super().setUp()
        for kind in ("GDScript", "ScenarioInfo"):
            write(self.root, def_path(kind, TXN, SOURCE), ndfbin_file(kind))
            write(self.root, def_path(kind, TAG, SOURCE), tag_file(kind))
            write(self.root, def_path(kind, DBG, SOURCE), dbg_file(kind))

    def test_rekeys_every_kind_or_ships_the_generated_one(self):
        root = Node("TScript", [("Name", Str(NEW))], export="$/GDScript/RootDescriptor")
        gd = encode(build_graph([root], [root]), "GDScript")
        items = plan_definition(table(), self.root, {"GDScript": (gd, "generated (test)", "GDScript.txt")},
                                transactions)
        self.assertEqual([(it.path, it.action) for it in items],
                         [(def_path("GDScript", TXN, NEW), "generate"), (def_path("GDScript", TAG, NEW), "tag"),
                          (def_path("GDScript", DBG, NEW), "generate"),
                          (def_path("ScenarioInfo", TXN, NEW), "rekey"), (def_path("ScenarioInfo", TAG, NEW), "tag"),
                          (def_path("ScenarioInfo", DBG, NEW), "rekey")])
        self.assertEqual((payload(items[0]), items[0].source, items[0].fixture, items[0].stock),
                         (gd, "generated (test)", "GDScript.txt", None))
        source = GENERATED_SOURCE.format(scenario=NEW, kind="GDScript")
        self.assertEqual(dbg.read(payload(items[2])), [dbg.Line("RootDescriptor", source, 1, 1)])
        self.assertEqual((items[2].fixture, items[2].stock), (None, None))  # no typed dump: not a CNDF file
        info = items[3]
        self.assertEqual(info.stock, ndfbin_file("ScenarioInfo"))
        self.assertTrue(info.source.endswith(def_path("ScenarioInfo", TXN, SOURCE)), info.source)
        nb, _, _ = decode(payload(info))
        self.assertEqual(nb.strings, [NEW.encode()])
        self.assertEqual(dbg.read(payload(items[5])), [dbg.Line("", f"ScenariosData:/{NEW}/Scenario.ndf", 1, 1)])

    def test_without_generated_kinds_every_file_is_rekeyed(self):
        items = plan_definition(table(), self.root, {}, transactions)
        self.assertEqual([it.action for it in items], ["rekey", "tag", "rekey", "rekey", "tag", "rekey"])
        for it in items:   # each tag holds its kind's computed ConfigHash
            if it.path.endswith(".txn.tag"):
                kind = it.path.rsplit("/", 1)[1].split(".")[0]
                self.assertEqual(txntag.read_tag(payload(it))[0],
                                 txntag.config_hash(transactions([it.path[:-4]])[kind]))

    def test_a_kind_without_a_known_transaction_fails(self):
        with self.assertRaisesRegex(CheckError, "no data names the transaction of ScenarioInfo"):
            plan_definition(table(), self.root, {}, lambda entries: {})

    def test_missing_template_file(self):
        with self.assertRaises(OSError):
            plan_definition(table(("GDScript", "ScenarioLoader")), self.root, {}, transactions)


class PlanDetailsTest(TempDirTest):
    def setUp(self):
        super().setUp()
        self.stock, self.other = os.path.join(self.root, "stock"), os.path.join(self.root, "other")
        for folder, files in ((self.stock, {"out/Z.ndfbin": b"zz", "out/C.ndfbin": b"ccc"}),
                              (self.other, {"Cam.ndfbin": b"m"})):
            for inner, raw in files.items():
                write(folder, inner, raw)
            with open(os.path.join(folder, "_provenance.tsv"), "w", encoding="utf-8", newline="") as fh:
                fh.write("".join(f"{inner}\tp.dat\t0\t{len(raw)}\n" for inner, raw in files.items()))

    def test_layout_in_order_generated_or_copied(self):
        layout = [("out/LD.ndfbin", None), ("out/Z.ndfbin", self.stock), ("out/C.ndfbin", self.stock),
                 ("Cam.ndfbin", self.other)]
        items = plan_details(layout, {"out/LD.ndfbin": (b"ld", "generated (items)", "LD.txt"),
                                     "out/C.ndfbin": (b"cz", "generated (zones)", "C.txt")})
        self.assertEqual([(it.path, it.action, payload(it)) for it in items],
                         [("out/LD.ndfbin", "generate", b"ld"), ("out/Z.ndfbin", "copy", b"zz"),
                          ("out/C.ndfbin", "generate", b"cz"), ("Cam.ndfbin", "copy", b"m")])
        self.assertEqual([it.fixture for it in items], ["LD.txt", None, "C.txt", None])

    def test_an_entry_without_a_folder_must_be_generated(self):
        with self.assertRaisesRegex(CheckError, "no stock folder"):
            plan_details([("out/LD.ndfbin", None)], {})


class PlanAssetsTest(TempDirTest):
    RULES = (AssetRule(f"PC/Texture/{SOURCE}/Menu/*.tgv", "copy", "menu pictures"),
             AssetRule("PC/*", "drop", "not referenced"),
             AssetRule(f"Localisation/{SOURCE}/*", "drop", "replaced"))

    def setUp(self):
        super().setUp()
        for inner in (f"PC/Texture/{SOURCE}/Menu/a.tgv", f"PC/Texture/{SOURCE}/Portrait/b.tgv",
                      f"Localisation/{SOURCE}/X-US.dic", "Map/ignored.bin"):
            write(self.root, inner, inner.encode())

    def test_dictionaries_then_rules(self):
        dics = [(f"Localisation/{NEW}/D-US.dic", b"dic", "strings")]
        items, dropped = plan_assets(dics, self.root, ("Localisation", "PC"), self.RULES, SOURCE, NEW)
        self.assertEqual([(it.path, it.action) for it in items],
                         [(f"Localisation/{NEW}/D-US.dic", "generate"), (f"PC/Texture/{NEW}/Menu/a.tgv", "copy")])
        self.assertEqual(payload(items[1]), f"PC/Texture/{SOURCE}/Menu/a.tgv".encode())
        self.assertEqual(dropped, [(f"Localisation/{SOURCE}/X-US.dic", "replaced"),
                                   (f"PC/Texture/{SOURCE}/Portrait/b.tgv", "not referenced")])

    def test_plain_tuples_and_the_first_rule_wins(self):
        rules = [("PC/*", "drop", "first"), ("PC/*", "copy", "second")]
        self.assertEqual(asset_rule("PC/x", rules), ("drop", "first"))
        self.assertEqual(asset_rule("PC/x", self.RULES), ("drop", "not referenced"))

    def test_every_file_needs_a_rule(self):
        with self.assertRaisesRegex(CheckError, "without a rule: Map/ignored.bin"):
            plan_assets([], self.root, ("Map",), self.RULES, SOURCE, NEW)


class MenuArtTest(TempDirTest):
    """A menu picture from another stock scenario, in place of the template's, at the path the MapConfiguration
    names."""
    RULES = (AssetRule(f"PC/Texture/{SOURCE}/MapPackAssets/Textures/*.tgv", "copy", "menu pictures"),)

    def setUp(self):
        super().setUp()
        self.template, self.stock = os.path.join(self.root, "template"), os.path.join(self.root, "stock")
        for name in ("CornerLogo", "MapTexture"):
            write(self.template, MENU_ART.format(SOURCE, name), f"template {name}".encode())
        write(self.stock, MENU_ART.format("challenge_C", "CornerLogo"), b"stock CornerLogo")
        self.items, self.dropped = plan_assets([], self.template, ("PC",), self.RULES, SOURCE, NEW)

    def test_the_stock_picture_ships_at_the_templates_path(self):
        """CornerLogo is challenge_C's, byte for byte, with challenge_C's file as its source, at the path the template's
        re-pathed copy had; MapTexture stays the template's; the template's CornerLogo is listed as given up."""
        items, given_up = menu_art(self.items, {"CornerLogo": ("challenge_C", self.stock)}, SOURCE, NEW)
        self.assertEqual([it.path for it in items], [it.path for it in self.items])
        got = {it.path.rsplit("/", 1)[-1]: it for it in items}
        self.assertEqual(payload(got["CornerLogo.tgv"]), b"stock CornerLogo")
        self.assertEqual(got["CornerLogo.tgv"].action, "copy")
        self.assertTrue(got["CornerLogo.tgv"].source.endswith("/" + MENU_ART.format("challenge_C", "CornerLogo")))
        self.assertEqual(payload(got["MapTexture.tgv"]), b"template MapTexture")
        self.assertEqual(given_up, [(MENU_ART.format(SOURCE, "CornerLogo"),
                                     "menu art: challenge_C's CornerLogo ships in its place")])

    def test_a_generated_picture_ships_at_the_templates_path(self):
        """MapTexture made at build time (OpProfile.menu_art's MenuPicture): its bytes at the template's path,
        generated, with its own source line; the template's MapTexture is listed as given up, after the stock
        pictures."""
        items, given_up = menu_art(self.items, {"CornerLogo": ("challenge_C", self.stock)}, SOURCE, NEW,
                                   {"MapTexture": (b"a new card", "generated (a card)")})
        self.assertEqual([it.path for it in items], [it.path for it in self.items])
        got = {it.path.rsplit("/", 1)[-1]: it for it in items}
        self.assertEqual((payload(got["MapTexture.tgv"]), got["MapTexture.tgv"].action, got["MapTexture.tgv"].source),
                         (b"a new card", "generate", "generated (a card)"))
        self.assertEqual(payload(got["CornerLogo.tgv"]), b"stock CornerLogo")
        self.assertEqual(given_up, [(MENU_ART.format(SOURCE, "CornerLogo"),
                                     "menu art: challenge_C's CornerLogo ships in its place"),
                                    (MENU_ART.format(SOURCE, "MapTexture"),
                                     "menu art: a generated MapTexture ships in its place")])

    def test_no_menu_art_changes_nothing(self):
        items, given_up = menu_art(self.items, {}, SOURCE, NEW)
        self.assertEqual([(it.path, it.digest, it.source) for it in items],
                         [(it.path, it.digest, it.source) for it in self.items])
        self.assertEqual(given_up, [])

    def test_a_picture_the_template_does_not_ship_fails(self):
        with self.assertRaisesRegex(CheckError, r"menu art EndgameBlazon: the template's "
                                                rf"{MENU_ART.format(SOURCE, 'EndgameBlazon')} is not shipped"):
            menu_art(self.items, {"EndgameBlazon": ("challenge_C", self.stock)}, SOURCE, NEW)
        with self.assertRaisesRegex(CheckError, r"menu art EndgameBlazon: the template's "):
            menu_art(self.items, {}, SOURCE, NEW, {"EndgameBlazon": (b"x", "generated")})

    def test_a_missing_stock_picture_fails(self):
        with self.assertRaises(FileNotFoundError):
            menu_art(self.items, {"MapTexture": ("challenge_C", self.stock)}, SOURCE, NEW)


if __name__ == "__main__":
    unittest.main()
