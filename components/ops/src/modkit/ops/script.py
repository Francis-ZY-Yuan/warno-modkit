"""GDScript blocks above the bricks: the HUD restore, the deployment phase, silent dialog voices, and a skeleton for
a hold-a-point mission.

A scenario cloned from a stock Operation copies a few objects of the template's own GDScript verbatim: its game rules
and the two HUD nodes around LoadingDone. ``Templates`` names them by object index (``graph.template_scalars``
specs). Comments name the stock object a shape comes from: S = Survivors, D = TheDieburgSalient,
B = BlackHorsesLastStand, R or DR = DelayedRetribution, HUR = HoldUntilRelieved (``S#296`` is object 296 of
Survivors' GDScript).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Mapping, Sequence

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.core.ndfbin import Value
from modkit.ops.bricks import (
    g_cmp, g_compete, g_dialog, g_hint, g_income, g_seq, g_simul, g_start_timer, g_timer, g_union, g_until, g_wait,
    g_zone_owner,
)
from modkit.ops.graph import TRUE, Imp, Node, Str, i32, loc, template_scalars, with_scalars

TemplateObject = tuple[int, str, tuple[str, ...]]  # (object index, class, props to drop): a template_scalars spec


@dataclass(frozen=True)
class Templates:
    """The template GDScript's objects whose scalars a generated script copies."""
    game_rules: TemplateObject   # TGDSpecificTacticalGameRules (S#114)
    hud_hide: TemplateObject     # the ForceDisplayUIElement that hides the HUD before LoadingDone (S#121)
    hud_restore: TemplateObject  # the ForceDisplayUIElement that brings it back (S#296)


# EGDBrickStatus (GameData/Gameplay/Constantes/Enumerations/GDBrickStatus.ndf). Stock writes Default by leaving the
# property out (the class default): HoldUntilRelieved's and Survivors' binary dumps carry
# ShowProdMenuSwitchMenuTypeButtons only where it is ForceHide.
BRICK_DEFAULT, BRICK_FORCE_HIDE, BRICK_FORCE_SHOW = 0, 1, 2
# The buy menu's switch between Groups mode and the factory tabs. S#296 force-hides it, as every stock HUD node that
# shows the buy menu does (14); its Default uses (29) are all in hide-all nodes.
PROD_MENU_SWITCH = "ShowProdMenuSwitchMenuTypeButtons"
# What a deployment phase shows when the HUD comes back: the launch button, the buy menu and the top bar.
DEPLOY_HUD = (("ShowLaunchBattleButton", BRICK_FORCE_SHOW), ("ShowProdMenu", BRICK_FORCE_SHOW),
              ("ShowTopBar", BRICK_FORCE_SHOW))
PRODUCTION_TYPE = 1       # ChangeProductionType EGDBrickProduction.Groups after the first ForceHideAll (HUR #97)
# EGDBrickProduction.Deck (GDBrickProduction.ndf: Deck 0, Groups 1): the buy menu's BATTLEGROUP view, every card of the
# deck by factory tab, the cards a script adds among them [[add-unit-to-deck]]. No stock node writes it (all 14 write
# Groups); a content asks for it through deploy_phase's production_type.
PRODUCTION_DECK = 0
DEPLOY_INITIAL_PHASE = 1  # GameRules InitialGamePhase 1 Deploiement (12 of 16 Operations, HUR; Survivors: 2 Command)
BATTLE_PHASE = 2          # TGDConditionPhase: "Launch battle" has ended the deployment phase (HUR #283/#333)
COMMAND_POINTS = 1        # SetRessourceForTeam ResourceType 1 = command points (HUR #254)
FOREVER = 0xFFFFFFFF      # NbExecutions of a loop that repeats until something else ends it (uint32 max)
SILENCE = "GameData:/Assets/Sounds/Solo/silence_5s.ogg"  # the stock silent clip, the voice of a text-only dialog


def hud_restore(tpl: ndfbin.NdfBin, templates: Templates, deploy: bool, prod_menu_switch: int
                ) -> list[tuple[str, Value]]:
    """The template's HUD restore (`templates.hud_restore`); with a deployment phase (`deploy`), DEPLOY_HUD too, new
    fields placed in the hide node's (stock) order. `prod_menu_switch`: BRICK_FORCE_HIDE keeps the template's
    force-hidden PROD_MENU_SWITCH (the buy menu stays in Groups mode); BRICK_DEFAULT leaves it out, as stock writes
    Default, so the player can switch. Never ForceShow: no stock use."""
    check(prod_menu_switch in (BRICK_DEFAULT, BRICK_FORCE_HIDE),
          f"{PROD_MENU_SWITCH} = {prod_menu_switch}: only Default ({BRICK_DEFAULT}) or ForceHide ({BRICK_FORCE_HIDE}); "
          f"no stock HUD node force-shows it")
    props = template_scalars(tpl, templates.hud_restore)
    check(getattr(dict(props).get(PROD_MENU_SWITCH), "v", None) == BRICK_FORCE_HIDE,
          f"template #{templates.hud_restore[0]} no longer force-hides {PROD_MENU_SWITCH}")
    if prod_menu_switch == BRICK_DEFAULT:
        props = [(name, value) for name, value in props if name != PROD_MENU_SWITCH]
    if not deploy:
        return props
    return with_scalars(props, DEPLOY_HUD, [n for n, _ in template_scalars(tpl, templates.hud_hide)])


@dataclass(frozen=True)
class DeployPhase:
    """A deployment phase's pieces, for a mission script to place. The deployment zones need no script: the game
    reads them from LevelDesign and out/DeploymentZone.ndfbin."""
    setup: tuple[Node, ...]  # Main, before LoadingDone: production type, points, income, command zone owner
    refresh: Node            # the player group's refresh loop (exported), to run beside the battle
    launched: Node           # waits for "Launch battle", raced against the hint if any
    game_rules: Node         # RootDescriptor GameRules, starting in the deployment phase


def deploy_phase(tpl: ndfbin.NdfBin, templates: Templates, joueur: Node, groupe_joueur: Node,
                 command_zones: Sequence[Node], *, points: int, income: int, hint: str | None, refresh_export: str,
                 refresh_s: float, production_type: int = PRODUCTION_TYPE) -> DeployPhase:
    """The game starts in the deployment phase with `points` command points and `income` per tick for `joueur`
    (bricks.g_income: an income of 0 is written as stock writes it, with no amount); it owns the command zones at the
    GdItems tags `command_zones` (none: no SetCommandZoneOwner); a loop exported at `refresh_export` adds every unit
    of `joueur`'s, bought ones included, to `groupe_joueur` every `refresh_s` seconds; and the battle waits for
    "Launch battle", raced against the LDHint `hint` (None: no hint). The buy menu opens on `production_type`
    (PRODUCTION_TYPE, stock's Groups view, unless a content asks for PRODUCTION_DECK). Pair it with
    hud_restore(..., deploy=True). DelayedRetribution likewise sets money and zone owners first in its Main."""
    setup = [Node("TGDDescriptorChangeProductionType", [("ProductionType", i32(production_type))]),       # HUR #97
             Node("TGDDescriptorSetRessourceForTeam", [("Camp", joueur), ("Quantite", i32(points)),
                                                       ("ResourceType", i32(COMMAND_POINTS))]),       # HUR #254
             g_income(joueur, income)]                                                                 # DR #109
    if command_zones:
        setup.append(g_zone_owner(joueur, command_zones))                                              # HUR #107
    refresh = g_seq([Node("TGDDescriptorAddAllCampUnitsToUnitGroup", [                                  # HUR #99
        ("Camp", joueur), ("ExcludeInProduction", TRUE), ("Group", groupe_joueur)]),
        g_wait(refresh_s)], runs=FOREVER, export=refresh_export)
    launched = g_until(Node("TGDConditionPhase", [("Phase", i32(BATTLE_PHASE))]))                      # HUR #283/#333
    if hint is not None:
        launched = g_compete([g_hint(hint, -1.0, "shint_op"), launched])                               # HUR #160
    rules = Node("TGDSpecificTacticalGameRules", with_scalars(template_scalars(tpl, templates.game_rules),
                                                              (("InitialGamePhase", DEPLOY_INITIAL_PHASE),)))
    return DeployPhase(tuple(setup), refresh, launched, rules)


def silent_cutscenes(tokens: Iterable[str]) -> Node:
    """TCutsceneDescriptorDatabase giving each dialog token the SILENCE clip (B#0, #1, #17, #33)."""
    return Node("TCutsceneDescriptorDatabase", [("CutsceneDescriptorList", [
        Node("TCutsceneDescriptor", [("Key", loc(token)), ("DefaultSoundDescriptor", Node("TSoundDescriptor", [
            ("SoundSettings", Imp("$/SoundSettings/Dialog_SoundSettings")),
            ("TheSoundStream", Node("TSoundStream", [("FileName", Str(SILENCE, 0x1C))])),
            ("Filter", i32(1))]))]) for token in tokens])])


def hold_script(tpl: ndfbin.NdfBin, templates: Templates, *, folder: str, camps: Sequence[Node],
                setup: Sequence[Node], tags: Mapping[str, Node], player_tags: Sequence[Node],
                hold_at: Node, hold_s: int, intro: str, objective: tuple[str, str], start_delay_s: float,
                parallel: Sequence[Node], variables: Sequence[Node], prod_menu_switch: int
                ) -> tuple[list[Node], list[Node]]:
    """A hold-a-point mission on the template's skeleton. Returns (roots, exports), exports in EXPR tree order.

    After `start_delay_s`, Main runs `setup` (the camps' SetDecks: S#117-#120), hides the HUD, ends loading, puts the
    units of `player_tags` in Groupe_Joueur, shows the `intro` dialog, restores the HUD, waits for a player unit and
    starts a `hold_s` timer; then the objective (`objective`: text and etiquette tokens, pinned at `hold_at`) runs
    beside the `parallel` nodes. The timer running out wins (MajorVictory); losing every unit of Groupe_Joueur fails.
    `prod_menu_switch` is the buy menu's switch at the HUD restore (hud_restore). `camps` are the RootDescriptor's
    CampList; `tags` the GdItems tags; `folder` (e.g. '$/GDScript/<Mod>') holds
    Main, Objective, the two endings and Variables/, where `variables` are exported between Groupe_Joueur and
    HoldTimer."""
    groupe_joueur = Node("TGDVariableUnitGroup", export=f"{folder}/Variables/Groupe_Joueur")                # S#148
    hold_timer = g_timer(hold_s, export=f"{folder}/Variables/HoldTimer")                                    # D#210

    def end_game(export: str, winner: int | None) -> Node:
        result = [("VictoryReason", i32(6)), ("VictoryType", i32(5))]          # ScriptDecided, MajorVictory
        result += [("WinningAlliance", i32(winner))] if winner is not None else []
        return g_seq([Node("TGDDescriptorForceDisplayUIElement", [("ForceHideAll", TRUE)]),
                      Node("TGDDescriptorTriggerEndGame", result)], export=export)

    success = end_game(f"{folder}/Mission_Success", None)                      # S#781 minus achievement
    fail = end_game(f"{folder}/Mission_Fail", 1)                               # S#778 minus obj_886
    text, etiquette = objective
    hold = Node("TGDDescriptorGereObjectif", [                                  # D#171 + S#295
        ("ActionsEchec", fail),
        ("ActionsReussi", success),
        ("BonusScoreMission", i32(50)),
        ("Condition", g_cmp(hold_timer, op=3)),                                 # D#208: timer <= 0
        ("ConditionEchec", g_cmp(groupe_joueur)),                               # S#728: count == 0
        ("LabelComponent", Str("Primary")),
        ("ListTimersForEtiquetteText", [hold_timer]),
        ("ObjectiveEtiquetteText", loc(etiquette)),
        ("ObjectiveText", loc(text)),
        ("Position", hold_at),
        ("ShowAddAnimation", TRUE),
        ("ShowBaseAnimation", TRUE),
        ("ShowEtiquette", TRUE),
    ], export=f"{folder}/Objective")
    main = g_seq([
        *setup,
        Node("TGDDescriptorForceDisplayUIElement", template_scalars(tpl, templates.hud_hide)),          # S#121
        Node("TGDDescriptorLoadingDone"),                                                               # S#122
        g_union(groupe_joueur, player_tags),                                                            # S#128
        g_dialog(intro),                                                                                # D#257/D#392
        Node("TGDDescriptorForceDisplayUIElement", hud_restore(tpl, templates, False, prod_menu_switch)),  # S#296
        g_until(g_cmp(groupe_joueur, 1, 2)),                                                            # R#340
        g_start_timer(hold_timer),                                                                      # D#271
        g_simul([hold, *parallel]),
    ], export=f"{folder}/Main")
    root = Node("TGDDescriptorLaunchEffetStandard", [                                                   # S#108
        ("CampList", list(camps)),
        ("EffetMap", g_seq([g_wait(start_delay_s), main])),                                             # S#113
        ("GameRules", Node("TGDSpecificTacticalGameRules", template_scalars(tpl, templates.game_rules))),  # S#114
    ], export="$/GDScript/RootDescriptor")
    exports = [root, *camps, *tags.values(), main, hold, *(nd for nd in parallel if nd.export), success, fail,
               groupe_joueur, *variables, hold_timer]
    return [silent_cutscenes([intro]), root], exports
