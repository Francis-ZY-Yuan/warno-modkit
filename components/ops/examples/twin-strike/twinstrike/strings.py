"""Twin Strike's string table (modkit.ops.strings): every text the op shows, per token, in English (US) and Simplified
Chinese (SC); the other six languages get the English. The keys are the three dictionaries the profile packs
(twinstrike.profile.DICTIONARIES). A dialog takes no variables, so no dialog text holds %1..%9; hints and objectives
may.

The menu texts (SCENARIO_DEFINITION, profile.MENU_RENAMES) take the form of the stock Operations' own, and in each
language stock's length range for their element (test_twin_strike_frame.Strings): the briefing (ts_order) is the date
and time, the order number, a paragraph to the commander and four numbered points; the forces line (ts_headr) is the
chain of command on two lines; the text under the title (ts_recap) is three past-tense paragraphs; the outcomes (ts_vic,
ts_def) are one paragraph each. No markup. Only the two titles (profile.TITLE_TOKENS) are held to 30 UTF-16 units.

The Chinese follows the warno-localization skill, with TERMS as the op's term table. A native reader reviewed it; no
Chinese play has shown it yet. Dialog buttons are stock in-game tokens (gates.INGAME_PROPS)
[[dialog-button-ingame-dictionary]], so each dialog's text names its two buttons (BUTTONS) by their labels in its
language.
"""
from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.dataclasses import dataclass

from modkit.core.models import StringTable, Texts

# Each two-button dialog's buttons: stock INTERFACE_INGAME tokens, in all 8 languages (their English labels beside).
BUTTONS: dict[str, tuple[str, str]] = {
    "ts_dprep": ("ORD_AIARA", "ORD_HOLDF"),     # 'FIRE AT WILL', 'HOLD FIRE' (Open Door's spring)
    "ts_dfire1": ("TC_rkt", "HPD_ARTT"),        # 'ROCKET', 'ARTILLERY'
    "ts_dfire2": ("ZONEOTAN_A", "ZONEOTAN_B"),  # 'ALPHA', 'BRAVO'
    "ts_dplan": ("ORD_AIARA", "ORD_HOLDF"),     # 'FIRE AT WILL', 'HOLD FIRE'
    "ts_drel": ("UIP_YES", "UIP_NO"),           # 'Yes', 'No'
}


@dataclass(frozen=True)
class Rendering:
    """A term in one language: its text, and where the text comes from."""
    text: str
    source: str


class Term(BaseModel):
    """A term of TERMS (its English is the key) in each other language the op is in."""
    model_config = ConfigDict(frozen=True, extra="forbid")

    SC: Rendering


# The op's term table (warno-localization, step 2): English term -> its text and source in each language. "stock
# <DICTIONARY>" is the game's own text (python -m modkit.core.glossary term / token), "doctrine" PRC military
# terminology on the Soviet Army (the Russian original beside it), "term sheet" the maintainer's review, "ours" this
# op's own wording.
TERMS: dict[str, Term] = {
    # the dialog buttons (BUTTONS): their SC labels, verbatim
    "FIRE AT WILL": Term(SC=Rendering("自由射击", "stock INTERFACE_INGAME ORD_AIARA")),
    "HOLD FIRE": Term(SC=Rendering("不射击", "stock INTERFACE_INGAME ORD_HOLDF")),
    "ROCKET": Term(SC=Rendering("火箭弹", "stock INTERFACE_INGAME TC_rkt")),
    "ARTILLERY": Term(SC=Rendering("炮兵", "stock INTERFACE_INGAME HPD_ARTT")),
    "ALPHA": Term(SC=Rendering("ALPHA", "stock INTERFACE_INGAME ZONEOTAN_A")),
    "BRAVO": Term(SC=Rendering("BRAVO", "stock INTERFACE_INGAME ZONEOTAN_B")),
    "Yes": Term(SC=Rendering("是", "stock INTERFACE_INGAME UIP_YES")),
    "No": Term(SC=Rendering("否", "stock INTERFACE_INGAME UIP_NO")),
    # what the game's own screens show
    "TOTAL VICTORY": Term(SC=Rendering("大获全胜", "stock INTERFACE_INGAME, the end screen")),
    "MAJOR VICTORY": Term(SC=Rendering("酣畅大捷", "stock INTERFACE_INGAME, the end screen")),
    "MINOR VICTORY": Term(SC=Rendering("略占上风", "stock INTERFACE_INGAME, the end screen")),
    "DEFEAT": Term(SC=Rendering("败北", "stock INTERFACE_INGAME, the end screen's DEFEAT!")),
    "Easy": Term(SC=Rendering("简单", "stock INTERFACE_OUTGAME AB_GM_0, the difficulty")),
    "Medium": Term(SC=Rendering("标准", "stock INTERFACE_OUTGAME AB_GM_1, the difficulty")),
    "Hard": Term(SC=Rendering("困难", "stock INTERFACE_OUTGAME AB_GM_2, the difficulty")),
    "difficulty": Term(SC=Rendering("难度", "stock INTERFACE_INGAME, Select difficulty")),
    "Twin Cities (the twin towns)": Term(SC=Rendering("双城", "stock MAPS, the map's name")),
    "village": Term(SC=Rendering("村庄", "stock MAPS")),
    "launch (the battle)": Term(SC=Rendering("发起战斗", "stock INTERFACE_INGAME, LAUNCH BATTLE")),
    "deploy": Term(SC=Rendering("部署", "stock INTERFACE_INGAME, DEPLOYMENT PHASE")),
    "phase": Term(SC=Rendering("阶段", "stock INTERFACE_INGAME, DEPLOYMENT PHASE")),
    "objectives": Term(SC=Rendering("目标", "stock INTERFACE_INGAME, OBJECTIVE")),
    "command unit": Term(SC=Rendering("指挥单位", "stock UNITS")),
    "points": Term(SC=Rendering("点", "stock INTERFACE_INGAME, %1 points")),
    "income": Term(SC=Rendering("收入", "stock INTERFACE_INGAME, INCOME")),
    "stunned": Term(SC=Rendering("被压制", "stock INTERFACE_INGAME, the STUNNED! status")),
    "recon": Term(SC=Rendering("侦察", "stock UNITS")),
    "helicopters": Term(SC=Rendering("直升机", "stock INTERFACE_INGAME")),
    "NATO": Term(SC=Rendering("北约", "stock INTERFACE_INGAME")),
    "Soviet Army": Term(SC=Rendering("苏军", "stock, throughout")),
    "West German": Term(SC=Rendering("西德", "stock, throughout (term sheet C)")),
    "US": Term(SC=Rendering("美军", "stock, throughout")),
    "Panzergrenadier": Term(SC=Rendering("装甲掷弹兵", "stock UNITS")),
    # military wording: the doctrinal register
    "Operation Twin Strike": Term(SC=Rendering("双重突击行动", "ours: term sheet A")),
    "Comrade commander": Term(SC=Rendering("指挥员同志", "doctrine: товарищ командир")),
    "Combat Order No. 79/014": Term(SC=Rendering("战斗命令第79/014号", "doctrine: боевой приказ")),
    "79th Guards Tank Division": Term(SC=Rendering("近卫坦克第79师", "doctrine: 近卫, the arm, then 第N")),
    "forward detachment (and the division's vanguard)": Term(SC=Rendering("先遣支队", "doctrine: передовой отряд")),
    "Front": Term(SC=Rendering("方面军", "doctrine: фронт")),
    "division artillery (its name, its dialogs)": Term(SC=Rendering("师炮兵群", "doctrine: ДАГ")),
    "the division's guns (briefing prose)": Term(SC=Rendering("师炮兵", "doctrine: ДАГ, in prose")),
    "preparation fire": Term(SC=Rendering("冲击炮火准备", "doctrine: артподготовка атаки")),
    "fire mission": Term(SC=Rendering("射击任务", "doctrine: огневая задача")),
    "division fire plan": Term(SC=Rendering("师炮兵群火力急袭", "doctrine: огневой налёт")),
    "battery": Term(SC=Rendering("炮兵连", "doctrine: батарея")),
    "rocket battery": Term(SC=Rendering("火箭炮连", "doctrine: реактивная батарея")),
    "salvo": Term(SC=Rendering("齐射", "term sheet")),
    "blow": Term(SC=Rendering("突击", "doctrine: удар")),
    "attack (a NATO battalion's)": Term(SC=Rendering("冲击", "doctrine: атака")),
    "the assault (the player's assaulting force)": Term(SC=Rendering("冲击分队", "doctrine: атака")),
    "counter-attack": Term(SC=Rendering("反冲击", "doctrine: контратака")),
    "assembly area": Term(SC=Rendering("集结地域", "doctrine: район сосредоточения")),
    "assemble": Term(SC=Rendering("集结", "doctrine: сосредоточиваться")),
    "tactical nuclear strike": Term(SC=Rendering("战术核突击", "doctrine: ядерный удар (term sheet: 核)")),
    "the strike": Term(SC=Rendering("核突击", "doctrine: ядерный удар")),
    "nuclear release": Term(SC=Rendering("批准使用核武器", "doctrine, descriptive (term sheet 12)")),
    "request release": Term(SC=Rendering("请求批准", "doctrine, descriptive (term sheet 12)")),
    "release withheld (the player declines)": Term(SC=Rendering("不使用核武器", "term sheet 12")),
    "the division's reserve": Term(SC=Rendering("师预备队", "doctrine: резерв")),
    "seize": Term(SC=Rendering("夺取", "doctrine: захватить")),
    "hold": Term(SC=Rendering("扼守", "doctrine: удерживать")),
    "road junction": Term(SC=Rendering("道路枢纽", "doctrine: узел дорог")),
    "opens the road west": Term(SC=Rendering("打通西进道路", "term sheet 15")),
    "screen": Term(SC=Rendering("警戒", "doctrine: охранение")),
    "motor rifles": Term(SC=Rendering("摩步", "doctrine: мотострелки (摩托化步兵, short 摩步)")),
    "a battalion breaks, is broken": Term(SC=Rendering("丧失战斗力", "doctrine: потерять боеспособность")),
    "break off": Term(SC=Rendering("脱离接触", "ours")),
    "survivors (of a beaten unit)": Term(SC=Rendering("残部", "ours")),
    "US armoured task force": Term(SC=Rendering("美军坦克营特遣队", "term sheet 20")),
    "a US armoured battalion; a West German Panzer battalion": Term(SC=Rendering("坦克营", "term sheet 20")),
    "heavy air defence": Term(SC=Rendering("强大的防空火力", "term sheet 21, descriptive")),
    "engineers": Term(SC=Rendering("工兵", "doctrine: сапёры")),
    "scouts": Term(SC=Rendering("侦察兵", "doctrine: разведчики")),
    # weapons: a designation in Latin with a class word; a name that is only a nickname in stock's Chinese for it,
    # without its quotes (term sheet: 豹2A4)
    "tanks": Term(SC=Rendering("坦克", "stock UNITS")),
    "IFVs": Term(SC=Rendering("步兵战车", "stock UNITS")),
    "SP howitzers": Term(SC=Rendering("自行榴弹炮", "stock INTERFACE_INGAME")),
    "SPAAGs": Term(SC=Rendering("自行高炮", "stock UNITS")),
    "ATGM teams": Term(SC=Rendering("反坦克小组", "stock INTERFACE_OUTGAME")),
    "air defence": Term(SC=Rendering("防空", "stock UNITS")),
    "Leopard": Term(SC=Rendering("豹", "stock UNITS, term sheet")),
    "Marder": Term(SC=Rendering("黄鼠狼", "stock UNITS")),
    "Milan": Term(SC=Rendering("米兰", "stock UNITS")),
    "Shilka": Term(SC=Rendering("石勒喀", "stock UNITS")),
    "Tunguska": Term(SC=Rendering("通古斯卡", "stock UNITS")),
    "Osa": Term(SC=Rendering("黄蜂", "stock UNITS")),
    "Kub": Term(SC=Rendering("立方", "stock UNITS")),
    "Konkurs-M": Term(SC=Rendering("竞赛-M", "stock UNITS")),
    "Metis": Term(SC=Rendering("混血儿", "ours: the PRC name; stock has none")),
    # the op's own coinages
    "BOX W": Term(SC=Rendering("W区", "ours: term sheet B")),
    "BOX C": Term(SC=Rendering("C区", "ours: term sheet B")),
    "fire box": Term(SC=Rendering("火力区", "ours")),
    "the west lane": Term(SC=Rendering("西路", "ours")),
    "the centre lane": Term(SC=Rendering("中路", "ours")),
    "both lanes": Term(SC=Rendering("两路", "ours")),
    "STRIKE ZONE": Term(SC=Rendering("核突击区", "ours")),
    "HOLD ON (P3)": Term(SC=Rendering("坚守", "ours")),
    "BREAK (B1)": Term(SC=Rendering("击溃", "ours")),
    "DEAL WITH (B2)": Term(SC=Rendering("应对", "ours")),
    "FINISH (B2 after a strike)": Term(SC=Rendering("歼灭", "ours")),
    "the first battalion": Term(SC=Rendering("第一个营", "ours")),
    "the second battalion": Term(SC=Rendering("第二个营", "ours")),
    "fighter sweeps": Term(SC=Rendering("战斗机扫荡", "ours")),
    "Intel indicates hostile forces include (the briefing's point 3)": Term(SC=Rendering("敌情", "ours: an order's heading")),
}

STRINGS: StringTable = {
    "SCENARIO_DEFINITION": {  # the menu (profile.MENU_RENAMES), in stock's form (the module docstring)
        # the titles (profile.TITLE_TOKENS): MissionName and TitreObjectifs, each at most 30 UTF-16 units
        "ts_name": Texts(US="Operation Twin Strike", SC="双重突击行动"),
        "ts_cname": Texts(US="OPERATION TWIN STRIKE", SC="双重突击行动"),
        # TexteForcesEnPresence: the player's chain of command (design 6.1)
        "ts_headr": Texts(US="Soviet Army\n79th Guards Tank Division - Forward Detachment", SC="苏军\n近卫坦克第79师 - 先遣支队"),
        # TextePresentationScenario, the briefing: the story (design 1), the phases (4) and the forces (6.1, 6.3)
        "ts_order": Texts(
            US="July 4, 1989, 04:30 UTC\n"
               "Combat Order No. 79/014\n"
               "\n"
               "Comrade commander, two weeks into the war, the division's advance hangs on a road-junction "
               "village at the western edge of the twin towns. It opens the road west.\n"
               "\n"
               "1. Seize the village from the north. The division's guns can fire a preparation on it: keep your "
               "assault out while they fire.\n"
               "\n"
               "2. Once the village falls, the division's reserve is yours. Hold it against NATO's two blows: a "
               "US armoured battalion up both roads from the south, then a West German Panzer battalion "
               "assembling south of the village. Front offers release for one tactical nuclear strike on that "
               "assembly area. The decision is yours.\n"
               "\n"
               "3. Intel indicates hostile forces include:\n"
               "- A West German Panzergrenadier company in the village, with Marders, Leopard 1A5s and Milan "
               "teams.\n"
               "- A US armoured task force of M1A1HA Abrams and M2A2 Bradleys, with recon and heavy air defence.\n"
               "- A West German Panzer battalion of Leopard 2A4s and Marders.\n"
               "- NATO fighter sweeps.\n"
               "\n"
               "4. Under your command, the forward detachment of the 79th Guards Tank Division:\n"
               "- T-80BV tanks, motor rifles in BMP-2s, Konkurs-M teams in BTR-80s, engineers, scouts, Shilkas, "
               "2S1s and Ka-29s.\n"
               "- The division's 2S7M and BM-27 batteries, on call.\n"
               "- In reserve: T-80U tanks, Konkurs-M and Metis teams, Ka-50 and Mi-24V helicopters, Tunguska, Osa "
               "and Kub air defence.",
            SC="1989年7月4日 04:30 UTC\n"
               "战斗命令第79/014号\n"
               "\n"
               "指挥员同志，开战两周，全师推进系于双城西缘的道路枢纽村庄。夺取该村即可打通西进道路。\n"
               "\n"
               "1. 从北面夺取该村。师炮兵可实施冲击炮火准备，届时冲击分队须在村外。\n"
               "\n"
               "2. 夺取该村后，师预备队归您指挥。扼守该村，抗击北约两次突击：美军坦克营由南沿两路北上，西德坦克营"
               "随后在村南集结。方面军可批准对该集结地域实施一次战术核突击，由您决定。\n"
               "\n"
               "3. 敌情：\n"
               "- 村内：西德装甲掷弹兵连，有黄鼠狼步兵战车、豹1A5坦克和米兰反坦克小组。\n"
               "- 美军坦克营特遣队：M1A1HA坦克和M2A2步兵战车，另有侦察分队和强大的防空火力。\n"
               "- 西德坦克营：豹2A4坦克和黄鼠狼步兵战车。\n"
               "- 北约战斗机扫荡。\n"
               "\n"
               "4. 您指挥的近卫坦克第79师先遣支队：\n"
               "- T-80BV坦克、乘BMP-2步兵战车的摩步、乘BTR-80的竞赛-M反坦克小组、工兵、侦察兵、石勒喀自行高炮、"
               "2S1自行榴弹炮和Ka-29直升机。\n"
               "- 师炮兵2S7M炮兵连和BM-27火箭炮连随时待命。\n"
               "- 预备队：T-80U坦克，竞赛-M和混血儿反坦克小组，Ka-50和Mi-24V直升机，通古斯卡、黄蜂和立方防空系统。",
        ),
        # TexteObjectifs, under the title: the background (design 1), ending on the detachment's orders
        "ts_recap": Texts(
            US="Two weeks into the war, the Soviet advance was still rolling west. The next bound of the 79th "
               "Guards Tank Division hung on one road junction: a small village on the western edge of a pair of "
               "towns, whose road led west. The division sent its forward detachment to seize it.\n"
               "\n"
               "NATO could not let the road go. A US armoured battalion was ordered to counter-attack at once, up "
               "both roads from the south, behind a recon screen and under heavy air defence. A West German "
               "Panzer battalion was to assemble south of the village for a second, heavier blow.\n"
               "\n"
               "Soviet doctrine of the time planned nuclear strikes against exactly this: an enemy reserve "
               "concentrating to counter-attack. Front command stood ready to release one tactical nuclear strike "
               "on the assembly area. The forward detachment was to take the village, hold it against both blows, "
               "and decide whether to ask for the strike.",
            SC="开战两周后，苏军仍在向西推进。近卫坦克第79师的下一步推进取决于一个道路枢纽：双城西缘的一个小村庄，"
               "村中道路通向西方。该师派出先遣支队前去夺取。\n"
               "\n"
               "北约不能放弃这条道路。美军一个坦克营奉命立即从南面沿两条道路实施反冲击，以侦察分队担任警戒，并有"
               "强大的防空火力掩护。西德一个坦克营则将在村南集结，准备实施第二次、更猛烈的突击。\n"
               "\n"
               "按照当时的苏军条令，核突击针对的正是这种目标：集结准备反冲击的敌预备队。方面军已准备批准对该集结"
               "地域实施一次战术核突击。先遣支队的任务是夺取该村，扼守该村抗击两次突击，并决定是否请求核突击。",
        ),
        # VictoryOperationOutcomeText and DefeatOperationOutcomeText: true of every win and every loss (design 4.2, 5.8)
        "ts_vic": Texts(
            US="Comrade commander, the village is ours. Both NATO counter-attacks failed to retake it, and the road "
               "west lies open to the division. Front will remember the forward detachment that held the "
               "junction.\n",
            SC="指挥员同志，村庄已在我军手中。北约的两次反冲击都未能夺回该村，全师西进的道路已经打通。方面军不会忘记"
               "扼守这一道路枢纽的先遣支队。\n",
        ),
        "ts_def": Texts(
            US="Comrade commander, we do not hold the village, and the road west stays closed. The forward "
               "detachment was spent for nothing. Front will want to know why a Guards tank division's vanguard "
               "could not take and hold one village.\n",
            SC="指挥员同志，村庄不在我军手中，西进道路依然受阻。先遣支队白白消耗殆尽。方面军将追问：一个近卫坦克师的"
               "先遣支队，为何连一个村庄都夺不下、守不住。\n",
        ),
    },
    "Scripting/Dialog": {
        # design 5.4: the preparation fire, asked again every 2 minutes until fired or the village falls
        "ts_dprep": Texts(
            US="#bold{DIVISION GUNS: PREPARATION FIRE?}\nThe 2S7M battery can put one salvo on the village. "
               "Keep the assault out of it while the guns fire.\n"
               "FIRE AT WILL: fire now.\n"
               "HOLD FIRE: not yet. The guns ask again in 2 minutes.",
            SC="#bold{师炮兵群：实施冲击炮火准备？}\n2S7M炮兵连可对村庄实施一次齐射。射击期间，冲击分队须留在村外。\n"
               "自由射击：立即射击。\n"
               "不射击：暂不射击。师炮兵群2分钟后再次请示。",
        ),
        # design 5.4: a fire mission, asked as two dialogs in turn (a dialog has two buttons): which guns, then where
        "ts_dfire1": Texts(
            US="#bold{FIRE MISSION: WHICH GUNS?}\nROCKET: the BM-27 battery.\nARTILLERY: the 2S7M battery.",
            SC="#bold{射击任务：使用哪个炮兵连？}\n火箭弹：BM-27火箭炮连。\n炮兵：2S7M炮兵连。",
        ),
        "ts_dfire2": Texts(
            US="#bold{FIRE MISSION: WHERE?}\nALPHA: BOX W, on the west lane.\nBRAVO: BOX C, on the centre lane.",
            SC="#bold{射击任务：射向何处？}\nALPHA：W区，在西路。\nBRAVO：C区，在中路。",
        ),
        # design 5.4: the division fire plan, once per battle
        "ts_dplan": Texts(
            US="#bold{DIVISION FIRE PLAN}\nEvery battery fires together, once, on whichever box holds more NATO "
               "vehicles when it fires. There is one fire plan.\n"
               "FIRE AT WILL: fire it now.\n"
               "HOLD FIRE: hold it for later.",
            SC="#bold{师炮兵群火力急袭}\n所有炮兵连同时射击一次，目标为射击时北约车辆较多的火力区。火力急袭仅此一次。\n"
               "自由射击：立即实施。\n"
               "不射击：留待以后。",
        ),
        # design 5.6: the release dialog
        "ts_drel": Texts(
            US="#bold{FRONT: NUCLEAR RELEASE?}\nA second NATO battalion is assembling south of the village. Front "
               "offers one tactical nuclear strike on its assembly area.\n"
               "Yes: request release.\n"
               "No: fight it conventionally.",
            SC="#bold{方面军：请求批准使用核武器？}\n北约第二个营正在村南集结。方面军可批准对其集结地域实施一次战术核突击。\n"
               "是：请求批准。\n"
               "否：以常规手段作战。",
        ),
        # design 5.8: the endings. A win names its grade and whether the strike was released or withheld.
        "ts_dtotr": Texts(
            US="#bold{TOTAL VICTORY.}\nThe village is held and both battalions are broken. The strike was "
               "released, and you finished the second battalion.",
            SC="#bold{大获全胜。}\n村庄已守住，敌两个营均已丧失战斗力。已实施核突击，您歼灭了第二个营的残部。",
        ),
        "ts_dtotw": Texts(
            US="#bold{TOTAL VICTORY.}\nThe village is held and both battalions are broken. The strike was "
               "withheld: the second battalion was beaten in the field.",
            SC="#bold{大获全胜。}\n村庄已守住，敌两个营均已丧失战斗力。未实施核突击：第二个营是在战场上被击败的。",
        ),
        "ts_dmajr": Texts(
            US="#bold{MAJOR VICTORY.}\nThe village is held. The strike was released.",
            SC="#bold{酣畅大捷。}\n村庄已守住。已实施核突击。",
        ),
        "ts_dmajw": Texts(
            US="#bold{MAJOR VICTORY.}\nThe village is held. The strike was withheld.",
            SC="#bold{酣畅大捷。}\n村庄已守住。未实施核突击。",
        ),
        "ts_dminr": Texts(
            US="#bold{MINOR VICTORY.}\nThe village is held, at the cost of more than half of your force. The "
               "strike was released.",
            SC="#bold{略占上风。}\n村庄已守住，但您损失了一半以上的兵力。已实施核突击。",
        ),
        "ts_dminw": Texts(
            US="#bold{MINOR VICTORY.}\nThe village is held, at the cost of more than half of your force. The "
               "strike was withheld.",
            SC="#bold{略占上风。}\n村庄已守住，但您损失了一半以上的兵力。未实施核突击。",
        ),
        # design 4.2: the losses
        "ts_dfail": Texts(
            US="#bold{DEFEAT.}\nThe detachment failed to take the village.",
            SC="#bold{败北。}\n先遣支队未能夺取村庄。",
        ),
        "ts_dlost": Texts(US="#bold{DEFEAT.}\nNATO has retaken the village.", SC="#bold{败北。}\n北约已夺回村庄。"),
        "ts_dempty": Texts(
            US="#bold{DEFEAT.}\nThe village is lost: none of your units is left in it.",
            SC="#bold{败北。}\n村庄失守：村内已没有您的任何单位。",
        ),
    },
    "Scripting/Localization": {
        # the camps' PlayerName (profile.CAMP_TOKENS)
        "ts_csov": Texts(US="Soviet Army", SC="苏军"),
        "ts_cart": Texts(US="Division artillery", SC="师炮兵群"),
        "ts_cnato": Texts(US="NATO", SC="北约"),
        "ts_cnato2": Texts(US="NATO", SC="北约"),
        # design 7: the start hint, shown until "Launch battle", names the village
        "ts_hdep": Texts(
            US="DEPLOY in the north: the forward detachment of the 79th Guards Tank Division. Your objective is "
               "the VILLAGE to the south, held by a West German company. Take it within 20 minutes of the launch.",
            SC="部署于北面：近卫坦克第79师先遣支队。您的目标是南面的村庄，由西德一个连据守。须在发起战斗后20分钟内"
               "将其夺取。",
        ),
        # the difficulty the script read (modkit.ops.mission.difficulty: <hint><level>, <hint>9)
        "ts_hdif0": Texts(US="DIFFICULTY: Easy.", SC="难度：简单。"),
        "ts_hdif1": Texts(US="DIFFICULTY: Medium.", SC="难度：标准。"),
        "ts_hdif2": Texts(US="DIFFICULTY: Hard.", SC="难度：困难。"),
        "ts_hdif9": Texts(US="DIFFICULTY: not received, so the battle plays Medium.", SC="难度：未收到，本场战斗按标准进行。"),
        # phase 1 (design 4, 5.1, 5.4)
        "ts_hph1": Texts(
            US="PHASE 1: take the VILLAGE. It falls when few of its defenders are left and one of your command "
               "units is inside it.",
            SC="第一阶段：夺取村庄。当村内守军所剩无几，且您的一个指挥单位位于村内时，村庄即被攻占。",
        ),
        "ts_hprep": Texts(
            US="Division guns standing by. Keep the assault out of the village while the guns fire.",
            SC="师炮兵群已准备就绪。射击期间，冲击分队须留在村外。",
        ),
        # phase 2 (design 5.2)
        "ts_hfall": Texts(
            US="Village taken. Front releases the division's reserve and 8,000 points, with income from now on. "
               "NATO recon is moving north.",
            SC="村庄已夺取。方面军向您调拨师预备队和8,000点，此后持续提供收入。北约侦察分队正在向北移动。",
        ),
        # phase 3 (design 5.3, 5.4): every fire mission names its box; the fire plan announces its target
        "ts_hph3": Texts(
            US="PHASE 3: a US armoured battalion counter-attacks up both lanes, its recon first. Fire missions are "
               "ready on BOX W and BOX C.",
            SC="第三阶段：美军一个坦克营沿两路实施反冲击，侦察分队在前。W区和C区的射击任务已准备就绪。",
        ),
        "ts_hfirew": Texts(US="Fire mission on BOX W.", SC="对W区执行射击任务。"),
        "ts_hfirec": Texts(US="Fire mission on BOX C.", SC="对C区执行射击任务。"),
        "ts_hreload": Texts(US="The batteries are reloading for the next fire mission.", SC="各炮兵连正在为下一次射击任务装填弹药。"),
        "ts_hplanw": Texts(US="Division fire plan on BOX W: every battery fires.", SC="对W区实施师炮兵群火力急袭：所有炮兵连同时射击。"),
        "ts_hplanc": Texts(US="Division fire plan on BOX C: every battery fires.", SC="对C区实施师炮兵群火力急袭：所有炮兵连同时射击。"),
        "ts_hbn1": Texts(US="The first battalion is broken.", SC="第一个营已丧失战斗力。"),
        "ts_hbreak": Texts(
            US="Time is up for the first battalion: its survivors break off to the south.",
            SC="第一个营的时限已到：其残部向南脱离接触。",
        ),
        # phase 4 (design 5.5, 5.6)
        "ts_hbn2": Texts(
            US="A second NATO battalion is assembling. It attacks in 05:00.",
            SC="北约第二个营正在集结，05:00后发起冲击。",
        ),
        "ts_hrel": Texts(
            US="Release granted. Strike in 0:30. Keep clear of the marked zone.",
            SC="已批准使用核武器。0:30后实施核突击。部队须远离标出的区域。",
        ),
        "ts_hwith": Texts(
            US="Release withheld. Fight the second battalion with what you have.",
            SC="不使用核武器。以现有兵力抗击第二个营。",
        ),
        "ts_hatk": Texts(US="The second battalion is attacking up both lanes.", SC="第二个营正沿两路发起冲击。"),
        "ts_hbn2b": Texts(US="The second battalion is broken.", SC="第二个营已丧失战斗力。"),
        # after the strike's cutscene (design 5.6): what the strike left to do
        "ts_hstruck": Texts(
            US="The strike has gutted the second battalion. Its survivors are stunned and damaged: finish it.",
            SC="核突击已重创第二个营。其残部已受损并被压制：将其歼灭。",
        ),
        # phase 5 (design 5.8): P3 shows the end clock
        "ts_hph5": Texts(
            US="PHASE 5: hold the village to the end. HOLD ON, on the village and in the objectives, shows the time "
               "left; the battle ends then, or at once when NATO has no ground unit left.",
            SC="第五阶段：扼守村庄直至战斗结束。村庄上和目标列表中的“坚守”显示剩余时间；时间一到战斗即结束，若北约已"
               "无地面单位，则立即结束。",
        ),
        # the losses' warnings (design 4.2)
        "ts_hnato": Texts(
            US="NATO is in the village. Throw them out within 60 seconds, or the battle is lost.",
            SC="北约部队已进入村庄。须在60秒内将其逐出，否则战斗失败。",
        ),
        # shown 20 s into an empty streak (op.EMPTY_WARN_S): 2:40 of the 3 minutes are left, and P2 shows the clock
        "ts_hempty": Texts(
            US="No Soviet unit in the village zone. Get one back in within 2:40, or the battle is lost.",
            SC="村庄区域内已无苏军单位。须在2:40内让一个单位重新进入，否则战斗失败。",
        ),
        # the objectives (design 4.1) and their pinned labels (design 7)
        "ts_p1": Texts(US="TAKE THE VILLAGE: %1 enemy left in it", SC="夺取村庄：村内剩余敌军%1"),
        "ts_p1l": Texts(US="Enemy left: %1", SC="剩余敌军：%1"),
        "ts_p2": Texts(
            US="HOLD THE VILLAGE: never let NATO own it for 60 s, nor leave its zone empty for 180 s "
               "(NATO hold %1 s, empty %2 s)",
            SC="扼守村庄：不得让北约占领60秒，也不得让村庄区域空置180秒（北约占领%1秒，空置%2秒）",
        ),
        "ts_p2l": Texts(US="NATO %1/60 s, empty %2/180 s", SC="北约%1/60秒，空置%2/180秒"),
        "ts_b1": Texts(
            US="BREAK THE FIRST BATTALION: tanks destroyed %1 / %2. It breaks with 3 in 10 left.",
            SC="击溃第一个营：已摧毁坦克%1 / %2。坦克剩余十分之三时，该营即丧失战斗力。",
        ),
        "ts_b1l": Texts(US="%1 / %2", SC="%1 / %2"),
        "ts_b2": Texts(US="DEAL WITH THE SECOND BATTALION: it attacks in %1 s", SC="应对第二个营：%1秒后发起冲击"),
        "ts_b2l": Texts(US="Attacks in %1 s", SC="%1秒后发起冲击"),
        "ts_b2n": Texts(
            US="DEAL WITH THE SECOND BATTALION: %1 tanks left. It breaks with 3 in 10 left.",
            SC="应对第二个营：剩余坦克%1辆。坦克剩余十分之三时，该营即丧失战斗力。",
        ),
        "ts_b2nl": Texts(US="%1 tanks left", SC="剩余坦克%1辆"),
        "ts_b2f": Texts(
            US="FINISH THE SECOND BATTALION: %1 tanks left after the strike. It breaks with 3 in 10 left.",
            SC="歼灭第二个营：核突击后剩余坦克%1辆。坦克剩余十分之三时，该营即丧失战斗力。",
        ),
        "ts_b2fl": Texts(US="%1 tanks left", SC="剩余坦克%1辆"),
        # P3, phase 5's end clock (op.end_clock): the label's %1 is its running timer (op.END_CLOCK_S after a strike,
        # op.END_CLOCK_WITHHELD_S at most after withholding)
        "ts_p3r": Texts(
            US="HOLD ON FOR 5 MIN: then the battle ends. It ends at once when NATO has no ground unit left.",
            SC="坚守5分钟：随后战斗结束。若北约已无地面单位，战斗立即结束。",
        ),
        "ts_p3rl": Texts(US="Ends in %1", SC="%1后结束"),
        "ts_p3w": Texts(
            US="HOLD ON, 20 MIN AT MOST: the battle ends when the second battalion breaks, or at once when NATO has "
               "no ground unit left.",
            SC="坚守，最多20分钟：第二个营丧失战斗力时战斗结束；若北约已无地面单位，战斗立即结束。",
        ),
        "ts_p3wl": Texts(US="Ends in %1 at most", SC="最多%1后结束"),
        "ts_obw": Texts(US="BOX W: the fire box on the west lane", SC="W区：西路上的火力区"),
        "ts_obwl": Texts(US="BOX W", SC="W区"),
        "ts_obc": Texts(US="BOX C: the fire box on the centre lane", SC="C区：中路上的火力区"),
        "ts_obcl": Texts(US="BOX C", SC="C区"),
        "ts_ozone": Texts(US="STRIKE ZONE: keep clear", SC="核突击区：不要进入"),
        "ts_ozonel": Texts(US="STRIKE ZONE", SC="核突击区"),
    },
}
