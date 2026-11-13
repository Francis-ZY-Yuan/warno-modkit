"""The empty probe: the smallest op the profile builds, to prove the clone itself loads.

Two Name tags and one player Abrams. Its script is modkit.ops.script.hold_script with the SetDeck block and no waves:
an intro dialog, then hold NECK MID for 10 minutes; losing the Abrams fails it. No deployment phase. It shares probe
1's identity and is never installed beside it.
"""
from __future__ import annotations

from modkit.core import ndfbin
from modkit.core.models import StringTable, Texts
from modkit.ops.graph import Node
from modkit.ops.leveldesign import gd_tags
from modkit.ops.profile import Content
from modkit.ops.script import BRICK_FORCE_HIDE, hold_script
from modkit.ops.shapes import camp_nodes, setdeck_block
from probes import profile
from probes.geisa import MAP


def content(scenario: str = profile.SCENARIO, mod_name: str = profile.MOD_NAME) -> Content:
    """The empty op under the identity `scenario` in `mod_name` (probe 1's by default)."""
    items = (
        MAP.item("Tags", "OD_TownNE", "TOWN_NE", "Name"),
        MAP.item("Tags", "OD_NeckMid", "NECK_MID", "Name"),
        MAP.item("Camp_0", "OD_P_Abrams", "NECK_MID", "Spawn", unit="M1A1HA_Abrams_US"),
    )
    title = Texts(US="Open Door: empty build", SC="开门行动：空构建")
    strings: StringTable = {
        "SCENARIO_DEFINITION": {token: title for token in profile.MENU_TOKENS},
        "Scripting/Dialog": {
            "od_intro": Texts(US="Open Door: empty build. One M1A1HA holds NECK MID for 10 minutes.",
                              SC="开门行动：空构建。一辆M1A1HA坚守NECK MID十分钟。"),
        },
        "Scripting/Localization": {
            "od_obj": Texts(US="PRIMARY: HOLD NECK MID", SC="主要目标：坚守NECK MID"),
            "od_objl": Texts(US="Hold for %1", SC="坚守%1"),
            "od_cnato": Texts(US="NATO", SC="北约"),
            "od_cdecoy": Texts(US="NATO decoys", SC="北约佯动部队"),  # 诱饵 (decoy) is outside the stock SC set
            "od_cddr": Texts(US="NVA", SC="东德军"),
            "od_csov": Texts(US="Soviet Army", SC="苏军"),
        },
    }

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

    return profile.content("empty", items, script, strings, profile.MENU_TOKENS, scenario=scenario, mod_name=mod_name)
