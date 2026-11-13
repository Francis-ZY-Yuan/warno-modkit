"""What the Twin Strike tests share: the example on sys.path, its quiet builds, the stock data its classes skip
without, the readers the deck and range tests use, and `Model`, a step model of the script runtime that the mission
tests drive with a `World`. Not a test module itself.

The example is found from this component's own folder (a clone's components/ops, or an installed plugin's folder),
and the test builds go to a temporary folder, the profile's build root while the tests run."""
from __future__ import annotations

import atexit
import dataclasses
import math
import os
import re
import shutil
import sys
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path
from typing import NamedTuple

COMPONENT = Path(__file__).resolve().parents[1]   # the ops component: its tests/, examples/, src/, ...
TWIN_STRIKE = COMPONENT / "examples" / "twin-strike"
sys.path.insert(0, str(TWIN_STRIKE))

from modkit.core import paths  # noqa: E402
from modkit.ops import build as ops_build  # noqa: E402
from modkit.ops import testing  # noqa: E402
from modkit.ops.maps import WORLD_PER_MINIMAP_PX  # noqa: E402
from modkit.ops.models import ForceRow  # noqa: E402
from modkit.ops.profile import Content  # noqa: E402
from modkit.ops.shapes import GRU_WORLD  # noqa: E402
from twinstrike import CONTENTS, profile  # noqa: E402

OUT_ROOT = tempfile.mkdtemp(prefix="modkit-ops-twin-strike-")   # test builds, removed after each test
atexit.register(shutil.rmtree, OUT_ROOT, True)
# What the tests read: Survivors' Definition (every script's input), Twin Cities' small layout (the cut and its
# camera), the stock decks (the deck diff) and the game's unit database (the build's unit gate). A class needing one
# skips without it.
SCRIPT_DATA = paths.skip_unless_extracted("kreide_op", "challenge_Survivors_Definition")
LAYOUT_DATA = paths.skip_unless_extracted("twincities_op", "SM_SU_3x3_TwinCities_03_Details", "out")
DECK_DATA = paths.skip_unless_extracted("moddata_base", "GameData", "Generated", "Gameplay", "Decks", "DeckPacks.ndf")
GAME = paths.skip_unless_game_dir("Mods", "ModData", "base.zip")


def build_profile():
    """Twin Strike's profile with OUT_ROOT as its build root, so a rebuild may clear a test build there."""
    return dataclasses.replace(profile.profile(), build_root=OUT_ROOT)


def quiet_build(content: Content, out_dir: str):
    """Twin Strike's build of `content` (every gate) with its report swallowed."""
    return testing.quiet_build(build_profile(), content, out_dir)


def build_main(argv: list[str]) -> int:
    """Twin Strike's build.py front end."""
    return ops_build.cli(build_profile, CONTENTS, argv)


def gru(a: tuple[float, float], b: tuple[float, float]) -> float:
    """The distance between two minimap points in GRU (shapes.GRU_WORLD world units each)."""
    return math.dist(a, b) * WORLD_PER_MINIMAP_PX / GRU_WORLD


def _decks_folder() -> str:
    return os.path.join(str(paths.extracted_root()), "moddata_base", "GameData", "Generated", "Gameplay", "Decks")


def _deck_block(identifier: str) -> str:
    """The Decks.ndf text of the TDeckDescriptor whose DeckIdentifier is `identifier`."""
    with open(os.path.join(_decks_folder(), "Decks.ndf"), encoding="utf-8", errors="replace") as fh:
        decks = fh.read()
    blocks = [b for b in re.split(r"(?m)^export ", decks) if f'DeckIdentifier = "{identifier}"' in b]
    if len(blocks) != 1:
        raise LookupError(f"{len(blocks)} stock decks are named {identifier}")
    return blocks[0]


def stock_deck(identifier: str) -> list[ForceRow]:
    """The packs of the stock deck `identifier` as rows (unit, number, transport or None), in its DeckPackList order:
    the mod SDK's Decks.ndf and DeckPacks.ndf from the extraction, read by the toolkit's reader (gates.deck_packs,
    which gates.stock_deck_packs reads the game's copy with). A deck stock lacks raises LookupError."""
    _deck_block(identifier)
    texts = []
    for name in ("Decks.ndf", "DeckPacks.ndf"):
        with open(os.path.join(_decks_folder(), name), encoding="utf-8", errors="replace") as fh:
            texts.append(fh.read())
    return gates.deck_packs(*texts, identifier)


def stock_deck_groups(identifier: str) -> list[list[tuple[str, tuple[int, ...]]]]:
    """The battlegroups of the stock deck `identifier`, in DeckCombatGroupList order: each a list of its smart groups
    as (name, the DeckPackList indices it holds), from the extraction's Decks.ndf. A pack no group holds is not in the
    buy menu."""
    groups = _deck_block(identifier).split("DeckPackList", 1)[0].split("TDeckCombatGroupDescriptor")[1:]
    return [[(name, tuple(int(i) for i in re.findall(r"\((\d+),\s*\d+\)", held)))
             for name, held in re.findall(r'TDeckSmartGroupDescriptor\s*\(\s*Name = "(\w+)"\s*'
                                          r"PackIndexUnitNumberList\s*=\s*\[(.*?)\]", group, re.S)]
            for group in groups]


DIVISION_RULES = "GameData/Generated/Gameplay/Decks/DivisionRules.ndf"


def division_rules() -> dict[str, dict[str, tuple[str, ...]]]:
    """Every division's rule in the game's DivisionRules.ndf (the deck builder's: what a division can field), by the
    rule's name -> {bare unit name: the transports its AvailableTransportList allows}."""
    text = gates.database_text(gates.unit_archive(), DIVISION_RULES)
    out = {}
    for name, body in gates.top_blocks(text):
        units = {}
        for rule in re.split(r"\bTDeckUniteRule\b", body)[1:]:
            unit = re.search(r"UnitDescriptor\s*=\s*\$/GFX/Unit/Descriptor_Unit_(\w+)", rule)
            carriers = re.search(r"AvailableTransportList\s*=\s*\[(.*?)\]", rule, re.S)
            units[unit.group(1)] = tuple(re.findall(r"Descriptor_Unit_(\w+)", carriers.group(1) if carriers else ""))
        out[name] = units
    return out


class Unit(NamedTuple):
    """What the tests read of a unit in the game's unit database: its country, whether it is infantry, its UI role, its
    deck cost (Resource_CommandPoints) and its guided AT missiles as (AP, range in GRU)."""
    country: str
    infantry: bool
    role: str
    cost: int
    missiles: tuple[tuple[int, float], ...]


def unit_facts() -> dict[str, Unit]:
    """Every unit of the game's unit database by bare name (TacticalUnits.ndf, WeaponDescriptor.ndf and the
    ammunition, read as gates' readers read them): a missile is an ammunition of the unit's weapons that is a guided
    missile (EProjectileType/GuidedMissile) of the AP missile damage family, its AP that family's index."""
    archive = gates.unit_archive()
    ammo = {}
    for inner in gates.AMMO_DATABASE:
        for name, body in gates.top_blocks(gates.database_text(archive, inner)):
            arme = re.search(r"Arme\s*=\s*TDamageTypeRTTI\(Family=DamageFamily_ap_missile Index=(\d+)\)", body)
            reach = re.search(r"\bMaximumRangeGRU\s*=\s*([\d.]+)", body)
            if arme and reach and "EProjectileType/GuidedMissile" in body:
                ammo[name] = (int(arme.group(1)), float(reach.group(1)))
    weapons = {name: tuple(ammo[a] for a in re.findall(r"\bAmmunition\s*=\s*\$/GFX/Weapon/(\w+)", body) if a in ammo)
               for name, body in gates.top_blocks(gates.database_text(archive, gates.WEAPON_DATABASE))}
    out = {}
    for name, body in gates.top_blocks(gates.database_text(archive, gates.UNIT_DATABASE[0])):
        if not name.startswith("Descriptor_Unit_"):
            continue
        country, role = (re.search(rf"\b{k}\s*=\s*'(\w+)'", body) for k in ("MotherCountry", "UnitRole"))
        cost = re.search(r"Resource_CommandPoints\s*,\s*(\d+)", body)
        out[name.removeprefix("Descriptor_Unit_")] = Unit(
            country.group(1) if country else "", "TAcknowUnitType_Inf" in body, role.group(1) if role else "",
            int(cost.group(1)) if cost else 0,
            tuple(m for w in re.findall(r"\$/GFX/Weapon/(WeaponDescriptor_\w+)", body) for m in weapons.get(w, ())))
    return out


def supply_units() -> dict[str, bool]:
    """Every supply unit of the game's unit database (a unit with a TSupplyModuleDescriptor), by bare stock name ->
    whether it is a helicopter (THelicopterMovementModuleDescriptor): the mod SDK's TacticalUnits.ndf in the game's
    base.zip, where gates.unit_database reads the units."""
    archive = os.path.join(str(paths.game_dir()), *gates.UNIT_ARCHIVE.split("/"))
    with zipfile.ZipFile(archive) as z:
        text = z.read(gates.UNIT_DATABASE[0]).decode("utf-8", "replace")
    out = {}
    for block in re.split(r"(?m)^export ", text):
        m = re.match(r"Descriptor_Unit_(\w+) is TEntityDescriptor", block)
        if m and "TSupplyModuleDescriptor" in block:
            out[m.group(1)] = "THelicopterMovementModuleDescriptor" in block
    return out


# --------------------------------------------------------------------------- a step model of the script runtime

from modkit.ops import gates  # noqa: E402
from modkit.ops.bricks import g_seq, g_simul, g_wait  # noqa: E402
from modkit.ops.graph import Node, walk  # noqa: E402
from modkit.ops.script import FOREVER  # noqa: E402
from modkit.ops.testing import last, of, prop, subs, token  # noqa: E402

Steps = list[tuple[int, int]]          # (from this second on, the value)
JOUEUR, ALLIE, NATO = profile.CAMPS["Soviet"], profile.CAMPS["SovietAlly"], profile.CAMPS["NATO"]


def at(steps: Steps, t: int) -> int:
    """The value of `steps` at second `t` (0 before the first step)."""
    return next((v for t0, v in reversed(steps) if t0 <= t), 0)


class World:
    """What the model reads of the battle, by second:
    - `rings`: a circle's or a command zone's tag name -> what its detectors (or zone counts) find -> Steps. What is a
      camp export name (a constraint on that camp's team, alone or with unit types left out) or "cmd" (a constraint of
      unit types only: the command units);
    - `spent`: a group's name -> Steps of how many of its units are out of fuel or ammunition (UnitGroupWithFilter);
    - `captures`: second -> {zone tag name: camp export name}: zones taken by capture (every zone starts `owner`'s);
    - `groups`: a group's name -> Steps of its alive count, for groups the script does not fill itself;
    - `kills`: camp export name -> Steps of its GetNbKillsCamp count; `lost`: Steps of the player's GetNbLossCamp;
    - `answers`: a dialog token -> the buttons picked in turn (button 1 once none is left); a dialog takes no game time
      (it pauses the game);
    - `difficulty`: the level every ConditionOnGameDifficulty holds for (None: the game passed none);
    - `arrive_s`, `board_s`: how long a blocking order or a boarding takes (None: never)."""

    def __init__(self, rings: dict | None = None, captures: dict | None = None, owner: str = NATO,
                 groups: dict | None = None, kills: dict | None = None, lost: Steps | None = None,
                 answers: dict | None = None, difficulty: int | None = 1, arrive_s: int | None = None,
                 board_s: int | None = None, spent: dict | None = None) -> None:
        self.rings, self.captures, self.owner0 = rings or {}, captures or {}, owner
        self.groups, self.kills, self.lost = groups or {}, kills or {}, lost or []
        self.spent = spent or {}
        self.answers = {k: list(v) for k, v in (answers or {}).items()}
        self.difficulty, self.arrive_s, self.board_s = difficulty, arrive_s, board_s

    def detected(self, ring: str, what: str, t: int) -> int:
        return at(self.rings.get(ring, {}).get(what, []), t)


class Model:
    """A 1 s step model of the script runtime for the nodes Twin Strike uses ([[script-container-semantics]]): a
    Sequential runs its children in turn (NbExecutions times), a Simultaneous all until all finish, a Competition until
    its first finishes; a WaitDuration takes its seconds (rounded to whole ones), a WaitCondition until its condition
    holds; a camera cutscene takes its path's TimeInSecond and its hold (CutsceneWaitDuree). An objective resolves on
    the first tick its Condition (first) or ConditionEchec holds, then runs that action. TriggerEndGame, LockDeckUnit
    and a (blocking) Attack never finish. A timer reads its seconds left: its Duree until StartTimer, then down to 0.
    Instant actions are logged as (second, kind, ...); variables and script-filled groups are kept by name."""

    def __init__(self, world: World, values: dict[str, int] | None = None) -> None:
        self.world, self.t, self.vars, self.log = world, 0, dict(values or {}), []
        self.owner: dict[str, str] = {}
        self.groups: dict[str, int] = {}
        self.started: dict[str, int] = {}        # a timer's name -> the second StartTimer started it

    def value(self, v: Node) -> int:
        if v.cls in gates.UNIT_GROUPS:
            return self.groups[last(v)] if last(v) in self.groups else at(self.world.groups.get(last(v), []), self.t)
        if v.cls == "TGDVariableTimer":
            duree, start = prop(v, "Duree").v, self.started.get(last(v))
            return duree if start is None else max(0, duree - (self.t - start))
        return self.vars.get(last(v), 0)

    @staticmethod
    def finds(contrainte: Node) -> str:
        """What a detector's constraint finds (World.rings' keys)."""
        teams = [k for k in walk([contrainte]) if k.cls == "TGDContrainteOnUnitTeam"]
        return last(prop(teams[0], "Camp")) if teams else "cmd"

    def compare(self, left: int, op: Node) -> bool:
        other, value, kind = prop(op, "Variable"), prop(op, "Value"), prop(op, "OperatorType")
        right = self.value(other) if other is not None else value.v if value is not None else 0
        return gates.INT_OPERATORS[kind.v if kind is not None else 0](left, right)

    def cond(self, c: Node) -> bool:
        if c.cls == "TGDConditionAnd":
            return all(self.cond(k) for k in prop(c, "SousConditions"))
        if c.cls == "TGDConditionOr":
            return any(self.cond(k) for k in prop(c, "SousConditions"))
        if c.cls == "TGDConditionVariable":
            return self.compare(self.value(prop(c, "Variable")), prop(c, "Operator"))
        if c.cls == "TGDConditionTeamControleZone":
            return self.owner.get(last(prop(c, "Position")), self.world.owner0) == last(prop(c, "Camp"))
        if c.cls == "TGDConditionDetectUnitDansDetecteur":
            n = self.world.detected(last(prop(c, "Detecteur")), self.finds(prop(c, "Contrainte")), self.t)
            return self.compare(n, prop(c, "ComparaisonNbUnits"))
        if c.cls == "TGDConditionUnitDansZone":
            what = self.finds(prop(c, "Contrainte"))
            n = sum(self.world.detected(last(z), what, self.t) for z in prop(c, "Detecteurs"))
            return self.compare(n, prop(c, "ComparaisonNbUnits"))
        if c.cls == "TGDConditionUnitGroupWithFilter":
            return self.compare(at(self.world.spent.get(last(prop(c, "Variable")), []), self.t), prop(c, "Operator"))
        if c.cls == "TGDConditionOnGameDifficulty":
            level = prop(c, "Difficulty")
            return self.world.difficulty == (level.v if level is not None else 0)
        if c.cls == "TGDConditionPhase":
            return True
        raise AssertionError(f"the model has no {c.cls}")

    def note(self, *what: object) -> None:
        self.log.append((self.t, *what))

    @staticmethod
    def step(g: Iterator) -> bool:
        try:
            next(g)
            return True
        except StopIteration:
            return False

    def wait(self, seconds: int | None) -> Iterator[None]:
        k = 0
        while seconds is None or k < seconds:
            k += 1
            yield

    def run(self, n: Node) -> Iterator[None]:  # noqa: C901 - one branch per node class
        cls = n.cls.removeprefix("TGDDescriptor")
        if cls == "Sequential":
            runs, k = prop(n, "NbExecutions").v, 0
            while runs == FOREVER or k < runs:
                k += 1
                for kid in subs(n):
                    yield from self.run(kid)
        elif cls in ("Simultaneous", "Competition"):
            gens = [self.run(k) for k in subs(n)]
            while gens:
                left = [g for g in gens if self.step(g)]
                if cls == "Competition" and len(left) < len(gens):
                    for g in left:
                        g.close()
                    return
                gens = left
                if gens:
                    yield
        elif cls == "WaitDuration":
            yield from self.wait(round(prop(n, "Duree").v))
        elif cls == "WaitCondition":
            while not self.cond(prop(n, "Condition")):
                yield
        elif cls == "IfThenElse":
            branch = prop(n, "EffetIfTrue" if self.cond(prop(n, "Condition")) else "EffetIfFalse")
            if branch is not None:
                yield from self.run(branch)
        elif cls == "ModifieVariableInteger":
            name, other, value, kind = (prop(n, k) for k in ("Variable1", "Variable2", "Value", "ModificationType"))
            v = self.value(other) if other is not None else value.v if value is not None else 0
            old = self.vars.get(last(name), 0)
            ops = {None: lambda: v, 1: lambda: old + v, 2: lambda: old - v, 4: lambda: int(old / v)}
            self.vars[last(name)] = ops[kind.v if kind is not None else None]()
        elif cls == "SetVariableIntegerFromUnitGroup":
            self.vars[last(prop(n, "Variable"))] = self.value(prop(n, "Group"))
        elif cls == "ClearUnitGroup":
            self.groups[last(prop(n, "Group"))] = 0
        elif cls == "AddDetectedUnitsToUnitGroup":
            detector, name = prop(n, "Detector"), last(prop(n, "Group"))
            ring = last(prop(detector, "Detecteur"))
            found = self.world.detected(ring, self.finds(prop(detector, "Contrainte")), self.t)
            self.groups[name] = self.groups.get(name, 0) + found
            self.note("collect", name, ring, found)
        elif cls == "GetNbKillsCamp":
            self.vars[last(prop(n, "Variable"))] = at(self.world.kills.get(last(prop(n, "Camp")), []), self.t)
        elif cls == "GetNbLossCamp":
            self.vars[last(prop(n, "Variable"))] = at(self.world.lost, self.t)
        elif cls == "EncapsuleCutsceneDialogListWithMultipleChoice":
            (text,) = [k for k in walk([n]) if k.cls == "TGDDescriptorCutsceneTextComponent"]
            (dialog,) = prop(n, "DialogList")
            name = token(prop(text, "LocalizedText"))
            queue = self.world.answers.get(name, [])
            answer = queue.pop(0) if queue else 1
            self.vars[last(prop(dialog, "SelectedButton"))] = answer
            self.note("ask", name, answer)
        elif cls == "EncapsuleCutscene" and of(list(walk([n])), "CutsceneStartCameraPath"):
            # a camera cutscene (bricks.g_camera): logged as (path, from the current camera, its time, its hold)
            (cam,) = of(list(walk([n])), "CutsceneStartCameraPath")
            fly = prop(cam, "TimeInSecond").v if prop(cam, "TimeInSecond") is not None else 0.0
            hold = sum(prop(k, "WaitDuration").v for k in of(list(walk([n])), "CutsceneWaitDuree"))
            self.note("camera", prop(cam, "CameraPathName").text,
                      prop(cam, "StartFromCurrentCameraPosition") is not None, fly, hold)
            yield from self.wait(round(fly + hold))
        elif cls == "EncapsuleCutscene":
            self.note("dialog", *(token(prop(k, "LocalizedText")) for k in walk([n])
                                  if k.cls == "TGDDescriptorCutsceneTextComponent"))
        elif cls == "TriggerEndGame":
            winner = prop(n, "WinningAlliance")
            self.note("end", prop(n, "VictoryType").v, winner.v if winner is not None else None)
            yield from self.wait(None)
        elif cls == "LockDeckUnit":
            self.note("lock", *(prop(u, "Unit").path.rsplit("_Unit_", 1)[1] for u in prop(n, "Units")))
            yield from self.wait(None)
        elif cls == "AddUnitToDeck":
            self.note("card", prop(n, "TypeUnit").path.rsplit("_Unit_", 1)[1], prop(n, "NbUnitsToAdd").v)
        elif cls == "SetAmmo":
            self.note("ammo", [last(u) for u in prop(n, "Units")], prop(n, "MaxAmmoRatio") is not None)
        elif cls == "LaunchFXFireAndForgetOnPosition":
            self.note("fx", prop(n, "DatabaseName").text.rsplit("/", 1)[1], last(prop(n, "Position")))
        elif cls == "Fow":
            self.note("fow", bool(prop(n, "Fow").v))
        elif cls == "ChangeStress":
            self.note("stress", last(prop(n, "Group")), prop(n, "DamageType").v, prop(n, "Value").v)
        elif cls == "KillAllUnit":
            cause = prop(n, "DeathCause")
            self.note("kill", [last(g) for g in prop(n, "GroupList")], cause.v if cause is not None else None)
        elif cls == "GiveOrderStandard":
            blocking, at_ = prop(n, "Blocking") is not None, prop(n, "Position")
            self.note("order", last(prop(n, "Group")), prop(n, "OrderType").v, last(at_) if at_ else None, blocking)
            if blocking:
                yield from self.wait(self.world.arrive_s)
        elif cls == "Attack":
            # blocking, and the model never ends it: stock puts it last, and its wave's race retires it
            self.note("attack", last(prop(n, "Group")), last(prop(n, "Targets")))
            yield from self.wait(None)
        elif cls == "AddIgnoredUnitByScript":
            self.note("ignored", last(prop(n, "UnitGroup")))
        elif cls in ("GiveRessourceToTeam", "SetIncomeToTeam"):
            amount = prop(n, "Quantite")
            self.note("points" if cls == "GiveRessourceToTeam" else "income", amount.v if amount is not None else 0)
        elif cls == "LoadIntoTransporter":
            self.note("board", last(prop(n, "Group")), last(prop(n, "Targets")))
            yield from self.wait(self.world.board_s)
        elif cls == "CreateUnitOnPosition":
            self.note("create", last(prop(n, "Group")), prop(n, "NbUnit").v,
                      prop(n, "TypeUnit").path.rsplit("_Unit_", 1)[1], last(prop(n, "Position")))
        elif cls == "SpawnUnits":
            self.note("spawn", [last(u) for u in prop(n, "Units")])
        elif cls == "AddUnitGroupListToUnitGroup":
            self.note("union", last(prop(n, "GroupDestination")), [last(g) for g in prop(n, "ListGroupSource")])
        elif cls == "SetCommandZoneOwnerAndForceConvergence":
            zones = [last(z) for z in prop(n, "Positions")]
            self.owner |= dict.fromkeys(zones, last(prop(n, "Camp")))
            self.note("owner", last(prop(n, "Camp")), zones)
        elif cls == "LDHint":
            self.note("hint", token(prop(n, "Info")))
        elif cls == "StartTimer":
            timer = prop(n, "Timer")
            self.started[last(timer)] = self.t
            self.note("timer", last(timer), prop(timer, "Duree").v)
        elif cls == "GereObjectif":
            name, counters = token(prop(n, "ObjectiveText")), prop(n, "ListVariables") or []
            self.note("show", name, *([last(k) for k in prop(n, "ListTimersForEtiquetteText")]
                                      if prop(n, "ListTimersForEtiquetteText") else []))
            while True:
                for key, then, how in (("Condition", "ActionsReussi", "done"),
                                       ("ConditionEchec", "ActionsEchec", "failed")):
                    if prop(n, key) is not None and self.cond(prop(n, key)):
                        self.note(how, name, [self.value(v) for v in counters])
                        if prop(n, then) is not None:
                            yield from self.run(prop(n, then))
                        return
                yield
        else:
            self.note(cls)

    def play(self, root: Node, until: int) -> "Model":
        """Runs `root` from second 0 to `until` (or until it finishes)."""
        g = self.run(root)
        while self.t <= until:
            self.owner |= self.world.captures.get(self.t, {})
            if not self.step(g):
                break
            self.t += 1
        return self

    def when(self, *what: object) -> list[int]:
        """The seconds of the log entries that start with `what`."""
        return [e[0] for e in self.log if e[1:1 + len(what)] == what]

    def entries(self, kind: str) -> list[tuple]:
        """The log entries of `kind`, each (second, the rest)."""
        return [(e[0], *e[2:]) for e in self.log if e[1] == kind]


def beats_root(beats, ctx) -> Node:
    """The beats as script_frame runs them, the launch at second 0: Simultaneous[each load beat, Sequential[WaitDuration
    t, beat] for each timed beat]."""
    return g_simul([b.build(ctx) if b.t is None else g_seq([g_wait(b.t), b.build(ctx)]) for b in beats])
