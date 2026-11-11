"""Every example's registered contents (what each example's build.py builds with --content) against each other, and the
menu-order gate on a real build.

`Registered` needs no stock data: each content installed beside the others has its own scenario, GUID, mod folder,
menu-token prefix and Operations menu order (OrderToChainMission) [[content-identity-unique]], and every content outside
the frozen group holds exactly its derived order (modkit.ops.leveldesign.derived_menu_order), so a hand pick fails. The
exceptions are named: the probes' fallbacks (spike_safe and empty share spike's identity and are never installed beside
it), and the frozen group, which shares order 1001 (regression baselines whose builds never change, active one at a
time). `OrderBuild` builds the empty probe with its order moved onto a stock Operation's (the gate fails it) and with
none set (the build derives one); `StockOrders` holds every content's order to stock's. They skip without the
extraction (and the game install, for the builds).
"""
from __future__ import annotations

import dataclasses
import os
import unittest

from open_door_support import GAME, SCRIPT_DATA  # noqa: F401 (puts open-door and the probes on sys.path)
import twin_strike_support  # noqa: F401 (puts twin-strike on sys.path)
from probe_support import OUT_ROOT, quiet_build
from modkit.core import paths
from modkit.core.gates import CheckError
from modkit.ops import build as ops_build
from modkit.ops.gates import stock_menu_orders
from modkit.ops.graph import decode
from modkit.ops.leveldesign import derived_menu_order, scenario_guid
from modkit.ops.rekey import def_path
from modkit.ops.profile import Content
from opendoor import CONTENTS as OPEN_DOOR
from opendoor import profile as open_door_profile
from probes import CONTENTS as PROBES
from probes import empty
from probes import profile as probe_profile
from twinstrike import CONTENTS as TWIN_STRIKE
from twinstrike import profile as twin_strike_profile

# Each example's registered contents and its profile module, by example folder.
EXAMPLES = {"open-door": (OPEN_DOOR, open_door_profile), "probes": (PROBES, probe_profile),
            "twin-strike": (TWIN_STRIKE, twin_strike_profile)}
FALLBACKS = ("probes/spike_safe", "probes/empty")   # spike's identity, never installed beside it
# The frozen group: regression baselines whose builds never change, so their order stays Open Door's 1001. They share
# it, so only one of them is active at a time, and they never ship (publishing one means moving it to its derived order
# first). Every other content holds its derived order.
FROZEN = ("open-door/op", "probes/empty", "probes/spike", "probes/spike_safe", "probes/spike2")
FROZEN_ORDER = 1001
TEST_ID = ("challenge_OpenDoorTest", "OpenDoorTest", "o2")   # probe 2's identity


def registered() -> dict[str, tuple[Content, object]]:
    """{'<example>/<content>': (the content, its example's profile module)} over every example's CONTENTS."""
    return {f"{example}/{name}": (make(), module) for example, (contents, module) in EXAMPLES.items()
            for name, make in contents.items()}


def menu_order(content: Content, module) -> int | None:
    """The OrderToChainMission the content's build writes: the new value of its re-keying's MapConfiguration edit of
    TChallengeMapInfo.OrderToChainMission (the content's own scalar edits, else its profile's, else the derived order
    the build defaults to); None when no edit moves the template's."""
    edits = ops_build.rekey_table(module.profile(), content).scalar_edits
    moved = [e.new.v for e in edits if (e.kind, e.cls, e.prop) ==
             ("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission")]
    return moved[0] if len(moved) == 1 else None


def derived_orders(contents: dict[str, tuple[Content, object]]) -> dict[str, int]:
    """Each content's derived menu order: derived_menu_order of its scenario under its example's GUID namespace."""
    return {key: derived_menu_order(c.scenario, module.GUID_NAMESPACE) for key, (c, module) in contents.items()}


def order_clashes(orders: dict[str, int | None], derived: dict[str, int]) -> list[str]:
    """What breaks the rule: a content without a menu order of its own; a frozen content off FROZEN_ORDER; any other
    content off its derived order (`derived`: a hand pick), on FROZEN_ORDER or on another content's menu order."""
    bad = [f"{key}: no order of its own" for key, order in orders.items() if order is None]
    bad += [f"{key}: {order}, but the frozen group keeps {FROZEN_ORDER}" for key, order in orders.items()
            if key in FROZEN and order != FROZEN_ORDER]
    others = {key: order for key, order in orders.items() if key not in FROZEN and order is not None}
    bad += [f"{key}: {order}, not its derived order {derived[key]}" for key, order in others.items()
            if order != derived[key]]
    bad += [f"{key}: {order}, the frozen group's" for key, order in others.items() if order == FROZEN_ORDER]
    for key, order in others.items():
        bad += [f"{key}: {order}, also {other}'s" for other, theirs in others.items()
                if other != key and theirs == order]
    return bad


class Registered(unittest.TestCase):
    def test_registered_contents_are_distinct(self):
        """Every example's CONTENTS: each installed content has its own scenario, GUID, mod folder and menu token
        prefix; spike_safe is spike's fallback, one mod with it, and empty is never installed. Every content's menu
        order is its derived one, but the frozen group's shared 1001; all are distinct otherwise."""
        contents = registered()
        self.assertEqual(sorted(contents), ["open-door/op", "probes/empty", "probes/nuke", "probes/nuke_sov",
                                            "probes/spike", "probes/spike2", "probes/spike_safe", "twin-strike/op"])
        ids = {}
        for key, (c, module) in contents.items():
            self.assertEqual(c.name, key.split("/")[1])
            ids[key] = (c.scenario, scenario_guid(c.scenario, module.GUID_NAMESPACE), c.mod_name,
                        dict(c.menu_renames)["op13_name"].split("_")[0])
        for key in FALLBACKS:
            self.assertEqual(ids[key], ids["probes/spike"])
        installed = [ids[key] for key in contents if key not in FALLBACKS]
        for k, what in enumerate(("scenario", "GUID", "mod folder", "menu prefix")):
            with self.subTest(what=what):
                self.assertEqual(len({i[k] for i in installed}), len(installed), installed)
        self.assertEqual((ids["probes/spike2"][0], ids["probes/spike2"][2], ids["probes/spike2"][3]), TEST_ID)
        orders = {key: menu_order(c, module) for key, (c, module) in contents.items()}
        self.assertEqual(order_clashes(orders, derived_orders(contents)), [], orders)
        self.assertEqual({key: order for key, order in orders.items() if key in FROZEN}, dict.fromkeys(FROZEN, 1001))

    def test_the_derived_orders_are_pinned(self):
        """The three published contents' orders, pinned so that a change of scheme (the hash, MENU_ORDER_BASE or
        MENU_ORDER_SPAN) shows up in review."""
        orders = {key: menu_order(c, module) for key, (c, module) in registered().items() if key not in FROZEN}
        self.assertEqual(orders, {"probes/nuke": 1157107, "probes/nuke_sov": 8406806, "twin-strike/op": 9348213})
        self.assertEqual(orders, {key: d for key, d in derived_orders(registered()).items() if key in orders})

    def test_a_taken_order_breaks_the_rule(self):
        """The rule fails a hand pick (Twin Strike on TS5's 1002), Twin Strike on 1001, a new content on another's
        order, and a frozen content moved."""
        contents = registered()
        orders = {key: menu_order(c, module) for key, (c, module) in contents.items()}
        derived = derived_orders(contents)
        nuke = orders["probes/nuke"]
        self.assertEqual(order_clashes({**orders, "twin-strike/op": 1002}, derived),
                         [f"twin-strike/op: 1002, not its derived order {derived['twin-strike/op']}"])
        self.assertEqual(order_clashes({**orders, "twin-strike/op": 1001}, derived),
                         [f"twin-strike/op: 1001, not its derived order {derived['twin-strike/op']}",
                          "twin-strike/op: 1001, the frozen group's"])
        self.assertEqual(order_clashes({**orders, "new/op": nuke}, {**derived, "new/op": nuke}),
                         [f"probes/nuke: {nuke}, also new/op's", f"new/op: {nuke}, also probes/nuke's"])
        self.assertEqual(order_clashes({**orders, "probes/spike2": 1005}, derived),
                         ["probes/spike2: 1005, but the frozen group keeps 1001"])

    def test_a_content_carries_its_own_order(self):
        """Content.scalar_edits replaces the profile's in the re-keying: the nuke probes carry their derived orders,
        the frozen group carries none and takes the profile's MENU_ORDER, and Twin Strike's profile derives its own. A
        content whose edits move no order gets the derived one from the build (ops_build.scalar_edits)."""
        nuke = PROBES["nuke"]()
        mine = derived_menu_order(nuke.scenario, probe_profile.GUID_NAMESPACE)
        self.assertEqual(nuke.scalar_edits, probe_profile.scalar_edits(mine))
        self.assertEqual(ops_build.rekey_table(probe_profile.profile(), nuke).scalar_edits,
                         probe_profile.scalar_edits(mine))
        for key in ("probes/empty", "probes/spike", "probes/spike_safe", "probes/spike2"):
            with self.subTest(content=key):
                self.assertIsNone(PROBES[key.split("/")[1]]().scalar_edits)
        self.assertEqual(probe_profile.SCALAR_EDITS, probe_profile.scalar_edits(probe_profile.MENU_ORDER))
        self.assertEqual((probe_profile.MENU_ORDER, twin_strike_profile.MENU_ORDER),
                         (1001, derived_menu_order(twin_strike_profile.SCENARIO, twin_strike_profile.GUID_NAMESPACE)))
        unset = dataclasses.replace(nuke, scalar_edits=probe_profile.SCALAR_EDITS[1:])   # the Duration edit only
        self.assertEqual(menu_order(unset, probe_profile), mine)


@SCRIPT_DATA
@GAME
class OrderBuild(unittest.TestCase):
    def test_a_stock_order_fails_the_build(self):
        """The empty probe with its order moved onto a stock Operation's (DelayedRetribution's 997) fails the
        menu-order gate in the game's words, naming derived_menu_order as the fix, before anything is written."""
        out = os.path.join(OUT_ROOT, "bad-order-997")
        with self.assertRaisesRegex(CheckError, r"OrderToChainMission 997 is the menu order of the stock Operation "
                                                r"challenge_DelayedRetribution\. .*"
                                                r'"Duplicate OrderToChainMission 997": '
                                                r"give this Operation its derived menu order \(modkit\.ops\."
                                                r"leveldesign\.derived_menu_order"):
            quiet_build(dataclasses.replace(empty.content(), scalar_edits=probe_profile.scalar_edits(997)), out)
        self.assertFalse(os.path.exists(out))

    def test_none_set_builds_with_the_derived_order(self):
        """The empty probe with no order edit (the Duration edit only) builds, every gate passing, and its
        MapConfiguration holds its derived order in place of Survivors' 130."""
        base = empty.content()
        duration = tuple(e for e in probe_profile.SCALAR_EDITS if e.prop != "OrderToChainMission")
        out = os.path.join(OUT_ROOT, "derived-order")
        items = quiet_build(dataclasses.replace(base, scalar_edits=duration), out)
        inner = def_path("MapConfiguration", "ndfbin", base.scenario)
        (mc,) = [it for it in items if it.pack == "Definition" and it.path == inner]
        nb = decode(b"".join(mc.chunks()))[0]
        orders = [v.v for ob in nb.objects for pi, v in ob.props if nb.pname(pi) == "OrderToChainMission"]
        self.assertEqual(orders, [derived_menu_order(base.scenario, probe_profile.GUID_NAMESPACE)])


@paths.skip_unless_extracted("scenarios")
class StockOrders(unittest.TestCase):
    def test_every_examples_order_is_free_of_stock(self):
        """No registered content's order is a stock Operation's (each build's menu-order gate holds it as well)."""
        stock = stock_menu_orders()
        orders = {key: menu_order(c, module) for key, (c, module) in registered().items()}
        self.assertEqual({key: order for key, order in orders.items() if order in stock}, {})


if __name__ == "__main__":
    unittest.main()
