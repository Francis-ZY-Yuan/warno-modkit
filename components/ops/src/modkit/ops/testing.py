"""Helpers for tests that read a generated script back: find nodes, read their properties, follow their timing.

A content's tests build its script (``Content.script(tpl)``) and walk it (``graph.walk``); these helpers name what
they look for. Classes are matched by name substring (``of(nodes, "LDHint")``).
"""
from __future__ import annotations

import contextlib
import io
import os
import shutil

from modkit.core import ndfbin
from modkit.ops.graph import Node, prop_nodes
from modkit.ops.items import Item
from modkit.ops.script import FOREVER

SEQ, SIM, COMP = "TGDDescriptorSequential", "TGDDescriptorSimultaneous", "TGDDescriptorCompetition"


def quiet_build(profile, content, out_dir: str) -> list[Item]:
    """modkit.ops.build.build with its gate report swallowed, so the test output stays clean."""
    from modkit.ops.build import build
    with contextlib.redirect_stdout(io.StringIO()):
        return build(profile, content, out_dir)


def remove_out(out_dir: str) -> None:
    """Delete a test build's folder, and its parent if nothing else is in it."""
    shutil.rmtree(out_dir, ignore_errors=True)
    with contextlib.suppress(OSError):
        os.rmdir(os.path.dirname(out_dir))


def of(nodes: list[Node], part: str) -> list[Node]:
    return [n for n in nodes if part in n.cls]


def prop(node: Node, name: str) -> object:
    return dict(node.props).get(name)


def subs(node: Node) -> list[Node]:
    return prop(node, "SubActions")


def token(v: ndfbin.Value) -> str:
    return ndfbin.token_unhash(int.from_bytes(v.v, "little"))


def hints(nodes: list[Node]) -> list[str]:
    return [token(prop(n, "Info")) for n in of(nodes, "LDHint")]


def last(node: Node) -> str:
    """The last component of a node's export path (a variable's or a tag's name)."""
    return node.export.rsplit("/", 1)[1]


def sets(nodes: list[Node], var: Node) -> list[int]:
    """The constant values the ModifieVariableIntegers among `nodes` set `var` to (Set, no Variable2)."""
    return [prop(n, "Value").v for n in of(nodes, "ModifieVariableInteger")
            if prop(n, "Variable1") is var and prop(n, "Variable2") is None and prop(n, "ModificationType") is None]


def set_values(nodes: list[Node], var: Node) -> list[int]:
    """The values the plain Sets among `nodes` give `var` (a Set to 0 leaves Value out)."""
    return [prop(n, "Value").v if prop(n, "Value") else 0 for n in of(nodes, "ModifieVariableInteger")
            if prop(n, "Variable1") is var and prop(n, "Variable2") is None and prop(n, "ModificationType") is None]


def cmp_of(cond: Node) -> tuple[str, int, int]:
    """(variable name, operator, value) of a bricks.g_cmp condition (Equal 0 when both are omitted)."""
    op = prop(cond, "Operator")
    value, kind = prop(op, "Value"), prop(op, "OperatorType")
    return last(prop(cond, "Variable")), kind.v if kind else 0, value.v if value else 0


def end_game(node: Node) -> tuple[int, int, int | None]:
    """(VictoryReason, VictoryType, WinningAlliance or None) of a TriggerEndGame."""
    winner = prop(node, "WinningAlliance")
    return prop(node, "VictoryReason").v, prop(node, "VictoryType").v, winner.v if winner else None


def objective_named(nodes: list[Node], text: str) -> Node:
    """The one GereObjectif among `nodes` whose ObjectiveText token is `text`."""
    (obj,) = [o for o in of(nodes, "GereObjectif") if token(prop(o, "ObjectiveText")) == text]
    return obj


def parent_of(nodes: list[Node], child: Node) -> Node:
    """The one node among `nodes` that holds `child` in a property."""
    (up,) = [n for n in nodes if any(k is child for _, spec in n.props for k in prop_nodes(spec))]
    return up


def within(seq: Node, *steps: Node) -> list[int]:
    """The indexes of `steps` among the SubActions of Sequential `seq`."""
    kids = prop(seq, "SubActions")
    return [next(i for i, k in enumerate(kids) if k is s) for s in steps]


def least_s(n: Node) -> float:
    """A lower bound on how long `n` runs: its WaitDurations, through Sequentials (times their runs), Simultaneous
    (the longest child) and Competitions (the shortest); anything else counts 0."""
    if n.cls == "TGDDescriptorWaitDuration":
        return prop(n, "Duree").v
    kids = prop(n, "SubActions") if n.cls in (SEQ, SIM, COMP) else None
    if not kids:
        return 0.0
    if n.cls == SEQ:
        return sum(least_s(k) for k in kids) * max(1, prop(n, "NbExecutions").v % FOREVER)
    return (max if n.cls == SIM else min)(least_s(k) for k in kids)


def start_s(n: Node, target: Node, t0: float = 0.0) -> float | None:
    """A lower bound on when `target` starts, counted from `n`'s start (None: not under `n`'s control nodes)."""
    if n is target:
        return t0
    if n.cls == "TGDDescriptorIfThenElse":
        kids = [k for k in (prop(n, "EffetIfTrue"), prop(n, "EffetIfFalse")) if k is not None]
        return next((s for k in kids if (s := start_s(k, target, t0)) is not None), None)
    t = t0
    for k in (prop(n, "SubActions") or []) if n.cls in (SEQ, SIM, COMP) else []:
        s = start_s(k, target, t)
        if s is not None:
            return s
        t += least_s(k) if n.cls == SEQ else 0.0
    return None
