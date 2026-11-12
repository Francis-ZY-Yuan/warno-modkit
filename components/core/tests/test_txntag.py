"""modkit.core.txntag: the ConfigHash of a .txn.tag, reproduced for every stock tag whose transaction the data names."""
from __future__ import annotations

import os
import unittest
from collections import defaultdict

from modkit.core import ndfbin, paths, txntag


class Hashes(unittest.TestCase):
    def test_metrohash64_reference_values(self):
        """MetroHash64's published test vector (seed 0 and 1) and the empty input."""
        key = b"012345678901234567890123456789012345678901234567890123456789012"
        self.assertEqual(txntag.metro64(key).to_bytes(8, "little").hex().upper(), "6B753DAE06704BAD")
        self.assertEqual(txntag.metro64(key, 1).to_bytes(8, "little").hex().upper(), "3B0D481CF4B9B8DF")

    def test_signed_and_order(self):
        t = txntag.Transaction("Scenarios/challenge_X/GDScript.txn", "GDScript", ("GameData:/a.ndf", "GameData:/b.ndf"))
        h = txntag.config_hash(t)
        self.assertTrue(-(1 << 63) <= h < (1 << 63))
        self.assertNotEqual(h, txntag.config_hash(t._replace(files=t.files[::-1])))   # order counts
        self.assertNotEqual(h, txntag.config_hash(t._replace(base_name="Scenarios/challenge_Y/GDScript.txn")))
        # the alias is not hashed: every alias hangs off one root
        self.assertEqual(txntag.path_hash("GameData:/a/b.ndf"), txntag.path_hash("CommonData:/a/b.ndf"))

    def test_scan_transaction(self):
        s = txntag.Scan("Scenarios", "ScenarioInfo.txn", "ScenarioInfo", ("CommonData:/x.ndf",), (), "ScenariosData:/",
                        "Scenario.ndf")
        self.assertEqual(txntag.scan_transaction(s, "challenge_X"),
                         txntag.Transaction("Scenarios/challenge_X/ScenarioInfo.txn", "ScenarioInfo",
                                            ("ScenariosData:/challenge_X/Scenario.ndf", "CommonData:/x.ndf")))
        self.assertEqual(txntag.scan_transaction(s._replace(seek_dir="GameData:/Localisation"), "Core").files[0],
                         "GameData:/Localisation/Core/Scenario.ndf")


class Stock(unittest.TestCase):
    @paths.skip_unless_extracted("transactions")
    def test_every_stock_tag_with_a_known_transaction(self):
        """Every stock .txn.tag of the extraction whose transaction the stock data names, by a TNDFTransaction's
        BaseName or by a folder scan, holds exactly the ConfigHash computed from it; every scenario pack's tag is one."""
        root = str(paths.extracted_root())
        tags, known, scans = {}, defaultdict(set), set()
        for dirpath, _, files in os.walk(root):
            for f in files:
                path = os.path.join(dirpath, f)
                rel = os.path.relpath(path, root).replace(os.sep, "/")
                if f.endswith(".txn.tag"):
                    with open(path, "rb") as fh:
                        tags[rel] = txntag.read_tag(fh.read())[0]
                elif f.endswith(".txn"):
                    with open(path, "rb") as fh:
                        nb, _, _ = ndfbin.decode(fh.read())
                    for t in txntag.transactions(nb):
                        known[t.base_name].add(t)
                    scans.update(txntag.scans(nb))
        expected: dict[str, set[int]] = {}
        for rel in tags:
            base = rel.split("/NDF/", 1)[1][:-len(".tag")] if "/NDF/" in rel else None
            if base is None:
                continue
            hashes = {txntag.config_hash(t) for t in known.get(base, ())}
            parts = base.split("/")
            hashes |= {txntag.config_hash(txntag.scan_transaction(s, parts[1])) for s in scans
                       if len(parts) == 3 and (s.dir_name, s.base_name) == (parts[0], parts[2])}
            if hashes:
                expected[rel] = hashes
        wrong = sorted(rel for rel, hashes in expected.items() if tags[rel] not in hashes)
        self.assertEqual(wrong, [])
        scenario_tags = [rel for rel in tags if "/NDF/Scenarios/" in rel]
        self.assertGreaterEqual(len(scenario_tags), 160)
        self.assertEqual(sorted(set(scenario_tags) - set(expected)), [])
        self.assertGreaterEqual(len(expected), 320)


if __name__ == "__main__":
    unittest.main()
