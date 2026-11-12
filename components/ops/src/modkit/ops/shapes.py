"""Mission building blocks: the pieces the example ops and probes lay their scripts out with.

A mission is a list of beats (``Beat``). A beat runs at load (t None), beside the deployment phase, or t seconds after
the battle starts (the deployment phase's "Launch battle"), each as the last node of its own Sequential[wait t, beat] in
the battle's Simultaneous, so nothing waits on a beat. A timed beat opens with a hint (``beat_hint``).

``Ctx`` is one build's script state: the camps, the GdItems tag of every LevelDesign item, and the script variables,
each made once per name. ``Minimap`` places LevelDesign items by minimap pixels on a stock map (``modkit.ops.maps``).
The blocks below copy stock objects' property order and value forms, cited by scenario and object id (the scenarios'
decoded scripts; ``S#296`` is object 296 of Survivors' GDScript). Two facts shape most of them:

* SetEffect and LockDeckUnit never finish, and hold their effect only while they run. A beat that applies one runs it
  beside the rest of the beat (``reveal``, ``lock_card``), and nothing may follow such a container in a Sequential
  (gates.check_never_finishing).
* An objective finishes only once it resolves and its chosen action has (gates.finish_status), so it goes last in its
  Sequential, and only an objective with a position shows its map label (gates.check_objective_pins).
"""
from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass

from modkit.core.gates import check
from modkit.core.ndfbin import Value, token_unhash
from modkit.ops.bricks import (
    g_cmp, g_compete, g_create, g_hint, g_if, g_modify, g_seq, g_set, g_simul, g_timer, g_until, g_wait, unit_path,
)
from modkit.ops.graph import TRUE, Imp, Node, Str, i32, loc, walk
from modkit.ops.leveldesign import LdItem, gd_tags
from modkit.ops.maps import StockMap
from modkit.ops.script import BATTLE_PHASE, FOREVER  # noqa: F401  (shared constants, re-exported)
from modkit.ops.zones import heading, rect_polygon

GD = "$/GDScript"

# --------------------------------------------------------------------------- shared constants

HINT_S = 15.0                        # 'shint' panel time, the mid-battle notice (Sledgehammer #601)
POLL_S = 1.0                         # the period of a readout loop
GRU_WORLD = 73.6                     # world units per RadiusGRU unit (a CircularZone's radius)
DIFF_NONE = 9                        # a difficulty readout before any difficulty branch has set it
# The EffectCapacity pack that shows a unit to the other side (TUnitEffectMakeUnitVisibleDescriptor)
REVEAL_EFFECT = "UnitEffect_revealUnit"
# EOrderType (GameData/Generated/Gameplay/Gfx/Enums/OrderType.ndf)
FAST_MOVE_AND_ATTACK = 12            # "QUICK HUNT": by road, engaging on sight (Survivors #852-858, final waves)
MOVE_AND_ATTACK = 24                 # "HUNT": to the position, engaging on sight (DelayedRetribution #275)
LAND = 18                            # an instant order with no target (its button is OrderInstant)
# Fire on a position or zone. Stock's artillery ShootOnPosition: TheWingedHussars #362 and Marauders #1341/#1352/#1353
# (each Blocking, on CommandPoints); Survivors #1231/#1232 order its bombers so onto Name tags. (BackhandBlow #283 is
# OrderType 29, Shoot.)
SHOOT_ON_POSITION = 31
AIRPLANE_EVACUATE = 2                # sends aircraft home: Survivors #1648, Blocking, no Position
AIRPLANE_MOVE_AND_ENGAGE = 3         # aircraft fly to a place and engage there: Survivors #1496, onto a circle
# EVariableIntegerModification, EGDOperator
ADD, SUB, DIVIDE = 1, 2, 4
GE, LE, STRICTLY_LESS = 2, 3, 5      # MoreOrEqual, LessOrEqual, StrictlyLess
SEIZE = 1                            # LaunchSmartOrder SmartOrderType Seize (TheDieburgSalient #519; bricks.g_seize)
HOLD = 2                             # LaunchSmartOrder SmartOrderType Hold (RedJuggernaut #249; bricks.g_smart_hold)
# EIdleBehavior (bricks.g_idle_roe) and EShotReactionBehaviour (bricks.g_roe), their stock values for a camp with no AI
# (RunningTheGauntlet #104/#105, Sledgehammer #316/#319): HOLD POSITION when idle, Aggressive when fired on
IDLE_HOLD_POSITION = 2
AGGRESSIVE = 2
# TriggerEndGame (CommonData/Gameplay/Constantes/Enumerations/: TGameEndingCondition, EVictoryType; bricks.g_end_game).
# A player win leaves WinningAlliance out (0); a loss names the enemy side's alliance, 1.
SCRIPT_DECIDED = 6                   # TGameEndingCondition ScriptDecided, every Operation's VictoryReason
MINOR_VICTORY, MAJOR_VICTORY, TOTAL_VICTORY = 4, 5, 6  # EVictoryType; the type grades the winner
PACT_ALLIANCE = 1                    # WinningAlliance of every stock Operation loss
EASY, MEDIUM, HARD = 0, 1, 2         # EGameDifficulty (bricks.g_difficulty)
# EDeathCause (CommonData/Gameplay/Constantes/Enumerations/DeathCause.ndf), EDamageType
# (GameData/Gameplay/Constantes/Enumerations/DamageType.ndf)
PENETRATION = 2
PHYSICAL, STUN = 1, 2                # not Suppress (0): ChangeStress rejects DamageType 0 at load; Physical (1) is HP

# GDScript shapes no stock file uses but a block writes (Content.extra_shapes): a content that uses the block admits
# the shape. add_card(transport=...) sets AddUnitToDeck.Transporter, a property the class has; a KillAllUnit with a
# DeathCause is stock only in the strategic-campaign tutorials (CampagneStrat_tuto_1 #145: DeathCause <int32> 2), which
# the shape gate does not survey; every challenge kills Vanished (0, omitted).
TRANSPORTER_SHAPE = ("TGDDescriptorAddUnitToDeck", "Transporter", 0x09, "import $/GFX/Unit")
DEATH_CAUSE_SHAPE = ("TGDDescriptorKillAllUnit", "DeathCause", 0x02, None)
# ChangeStress (bricks.g_stress) is a class the game has, with Group, Value and DamageType, but no stock file uses it,
# so a content that writes it admits the class too, and its place in a Sequential. Value and DamageType are ints, as
# SetFuel's stock MaxFuelRatio (<int32>) is; DamageType is an EDamageType and may not be 0
# [[changestress-damagetype-zero]]. Property order: alphabetical, as the natives' own properties are (KillAllUnit,
# SetEffect, SetFuel).
STRESS_SHAPES = (
    ("TGDDescriptorChangeStress", "DamageType", 0x02, None),
    ("TGDDescriptorChangeStress", "Group", 0x09, "TGDVariableUnitGroup"),
    ("TGDDescriptorChangeStress", "Value", 0x02, None),
    ("TGDDescriptorSequential", "SubActions", 0x11, "TGDDescriptorChangeStress"),
)
# bricks.g_fow: the scenario API's fog switch, a bool Fow, in a Sequential. No stock script writes the class.
FOW_SHAPES = (("TGDDescriptorFow", "Fow", 0x00, None),
              ("TGDDescriptorSequential", "SubActions", 0x11, "TGDDescriptorFow"))
# bricks.fx_wrapper: an effect wrapper exported by the op's own script, in GameFx's own class and value shapes
# (fx_FumeeNoire_ForScript_RandomPosition, FX_Vehicule_Dest_Fire_FireAndForget, TConstantFloat/TConstantFloat3), which
# no stock script holds.
FX_WRAPPER_SHAPES = (("TSimultaneousAction", "_ShortDatabaseName", 0x07, None),
                     ("TSimultaneousAction", "Actions", 0x11, "TActionCall"),
                     ("TActionCall", "NamedParams", 0x12, "TConstantFloat3"),
                     ("TActionCall", "NamedParams", 0x12, "TConstantFloat"),
                     ("TActionCall", "Action", 0x09, "import $/GFX/GameFx"),
                     ("TConstantFloat3", "Value", 0x0B, None),
                     ("TConstantFloat", "Value", 0x05, None))

# One camp of the template's CampList: export name, TGDVariableCamp scalars before PlayerName as (property, value
# tag, value), and its SetDeck id.
CampRow = tuple[str, tuple[tuple[str, int, int], ...], str]


# --------------------------------------------------------------------------- frame

@dataclass(frozen=True)
class Beat:
    """One beat of a mission. `t`: seconds after the battle starts, or None for a load beat, which starts once loading
    is done and runs beside the deployment phase. `check`: what the beat is for (a probe's checklist number, a
    label), comma-separated. `build` makes its action; a timed beat's action opens with its hint."""
    t: float | None
    check: str
    build: Callable[["Ctx"], Node]


def camp_nodes(camps: Sequence[CampRow], tokens: Mapping[str, str]) -> dict[str, Node]:
    """The template's TGDVariableCamps (Survivors S#109-#112) by export name, in CampList order, each named by its
    PlayerName token in `tokens` (Scripting/Localization)."""
    return {name: Node("TGDVariableCamp", [*((p, Value(tag, v)) for p, tag, v in scalars),
                                           ("PlayerName", loc(tokens[name]))],
                       export=f"{GD}/RootDescriptor/{name}")
            for name, scalars, _ in camps}


def setdeck_block(camps: Mapping[str, Node], rows: Sequence[CampRow]) -> list[Node]:
    """One SetDeck per camp row (Survivors S#117-#120), each with its row's deck."""
    return [Node("TGDDescriptorSetDeck", [("Camp", camps[name]), ("DeckIdentifier", Str(deck))])
            for name, _, deck in rows]


class Ctx:
    """One build's script state: `camps` (camp_nodes, by export name), `sides` (a side's name -> its camp's export
    name; `player` is the player's side), the GdItems tag of every item of `items` (keyed to `scenario` under the GUID
    `namespace`: gates.check_binding fails tags made for another scenario), and the script variables, exported under
    `folder`/Variables, each made once per name (two beats naming one variable share it)."""

    def __init__(self, camps: Mapping[str, Node], sides: Mapping[str, str], player: str, items: Sequence[LdItem],
                 scenario: str, namespace: str, folder: str) -> None:
        self.camps = dict(camps)
        self.sides = dict(sides)
        self.player = player
        self.items = list(items)
        self.folder = folder
        self.tags: dict[str, Node] = {}
        for key, tag in gd_tags(self.items, scenario, namespace).items():
            name = key.split("/", 1)[1]
            check(name not in self.tags, f"two ITEMS entries are named {name}")
            self.tags[name] = tag
        self.variables: dict[str, Node] = {}

    def camp(self, side: str) -> Node:
        """The camp of side `side`."""
        return self.camps[self.sides[side]]

    def group(self, name: str) -> Node:
        return self._variable(name, "TGDVariableUnitGroup")

    def int_var(self, name: str) -> Node:
        return self._variable(name, "TGDVariableInteger")

    def timer(self, name: str, seconds: int) -> Node:
        """The script timer `name` of `seconds` (bricks.g_timer), exported with the variables, made once per name."""
        node = self.variables.setdefault(name, g_timer(seconds, export=f"{self.folder}/Variables/{name}"))
        check(node.cls == "TGDVariableTimer" and dict(node.props)["Duree"].v == seconds,
              f"variable {name} is a {node.cls}, not a timer of {seconds} s")
        return node

    def tag(self, name: str) -> Node:
        """The GdItems tag of the item named `name`."""
        check(name in self.tags, f"{name} is not an ITEMS entry")
        return self.tags[name]

    def _variable(self, name: str, cls: str) -> Node:
        node = self.variables.setdefault(name, Node(cls, export=f"{self.folder}/Variables/{name}"))
        check(node.cls == cls, f"variable {name} is a {node.cls}, not a {cls}")
        return node


@dataclass(frozen=True)
class Minimap:
    """LevelDesign items placed by minimap pixels on `map`, by position or by the name of one of `points`."""
    map: StockMap
    points: Mapping[str, tuple[float, float]]

    def at(self, at: str | tuple[float, float], what: str = "") -> tuple[float, float]:
        """`at` in minimap px: a named point's, or `at` itself."""
        if isinstance(at, str):
            check(at in self.points, f"{what}: {at} is not a named point of the map")
            return self.points[at]
        return at

    def item(self, ranking: str, name: str, at: str | tuple[float, float], addon: str, **kw) -> LdItem:
        """An item at `at` (a named point or minimap px), in world units."""
        x, y = self.map.px_to_world(self.at(at, f"{ranking}/{name}"))
        return LdItem(ranking, name, x, y, addon, **kw)

    def zone_item(self, ranking: str, name: str, box: tuple[float, float, float, float], addon: str,
                  **kw) -> LdItem:
        """A deployment or command zone over a minimap-px box (x0, y0, x1, y1): the closed world polygon, the item at
        its centre."""
        x0, y0, x1, y1 = box
        polygon = rect_polygon((*self.map.px_to_world((x0, y0)), *self.map.px_to_world((x1, y1))))
        return self.item(ranking, name, ((x0 + x1) / 2, (y0 + y1) / 2), addon, polygon=polygon, **kw)

    def ring_item(self, name: str, point: str | tuple[float, float], radius_px: float) -> LdItem:
        """A CircularZone of `radius_px` minimap px around `point` (RadiusGRU at GRU_WORLD). The game's unit
        detectors read circles only (DetectUnitDansDetecteur)."""
        return self.item("CircularZones", name, point, "CircularZone",
                         radius_gru=radius_px * self.map.world_per_px / GRU_WORLD)

    def arrival_item(self, ranking: str, name: str, start: str | tuple[float, float], end: str | tuple[float, float],
                     addon: str, **kw) -> LdItem:
        """A ReinforcementLocation or AerialCorridor (`addon`) from `start` to `end` (named points or minimap px), laid
        out as stock's entries are: the item at the midpoint of Start and End, Rotation the Start -> End heading
        (gates.check_zone_layout's midpoint and heading clauses)."""
        where = f"{ranking}/{name}"
        s, e = self.map.px_to_world(self.at(start, where)), self.map.px_to_world(self.at(end, where))
        return LdItem(ranking, name, (s[0] + e[0]) / 2, (s[1] + e[1]) / 2, addon, rotation=heading(s, e), start=s,
                      end=e, **kw)

    # ------------------------------------------------------------------ reading items back

    def px_of(self, it: LdItem) -> tuple[float, float]:
        return self.map.world_to_px((it.x, it.y))

    def radius_px(self, it: LdItem) -> float:
        return it.radius_gru * GRU_WORLD / self.map.world_per_px

    def box_px(self, it: LdItem) -> tuple[float, float, float, float]:
        """A zone item's polygon bounds in minimap px (x0, y0, x1, y1)."""
        xs, ys = zip(*(self.map.world_to_px(p) for p in it.polygon))
        return min(xs), min(ys), max(xs), max(ys)


# --------------------------------------------------------------------------- blocks

def beat_hint(token: str, *actions: Node) -> Node:
    """A timed beat's action: its hint beside the actions (the Sledgehammer #569 shape), so the hint does not hold the
    actions back for its HINT_S."""
    return g_simul([g_hint(token, HINT_S, "shint"), *actions])


def objective(text: str, label: str, condition: Node | None, position: Node | None = None,
              counters: list[Node] | None = None, *, fail: Node | None = None, reussi: Node | None = None,
              echec: Node | None = None, kind: str = "Primary", label_counters: list[Node] | None = None,
              timers: list[Node] | None = None) -> Node:
    """GereObjectif in stock property order (DelayedRetribution #344 with counters). `counters` fill the %1 (and %2)
    of both texts (ListVariables: ObjectiveText; ListVariablesForEtiquetteText: the label). `label_counters` fill the
    label's only (ListVariablesForEtiquetteText, no ListVariables: DelayedRetribution #344, Survivors #295); give one
    or the other. `timers` (bricks.g_timer) fill the label's %1 with a running clock instead (ListTimersForEtiquetteText:
    the 7 stock timer objectives, TheWingedHussars #487 "Time remaining %1" among them), with no counters: no stock
    objective lists both. Only an objective with a `position` shows its map label (ShowEtiquette): a positionless
    objective's pin lands in the map corner, and stock leaves ShowEtiquette out on its positionless objectives; the
    objective list shows the label's text either way. `fail` is the ConditionEchec, `reussi` and `echec` the
    ActionsReussi and ActionsEchec, the first properties (Survivors #295); a None `condition` makes a fail-only
    objective (TheHydra #101); `kind` is the LabelComponent ('Bonus': Survivors #775). It finishes only once it
    resolves and its chosen action has, so it goes last in its Sequential."""
    check(not (counters and label_counters), "objective: give counters (both texts) or label_counters (the label "
                                             "only), not both")
    check(not (timers and (counters or label_counters)), "objective: a label shows timers or counters, not both (no "
                                                         "stock objective lists both)")
    props: list[tuple[str, object]] = [*([("ActionsEchec", echec)] if echec is not None else []),
                                       *([("ActionsReussi", reussi)] if reussi is not None else []),
                                       ("BonusScoreMission", i32(50)),
                                       *([("Condition", condition)] if condition is not None else []),
                                       *([("ConditionEchec", fail)] if fail is not None else []),
                                       ("LabelComponent", Str(kind)),
                                       *([("ListTimersForEtiquetteText", list(timers))] if timers else [])]
    if counters:
        props += [("ListVariables", list(counters)), ("ListVariablesForEtiquetteText", list(counters))]
    elif label_counters:
        props += [("ListVariablesForEtiquetteText", list(label_counters))]
    props += [("ObjectiveEtiquetteText", loc(label)), ("ObjectiveText", loc(text))]
    props += [("Position", position)] if position is not None else []
    return Node("TGDDescriptorGereObjectif", props + [("ShowAddAnimation", TRUE), ("ShowBaseAnimation", TRUE),
                                                       *([("ShowEtiquette", TRUE)] if position is not None else [])])


def create(ctx: Ctx, side: str, group: Node, count: int, at: Node, unit: str) -> Node:
    """CreateUnitOnPosition of `count` `unit` (a unit_path) into `group`, in `side`'s camp, at tag `at`. A beat that
    creates enemy units the player should see ends with reveal() on their groups."""
    return g_create(ctx.camp(side), group, count, at, unit)


def set_effect(effect: str, groups: list[Node]) -> Node:
    """SetEffect of the EffectCapacity pack `effect` on `groups`, in stock property order: Effet, UnitGroup
    (RedJuggernaut #347). It never finishes, and its effect holds only while it runs."""
    return Node("TGDDescriptorSetEffect", [("Effet", Imp(f"$/GFX/EffectCapacity/{effect}")),
                                           ("UnitGroup", list(groups))])


def reveal(groups: list[Node], rest: list[Node]) -> Node:
    """The end of a beat that creates enemy units: Simultaneous[SetEffect(REVEAL_EFFECT, `groups`), Sequential[`rest`,
    the rest of the beat]], placed after the beat's creates as its last node. The pack is stock, but only a capacity
    uses it.

    SetEffect never finishes and its effect lasts only while it runs: in a beat's Sequential right after a create, it
    would stop the beat there. So it runs beside the rest of the beat, as BlackHorsesLastStand Sequential#185 runs a
    ModifyUnitSpeed, which also lasts: [CreateUnitOnPosition #218, Simultaneous #219[ModifyUnitSpeed #258,
    LaunchSmartOrder #259]]. The units are in their groups by then (CreateUnitOnPosition adds them at once), and units
    that join later get the effect too. The Simultaneous never finishes either, so nothing may follow it."""
    return g_simul([set_effect(REVEAL_EFFECT, groups), *([g_seq(rest)] if rest else [])])


def move(group: Node, *positions: Node, blocking: bool = False) -> Node:
    """MoveUnitGroup in stock order (HoldUntilRelieved #396 with Blocking, Sledgehammer #637 without)."""
    return Node("TGDDescriptorMoveUnitGroup", [*([("Blocking", TRUE)] if blocking else []), ("Group", group),
                                               ("Positions", list(positions))])


def order(group: Node, order_type: int, position: Node | None, blocking: bool = False,
          cancelable: bool = False) -> Node:
    """A GiveOrderStandard to a position: non-blocking (Survivors #1231, Marauders #1276), or with `blocking` one
    its Sequential waits on until the group arrives (DelayedRetribution #275/#276), which a caller races against a
    timeout (mission.lane_route). `cancelable` writes OrderCancelable (Survivors #1496, its aircraft's
    AirplaneMoveAndEngage); `position` None writes none (Survivors #1648, AirplaneEvacuate)."""
    return Node("TGDDescriptorGiveOrderStandard", [*([("Blocking", TRUE)] if blocking else []), ("Group", group),
                                                   *([("OrderCancelable", TRUE)] if cancelable else []),
                                                   ("OrderType", i32(order_type)),
                                                   *([("Position", position)] if position is not None else [])])


def add_card(ctx: Ctx, unit: str, count: int, transport: str | None = None, experience: int | None = None) -> Node:
    """AddUnitToDeck to the player's deck. Stock order (HoldUntilRelieved #383, SigurdsStrike #1042): Camp,
    [Experience], NbUnitsToAdd, TypeUnit; the native's own properties sort by name, so Transporter sits before TypeUnit
    (a content with a `transport` admits TRANSPORTER_SHAPE). An `experience` is written even when 0 (the native's
    default, which the stock serialiser leaves out), so the dump shows what the card asks for."""
    props: list[tuple[str, object]] = [("Camp", ctx.camp(ctx.player)),
                                       *([("Experience", i32(experience))] if experience is not None else []),
                                       ("NbUnitsToAdd", i32(count))]
    props += [("Transporter", Imp(unit_path(transport)))] if transport else []
    return Node("TGDDescriptorAddUnitToDeck", props + [("TypeUnit", Imp(unit_path(unit)))])


def lock_card(ctx: Ctx, unit: str, until: Node) -> Node:
    """A deck card locked until `until` holds: Competition[WaitCondition(until), LockDeckUnit], stock's lock in stock
    order (BlackHorsesLastStand "A10_Blocking" #94 = [#131, #132]). LockDeckUnit never finishes and locks only while it
    runs, so the race's end unlocks the card."""
    lock = Node("TGDDescriptorLockDeckUnit", [("Camp", ctx.camp(ctx.player)),
                                              ("Units", [Node("TGDDeckUnit", [("Unit", Imp(unit_path(unit)))])])])
    return g_compete([g_until(until), lock])


def set_end(end: Node, value: int) -> Node:
    """`end` = `value` only while it is still 0, so the first ending stands and one funnel then ends the game
    (gates.check_end_funnel): IfThenElse(end == 0, Simultaneous[set]) (stock branches are containers: Survivors #295's
    ActionsReussi IfThenElse)."""
    return g_if(g_cmp(end), g_simul([g_set(end, value)]))


def seconds_while(holds: Callable[[], Node], broken: Callable[[], Node], var: Node, reset: bool) -> Node:
    """A forever loop that adds 1 to `var` every POLL_S while `holds()` is true: WaitCondition(holds), then
    Competition[Sequential(forever)[WaitDuration POLL_S, var += 1], WaitCondition(broken)] (bricks.g_hold's race of a
    timer against its break), then, with `reset`, var = 0 (a streak); without, `var` sums every stay. Event-driven, as
    stock's count waits are: no IfThenElse reads a count. `holds` and `broken` build fresh condition nodes."""
    tick = g_seq([g_wait(POLL_S), g_modify(var, ADD, 1)], runs=FOREVER)
    return g_seq([g_until(holds()), g_compete([tick, g_until(broken())]), *([g_set(var)] if reset else [])],
                 runs=FOREVER)


def count_ladder(inside: Callable[[int, int], Node], var: Node, top: int) -> list[Node]:
    """Loops that keep `var` = the count `inside(value, op)` compares, up to `top` (top means top or more): one forever
    loop per k in 1..top, Sequential[WaitCondition(count >= k), var += 1, WaitCondition(count <= k - 1), var -= 1], so
    `var` is the number of thresholds the count has reached. A zone count is a condition, not a number, and stock reads
    one with IfThenElse only once (BlackHorsesLastStand #223); a WaitCondition on it is stock's way (Marauders
    Sequential#516's WaitCondition(And[UnitDansZone x2])). `inside` builds a fresh condition each call."""
    return [g_seq([g_until(inside(k, GE)), g_modify(var, ADD, 1), g_until(inside(k - 1, LE)), g_modify(var, SUB, 1)],
                  runs=FOREVER) for k in range(1, top + 1)]


def dialog_tokens(roots: list[Node]) -> list[str]:
    """The text token of every cutscene text component under `roots`, in first-use order (script.silent_cutscenes
    gives each the silent sound)."""
    out: list[str] = []
    for nd in walk(roots):
        if nd.cls == "TGDDescriptorCutsceneTextComponent":
            token = token_unhash(int.from_bytes(dict(nd.props)["LocalizedText"].v, "little"))
            if token not in out:
                out.append(token)
    return out
