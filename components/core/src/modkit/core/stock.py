"""The declaration format for stock data: what a component reads from your own WARNO install.

Each component publishes ``STOCK_PATHS`` (in its package ``__init__``): a tuple of ``Stock`` entries naming a
path under the extraction folder (``paths.extracted_root()``) and how ``python -m modkit.core.setup extract``
produces it from the install. A new reader of stock data adds an entry; ``test_declared_paths_cover_every_reader``
holds every ``extracted_root()`` path join in the repository to the declared set.

How an entry is produced (``Stock.dest`` is the folder, or for ``index`` the file, below the extraction folder):

* ``packs``: the data archives (``.dat``, edat) named here, found through the install's index. Every revision of
  the install holds some of them. By default the archives are overlaid, the newest revision winning per inner path
  (the patch archives are deltas); two archives of one revision holding the same inner path are an error. With
  ``latest`` only the newest revision's archive is read (those archives are full copies, so inner paths a newer
  game dropped stay dropped).
* ``dest`` may end in a component with ``*``, with ``{}`` in the pack names standing for the same text: one folder per
  name found in the install (``scenarios/challenge_*`` with ``"{}_Details"``).
* ``include`` (fnmatch patterns on the inner path) and ``rename`` (a regular expression the whole inner path must
  match, and its replacement; a path that does not match is skipped) pick and place the files.
* ``archive``: a ``.zip`` below the game folder, extracted whole (or by ``include``).
* ``index``: the index of every archive of the install, as a TSV (``revision, archive, inner path, size``).
* ``provenance``: also write ``_provenance.tsv`` in ``dest`` (inner path, revision, archive, size, checksum ok).
* ``corpus``: False for files the installed game no longer loads (an earlier build's copy, kept for a reader that
  still names it): ``modkit.core.ndfrules`` leaves them out of the stock corpus it checks its table against.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Stock:
    dest: str
    packs: tuple[str, ...] = ()
    latest: bool = False
    include: tuple[str, ...] = ()
    rename: tuple[str, str] | None = None
    archive: str = ""
    index: bool = False
    provenance: bool = False
    corpus: bool = True
    why: str = field(default="", compare=False)  # for the reader of the declaration; two components declaring the same path agree

    def __post_init__(self):
        kinds = bool(self.packs) + bool(self.archive) + self.index
        if kinds != 1:
            raise ValueError(f"{self.dest}: give exactly one of packs, archive, index")
        if self.dest.startswith("/") or ".." in self.dest.split("/") or ":" in self.dest:
            raise ValueError(f"{self.dest}: dest must be a relative path below the extraction folder")
        if ("*" in self.dest) != any("{}" in p for p in self.packs):
            raise ValueError(f"{self.dest}: '*' in dest and '{{}}' in the pack names go together")
