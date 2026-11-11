"""The generated navigation. Nothing here is edited by hand; ``render`` rewrites it from the records.

The map lives in the ``knowledge/`` folder at the root it is rendered for:

* ``README.md`` (L0, the one page to read first): where each kind of question starts, the topics with their
  mechanism counts, the components, and where the guide to writing records is;
* ``topics/<topic>.md`` (L1), one per declared topic that some mechanism carries: its mechanisms by status, the
  lessons taught by their trials, and those trials;
* ``symptoms.md``, ``status.md``, ``trials.md``, ``lessons.md`` and ``builds.md`` (L1): the symptom index (the game's
  words, the mechanism behind them, the gate that now catches them), the mechanisms by status, the trials newest
  first, one line per lesson, and the game builds with what was verified or tried on each.

Beside the map:

* ``components/<name>/knowledge/INDEX.md`` for each component of a repository: its mechanisms under each topic they
  carry, the symptom index of its own trials, its trials and its lessons. It links nothing outside the component's
  knowledge folder, so an installed plugin carries a working index of its own;
* on each mechanism and lesson page, the block between ``<!-- referenced-by:start -->`` and
  ``<!-- referenced-by:end -->``: the trials, gates, shapes, skills, examples and other records that cite it.

A modder's project folder (a root with ``knowledge/`` and no ``modkit.repo.toml``) gets the map in that same
``knowledge/`` folder, beside its record folders, and no INDEX.md: the map's README covers the project's records.

A repository shows only what its visibility allows: a public repository's pages are rendered from the public part
of the corpus, so a private record is never named in a public file even when private components are installed. A
render only writes files of the root it was asked about, and deletes the generated pages it no longer writes (a
file that starts with the generated header, in the map folder or as the root ``KNOWLEDGE.md`` of the one-page map).
"""
from __future__ import annotations

import os
from pathlib import Path

from modkit.core import components
from modkit.core.knowledge import check as kcheck
from modkit.core.knowledge import corpus as kcorpus
from modkit.core.knowledge import schema
from modkit.core.knowledge.corpus import FOOTER_END, FOOTER_START, GENERATED, Corpus

NONE_YET = "None yet."
MAP = "knowledge"
OLD_MAP = "KNOWLEDGE.md"  # the one-page map the folder replaced; render deletes a generated one
UPDATES_TOPIC = "game-updates"
STATUS_MEANING = ("`PLAYED` worked in a real play; `PROBED` loaded and ran in a probe build, not yet confirmed in "
                  "play; `RE` shown by analysis of the game, not yet by a build; `STOCK` stock does it in the same "
                  "place, we have not; `FAILED` tried and does not work (the record names the alternative); "
                  "`UNTESTED` not tried yet.")


class RenderError(RuntimeError):
    """The records have errors, so nothing was rendered."""


def _same(a, b) -> bool:
    return os.path.normcase(os.path.abspath(str(a))) == os.path.normcase(os.path.abspath(str(b)))


def _key(path) -> str:
    return os.path.normcase(os.path.abspath(str(path)))


def _cell(text: str) -> str:
    return " ".join(text.split()).replace("|", "\\|")


def _newest_first(trials) -> list:
    out = sorted(trials, key=lambda t: t.id, reverse=True)
    out.sort(key=lambda t: t.date, reverse=True)
    return out


def _build_order(build: str):
    """Newest first: numeric builds by value, then anything else by name."""
    return (0, -int(build), "") if build.isdigit() else (1, 0, build)


class _Pages:
    def __init__(self, root: Path, full: Corpus):
        self.repo = Path(root)
        self.is_repo = kcorpus.is_repo(self.repo)
        public = self.is_repo and components.visibility(self.repo) == "public"
        self.view = full.restricted("public") if public else full
        self.resolver = kcheck.Resolver(self.view)
        self.own = ([r for r in self.view.roots.values() if not r.is_project and _same(r.repo_root, self.repo)]
                    if self.is_repo else [])
        self.map = self.repo / MAP

    # ---- what is written --------------------------------------------------------------------------------------
    def used_topics(self) -> list[schema.Topic]:
        """The declared topics some mechanism carries, in declaration order."""
        used = {t for m in self.view.mechanisms.values() for t in m.topics}
        return [t for t in self.view.topics.values() if t.id in used]

    def targets(self) -> dict[Path, object]:
        """Every page this render writes, mapped to the function that makes its text."""
        out: dict[Path, object] = {}
        for root in self.own:
            out[root.knowledge / "INDEX.md"] = lambda root=root: self.index(root)
        out[self.map / "README.md"] = self.readme
        for t in self.used_topics():
            out[self.map / "topics" / f"{t.id}.md"] = lambda t=t: self.topic(t)
        for name, make in (("symptoms.md", self.symptom_page), ("status.md", self.status_page),
                           ("trials.md", self.trials_page), ("lessons.md", self.lessons_page),
                           ("builds.md", self.builds_page)):
            out[self.map / name] = make
        for record in [*self.view.mechanisms.values(), *self.view.lessons.values()]:
            if self._mine(record.where):
                path = Path(record.where.path)
                out[path] = lambda path=path, record=record: _with_footer(path.read_bytes().decode("utf-8"),
                                                                          self.footer(record))
        return out

    # ---- links -----------------------------------------------------------------------------------------------
    def _link(self, from_dir: Path, target: str | Path) -> str:
        return Path(os.path.relpath(target, from_dir)).as_posix()

    def _mine(self, where: schema.Where) -> bool:
        return _same(where.repo_root, self.repo)

    def ref(self, record, from_dir: Path, named: bool = True) -> str:
        """A link to the record's page when it is in this root; otherwise its ID (and, if ``named``, component)."""
        if self._mine(record.where):
            return f"[{record.id}]({self._link(from_dir, record.where.path)})"
        return f"`{record.id}`" + (f" ({record.where.component})" if named else "")

    def code(self, dotted: str, from_dir: Path) -> str:
        """A link to the file that defines ``dotted``, with no line anchor: a line number would go stale on every
        edit above the definition, and with it every page that cites the gate."""
        found = self.resolver.locate(dotted)
        if found and _same_prefix(found[0], self.repo):
            return f"[`{dotted}`]({self._link(from_dir, found[0])})"
        return f"`{dotted}`"

    def _mech_line(self, m: schema.Mechanism, here: Path) -> str:
        build = m.verified_build
        return (f"- {self.ref(m, here, named=False)}: {m.title} ({m.where.component}"
                + (f", verified {build})" if build else ")"))

    def _trial_line(self, t: schema.Trial, here: Path) -> str:
        return f"- {t.date} {self.ref(t, here, named=False)} ({t.where.component}): {t.kind}, {t.outcome}"

    def _lesson_line(self, x: schema.Lesson, here: Path) -> str:
        return f"- {self.ref(x, here, named=False)} ({x.where.component}): {x.title}"

    def _by_status(self, mechs, line, level: str = "###") -> list[str]:
        out = []
        for status in schema.STATUSES:
            group = sorted((m for m in mechs if m.status == status), key=lambda m: m.id)
            if group:
                out += [f"{level} {status}", "", *(line(m) for m in group), ""]
        return out or [NONE_YET, ""]

    # ---- the symptom index ------------------------------------------------------------------------------------
    def symptoms(self, trials, here: Path, inside: Path | None = None) -> list[str]:
        """The symptom table of `trials` (the game's own words, the mechanism behind them, the gate that now catches
        them), one row per symptom and mechanism, followed by a blank line; "None yet." when no trial has one.

        With `inside` (a component's folder) the table links nothing outside that component's knowledge folder: a
        mechanism of another component and every gate are named, not linked, so the page reads the same in an
        installed plugin, whose neighbours are not where a clone keeps them."""
        v, rows = self.view, set()
        for t in trials:
            if not t.symptom:
                continue
            for mid in t.mechanisms:
                m = v.mechanisms.get(mid)
                if not m:
                    continue
                if inside is None:
                    mech, gates = self.ref(m, here), [self.code(g, here) for g in m.gates]
                else:
                    mech = (self.ref(m, here) if _same_prefix(m.where.path, inside)
                            else f"`{m.id}` ({m.where.component})")
                    gates = [f"`{g}`" for g in m.gates]
                rows.add((_cell(t.symptom), mech, ", ".join(gates) or "none yet"))
        if not rows:
            return [NONE_YET, ""]
        return ["| Symptom | Mechanism | Gate |", "| --- | --- | --- |",
                *(f"| {s} | {m} | {g} |" for s, m, g in sorted(rows, key=lambda r: (r[0].lower(), r))), ""]

    # ---- INDEX.md --------------------------------------------------------------------------------------------
    def index(self, root) -> str:
        v, here = self.view, root.knowledge
        mechs = sorted((m for m in v.mechanisms.values() if m.where.component == root.name),
                       key=lambda m: (schema.STATUSES.index(m.status), m.id))
        trials = _newest_first(t for t in v.trials.values() if t.where.component == root.name)
        lessons = sorted((x for x in v.lessons.values() if x.where.component == root.name), key=lambda x: x.id)
        topics = sorted(v.topics.values(), key=lambda t: t.where.component != root.name)  # its own topics first
        out = [GENERATED, f"# {root.name}: knowledge index", "", "## Mechanisms by topic", "",
               "A mechanism filed under two topics is listed under both.", ""]
        if not mechs:
            out += [NONE_YET, ""]
        for t in topics:
            group = [m for m in mechs if t.id in m.topics]
            if group:
                out += [f"### {t.title}", ""]
                out += [f"- {self.ref(m, here)}: {m.title} ({m.status}"
                        + (f", verified {m.last_verified})" if m.last_verified else ")") for m in group]
                out.append("")
        out += ["## Symptom index", "", "The game's own words in this component's trials, the mechanism behind them, "
                "and the gate that now catches them.", ""]
        out += self.symptoms(trials, here, inside=root.path)
        out += ["## Trials, newest first", ""]
        out += [f"- {t.date} {self.ref(t, here)}: {t.kind}, {t.outcome}" + (f". {t.symptom}" if t.symptom else "")
                for t in trials] or [NONE_YET]
        out += ["", "## Lessons", ""]
        out += [f"- {self.ref(x, here)}: {x.title}" for x in lessons] or [NONE_YET]
        return "\n".join(out) + "\n"

    # ---- the map: README.md ------------------------------------------------------------------------------------
    def readme(self) -> str:
        v, here = self.view, self.map
        if self.is_repo:
            seen, raw = "this repository", "in each component's `knowledge/` folder (`components/*/knowledge/`)"
        else:
            seen = "this project folder"
            raw = ("in each component's `knowledge/` folder and, for this project, beside these pages in "
                   "`mechanisms/`, `trials/` and `lessons/`")
        out = [GENERATED, "# Knowledge map", "",
               f"What the game does (mechanisms), what was tried and how it came out (trials), and the rules learned "
               f"(lessons), over every component visible from {seen}. These pages are generated; the raw facts, "
               f"one per file, live {raw}.", "",
               "## Start here", "", "| Question | Go to |", "| --- | --- |",
               "| What is known about X? | [the topics below](#topics) |",
               "| I saw this in game | [symptoms.md](symptoms.md) |",
               "| How sure is it? | [status.md](status.md) |",
               "| Which game build was it checked on? | [builds.md](builds.md) |",
               "| What was tried? | [trials.md](trials.md) |",
               "| What rules did it teach? | [lessons.md](lessons.md) |", "", "## Topics", ""]
        used = {t.id for t in self.used_topics()}
        if not v.topics:
            out += [NONE_YET, ""]
        else:
            out += ["| Topic | Scope | Mechanisms | PLAYED |", "| --- | --- | --- | --- |"]
            for t in v.topics.values():
                mechs = [m for m in v.mechanisms.values() if t.id in m.topics]
                label = f"[{_cell(t.title)}](topics/{t.id}.md)" if t.id in used else _cell(t.title)
                out.append(f"| {label} | {_cell(t.scope)} | {len(mechs)} "
                           f"| {sum(1 for m in mechs if m.status == 'PLAYED')} |")
            out.append("")
        out += ["## Components", ""]
        rows = sorted(v.roots.values(), key=lambda r: (r.is_project, r.name))
        if not rows:
            out += [NONE_YET, ""]
        else:
            out += ["| Component | Knows | Mechanisms | Trials | Lessons |", "| --- | --- | --- | --- | --- |"]
            for r in rows:
                count = lambda store: sum(1 for x in store.values() if x.where.component == r.name)  # noqa: E731
                if r.is_project:
                    label, knows = "this project", "your own records, beside these pages"
                else:
                    label = (f"[{r.name}]({self._link(here, r.knowledge / 'INDEX.md')})" if r in self.own
                             else r.name)
                    knows = _cell(r.description)
                out.append(f"| {label} | {knows} | {count(v.mechanisms)} | {count(v.trials)} | {count(v.lessons)} |")
            out.append("")
        core = v.roots.get("core")
        guide = core.knowledge / "README.md" if core is not None else None
        if guide is not None and guide.is_file() and _same_prefix(guide, self.repo):
            how = f"[{Path(os.path.relpath(guide, self.repo)).as_posix()}]({self._link(here, guide)})"
        else:
            how = "the `knowledge/README.md` in the `warno-core` plugin's folder"
        out += ["## Writing records", "",
                f"To add or change a record, follow {how}. Never edit these pages: "
                "`python -m modkit.core.knowledge render` rewrites them."]
        return "\n".join(out) + "\n"

    # ---- the map: one page per topic ---------------------------------------------------------------------------
    def topic(self, t: schema.Topic) -> str:
        v, here = self.view, self.map / "topics"
        mechs = [m for m in v.mechanisms.values() if t.id in m.topics]
        trial_ids = {x.id for m in mechs for x in kcheck.linked_trials(v, m)}
        lessons = sorted((x for x in v.lessons.values() if trial_ids & set(x.trials)), key=lambda x: x.id)
        out = [GENERATED, f"# {t.title}", "", t.scope, "",
               f"Topic `{t.id}`, declared by {t.where.component}. Back to "
               f"[the map]({self._link(here, self.map / 'README.md')}).", "",
               "## Mechanisms", ""]
        out += self._by_status(mechs, lambda m: self._mech_line(m, here))
        out += ["## Lessons", "", "Taught by the trials of these mechanisms.", ""]
        out += [self._lesson_line(x, here) for x in lessons] or [NONE_YET]
        out += ["", "## Trials, newest first", ""]
        out += [self._trial_line(x, here) for x in _newest_first(v.trials[i] for i in trial_ids)] or [NONE_YET]
        return "\n".join(out) + "\n"

    # ---- the map: the L1 pages --------------------------------------------------------------------------------
    def _head(self, title: str, intro: str) -> list[str]:
        return [GENERATED, f"# {title}", "", intro + " Back to [the map](README.md).", ""]

    def symptom_page(self) -> str:
        out = self._head("Symptom index", "The game's own words for a failure, the mechanism behind them, and the "
                                          "gate that now catches them.")
        out += self.symptoms(self.view.trials.values(), self.map)
        return "\n".join(out).rstrip("\n") + "\n"

    def status_page(self) -> str:
        out = self._head("Mechanisms by status", "How far each mechanism is proven: " + STATUS_MEANING)
        out += self._by_status(self.view.mechanisms.values(),
                               lambda m: f"- {self.ref(m, self.map, named=False)} ({m.where.component}): {m.title}",
                               level="##")
        return "\n".join(out).rstrip("\n") + "\n"

    def trials_page(self) -> str:
        out = self._head("Trials, newest first", "Every attempt, with its kind and outcome.")
        out += [self._trial_line(t, self.map) for t in _newest_first(self.view.trials.values())] or [NONE_YET]
        return "\n".join(out) + "\n"

    def lessons_page(self) -> str:
        v, here = self.view, self.map
        out = self._head("Lessons", "The rules the trials taught, one file each, with the trials that taught them.")
        for x in sorted(v.lessons.values(), key=lambda x: x.id):
            links = ", ".join(self.ref(v.trials[t], here, named=False) if t in v.trials else f"`{t}`"
                              for t in x.trials)
            out.append(f"{self._lesson_line(x, here)}. Trials: {links}")
        if not v.lessons:
            out.append(NONE_YET)
        return "\n".join(out) + "\n"

    def builds_page(self) -> str:
        v, here = self.view, self.map
        intro = ("A fact holds for the build it was last verified on. After a game update, a record still on an older "
                 "build is unconfirmed until re-verified.")
        if UPDATES_TOPIC in {t.id for t in self.used_topics()}:
            intro += f" Start with [topics/{UPDATES_TOPIC}.md](topics/{UPDATES_TOPIC}.md)."
        out = self._head("Game builds", intro)
        builds: dict[str, tuple[list, list]] = {}
        for m in v.mechanisms.values():
            if m.verified_build:
                builds.setdefault(m.verified_build, ([], []))[0].append(m)
        for t in v.trials.values():
            builds.setdefault(t.game_version, ([], []))[1].append(t)

        def mech(m):
            date = m.last_verified.split(" ", 1)[1] if m.verified_build else ""
            return (f"- {self.ref(m, here, named=False)} ({m.where.component}): {m.title} ({m.status}"
                    + (f", {date})" if date else ")"))

        for build in sorted(builds, key=_build_order):
            mechs, trials = builds[build]
            out += [f"## {build}", "", "### Mechanisms last verified on it", ""]
            out += [mech(m) for m in sorted(mechs, key=lambda m: m.id)] or [NONE_YET]
            out += ["", "### Trials run on it", ""]
            out += [self._trial_line(t, here) for t in _newest_first(trials)] or [NONE_YET]
            out.append("")
        out += ["## Not verified on any build", ""]
        out += [mech(m) for m in sorted(v.mechanisms.values(), key=lambda m: m.id) if not m.verified_build] \
            or [NONE_YET]
        return "\n".join(out) + "\n"

    # ---- the footer on a mechanism or lesson page ----------------------------------------------------------------
    def footer(self, record) -> str:
        v, here = self.view, Path(record.where.path).parent
        lines = [FOOTER_START, "## Referenced by", ""]
        if record.record_kind == "mechanism":
            trials = kcheck.linked_trials(v, record)
        else:
            trials = [v.trials[t] for t in sorted(set(record.trials)) if t in v.trials]
        if trials:
            lines.append("- Trials: " + ", ".join(self.ref(t, here) for t in trials))
        if getattr(record, "gates", ()):
            lines.append("- Gates: " + ", ".join(self.code(g, here) for g in record.gates))
        if getattr(record, "shapes", ()):
            lines.append("- Shapes: " + ", ".join(self.code(g, here) for g in record.shapes))
        for kind, title in (("skill", "Skills"), ("example", "Examples")):
            cites = sorted({c.where.path for c in v.citations if c.id == record.id and c.kind == kind})
            if cites:
                lines.append(f"- {title}: " + ", ".join(self._file(p, here) for p in cites))
        records = sorted({c.source_id for c in v.citations if c.id == record.id and c.kind == "record"} - {record.id})
        if records:
            lines.append("- Records: " + ", ".join(
                self.ref(v.record(r), here) if v.record(r) else f"`{r}`" for r in records))
        if len(lines) == 3:
            lines.append("Nothing references this yet.")
        lines.append(FOOTER_END)
        return "\n".join(lines)

    def _file(self, path: str, from_dir: Path) -> str:
        if _same_prefix(path, self.repo):
            rel = Path(os.path.relpath(path, self.repo)).as_posix()
            return f"[`{rel}`]({self._link(from_dir, path)})"
        return f"`{Path(path).name}`"


def _same_prefix(path, root) -> bool:
    try:
        Path(os.path.abspath(str(path))).relative_to(os.path.abspath(str(root)))
        return True
    except ValueError:
        return False


def _with_footer(text: str, block: str) -> str:
    eol = "\r\n" if "\r\n" in text else "\n"
    block = block.replace("\n", eol)
    start = text.find(FOOTER_START)
    if start >= 0:
        end = text.find(FOOTER_END, start)
        return text[:start] + block + (text[end + len(FOOTER_END):] if end >= 0 else eol)
    return text.rstrip("\r\n") + eol * 2 + block + eol


def _load(root: Path, corpus: Corpus | None) -> Corpus:
    return corpus if corpus is not None else kcorpus.load_folder(root)


def plan(root: Path, corpus: Corpus | None = None) -> dict[Path, str]:
    """Every generated file of the root (a repository or a project folder) and its text. Raises ``RenderError`` if
    the records have errors."""
    root = Path(root)
    full = _load(root, corpus)
    errors, _ = kcheck.check(full, current_build=None, repo=root)
    if errors:
        raise RenderError("the records have errors; fix them first:\n  " + "\n  ".join(errors[:20]))
    return {path: make() for path, make in _Pages(root, full).targets().items()}


def _generated_files(root: Path) -> list[Path]:
    """The generated pages under the root's map folder, and a generated root ``KNOWLEDGE.md``."""
    found = []
    old = root / OLD_MAP
    if old.is_file() and kcorpus.is_generated(old):
        found.append(old)
    folder = root / MAP
    for path in sorted(folder.rglob("*.md")) if folder.is_dir() else []:
        if not (kcorpus.SKIP_DIRS & set(path.relative_to(folder).parts)) and kcorpus.is_generated(path):
            found.append(path)
    return found


def orphans(root: Path, corpus: Corpus | None = None) -> list[Path]:
    """The generated pages that ``render`` no longer writes (and so deletes). Only files that start with the
    generated header count, so a hand-written file in the map folder is never one."""
    root = Path(root)
    written = {_key(p) for p in _Pages(root, _load(root, corpus)).targets()}
    return [p for p in _generated_files(root) if _key(p) not in written]


def orphan_problems(root: Path, corpus: Corpus | None = None) -> list[str]:
    """One line per generated page that ``render`` no longer writes."""
    root = Path(root)
    return sorted(f"{Path(os.path.relpath(p, root)).as_posix()}: stale generated page that render no longer writes; "
                  "run `python -m modkit.core.knowledge render`, which deletes it" for p in orphans(root, corpus))


def _current(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except OSError:
        return None


def _differs(path: Path, text: str) -> bool:
    """Whether the file differs from ``text``; line endings are not a difference (a checkout may use CRLF)."""
    current = _current(path)
    return current is None or current.replace(b"\r\n", b"\n") != text.replace("\r\n", "\n").encode("utf-8")


def stale(root: Path, corpus: Corpus | None = None) -> list[Path]:
    """The generated files that differ from what ``render`` would write, then the ones it would delete."""
    root = Path(root)
    full = _load(root, corpus)
    return [p for p, text in plan(root, full).items() if _differs(p, text)] + orphans(root, full)


def problems(root: Path, corpus: Corpus | None = None) -> list[str]:
    """One line per generated file that is stale, was edited by hand, or is no longer written, naming the fix. A
    mechanism or lesson page whose referenced-by block differs from what ``render`` writes is
    ``footer-not-generated``. Out-of-date pages are not reported while the records themselves have errors (the
    check reports those)."""
    root = Path(root)
    full = _load(root, corpus)
    out = orphan_problems(root, full)
    try:
        texts = plan(root, full)
    except RenderError:
        return out
    pages = {_key(r.where.path) for r in [*full.mechanisms.values(), *full.lessons.values()]}
    fix = "run `python -m modkit.core.knowledge render`"
    for path, text in texts.items():
        if not _differs(path, text):
            continue
        rel = Path(os.path.relpath(path, root)).as_posix()
        if _key(path) in pages:
            out.append(f"{rel}: footer-not-generated: the referenced-by block is not what render writes; {fix}")
        else:
            out.append(f"{rel}: generated file is stale or was edited by hand; {fix}")
    return sorted(out)


def render(root: Path, corpus: Corpus | None = None) -> list[Path]:
    """Write the navigation and delete the generated pages no longer written; returns the files changed."""
    root = Path(root)
    full = _load(root, corpus)
    changed = []
    for path, text in plan(root, full).items():
        if _differs(path, text):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(text.encode("utf-8"))
            changed.append(path)
    for path in orphans(root, full):
        path.unlink()
        changed.append(path)
        folder = path.parent
        if folder != root / MAP and _same_prefix(folder, root / MAP) and not any(folder.iterdir()):
            folder.rmdir()  # an emptied topics/ folder
    return changed
