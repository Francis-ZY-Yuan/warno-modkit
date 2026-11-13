"""Probe 3 (`nuke`, `nuke_sov`): how does a scripted strike look against two groups of tanks, with effects a script can
launch, and can the player's camp be Soviet in a clone of Survivors?

The first play crashed the game at the effect steps, which launched the tactical-nuke impact effects: those are
parameterised, and a script launch cannot bind them [[scripted-nuke-effect]]. The steps now launch self-contained
effects only [[script-effects-self-contained]]: N2 the game's script-only mega bomb, N3 the design's fallback stack.

Two contents from one module, each its own scenario, mod folder, GUID and menu tokens, so both install beside the other
probes. `nuke` keeps the probes' camps: the player is NATO and the victims are PACT T-80BV. `nuke_sov` flips them: the
player is Soviet (the stock Soviet-player Operations' camp shape and deck) and the victims are NATO M1A1HA Abrams. The
steps are the same in both.

Everything runs on the clock of LoadingDone (load beats, Beat.t None), so the steps need no deployment and no
"Launch battle"; the deployment phase still runs beside them, for nuke_sov's buy-menu questions.

  N1  0:20  two groups of five victims, A and B, about 600 m apart on open ground; each has a pinned map objective
  N2  0:40  fx_HE_Mega_Bomb_ForScript on A; 3 s later the victims within 300 m of A are killed with Penetration
  N3  1:10  fx_HE_Artillery_203mm_ForScript_RandomPosition and fx_FumeeNoire_ForScript_RandomPosition together on B;
            3 s later the victims within 300 m of B are killed with Vanished
  N4  1:40  "probe done"

Nothing orders the victims. The detector collects only the victims' camp, so the player's own units are not touched.
The play sheet is in README.md (probe 3).
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import NamedTuple

from modkit.core import ndfbin
from modkit.core.models import StringTable, Texts
from modkit.ops import script as ops_script
from modkit.ops.bricks import (
    c_team, g_cmp, g_collect, g_detect, g_fx, g_kill, g_seq, g_set, g_simul, g_wait, unit_path,
)
from modkit.ops.graph import Node
from modkit.ops.leveldesign import LdItem, derived_menu_order
from modkit.ops.mission import script_frame
from modkit.ops.models import CampRow
from modkit.ops.profile import (
    SOVIET_PLAYER_CAMP_ROWS, SOVIET_PLAYER_DECK_SWAP, SOVIET_PLAYER_SIDES, SOVIET_PLAYER_SUPPLY, Content,
)
from modkit.ops.script import BRICK_FORCE_HIDE
from modkit.ops.shapes import (
    DEATH_CAUSE_SHAPE, PENETRATION, SHOOT_ON_POSITION, TRANSPORTER_SHAPE, Beat, add_card, beat_hint, camp_nodes,
    create, lock_card, objective, order, reveal,
)
from modkit.ops.shapes import Ctx as ShapesCtx
from probes import profile, spike
from probes.geisa import MAP

# --------------------------------------------------------------------------- the effects

# Every effect here is self-contained (the driver's script-effects gate holds it). N2's mega bomb is script-named but no
# stock scenario launches it; N3's two are the stock-launched barrage and black smoke, launched together.
FX_MEGA = "$/GFX/GameFx/fx_HE_Mega_Bomb_ForScript"
FX_HE = spike.FX_BOMB                # the stock script-only 203 mm effect: N3, and N1b alone near A
FX_SMOKE = "$/GFX/GameFx/fx_FumeeNoire_ForScript_RandomPosition"
FX_STACK = (FX_HE, FX_SMOKE)
# What the first play launched at N2 and N3, and crashed on: parameterised impact actions, which the gate refuses.
FX_CRASHED = ("$/GFX/GameFx/fx_impact_sol_Tactical_Nuke", "$/GFX/GameFx/fx_impact_Tactical_Nuke")

# --------------------------------------------------------------------------- knobs

# One km is 84 minimap px (spike2.KM_PX): 1 px is 11.9 m. A and B are 50 px (595 m) apart on the open fields east of
# the player's deployment zone (spike.DZ_W ends at x 540), clear of the roads, the towns and every zone, on the line
# y 300 that spike2's parked groups also use. The detector circles are 25 px (298 m): A's reaches x 571, and B's
# does not reach A.
POINT_A_PX, POINT_B_PX = (596.0, 300.0), (646.0, 300.0)
DETECTOR_PX = 25.0
VICTIM_COUNT = 5
FX_TO_KILL_S = 3.0                   # the kill comes this long after the effect starts, so the effect is seen alone
DEPLOY_POINTS = spike.DEPLOY_POINTS
CZ_POINTS = spike.CZ_POINTS


class Step(NamedTuple):
    name: str
    t: float                         # seconds after LoadingDone


TIMELINE = (Step("N1", 20.0), Step("N2", 40.0), Step("N3", 70.0), Step("N4", 100.0))
# nuke_sov's: the same steps plus N0 (at load), N1b (a script effect), N5 (an allied battery fires) and N6 (the unlock).
# Each hint shows 15 s, so N4 moves after N6; N1b follows N1's hint after 5 s, as the foreman's addendum sets it.
SOV_TIMELINE = (Step("N0", 0.0), Step("N1", 20.0), Step("N1b", 25.0), Step("N2", 40.0), Step("N3", 70.0),
                Step("N5", 90.0), Step("N6", 110.0), Step("N4", 130.0))

# nuke_sov's extra beats
FX_HE_PX = (606.0, 314.0)            # N1b's FX_HE, near A (inside its circle; the effect harms nothing)
BATTERY_UNIT, BATTERY_COUNT = "2S7M_Malka_SOV", 2
BATTERY_PX = MAP.points["EDGE_W"]    # the player's side's west edge, in its deployment zone: 650 px (22,600 GRU) from
TARGET_PX = (621.0, 345.0)           # the empty spot in view, which is inside the 2A44's 7,000..35,000 GRU
TARGET_RADIUS_PX = 8.0
TRANSPORT_CARD, CARD_UNIT, CARD_COUNT = "BMP_2_SOV", "MotRifles_SOV", 2
LOCKED_CARD, LOCKED_COUNT = "T80U_SOV", 2

# --------------------------------------------------------------------------- identities and camps


class Variant(NamedTuple):
    """What differs between the two contents."""
    name: str                        # the --content name
    prefix: str                      # the prefix of its script and menu tokens
    scenario: str
    mod_name: str
    victim_unit: str
    victim_label: str                # for the hints
    victim_side: str                 # the side the victims belong to
    sides: Mapping[str, str]         # side -> camp export name
    player: str                      # the player's side
    camp_rows: tuple[CampRow, ...]   # the four camps, CampList order
    camp_names: dict[str, Texts]     # camp export name -> its PlayerName
    deck_swap: Mapping[str, str] | None  # MapConfiguration LocalPlayerDeck swap (None: the profile's)
    timeline: tuple = TIMELINE       # the Steps
    ally_side: str | None = None     # the player's ally camp's side (nuke_sov's battery)


# nuke: the probes' own camps (profile.CAMP_ROWS), victims in the PACT AI camp
NUKE = Variant(
    "nuke", "nk", "challenge_OpenDoorNuke", "OpenDoorNuke", "T80BV_SOV", "T-80BV", "PACT", profile.CAMPS,
    profile.PLAYER, profile.CAMP_ROWS,
    {"joueur": Texts(US="NATO", SC="北约"), "Allie": Texts(US="NATO ally", SC="北约盟军"),
     "ordinateur_DDR": Texts(US="NVA", SC="东德军"), "ordinateur_SOV": Texts(US="Soviet Army", SC="苏军")},
    None)

# nuke_sov: the stock Soviet-player camp shape, modkit.ops.profile's (the player Alliance 0, REDFOR, PACT, on
# OP_BASE_RJ_Player; the enemies Alliance 1, BLUFOR, NATO) [[soviet-player-camp]]. The camp names are the probe's.
SOV = Variant(
    "nuke_sov", "ns", "challenge_OpenDoorNukeSov", "OpenDoorNukeSov", "M1A1HA_Abrams_US", "M1A1HA Abrams", "NATO",
    SOVIET_PLAYER_SIDES, "Soviet",
    SOVIET_PLAYER_CAMP_ROWS,
    {"joueur": Texts(US="Soviet Army", SC="苏军"), "Allie": Texts(US="Soviet ally", SC="苏军盟军"),
     "ordinateur_DDR": Texts(US="NATO", SC="北约"), "ordinateur_SOV": Texts(US="NATO", SC="北约")},
    SOVIET_PLAYER_DECK_SWAP, SOV_TIMELINE, "SovietAlly")
VARIANTS = {v.name: v for v in (NUKE, SOV)}
EXTRA_SHAPES = (DEATH_CAUSE_SHAPE,)   # N2 kills with Penetration
SOV_EXTRA_SHAPES = (DEATH_CAUSE_SHAPE, TRANSPORTER_SHAPE)   # and N0's card has a Transporter


def camp_tokens(v: Variant) -> dict[str, str]:
    """Each camp's PlayerName token (Scripting/Localization)."""
    return {name: f"{v.prefix}_camp{k}" for k, name in enumerate(v.camp_names)}


# --------------------------------------------------------------------------- items

def items(sov: bool = False) -> list[LdItem]:
    """The LevelDesign items: the player's deployment, the two victim points with their detector circles; with `sov`
    (nuke_sov) also N1b's effect tag and N5's battery tag and target."""
    base = [
        MAP.zone_item("DeploymentZone", "NK_DZ_W", spike.DZ_W, "DeploymentZone"),
        MAP.zone_item("CommandPoints", "NK_CZ_SW", spike.CZ_SW, "CommandPoints", points=CZ_POINTS),
        *MAP.map.player_arrivals("NK"),
        MAP.item("Tags", "NK_PointA", POINT_A_PX, "Name"),     # the victims' centre and the effect's position
        MAP.item("Tags", "NK_PointB", POINT_B_PX, "Name"),
        MAP.ring_item("NK_RingA", POINT_A_PX, DETECTOR_PX),    # the detector circles (circles only: detector-circles-only)
        MAP.ring_item("NK_RingB", POINT_B_PX, DETECTOR_PX),
    ]
    return base + ([
        MAP.item("Tags", "NK_FxHe", FX_HE_PX, "Name"),
        MAP.item("Tags", "NK_Battery", BATTERY_PX, "Name"),
        MAP.ring_item("NK_Target", TARGET_PX, TARGET_RADIUS_PX),
    ] if sov else [])


ITEMS, SOV_ITEMS = items(), items(True)


class Ctx(ShapesCtx):
    """The shapes Ctx over variant `v`'s camps and sides, with `items` keyed to its scenario."""

    def __init__(self, v: Variant) -> None:
        self.variant = v
        super().__init__(camp_nodes(v.camp_rows, camp_tokens(v)), v.sides, v.player, SOV_ITEMS if v is SOV else ITEMS, v.scenario,
                         profile.GUID_NAMESPACE, profile.FOLDER)


# --------------------------------------------------------------------------- steps

def victims_camp(ctx: Ctx) -> Node:
    return ctx.camp(ctx.variant.victim_side)


def victims(ctx: Ctx) -> Node:
    """N1: VICTIM_COUNT victims at each point, in groups A and B, each pinned on the map; revealed to the player, not
    ordered."""
    v, p = ctx.variant, ctx.variant.prefix
    a, b, up = ctx.group(f"{p}_a"), ctx.group(f"{p}_b"), ctx.int_var(f"{p}_up")
    pins = [objective(f"{p}_oa", f"{p}_ola", g_cmp(up, 1), ctx.tag("NK_PointA")),   # nothing sets up: they stay
            objective(f"{p}_ob", f"{p}_olb", g_cmp(up, 1), ctx.tag("NK_PointB"))]
    return beat_hint(f"{p}_h1", g_seq([
        create(ctx, v.victim_side, a, VICTIM_COUNT, ctx.tag("NK_PointA"), unit_path(v.victim_unit)),
        create(ctx, v.victim_side, b, VICTIM_COUNT, ctx.tag("NK_PointB"), unit_path(v.victim_unit)),
        reveal([a, b], []),
    ]), *pins)


def strike(ctx: Ctx, hint: str, fx: tuple[str, ...], point: str, ring: str, caught: str, cause: int | None) -> Node:
    """N2, N3: the effects `fx` on the Name tag `point` (several launched together, in a Simultaneous), then
    (FX_TO_KILL_S later) every unit of the victims' camp in the detector circle `ring` into the group `caught`, which
    is killed with `cause` (bricks.g_kill: Penetration, or Vanished when None)."""
    group = ctx.group(f"{ctx.variant.prefix}_{caught}")
    launches = [g_fx(name, ctx.tag(point)) for name in fx]
    return beat_hint(hint, g_seq([
        launches[0] if len(launches) == 1 else g_simul(launches),
        g_wait(FX_TO_KILL_S),
        g_collect(group, g_detect(ctx.tag(ring), c_team(victims_camp(ctx)), compare=False)),
        g_kill(group, cause=cause),
    ]))


def nuke_a(ctx: Ctx) -> Node:
    """N2: the mega bomb on A, the victims near it killed with Penetration (wrecks?)."""
    return strike(ctx, f"{ctx.variant.prefix}_h2", (FX_MEGA,), "NK_PointA", "NK_RingA", "boxa", PENETRATION)


def nuke_b(ctx: Ctx) -> Node:
    """N3: the 203 mm barrage and black smoke together on B, the victims near it removed with Vanished."""
    return strike(ctx, f"{ctx.variant.prefix}_h3", FX_STACK, "NK_PointB", "NK_RingB", "boxb", None)


def done(ctx: Ctx) -> Node:
    """N4: the closing hint."""
    return beat_hint(f"{ctx.variant.prefix}_h4")


def load_deck(ctx: Ctx) -> Node:
    """N0 at load: a MotRifles card in a BMP-2 (the Transporter, as spike's start cards), a T-80U card, the Soviet
    player's supply (modkit.ops.profile.SOVIET_PLAYER_SUPPLY: RJ's deck has no supply helicopter, and its trucks sit
    only in its tank battalions' groups [[soviet-player-camp]]), and the T-80U locked until the flag is set
    (shapes.lock_card: Competition[WaitCondition, LockDeckUnit]; the race is the last node)."""
    return g_seq([add_card(ctx, CARD_UNIT, CARD_COUNT, transport=TRANSPORT_CARD),
                  add_card(ctx, LOCKED_CARD, LOCKED_COUNT),
                  *(add_card(ctx, c.unit, c.count, transport=c.transport) for c in SOVIET_PLAYER_SUPPLY),
                  lock_card(ctx, LOCKED_CARD, g_cmp(ctx.int_var(f"{ctx.variant.prefix}_t80u"), 1))])


def script_fx(ctx: Ctx) -> Node:
    """N1b: the stock script-only 203 mm effect once near A."""
    return beat_hint(f"{ctx.variant.prefix}_h1b", g_fx(FX_HE, ctx.tag("NK_FxHe")))


def allied_battery(ctx: Ctx) -> Node:
    """N5: 2S7M x2 in the player's ally camp at the west edge, ShootOnPosition on the empty spot NK_Target."""
    group = ctx.group(f"{ctx.variant.prefix}_battery")
    return beat_hint(f"{ctx.variant.prefix}_h5", g_seq([
        create(ctx, ctx.variant.ally_side, group, BATTERY_COUNT, ctx.tag("NK_Battery"), unit_path(BATTERY_UNIT)),
        order(group, SHOOT_ON_POSITION, ctx.tag("NK_Target")),
    ]))


def unlock(ctx: Ctx) -> Node:
    """N6: lift the T-80U lock."""
    return beat_hint(f"{ctx.variant.prefix}_h6", g_set(ctx.int_var(f"{ctx.variant.prefix}_t80u"), 1))


BUILDERS = {"N0": load_deck, "N1": victims, "N1b": script_fx, "N2": nuke_a, "N3": nuke_b, "N4": done,
            "N5": allied_battery, "N6": unlock}


def beat(step: Step) -> Beat:
    """A load beat (it runs from LoadingDone) that waits `step.t` seconds, then does the step."""
    if step.t == 0.0:
        return Beat(None, step.name, BUILDERS[step.name])
    return Beat(None, step.name, lambda ctx: g_seq([g_wait(step.t), BUILDERS[step.name](ctx)]))


BEATS: list[Beat] = [beat(s) for s in TIMELINE]
SOV_BEATS: list[Beat] = [beat(s) for s in SOV_TIMELINE]

# --------------------------------------------------------------------------- strings


def strings(v: Variant) -> StringTable:
    p, unit = v.prefix, v.victim_label
    title = "Nuke probe" if v is NUKE else "Nuke probe, Soviet"
    zh_title = "打击特效测试" if v is NUKE else "打击特效测试：苏军"
    local = {f"{p}_camp{k}": v.camp_names[name] for k, name in enumerate(v.camp_names)}
    local.update({
        f"{p}_hdep": Texts(US="Deploy if you like, then launch. The strike steps run on their own clock from loading.",
                           SC="可自行部署后发起战斗。打击测试从加载完成起自行计时。"),
        f"{p}_h1": Texts(US=f"N1 VICTIMS: 2 groups of 5 {unit}, A and B, about 600 m apart, pinned on the map. Find them.",
                         SC=f"N1 目标：A和B两组各5辆{unit}，相距约600米，已在地图上标出。请找到它们。"),
        f"{p}_h2": Texts(US="N2 STRIKE A + PENETRATION: the script-only mega bomb effect fx_HE_Mega_Bomb_ForScript on "
                            "A. 3 s later every unit within 300 m of A is killed with Penetration. Watch A.",
                         SC="N2 打击A+穿透：在A处使用脚本专用的超级炸弹特效fx_HE_Mega_Bomb_ForScript。3秒后，A周围300米内的"
                            "单位被穿透击杀。请观察A。"),
        f"{p}_h3": Texts(US="N3 STRIKE B + VANISHED: the 203 mm barrage and black smoke effects together on B. 3 s "
                            "later every unit within 300 m of B is removed with Vanished. Watch B.",
                         SC="N3 打击B+消失：在B处同时使用203毫米炮击和黑烟特效。3秒后，B周围300米内的单位被直接移除。"
                            "请观察B。"),
        f"{p}_h4": Texts(US="N4 PROBE DONE: answer the play sheet (README, probe 3).", SC="N4 测试完成：请回答试玩问卷。"),
        f"{p}_oa": Texts(US=f"A: 5 {unit} (N2)", SC=f"A：5辆{unit}（N2）"),
        f"{p}_ola": Texts(US="A", SC="A"),
        f"{p}_ob": Texts(US=f"B: 5 {unit} (N3)", SC=f"B：5辆{unit}（N3）"),
        f"{p}_olb": Texts(US="B", SC="B"),
    })
    if v is SOV:
        local.update({
            f"{p}_hdep": Texts(US="N0 DECK: a BMP-2 card carrying motor riflemen, a T-80U card that is locked until "
                                  "N6, and supply: 4 Ural-4320 trucks and 2 Mi-8TZ helicopters. Deploy and launch if "
                                  "you like; the steps run on their own clock from loading.",
                               SC="N0 卡组：一张载有摩托化步兵的BMP-2卡，一张在N6前锁定的T-80U卡，以及补给：4辆Ural-4320卡车和"
                                  "2架Mi-8TZ直升机。可自行部署并发起战斗；各步骤从加载完成起自行计时。"),
            f"{p}_h1b": Texts(US="N1b SCRIPT EFFECT: the stock 203 mm artillery effect alone near A, to compare with "
                                 "N3's barrage and smoke.",
                              SC="N1b 脚本特效：在A附近单独使用一次游戏自带的203毫米炮击特效，与N3的炮击加黑烟对比。"),
            f"{p}_h5": Texts(US="N5 ALLIED BATTERY: 2 2S7M of your ally appear at the west edge and fire on the marked "
                                "empty spot south of A. Do the shells land there?",
                             SC="N5 友军炮兵：盟军的2辆2S7M出现在西侧边缘，并向A以南的空地开火。炮弹是否落在那里？"),
            f"{p}_h6": Texts(US="N6: T-80U unlocked, check the buy menu.", SC="N6：T-80U已解锁，请查看购买菜单。"),
        })
    return {
        "SCENARIO_DEFINITION": {  # menu tokens, each text at most 30 UTF-16 units
            f"{p}_name": Texts(US=title, SC=zh_title),
            f"{p}_cname": Texts(US=title.upper(), SC=zh_title),
            f"{p}_headr": Texts(US=f"{title} play sheet", SC=f"{zh_title}问卷"),
            f"{p}_order": Texts(US="Each hint names its step.", SC="每条提示都标明步骤编号。"),
            f"{p}_recap": Texts(US="Test op: two strike looks", SC="测试行动：两次打击特效"),
            f"{p}_vic": Texts(US="Probe complete.", SC="测试完成。"),
            f"{p}_def": Texts(US="Probe ended.", SC="测试结束。"),
        },
        "Scripting/Dialog": {},
        "Scripting/Localization": local,
    }


# --------------------------------------------------------------------------- script and content

def script(tpl: ndfbin.NdfBin, v: Variant = NUKE) -> tuple[list[Node], list[Node]]:
    """The probe's GDScript for variant `v`, from Survivors' GDScript template `tpl` (modkit.ops.mission.script_frame):
    Main: SetDeck x4, HUD hidden, deployment setup, LoadingDone, HUD restored, then Simultaneous[ the step beats (each
    a load beat that waits for its own time), the Groupe_Joueur refresh loop, the wait for "Launch battle" ]."""
    ctx = Ctx(v)
    deploy = ops_script.deploy_phase(tpl, profile.TEMPLATES, ctx.camp(ctx.player), ctx.group("Groupe_Joueur"),
                                     [ctx.tag("NK_CZ_SW")], points=DEPLOY_POINTS, income=profile.PLAYER_INCOME,
                                     hint=f"{v.prefix}_hdep", refresh_export=profile.REFRESH_EXPORT,
                                     refresh_s=profile.REFRESH_S)
    return script_frame(tpl, profile.TEMPLATES, ctx, deploy, SOV_BEATS if v is SOV else BEATS,
                        camp_rows=v.camp_rows, folder=profile.FOLDER, start_delay_s=profile.START_DELAY_S,
                        prod_menu_switch=BRICK_FORCE_HIDE)


def content(name: str = "nuke") -> Content:
    """The probe content `name` ('nuke' or 'nuke_sov'): its own scenario, mod folder, GUID, menu tokens and menu
    order, the order derived from its scenario GUID (modkit.ops.leveldesign.derived_menu_order)."""
    v = VARIANTS[name]
    renames = profile.menu_renames(v.prefix)
    return profile.content(v.name, SOV_ITEMS if v is SOV else ITEMS, lambda tpl: script(tpl, v), strings(v), tuple(new for _, new in renames),
                           extra_shapes=SOV_EXTRA_SHAPES if v is SOV else EXTRA_SHAPES, scenario=v.scenario, mod_name=v.mod_name, menu_renames=renames,
                           deck_swap=v.deck_swap, menu_order=derived_menu_order(v.scenario, profile.GUID_NAMESPACE))
