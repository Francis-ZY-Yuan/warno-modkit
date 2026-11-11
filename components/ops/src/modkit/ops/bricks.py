"""Script bricks: small builders for GDScript actions (g_*), conditions and unit constraints (c_*).

Each returns a fresh ``Node``. Shapes (property order, value tags) follow the stock objects surveyed in the 16
Operations; a shape gate re-checks every generated object against stock. Comments name the stock object a shape
comes from: S = Survivors, D = TheDieburgSalient, B = BlackHorsesLastStand, R = DelayedRetribution,
HUR = HoldUntilRelieved (``S#778`` is object 778 of Survivors' GDScript).
"""
from __future__ import annotations

from typing import Callable, Sequence

from modkit.core.names import unit_path  # noqa: F401 - core's, re-exported here for the bricks' users
from modkit.ops.graph import TRUE, Imp, Node, Str, f32, i32, loc, u32


def g_seq(actions: list[object], runs: int = 1, export: str | None = None) -> Node:
    return Node("TGDDescriptorSequential", [("SubActions", actions), ("NbExecutions", u32(runs))], export)


def g_simul(actions: list[object], export: str | None = None) -> Node:
    return Node("TGDDescriptorSimultaneous", [("SubActions", actions), ("NbExecutions", u32(1))], export)


def g_compete(actions: list[object], export: str | None = None) -> Node:
    """First child to finish ends it (stock: hint until phase change, hold-for-N-seconds)."""
    return Node("TGDDescriptorCompetition", [("SubActions", actions), ("NbExecutions", u32(1))], export)


def g_wait(seconds: float) -> Node:
    return Node("TGDDescriptorWaitDuration", [("Duree", f32(seconds))])


def g_until(cond: Node) -> Node:
    return Node("TGDDescriptorWaitCondition", [("Condition", cond)])


def g_int_compare(value: int | None = None, op: int | None = None, other: Node | None = None) -> Node:
    """EGDOperator: 0 Equal (default), 2 MoreOrEqual, 3 LessOrEqual, 5 StrictlyLess; value 0 omitted."""
    props: list[tuple[str, object]] = [("Variable", other)] if other is not None else []
    props += [("Value", i32(value))] if value else []
    props += [("OperatorType", i32(op))] if op else []
    return Node("TGDOperatorIntegerCompare", props)


def g_cmp(var: Node, value: int | None = None, op: int | None = None, other: Node | None = None) -> Node:
    """`var <op> value|other` on a VariableInteger, VariableUnitGroup (unit count) or timer."""
    return Node("TGDConditionVariable", [("Operator", g_int_compare(value, op, other)), ("Variable", var)])


def g_detect(zone: Node, contrainte: Node, value: int | None = None, op: int | None = None,
             compare: bool = True) -> Node:
    """Units matching `contrainte` in `zone` <op> value (compare=False: no comparison, as AddDetected uses)."""
    props: list[tuple[str, object]] = [("ComparaisonNbUnits", g_int_compare(value, op))] if compare else []
    return Node("TGDConditionDetectUnitDansDetecteur", props + [("Detecteur", zone), ("Contrainte", contrainte)])


def g_and(*conds: Node) -> Node:
    return Node("TGDConditionAnd", [("SousConditions", list(conds))])


def g_or(*conds: Node) -> Node:
    return Node("TGDConditionOr", [("SousConditions", list(conds))])


def c_team(camp: Node) -> Node:
    return Node("TGDContrainteOnUnitTeam", [("Camp", camp)])  # OperatorType SameTeam (0) omitted


def c_type(unit: str) -> Node:
    return Node("TGDContrainteOnUnitType", [("TypeUnit", Imp(unit_path(unit)))])


def c_all(*cs: Node) -> Node:
    return Node("TGDContrainteOnUnitAllContrainte", [("ContrainteList", list(cs))])


def c_none(*cs: Node) -> Node:
    return Node("TGDContrainteOnUnitNoContrainte", [("ContrainteList", list(cs))])


def c_any(*cs: Node) -> Node:
    return Node("TGDContrainteOnUnitAnyContrainte", [("ContrainteList", list(cs))])


def g_set(var: Node, value: int = 0, other: Node | None = None) -> Node:
    """ModifieVariableInteger Set (EVariableIntegerModification 0, omitted): var = value | other."""
    props: list[tuple[str, object]] = [("Variable1", var)]
    props += [("Variable2", other)] if other is not None else [("Value", i32(value))] if value else []
    return Node("TGDDescriptorModifieVariableInteger", props)


def g_modify(var: Node, kind: int, value: int = 0, other: Node | None = None) -> Node:
    """kind: 1 Add, 2 Substract."""
    props: list[tuple[str, object]] = [("Variable1", var)]
    props += [("Variable2", other)] if other is not None else [("Value", i32(value))]
    return Node("TGDDescriptorModifieVariableInteger", props + [("ModificationType", i32(kind))])


def g_count(var: Node, group: Node) -> Node:
    return Node("TGDDescriptorSetVariableIntegerFromUnitGroup", [("Group", group), ("Variable", var)])


def g_collect(group: Node, detector: Node) -> Node:
    return Node("TGDDescriptorAddDetectedUnitsToUnitGroup", [("Detector", detector), ("Group", group)])


def g_ammo(units: Sequence[Node], refill: bool = False) -> Node:
    """SetAmmo on `units` (unit groups or Spawn tags) in stock's two forms: with `refill`, MaxAmmoRatio 100, full
    (HoldUntilRelieved #281; every stock MaxAmmoRatio is 100); else Units only, MaxAmmoRatio left at its 0, emptied
    (Survivors #1332, its captured T-55). It is instantaneous."""
    return Node("TGDDescriptorSetAmmo", [*([("MaxAmmoRatio", i32(100))] if refill else []), ("Units", list(units))])


def g_vanish(*groups: Node) -> Node:
    return Node("TGDDescriptorKillAllUnit", [("GroupList", list(groups))])  # DeathCause Vanished (0) omitted


def g_kill(*groups: Node, cause: int | None) -> Node:
    """KillAllUnit of `groups` with DeathCause `cause` (an EDeathCause: shapes.PENETRATION; no stock challenge writes
    one, so a content that does admits shapes.DEATH_CAUSE_SHAPE), or with `cause` None Vanished (g_vanish: the
    cause left out)."""
    if cause is None:
        return g_vanish(*groups)
    return Node("TGDDescriptorKillAllUnit", [("DeathCause", i32(cause)), ("GroupList", list(groups))])


def g_union(into: Node, groups: Sequence[Node]) -> Node:
    """AddUnitGroupListToUnitGroup: the units of `groups` (unit groups or Spawn tags) join `into` now (S#1331:
    GroupDestination, ListGroupSource)."""
    return Node("TGDDescriptorAddUnitGroupListToUnitGroup", [("GroupDestination", into),
                                                             ("ListGroupSource", list(groups))])


def g_spawn(tags: Sequence[Node]) -> Node:
    """SpawnUnits: reveals the pre-placed hidden units (Spawn items with DisableAutoSpawn) at the tags `tags`
    (S#1330). Stock never puts one straight in a Simultaneous: it sits in a Sequential."""
    return Node("TGDDescriptorSpawnUnits", [("Units", list(tags))])


def g_create(camp: Node, group: Node, count: int, pos: Node, unit: str) -> Node:
    return Node("TGDDescriptorCreateUnitOnPosition", [("Camp", camp), ("Group", group), ("NbUnit", i32(count)),
                                                      ("Position", pos), ("TypeUnit", Imp(unit))])


def g_roe(group: Node, behaviour: int) -> Node:
    """SetShotReactionROEBehavior: `behaviour` is an EShotReactionBehaviour (2 Agressive)."""
    return Node("TGDDescriptorSetShotReactionROEBehavior", [("Group", group), ("ShotReactionBehavior", i32(behaviour))])


def g_idle_roe(group: Node, behaviour: int) -> Node:
    """SetIdleROEBehavior: what `group`'s units do when idle; `behaviour` is an EIdleBehavior (1 AutoCover, 2 IADefend,
    the HOLD POSITION button; shapes.IDLE_HOLD_POSITION). Stock order and form (Survivors #188: Group, IdleBehavior
    int32; RunningTheGauntlet #105 and Sledgehammer #319 write 2). It finishes at once."""
    return Node("TGDDescriptorSetIdleROEBehavior", [("Group", group), ("IdleBehavior", i32(behaviour))])


def g_ignored(group: Node) -> Node:
    """AddIgnoredUnitByScript: keeps `group`'s units off their camp's AI, for the script alone (TheDieburgSalient
    #143-#145 on its scripted 2S1 battery: UnitGroup only). It finishes at once (siblings follow it in Marauders and
    RunningTheGauntlet)."""
    return Node("TGDDescriptorAddIgnoredUnitByScript", [("UnitGroup", group)])


def g_attack(group: Node, targets: Node) -> Node:
    """Attack: `group` attacks the units of the group `targets`, blocking (Survivors #1099: Blocking, Group,
    AttackEnPrioriteUniteNotUbserstress True, Targets = Groupe_Joueur; 41 of its 48 Attacks write exactly these). Stock
    puts every Attack last in its Sequential, never in a loop (65/65)."""
    return Node("TGDDescriptorAttack", [("Blocking", TRUE), ("Group", group),
                                        ("AttackEnPrioriteUniteNotUbserstress", TRUE), ("Targets", targets)])


def g_income(camp: Node, amount: int) -> Node:
    """SetIncomeToTeam: `camp`'s income from now on, per income tick (DelayedRetribution #109: Camp, Quantite). An
    `amount` of 0 leaves Quantite out, as stock writes a zero income (RunningTheGauntlet #275/#286/#296), never as an
    explicit 0. It finishes at once (TheWingedHussars #318 is followed in its Sequential)."""
    return Node("TGDDescriptorSetIncomeToTeam", [("Camp", camp), *([("Quantite", i32(amount))] if amount else [])])


def g_grant(camp: Node, amount: int) -> Node:
    """GiveRessourceToTeam: `amount` command points (ResourceType 1) given to `camp` once (BlackHorsesLastStand #312:
    Camp, Quantite, ResourceType, in a Simultaneous after its wait)."""
    return Node("TGDDescriptorGiveRessourceToTeam", [("Camp", camp), ("Quantite", i32(amount)),
                                                     ("ResourceType", i32(1))])


def g_planes_spent(group: Node, count: int) -> Node:
    """UnitGroupWithFilter: at least `count` of `group`'s units have run out of fuel or ammunition, Survivors' test
    before it sends its strike aircraft home (#1682, under WaitCondition #1647): Operator MoreOrEqual `count`, the
    group, and AnyContrainte of its three ContrainteOnUnitLogistic, node for node. Survivors' group holds two
    Harriers and asks for 2: all of them."""
    def logistic(kind: int, at_most: int) -> Node:
        return Node("TGDContrainteOnUnitLogistic", [*([("OperatorType", i32(kind))] if kind else []),
                                                    ("CompareInteger", g_int_compare(at_most, 3))])

    return Node("TGDConditionUnitGroupWithFilter", [
        ("Operator", g_int_compare(count, 2)), ("Variable", group),
        ("Contrainte", c_any(logistic(2, 0), logistic(2, 0), logistic(0, 50)))])


def g_zone_owner(camp: Node, zones: Sequence[Node]) -> Node:
    """SetCommandZoneOwnerAndForceConvergence: `camp` owns each command zone whose polygon holds a tag of `zones` and
    its influence grid is filled, so the owner holds with no commander inside (HoldUntilRelieved #107 at deployment,
    Marauders #1134 after a count race). A tag in no command zone does nothing."""
    return Node("TGDDescriptorSetCommandZoneOwnerAndForceConvergence", [("Camp", camp), ("Positions", list(zones))])


def g_fx(name: str, pos: Node) -> Node:
    return Node("TGDDescriptorLaunchFXFireAndForgetOnPosition", [("DatabaseName", Str(name)), ("Position", pos)])


def g_dialog(token: str) -> Node:
    """Text-only dialog box, the stock intro shape (D#257/D#392); voiced by a silent sound descriptor."""
    return Node("TGDDescriptorEncapsuleCutscene", [("SubActions", [
        Node("TGDDescriptorCutscenePlayDialogList", [
            ("DialogList", [Node("TGDDescriptorCutsceneDialog", [
                ("CanBeSkippedWithEscape", TRUE),
                ("ComponentName", Str("Component_1Text")),
                ("DureePause", f32(-1.0)),
                ("TextComponentsToFill", [Node("TGDDescriptorCutsceneTextComponent", [
                    ("UIComponentName", Str("Text1")), ("LocalizedText", loc(token))])]),
                ("TokenBoutonChoix0", loc("SI_NEXT")),
                ("VisibleByAlliedOfSpecifiedCamp", TRUE),
            ])]),
            ("DelayToWaitAfterEndingLastDialogSound", f32(1.0)),
        ])])])


def g_camera(path: str, seconds: float | None = None) -> Node:
    """The camera runs the camera path `path` (a CamPaths_LevelDesign path of the scenario's Details), easing in and
    out, skippable with Escape, with the player's actions blocked while it moves: EncapsuleCutscene[
    CutsceneStartCameraPath], stock order. With no `seconds`, a one-key path is a snap (DelayedRetribution #65/#79,
    camera_intro_end); with `seconds`, the camera flies a path of two keys or more in that time (DelayedRetribution
    #92, camera_intro: 2 keys in 20 s). DelayedRetribution, GloryOrAttrition and TheHydra open so, right after
    LoadingDone: the move, then a snap to its last key."""
    timed = [("TimeInSecond", f32(seconds))] if seconds is not None else []
    return Node("TGDDescriptorEncapsuleCutscene", [("SubActions", [
        Node("TGDDescriptorCutsceneStartCameraPath", [
            ("CameraPathName", Str(path)), *timed, ("AccelerationActivated", TRUE), ("DecelerationActivated", TRUE),
            ("CanBeSkippedWithEscape", TRUE), ("VisibleByAlliedOfSpecifiedCamp", TRUE)])]),
        ("BlockPlayerActions", TRUE)])


def g_hint(token: str, seconds: float, component: str) -> Node:
    """LDHint panel, stock property order. 'shint_op' Time -1 stays up until its Competition drops it (HUR #208,
    beside the phase gate); 'shint' Time 15 is the mid-battle notice (Sledgehammer #601, beside a spawn)."""
    return Node("TGDDescriptorLDHint", [("Info", loc(token)), ("Time", f32(seconds)), ("ComponentName", Str(component)),
                                        ("VisibleByAlliedOfSpecifiedCamp", TRUE)])


def g_hold(cond: Callable[[], Node], broken: Callable[[], Node], seconds: float, flag: Node,
           export: str | None = None) -> Node:
    """Set `flag` = 1 once `cond` has held for `seconds` without a break; the timer restarts on a break."""
    return g_compete([
        g_seq([g_until(cond()), g_compete([g_seq([g_wait(seconds), g_set(flag, 1)]), g_until(broken())])],
              runs=0xFFFFFFFF),
        g_until(g_cmp(flag, 1)),
    ], export)


def g_end_sequence(token: str, victory_type: int, winner: int | None, export: str) -> Node:
    """S#778/S#781 wrap-up: hide the HUD, outro dialog, TriggerEndGame(ScriptDecided)."""
    result = [("VictoryReason", i32(6)), ("VictoryType", i32(victory_type))]
    result += [("WinningAlliance", i32(winner))] if winner is not None else []
    return g_seq([Node("TGDDescriptorForceDisplayUIElement", [("ForceHideAll", TRUE)]), g_dialog(token),
                  Node("TGDDescriptorTriggerEndGame", result)], export=export)


def g_if(cond: Node, then: Node, otherwise: Node | None = None) -> Node:
    props: list[tuple[str, object]] = [("Condition", cond), ("EffetIfTrue", then)]
    return Node("TGDDescriptorIfThenElse", props + ([("EffetIfFalse", otherwise)] if otherwise else []))


# --------------------------------------------------------------------------- mission bricks
# Each copies a stock object's property order and value forms, cited by scenario and object id (the scenarios'
# decoded scripts).

# Their enumeration values are shapes' constants (SCRIPT_DECIDED, the victory types, EASY .. HARD, SEIZE): a brick
# takes every value as an argument, or writes the one stock value its shape always has.


def g_choice(token: str, button0: str, button1: str, camp: Node, chosen: Node) -> Node:
    """A two-button dialog in stock order (Sledgehammer #590/#621): text `token`, buttons `button0` and `button1`
    (INGAME tokens only: gates.INGAME_PROPS), shown to `camp`'s side with the game paused until a button is picked,
    which sets `chosen` to 0 or 1 (Sledgehammer routes on it in IfThenElse #591). It sits in a Sequential: no stock
    Simultaneous holds one."""
    return Node("TGDDescriptorEncapsuleCutsceneDialogListWithMultipleChoice", [("DialogList", [
        Node("TGDDescriptorCutsceneDialogWithMultipleChoice", [
            ("AfficherBoutonPause", TRUE),
            ("ComponentName", Str("Component_1Text")),
            ("DureePause", f32(-1.0)),
            ("Pause", TRUE),
            ("TextComponentsToFill", [Node("TGDDescriptorCutsceneTextComponent", [
                ("UIComponentName", Str("Text1")), ("LocalizedText", loc(token))])]),
            ("TokenBoutonChoix0", loc(button0)),
            ("VisibleByAlliedOfSpecifiedCamp", TRUE),
            ("VisibleByCamp", camp),
            ("SelectedButton", chosen),
            ("TokenBoutonChoix1", loc(button1)),
        ])])])


def g_difficulty(level: int) -> Node:
    """ConditionOnGameDifficulty: true when the battle runs at `level` (shapes.EASY, MEDIUM, HARD). Difficulty 0 is
    omitted, so Easy is an empty object (HoldUntilRelieved #199; Medium #201, Hard #203). All three are false when the
    game passes no difficulty."""
    return Node("TGDConditionOnGameDifficulty", [("Difficulty", i32(level))] if level else [])


def g_end_game(victory_type: int, winner: int | None = None) -> Node:
    """TriggerEndGame decided by the script (VictoryReason 6, shapes.SCRIPT_DECIDED), graded `victory_type`
    (shapes.MINOR_VICTORY .. TOTAL_VICTORY): the player wins with `winner` None (Gotterdammerung #258: VictoryReason 6,
    VictoryType 6), loses with shapes.PACT_ALLIANCE (#254). It never finishes, and only the first call of a battle
    counts, so a script sends every ending through one funnel (gates.check_end_funnel). Stock places it last in a
    Sequential; no Simultaneous or IfThenElse branch holds one bare."""
    props = [("VictoryReason", i32(6)), ("VictoryType", i32(victory_type))]
    props += [("WinningAlliance", i32(winner))] if winner is not None else []
    return Node("TGDDescriptorTriggerEndGame", props)


def g_zone_control(camp: Node, zone: Node) -> Node:
    """ConditionTeamControleZone: `camp`'s side owns the command zone whose polygon holds tag `zone` (TheDieburgSalient
    #262: Position, Camp, AutoriseControleAllie True, ZoneType 1, as all 131 stock uses). ZoneType 1 is written: an
    omitted ZoneType is 0, the deployment-zone file (gates.check_zone_tags)."""
    return Node("TGDConditionTeamControleZone", [("Position", zone), ("Camp", camp), ("AutoriseControleAllie", TRUE),
                                                 ("ZoneType", i32(1))])


def g_units_in_zones(zones: Sequence[Node], contrainte: Node, value: int | None = None, op: int | None = None) -> Node:
    """ConditionUnitDansZone: the units matching `contrainte` inside the union of the command zones holding the tags
    `zones`, compared with `value` (Marauders #1343/#1344: ComparaisonNbUnits, Detecteurs, Contrainte, ZoneType 1).
    ZoneType 1 is written, as in all 4 stock uses: with 0 a tag outside every deployment zone counts every unit
    outside all zones."""
    return Node("TGDConditionUnitDansZone", [("ComparaisonNbUnits", g_int_compare(value, op)),
                                             ("Detecteurs", list(zones)), ("Contrainte", contrainte),
                                             ("ZoneType", i32(1))])


def g_kills(var: Node, camp: Node, units: Sequence[str] = ()) -> Node:
    """GetNbKillsCamp: `var` = how many units of the types `units` (unit_path suffixes; none = every type) `camp` has
    killed, once (HoldUntilRelieved #237, TheDieburgSalient #332: Camp, TypeUnitList, Variable; each polled in
    Sequential(forever)[it, WaitDuration 1]). It counts by the victim's type, not its group."""
    types = [("TypeUnitList", [Imp(unit_path(u)) for u in units])] if units else []
    return Node("TGDDescriptorGetNbKillsCamp", [("Camp", camp), *types, ("Variable", var)])


def g_losses(var: Node, camp: Node) -> Node:
    """GetNbLossCamp: `var` = how many units `camp` has lost, once (GloryOrAttrition #161: Camp, Variable, polled in
    Sequential(forever) #111)."""
    return Node("TGDDescriptorGetNbLossCamp", [("Camp", camp), ("Variable", var)])


def g_seize(group: Node, zone: Node) -> Node:
    """LaunchSmartOrder Seize (SmartOrderType 1, shapes.SEIZE): `group` drives to the zone at tag `zone` and takes it
    (TheDieburgSalient #519: Position a CommandPoints tag, SmartOrderType 1, UnitGroup; its group #556 holds the
    T80BV_CMD_SOV created by #514). Only a command unit captures; other units just go there (BlackHorsesLastStand
    #259, 2 BMP-2). It finishes at once."""
    return Node("TGDDescriptorLaunchSmartOrder", [("Position", zone), ("SmartOrderType", i32(1)),
                                                  ("UnitGroup", group)])


def g_smart_hold(group: Node, at: Node) -> Node:
    """LaunchSmartOrder Hold (SmartOrderType 2, shapes.HOLD): `group` holds the place at tag `at` and redeploys to the
    best defensive positions near it (RedJuggernaut #249: Position a Name tag, SmartOrderType 2, UnitGroup; its village
    defenders, last in their container). It finishes at once (TheDieburgSalient #414-#416 run three in a row)."""
    return Node("TGDDescriptorLaunchSmartOrder", [("Position", at), ("SmartOrderType", i32(2)),
                                                  ("UnitGroup", group)])


def g_random(children: Sequence[Node]) -> Node:
    """RandomLauncher: runs one of `children`, picked at random, and finishes with it (BlackHorsesLastStand #100 and
    Marauders #282: SubActions, NbExecutions 1). Stock children are Sequential, SpawnUnits or WaitDuration only (the
    shape gate holds content to them)."""
    return Node("TGDDescriptorRandomLauncher", [("SubActions", list(children)), ("NbExecutions", u32(1))])
