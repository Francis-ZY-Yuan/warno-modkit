"""The probe mods: small Operation mods that each verify a set of game mechanisms in one play session.

CONTENTS maps each `--content` name to a function making its Content. Each installs under its own identity (scenario,
GUID, mod folder, menu token prefix), but spike_safe (spike's fallback: one mod with spike, install one or the other)
and empty (never installed beside them). nuke and nuke_sov are probe 3: each has its own identity, as
fxprobe (every strike effect) has.
"""
from __future__ import annotations

from typing import Callable

from modkit.ops.profile import Content
from probes import empty, fxprobe, nuke, spike, spike2

CONTENTS: dict[str, Callable[[], Content]] = {
    "empty": empty.content,
    "spike": spike.content,
    "spike_safe": lambda: spike.content(safe=True),
    "spike2": spike2.content,
    "nuke": nuke.content,
    "nuke_sov": lambda: nuke.content("nuke_sov"),
    "fxprobe": fxprobe.content,
}
