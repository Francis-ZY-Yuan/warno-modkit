"""Where the probes put things on Geisa, and the force rows they create.

The probes have no place or force row of their own: every one they use, Open Door uses too, so both read the shared
tables. POINTS are modkit.ops.maps.GEISA_POINTS, named positions in minimap pixels (768 x 1024;
modkit.ops.maps.GEISA.px_to_world gives world units). ROWS are modkit.ops.forces.GEISA_SOVIET_ROWS, the force rows the
probes create at 1x: probe 1's battery, recon probe, air defence and stress wave.
"""
from __future__ import annotations

from modkit.ops.forces import GEISA_SOVIET_ROWS
from modkit.ops.maps import GEISA, GEISA_POINTS
from modkit.ops.shapes import Minimap

POINTS = GEISA_POINTS
MAP = Minimap(GEISA, POINTS)
ROWS = GEISA_SOVIET_ROWS
FORCE_SCALE = 1.0                    # the probes' scale knob: every row but probe 1's stress wave is at 1x
