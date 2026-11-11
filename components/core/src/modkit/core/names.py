"""Names the toolkit gives things in the game's data: a unit descriptor's export path, and stable GUIDs.

A generated object needs a GUID that stays the same from build to build, so that a rebuild (after a game patch, say)
writes the same bytes: ``name_guid`` is uuid5 of a name under the mod's own namespace, never a fresh uuid4. Each mod
picks its own namespace, so two mods never share a GUID.
"""
from __future__ import annotations

import uuid


def unit_path(name: str) -> str:
    """The export path of the unit descriptor `name`: ``$/GFX/Unit/Descriptor_Unit_<name>``."""
    return f"$/GFX/Unit/Descriptor_Unit_{name}"


def name_guid(namespace: str, name: str) -> bytes:
    """The GUID of `name` under the mod's `namespace`, as stored (uuid.bytes, tag 0x1A):
    uuid5(NAMESPACE_URL, '<namespace>/<name>')."""
    return uuid.uuid5(uuid.NAMESPACE_URL, f"{namespace}/{name}").bytes
