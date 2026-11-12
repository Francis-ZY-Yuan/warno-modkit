#!/usr/bin/env python3
"""The ConfigHash of a ``.txn.tag`` (WARNO build 210942 and later), computed from the transaction it belongs to.

Since build 210942 every compiled transaction ``<name>.txn`` ships beside a ``<name>.txn.tag``, one ``TNDFTagFile``
holding a ``ConfigHash`` and its sources' hashes. Before the game loads a ``.txn`` it computes the ConfigHash of the
transaction that names it; when the tag holds another, it treats the ``.txn`` as stale and compiles the transaction
from its NDF sources instead, which a mod does not ship (the game stops with "NDF parsing error. Retry?" and "File
not found" for the transaction's first source). A source missing from the install does not count against the tag,
which is how stock loads without its sources.

The ConfigHash of a transaction (its BaseName, NameSpace, UsingNamespaces and Files) is::

    head  = combine(combine(SEED, name(BaseName)), name(NameSpace)), then combine(head, name(u)) for each UsingNamespace
    files = len(Files), then files = fmix64(path(f) ^ files) for each file, in order
    ConfigHash = head ^ files          (stored as a signed 64-bit integer)

with ``name(s)`` the low 31 bits of MetroHash64(s, seed 0), ``combine(s, v) = s ^ (v + GOLDEN + (s << 6) +
(s >> 2))`` and ``path(f)`` the fold, from ``PATH_SEED``, of ``combine(acc, fmix64(MetroHash64(c)))`` over the path's
components after its alias (``GameData:``, ``ScenariosData:``, ... are not hashed), the file name first and the
first folder last, then over the root of the path tree (``ROOT``). Directories, Public and GenerateCRC are not
hashed. ``check_stock`` (the test) reproduces every stock tag of an extraction whose transaction is known: each one
named by a ``TNDFTransaction`` in the stock data, and each scenario folder scanned by a
``TClusterMultipleNdfTransactions`` (``scan_transaction``).

CLI (run as ``python -m modkit.core.txntag ...``)::

    show <file.txn.tag>      the ConfigHash and the sources, one per line
"""
from __future__ import annotations

import argparse
import struct
import sys
from typing import NamedTuple, Sequence

from modkit.core import ndfbin

M = (1 << 64) - 1
K0, K1, K2, K3 = 0xD6D018F5, 0xA2AA033B, 0x62992FC1, 0x30BC5B29   # MetroHash64's constants
GOLDEN = 0x9E3779B9
SEED = 0x18775B986       # the head's first seed
PATH_SEED = 0x7DCF0      # a path's first seed
ROOT = 0x52706CAAD497DB23  # MetroHash64 of the path tree's root component, solved from 43 stock tags alike
TAG_CLASS = "TNDFTagFile"
TRANSACTION = "TNDFTransaction"
SCAN = "TClusterMultipleNdfTransactions"


def _rotr(x: int, r: int) -> int:
    return ((x >> r) | (x << (64 - r))) & M


def metro64(data: bytes, seed: int = 0) -> int:
    """MetroHash64 of `data` (J. Andrew Rogers' reference algorithm, little-endian reads)."""
    rd8, rd4, rd2 = (lambda p: struct.unpack_from("<Q", data, p)[0]), (lambda p: struct.unpack_from("<I", data, p)[0]), \
        (lambda p: struct.unpack_from("<H", data, p)[0])
    h = ((seed + K2) * K0) & M
    p, n = 0, len(data)
    if n >= 32:
        v = [h, h, h, h]
        while p <= n - 32:
            v[0] = (_rotr((v[0] + rd8(p) * K0) & M, 29) + v[2]) & M
            v[1] = (_rotr((v[1] + rd8(p + 8) * K1) & M, 29) + v[3]) & M
            v[2] = (_rotr((v[2] + rd8(p + 16) * K2) & M, 29) + v[0]) & M
            v[3] = (_rotr((v[3] + rd8(p + 24) * K3) & M, 29) + v[1]) & M
            p += 32
        v[2] ^= (_rotr((((v[0] + v[3]) * K0) + v[1]) & M, 37) * K1) & M
        v[3] ^= (_rotr((((v[1] + v[2]) * K1) + v[0]) & M, 37) * K0) & M
        v[0] ^= (_rotr((((v[0] + v[2]) * K0) + v[3]) & M, 37) * K1) & M
        v[1] ^= (_rotr((((v[1] + v[3]) * K1) + v[2]) & M, 37) * K0) & M
        h = (h + (v[0] ^ v[1])) & M
    if n - p >= 16:
        v0 = (_rotr((h + rd8(p) * K2) & M, 29) * K3) & M
        v1 = (_rotr((h + rd8(p + 8) * K2) & M, 29) * K3) & M
        p += 16
        v0 ^= (_rotr((v0 * K0) & M, 21) + v1) & M
        v1 ^= (_rotr((v1 * K3) & M, 21) + v0) & M
        h = (h + v1) & M
    for size, rd, r in ((8, rd8, 55), (4, rd4, 26), (2, rd2, 48), (1, lambda q: data[q], 37)):
        if n - p >= size:
            h = (h + rd(p) * K3) & M
            h ^= (_rotr(h, r) * K1) & M
            p += size
    h ^= _rotr(h, 28)
    h = (h * K0) & M
    h ^= _rotr(h, 29)
    return h


def fmix64(k: int) -> int:
    """MurmurHash3's 64-bit finalizer."""
    k ^= k >> 33
    k = (k * 0xFF51AFD7ED558CCD) & M
    k ^= k >> 33
    k = (k * 0xC4CEB9FE1A85EC53) & M
    return k ^ (k >> 33)


def combine(seed: int, value: int) -> int:
    """boost::hash_combine on 64 bits."""
    return (seed ^ ((value + GOLDEN + ((seed << 6) & M) + (seed >> 2)) & M)) & M


def name_hash(text: str) -> int:
    """A name's hash: the low 31 bits of MetroHash64."""
    return metro64(text.encode("latin-1")) & 0x7FFFFFFF


def path_hash(path: str) -> int:
    """A game path's hash: its components after the alias, file name first, then the tree's root."""
    rest = path.split(":/", 1)[1] if ":/" in path else path
    acc = PATH_SEED
    for part in reversed(rest.split("/")):
        acc = combine(acc, fmix64(metro64(part.encode("latin-1"))))
    return combine(acc, fmix64(ROOT))


class Transaction(NamedTuple):
    """What the ConfigHash covers of a transaction."""
    base_name: str
    namespace: str
    files: tuple[str, ...]
    using: tuple[str, ...] = ()


def config_hash(t: Transaction) -> int:
    """The ConfigHash of transaction `t`, as the signed 64-bit integer a tag stores."""
    head = combine(combine(SEED, name_hash(t.base_name)), name_hash(t.namespace))
    for u in t.using:
        head = combine(head, name_hash(u))
    files = len(t.files)
    for f in t.files:
        files = fmix64(path_hash(f) ^ files)
    h = head ^ files
    return h - (1 << 64) if h >> 63 else h


def _text(nb: ndfbin.NdfBin, v: ndfbin.Value | None) -> str:
    return nb.strings[v.v].decode("latin-1") if v is not None and v.tag in (0x07, 0x1C) else ""


def _texts(nb: ndfbin.NdfBin, v: ndfbin.Value | None) -> tuple[str, ...]:
    return tuple(_text(nb, x) for x in v.v) if v is not None and v.tag == 0x11 else ()


def transactions(nb: ndfbin.NdfBin) -> list[Transaction]:
    """Every TNDFTransaction of the decoded file `nb`, as the ConfigHash reads it."""
    out = []
    for ob in nb.objects:
        if nb.cname(ob.cls) == TRANSACTION:
            p = {nb.pname(pi): v for pi, v in ob.props}
            out.append(Transaction(_text(nb, p.get("BaseName")), _text(nb, p.get("NameSpace")),
                                   _texts(nb, p.get("Files")), _texts(nb, p.get("UsingNamespaces"))))
    return out


class Scan(NamedTuple):
    """A TClusterMultipleNdfTransactions: one transaction per folder of `dir_name` that holds `seek`."""
    dir_name: str
    base_name: str
    namespace: str
    files: tuple[str, ...]
    using: tuple[str, ...]
    seek_dir: str
    seek: str


def scans(nb: ndfbin.NdfBin) -> list[Scan]:
    """Every folder scan of the decoded file `nb` that seeks a file by name."""
    out = []
    for ob in nb.objects:
        if nb.cname(ob.cls) != SCAN:
            continue
        p = {nb.pname(pi): v for pi, v in ob.props}
        loader = p.get("Loader")
        if loader is None or loader.tag != 0x09 or loader.v.kind != ndfbin.REF_OBJECT:
            continue
        lp = {nb.pname(pi): v for pi, v in nb.objects[loader.v.index].props}
        if "FileNameToSeek" not in lp:
            continue
        out.append(Scan(_text(nb, p.get("DirName")), _text(nb, p.get("BaseName")),
                        _text(nb, p.get("TransactionsNameSpace")), _texts(nb, p.get("Files")),
                        _texts(nb, p.get("UsingNamespaces")), _text(nb, lp.get("Directory")),
                        _text(nb, lp.get("FileNameToSeek"))))
    return out


def scan_transaction(s: Scan, folder: str) -> Transaction:
    """The transaction scan `s` makes for `folder`: BaseName <DirName>/<folder>/<BaseName>, the found file first."""
    found = f"{s.seek_dir.rstrip('/')}/{folder}/{s.seek}"
    return Transaction(f"{s.dir_name}/{folder}/{s.base_name}", s.namespace, (found, *s.files), s.using)


def read_tag(raw: bytes) -> tuple[int, list[tuple[str, int]]]:
    """(ConfigHash, [(source path, its hash)]) of a .txn.tag."""
    nb, _, _ = ndfbin.decode(raw)
    if [nb.cname(ob.cls) for ob in nb.objects] != [TAG_CLASS]:
        raise ValueError(f"not one {TAG_CLASS}")
    p = {nb.pname(pi): v for pi, v in nb.objects[0].props}
    sources = p.get("SourceFileHashes")
    return p["ConfigHash"].v, [(_text(nb, k), v.v) for k, v in (sources.v if sources is not None else ())]


def main(argv: Sequence[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m modkit.core.txntag", description=__doc__.split("\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("show", help="the ConfigHash and the sources of a .txn.tag")
    p.add_argument("path")
    args = ap.parse_args(argv)
    with open(args.path, "rb") as fh:
        h, sources = read_tag(fh.read())
    print(f"ConfigHash {h}")
    for path, value in sources:
        print(f"{value}\t{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
