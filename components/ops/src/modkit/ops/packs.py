"""Writing and reading back a build: a scenario's packs, the read-back gate over them, and loose files under the mod
folder."""
from __future__ import annotations

import os
from typing import Iterable

from modkit.core import edat, ndfbin
from modkit.core.gates import check
from modkit.ops.files import file_chunks, long_path, stream_digest
from modkit.ops.graph import decode
from modkit.ops.items import Item


def write_packs(items: list[Item], mod_root: str, scenario: str, packs: Iterable[str]) -> dict[str, str]:
    """One <mod_root>/Scenarios/<scenario>_<pack>.dat per pack of `packs` that holds items, in that order (loose items
    are write_loose's). Returns {pack: path}."""
    out = {}
    for pack in packs:
        group = [it for it in items if it.pack == pack]
        if not group:
            continue
        path = os.path.join(mod_root, "Scenarios", f"{scenario}_{pack}.dat")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        edat.write_edat_stream(path, [(it.path, it.size, it.chunks) for it in group])
        out[pack] = path
    return out


def verify_packs(items: list[Item], pack_paths: dict[str, str]) -> None:
    """Read every written pack back: entry list, CRC32, payload hash, CNDF round trip."""
    for pack, path in pack_paths.items():
        want = {it.path: it for it in items if it.pack == pack}
        entries = edat.read_index(path)
        check(sorted(e.path for e in entries) == sorted(want), f"{path}: entry list differs from the plan")
        roundtrips = 0
        for e in entries:
            check(edat.verify_entry(path, e), f"{path}: CRC32 mismatch for {e.path}")
            size, digest = stream_digest(edat.iter_entry_chunks(path, e))
            check(size == want[e.path].size and digest == want[e.path].digest,
                  f"{path}: {e.path} differs from its planned payload")
            if pack in ("Definition", "Details"):
                raw = edat.read_entry(path, e)
                if raw[:4] == b"EUG0" and raw[8:12] == b"CNDF":
                    nb, _, image = decode(raw)
                    check(ndfbin.encode_image(nb) == image, f"{path}: {e.path} does not round-trip")
                    roundtrips += 1
        total = sum(e.size for e in entries)
        print(f"  {os.path.basename(path)}: {len(entries)} entries, {total:,} B payload, "
              f"{os.path.getsize(path):,} B file; all CRC32 + SHA-256 match"
              + (f"; {roundtrips} CNDF round-trip" if roundtrips else ""))


def write_loose(items: list[Item], mod_root: str) -> list[str]:
    """Loose (unpacked) files under the mod folder, e.g. a scenario video."""
    out = []
    for it in items:
        if it.pack != "Loose":
            continue
        dest = os.path.join(mod_root, *it.path.split("/"))
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(long_path(dest), "wb") as fh:
            for chunk in it.chunks():
                fh.write(chunk)
        size, digest = stream_digest(file_chunks(dest))
        check(size == it.size and digest == it.digest, f"{dest}: written file differs from its source")
        out.append(dest)
        print(f"  loose {it.path}: {size:,} B; SHA-256 matches {it.source}")
    return out
