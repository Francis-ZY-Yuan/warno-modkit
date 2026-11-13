"""Open Door's string table: every text the mission shows, in English and Simplified Chinese (modkit.ops.strings).

The keys are the three dictionaries the profile packs (opendoor.profile.DICTIONARIES), each a {token: Texts(US=English,
SC=Chinese)} map; the build packs Chinese for SC and English for the other seven languages. Menu tokens (o3_*) are held
to 30 UTF-16 units, Chinese to the characters stock's own SC dictionaries use (gate 1). A dialog takes no variables,
so no dialog text holds %1..%9; hints and objectives do.

Where the obvious Chinese character is outside the stock SC set, the text says so beside it and uses another word.
"""
from __future__ import annotations

from modkit.core.models import StringTable, Texts

STRINGS: StringTable = {
    "SCENARIO_DEFINITION": {  # menu tokens (profile.MENU_RENAMES), each text at most 30 UTF-16 units
        "o3_name": Texts(US="Operation Open Door", SC="开门行动"),
        "o3_cname": Texts(US="OPERATION OPEN DOOR", SC="开门行动"),
        "o3_headr": Texts(US="We open the door.", SC="我们打开大门。"),
        "o3_order": Texts(US="Let them in, then shut it.", SC="放敌人进来，再关上大门。"),
        "o3_recap": Texts(US="Lure them in, shut the door", SC="引敌深入，关门围歼"),
        "o3_vic": Texts(US="The door is shut.", SC="大门已经关上。"),
        "o3_def": Texts(US="The trap failed.", SC="伏击失败。"),
    },
    "Scripting/Dialog": {  # the end funnel's; no variables, a dialog takes none
        "od_dtotal": Texts(US="#bold{TOTAL VICTORY.}\nThe door is shut. The enemy's forward detachment is destroyed or "
                              "in our hands, both necks hold and the anvil never gave way.",
                           SC="#bold{完全胜利。}\n大门已经关上。敌军先头部队已被消灭或被我军俘获，两处要道都在我军手中，ANVIL防线始终未破。"),
        # Major and Minor: true after the surrender and after the backstop, where the door was never shut
        "od_dmajor": Texts(US="#bold{MAJOR VICTORY.}\nA large part of the enemy's forward detachment is destroyed or "
                              "in our hands. Some of it got away.",
                           SC="#bold{重大胜利。}\n敌军先头部队的大部分已被消灭或被我军俘获，仍有一部分逃脱。"),
        "od_dminor": Texts(US="#bold{MINOR VICTORY.}\nToo few of the enemy's forward detachment were destroyed or "
                              "caught. Corps counts it a partial win.",
                           SC="#bold{小胜。}\n被消灭或俘获的敌军先头部队太少。军部只算作部分胜利。"),
        "od_danvil": Texts(US="#bold{DEFEAT.}\nSoviet forces hold the ANVIL. The pocket is open and the trap has "
                              "failed.",
                           SC="#bold{失败。}\n苏军占领了ANVIL。包围圈已经打开，伏击失败。"),
        "od_drear": Texts(US="#bold{DEFEAT.}\nSoviet vehicles have broken out through the rear exit. The breakthrough "
                             "has succeeded.",
                          SC="#bold{失败。}\n苏军车辆已从后方出口突破。突破成功。"),
        "od_dlost": Texts(US="#bold{DEFEAT.}\nYour whole force is destroyed.", SC="#bold{失败。}\n您的全部部队已被消灭。"),
        # P1 failed: PL BLUE still held at H+12. H+12's one announcement (tiered: the towns' tiers close; fixed, _f:
        # only their zones turn red)
        "od_dheld": Texts(US="#bold{PL BLUE HELD TOO LONG.}\nIt is H+12 and the towns are still ours. Corps gives up "
                             "PL BLUE anyway: Town NE, Village E and Town SE are the Soviets' now, and reinforcements "
                             "no longer arrive there. The door is open: the Soviet main body is on its way.",
                          SC="#bold{PL BLUE坚守过久。}\n已到H+12，城镇仍在我军手中。军部仍然下令放弃PL BLUE：Town NE、Village E"
                             "和Town SE现已归苏军所有，增援部队不再从那里到达。大门已经打开：苏军主力已经出发。"),
        "od_dheld_f": Texts(US="#bold{PL BLUE HELD TOO LONG.}\nIt is H+12 and the towns are still ours. Corps gives up "
                               "PL BLUE anyway: Town NE, Village E and Town SE are the Soviets' now. The door is open: "
                               "the Soviet main body is on its way.",
                            SC="#bold{PL BLUE坚守过久。}\n已到H+12，城镇仍在我军手中。军部仍然下令放弃PL BLUE：Town NE、"
                               "Village E和Town SE现已归苏军所有。大门已经打开：苏军主力已经出发。"),
        # the spring (design 5.2): the re-asked choice (buttons: stock INGAME FIRE AT WILL / HOLD FIRE), and Corps
        # springing it at H+30 or at the anvil
        "od_dspring": Texts(US="#bold{CORPS: SPRING THE TRAP NOW?}\nThe Soviet main body is in the sack.\nFIRE AT "
                               "WILL: spring it now.\nHOLD FIRE: wait. Corps asks again in 2 minutes, and springs it "
                               "anyway at H+30 or when the Soviets reach the ANVIL.",
                            SC="#bold{军部：现在发动伏击？}\n苏军主力已经进入包围圈。\n"
                               "自由射击：现在发动。\n"
                               "不射击：等待。军部2分钟后再次提问；到H+30或苏军到达ANVIL时，军部仍将发动伏击。"),
        "od_dauto": Texts(US="#bold{CORPS SPRINGS THE TRAP.}\nCorps will not wait any longer: it is H+30, or the "
                             "Soviets have reached the ANVIL. The trap is sprung now.",
                          SC="#bold{军部发动伏击。}\n军部不再等待：已到H+30，或苏军已到达ANVIL。现在发动伏击。"),
        # phase 3: the codeword at the spring (design 5.3; 钳 is outside the stock SC set: 翼, wing), and the backstop
        "od_dcode": Texts(US="#bold{CODEWORD: SHUT THE DOOR.}\nThe trap is sprung. The north jaw, an M1A1HA company "
                             "team, is yours at RESERVE N, and the south jaw, a Leopard 2A4 company, at HIDE S. Drive "
                             "them onto NECK MID and NECK S and seal both necks.\nCorps adds M1A1HA, Leopard 2A4 and "
                             "OH-58D cards to your deck, and the A-10s are cleared to fly.",
                          SC="#bold{暗号：关上大门。}\n伏击已经发动。北翼（一个M1A1HA连级战斗群）已在RESERVE N归您指挥，南翼"
                             "（一个Leopard 2A4坦克连）在HIDE S。把它们开往NECK MID和NECK S，封锁两处要道。\n军部向您的卡组"
                             "加入M1A1HA、Leopard 2A4和OH-58D，A-10也获准出动。"),
        "od_dback": Texts(US="#bold{CORPS ENDS THE BATTLE.}\nIt is 25 minutes since the trap was sprung, and the door "
                             "is still open: NECK MID and NECK S were never both sealed. Corps calls the battle off. "
                             "Only the Soviet vehicles destroyed count; the pocket captured none.",
                          SC="#bold{军部结束战斗。}\n伏击发动已过25分钟，大门仍然敞开：NECK MID和NECK S始终未被同时封锁。"
                             "军部取消了这场战斗。只计算被摧毁的苏军车辆，包围圈没有俘获任何车辆。"),
    },
    "Scripting/Localization": {
        "od_cnato": Texts(US="NATO", SC="北约"),
        "od_cdecoy": Texts(US="NATO decoys", SC="北约佯动部队"),  # 诱饵 (decoy) is outside the stock SC set
        "od_cddr": Texts(US="NVA", SC="东德军"),
        "od_csov": Texts(US="Soviet Army", SC="苏军"),
        # up until "Launch battle", the one hint of the deployment phase (砧 is outside the stock SC set: ANVIL
        # instead). The Soviet cards by unit and count (op.SOVIET_CARDS), not by tab: the buy menu opens in Groups
        # mode, and where it shows a card with no group is unread (the op lets the player switch it to the factory
        # tabs: op.PROD_MENU_SWITCH)
        "od_hdep": Texts(US="DEPLOY (6,000 points): the rearguard in Town NE, Village E and Town SE, a force on "
                            "SHOULDER, the ANVIL in the west. Your deck holds captured Soviet equipment: two T-80U "
                            "tanks, two Ka-50 helicopters and two TOS-1 rocket launchers.",
                         SC="部署（6,000点）：后卫部署在Town NE、Village E和Town SE，一支部队守住SHOULDER，ANVIL部队部署在西侧。"
                            "您的卡组中有缴获的苏军装备：两辆T-80U坦克、两架Ka-50直升机和两辆TOS-1火箭炮。"),
        # the difficulty the script read, op.DIFF_HINT_T after the launch
        "od_hdif0": Texts(US="DIFFICULTY: Easy.", SC="难度：简单。"),
        "od_hdif1": Texts(US="DIFFICULTY: Medium.", SC="难度：中等。"),
        "od_hdif2": Texts(US="DIFFICULTY: Hard.", SC="难度：困难。"),
        # P2, a fail-only objective
        "od_p2": Texts(US="HOLD THE ANVIL: at all costs", SC="守住ANVIL：不惜一切代价"),
        "od_p2l": Texts(US="Hold the ANVIL", SC="守住ANVIL"),
        "od_hdif9": Texts(US="DIFFICULTY: not received, so the mission plays Medium.", SC="难度：未收到，任务按中等进行。"),
        # phase 1: the phase hint, P1 and B1 (B1 promises nothing more), the captured T-80U
        "od_hph1": Texts(US="PHASE 1: at H+1 the Soviet first echelon attacks Town NE, Village E and Town SE. Make "
                            "them pay, then give up the towns by H+12 and fall back west.",
                         SC="第一阶段：H+1时苏军第一梯队将进攻Town NE、Village E和Town SE。让敌人付出代价，然后在H+12前放弃"
                            "这些城镇，向西撤退。"),
        "od_p1": Texts(US="SELL THE RETREAT: fight on PL BLUE, then give it up by H+12 (%1 min left)",
                       SC="佯装撤退：在PL BLUE作战，并在H+12前放弃（剩余%1分钟）"),
        "od_p1l": Texts(US="Give up by H+12: %1 min", SC="H+12前放弃：%1分钟"),
        "od_b1": Texts(US="MAKE THEM PAY: destroy %1 / %2 first-echelon units before PL BLUE falls",
                       SC="让敌人付出代价：在PL BLUE失守前消灭%1 / %2个第一梯队单位"),
        "od_b1l": Texts(US="%1 / %2", SC="%1 / %2"),
        "od_hcapt": Texts(US="CAPTURED: a Soviet T-80U, taken intact, is yours. It waits on the road west of Village "
                             "E.",
                          SC="缴获：一辆完好的苏军T-80U归您指挥，位于Village E以西的道路上。"),
        # a town falls (tiered: its tier closes; fixed, _f: only its zone turns red)
        "od_hfne": Texts(US="Town NE has fallen to the Soviets: reinforcements no longer arrive there.",
                         SC="Town NE已落入苏军之手：增援部队不再从那里到达。"),
        "od_hfve": Texts(US="Village E has fallen to the Soviets: reinforcements no longer arrive there.",
                         SC="Village E已落入苏军之手：增援部队不再从那里到达。"),
        "od_hfse": Texts(US="Town SE has fallen to the Soviets: reinforcements no longer arrive there.",
                         SC="Town SE已落入苏军之手：增援部队不再从那里到达。"),
        "od_hfne_f": Texts(US="Town NE has fallen to the Soviets.", SC="Town NE已落入苏军之手。"),
        "od_hfve_f": Texts(US="Village E has fallen to the Soviets.", SC="Village E已落入苏军之手。"),
        "od_hfse_f": Texts(US="Town SE has fallen to the Soviets.", SC="Town SE已落入苏军之手。"),
        # the release when PL BLUE fell (at H+12, P1's dialog od_dheld announces it instead)
        "od_hopen": Texts(US="PL BLUE has fallen: the door is open. The Soviet main body is on its way.",
                          SC="PL BLUE已经失守：大门已经打开。苏军主力已经出发。"),
        # phase 2: the phase hint with B6's stand (design 5.1; B6 promises nothing more), P4, B6, and the PL GREEN
        # window's close (tiered: the necks' tiers close; fixed, _f: only their zones turn red)
        "od_hph2": Texts(US="PHASE 2: the Soviet main body comes down the passage and the defile. Make one more stand "
                            "at NECK MID or NECK S, then break contact and fall back on the ANVIL. Standing longer "
                            "earns nothing more.",
                         SC="第二阶段：苏军主力正沿通道和山谷推进。在NECK MID或NECK S再坚守一次，然后脱离接触，撤往ANVIL。"
                            "坚守更久不会有更多收获。"),
        "od_p4": Texts(US="LET THEM IN: Soviet vehicles in the sack %1 / %2", SC="放敌深入：包围圈内的苏军车辆 %1 / %2"),
        "od_p4l": Texts(US="%1 / %2", SC="%1 / %2"),
        "od_b6": Texts(US="MAKE A STAND AT PL GREEN: hold a neck village with Soviets at its approach for %1 / %2 s",
                       SC="在PL GREEN坚守：在苏军接近时守住一处要道村庄 %1 / %2 秒"),
        "od_b6l": Texts(US="%1 / %2 s", SC="%1 / %2 秒"),
        "od_hgrn": Texts(US="PL GREEN is over: break contact and fall back on the ANVIL. NECK MID and NECK S are the "
                            "Soviets' now: reinforcements arrive only at the ANVIL.",
                         SC="PL GREEN坚守结束：脱离接触，撤往ANVIL。NECK MID和NECK S现已归苏军所有：增援部队只从ANVIL到达。"),
        "od_hgrn_f": Texts(US="PL GREEN is over: break contact and fall back on the ANVIL. NECK MID and NECK S are the "
                              "Soviets' now.",
                           SC="PL GREEN坚守结束：脱离接触，撤往ANVIL。NECK MID和NECK S现已归苏军所有。"),
        # the same close when the spring ends PL GREEN: the necks are P5's to seal again
        "od_hgrs": Texts(US="The trap is sprung: NECK MID and NECK S are the Soviets' now. Reinforcements arrive only "
                            "at the ANVIL until you seal a neck again.",
                         SC="伏击已经发动：NECK MID和NECK S现已归苏军所有。在您重新封锁一处要道之前，增援部队只从ANVIL到达。"),
        "od_hgrs_f": Texts(US="The trap is sprung: NECK MID and NECK S are the Soviets' now.",
                           SC="伏击已经发动：NECK MID和NECK S现已归苏军所有。"),
        # phase 3: the jaw hint, P5 per neck (the "%1 / 30 s": op.SEAL_HOLD_S), and each seal (tiered: its tier
        # reopens; fixed, _f: only its zone turns blue)
        "od_hjaw": Texts(US="SHUT THE DOOR: drive the M1A1HA from RESERVE N onto NECK MID and the Leopards from HIDE S "
                            "onto NECK S. A neck is sealed once your units hold it with no Soviet unit inside for 30 "
                            "s.",
                         SC="关上大门：把M1A1HA从RESERVE N开往NECK MID，把Leopard坦克从HIDE S开往NECK S。您的部队占住一处要道、"
                            "且其中30秒内没有苏军单位，该要道即被封锁。"),
        "od_p5m": Texts(US="SHUT THE DOOR: seal NECK MID, your units in it and no Soviet unit, %1 / 30 s",
                        SC="关上大门：封锁NECK MID，您的部队在内且无苏军单位 %1 / 30 秒"),
        "od_p5ml": Texts(US="Seal NECK MID: %1 / 30 s", SC="封锁NECK MID：%1 / 30 秒"),
        "od_p5s": Texts(US="SHUT THE DOOR: seal NECK S, your units in it and no Soviet unit, %1 / 30 s",
                        SC="关上大门：封锁NECK S，您的部队在内且无苏军单位 %1 / 30 秒"),
        "od_p5sl": Texts(US="Seal NECK S: %1 / 30 s", SC="封锁NECK S：%1 / 30 秒"),
        "od_hsm": Texts(US="NECK MID is sealed: it is ours again, and reinforcements arrive there again.",
                        SC="NECK MID已被封锁：要道重归我军所有，增援部队重新从那里到达。"),
        "od_hsm_f": Texts(US="NECK MID is sealed: it is ours again.", SC="NECK MID已被封锁：要道重归我军所有。"),
        "od_hss": Texts(US="NECK S is sealed: it is ours again, and reinforcements arrive there again.",
                        SC="NECK S已被封锁：要道重归我军所有，增援部队重新从那里到达。"),
        "od_hss_f": Texts(US="NECK S is sealed: it is ours again.", SC="NECK S已被封锁：要道重归我军所有。"),
        # phase 4: P6 (design 4.1, with the surrender point: design 5.4's share and T_hold) and the catch (5.5)
        "od_p6": Texts(US="REDUCE THE POCKET: %1 Soviet vehicles left in the pocket; it gives up at %2, or 15 min "
                          "after the seal",
                       SC="压缩包围圈：包围圈内剩余苏军车辆%1辆；降至%2辆或封锁15分钟后，敌军投降"),
        "od_p6l": Texts(US="%1 left, gives up at %2", SC="剩余%1，%2时投降"),
        "od_catch": Texts(US="THE CATCH: %1 / %2 main-body vehicles destroyed or captured",
                          SC="战果：苏军主力车辆被消灭或俘获 %1 / %2"),
        "od_catchl": Texts(US="%1 / %2", SC="%1 / %2"),
    },
}
