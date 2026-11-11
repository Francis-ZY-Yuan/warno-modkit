"""Composed mission pieces: the parts of a mission script that more than one op uses, built from the bricks and shapes.

Each was first written inside an example (Open Door's op, the probes) and lives here so every op imports the one
copy. The caller passes its own names, tags, variables and timings; nothing here names an op. `Ctx` is
``modkit.ops.shapes.Ctx``. Comments name the stock object a shape comes from, as in ``modkit.ops.bricks``.

* Placed and hidden units (``placed_units``, ``hidden_units``): units of one camp laid out in a formation, standing
  from the start, or the player's hidden until a SpawnUnits reveals them.
* Lanes (``Leg``, ``Lane``, ``lane_route``): a group drives its lane by waypoints, each leg raced against a timeout.
* Waves and boarding (``Wave``, ``wave``, ``create_rows``, ``board``): rows created at a lane's entry, the riflemen
  boarding their carriers, then the lane.
* The dialog re-ask loop (``reask_loop``, ``CHOICE_NONE``): a two-button dialog asked again until an exit ends it.
* Zones (``zone_race``, ``zone_handover``): a timed count race over command zones, and handing zones to a side.
* Circle counts (``ring_round``): the units in detector circles, gathered into a group and counted.
* The end funnel (``end_funnel``): the one node that shows an ending's dialog and ends the battle.
* Difficulty (``difficulty``, ``after_launch``): a Medium baseline that the Easy and Hard branches overwrite.
* The script frame (``script_frame``): Main, the root and the export list around a list of beats.
"""
from __future__ import annotations

from collections.abc import Callable, Collection, Mapping, Sequence
from typing import NamedTuple

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.ops import script as ops_script
from modkit.ops.bricks import (
    c_team, g_and, g_choice, g_cmp, g_collect, g_compete, g_count, g_detect, g_dialog, g_difficulty, g_end_game,
    g_hint, g_if, g_or, g_seq, g_set, g_simul, g_union, g_units_in_zones, g_until, g_wait, g_zone_owner, unit_path,
)
from modkit.ops.forces import formation
from modkit.ops.graph import TRUE, Node, i32, template_scalars, walk
from modkit.ops.leveldesign import LdItem
from modkit.ops.shapes import (
    BATTLE_PHASE, DIFF_NONE, EASY, FAST_MOVE_AND_ATTACK, FOREVER, GD, GE, HARD, HINT_S, LE, MEDIUM, PACT_ALLIANCE,
    Beat, CampRow, Ctx, Minimap, create, dialog_tokens, order, seconds_while, setdeck_block,
)

Row = tuple[str, int, "str | None"]   # (unit descriptor, count, transport descriptor or None): a force row
Ending = tuple[str, int, bool]        # (dialog token, EVictoryType, whether the player loses): an end_funnel row
CHOICE_NONE = 2                       # a choice variable's value before an answer: no button gives it (0 or 1)


# --------------------------------------------------------------------------- placed and hidden units

def placed_units(minimap: Minimap, at: tuple[float, float], units: Sequence[tuple[str, str]], spacing_px: float,
                 cols: int, group: str, *, camp: int = 0, hidden: bool = False,
                 rotation: float | None = None, experience: int | None = None) -> list[LdItem]:
    """Units pre-placed in camp `camp` (its CampList index): one Spawn item per (item name, unit descriptor) of
    `units`, ranked Camp_<camp>, all in item group `group`, laid out by forces.formation, `cols` to a row,
    `spacing_px` minimap px apart, centred on `at` (minimap px), each facing `rotation` (None: no Rotation), at
    ExperienceLevel `experience` (None: left out). They stand from the start (the Camp_3 spawns of Survivors'
    LevelDesign) unless `hidden` (DisableAutoSpawn: until a SpawnUnits reveals them, bricks.g_spawn)."""
    spots = formation(at, len(units), spacing_px, cols)
    return [minimap.item(f"Camp_{camp}", name, spot, "Spawn", unit=unit, camp=camp, disable_auto_spawn=hidden,
                         group=group, rotation=rotation, experience=experience)
            for (name, unit), spot in zip(units, spots)]


def hidden_units(minimap: Minimap, at: tuple[float, float], units: Sequence[tuple[str, str]], spacing_px: float,
                 cols: int, group: str) -> list[LdItem]:
    """Player (camp 0) units hidden until a SpawnUnits reveals them (bricks.g_spawn): placed_units with
    DisableAutoSpawn, one Spawn item per (item name, unit descriptor) of `units`, all in item group `group`, laid out
    by forces.formation, `cols` to a row, `spacing_px` minimap px apart, centred on `at` (minimap px)."""
    return placed_units(minimap, at, units, spacing_px, cols, group, hidden=True)


# --------------------------------------------------------------------------- lanes

class Leg(NamedTuple):
    """A lane leg: to the waypoint tag named `to`, by `order` (an EOrderType; FastMoveAndAttack keeps to the roads).
    Every leg but the last is a blocking order raced against `timeout` seconds; the last has `timeout` None and is a
    plain order: nothing follows it. A route with a final node (lane_route's `final`) times its last leg too."""
    to: str
    timeout: float | None
    order: int = FAST_MOVE_AND_ATTACK


class Lane(NamedTuple):
    """A lane: the tag its waves are created at (`entry`), then its legs."""
    entry: str
    legs: tuple[Leg, ...]


def lane_route(ctx: Ctx, group: Node, legs: Sequence[Leg], final: Node | None = None) -> Node:
    """`group` drives `legs` by their waypoints. Each leg but the last is a blocking GiveOrderStandard in its own
    Sequential, raced against the leg's timeout (Marauders Competition#325's [WaitDuration, Sequential] shape; stock
    Competitions take no GiveOrderStandard bare; DelayedRetribution #275/#276 and RunningTheGauntlet #515/#516 block
    on a GiveOrderStandard leg by leg), so a unit that never arrives cannot hold the group at a waypoint: a timeout
    early only sends it on to the next. The last leg is a plain GiveOrderStandard (shapes.order: Survivors #1231).

    With a `final` node, the last leg is timed as the others are, and `final` follows it, last in the route's
    Sequential: what the group does once there, such as Survivors' follow-on Attack on the player's units
    (bricks.g_attack) [[wave-ends-with-attack]]. Without one the route is as above."""
    if final is None:
        check(bool(legs) and all(leg.timeout is not None for leg in legs[:-1]) and legs[-1].timeout is None,
              f"lane {[leg.to for leg in legs]}: every leg but the last needs a timeout, and the last none")
    else:
        check(bool(legs) and all(leg.timeout is not None for leg in legs),
              f"lane {[leg.to for leg in legs]}: with a final node every leg needs a timeout")
    timed = legs if final is not None else legs[:-1]
    steps = [g_compete([g_wait(leg.timeout), g_seq([order(group, leg.order, ctx.tag(leg.to), blocking=True)])])
             for leg in timed]
    last = final if final is not None else order(group, legs[-1].order, ctx.tag(legs[-1].to))
    return g_seq([*steps, last])


# --------------------------------------------------------------------------- waves and boarding

class Wave(NamedTuple):
    """A wave: its force rows, created at its lane's entry `offset` seconds after the wave's node starts; then it
    drives its lane (`lane`: a key of the lanes the caller gives wave())."""
    key: int
    offset: float
    lane: str
    rows: tuple[Row, ...]


def create_rows(ctx: Ctx, side: str, rows: Sequence[Row], at: Node, group: Node, inf: Node | None = None,
                ifv: Node | None = None, tracked: tuple[Node, Collection[str]] | None = None) -> list[Node]:
    """One CreateUnitOnPosition (shapes.create) per force row of `rows`, in `side`'s camp at tag `at`, in row order:
    a row with a transport (riflemen) into `inf`, a row of their carriers (a descriptor some row names as its
    transport) into `ifv`, a row of a type of `tracked` (a group and unit types, none of them riflemen or carriers)
    into its group, every other row into `group`. `inf` and `ifv` are needed only when a row has a transport."""
    carriers = {t for _, _, t in rows if t}
    check(not carriers or (inf is not None and ifv is not None),
          f"create_rows: rows with transports {sorted(carriers)} need the inf and ifv groups")
    trk, types = tracked if tracked is not None else (None, frozenset())
    check(not any(unit in types and (transport or unit in carriers) for unit, _, transport in rows),
          f"create_rows: tracked types {sorted(types)} may be neither riflemen nor carriers")

    def into(unit: str, transport: str | None) -> Node:
        return inf if transport else ifv if unit in carriers else trk if unit in types else group

    return [create(ctx, side, into(unit, transport), n, at, unit_path(unit)) for unit, n, transport in rows]


def board(riflemen: Node, carriers: Node, timeout: float) -> Node:
    """`riflemen` board `carriers` (LoadIntoTransporter Blocking, Survivors #786's ground boarding; script groups as
    in RunningTheGauntlet's four), raced against `timeout` seconds so a boarding that never ends holds nothing; the
    ones left follow on foot. Stock never races a LoadIntoTransporter bare, so it sits in its own Sequential. Stock
    boards ground vehicles only: none of its LoadIntoTransporter targets a helicopter."""
    load = Node("TGDDescriptorLoadIntoTransporter", [("Blocking", TRUE), ("Group", riflemen), ("Targets", carriers)])
    return g_compete([g_seq([load]), g_wait(timeout)])


def wave(ctx: Ctx, w: Wave, lanes: Mapping[str, Lane], *, side: str, prefix: str, board_s: float,
         track: tuple[str, Collection[str]] | None = None,
         before_route: Callable[[Node], Sequence[Node]] | None = None,
         final: Callable[[Node], Node] | None = None) -> Node:
    """Wave `w`: after `w.offset` seconds, its rows are created at its lane's entry (`lanes[w.lane]`, create_rows, in
    `side`'s camp) into the groups <prefix><key> (the wave), <prefix><key>_inf (its riflemen) and <prefix><key>_ifv
    (their carriers). The wave's vehicles join <prefix> (every wave's vehicles) before its riflemen join the wave,
    and the riflemen join <prefix>_inf; then the riflemen board (board(), raced against `board_s`; the ones left
    follow on foot) and the wave, riflemen and all, drives its lane (lane_route). RunningTheGauntlet #495-#499 then
    #515: create at one tag, board, then order the whole group. The route is the wave's only order, and no smart
    order (gates.check_smart_orders).

    `track` (a name and unit types) keeps those types' units in a group of their own, so a caller can count them
    alive (SetVariableIntegerFromUnitGroup [[kill-counts-by-type]]): a wave with such rows creates them into
    <prefix><key>_<name>, which joins the wave and <prefix>_<name> (every wave's), before the wave joins <prefix>.

    `before_route` gives the nodes the whole wave (its group) gets right before its route, such as its ROE
    (RunningTheGauntlet #326 sets its counter-attack group's idle behaviour before the group's legs); `final` gives the
    route's final node (lane_route's `final`: every leg timed, then it, last). Neither given: the wave is as above."""
    group, every = ctx.group(f"{prefix}{w.key}"), ctx.group(prefix)
    carriers = {t for _, _, t in w.rows if t}
    inf, ifv = (ctx.group(f"{prefix}{w.key}{s}") for s in ("_inf", "_ifv")) if carriers else (None, None)
    name, types = track if track is not None else ("", frozenset())
    trk = ctx.group(f"{prefix}{w.key}_{name}") if any(unit in types for unit, _, _ in w.rows) else None
    lane = lanes[w.lane]
    steps = [g_wait(w.offset)] if w.offset else []
    steps += create_rows(ctx, side, w.rows, ctx.tag(lane.entry), group, inf, ifv,
                         tracked=(trk, types) if trk is not None else None)
    if trk is not None:
        steps += [g_union(group, [trk]), g_union(ctx.group(f"{prefix}_{name}"), [trk])]
    steps.append(g_union(every, [group, *([ifv] if carriers else [])]))
    if carriers:
        steps += [g_union(ctx.group(f"{prefix}_inf"), [inf]), g_union(group, [inf, ifv]), board(inf, ifv, board_s)]
    steps += list(before_route(group)) if before_route is not None else []
    return g_seq([*steps, lane_route(ctx, group, lane.legs, final(group) if final is not None else None)])


# --------------------------------------------------------------------------- the dialog re-ask loop

def reask_loop(token: str, buttons: tuple[str, str], camp: Node, pick: Node, ans: Node, asking: Node,
               gap_s: float) -> Node:
    """A two-button dialog asked again and again: Sequential(forever)[pick = ans = CHOICE_NONE, asking = 1, the
    dialog `token` (g_choice: `buttons`, INGAME tokens, shown to `camp`'s side; SelectedButton = pick), ans = pick
    once the dialog has closed, asking = 0, then `gap_s` seconds (game time after the answer: the dialog pauses the
    game)]. Read the answer in `ans`, never in `pick`, which an exit could read while the dialog is still open. Race
    the loop against its exits in a Competition (BackhandBlow Competition#194's forever dialog loop against a
    WaitCondition); an exit that is not the answer should wait for asking = 0, so the race never ends mid-dialog.

    The answer exit, too, can end the race mid-step: the loop writes `ans` and then `asking` = 0, and a
    WaitCondition(ans == ...) may end the race between the two, leaving `asking` at 1 for good. So reset `asking`
    (g_set(asking)) right after the race, in its Sequential, whichever exit won [[dialog-reask-loop]]."""
    return g_seq([g_set(pick, CHOICE_NONE), g_set(ans, CHOICE_NONE), g_set(asking, 1),
                  g_choice(token, buttons[0], buttons[1], camp, pick),
                  g_set(ans, other=pick), g_set(asking), g_wait(gap_s)], runs=FOREVER)


# --------------------------------------------------------------------------- zones and circles

def zone_race(ctx: Ctx, zones: Sequence[str], side: str, other: str, at_least: int, hold_s: float,
              held: Node) -> Node:
    """A count race over the command zones named `zones` (their tags; g_units_in_zones, ZoneType 1:
    ConditionUnitDansZone on the union, Marauders #1343/#1344): `side` has >= `at_least` units there and `other`
    none starts a streak, `side` below `at_least` or `other` >= 1 breaks it. `held` counts the streak's seconds
    (shapes.seconds_while, reset on a break). The node is Competition[the counting loop, WaitCondition(held >=
    hold_s)], so it finishes once the race is held for `hold_s`, then runs what follows it; `held` stays at `hold_s`
    after. Each condition sits in an And, an Or of Ands for the break (stock Or holds no UnitDansZone bare)."""
    tags = [ctx.tag(name) for name in zones]

    def inside(camp: str) -> Callable[[int, int], Node]:
        return lambda value, op: g_units_in_zones(tags, c_team(ctx.camp(camp)), value, op)

    mine, theirs = inside(side), inside(other)
    holds = lambda: g_and(mine(at_least, GE), theirs(0, LE))  # noqa: E731
    broken = lambda: g_or(g_and(mine(at_least - 1, LE)), g_and(theirs(1, GE)))  # noqa: E731
    return g_compete([seconds_while(holds, broken, held, reset=True),
                      g_until(g_cmp(held, int(hold_s), GE))])


def zone_handover(ctx: Ctx, side: str, zones: Sequence[str], hint: str | Node | None) -> Node:
    """`side` takes the command zones named `zones` (SetCommandZoneOwnerAndForceConvergence: the owner holds with
    nobody inside; Marauders #1134 after its count wait, HoldUntilRelieved #107), then the hint `hint`: the game shows
    nothing when a zone changes hands by script. The count race's hand-over: Sequential[owner,
    Simultaneous[LDHint]]. `hint` may instead be the action that shows the hint, for a caller that picks its hint at
    run time, or None for a caller whose hints show elsewhere: Sequential[owner]. Each name is one CommandPoints item
    of ctx.items."""
    for name in zones:
        hits = [it for it in ctx.items if it.name == name]
        check(len(hits) == 1, f"{len(hits)} items are named {name}")
        check(hits[0].addon == "CommandPoints", f"zone_handover: {name} is not a command zone")
    owner = g_zone_owner(ctx.camp(side), [ctx.tag(name) for name in zones])
    if hint is None:
        return g_seq([owner])
    return g_seq([owner, g_simul([g_hint(hint, HINT_S, "shint")]) if isinstance(hint, str) else hint])


def ring_round(ctx: Ctx, group: Node, rings: Sequence[str], contrainte: Callable[[], Node],
               var: Node | None = None) -> list[Node]:
    """One count of the detector circles named `rings`: ClearUnitGroup(`group`), then AddDetectedUnitsToUnitGroup on
    each circle with a fresh `contrainte()` (HoldUntilRelieved #112's shape), then, given `var`, `var` = the group's
    count (SetVariableIntegerFromUnitGroup: Survivors #306), the round's one write, so no reader sees a half-done
    value. A group never holds a unit twice, so overlapping circles count a unit once, and a dead one leaves it. The
    nodes run in one instant chain."""
    return [Node("TGDDescriptorClearUnitGroup", [("Group", group)]),
            *(g_collect(group, g_detect(ctx.tag(ring), contrainte(), compare=False)) for ring in rings),
            *([g_count(var, group)] if var is not None else [])]


# --------------------------------------------------------------------------- the end funnel

def end_funnel(end: Node, endings: Mapping[int, Ending], export: str) -> Node:
    """The one ending node (gates.check_end_funnel), run from load beside the battle: wait for `end` >= 1, then for
    the value found the dialog (g_dialog) and the TriggerEndGame of its `endings` row, the dialog first so the player
    reads why before the screen: IfThenElse(end == value) per row in `endings` order, the last row the last else.
    Each branch is a Sequential ending in its TriggerEndGame (stock places it last in a Sequential; the HUD stays,
    DelayedRetribution #130); a loss names alliance 1, the enemy's (shapes.PACT_ALLIANCE). There is no ending race.
    Only the first TriggerEndGame of a battle counts, so write `end` only through shapes.set_end: the first ending
    stands. Every value is 1 or more (0: no ending yet)."""
    values = list(endings)
    check(bool(values) and min(values) >= 1, f"end_funnel: ending values {values} must be 1 or more")

    def row(value: int) -> Node:
        token, kind, loses = endings[value]
        return g_seq([g_dialog(token), g_end_game(kind, PACT_ALLIANCE if loses else None)])

    pick = row(values[-1])
    for value in reversed(values[:-1]):
        pick = g_if(g_cmp(end, value), row(value), pick)
    return g_seq([g_until(g_cmp(end, 1, GE)), pick], export=export)


# --------------------------------------------------------------------------- difficulty

def after_launch(hint: str, delay: float) -> Node:
    """Sequential[wait for "Launch battle" (Phase BATTLE_PHASE: HoldUntilRelieved #283/#333), WaitDuration `delay`,
    Simultaneous[the hint `hint`]] (stock holds an LDHint in a Simultaneous)."""
    return g_seq([g_until(Node("TGDConditionPhase", [("Phase", i32(BATTLE_PHASE))])), g_wait(delay),
                  g_simul([g_hint(hint, HINT_S, "shint")])])


def difficulty(ctx: Ctx, diff: Node, knobs: Mapping[str, tuple[int, int, int]], hint: str, hint_t: float) -> Node:
    """`diff` = DIFF_NONE, then every `knobs` variable (by name, its (Easy, Medium, Hard) values) takes its Medium
    value; then three IfThenElse on ConditionOnGameDifficulty, consecutive children of a Simultaneous with no else
    (HoldUntilRelieved #154-#156, read right after LoadingDone; Easy's condition is an empty object, #199), set `diff`
    to EASY, MEDIUM or HARD, and Easy's and Hard's overwrite the knobs. Then, if `diff` is still DIFF_NONE (no
    difficulty reached the script: every condition is false), it becomes MEDIUM. Each case's hint, `hint` and the
    level's number (DIFF_NONE's for "not received"), shows `hint_t` after "Launch battle" (after_launch). So `diff`
    and the knobs are final at load either way: a branch that fires sets them before its hint's wait, and with none
    the fallback runs at once."""
    def branch(level: int) -> Node:
        sets = [g_set(ctx.int_var(name), values[level]) for name, values in knobs.items() if level != MEDIUM]
        return g_if(g_difficulty(level),
                    g_simul([g_set(diff, level), *sets, after_launch(f"{hint}{level}", hint_t)]))

    return g_seq([g_set(diff, DIFF_NONE),
                  *(g_set(ctx.int_var(name), values[MEDIUM]) for name, values in knobs.items()),
                  g_simul([branch(EASY), branch(MEDIUM), branch(HARD)]),
                  g_if(g_cmp(diff, DIFF_NONE),
                       g_simul([g_set(diff, MEDIUM), after_launch(f"{hint}{DIFF_NONE}", hint_t)]))])


# --------------------------------------------------------------------------- the script frame

def script_frame(tpl: ndfbin.NdfBin, templates: ops_script.Templates, ctx: Ctx, deploy: ops_script.DeployPhase,
                 beats: Sequence[Beat], *, camp_rows: Sequence[CampRow], folder: str, start_delay_s: float,
                 prod_menu_switch: int, flags: Sequence[str] = ()) -> tuple[list[Node], list[Node]]:
    """A mission's GDScript around its `beats`, on the skeleton of the template `tpl` (its objects named by
    `templates`). Returns (roots, exports):

      RootDescriptor: CampList, EffetMap = Sequential[WaitDuration `start_delay_s`, Main], GameRules (`deploy`'s)
      Main (<folder>/Main): SetDeck per `camp_rows` row (S#117-#120), the HUD hidden (S#121), `deploy.setup`,
        LoadingDone (S#122), the HUD restored with the deployment's (S#296 + DEPLOY_HUD; `prod_menu_switch`), then
        Simultaneous[ the load beats (t None), deploy.refresh,
                      Sequential[ deploy.launched, Simultaneous[ one Sequential[wait t, beat] per timed beat ] ] ]

    With no timed beat, deploy.launched stands alone in Main's Simultaneous. The beats are built in their order, the
    load beats first; then each name of `flags` (the variables several beats read) is declared, an integer at 0, so
    it is exported even where no beat names it. The exports: the root, the camps, the tags, Main, deploy.refresh,
    every other exported node of the tree in walk order (an end funnel), then the variables. The roots: the silent
    voice of every dialog (script.silent_cutscenes), then the root."""
    load = [b.build(ctx) for b in beats if b.t is None]
    timed = [g_seq([g_wait(b.t), b.build(ctx)]) for b in beats if b.t is not None]
    for name in flags:
        ctx.int_var(name)
    battle = g_seq([deploy.launched, g_simul(timed)]) if timed else deploy.launched
    main = g_seq([
        *setdeck_block(ctx.camps, camp_rows),                                                   # S#117-#120
        Node("TGDDescriptorForceDisplayUIElement", template_scalars(tpl, templates.hud_hide)),  # S#121
        *deploy.setup,
        Node("TGDDescriptorLoadingDone"),                                                       # S#122
        Node("TGDDescriptorForceDisplayUIElement",                                              # S#296 + DEPLOY_HUD
             ops_script.hud_restore(tpl, templates, True, prod_menu_switch)),
        g_simul([*load, deploy.refresh, battle]),
    ], export=f"{folder}/Main")
    root = Node("TGDDescriptorLaunchEffetStandard", [                                           # S#108
        ("CampList", list(ctx.camps.values())),
        ("EffetMap", g_seq([g_wait(start_delay_s), main])),                                     # S#113
        ("GameRules", deploy.game_rules),
    ], export=f"{GD}/RootDescriptor")
    base = [root, *ctx.camps.values(), *ctx.tags.values(), main, deploy.refresh]
    listed = {id(nd) for nd in [*base, *ctx.variables.values()]}
    extra = [nd for nd in walk([root]) if nd.export and id(nd) not in listed]
    return [ops_script.silent_cutscenes(dialog_tokens([root])), root], [*base, *extra, *ctx.variables.values()]
