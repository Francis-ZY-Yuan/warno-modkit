"""The empty probe: the smallest op the profile builds, to prove the clone itself loads.

Two Name tags and one player Abrams. Its script is modkit.ops.script.hold_script with the SetDeck block and no waves:
an intro dialog, then hold NECK MID for 10 minutes; losing the Abrams fails it. No deployment phase. It shares probe
1's identity and is never installed beside it.
"""
from __future__ import annotations

from pathlib import Path

from modkit.core import ndfbin
from modkit.ops.graph import Node
from modkit.ops.leveldesign import gd_tags
from modkit.ops.profile import Content
from modkit.ops.script import BRICK_FORCE_HIDE, hold_script
from modkit.ops.shapes import camp_nodes, setdeck_block
from modkit.ops.strings import load
from probes import profile
from probes.geisa import MAP

TABLE = Path(__file__).with_name("empty.strings.toml")   # its texts, per token and language (load)


def content(scenario: str = profile.SCENARIO, mod_name: str = profile.MOD_NAME) -> Content:
    """The empty op under the identity `scenario` in `mod_name` (probe 1's by default)."""
    items = (
        MAP.item("Tags", "OD_TownNE", "TOWN_NE", "Name"),
        MAP.item("Tags", "OD_NeckMid", "NECK_MID", "Name"),
        MAP.item("Camp_0", "OD_P_Abrams", "NECK_MID", "Spawn", unit="M1A1HA_Abrams_US"),
    )
    def script(tpl: ndfbin.NdfBin) -> tuple[list[Node], list[Node]]:
        tags = gd_tags(items, scenario, profile.GUID_NAMESPACE)
        player_tags = [tags[f"{it.ranking}/{it.name}"] for it in items
                       if it.addon == "Spawn" and not it.camp and not it.disable_auto_spawn]
        camps = camp_nodes(profile.CAMP_ROWS, profile.CAMP_TOKENS)
        return hold_script(tpl, profile.TEMPLATES, folder=profile.FOLDER, camps=list(camps.values()),
                           setup=setdeck_block(camps, profile.CAMP_ROWS),                  # S#117-#120
                           tags=tags, player_tags=player_tags, hold_at=tags["Tags/OD_NeckMid"], hold_s=600,
                           intro="od_intro", objective=("od_obj", "od_objl"), start_delay_s=profile.START_DELAY_S,
                           parallel=[], variables=[], prod_menu_switch=BRICK_FORCE_HIDE)  # its Content's default

    return profile.content("empty", items, script, load(TABLE), profile.MENU_TOKENS, scenario=scenario, mod_name=mod_name)
