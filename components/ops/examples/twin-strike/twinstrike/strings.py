"""Twin Strike's string table: every text the whole op shows, in English (modkit.ops.strings).

The keys are the three dictionaries the profile packs (twinstrike.profile.DICTIONARIES). ENGLISH is {dictionary:
{token: text}}; the frame shows only the menu, the camp names and the deploy hint, and the rest waits for the mission
(TS4b), which uses these tokens as they are. Menu tokens (ts_*: profile.MENU_RENAMES) are held to 30 UTF-16 units
(gate 1). A dialog takes no variables, so no dialog text holds %1..%9; hints and objectives may.

Simplified Chinese is a later build (design 7). The toolkit's table holds an English and a Chinese text per token and
requires both (modkit.ops.strings.check_parity: no empty Chinese), so until then STRINGS gives the SC dictionaries the
English text: plain ASCII, which the glyph gate admits, and the same placeholders and markup by construction.

Dialog buttons are stock in-game tokens (gates.INGAME_PROPS) [[dialog-button-ingame-dictionary]], so each dialog's
text says what its two buttons do (BUTTONS names them, with their English labels).
"""
from __future__ import annotations

from modkit.ops.strings import Table

# Each two-button dialog's buttons: stock INTERFACE_INGAME tokens, in all 8 languages (their English labels beside).
BUTTONS: dict[str, tuple[str, str]] = {
    "ts_dprep": ("ORD_AIARA", "ORD_HOLDF"),     # 'FIRE AT WILL', 'HOLD FIRE' (Open Door's spring)
    "ts_dfire1": ("TC_rkt", "HPD_ARTT"),        # 'ROCKET', 'ARTILLERY'
    "ts_dfire2": ("ZONEOTAN_A", "ZONEOTAN_B"),  # 'ALPHA', 'BRAVO'
    "ts_dplan": ("ORD_AIARA", "ORD_HOLDF"),     # 'FIRE AT WILL', 'HOLD FIRE'
    "ts_drel": ("UIP_YES", "UIP_NO"),           # 'Yes', 'No'
}

ENGLISH: dict[str, dict[str, str]] = {
    "SCENARIO_DEFINITION": {  # menu tokens (profile.MENU_RENAMES), each text at most 30 UTF-16 units
        "ts_name": "Operation Twin Strike",
        "ts_cname": "OPERATION TWIN STRIKE",
        "ts_headr": "Take the village. Hold it.",
        "ts_order": "Take it, hold it, decide.",
        "ts_recap": "Seize, hold, then decide",
        "ts_vic": "The road west is open.",
        "ts_def": "The village is lost.",
    },
    "Scripting/Dialog": {
        # design 5.4: the preparation fire, asked again every 2 minutes until fired or the village falls
        "ts_dprep": "#bold{DIVISION GUNS: PREPARATION FIRE?}\nThe 2S7M battery can put one salvo on the village. "
                    "Keep the assault out of it while the guns fire.\n"
                    "FIRE AT WILL: fire now.\n"
                    "HOLD FIRE: not yet. The guns ask again in 2 minutes.",
        # design 5.4: a fire mission, asked as two dialogs in turn (a dialog has two buttons): which guns, then where
        "ts_dfire1": "#bold{FIRE MISSION: WHICH GUNS?}\nROCKET: the BM-27 battery.\nARTILLERY: the 2S7M battery.",
        "ts_dfire2": "#bold{FIRE MISSION: WHERE?}\nALPHA: BOX W, on the west lane.\nBRAVO: BOX C, on the centre lane.",
        # design 5.4: the division fire plan, once per battle
        "ts_dplan": "#bold{DIVISION FIRE PLAN}\nEvery battery fires together, once, on whichever box holds more NATO "
                    "vehicles when it fires. There is one fire plan.\n"
                    "FIRE AT WILL: fire it now.\n"
                    "HOLD FIRE: hold it for later.",
        # design 5.6: the release dialog
        "ts_drel": "#bold{FRONT: NUCLEAR RELEASE?}\nA second NATO battalion is assembling south of the village. Front "
                   "offers one tactical nuclear strike on its assembly area.\n"
                   "Yes: request release.\n"
                   "No: fight it conventionally.",
        # design 5.8: the endings. A win names its grade and whether the strike was released or withheld.
        "ts_dtotr": "#bold{TOTAL VICTORY.}\nThe village is held, the first battalion broken and the second destroyed. "
                    "The strike was released.",
        "ts_dtotw": "#bold{TOTAL VICTORY.}\nThe village is held and both battalions are broken. The strike was "
                    "withheld: the second battalion was beaten in the field.",
        "ts_dmajr": "#bold{MAJOR VICTORY.}\nThe village is held. The strike was released.",
        "ts_dmajw": "#bold{MAJOR VICTORY.}\nThe village is held. The strike was withheld.",
        "ts_dminr": "#bold{MINOR VICTORY.}\nThe village is held, at the cost of more than half of your force. The "
                    "strike was released.",
        "ts_dminw": "#bold{MINOR VICTORY.}\nThe village is held, at the cost of more than half of your force. The "
                    "strike was withheld.",
        # design 4.2: the losses
        "ts_dfail": "#bold{DEFEAT.}\nThe detachment failed to take the village.",
        "ts_dlost": "#bold{DEFEAT.}\nNATO has retaken the village.",
        "ts_dempty": "#bold{DEFEAT.}\nThe village is lost: none of your units is left in it.",
    },
    "Scripting/Localization": {
        # the camps' PlayerName (profile.CAMP_TOKENS)
        "ts_csov": "Soviet Army",
        "ts_cart": "Division artillery",
        "ts_cnato": "NATO",
        "ts_cnato2": "NATO",
        # design 7: the start hint, shown until "Launch battle", names the village
        "ts_hdep": "DEPLOY in the north: the forward detachment of the 79th Guards Tank Division. Your objective is "
                   "the VILLAGE to the south, held by a West German company. Take it within 20 minutes of the launch.",
        # the difficulty the script read (modkit.ops.mission.difficulty: <hint><level>, <hint>9)
        "ts_hdif0": "DIFFICULTY: Easy.",
        "ts_hdif1": "DIFFICULTY: Medium.",
        "ts_hdif2": "DIFFICULTY: Hard.",
        "ts_hdif9": "DIFFICULTY: not received, so the battle plays Medium.",
        # phase 1 (design 4, 5.1, 5.4)
        "ts_hph1": "PHASE 1: take the VILLAGE. It falls when few of its defenders are left and one of your command "
                   "units is inside it.",
        "ts_hprep": "Division guns standing by. Keep the assault out of the village while the guns fire.",
        # phase 2 (design 5.2)
        "ts_hfall": "Village taken. Front releases the division's reserve and 4,000 points, with income from now on. "
                    "NATO recon is moving north.",
        # phase 3 (design 5.3, 5.4): every fire mission names its box; the fire plan announces its target
        "ts_hph3": "PHASE 3: a US armoured battalion counter-attacks up both lanes, its recon first. Fire missions are "
                   "ready on BOX W and BOX C.",
        "ts_hfirew": "Fire mission on BOX W.",
        "ts_hfirec": "Fire mission on BOX C.",
        "ts_hreload": "The batteries are reloading for the next fire mission.",
        "ts_hplanw": "Division fire plan on BOX W: every battery fires.",
        "ts_hplanc": "Division fire plan on BOX C: every battery fires.",
        "ts_hbn1": "The first battalion is broken.",
        "ts_hbreak": "Time is up for the first battalion: its survivors break off to the south.",
        # phase 4 (design 5.5, 5.6)
        "ts_hbn2": "A second NATO battalion is assembling. It attacks in 05:00.",
        "ts_hrel": "Release granted. Strike in 0:30. Keep clear of the marked zone.",
        "ts_hwith": "Release withheld. Fight the second battalion with what you have.",
        "ts_hatk": "The second battalion is attacking up both lanes.",
        "ts_hbn2b": "The second battalion is broken.",
        # phase 5 (design 5.8)
        "ts_hph5": "PHASE 5: hold the village to the end: 5 minutes after a strike; if you withheld it, until the "
                   "second battalion breaks, at most 20 minutes.",
        # the losses' warnings (design 4.2)
        "ts_hnato": "NATO is in the village. Throw them out within 60 seconds, or the battle is lost.",
        # shown 20 s into an empty streak (op.EMPTY_WARN_S): 2:40 of the 3 minutes are left, and P2 shows the clock
        "ts_hempty": "No Soviet unit in the village zone. Get one back in within 2:40, or the battle is lost.",
        # the objectives (design 4.1) and their pinned labels (design 7)
        "ts_p1": "TAKE THE VILLAGE: %1 enemy left in it",
        "ts_p1l": "Enemy left: %1",
        "ts_p2": "HOLD THE VILLAGE: never let NATO own it for 60 s, nor leave its zone empty for 180 s (NATO hold %1 s, "
                 "empty %2 s)",
        "ts_p2l": "NATO %1/60 s, empty %2/180 s",
        "ts_b1": "BREAK THE FIRST BATTALION: tanks destroyed %1 / %2. It breaks with 3 in 10 left.",
        "ts_b1l": "%1 / %2",
        "ts_b2": "DEAL WITH THE SECOND BATTALION: it attacks in %1 s",
        "ts_b2l": "Attacks in %1 s",
        "ts_b2n": "DEAL WITH THE SECOND BATTALION: %1 tanks left. It breaks with 3 in 10 left.",
        "ts_b2nl": "%1 tanks left",
        "ts_obw": "BOX W: the fire box on the west lane",
        "ts_obwl": "BOX W",
        "ts_obc": "BOX C: the fire box on the centre lane",
        "ts_obcl": "BOX C",
        "ts_ozone": "STRIKE ZONE: keep clear",
        "ts_ozonel": "STRIKE ZONE",
    },
}

# The packed table: the English text in both columns until the Chinese build (the module docstring).
STRINGS: Table = {dic: {token: (text, text) for token, text in tokens.items()} for dic, tokens in ENGLISH.items()}
