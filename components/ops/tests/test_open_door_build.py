"""Tests for the Open Door example as a whole: its front end with nothing configured, its identity beside the probes,
and the op's build through Open Door's profile, every gate included.

`Build` builds the op into a temporary folder (and the "fixed" tier mode beside it) and removes them
afterwards. Classes that read the stock extraction or the game install skip without them.
"""
from __future__ import annotations

import contextlib
import io
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid

from modkit.core import edat, ndfbin
from modkit.core.models import Texts
from modkit.ops import build as ops_build
from modkit.ops.graph import all_values, decode
from modkit.ops.rekey import TXN, def_path
from modkit.ops.testing import remove_out
from open_door_support import GAME, OPEN_DOOR, OUT_ROOT, SCRIPT_DATA, build_main, scenario_guid
from opendoor import CONTENTS, profile
from opendoor import op as mission
from probes import CONTENTS as PROBES
from probes import profile as probe_profile
from probes import spike2 as probe2

OUT = os.path.join(OUT_ROOT, "op")
OUT_FIXED = os.path.join(OUT_ROOT, "op_fixed")


class LazyPaths(unittest.TestCase):
    def test_unconfigured_import_and_build(self):
        """Importing the example resolves no path; build.py with neither the extraction nor the game folder
        configured prints one FAILED line naming warno-setup and exits 1, no traceback, nothing written."""
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            code = textwrap.dedent(f"""
                import runpy, sys
                from modkit.core import paths
                paths._code_dirs = lambda: []          # only the working folder (empty) is searched
                sys.path.insert(0, {str(OPEN_DOOR)!r})
                import opendoor, opendoor.forces, opendoor.map, opendoor.op, opendoor.profile, opendoor.strings
                sys.argv = ["build.py", "--content", "op", "--out", {out!r}]
                runpy.run_path({str(OPEN_DOOR / "build.py")!r}, run_name="__main__")
            """)
            env = {k: v for k, v in os.environ.items() if not k.startswith("MODKIT_")}
            r = subprocess.run([sys.executable, "-c", code], cwd=tmp, env=env, capture_output=True, text=True,
                               encoding="utf-8", errors="replace")
            self.assertEqual(r.returncode, 1, r.stdout + r.stderr)
            self.assertNotIn("Traceback", r.stderr)
            (line,) = r.stderr.strip().splitlines()
            self.assertTrue(line.startswith("FAILED: ") and "warno-setup" in line, line)
            self.assertFalse(os.path.exists(out))


class Identity(unittest.TestCase):
    def test_identity(self):
        """challenge_OperationOpenDoor in OpenDoor, uuid5 GUID under warno-opendoor, menu prefix o3, title "Operation
        Open Door" / 开门行动."""
        c = mission.content()
        self.assertEqual(sorted(CONTENTS), ["op"])
        self.assertEqual((c.name, c.scenario, c.mod_name), ("op", "challenge_OperationOpenDoor", "OpenDoor"))
        self.assertEqual((c.scenario, c.mod_name), (profile.SCENARIO, profile.MOD_NAME))
        self.assertEqual(scenario_guid(c.scenario),
                         uuid.uuid5(uuid.NAMESPACE_URL, "warno-opendoor/challenge_OperationOpenDoor").bytes)
        self.assertEqual(c.menu_renames, tuple((f"op13_{k}", f"o3_{k}") for k in
                                               ("name", "order", "headr", "cname", "recap", "vic", "def")))
        self.assertEqual(c.menu_tokens, tuple(dict(c.menu_renames).values()))
        self.assertEqual(sorted(mission.STRINGS["SCENARIO_DEFINITION"]), sorted(c.menu_tokens))
        self.assertEqual(mission.STRINGS["SCENARIO_DEFINITION"]["o3_name"], Texts(US="Operation Open Door", SC="开门行动"))
        self.assertEqual(CONTENTS["op"]().scenario, profile.SCENARIO)

    def test_installs_beside_the_probes(self):
        """The op and every installed probe have their own scenario, GUID, mod folder and menu token prefix
        [[content-identity-unique]] (spike_safe is spike's fallback, one mod with it, and empty is never installed)."""
        ids = {}
        for name, make in (*CONTENTS.items(), *PROBES.items()):
            c = make()
            self.assertEqual(c.name, name)
            ids[name] = (c.scenario, scenario_guid(c.scenario), c.mod_name,
                         dict(c.menu_renames)["op13_name"].split("_")[0])
        installed = [ids[name] for name in ids if name not in ("spike_safe", "empty")]
        for k, what in enumerate(("scenario", "GUID", "mod folder", "menu prefix")):
            with self.subTest(what=what):
                self.assertEqual(len({i[k] for i in installed}), len(installed), installed)
        self.assertEqual(ids["op"][0::2], ("challenge_OperationOpenDoor", "OpenDoor"))
        tokens = set(mission.content().menu_tokens)
        self.assertFalse(tokens & (set(probe_profile.MENU_TOKENS) | set(probe2.MENU_TOKENS)))

    def test_extra_gates(self):
        """Open Door's gates beyond the driver's, by name (the keys a reviewed-pending entry would use)."""
        self.assertEqual([g.name for g in profile.EXTRA_GATES], ["units", "no-template-name", "grid", "zone-layout",
                                                                 "menu-order"])
        self.assertEqual(profile.profile().extra_gates, profile.EXTRA_GATES)
        self.assertEqual(profile.profile().reviewed_pending, {})


@SCRIPT_DATA
@GAME
class Build(unittest.TestCase):
    def test_op_builds(self):
        """`--content op` ("tiered") passes every gate, the extra gates included, and writes OpenDoor with
        challenge_OperationOpenDoor packs, whose MapConfiguration carries the o3_* menu tokens and the scenario's
        GUID."""
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                self.assertEqual(build_main(["--content", "op", "--out", OUT]), 0)
            log = out.getvalue()
            self.assertIn("gate 3 tiers: 5 tiered reinforcement locations", log)
            self.assertIn("7 player reinforcement locations and 2 aerial corridors", log)
            # The endings' 20; per town: TeamControleZone, the race's 4 UnitDansZone, the hand-over; H+12's 3; phase
            # 2's: B6's contact (2 + 2 necks), the emptied necks (2), their hand-over (2), the anvil contested (3);
            # per neck: the seal race's 4 UnitDansZone, the hand-over. Circles: the rear exit's, the sack's five, B6's
            # approaches (2 + 2); four rounds of the sack's five (the seal, the pocket loop, the captured, the
            # removed).
            self.assertIn("62 zone lookups each in exactly one shipped polygon, 30 detectors on circles, 13 zone items "
                          "inside their own polygon, 8 command zones apart", log)   # 5 deployment zones, 8 command
            self.assertIn("3 smart-ordered groups, none ordered again after its smart order in a Sequential", log)
            self.assertIn("6 TriggerEndGame, each under $/GDScript/OD/EndFunnel", log)
            self.assertIn("11 dialog texts without %1..%9", log)
            self.assertIn("9 objectives (0 reviewed to hold their Sequential), none with a node after it", log)
            self.assertIn("3 dialog-button tokens in the game's INGAME dictionary", log)   # SI_NEXT and the spring's
            self.assertIn("+ 1 admitted", log)                                      # the Rifles card's Transporter
            self.assertIn("gate 3 units: 45 unit descriptors exist", log)
            # 47: the Definition pack's 12 (4 kinds, each a .txn, .txn.tag and .dbg), Details' 7, Assets' 28. 14 read:
            # the 11 Definition entries with a fixture or stock bytes (the generated GDScript .dbg has neither) and the
            # 3 generated Details files.
            self.assertIn("gate 5 package: all 47 entries lie under challenge_OperationOpenDoor; no Gameplay file", log)
            self.assertIn("gate 3 no-template-name: 14 re-keyed or generated dumps without Survivors", log)
            self.assertIn("gate 3 grid: 294 AI tiles and 86,142 path costs under the shipped playable zone", log)
            self.assertIn("gate 3 zone-layout: 13 zones and 9 arrivals laid out by stock's rules", log)
            packs = sorted(os.listdir(os.path.join(OUT, "OpenDoor", "Scenarios")))
            self.assertEqual(packs, [f"{profile.SCENARIO}_{p}.dat" for p in ("Assets", "Definition", "Details")])
            dat = os.path.join(OUT, "OpenDoor", "Scenarios", "challenge_OperationOpenDoor_Definition.dat")
            (entry,) = [e for e in edat.read_index(dat)
                        if e.path == def_path("MapConfiguration", TXN, "challenge_OperationOpenDoor")]
            nb, _, _ = decode(edat.read_entry(dat, entry))
            tokens = {ndfbin.token_unhash(int.from_bytes(x.v, "little")) for _, _, x in all_values(nb)
                      if x.tag == 0x1D}
            self.assertLessEqual(set(profile.MENU_TOKENS), tokens)
            self.assertEqual([x.v for _, _, x in all_values(nb) if x.tag == 0x1A],
                             [scenario_guid(profile.SCENARIO)])
        finally:
            remove_out(OUT)
        self.assertFalse(os.path.exists(OUT))

    def test_fixed_builds(self):
        """The "fixed" fallback still builds and passes every gate: no tiered entry, each tier End in its own player
        deployment zone (18 zone items: 10 deployment zones, 8 command)."""
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out):
                ops_build.build(profile.profile(), mission.content("fixed"), OUT_FIXED)
            log = out.getvalue()
            self.assertIn("gate 3 tiers: 0 tiered reinforcement locations", log)
            self.assertIn("7 player reinforcement locations and 2 aerial corridors", log)
            self.assertIn("62 zone lookups each in exactly one shipped polygon, 30 detectors on circles, 18 zone items "
                          "inside their own polygon, 8 command zones apart", log)
            self.assertIn("gate 3 zone-layout: 18 zones and 9 arrivals", log)
            self.assertIn("gate 6 packs read back", log)
            self.assertTrue(os.path.isdir(os.path.join(OUT_FIXED, "OpenDoor", "Scenarios")))
        finally:
            remove_out(OUT_FIXED)
        self.assertFalse(os.path.exists(OUT_FIXED))


if __name__ == "__main__":
    unittest.main()
