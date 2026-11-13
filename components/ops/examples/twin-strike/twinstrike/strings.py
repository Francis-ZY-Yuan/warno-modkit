"""Where Twin Strike's texts are, and its dialog buttons.

Every text the op shows is in its string table, TABLE (strings.toml beside this file: one section per token, one key
per language; modkit.ops.strings.load), in English (US) and Simplified Chinese (SC). The Chinese follows the
warno-localization skill, with TERM_SHEET (terms.toml) as the op's term table. Dialog buttons are stock in-game tokens
(gates.INGAME_PROPS) [[dialog-button-ingame-dictionary]], so each dialog's text names its two buttons (BUTTONS) by their
labels in its language.
"""
from __future__ import annotations

from pathlib import Path

from modkit.ops.models import Buttons

TABLE = Path(__file__).with_name("strings.toml")       # the string table: twinstrike.op packs load(TABLE)
TERM_SHEET = Path(__file__).with_name("terms.toml")    # the term table, the same shape: load(TERM_SHEET, Term)

# Each two-button dialog's buttons: stock INTERFACE_INGAME tokens, in all 8 languages (their English labels beside).
BUTTONS: dict[str, Buttons] = {
    "ts_dprep": Buttons("ORD_AIARA", "ORD_HOLDF"),     # 'FIRE AT WILL', 'HOLD FIRE' (Open Door's spring)
    "ts_dfire1": Buttons("TC_rkt", "HPD_ARTT"),        # 'ROCKET', 'ARTILLERY'
    "ts_dfire2": Buttons("ZONEOTAN_A", "ZONEOTAN_B"),  # 'ALPHA', 'BRAVO'
    "ts_dplan": Buttons("ORD_AIARA", "ORD_HOLDF"),     # 'FIRE AT WILL', 'HOLD FIRE'
    "ts_drel": Buttons("UIP_YES", "UIP_NO"),           # 'Yes', 'No'
}
