"""Probe: strike effects (`fxprobe`): every way a script can make a strike look massive and visible, on one target
group, in one timed run, the riskiest step last.

The player is Soviet (the stock Soviet-player camp shape, as nuke_sov) and the targets are NATO. Every step runs on the
battle clock (seconds after "Launch battle"); each step's hint shows LEAD_S before it acts and names it, so a crash
points at the step its hint named. Each step is its own branch: one that stalls hides no other.

  F1  0:15  the targets: 6 M1A1HA Abrams and 6 M2A2 Bradleys at T, kept off their camp's AI and emptied of
            ammunition, pinned on the map; nothing of the player's sees them yet
  F2  0:40  the camera flies from where the player has it to Geisa's stock one-key path Camp1, over T, in
            CAMERA_S (stock's mid-battle look, SigurdsStrike's MLRS: StartFromCurrentCameraPosition; Escape skips)
  F3  1:05  fog off (TGDDescriptorFow, no stock use): the targets should show with nothing of the player's near
  F3b 1:25  3 BRDM-2 of the player's at V, 360 m from T: vision if the fog did not lift
  F4  1:50  the proven effects massed, RedJuggernaut's scale: 10 mega bombs (T and a ring of 9 at 300 m), the 203 mm
            random barrage 10 times at 5 tags (50), white smoke and black smoke at 4 tags each
  F5  2:20  40 % of the targets killed with Penetration (a TransferUnitToUnitGroup subgroup, then KillAllUnit)
  F6  2:45  the survivors damaged: ChangeStress with DamageType Physical, DAMAGE_VALUE of their 10 hit points
  F7  3:10  the survivors stunned: ChangeStress with DamageType Stun, STRESS_VALUE [[changestress-damagetype-zero]]
  F8  3:40  the game's tactical-nuke impact effect through the script's own wrapper (bricks.fx_wrapper): parPosition 0,
            on T
  F9  4:10  the same at U, with parPosition the tag's world position
  F10 4:45  fog back on; probe done

The nuke's wrapper is the shape of stock's fx_FumeeNoire_ForScript_RandomPosition: a TSimultaneousAction whose
TActionCall binds every parameter the effect declares with no default; the script-effects gate holds it to that
[[script-effects-self-contained]] [[scripted-nuke-effect]]. The play sheet is in README.md (fxprobe).
"""
from __future__ import annotations

import math
from typing import NamedTuple

from modkit.core import ndfbin
from modkit.ops import script as ops_script
from modkit.ops.bricks import (
    g_ammo, g_camera, g_cmp, g_count, g_fow, g_fx, g_hint, g_if, g_ignored, g_kill, g_modify, g_seq,
    g_set, g_simul, g_stress, g_wait, unit_path,
)
from modkit.ops.graph import Node, i32
from modkit.ops.leveldesign import LdItem, derived_menu_order
from modkit.ops.maps import GEISA
from modkit.ops.mission import script_frame
from modkit.ops.profile import SOVIET_PLAYER_CAMP_ROWS, SOVIET_PLAYER_DECK_SWAP, SOVIET_PLAYER_SIDES, Content
from modkit.ops.script import BRICK_FORCE_HIDE
from modkit.ops.shapes import (
    DEATH_CAUSE_SHAPE, DIVIDE, FOW_SHAPES, FX_WRAPPER_SHAPES, HINT_S, PENETRATION, PHYSICAL, STRESS_SHAPES,
    STRICTLY_LESS, STUN, TACTICAL_NUKE_FX, Beat, camp_nodes, create, nuke_wrapper, objective,
)
from modkit.ops.shapes import Ctx as ShapesCtx
from modkit.ops.strings import Table
from probes import profile, spike
from probes.geisa import MAP

# --------------------------------------------------------------------------- identity

NAME, PREFIX = "fxprobe", "fx"
SCENARIO, MOD_NAME = "challenge_OpenDoorFx", "OpenDoorFx"
SIDES, PLAYER, TARGET_SIDE = SOVIET_PLAYER_SIDES, "Soviet", "NATO"
CAMP_NAMES = {"joueur": ("Soviet Army", "苏军"), "Allie": ("Soviet ally", "苏军盟军"), "ordinateur_DDR": ("NATO", "北约"),
              "ordinateur_SOV": ("NATO", "北约")}
CAMP_TOKENS = {name: f"{PREFIX}_camp{k}" for k, name in enumerate(CAMP_NAMES)}

# --------------------------------------------------------------------------- places (Geisa minimap px; 1 px is 11.9 m)

# T: the open fields east of the player's deployment zone (spike.DZ_W ends at x 540), between probe 3's two victim
# points (596, 300) and (646, 300) and its empty target spot (621, 345). Geisa's stock camera path Camp1 looks at
# (631, 373), 43 px (510 m) south of T, from 489,440 above the ground: T, U and V all sit in its view.
T_PX = (626.0, 330.0)
U_PX = (676.0, 330.0)                # F9's tag, 50 px (595 m) east of T, so F8's dust does not hide it
V_PX = (596.0, 345.0)                # the player's vision, 34 px (400 m) west-south-west of T
RING_PX, RING_N = 25.0, 9            # F4's ring of tags round T: 25 px (300 m), 9 of them
RING = tuple((T_PX[0] + RING_PX * math.cos(2 * math.pi * k / RING_N), T_PX[1] + RING_PX * math.sin(2 * math.pi * k / RING_N))
             for k in range(RING_N))
CAMERA_PATH, CAMERA_S = "Camp1", 4.0  # Geisa's stock one-key path (GEISA.copies ships its camera paths file as is)

# --------------------------------------------------------------------------- forces and knobs

TARGETS = (("M1A1HA_Abrams_US", 6), ("M2A2_Bradley_IFV_US", 6))
VISION_UNIT, VISION_COUNT = "BRDM_2_SOV", 3
KILL_NUM, KILL_DEN = 2, 5            # F5 kills count x 2 / 5 of the targets, rounded down: 4 of 12 (40 %)
TRANSFER_CAP = 20                    # the one-unit transfer loop's bound (spike's check 6 shape)
DAMAGE_VALUE = 5                     # F6: ChangeStress Physical, 5 of a vehicle's 10 hit points (MaxPhysicalDamages)
STRESS_VALUE = spike.STRESS_VALUE    # F7: 240, 0.8 of the ground-unit stun cap, as probe 1's check 6
MULTIPLY = 3                         # EVariableIntegerModification Multiply
LEAD_S = 5.0                         # each step's hint shows this long before the step acts

FX_MEGA = "$/GFX/GameFx/fx_HE_Mega_Bomb_ForScript"
FX_HE = spike.FX_BOMB                # fx_HE_Artillery_203mm_ForScript_RandomPosition
FX_WHITE = "$/GFX/GameFx/fx_FumeeBlanche_ForScript_RandomPosition"
FX_BLACK = "$/GFX/GameFx/fx_FumeeNoire_ForScript_RandomPosition"
HE_RUNS = 10                         # RedJuggernaut's all_impact: Sequential(NbExecutions 10)[203 mm] at 5 tags
HE_TAGS = ("FX_T", "FX_R1", "FX_R3", "FX_R5", "FX_R7")
SMOKE_TAGS = ("FX_R2", "FX_R4", "FX_R6", "FX_R8")

# The real nuke: the game's tactical-nuke impact effect, whose 4 parameters have no default, called through the
# script's own wrapper (shapes.nuke_wrapper). parRadiusPhysical sizes its ground scorch (0.75 x) and the scenery it
# destroys; the inner effect's own default is 25,000. parDirection takes the inner effect's default, 0.
FX_NUKE = TACTICAL_NUKE_FX
NUKE_RADIUS = 60000.0


WRAP_ZERO = f"{profile.FOLDER}/FxNukeP0"
WRAP_WORLD = f"{profile.FOLDER}/FxNukePW"
U_WORLD = (*MAP.map.px_to_world(U_PX), GEISA.ground_z)

EXTRA_SHAPES = (
    DEATH_CAUSE_SHAPE,               # F5 kills with Penetration
    *FOW_SHAPES,                     # F3, F10
    *FX_WRAPPER_SHAPES,              # F8, F9
    *STRESS_SHAPES,                  # F6, F7: ChangeStress, as probe 1's check 6 admits it
)


class Step(NamedTuple):
    name: str
    t: float                         # seconds after "Launch battle" when the step acts


TIMELINE = (Step("F1", 15.0), Step("F2", 40.0), Step("F3", 65.0), Step("F3b", 85.0), Step("F4", 110.0),
            Step("F5", 140.0), Step("F6", 165.0), Step("F7", 190.0), Step("F8", 220.0), Step("F9", 250.0),
            Step("F10", 285.0))

# --------------------------------------------------------------------------- items


def items() -> list[LdItem]:
    """The player's deployment and command zone (probe 3's), the arrivals, and the tags: T, U, V and the ring."""
    return [
        MAP.zone_item("DeploymentZone", "FX_DZ_W", spike.DZ_W, "DeploymentZone"),
        MAP.zone_item("CommandPoints", "FX_CZ_SW", spike.CZ_SW, "CommandPoints", points=spike.CZ_POINTS),
        *MAP.map.player_arrivals("FX"),
        MAP.item("Tags", "FX_T", T_PX, "Name"),
        MAP.item("Tags", "FX_U", U_PX, "Name"),
        MAP.item("Tags", "FX_V", V_PX, "Name"),
        *(MAP.item("Tags", f"FX_R{k + 1}", px, "Name") for k, px in enumerate(RING)),
    ]


ITEMS = items()


class Ctx(ShapesCtx):
    """The shapes Ctx over the Soviet-player camps and this probe's items."""

    def __init__(self) -> None:
        super().__init__(camp_nodes(SOVIET_PLAYER_CAMP_ROWS, CAMP_TOKENS), SIDES, PLAYER, ITEMS, SCENARIO,
                         profile.GUID_NAMESPACE, profile.FOLDER)


# --------------------------------------------------------------------------- steps


def step(token: str, actions: list[Node], *beside: Node) -> Node:
    """A step: its hint now, its `actions` LEAD_S later, `beside` (pins) alongside."""
    return g_simul([g_hint(token, HINT_S, "shint"), g_seq([g_wait(LEAD_S), *actions]), *beside])


def targets(ctx: Ctx) -> Node:
    """F1: the targets at T, off the AI and emptied of ammunition, with the pins of T and U (they stay up)."""
    tg, up = ctx.group("fx_targets"), ctx.int_var("fx_up")
    return step("fx_h1", [*(create(ctx, TARGET_SIDE, tg, n, ctx.tag("FX_T"), unit_path(u)) for u, n in TARGETS),
                          g_ignored(tg), g_ammo([tg])],
                objective("fx_ot", "fx_otl", g_cmp(up, 1), ctx.tag("FX_T")),
                objective("fx_ou", "fx_oul", g_cmp(up, 1), ctx.tag("FX_U")))


def camera(ctx: Ctx) -> Node:
    """F2: the camera to Camp1, from where the player has it."""
    return step("fx_h2", [g_camera(CAMERA_PATH, CAMERA_S, from_current=True)])


def fog_off(ctx: Ctx) -> Node:
    """F3: fog off."""
    return step("fx_h3", [g_fow(False)])


def vision(ctx: Ctx) -> Node:
    """F3b: the player's BRDM-2s at V."""
    return step("fx_h3b", [create(ctx, PLAYER, ctx.group("fx_vision"), VISION_COUNT, ctx.tag("FX_V"),
                                  unit_path(VISION_UNIT))])


def massed(ctx: Ctx) -> Node:
    """F4: the proven effects massed, all launched together."""
    ring = [ctx.tag(f"FX_R{k + 1}") for k in range(RING_N)]
    return step("fx_h4", [g_simul([
        *(g_fx(FX_MEGA, tag) for tag in [ctx.tag("FX_T"), *ring]),
        *(g_seq([g_fx(FX_HE, ctx.tag(name))], runs=HE_RUNS) for name in HE_TAGS),
        *(g_fx(fx, ctx.tag(name)) for name in SMOKE_TAGS for fx in (FX_WHITE, FX_BLACK)),
    ])])


def kill(ctx: Ctx) -> Node:
    """F5: KILL_NUM / KILL_DEN of the targets move one at a time to fx_struck, which is killed with Penetration."""
    tg, struck = ctx.group("fx_targets"), ctx.group("fx_struck")
    alive, n = ctx.int_var("fx_alive"), ctx.int_var("fx_kill_n")
    transfer = Node("TGDDescriptorTransferUnitToUnitGroup", [  # Sledgehammer #612's order, without CopyUnits
        ("GroupDestination", struck), ("GroupSource", tg), ("NBToTransfert", i32(1))])
    return step("fx_h5", [
        g_count(alive, tg), g_set(n, other=alive), g_modify(n, MULTIPLY, KILL_NUM), g_modify(n, DIVIDE, KILL_DEN),
        g_seq([g_if(g_cmp(struck, op=STRICTLY_LESS, other=n), g_seq([transfer]))], runs=TRANSFER_CAP),
        g_kill(struck, cause=PENETRATION),
    ])


def damage(ctx: Ctx) -> Node:
    """F6: ChangeStress Physical on the survivors."""
    return step("fx_h6", [g_stress(ctx.group("fx_targets"), DAMAGE_VALUE, PHYSICAL)])


def stun(ctx: Ctx) -> Node:
    """F7: ChangeStress Stun on the survivors."""
    return step("fx_h7", [g_stress(ctx.group("fx_targets"), STRESS_VALUE, STUN)])


def nuke_zero(ctx: Ctx) -> Node:
    """F8: the wrapper with parPosition 0, on T."""
    return step("fx_h8", [g_fx(WRAP_ZERO, ctx.tag("FX_T"))])


def nuke_world(ctx: Ctx) -> Node:
    """F9: the wrapper with parPosition U's world position, on U."""
    return step("fx_h9", [g_fx(WRAP_WORLD, ctx.tag("FX_U"))])


def done(ctx: Ctx) -> Node:
    """F10: fog back on."""
    return step("fx_h10", [g_fow(True)])


BUILDERS = {"F1": targets, "F2": camera, "F3": fog_off, "F3b": vision, "F4": massed, "F5": kill, "F6": damage,
            "F7": stun, "F8": nuke_zero, "F9": nuke_world, "F10": done}
BEATS: list[Beat] = [Beat(s.t - LEAD_S, s.name, BUILDERS[s.name]) for s in TIMELINE]


def wrappers() -> list[Node]:
    """The two nuke wrappers, exported by the script under profile.FOLDER."""
    return [nuke_wrapper(WRAP_ZERO, (0.0, 0.0, 0.0), NUKE_RADIUS), nuke_wrapper(WRAP_WORLD, U_WORLD, NUKE_RADIUS)]


# --------------------------------------------------------------------------- strings


def strings() -> Table:
    local = {CAMP_TOKENS[name]: text for name, text in CAMP_NAMES.items()}
    local.update({
        "fx_hdep": ("Deploy one cheap unit west of the central forest and nothing east of it, then launch the battle. "
                    "The steps start then; each hint names its step 5 s before it acts.",
                    "在中央森林以西部署一个便宜的单位，森林以东不要部署，然后发起战斗。各步骤从此开始；每条提示在步骤执行前5秒标明步骤。"),
        "fx_h1": ("F1 TARGETS: 6 M1A1HA Abrams and 6 M2A2 Bradleys appear at T (pinned), unarmed. You should not see "
                  "them yet: nothing of yours is near.",
                  "F1 目标：6辆M1A1HA艾布拉姆斯和6辆M2A2布雷德利出现在T（已标出），没有弹药。你现在应该看不到它们。"),
        "fx_h2": ("F2 CAMERA: the camera flies to T in 4 s. Escape skips it.",
                  "F2 镜头：镜头在4秒内飞到T。按Esc可略过。"),
        "fx_h3": ("F3 FOG OFF: the fog of war is lifted. Do the 12 targets at T show now?",
                  "F3 关闭战争雾：雾被移除。T处的12个目标现在能看到吗？"),
        "fx_h3b": ("F3b VISION: 3 BRDM-2 of yours appear 400 m west of T, so you see T even if the fog stayed. Keep "
                   "them there.",
                   "F3b 视野：你的3辆BRDM-2出现在T以西400米处，即使雾仍在也能看到T。请让它们留在原地。"),
        "fx_h4": ("F4 MASSED EFFECTS: 10 mega bombs over T, 50 203 mm impacts, white and black smoke, all at once. "
                  "How big does it look?",
                  "F4 大规模特效：T周围10颗超级炸弹、50发203毫米炮弹、白烟和黑烟同时出现。看起来有多大？"),
        "fx_h5": ("F5 KILL 40%: 4 of the 12 targets are killed with Penetration. Wrecks, or nothing?",
                  "F5 击杀40%：12个目标中的4个被穿透击杀。留下残骸，还是什么都没有？"),
        "fx_h6": ("F6 DAMAGE: ChangeStress Physical, 5 of 10 HP, on the survivors. Do they lose health, or die?",
                  "F6 伤害：对幸存者施加ChangeStress物理伤害，10点生命值中的5点。它们掉血了还是被摧毁了？"),
        "fx_h7": ("F7 STUN: ChangeStress Stun on the survivors. Are they stunned?",
                  "F7 Stun：对幸存者施加ChangeStress（Stun）。它们失去行动能力了吗？"),
        "fx_h8": ("F8 NUKE 1: the game's tactical nuke effect through the script's wrapper, position 0, on T. If the "
                  "game crashes now, it was this step. Where does it show, and how big?",
                  "F8 原子弹1：通过脚本封装使用游戏的战术原子弹特效，位置为0，目标T。如果游戏此时崩溃，就是这一步。"
                  "它出现在哪里，有多大？"),
        "fx_h9": ("F9 NUKE 2: the same effect at U, its position the tag's own. If the game crashes now, it was this "
                  "step. Where does it show, and how big?",
                  "F9 原子弹2：同样的特效在U处，位置为该标记自身的位置。如果游戏此时崩溃，就是这一步。它出现在哪里，有多大？"),
        "fx_h10": ("F10 FOG ON: the fog of war is back. Probe done: answer the play sheet (README, fxprobe).",
                   "F10 开启战争雾：雾恢复。测试完成：请回答试玩问卷。"),
        "fx_ot": ("T: 12 NATO targets (F1 to F8)", "T：12个北约目标（F1至F8）"),
        "fx_otl": ("T", "T"),
        "fx_ou": ("U: the second nuke (F9)", "U：第二颗原子弹（F9）"),
        "fx_oul": ("U", "U"),
    })
    return {
        "SCENARIO_DEFINITION": {  # menu tokens, each text at most 30 UTF-16 units
            "fx_name": ("Probe: strike effects", "测试：打击特效"),
            "fx_cname": ("PROBE: STRIKE EFFECTS", "测试：打击特效"),
            "fx_headr": ("Strike effects play sheet", "打击特效问卷"),
            "fx_order": ("Each hint names its step.", "每条提示都标明步骤编号。"),
            "fx_recap": ("Test op: every strike effect", "测试行动：所有打击特效"),
            "fx_vic": ("Probe complete.", "测试完成。"),
            "fx_def": ("Probe ended.", "测试结束。"),
        },
        "Scripting/Dialog": {},
        "Scripting/Localization": local,
    }


# --------------------------------------------------------------------------- script and content


def script(tpl: ndfbin.NdfBin) -> tuple[list[Node], list[Node]]:
    """The probe's GDScript from Survivors' template `tpl` (modkit.ops.mission.script_frame): the deployment phase,
    then the timed steps, each its own branch; the two wrappers exported beside the frame's exports."""
    ctx = Ctx()
    deploy = ops_script.deploy_phase(tpl, profile.TEMPLATES, ctx.camp(ctx.player), ctx.group("Groupe_Joueur"),
                                     [ctx.tag("FX_CZ_SW")], points=spike.DEPLOY_POINTS, income=profile.PLAYER_INCOME,
                                     hint="fx_hdep", refresh_export=profile.REFRESH_EXPORT,
                                     refresh_s=profile.REFRESH_S)
    roots, exports = script_frame(tpl, profile.TEMPLATES, ctx, deploy, BEATS, camp_rows=SOVIET_PLAYER_CAMP_ROWS,
                                  folder=profile.FOLDER, start_delay_s=profile.START_DELAY_S,
                                  prod_menu_switch=BRICK_FORCE_HIDE)
    return roots, [*exports, *wrappers()]


def content() -> Content:
    """The probe: its own scenario, mod folder, GUIDs, menu tokens and derived menu order."""
    renames = profile.menu_renames(PREFIX)
    return profile.content(NAME, ITEMS, script, strings(), tuple(new for _, new in renames),
                           extra_shapes=EXTRA_SHAPES, scenario=SCENARIO, mod_name=MOD_NAME, menu_renames=renames,
                           deck_swap=SOVIET_PLAYER_DECK_SWAP,
                           menu_order=derived_menu_order(SCENARIO, profile.GUID_NAMESPACE))
