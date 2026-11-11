"""Operation Twin Strike: the toolkit's showcase Operation, a Soviet player against a NATO AI on a cut of Twin Cities.

The design is docs/design.md. The package holds the map (twinstrike.map), the forces (twinstrike.forces), the strings
(twinstrike.strings), the profile (twinstrike.profile) and the op (twinstrike.op): its frame, every unit in place, and
its mission, the five phases, the division's fires, the strike, the difficulty and the endings.

CONTENTS maps each `--content` name to a function making its Content: `op`, the op (twinstrike.op).
"""
from __future__ import annotations

from typing import Callable

from modkit.ops.profile import Content
from twinstrike import op

CONTENTS: dict[str, Callable[[], Content]] = {
    "op": op.content,            # challenge_OperationTwinStrike in TwinStrike
}
