"""Tests for Twin Strike's mission (examples/twin-strike/twinstrike/op.py; docs/design.md 4, 4.1, 4.2, 5 and 7).

`Knobs` and `Places` need no stock data: the difficulty knobs, battalion 1's waves and lanes, the dialogs' schedule, the
endings, the fire boxes, battalion 2's layout and the strike zone. `Shapes` builds the script from Survivors' and pins
each phase's script shape for one representative case. The other classes drive the beats through
twin_strike_support.Model, a step model of the script runtime, with a World of circle counts, captures, kills and
dialog answers: the fall and phase 1's deadline, the preparation fire, the unlock, the losses, battalion 1's waves, B1
and its deadline, the fire missions, the division fire plan, battalion 2 and the release, the strike's order and
timing, the withheld road, the end clock and the grade, the end funnel and the difficulty branches."""
from __future__ import annotations

import math
import unittest

from twin_strike_support import JOUEUR, NATO, SCRIPT_DATA, Model, World, beats_root
from modkit.ops import shapes
from modkit.ops.files import read_file
from modkit.ops.graph import decode, walk
from modkit.ops.profile import SURVIVORS
from modkit.ops.shapes import GRU_WORLD
from modkit.ops.testing import last, objective_named, of, parent_of, prop, subs, token
from twinstrike import forces, profile
from twinstrike import map as ts_map
from twinstrike import op
from twinstrike.strings import BUTTONS, ENGLISH

GD = "$/GDScript"
STRINGS_LOC = ENGLISH["Scripting/Localization"]
VILLAGE_CZ = op.VILLAGE_ZONE


def item(name: str):
    (it,) = [x for x in op.ITEMS if x.name == name]
    return it


def px(it) -> tuple[float, float]:
    return ts_map.MAP.map.world_to_px((it.x, it.y))


def run(world: World, until: int, *checks: str, values: dict | None = None) -> Model:
    """The model over the beats named `checks` (all of op.BEATS when none), the launch at second 0."""
    beats = [b for b in op.BEATS if not checks or b.check in checks]
    return Model(world, values).play(beats_root(beats, op.Ctx()), until)


def village(nato: list, cmd: list | None = None, mine: list | None = None, zone: list | None = None,
            **extra) -> dict:
    """World.rings with the village's circle (NATO's Steps, the command units' and the player's) and its command zone
    (the player's units in it: `zone`, else as in the circle)."""
    mine = mine or [(0, 5)]
    return {op.VILLAGE_RING: {NATO: nato, "cmd": cmd or [], JOUEUR: mine}, VILLAGE_CZ: {JOUEUR: zone or mine},
            **extra}


# World.groups with a unit left in every NATO ground group, so phase 5 runs its clock (op.nato_spent ends it at once
# once all are empty), and with all of them empty from second `t` on.
NATO_LEFT = {name: [(0, 1)] for name in op.NATO_GROUND}


def nato_gone(t: int) -> dict:
    return {name: [(0, 1), (t, 0)] for name in op.NATO_GROUND}


# The fall at second FALL_T: the garrison down to 2 (Hard's threshold, so it falls at every difficulty), a command
# unit inside from FALL_T.
FALL_T = 310
FALLS = village([(0, 14), (300, 2)], [(FALL_T, 1)])
PH3_T = FALL_T + int(op.PHASE2_S)


class Knobs(unittest.TestCase):
    def test_difficulty_knobs(self):
        """(Easy, Medium, Hard): the village falls with 5, 4 or 2 of the garrison's 14 left (35/25/15 %); 2, 3 or 4
        company teams; a 2, 3 or 4 min cooldown; B1's tanks and the kills that break battalion 1 (30 % left); the third
        fighter sweep on Hard only."""
        self.assertEqual(op.KNOBS, {"ts_fall_n": (5, 4, 2), "ts_teams": (2, 3, 4), "ts_cool_s": (120, 180, 240),
                                    "ts_b1_tanks": (21, 31, 41), "ts_b1_need": (15, 22, 29), "ts_sweep3": (0, 0, 1)})
        self.assertEqual(op.KNOBS["ts_fall_n"][op.MEDIUM], forces.threshold("fall"))
        self.assertEqual(op.KNOBS["ts_b1_tanks"][op.MEDIUM] - op.KNOBS["ts_b1_need"][op.MEDIUM],
                         forces.threshold("bn1"))
        self.assertEqual(op.GARRISON_N, 14)

    def test_the_waves_split_battalion_one(self):
        """Medium sends the table's battalion 1 whole (design 6.3: 31 tanks, its recon screen and air defence), in five
        waves; Easy leaves out team C, Hard adds team D, a second company like A."""
        sent, table = op.bn1_tallies()
        self.assertEqual(sent, table)
        self.assertEqual(op.bn1_tanks(3), 31)
        by_team = {t.team: t.wave for t in op.BN1_WAVES if t.team}
        self.assertEqual(by_team[4].rows, by_team[1].rows)
        self.assertEqual([t.team for t in op.BN1_WAVES], [0, 0, 1, 2, 3, 4])
        for t in op.BN1_WAVES:
            with self.subTest(wave=t.wave.key):
                units = {u: n for u, n, _ in t.wave.rows}
                for unit, n, carrier in t.wave.rows:   # riflemen ride in their own wave's Bradleys
                    if carrier:
                        self.assertGreaterEqual(units[carrier], n)
                if t.team:                             # a company team: tanks, Bradleys, riflemen and air defence
                    self.assertEqual(sum(n for u, n, _ in t.wave.rows if u in forces.BN1_TANKS) // 10, 1)
                    self.assertTrue({"MANPAD_Stinger_C_US"} <= set(units))

    def test_waves_by_lane(self):
        """On each lane the recon screen first, then a company team every 2 min; the centre lane 60 s behind the west
        one, so no two waves are created together."""
        for lane, lead in (("W", 0.0), ("C", op.LANE_STAGGER_S)):
            waves = [t for t in op.BN1_WAVES if t.wave.lane == lane]
            self.assertEqual([t.wave.offset for t in waves], [lead + k * op.WAVE_GAP_S for k in range(3)])
            self.assertEqual(waves[0].team, 0)
            self.assertTrue(all(t.team for t in waves[1:]))
        offsets = [t.wave.offset for t in op.BN1_WAVES]
        self.assertEqual(len(offsets), len(set(offsets)))
        self.assertEqual((op.WAVE_GAP_S, op.LANE_STAGGER_S), (120.0, 60.0))

    def test_lanes(self):
        """Each lane follows twinstrike.map.PATHS from its entry, every leg by FastMoveAndAttack and raced against
        LEG_S but the last, MoveAndAttack into the village raced against FINAL_LEG_S; probe 2's pace (240 s for 362 px)
        drives each leg in its timeout."""
        tags = {name: point for name, point in op.TAGS.items()}
        for lane, path in (("W", "LANE_W"), ("C", "LANE_C")):
            ln = op.LANES[lane]
            self.assertEqual([tags[ln.entry], *(tags[leg.to] for leg in ln.legs)], list(ts_map.PATHS[path]))
            *legs, final = ln.legs
            self.assertEqual((final.order, final.timeout), (shapes.MOVE_AND_ATTACK, op.FINAL_LEG_S))
            self.assertTrue(all(leg.order == shapes.FAST_MOVE_AND_ATTACK and leg.timeout == op.LEG_S for leg in legs))
            stops = [tags[ln.entry], *(tags[leg.to] for leg in ln.legs)]
            for (a, b), leg in zip(zip(stops, stops[1:]), ln.legs):
                self.assertLessEqual(math.dist(ts_map.POINTS[a], ts_map.POINTS[b]) * 240.0 / 362, leg.timeout)

    def test_dialogs_never_open_together(self):
        """The fire missions' asks (FIRE_T0, then every FIRE_LEAD_S + FIRE_HOLD_S + cooldown) and the fire plan's
        (PLAN_T0, then every PLAN_GAP_S) fall 15 s or more apart over the counter-attack's 15 minutes, at every
        difficulty."""
        span = op.BN1_DEADLINE_S + 600
        plan = [op.PLAN_T0 + k * op.PLAN_GAP_S for k in range(int(span // op.PLAN_GAP_S) + 1)]
        for cool in op.COOLDOWN_S:
            period = op.FIRE_LEAD_S + op.FIRE_HOLD_S + cool
            missions = [op.FIRE_T0 + k * period for k in range(int(span // cool) + 1)]
            gap = min(abs(a - b) for a in missions for b in plan)
            with self.subTest(cooldown=cool):
                self.assertGreaterEqual(gap, 15.0)

    def test_endings(self):
        """END's values: the six wins first (Total, Major, Minor, each released then withheld), then the three
        losses; a Minor victory shows Major's screen, a loss names alliance 1."""
        self.assertEqual(list(op.ENDINGS), list(range(1, 10)))
        self.assertEqual([op.ENDINGS[k][0] for k in op.ENDINGS],
                         ["ts_dtotr", "ts_dtotw", "ts_dmajr", "ts_dmajw", "ts_dminr", "ts_dminw", "ts_dfail",
                          "ts_dlost", "ts_dempty"])
        self.assertEqual([op.ENDINGS[k][1] for k in range(1, op.WON + 1)],
                         [shapes.TOTAL_VICTORY] * 2 + [shapes.MAJOR_VICTORY] * 4)
        self.assertEqual([op.ENDINGS[k][2] for k in op.ENDINGS], [False] * op.WON + [True] * 3)


class Places(unittest.TestCase):
    def test_the_fire_boxes(self):
        """A 20 px circle on each box's road point, inside the cut, short of the village's circle."""
        for lane, ring in op.BOX_RINGS.items():
            it = item(ring)
            with self.subTest(box=lane):
                self.assertEqual(px(it), ts_map.POINTS[f"BOX_{lane}"])
                self.assertAlmostEqual(it.radius_gru * GRU_WORLD / ts_map.MAP.map.world_per_px, op.BOX_RING_PX)
                gap = math.dist(px(it), ts_map.POINTS["VILLAGE"]) - op.BOX_RING_PX - op.VILLAGE_RING_PX
                self.assertGreater(gap, 0)

    def test_command_units_and_infantry(self):
        """The command units are the player's (Soviet) *_CMD_* types; NATO's infantry are NATO rows' types, every
        carried squad among them."""
        self.assertTrue(all("_CMD_" in u and u.endswith("_SOV") for u in forces.COMMAND_UNITS))
        nato = {r.descriptor for r in forces.ROWS if r.camp == "NATO"}
        self.assertLessEqual(set(forces.NATO_INFANTRY), nato)
        self.assertLessEqual({r.descriptor for r in forces.ROWS if r.camp == "NATO" and r.transport},
                             set(forces.NATO_INFANTRY))

    def test_the_strike_zone(self):
        """R is 800 m (215 world units a metre, the probes' conversion): a 67.2 px (2,337 GRU) circle round ASSEMBLY.
        It holds BOX C but neither BOX W, TURN C nor the village's circle."""
        ring = item(op.STRIKE_RING)
        self.assertEqual(px(ring), ts_map.POINTS["ASSEMBLY"])
        self.assertAlmostEqual(op.STRIKE_R_PX * ts_map.MAP.map.world_per_px / op.WORLD_PER_METRE, 800.0)
        self.assertAlmostEqual(ring.radius_gru, 800.0 * 215.0 / GRU_WORLD)
        self.assertAlmostEqual(round(ring.radius_gru), 2337)
        a = ts_map.POINTS["ASSEMBLY"]
        self.assertLess(math.dist(a, ts_map.POINTS["BOX_C"]), op.STRIKE_R_PX)
        for place in ("BOX_W", "TURN_C"):
            self.assertGreater(math.dist(a, ts_map.POINTS[place]), op.STRIKE_R_PX)
        self.assertGreater(math.dist(a, ts_map.POINTS["VILLAGE"]), op.STRIKE_R_PX + op.VILLAGE_RING_PX)

    def test_battalion_two(self):
        """Design 6.3's battalion 2 (52, its tanks 29) in two halves, pre-placed hidden in the NATO camp (Camp_3),
        every unit inside 0.8 R of ASSEMBLY and inside the cut, facing the village; B2's label at its north edge, the
        dressing's spots inside the zone."""
        spawns = [it for it in op.ITEMS if it.group in ("bn2_w", "bn2_c")]
        self.assertEqual(len(spawns), 52)
        self.assertEqual(sum(it.unit in forces.BN2_TANKS for it in spawns), 29)
        self.assertEqual(op.BN2_BROKEN_N, 9)
        sent, table = op.tally(r for rows in op.BN2_HALVES.values() for r in rows), op.tally(
            (r.descriptor, r.count, r.transport) for r in forces.force_rows("bn2"))
        self.assertEqual(sent, table)
        a = ts_map.POINTS["ASSEMBLY"]
        x0, y0, x1, y1 = ts_map.CUT_PX
        for it in spawns:
            with self.subTest(unit=it.name):
                self.assertEqual((it.ranking, it.camp, it.disable_auto_spawn, it.rotation),
                                 ("Camp_3", 3, True, op.BN2_FACING))
                self.assertLessEqual(math.dist(px(it), a), op.BN2_FIT * op.STRIKE_R_PX)
                x, y = px(it)
                self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1)
        north = min(px(it)[1] for it in spawns)
        self.assertLessEqual(px(item(op.BN2_PIN))[1], north)
        self.assertLess(math.dist(px(item(op.BN2_PIN)), a), op.STRIKE_R_PX)
        for name in op.DRESSING:
            self.assertLess(math.dist(px(item(name)), a), op.BN2_FIT * op.STRIKE_R_PX)

    def test_battalion_two_lanes(self):
        """From ASSEMBLY the west half drives to BOX W and the village; the centre half battalion 1's centre lane.
        Each leg's timeout covers probe 2's pace."""
        tags = op.TAGS
        for half, start in (("W", "ASSEMBLY"), ("C", "ASSEMBLY")):
            *legs, final = op.BN2_LANES[half]
            self.assertEqual((final.to, final.order, final.timeout),
                             ("TS_Village", shapes.MOVE_AND_ATTACK, op.FINAL_LEG_S))
            stops = [start, *(tags[leg.to] for leg in legs)]
            for (a, b), leg in zip(zip(stops, stops[1:]), legs):
                self.assertLessEqual(math.dist(ts_map.POINTS[a], ts_map.POINTS[b]) * 240.0 / 362, leg.timeout)


@SCRIPT_DATA
class Shapes(unittest.TestCase):
    """The script's shape, from Survivors' template."""

    @classmethod
    def setUpClass(cls):
        tpl, _, _ = decode(read_file(SURVIVORS.gdscript()))
        cls.roots, cls.exports = op.content().script(tpl)
        cls.nodes = list(walk(cls.roots))
        (cls.main,) = [nd for nd in cls.nodes if nd.export == f"{GD}/TS/Main"]

    def var(self, name: str):
        (v,) = [n for n in self.exports if n.export == f"{GD}/TS/Variables/{name}"]
        return v

    def test_layout(self):
        """Main's Simultaneous: the four load beats (the frame's two first), the refresh loop, then the launch wait
        and the timed beats, each from H+0:00 (each later phase waits for its flag). The flags and the end funnel are
        exported."""
        self.assertEqual([(b.t, b.check) for b in op.BEATS][:4],
                         [(None, "deck"), (None, "groups"), (None, "difficulty"), (None, "funnel")])
        self.assertTrue(all(b.t == 0.0 for b in op.BEATS[4:]))
        *load, refresh, battle = subs(subs(self.main)[-1])
        self.assertEqual(len(load), 4)
        self.assertEqual(refresh.export, profile.REFRESH_EXPORT)
        self.assertEqual(load[3].export, profile.END_FUNNEL)
        launched, timed = subs(battle)
        self.assertEqual(token(prop(of(list(walk([launched])), "LDHint")[0], "Info")), "ts_hdep")
        self.assertEqual(len(subs(timed)), len(op.BEATS) - 4)
        for flag in op.FLAGS:
            self.var(flag)

    def test_every_fire_creates_its_battery_in_the_allied_camp(self):
        """No SetAmmo anywhere. Every fire's battery is created at GUN_SPAWN in the allied camp, into its own group,
        then: AddIgnoredUnitByScript on it, FIRE_LEAD_S, ShootOnPosition non-blocking, FIRE_HOLD_S, KillAllUnit
        Vanished on it; the guns are created nowhere else, and nothing else orders them."""
        self.assertEqual(of(self.nodes, "SetAmmo"), [])
        creates = [n for n in of(self.nodes, "CreateUnitOnPosition") if last(prop(n, "Group")) in op.BATTERIES]
        self.assertEqual({(last(prop(n, "Position")), last(prop(n, "Camp"))) for n in creates},
                         {(op.GUN_SPAWN, "Allie")})
        fires = 0
        for seq in of(self.nodes, "Sequential"):
            kids = subs(seq)
            for k, kid in enumerate(kids):
                if kid.cls != "TGDDescriptorAddIgnoredUnitByScript":
                    continue
                fires += 1
                group = last(prop(kid, "UnitGroup"))
                made = [last(prop(n, "Group")) for n in kids[:k] if n.cls == "TGDDescriptorCreateUnitOnPosition"]
                self.assertEqual(set(made), {group})
                lead, shot, hold, gone = kids[k + 1:k + 5]
                self.assertEqual((prop(lead, "Duree").v, prop(hold, "Duree").v), (op.FIRE_LEAD_S, op.FIRE_HOLD_S))
                self.assertEqual((last(prop(shot, "Group")), prop(shot, "OrderType").v, prop(shot, "Blocking")),
                                 (group, shapes.SHOOT_ON_POSITION, None))
                self.assertEqual((gone.cls, [last(g) for g in prop(gone, "GroupList")], prop(gone, "DeathCause")),
                                 ("TGDDescriptorKillAllUnit", [group], None))
        self.assertEqual(fires, 8)          # prep, 4 fire missions, the fire plan's 2, the strike's round
        ordered = {last(prop(n, "Group")) for n in of(self.nodes, "GiveOrderStandard")}
        self.assertEqual(ordered & set(op.BATTERIES), set(op.BATTERIES))

    def test_the_fall(self):
        """Phase 1's fall waits for And[ts_fall_n >= ts_left (MoreOrEqual against a variable), a command unit of
        forces.COMMAND_UNITS in the village's circle (>= 1)]; then FALLEN = 1 and the zone forced to the player with
        the hint ts_hfall."""
        (wait,) = [w for w in of(self.nodes, "WaitCondition") if prop(w, "Condition").cls == "TGDConditionAnd"
                   and any(k.cls == "TGDConditionDetectUnitDansDetecteur" for k in prop(prop(w, "Condition"),
                                                                                       "SousConditions"))]
        left, cmd = prop(prop(wait, "Condition"), "SousConditions")
        self.assertEqual((last(prop(left, "Variable")), last(prop(prop(left, "Operator"), "Variable")),
                          prop(prop(left, "Operator"), "OperatorType").v), ("ts_fall_n", "ts_left", shapes.GE))
        self.assertEqual(last(prop(cmd, "Detecteur")), op.VILLAGE_RING)
        types = [prop(c, "TypeUnit").path.rsplit("_Unit_", 1)[1] for c in prop(prop(cmd, "Contrainte"),
                                                                                 "ContrainteList")]
        self.assertEqual(types, list(forces.COMMAND_UNITS))
        owners = [n for n in of(self.nodes, "SetCommandZoneOwner") if last(prop(n, "Camp")) == JOUEUR]
        self.assertEqual([[last(z) for z in prop(n, "Positions")] for n in owners], [[VILLAGE_CZ]])

    def test_objectives(self):
        """P1 and P2 pinned on the village (their counters the garrison left and NATO's hold), the boxes' labels on
        their circles, B1 a bonus in the panel only."""
        p1, p2, b1 = (objective_named(self.nodes, t) for t in ("ts_p1", "ts_p2", "ts_b1"))
        self.assertEqual([last(prop(o, "Position")) for o in (p1, p2)], ["TS_Village", "TS_Village"])
        self.assertEqual([last(v) for v in prop(p1, "ListVariables")], ["ts_left"])
        self.assertEqual([last(v) for v in prop(p2, "ListVariables")], ["ts_nato_s", "ts_empty_s"])
        self.assertEqual((prop(b1, "Position"), prop(b1, "LabelComponent").text), (None, "Bonus"))
        self.assertEqual([last(v) for v in prop(b1, "ListVariables")], ["ts_b1_k", "ts_b1_tanks"])
        for lane, ring in op.BOX_RINGS.items():
            self.assertEqual(last(prop(objective_named(self.nodes, f"ts_ob{lane.lower()}"), "Position")), ring)

    def test_the_dialogs_buttons(self):
        """Each choice dialog's buttons are its strings.BUTTONS pair, shown to the player."""
        for choice in of(self.nodes, "DialogListWithMultipleChoice"):
            (dialog,) = prop(choice, "DialogList")
            (text,) = prop(dialog, "TextComponentsToFill")
            name = token(prop(text, "LocalizedText"))
            with self.subTest(dialog=name):
                self.assertEqual((token(prop(dialog, "TokenBoutonChoix0")), token(prop(dialog, "TokenBoutonChoix1"))),
                                 BUTTONS[name])
                self.assertEqual(last(prop(dialog, "VisibleByCamp")), JOUEUR)

    def test_fires_aim_at_name_tags(self):
        """Every ShootOnPosition aims at a Name tag (Survivors #1231/#1232's form), never a detector circle: the
        village, the two boxes and the assembly area; the batteries are HEAVY, ROCKETS, GUNS (both, the plan's) and
        the strike's one 2S7M."""
        targets = {last(prop(n, "Position")) for n in of(self.nodes, "GiveOrderStandard")
                   if prop(n, "OrderType").v == shapes.SHOOT_ON_POSITION}
        self.assertEqual(targets, {"TS_Village", *op.BOX_TAGS.values(), "TS_Assembly"})
        self.assertEqual(op.BATTERIES, {op.HEAVY: (("2S7M_Malka_SOV", 6),), op.ROCKETS: (("BM27_Uragan_SOV", 6),),
                                        op.GUNS: (("2S7M_Malka_SOV", 6), ("BM27_Uragan_SOV", 6)),
                                        op.STRIKER: (("2S7M_Malka_SOV", 1),)})

    def test_every_reask_race_resets_its_flag(self):
        """Every Competition holding a re-ask loop (a forever Sequential asking a choice dialog) is followed in its
        Sequential by its asking flag's reset (the variable the loop sets to 1), whichever exit won: the answer can end
        the race between the loop's two writes [[dialog-reask-loop]]."""
        races = 0
        for seq in of(self.nodes, "Sequential"):
            kids = subs(seq)
            for k, kid in enumerate(kids):
                loops = [x for x in subs(kid) or [] if kid.cls == "TGDDescriptorCompetition"
                         and x.cls.endswith("Sequential")
                         and prop(x, "NbExecutions").v == shapes.FOREVER
                         and of(list(walk([x])), "DialogListWithMultipleChoice")]
                if not loops:
                    continue
                races += 1
                (loop,) = loops
                flag = [last(prop(n, "Variable1")) for n in subs(loop) if n.cls.endswith("ModifieVariableInteger")
                        and prop(n, "Value") is not None and prop(n, "Value").v == 1]
                after = kids[k + 1]
                self.assertEqual((after.cls, last(prop(after, "Variable1")), prop(after, "Value")),
                                 ("TGDDescriptorModifieVariableInteger", flag[0], None))
        self.assertEqual(races, 2)            # the preparation fire and the division fire plan

    def test_the_release_wait_is_bounded(self):
        """The release dialog waits for quiet (BUSY and both dialog flags 0) or RELEASE_MAX_WAIT_S, whichever is
        first, then asks; the bound leaves more than half of the 5:00 countdown and covers one whole fire."""
        (choice,) = [n for n in of(self.nodes, "DialogListWithMultipleChoice")
                     if token(prop(of(list(walk([n])), "CutsceneTextComponent")[0], "LocalizedText")) == "ts_drel"]
        (seq,) = [s for s in of(self.nodes, "Sequential") if choice in subs(s)]
        kids = subs(seq)
        race = kids[1]
        self.assertEqual(race.cls, "TGDDescriptorCompetition")
        until, bound = subs(race)
        self.assertEqual((until.cls, prop(bound, "Duree").v), ("TGDDescriptorWaitCondition", op.RELEASE_MAX_WAIT_S))
        self.assertEqual({last(prop(c, "Variable")) for c in prop(prop(until, "Condition"), "SousConditions")},
                         {op.BUSY, "ts_fire_open", "ts_plan_open"})
        self.assertGreaterEqual(op.RELEASE_MAX_WAIT_S, op.FIRE_LEAD_S + op.FIRE_HOLD_S)
        self.assertLess(op.RELEASE_ASK_S + op.RELEASE_MAX_WAIT_S, op.COUNTDOWN_S / 2)

    def test_waves_end_with_an_attack(self):
        """Every NATO wave and battalion 2's halves: HOLD POSITION when idle and Aggressive when fired on, then their
        route, every leg raced against its timeout, the last MoveAndAttack into the village; then an Attack on
        Groupe_Joueur (Survivors #1099: blocking, AttackEnPrioriteUniteNotUbserstress), last in the route's
        Sequential [[wave-ends-with-attack]]."""
        attacks = [n for n in self.nodes if n.cls == "TGDDescriptorAttack"]
        self.assertEqual(len(attacks), len(op.BN1_WAVES) + len(op.BN2_HALVES))
        for attack in attacks:
            group = last(prop(attack, "Group"))
            with self.subTest(group=group):
                self.assertEqual([(k, getattr(v, "v", None)) for k, v in attack.props if k not in ("Group", "Targets")],
                                 [("Blocking", True), ("AttackEnPrioriteUniteNotUbserstress", True)])
                self.assertEqual(last(prop(attack, "Targets")), op.GROUPE_JOUEUR)
                (route,) = [s for s in of(self.nodes, "Sequential") if attack in subs(s)]
                *legs, last_node = subs(route)
                self.assertIs(last_node, attack)
                self.assertTrue(legs and all(leg.cls == "TGDDescriptorCompetition" for leg in legs))
                (village,) = [n for n in walk([legs[-1]]) if n.cls == "TGDDescriptorGiveOrderStandard"]
                self.assertEqual((last(prop(village, "Position")), prop(village, "OrderType").v),
                                 ("TS_Village", shapes.MOVE_AND_ATTACK))
                (holder,) = [s for s in of(self.nodes, "Sequential") if route in subs(s)]
                kids = subs(holder)
                idle, shot = kids[kids.index(route) - 2:kids.index(route)]
                self.assertEqual((idle.cls, last(prop(idle, "Group")), prop(idle, "IdleBehavior").v),
                                 ("TGDDescriptorSetIdleROEBehavior", group, shapes.IDLE_HOLD_POSITION))
                self.assertEqual((shot.cls, last(prop(shot, "Group")), prop(shot, "ShotReactionBehavior").v),
                                 ("TGDDescriptorSetShotReactionROEBehavior", group, shapes.AGGRESSIVE))

    def test_the_economy(self):
        """Phase 1 deploys on 3,000 points with no income (SetIncomeToTeam with no amount); the fall gives 8,000 at
        once, in a Simultaneous, then an income of 500, double the first fix's 250 [[scripted-economy]] (design 4.3,
        6.5)."""
        self.assertEqual((op.DEPLOY_POINTS, op.START_INCOME, op.FALL_GRANT, op.FALL_INCOME), (3000, 0, 8000, 500))
        (grant,) = of(self.nodes, "GiveRessourceToTeam")
        self.assertEqual([(k, getattr(v, "v", None)) for k, v in grant.props if k != "Camp"],
                         [("Quantite", 8000), ("ResourceType", 1)])
        (simul,) = [s for s in of(self.nodes, "Simultaneous") if subs(s) == [grant]]
        (seq,) = [s for s in of(self.nodes, "Sequential") if simul in subs(s)]
        kids = subs(seq)
        income = kids[kids.index(simul) + 1]
        self.assertEqual((income.cls, prop(income, "Quantite").v), ("TGDDescriptorSetIncomeToTeam", 500))
        self.assertIn(f"{op.FALL_GRANT:,} points", STRINGS_LOC["ts_hfall"])

    def test_the_sweeps(self):
        """Each sweep is Survivors' end strike (#1483-#1489, #1496, #1647/#1648): SpawnUnits on its hidden fighters,
        their group, HOLD POSITION; a second; AirplaneMoveAndEngage onto its circle, cancelable; then, once every one
        of them is out of fuel or ammunition, AirplaneEvacuate, blocking."""
        for s in op.SWEEPS:
            group = f"ts_air_{s.key}"
            with self.subTest(sweep=s.key):
                (spawn,) = [n for n in of(self.nodes, "SpawnUnits")
                            if [last(t) for t in prop(n, "Units")] == [it.name for it in op.ITEMS
                                                                        if it.group == f"air_{s.key}"]]
                (first,) = [x for x in of(self.nodes, "Sequential") if spawn in subs(x)]
                (sweep,) = [x for x in of(self.nodes, "Sequential") if first in subs(x)]
                _, union, idle = subs(first)
                self.assertEqual((last(prop(union, "GroupDestination")), prop(idle, "IdleBehavior").v),
                                 (group, shapes.IDLE_HOLD_POSITION))
                _, wait, engage, home = subs(sweep)
                self.assertEqual(prop(wait, "Duree").v, 1.0)
                (move,) = subs(engage)
                self.assertEqual([(k, getattr(v, "v", None)) for k, v in move.props if k not in ("Group", "Position")],
                                 [("OrderCancelable", True), ("OrderType", shapes.AIRPLANE_MOVE_AND_ENGAGE)])
                self.assertEqual(last(prop(move, "Position")), s.target)
                ((until, leave),) = [subs(x) for x in subs(home)]
                spent = prop(until, "Condition")
                self.assertEqual((spent.cls, last(prop(spent, "Variable")), prop(prop(spent, "Operator"), "Value").v),
                                 ("TGDConditionUnitGroupWithFilter", group, s.count))
                self.assertEqual([(k, getattr(v, "v", None)) for k, v in leave.props if k != "Group"],
                                 [("Blocking", True), ("OrderType", shapes.AIRPLANE_EVACUATE)])

    def test_the_strike_launches_and_kills(self):
        """The script launches the strike's look and the dressing only, all self-contained (the script-effects gate
        builds them); the strike kills with STRIKE_CAUSE the NATO units its zone's detector gathers, the break-off's
        removal is Vanished."""
        fx = sorted({prop(n, "DatabaseName").text for n in of(self.nodes, "LaunchFXFireAndForgetOnPosition")})
        self.assertEqual(fx, sorted({op.STRIKE_FX, *op.DRESSING_FX}))
        self.assertEqual(op.STRIKE_FX, "$/GFX/GameFx/fx_HE_Mega_Bomb_ForScript")
        kills = of(self.nodes, "KillAllUnit")
        self.assertEqual(sorted((prop(k, "DeathCause").v if prop(k, "DeathCause") else None) for k in kills
                                if prop(k, "DeathCause")), [shapes.PENETRATION])
        (collect,) = [n for n in of(self.nodes, "AddDetectedUnitsToUnitGroup")
                      if last(prop(prop(n, "Detector"), "Detecteur")) == op.STRIKE_RING]
        contrainte = prop(prop(collect, "Detector"), "Contrainte")
        self.assertEqual((contrainte.cls, last(prop(contrainte, "Camp"))), ("TGDContrainteOnUnitTeam", NATO))
        self.assertIn(shapes.DEATH_CAUSE_SHAPE, op.content().extra_shapes)

    def test_b1_counts_survivors(self):
        """B1's count is battalion 1's tanks created less those alive [[kill-counts-by-type]]: every tank row goes into
        its wave's tank group, which joins ts_bn1_w_tanks; each wave adds its tanks to ts_b1_made with its creates; the
        poll counts the group alive and writes ts_b1_k = made - alive once. No GetNbKillsCamp."""
        self.assertEqual(of(self.nodes, "GetNbKillsCamp"), [])
        tank_rows = [n for n in of(self.nodes, "CreateUnitOnPosition")
                     if prop(n, "TypeUnit").path.rsplit("_Unit_", 1)[1] in forces.BN1_TANKS]
        self.assertTrue(tank_rows)
        self.assertTrue(all(last(prop(n, "Group")).endswith("_tanks") for n in tank_rows))
        joins = {last(prop(n, "GroupDestination")) for n in of(self.nodes, "AddUnitGroupListToUnitGroup")
                 if any(last(g).endswith("_tanks") for g in prop(n, "ListGroupSource"))}
        self.assertIn(op.BN1_TANKS_G, joins)
        (count,) = [n for n in of(self.nodes, "SetVariableIntegerFromUnitGroup")
                    if last(prop(n, "Group")) == op.BN1_TANKS_G]
        self.assertEqual(last(prop(count, "Variable")), "ts_b1_alive")
        adds = [prop(n, "Value").v for n in of(self.nodes, "ModifieVariableInteger")
                if last(prop(n, "Variable1")) == "ts_b1_made"]
        self.assertEqual(adds, [10, 11, 10, 10])                     # teams A to D


class Phase1(unittest.TestCase):
    """The assault: the fall, its deadline, P1 and the preparation fire (design 5.1, 5.4, 4.2)."""

    def test_the_fall(self):
        """With 4 of the garrison left (Medium's threshold) and a command unit inside at 310 s: FALLEN, the zone the
        player's and the hint ts_hfall at 310 s; P1 done with "4 left"."""
        rings = village([(0, 14), (300, 4)], [(FALL_T, 1)])
        m = run(World(rings=rings), FALL_T + 5, "difficulty", "phase1")
        self.assertEqual(m.vars[op.FALLEN], 1)
        self.assertEqual(m.when("owner", JOUEUR, [VILLAGE_CZ]), [FALL_T])
        self.assertEqual(m.when("hint", "ts_hfall"), [FALL_T])
        self.assertEqual(m.entries("done"), [(FALL_T, "ts_p1", [4])])

    def test_the_locks_lift_at_the_fall(self):
        """The deck's three locks hold until the fall and end with it: their races finish, and with them the deck
        beat, so the run ends at the fall (phase 1's beat ends there too)."""
        m = run(World(rings=FALLS), FALL_T + 50, "deck", "difficulty", "phase1")
        self.assertEqual([e[2:] for e in m.log if e[1] == "lock"], [(u,) for u in forces.START_LOCKS])
        self.assertEqual(m.vars[op.FALLEN], 1)
        self.assertEqual(m.t, FALL_T + 1)       # the tick after the fall: every beat has ended

    def test_no_fall_without_a_command_unit(self):
        """The garrison gone but no command unit inside: no fall."""
        m = run(World(rings=village([(0, 0)])), 600, "difficulty", "phase1")
        self.assertEqual(m.vars.get(op.FALLEN, 0), 0)
        self.assertEqual(m.when("owner"), [])

    def test_the_deadline(self):
        """Not fallen 20 min after the launch: END_FAIL, the funnel's dialog ts_dfail and a loss (alliance 1)."""
        m = run(World(rings=village([(0, 14)], [(0, 1)])), 1210, "difficulty", "funnel", "phase1")
        self.assertEqual(m.vars[op.END], op.END_FAIL)
        (t_dialog,) = m.when("dialog", "ts_dfail")
        self.assertEqual(t_dialog, int(op.P1_DEADLINE_S) + 1)
        self.assertEqual(m.entries("end"), [(t_dialog, shapes.TOTAL_VICTORY, shapes.PACT_ALLIANCE)])

    def test_the_fall_beats_the_deadline(self):
        m = run(World(rings=FALLS), 1300, "difficulty", "funnel", "phase1")
        self.assertEqual(m.vars.get(op.END, 0), 0)
        self.assertEqual(m.when("end"), [])

    def test_the_preparation_fire(self):
        """The warning at 30 s, the dialog at 40 s and again every 2 min after HOLD FIRE; on FIRE AT WILL the 2S7M
        battery is created at GUN_SPAWN in the allied camp, kept off its AI, fires FIRE_LEAD_S later on the village's
        Name tag, and is removed FIRE_HOLD_S after that; the dialog's flag is 0 again."""
        m = run(World(rings=village([(0, 14)]), answers={"ts_dprep": [1, 1, 0]}), 600, "phase1")
        self.assertEqual(m.when("hint", "ts_hprep"), [30])
        self.assertEqual(m.when("ask", "ts_dprep"), [40, 160, 280])
        lead, hold = int(op.FIRE_LEAD_S), int(op.FIRE_HOLD_S)
        self.assertEqual(m.entries("create"), [(280, op.HEAVY, 6, "2S7M_Malka_SOV", op.GUN_SPAWN)])
        self.assertEqual(m.entries("ignored"), [(280, op.HEAVY)])
        self.assertEqual(m.entries("order"), [(280 + lead, op.HEAVY, shapes.SHOOT_ON_POSITION, "TS_Village", False)])
        self.assertEqual(m.entries("kill"), [(280 + lead + hold, [op.HEAVY], None)])
        self.assertEqual(m.entries("ammo"), [])
        self.assertEqual(m.vars["ts_prep_open"], 0)

    def test_the_preparation_fire_ends_at_the_fall(self):
        """Held at 40 s and 160 s, then the village falls: no more asks, no fire."""
        rings = village([(0, 14), (190, 4)], [(200, 1)])
        m = run(World(rings=rings), 800, "difficulty", "phase1")
        self.assertEqual(m.when("ask", "ts_dprep"), [40, 160])
        self.assertEqual(m.entries("order"), [])


class Phase2(unittest.TestCase):
    def test_the_unlock_and_the_timer(self):
        """On the fall: 8,000 points and an income of 500, the reserve's cards (the Kubs among them) a second later,
        phase 3 two minutes after the fall."""
        m = run(World(rings=FALLS), PH3_T + 1, "difficulty", "phase1", "phase2", "phase3")
        self.assertEqual((m.entries("points"), m.entries("income")),
                         ([(FALL_T, op.FALL_GRANT)], [(FALL_T, op.FALL_INCOME)]))
        cards = m.entries("card")
        self.assertEqual(cards, [(FALL_T + 1, u, n) for u, n, _ in forces.RESERVE])
        self.assertIn((FALL_T + 1, "2K12_KUB_SOV", 2), cards)
        self.assertEqual(m.when("hint", "ts_hph3"), [PH3_T])


class Losses(unittest.TestCase):
    """From the fall (design 4.2): NATO owns the village for 60 s, or none of the player's units is in its circle for
    3 min; P2."""

    def test_nato_owns_the_village(self):
        """Captured at 500 s: the warning at once, the loss 60 s on; P2 fails, the funnel ends the battle."""
        world = World(rings=FALLS, captures={500: {VILLAGE_CZ: NATO}})
        m = run(world, 600, "difficulty", "funnel", "phase1", "losses")
        self.assertEqual(m.when("hint", "ts_hnato"), [501])
        self.assertEqual(m.vars[op.END], op.END_LOST)
        (t,) = m.when("dialog", "ts_dlost")
        self.assertEqual(t, 500 + op.NATO_HOLD_S + 1)
        self.assertEqual([(e[0], e[1]) for e in m.entries("failed")], [(t - 1, "ts_p2")])

    def test_a_recapture_resets_the_clock(self):
        """NATO holds it 40 s, the player takes it back, NATO again: the clock restarts."""
        world = World(rings=FALLS, captures={500: {VILLAGE_CZ: NATO}, 540: {VILLAGE_CZ: JOUEUR},
                                             600: {VILLAGE_CZ: NATO}})
        m = run(world, 700, "difficulty", "funnel", "phase1", "losses")
        self.assertEqual(m.when("hint", "ts_hnato"), [501, 601])
        (t,) = m.when("dialog", "ts_dlost")
        self.assertEqual(t, 600 + op.NATO_HOLD_S + 1)

    def test_the_village_empty(self):
        """No Soviet unit in the village's command zone from 400 s: the warning EMPTY_WARN_S into the streak, P2's
        second counter the streak's seconds, then the loss 3 min on."""
        rings = village([(0, 14), (300, 4)], [(FALL_T, 1)], [(0, 5), (400, 0)])
        m = run(World(rings=rings), 700, "difficulty", "funnel", "phase1", "losses")
        self.assertEqual(m.when("hint", "ts_hempty"), [400 + op.EMPTY_WARN_S])
        self.assertEqual(m.vars[op.END], op.END_EMPTY)
        self.assertEqual(m.when("dialog", "ts_dempty"), [400 + op.EMPTY_S + 1])
        self.assertEqual([e[2] for e in m.entries("failed")], [[0, op.EMPTY_S]])     # P2: NATO hold, empty

    def test_a_short_empty_streak_and_the_circle_do_not_count(self):
        """Empty for less than EMPTY_WARN_S: no warning, no loss. The 40 px circle empty while the player holds the
        zone's edge: nothing either; only the zone counts."""
        short = village([(0, 14), (300, 4)], [(FALL_T, 1)], [(0, 5), (400, 0), (400 + op.EMPTY_WARN_S - 5, 2)])
        edge = village([(0, 14), (300, 4)], [(FALL_T, 1)], [(0, 5), (400, 0)], zone=[(0, 3)])
        for rings in (short, edge):
            m = run(World(rings=rings), 800, "difficulty", "funnel", "phase1", "losses")
            self.assertEqual((m.when("hint", "ts_hempty"), m.vars.get(op.END, 0)), ([], 0))
        self.assertEqual((op.EMPTY_S - op.EMPTY_WARN_S, op.EMPTY_WARN_S), (160, 20))
        self.assertIn("within 2:40", STRINGS_LOC["ts_hempty"])

    def test_no_loss_before_the_fall(self):
        """Before the fall nothing counts: the village is NATO's and empty of Soviets."""
        m = run(World(rings=village([(0, 14)], mine=[(0, 0)])), 1000, "difficulty", "funnel", "losses")
        self.assertEqual(m.vars.get(op.END, 0), 0)
        self.assertEqual(m.when("show", "ts_p2"), [])


class Phase3(unittest.TestCase):
    """The counter-attack: battalion 1's waves, B1, its deadline (design 5.3, 4.2)."""

    @staticmethod
    def unharmed() -> list[tuple[int, int]]:
        """Steps of battalion 1's tanks alive, every tank of every team alive from its wave's creation."""
        out, n = [], 0
        for t in op.BN1_WAVES:
            n += sum(k for u, k, _ in t.wave.rows if u in forces.BN1_TANKS)
            out.append((PH3_T + int(t.wave.offset), n))
        return out

    def waves(self, difficulty: int | None, alive: list | None = None, until: int = PH3_T + 400) -> Model:
        """Phases 1 to 3, battalion 1's tanks alive by `alive` (Steps of ts_bn1_w_tanks; none lost when None)."""
        world = World(rings=FALLS, difficulty=difficulty, groups={op.BN1_TANKS_G: alive or self.unharmed()},
                      arrive_s=20, board_s=10)
        return run(world, until, "difficulty", "phase1", "phase2", "phase3")

    def created(self, m: Model) -> list[tuple[int, str]]:
        return sorted({(t, g.removesuffix("_inf").removesuffix("_ifv").removesuffix(f"_{op.TANKS}"))
                       for t, g, *_ in m.entries("create")})

    def test_waves_by_difficulty(self):
        """Medium: the recon screens and teams A, B, C, each at its offset after phase 3 starts; Easy leaves out C,
        Hard adds D; with no difficulty passed, Medium's."""
        want = {t.wave.key: (PH3_T + int(t.wave.offset), f"{op.BN1}{t.wave.key}") for t in op.BN1_WAVES}
        for level, keys in ((op.EASY, (1, 2, 3, 4)), (op.MEDIUM, (1, 2, 3, 4, 5)), (op.HARD, (1, 2, 3, 4, 5, 6)),
                            (None, (1, 2, 3, 4, 5))):
            with self.subTest(difficulty=level):
                self.assertEqual(self.created(self.waves(level)), [want[k] for k in keys])

    def test_a_wave(self):
        """Team A: its rows at the west entry (NATO), its riflemen boarding, its ROE, then FastMoveAndAttack to BOX W
        raced against LEG_S, then MoveAndAttack into the village raced against FINAL_LEG_S, blocking, then its Attack
        on the player's units, which stands until the wave is retired."""
        m = self.waves(op.MEDIUM)
        t0 = PH3_T + int(op.WAVE_GAP_S)
        rows = [(g, n, u, at) for t, g, n, u, at in m.entries("create") if t == t0]
        def into(u: str, c: str | None) -> str:
            if u in forces.BN1_TANKS:
                return f"_{op.TANKS}"
            return "_inf" if c else "_ifv" if u == "M2A2_Bradley_IFV_US" else ""

        self.assertEqual(rows, [(f"{op.BN1}3{into(u, c)}", n, u, "TS_EntryW") for u, n, c in op.BN1_WAVES[2].wave.rows])
        self.assertEqual(m.when("board", f"{op.BN1}3_inf"), [t0])
        self.assertEqual([(t, at, kind, blocking) for t, g, kind, at, blocking in m.entries("order")
                          if g == f"{op.BN1}3"],
                         [(t0 + 10, "TS_BoxW", shapes.FAST_MOVE_AND_ATTACK, True),
                          (t0 + 30, "TS_Village", shapes.MOVE_AND_ATTACK, True)])
        self.assertEqual([e for e in m.entries("attack") if e[1] == f"{op.BN1}3"],
                         [(t0 + 50, f"{op.BN1}3", op.GROUPE_JOUEUR)])
        self.assertEqual(m.when("SetIdleROEBehavior")[:1], [PH3_T])   # the recon screen's, which has none to board

    def test_a_wave_that_never_arrives_still_attacks(self):
        """A wave whose units never reach the village: its last leg's timeout, then the Attack all the same."""
        world = World(rings=FALLS, difficulty=op.MEDIUM, groups={op.BN1_TANKS_G: Phase3.unharmed()}, board_s=10)
        m = run(world, PH3_T + 400, "difficulty", "phase1", "phase2", "phase3")
        t0 = PH3_T + int(op.WAVE_GAP_S)
        self.assertEqual([e for e in m.entries("attack") if e[1] == f"{op.BN1}3"],
                         [(t0 + 10 + int(op.LEG_S + op.FINAL_LEG_S), f"{op.BN1}3", op.GROUPE_JOUEUR)])

    def test_b1_breaks_battalion_one(self):
        """Hard: teams A, B and C bring 31 tanks; with 2 of them left 20 s after team C, the tanks destroyed (made less
        alive) reach 29: B1 done with "29 / 41", the hint ts_hbn1 and BN1_DONE; team D, not yet created, stays home."""
        a, b, c = (PH3_T + int(t.wave.offset) for t in op.BN1_WAVES[2:5])
        t = c + 20
        m = self.waves(op.HARD, [(a, 10), (b, 21), (c, 31), (t, 2)])
        self.assertEqual(m.vars["ts_b1_made"], 31)
        done = [e for e in m.entries("done") if e[1] == "ts_b1"]
        self.assertEqual(done, [(t, "ts_b1", [29, 41])])
        self.assertEqual(m.when("hint", "ts_hbn1"), [t])
        self.assertEqual((m.vars[op.BN1_DONE], m.vars[op.B1_DONE], m.vars.get(op.BN1_OFF, 0)), (1, 1, 0))
        self.assertEqual([k for _, k in self.created(m)], [f"{op.BN1}{k}" for k in (1, 2, 3, 4, 5)])

    def test_no_kill_counted_while_tanks_arrive(self):
        """Each wave's tanks join the count with their creates: with none lost, the count stays 0 as they arrive."""
        a, b, c = (PH3_T + int(t.wave.offset) for t in op.BN1_WAVES[2:5])
        m = self.waves(op.MEDIUM, [(a, 10), (b, 21), (c, 31)], until=c + 30)
        self.assertEqual((m.vars["ts_b1_made"], m.vars["ts_b1_alive"], m.vars["ts_b1_k"]), (31, 31, 0))

    def test_the_deadline_breaks_it_off(self):
        """15 min of counter-attack without the break: the hint ts_hbreak, every wave by road to its lane's entry,
        and 2 min later all of battalion 1 removed (Vanished)."""
        t = PH3_T + int(op.BN1_DEADLINE_S)
        a, b, c = (PH3_T + int(w.wave.offset) for w in op.BN1_WAVES[2:5])
        m = self.waves(op.MEDIUM, [(a, 10), (b, 21), (c, 31), (t + int(op.BREAK_OFF_S), 0)], until=t + 200)
        self.assertEqual(m.when("hint", "ts_hbreak"), [t])
        orders = [(g, kind, at) for when, g, kind, at, _ in m.entries("order") if when == t]
        self.assertEqual(orders, [(f"{op.BN1}{w.wave.key}", shapes.FAST_MOVE_AND_ATTACK, op.LANES[w.wave.lane].entry)
                                  for w in op.BN1_WAVES])
        self.assertEqual(m.entries("kill"), [(t + int(op.BREAK_OFF_S), [op.BN1, f"{op.BN1}_inf"], None)])
        self.assertEqual((m.vars[op.BN1_DONE], m.vars[op.BN1_OFF], m.vars.get(op.B1_DONE, 0)), (1, 1, 0))
        self.assertEqual(m.vars["ts_b1_k"], 0)         # the removal is no kill: the count froze at the break-off


class Fires(unittest.TestCase):
    """The fire missions and the division fire plan (design 5.4)."""

    def fires(self, answers: dict, difficulty: int = op.MEDIUM, until: int = PH3_T + 900, boxes: dict | None = None):
        rings = {**FALLS, **(boxes or {})}
        world = World(rings=rings, answers=answers, difficulty=difficulty, arrive_s=20, board_s=10)
        return run(world, until, "difficulty", "phase1", "phase2", "fire_missions", "fire_plan")

    LEAD, HOLD = int(op.FIRE_LEAD_S), int(op.FIRE_HOLD_S)

    def test_fire_missions(self):
        """FIRE_T0 after phase 3: which guns, then where; ROCKET on BRAVO creates the BM-27s at GUN_SPAWN, which fire
        FIRE_LEAD_S later on BOX C's Name tag (the hint ts_hfirec with the create) and are removed FIRE_HOLD_S after,
        then the reload hint and the cooldown; the next mission, ARTILLERY on ALPHA, the 2S7Ms on BOX W."""
        m = self.fires({"ts_dfire1": [0, 1], "ts_dfire2": [1, 0]})
        first = PH3_T + int(op.FIRE_T0)
        second = first + self.LEAD + self.HOLD + op.KNOBS["ts_cool_s"][op.MEDIUM]
        self.assertEqual(m.when("ask", "ts_dfire1")[:2], [first, second])
        self.assertEqual(m.when("ask", "ts_dfire2")[:2], [first, second])
        self.assertEqual([e for e in m.entries("order")][:2],
                         [(first + self.LEAD, op.ROCKETS, shapes.SHOOT_ON_POSITION, op.BOX_TAGS["C"], False),
                          (second + self.LEAD, op.HEAVY, shapes.SHOOT_ON_POSITION, op.BOX_TAGS["W"], False)])
        self.assertEqual(m.entries("create")[:1], [(first, op.ROCKETS, 6, "BM27_Uragan_SOV", op.GUN_SPAWN)])
        self.assertEqual(m.entries("kill")[:1], [(first + self.LEAD + self.HOLD, [op.ROCKETS], None)])
        self.assertEqual(m.when("hint", "ts_hfirec")[:1], [first])
        self.assertEqual(m.when("hint", "ts_hreload")[:1], [first + self.LEAD + self.HOLD])
        self.assertEqual(m.entries("ammo"), [])

    def test_the_cooldown_by_difficulty(self):
        for level, cool in zip((op.EASY, op.MEDIUM, op.HARD), op.COOLDOWN_S):
            with self.subTest(difficulty=level):
                m = self.fires({}, level)
                first, second = m.when("ask", "ts_dfire1")[:2]
                self.assertEqual(second - first, op.FIRE_LEAD_S + op.FIRE_HOLD_S + cool)

    def test_the_fire_plan(self):
        """Held once, then fired: the NATO vehicles in each box counted, both batteries created together and fired on
        the box holding more (BOX C here), its hint announcing it; the dialog's flag is 0 again."""
        boxes = {op.BOX_RINGS["W"]: {NATO: [(0, 2)]}, op.BOX_RINGS["C"]: {NATO: [(0, 5)]}}
        m = self.fires({"ts_dplan": [1, 0]}, boxes=boxes)
        first = PH3_T + int(op.PLAN_T0)
        self.assertEqual(m.when("ask", "ts_dplan"), [first, first + int(op.PLAN_GAP_S)])
        fired = first + int(op.PLAN_GAP_S)
        self.assertEqual((m.vars["ts_plan_w"], m.vars["ts_plan_c"]), (2, 5))
        self.assertIn((fired + self.LEAD, op.GUNS, shapes.SHOOT_ON_POSITION, op.BOX_TAGS["C"], False),
                      m.entries("order"))
        self.assertEqual([(g, n, u) for t, g, n, u, _ in m.entries("create") if t == fired],
                         [(op.GUNS, 6, "2S7M_Malka_SOV"), (op.GUNS, 6, "BM27_Uragan_SOV")])
        self.assertEqual(m.when("hint", "ts_hplanc"), [fired])
        self.assertEqual(m.vars["ts_plan_open"], 0)

    def test_one_fire_at_a_time(self):
        """A fire mission answered while the fire plan holds the guns waits for it to end."""
        m = self.fires({"ts_dplan": [1, 0]}, until=PH3_T + 1200)
        plan = PH3_T + int(op.PLAN_T0 + op.PLAN_GAP_S)
        second = PH3_T + int(op.FIRE_T0) + self.LEAD + self.HOLD + op.KNOBS["ts_cool_s"][op.MEDIUM]
        self.assertLess(plan, second)
        self.assertLess(second, plan + self.LEAD + self.HOLD)   # asked while the plan's guns are held
        shots = [t for t, *_ in m.entries("order")]
        self.assertEqual(shots[:3], [PH3_T + int(op.FIRE_T0) + self.LEAD, plan + self.LEAD,
                                     plan + self.LEAD + self.HOLD + 1 + self.LEAD])   # the next tick


# Phase 4 from second 0 (battalion 1 beaten): battalion 2 at BN2_T, the release dialog at ASK_T.
BN2_T = int(op.BN2_GAP_S)
ASK_T = BN2_T + int(op.RELEASE_ASK_S)
STRUCK_T = ASK_T + int(op.STRIKE_T + op.STRIKE_KILL_S)


def phase45(world: World, until: int, values: dict | None = None) -> Model:
    """Phases 4 and 5 and the funnel, battalion 1 beaten at second 0."""
    return run(world, until, "funnel", "phase4", "phase5", values={op.BN1_DONE: 1, **(values or {})})


class Phase4(unittest.TestCase):
    """The surprise and the release (design 5.5, 5.6)."""

    def test_battalion_two_appears(self):
        """BN2_GAP_S after battalion 1 is beaten: SpawnUnits on its 52 hidden spawns, its groups, the hint ts_hbn2 and
        B2's countdown from 300 s, pinned at its north edge."""
        m = phase45(World(), BN2_T + 5)
        (spawned,) = m.entries("spawn")
        self.assertEqual((spawned[0], len(spawned[1])), (BN2_T, 52))
        unions = {g: srcs for t, g, srcs in m.entries("union") if t == BN2_T}
        self.assertEqual(unions[op.BN2], [f"{op.BN2}_w", f"{op.BN2}_c"])
        self.assertEqual(len(unions[op.BN2_TANKS_G]), 29)
        self.assertEqual([len(unions[f"{op.BN2}_{h}_{k}"]) for h in "wc" for k in ("inf", "ifv")], [4, 4, 4, 4])
        self.assertEqual(m.when("hint", "ts_hbn2"), [BN2_T])
        self.assertEqual(m.when("show", "ts_b2"), [BN2_T])
        self.assertEqual(m.vars["ts_b2_s"], op.COUNTDOWN_S - 5)

    def test_the_release_waits_for_the_guns(self):
        """The release dialog waits until no fire holds the guns, then holds them itself."""
        m = phase45(World(answers={"ts_drel": [1]}), ASK_T + 60, values={op.BUSY: 1})
        self.assertEqual(m.when("ask", "ts_drel"), [])
        m = phase45(World(answers={"ts_drel": [0]}), ASK_T + 5)
        self.assertEqual(m.when("ask", "ts_drel", 0), [ASK_T])
        self.assertEqual(m.vars[op.BUSY], 1)

    def test_a_flag_left_set_never_hides_the_release(self):
        """The fire plan's dialog flag left at 1 (the first play's race): the release dialog shows RELEASE_MAX_WAIT_S
        on all the same, with most of the countdown left."""
        m = phase45(World(answers={"ts_drel": [1]}), ASK_T + int(op.RELEASE_MAX_WAIT_S) + 5,
                    values={"ts_plan_open": 1})
        self.assertEqual(m.when("ask", "ts_drel"), [ASK_T + int(op.RELEASE_MAX_WAIT_S)])
        self.assertGreater(m.vars["ts_b2_s"], op.COUNTDOWN_S / 2)

    def test_withheld(self):
        """No: the hint ts_hwith, the guns freed; the countdown runs out 300 s after battalion 2 appeared, then B2's
        countdown is done, battalion 2 attacks (each half boards, then its lane) and phase 5 starts; B2's "tanks left"
        is done once 9 or fewer are left, with the hint ts_hbn2b."""
        end = BN2_T + op.COUNTDOWN_S
        world = World(answers={"ts_drel": [1]}, groups={op.BN2_TANKS_G: [(0, 29), (end + 100, 9)], **NATO_LEFT},
                      arrive_s=20, board_s=10)
        m = phase45(world, end + 120)
        self.assertEqual((m.vars[op.STRIKE], m.vars[op.BUSY]), (op.WITHHELD, 0))
        self.assertEqual(m.when("hint", "ts_hwith"), [ASK_T])
        self.assertEqual(m.when("hint", "ts_hatk"), [end])
        self.assertEqual([(t, name) for t, name, _ in m.entries("done")][:1], [(end, "ts_b2")])
        self.assertEqual(m.when("board", f"{op.BN2}_w_inf"), [end])
        self.assertEqual([(g, at) for t, g, kind, at, _ in m.entries("order") if t == end + 10],
                         [(f"{op.BN2}_w", "TS_BoxW"), (f"{op.BN2}_c", "TS_BoxC")])
        self.assertEqual(m.entries("done")[-1], (end + 100, "ts_b2n", [9]))
        self.assertEqual(m.when("hint", "ts_hbn2b"), [end + 100])
        self.assertIn(m.when("hint", "ts_hph5")[0] - end, (0, 1))      # phase 5 with the attack (the model's tick)
        self.assertEqual(m.when("fx"), [])


class Strike(unittest.TestCase):
    """The strike's order and timing (design 5.6), seconds after the release: the warning and the round's 2S7M at
    once, its order FIRE_LEAD_S later (its shells leave after its 30 s aiming time), the effect at 0:30, the kill
    STRIKE_KILL_S later, then the dressing for a minute; B2 done and phase 5 with the kill."""

    @classmethod
    def setUpClass(cls):
        world = World(rings={op.STRIKE_RING: {NATO: [(0, 52)]}}, answers={"ts_drel": [0]}, groups=NATO_LEFT)
        cls.m = phase45(world, STRUCK_T + 120)

    def test_the_order(self):
        m, t0 = self.m, ASK_T
        self.assertEqual(m.vars[op.STRIKE], op.RELEASED)
        self.assertEqual(m.when("hint", "ts_hrel"), [t0])
        self.assertEqual(m.when("show", "ts_ozone"), [t0])
        round_t = t0 + int(op.STRIKE_ROUND_T)
        lead, hold = int(op.FIRE_LEAD_S), int(op.FIRE_HOLD_S)
        self.assertEqual(m.entries("create"), [(round_t, op.STRIKER, 1, "2S7M_Malka_SOV", op.GUN_SPAWN)])
        self.assertEqual(m.entries("ignored"), [(round_t, op.STRIKER)])
        self.assertEqual(m.entries("order"),
                         [(round_t + lead, op.STRIKER, shapes.SHOOT_ON_POSITION, "TS_Assembly", False)])
        fx = m.entries("fx")
        self.assertEqual(fx[0], (t0 + int(op.STRIKE_T), "fx_HE_Mega_Bomb_ForScript", "TS_Assembly"))
        self.assertEqual(m.entries("collect"), [(STRUCK_T, "ts_struck_g", op.STRIKE_RING, 52)])
        self.assertEqual(m.entries("kill"), [(STRUCK_T, ["ts_struck_g"], shapes.PENETRATION),
                                             (round_t + lead + hold, [op.STRIKER], None)])
        self.assertEqual(m.entries("ammo"), [])
        self.assertEqual(sorted((t, name) for t, name, _ in m.entries("done")),
                         [(STRUCK_T, "ts_b2"), (STRUCK_T, "ts_ozone")])
        self.assertIn(m.when("hint", "ts_hph5")[0] - STRUCK_T, (0, 1))  # phase 5 with the kill
        self.assertEqual(m.vars[op.BUSY], 0)

    def test_the_dressing(self):
        """Fires and black smoke together at each of the six spots, 10 s apart, from the kill: a minute."""
        dressing = self.m.entries("fx")[1:]
        self.assertEqual(dressing, [(STRUCK_T + k * int(op.DRESSING_STEP_S), fx.rsplit("/", 1)[1], name)
                                    for k, name in enumerate(op.DRESSING) for fx in op.DRESSING_FX])
        self.assertEqual(dressing[-1][0] - dressing[0][0] + op.DRESSING_STEP_S, 60.0)

    def test_no_attack_after_a_strike(self):
        self.assertEqual(self.m.vars.get(op.ATTACK, 0), 0)
        self.assertEqual(self.m.when("hint", "ts_hatk"), [])


class Air(unittest.TestCase):
    """NATO's fighter sweeps (design 6.3), from phase 3 (PH3 at second 0) and at battalion 2's attack."""

    def sweeps(self, difficulty: int | None, values: dict, until: int = 700, **world) -> Model:
        return run(World(difficulty=difficulty, **world), until, "difficulty", "air", values=values)

    def test_schedule(self):
        """Two F-15Cs over BOX W at 2:30, two over BOX C at 6:00, and on Hard one more over the village at 10:00;
        each revealed, ordered a second later, its own group."""
        for level, keys in ((op.EASY, ("s1", "s2")), (op.MEDIUM, ("s1", "s2")), (op.HARD, ("s1", "s2", "s3")),
                            (None, ("s1", "s2"))):
            with self.subTest(difficulty=level):
                m = self.sweeps(level, {op.PH3: 1})
                want = [s for s in op.SWEEPS_AFTER_PH3 if s.key in keys]
                self.assertEqual([(t, len(tags)) for t, tags in m.entries("spawn")],
                                 [(int(s.after), s.count) for s in want])
                self.assertEqual([(t, g, kind, at) for t, g, kind, at, _ in m.entries("order")],
                                 [(int(s.after) + 1, f"ts_air_{s.key}", shapes.AIRPLANE_MOVE_AND_ENGAGE, s.target)
                                  for s in want])
        self.assertEqual([(s.unit, s.count, s.target, s.after) for s in op.SWEEPS_AFTER_PH3],
                         [("F15C_Eagle_AA_US", 2, op.BOX_RINGS["W"], 150.0), ("F15C_Eagle_AA_US", 2, op.BOX_RINGS["C"],
                                                                              360.0),
                          ("F15C_Eagle_AA_US", 1, op.VILLAGE_RING, 600.0)])

    def test_home_once_spent(self):
        """A sweep goes home (AirplaneEvacuate, blocking) once all its fighters are out of fuel or ammunition."""
        m = self.sweeps(op.MEDIUM, {op.PH3: 1}, until=500, spent={"ts_air_s1": [(0, 0), (300, 1), (400, 2)]})
        self.assertEqual([(t, g, kind, blocking) for t, g, kind, _, blocking in m.entries("order")
                          if kind == shapes.AIRPLANE_EVACUATE], [(400, "ts_air_s1", shapes.AIRPLANE_EVACUATE, True)])

    def test_phantoms_come_with_battalion_two(self):
        """Once battalion 2 attacks (the strike withheld): two West German Phantoms over the village; nothing before."""
        m = self.sweeps(op.MEDIUM, {}, until=50)
        self.assertEqual(m.entries("spawn"), [])
        m = self.sweeps(op.MEDIUM, {op.ATTACK: 1}, until=50)
        self.assertEqual([(t, len(tags)) for t, tags in m.entries("spawn")], [(0, 2)])
        self.assertEqual(op.SWEEP_AT_ATTACK[1:4], ("F4F_Phantom_II_AA_RFA", 2, op.VILLAGE_RING))

    def test_the_fighters_wait_hidden(self):
        """Each sweep's fighters are pre-placed hidden in the NATO camp, ExperienceLevel 2 as Survivors' strike
        aircraft, inside the NATO deployment zone."""
        for s in op.SWEEPS:
            items = [it for it in op.ITEMS if it.group == f"air_{s.key}"]
            with self.subTest(sweep=s.key):
                self.assertEqual([it.unit for it in items], [s.unit] * s.count)
                for it in items:
                    self.assertEqual((it.ranking, it.camp, it.disable_auto_spawn, it.experience),
                                     ("Camp_3", 3, True, op.AIR_EXPERIENCE))
                    x, y = px(it)
                    x0, y0, x1, y1 = ts_map.NATO_DZ
                    self.assertTrue(x0 <= x <= x1 and y0 <= y <= y1, (x, y))


def clock(m: Model, dialog: str) -> int:
    """Seconds from phase 5's hint to the end dialog `dialog`."""
    return m.when("dialog", dialog)[0] - m.when("hint", "ts_hph5")[0]


class Phase5(unittest.TestCase):
    """The end clock and the grade (design 5.8)."""

    def grade(self, answer: int, until: int, values: dict | None = None, **world) -> Model:
        """Phases 4 and 5 with the release answered `answer`; the village the player's unless `owner` says; a NATO
        ground unit left in each group (NATO_LEFT) unless `groups` says otherwise."""
        world.setdefault("owner", JOUEUR)
        world["groups"] = {**NATO_LEFT, **world.get("groups", {})}
        return phase45(World(answers={"ts_drel": [answer]}, **world), until, values)

    def test_after_a_strike(self):
        """Released, battalion 1 broken: Total (released) 5 min after the kill, with its dialog and screen."""
        m = self.grade(0, STRUCK_T + 400, {op.B1_DONE: 1}, groups={"Groupe_Joueur": [(0, 40)]}, lost=[(0, 10)])
        self.assertEqual(m.vars[op.END], op.END_TOTAL_R)
        self.assertIn(clock(m, "ts_dtotr"), (op.END_CLOCK_S, op.END_CLOCK_S + 1))
        (t,) = m.when("dialog", "ts_dtotr")
        self.assertEqual(m.entries("end"), [(t, shapes.TOTAL_VICTORY, None)])

    def test_major_and_minor(self):
        """Released but battalion 1 not broken: Major, or Minor once the losses pass what is left (more than half of
        what was bought)."""
        until = STRUCK_T + 400
        m = self.grade(0, until, groups={"Groupe_Joueur": [(0, 40)]}, lost=[(0, 40)])
        self.assertEqual(m.vars[op.END], op.END_MAJOR_R)
        m = self.grade(0, until, groups={"Groupe_Joueur": [(0, 40)]}, lost=[(0, 41)])
        self.assertEqual(m.vars[op.END], op.END_MINOR_R)

    def test_total_comes_first(self):
        """Both battalions beaten with heavy losses: Total, not Minor."""
        m = self.grade(0, STRUCK_T + 400, {op.B1_DONE: 1}, groups={"Groupe_Joueur": [(0, 10)]}, lost=[(0, 50)])
        self.assertEqual(m.vars[op.END], op.END_TOTAL_R)

    def test_withheld_until_battalion_two_breaks(self):
        """Withheld: the end clock runs from the attack until battalion 2 is broken (here 10 min on), then Total
        (withheld) with battalion 1 broken."""
        attack = BN2_T + op.COUNTDOWN_S
        groups = {op.BN2_TANKS_G: [(0, 29), (attack + 600, 8)], "Groupe_Joueur": [(0, 40)]}
        m = self.grade(1, attack + 700, {op.B1_DONE: 1}, groups=groups, arrive_s=20, board_s=10)
        self.assertEqual(m.vars[op.END], op.END_TOTAL_W)
        self.assertIn(clock(m, "ts_dtotw"), (600, 601, 602))           # the break, read by the next count

    def test_withheld_cap(self):
        """Withheld and battalion 2 never broken: 20 min after the attack, Major (withheld)."""
        attack = BN2_T + op.COUNTDOWN_S
        groups = {op.BN2_TANKS_G: [(0, 29)], "Groupe_Joueur": [(0, 40)]}
        m = self.grade(1, attack + 1300, {op.B1_DONE: 1}, groups=groups, arrive_s=20, board_s=10)
        self.assertEqual(m.vars[op.END], op.END_MAJOR_W)
        self.assertIn(clock(m, "ts_dmajw"), (op.END_CLOCK_WITHHELD_S, op.END_CLOCK_WITHHELD_S + 1))

    def test_nato_owns_the_village_at_the_end(self):
        """NATO owns the village when the clock runs out: the battle is lost (NATO has retaken it)."""
        m = self.grade(0, STRUCK_T + 400, owner=NATO, groups={"Groupe_Joueur": [(0, 40)]})
        self.assertEqual(m.vars[op.END], op.END_LOST)

    def test_a_loss_written_first_stands(self):
        m = self.grade(0, STRUCK_T + 400, {op.END: op.END_EMPTY, op.B1_DONE: 1})
        self.assertEqual(m.vars[op.END], op.END_EMPTY)
        self.assertEqual([e[1:] for e in m.log if e[1] == "dialog"], [("dialog", "ts_dempty")])

    def test_the_clock_is_shown(self):
        """With phase 5's hint, its end clock starts and shows: after a strike the timer ts_clock_r of END_CLOCK_S, P3
        (ts_p3r) showing it; the battle ends as it reads 0, and P3 is done with the win. After withholding,
        ts_clock_w of END_CLOCK_WITHHELD_S and P3 ts_p3w."""
        m = self.grade(0, STRUCK_T + 400, {op.B1_DONE: 1}, groups={"Groupe_Joueur": [(0, 40)]})
        (t0,) = m.when("hint", "ts_hph5")
        self.assertEqual(m.entries("timer"), [(t0, op.CLOCK_R, int(op.END_CLOCK_S))])
        self.assertEqual(m.when("show", "ts_p3r", op.CLOCK_R), [t0])
        (end,) = m.when("dialog", "ts_dtotr")
        self.assertIn(end - t0, (op.END_CLOCK_S, op.END_CLOCK_S + 1))
        self.assertIn(m.when("done", "ts_p3r")[0] - end, (-1, 0, 1))
        attack = BN2_T + op.COUNTDOWN_S
        m = self.grade(1, attack + 30, {op.B1_DONE: 1}, arrive_s=20, board_s=10)
        (t0,) = m.when("hint", "ts_hph5")
        self.assertEqual(m.entries("timer"), [(t0, op.CLOCK_W, int(op.END_CLOCK_WITHHELD_S))])
        self.assertEqual(m.when("show", "ts_p3w", op.CLOCK_W), [t0])
        self.assertEqual(m.when("show", "ts_p3r"), [])

    def test_nato_spent_ends_at_once(self):
        """The smoke play's dead end: after a strike, with NATO's ground forces gone (at the kill, or a minute later),
        the battle ends at once with the grade that state earns (Total, released: battalion 1 broken, battalion 2
        struck), not when the 5:00 clock runs out; P2 and P3 are done with it."""
        for after in (0, 60):
            with self.subTest(after=after):
                gone = STRUCK_T + after
                m = self.grade(0, STRUCK_T + 400, {op.B1_DONE: 1},
                               groups={"Groupe_Joueur": [(0, 40)], **nato_gone(gone)}, lost=[(0, 10)])
                self.assertEqual(m.vars[op.END], op.END_TOTAL_R)
                (end,) = m.when("dialog", "ts_dtotr")
                self.assertIn(end - gone, (0, 1, 2))
                self.assertEqual(m.entries("end"), [(end, shapes.TOTAL_VICTORY, None)])
                self.assertIn(m.when("done", "ts_p3r")[0] - end, (-1, 0, 1))

    def test_a_unit_left_holds_the_clock(self):
        """One NATO ground group still holding a unit (any of the four) keeps the clock running to its end."""
        for name in op.NATO_GROUND:
            with self.subTest(group=name):
                groups = {"Groupe_Joueur": [(0, 40)], **nato_gone(STRUCK_T), name: [(0, 1)]}
                m = self.grade(0, STRUCK_T + 400, {op.B1_DONE: 1}, groups=groups)
                self.assertIn(clock(m, "ts_dtotr"), (op.END_CLOCK_S, op.END_CLOCK_S + 1))

    def test_withheld_nato_spent(self):
        """Withheld: battalion 2 destroyed to its last unit, with the rest of NATO's ground forces, ends the battle at
        once, Total (withheld) with battalion 1 broken, even while B2's count (polled) has not yet read the break: here
        its tanks' count reads the loss 2 s late."""
        attack = BN2_T + op.COUNTDOWN_S
        gone = attack + 400
        groups = {op.BN2_TANKS_G: [(0, 29), (gone + 2, 0)], "Groupe_Joueur": [(0, 40)], **nato_gone(gone)}
        m = self.grade(1, gone + 30, {op.B1_DONE: 1}, groups=groups, arrive_s=20, board_s=10)
        self.assertEqual(m.vars[op.END], op.END_TOTAL_W)
        self.assertIn(m.when("dialog", "ts_dtotw")[0] - gone, (0, 1, 2))


def boxes(answer: int, until: int, groups: dict | None = None) -> Model:
    """Phases 3 (PH3 at second 0, battalion 1 already beaten), 4 and 5 and the funnel, the release answered
    `answer`, the village the player's, a NATO ground unit left (NATO_LEFT) unless `groups` says."""
    world = World(answers={"ts_drel": [answer]}, owner=JOUEUR, groups={**NATO_LEFT, **(groups or {})}, arrive_s=20,
                  board_s=10)
    return run(world, until, "funnel", "phase3", "phase4", "phase5", values={op.PH3: 1, op.BN1_DONE: 1})


class Boxes(unittest.TestCase):
    """The fire boxes' labels close once nothing more comes through them, so they never stand as open tasks in
    phase 5."""

    def test_closed_at_the_kill(self):
        """After a strike: BOX W and BOX C done at the kill (or the model's next tick), five minutes before the end."""
        m = boxes(0, STRUCK_T + 30)
        done = [(t, name) for t, name, _ in m.entries("done") if name.startswith("ts_ob")]
        self.assertEqual(sorted(name for _, name in done), ["ts_obc", "ts_obw"])
        self.assertTrue(all(t - STRUCK_T in (0, 1) for t, _ in done), done)
        self.assertEqual(m.vars.get(op.END, 0), 0)

    def test_closed_once_battalion_two_breaks(self):
        """Withheld: the boxes stay open while battalion 2 attacks through them, and close once it is broken."""
        attack = BN2_T + op.COUNTDOWN_S
        broken = attack + 300
        m = boxes(1, broken + 30, groups={op.BN2_TANKS_G: [(0, 29), (broken, 9)]})
        (b2n,) = m.when("done", "ts_b2n")
        done = [(t, name) for t, name, _ in m.entries("done") if name.startswith("ts_ob")]
        self.assertEqual(sorted(name for _, name in done), ["ts_obc", "ts_obw"])
        self.assertTrue(all(t - b2n in (0, 1) for t, _ in done), (b2n, done))


class EndClock(unittest.TestCase):
    """Phase 5's end clock in stock's form (design 5.8), read off the beats (no stock data needed)."""

    @classmethod
    def setUpClass(cls):
        cls.ctx = op.Ctx()
        cls.nodes = list(walk([beats_root(op.BEATS, cls.ctx)]))

    def test_p3_shows_the_clock(self):
        """Each road's P3 is a Primary objective whose label shows on the village's command zone, as TheKitzingenRuse
        #281 ("HOLD DMITRI", "Reinforcements in %1", on CommandPoints/CZ_B): its label's one %1 is its timer
        (ListTimersForEtiquetteText), of END_CLOCK_S or END_CLOCK_WITHHELD_S, which StartTimer starts right before the
        Simultaneous holding P3, last; beside P3 the race that ends the phase: WaitDuration of the same length,
        (withheld) battalion 2 broken, and NATO spent."""
        for text, name, seconds in (("ts_p3r", op.CLOCK_R, op.END_CLOCK_S),
                                    ("ts_p3w", op.CLOCK_W, op.END_CLOCK_WITHHELD_S)):
            with self.subTest(objective=text):
                p3 = objective_named(self.nodes, text)
                (timer,) = prop(p3, "ListTimersForEtiquetteText")
                self.assertEqual((last(timer), timer.cls, prop(timer, "Duree").v),
                                 (name, "TGDVariableTimer", int(seconds)))
                self.assertEqual((last(prop(p3, "Position")), prop(p3, "ShowEtiquette") is not None,
                                  prop(p3, "ListVariables"), prop(p3, "LabelComponent").text),
                                 (VILLAGE_CZ, True, None, "Primary"))
                self.assertEqual(token(prop(p3, "ObjectiveEtiquetteText")), f"{text}l")
                self.assertEqual(STRINGS_LOC[f"{text}l"].count("%1"), 1)
                held = parent_of(self.nodes, p3)
                start, simul = subs(parent_of(self.nodes, held))
                self.assertEqual((start.cls, prop(start, "Timer"), simul, subs(simul)[-1]),
                                 ("TGDDescriptorStartTimer", timer, held, p3))
                race = subs(subs(simul)[0])[0]
                wait, *more, spent = subs(race)
                self.assertEqual((race.cls, prop(wait, "Duree").v), ("TGDDescriptorCompetition", seconds))
                self.assertEqual([last(prop(prop(w, "Condition"), "Variable")) for w in more],
                                 [] if name == op.CLOCK_R else [op.BN2_BROKEN])
                tests = prop(prop(spent, "Condition"), "SousConditions")
                self.assertEqual([last(prop(c, "Variable")) for c in tests], list(op.NATO_GROUND))
                self.assertTrue(all(prop(prop(c, "Operator"), "Value") is None
                                    and prop(prop(c, "Operator"), "OperatorType") is None for c in tests))  # == 0
        self.assertIn(f"{op.END_CLOCK_S / 60:g} MIN", STRINGS_LOC["ts_p3r"])
        self.assertIn(f"{op.END_CLOCK_WITHHELD_S / 60:g} MIN", STRINGS_LOC["ts_p3w"])

    def test_every_nato_ground_unit_is_counted(self):
        """Every NATO ground unit the script makes or reveals reaches a NATO_GROUND group through
        AddUnitGroupListToUnitGroup, so nato_spent never ends the battle while one is left: each CreateUnitOnPosition
        in the NATO camp creates into such a group, and each NATO Spawn item's tag (the garrison's and battalion 2's)
        is such a source. The fighters' are not: they are left out on purpose (op.nato_spent)."""
        into: dict[int, list] = {}
        for u in of(self.nodes, "AddUnitGroupListToUnitGroup"):
            for src in prop(u, "ListGroupSource"):
                into.setdefault(id(src), []).append(prop(u, "GroupDestination"))

        def counted(node) -> bool:
            seen, stack = set(), [node]
            while stack:
                n = stack.pop()
                if n.cls == "TGDVariableUnitGroup" and last(n) in op.NATO_GROUND:
                    return True
                if id(n) not in seen:
                    seen.add(id(n))
                    stack += into.get(id(n), [])
            return False

        creates = [n for n in of(self.nodes, "CreateUnitOnPosition") if last(prop(n, "Camp")) == NATO]
        self.assertEqual(sum(prop(n, "NbUnit").v for n in creates),
                         sum(n for t in op.BN1_WAVES for _, n, _ in t.wave.rows))
        for n in creates:
            self.assertTrue(counted(prop(n, "Group")), last(prop(n, "Group")))
        spawns = [it for it in op.ITEMS if it.addon == "Spawn" and it.camp == profile.camp_index(op.ENEMY)]
        ground = [it for it in spawns if not it.group.startswith("air_")]
        self.assertEqual(len(ground), op.GARRISON_N + len(op.bn2_items()))
        for it in spawns:
            self.assertEqual(counted(self.ctx.tag(it.name)), it in ground, it.name)


class Funnel(unittest.TestCase):
    def test_every_ending(self):
        """Each END value: its dialog, then its TriggerEndGame (a win leaves the winner out)."""
        for value, (dialog, kind, loses) in op.ENDINGS.items():
            with self.subTest(end=value):
                m = run(World(), 5, "funnel", values={op.END: value})
                self.assertEqual([e[1:] for e in m.log], [("dialog", dialog),
                                                          ("end", kind, shapes.PACT_ALLIANCE if loses else None)])


class Difficulty(unittest.TestCase):
    def test_branches(self):
        """Each level sets ts_diff and every knob to its value, and its hint shows DIFF_HINT_T after the launch; with
        none passed, Medium's values and the "not received" hint."""
        for level, hint in ((op.EASY, "ts_hdif0"), (op.MEDIUM, "ts_hdif1"), (op.HARD, "ts_hdif2"), (None, "ts_hdif9")):
            with self.subTest(difficulty=level):
                m = run(World(difficulty=level), 20, "difficulty")
                k = op.MEDIUM if level is None else level
                self.assertEqual({name: m.vars[name] for name in op.KNOBS},
                                 {name: values[k] for name, values in op.KNOBS.items()})
                self.assertEqual(m.vars["ts_diff"], k)
                self.assertEqual(m.when("hint", hint), [int(op.DIFF_HINT_T)])

    def test_the_fall_threshold_by_difficulty(self):
        """3 of the garrison left: the village falls at Easy (5) and Medium (4), not at Hard (2)."""
        rings = village([(0, 14), (300, 3)], [(FALL_T, 1)])
        for level, falls in ((op.EASY, True), (op.MEDIUM, True), (op.HARD, False)):
            with self.subTest(difficulty=level):
                m = run(World(rings=rings, difficulty=level), FALL_T + 5, "difficulty", "phase1")
                self.assertEqual(m.vars.get(op.FALLEN, 0), int(falls))


if __name__ == "__main__":
    unittest.main()
