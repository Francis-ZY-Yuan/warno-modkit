"""Byte-identical round-trip test for modkit.core.trad on stock WARNO .dic files (read only).

For every ``.dic`` in the fixed pack list checks ``write_dic(read_dic(x)) == x``, and that
``build_dic`` on the same tokens/texts (pool order, charset dropped) reproduces the file except, at
most, the tie order inside the charset row. Skips cleanly when the game folder is not configured.
"""
from __future__ import annotations

import unittest

from modkit.core import edat, paths, trad

PACKS = [
    "197351/201602/Scenarios/challenge_Survivors_Assets.dat",  # latest delta: holds no .dic
    "193438/197351/Scenarios/challenge_Survivors_Assets.dat",  # where Survivors' .dic live now
    "197351/201602/Scenarios/z_tuto_obusier_Assets.dat",
    "197351/201602/Scenarios/CampagneStrat_FuldaGap_Assets.dat",
    "193438/197351/Scenarios/challenge_TheHydra_Assets.dat",
]


def check_build(data: bytes) -> str | None:
    """None if build_dic matches exactly, 'charset-order' if only the charset ties differ."""
    entries = trad.read_dic(data)
    body = [(k, t) for k, t in entries if k != trad.CHARSET_KEY]
    mapping = {trad.token_unhash(k): t for k, t in body}
    if None in mapping or len(mapping) != len(body):
        raise AssertionError('non-token keys')
    rebuilt = trad.build_dic(mapping)
    if rebuilt == data:
        return None
    got = trad.read_dic(rebuilt)
    if got[:-1] != body or got[-1][0] != trad.CHARSET_KEY:
        raise AssertionError('build_dic changed rows, texts or pool order')
    # A handful of stock files leave '\' out of the charset; otherwise same characters.
    if sorted(got[-1][1].replace(chr(92), '')) != sorted(entries[-1][1].replace(chr(92), '')):
        raise AssertionError('build_dic charset has a different character set')
    return 'charset-order'


class TradRoundTrip(unittest.TestCase):
    @paths.skip_unless_game_dir("Data", "PC")
    def test_stock_dic_round_trip(self):
        data_pc = paths.game_dir() / "Data" / "PC"
        total = 0
        for rel in PACKS:
            pack = data_pc.joinpath(*rel.split("/"))
            try:
                index = edat.read_index(str(pack))
            except (edat.EdatError, OSError):
                continue  # pack not in this install
            for e in index:
                if not e.path.lower().endswith('.dic'):
                    continue
                total += 1
                with self.subTest(pack=rel, dic=e.path):
                    data = edat.read_entry(str(pack), e)
                    self.assertEqual(trad.write_dic(trad.read_dic(data)), data, 'round-trip differs')
                    check_build(data)
        if total == 0:
            self.skipTest("no .dic files found in the configured install")


if __name__ == "__main__":
    unittest.main()
