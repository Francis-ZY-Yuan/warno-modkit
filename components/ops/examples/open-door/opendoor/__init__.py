"""Operation Open Door: a playable Operation mod for WARNO built from stock parts.

CONTENTS maps each `--content` name to a function making its Content: `op`, the mission (opendoor.op).
"""
from __future__ import annotations

from typing import Callable

from modkit.ops.profile import Content
from opendoor import op

CONTENTS: dict[str, Callable[[], Content]] = {
    "op": op.content,            # challenge_OperationOpenDoor in OpenDoor
}
