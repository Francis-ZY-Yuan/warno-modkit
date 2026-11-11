"""The hygiene gates of a public repository, over the working tree and over every commit.

Rules (each ``Finding`` names one):

* ``stock-extension``  a file with a game-data extension, or named like the derived rules table or a file that
                       ``setup extract`` writes (its index, provenance and manifest)
* ``size``             a file over 512 KiB
* ``local-path``       a drive-letter or home-folder path, or a Steam library folder
* ``deny``             a normalised word 1- to 4-gram whose SHA-256 is in ``hygiene-deny.toml`` (hashes only, so the
                       tracked file names nothing), or a plain string in the git-ignored ``modkit.local.toml``'s
                       ``deny`` list; the finding's text is ``sha256:<hash>``, never the word
* ``address``          a 0x hex literal of 5+ digits, or the words that name exe internals
* ``private-ref``      ``modkit.<x>`` / ``modkit-<x>`` for an ``x`` that is no component of this repository, or a
                       ``warno-<x>`` plugin name in a manifest
* ``screenshot``       a file in ``docs/screenshots/`` with the suffix ``.jpg`` is a reviewed screenshot: it skips the
                       ``stock-extension`` finding and every content-text rule (``local-path``, ``address``, ``deny``,
                       ``private-ref``), while ``size`` and ``deny`` on its path still run. It is a finding when the
                       bytes are not a JPEG (``FF D8 FF``), when any segment in the file is an APPn other than APP0
                       (JFIF), APP2 (ICC) or APP14 (Adobe) or is a COM, when bytes follow the EOI, or when
                       ``docs/screenshots/README.md`` has no line that names the file and captions it. A ``.png``
                       there, or a ``.jpg`` elsewhere, stays ``stock-extension``
* ``manifest-personal`` an owner or author other than the generic one, or an email, in a plugin manifest

A finding is allowed only by an exact ``{path, text, reason}`` entry in ``components/core/hygiene-allow.toml``.
``python -m modkit.core.hygiene hash PHRASE`` prints the hash to add to ``hygiene-deny.toml``.
"""
from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path

from modkit.core import components, ndfrules, paths, setup

ALLOW_FILE = "components/core/hygiene-allow.toml"
DENY_FILE = "components/core/hygiene-deny.toml"
MAX_BYTES = 512 * 1024
SCREENSHOT_DIR = "docs/screenshots"
SCREENSHOT_README = SCREENSHOT_DIR + "/README.md"
SCREENSHOT_SUFFIX = ".jpg"
# The only APPn segments a screenshot may carry: APP0 (JFIF), APP2 (ICC profile), APP14 (Adobe colour transform).
JPEG_ALLOWED_APP = frozenset({0xE0, 0xE2, 0xEE})
SIZE_TEXT = "over 512 KiB"
# Game-data formats, every one `setup extract` writes into an extraction among them: the mod SDK's NDF text (.ndf),
# Definition sidecars (.tag), Details files (.sav), compiled scenario Python (.xyz).
STOCK_EXTENSIONS = frozenset(".ndfbin .ndf .dat .dic .tgv .tag .sav .xyz .ess .spk .webm .vid .zip .exe .dll .dmp .png "
                             ".jpg .dds".split())
# The derived rules table, and the index, provenance and manifest files `setup extract` writes beside the stock files.
STOCK_NAMES = frozenset({ndfrules.TABLE_NAME, setup.PROVENANCE, setup.INDEX_NAME, setup.MANIFEST})
SKIP_TOP = frozenset({".venv", ".git", "build", "modkit-data"})
GENERIC_OWNER = "warno-modkit contributors"
MANIFEST_NAMES = frozenset({"plugin.json", "marketplace.json"})
NOT_COMPONENTS = frozenset({"data"})  # modkit-data is the data folder, not a distribution

LOCAL_PATH = re.compile(
    r"(?<![A-Za-z0-9_])[A-Za-z]:[\\/]"
    r"|(?i:Steam[L]ibrary)"
    r"|(?<![\w.])/(?:Users|home)/[A-Za-z0-9_.-]+")
# 0x literals: digits may carry '_' separators and a type suffix (0x...ull); five or more digits count.
HEX_LITERAL = re.compile(r"\b0[xX]([0-9a-fA-F][0-9a-fA-F_]*)")
# A numbered slot, in any spelling, is reported with its number so a bare-word allowlist entry never covers it.
NUMBERED_SLOT = re.compile(r"(?i)(?<![A-Za-z0-9])s[l]ots?[\s_#]*(\d+)")
IDENTIFIER = re.compile(r"[A-Za-z0-9_]+")
IDENT_PART = re.compile(r"[A-Z]+(?![a-z])|[A-Z]?[a-z]+|\d+")
ADDRESS_WORDS = frozenset({"v" + "table", "v" + "tables", "r" + "va", "r" + "vas", "s" + "lot", "s" + "lots"})
PRIVATE_DOT = re.compile(r"(?i)(?<![A-Za-z0-9])modkit\.([A-Za-z_]\w*)\b(?!\.toml)")
PRIVATE_DASH = re.compile(r"(?i)(?:(?<![A-Za-z0-9])modkit-|(?<![A-Za-z0-9_])modkit_)([A-Za-z]+)")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PERSONAL_KEYS = frozenset({"author", "authors", "owner", "maintainers", "contributors"})
LINK_KEYS = frozenset({"url", "homepage", "repository", "email"})
TOKEN = re.compile(r"[a-z0-9]+")
# In the allowlist file the quoted ``text`` value is the thing being excused, so it is not scanned itself; the
# path, the reason and anything else in the file still are.
ALLOW_TEXT_FIELD = re.compile(r'(?m)^(\s*text\s*=\s*)"(?:[^"\\]|\\.)*"')


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    text: str
    commit: str = ""

    def __str__(self) -> str:
        where = f"{self.path}:{self.line}" if self.line else self.path
        return f"{where}: [{self.rule}] {self.text}" + (f" (first in commit {self.commit})" if self.commit else "")


@dataclass(frozen=True)
class AllowEntry:
    path: str
    text: str
    reason: str


def normalise(phrase: str) -> str:
    return " ".join(TOKEN.findall(phrase.lower()))


def phrase_hash(phrase: str) -> str:
    return hashlib.sha256(normalise(phrase).encode()).hexdigest()


def load_allowlist(root: Path) -> list[AllowEntry]:
    path = Path(root) / ALLOW_FILE
    if not path.is_file():
        return []
    with open(path, "rb") as fh:
        rows = tomllib.load(fh).get("allow", [])
    entries = []
    for row in rows:
        entry = AllowEntry(str(row.get("path", "")), str(row.get("text", "")), str(row.get("reason", "")).strip())
        if not (entry.path and entry.text and entry.reason):
            raise ValueError(f"{ALLOW_FILE}: every entry needs path, text and a reason: {row}")
        entries.append(entry)
    return entries


def load_deny_hashes(root: Path) -> frozenset[str]:
    path = Path(root) / DENY_FILE
    if not path.is_file():
        return frozenset()
    with open(path, "rb") as fh:
        return frozenset(h.lower() for h in tomllib.load(fh).get("hashes", []))


class _Rules:
    """Everything a scan needs, loaded once."""

    def __init__(self, root: Path, local_deny=None):
        self.root = Path(root)
        self.allow = {(e.path, e.text) for e in load_allowlist(self.root)}
        self.deny = load_deny_hashes(self.root)
        plain = paths.local_config(self.root).get("deny", []) if local_deny is None else local_deny
        self.local = frozenset(phrase_hash(p) for p in plain if normalise(p))
        lengths = {len(normalise(p).split()) for p in plain if normalise(p)}
        self.lengths = sorted({1, 2, 3, 4} | lengths)
        self.components = frozenset(components.repo_components(self.root))

    def keep(self, findings: list[Finding]) -> list[Finding]:
        return [f for f in findings if (f.path, f.text) not in self.allow]


def _texts(data: bytes) -> list[str]:
    """The ways to read a blob: text if it is UTF-8, else Latin-1 (so ASCII inside binaries is seen), plus UTF-16 for
    blobs that look like it."""
    try:
        out = [data.decode("utf-8")]
    except UnicodeDecodeError:
        out = [data.decode("latin-1")]
    if b"\0" in data[:4096]:
        out.append(data.decode("utf-16-le", "ignore"))
        out.append(data[1:].decode("utf-16-le", "ignore"))
    return out


def _line_starts(text: str) -> list[int]:
    starts, pos = [0], 0
    while (pos := text.find("\n", pos)) != -1:
        pos += 1
        starts.append(pos)
    return starts


def _line_of(starts: list[int], offset: int) -> int:
    lo, hi = 0, len(starts)
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if starts[mid] <= offset:
            lo = mid
        else:
            hi = mid
    return lo + 1


def _deny(path: str, text: str, rules: _Rules, starts: list[int] | None = None) -> list[Finding]:
    hashes = rules.deny | rules.local
    if not hashes:
        return []
    starts = starts or _line_starts(text)
    tokens = [(m.group(0), m.start()) for m in TOKEN.finditer(text.lower())]
    out = []
    for n in rules.lengths:
        for i in range(len(tokens) - n + 1):
            window = tokens[i:i + n]
            if any(len(t) > 64 for t, _ in window):
                continue
            digest = hashlib.sha256(" ".join(t for t, _ in window).encode()).hexdigest()
            if digest in hashes:
                out.append(Finding(path, _line_of(starts, window[0][1]) if text else 0, "deny", "sha256:" + digest))
    return out


def _scan_manifest(path: str, text: str, rules: _Rules) -> list[Finding]:
    out = []
    try:
        data = json.loads(text)
    except ValueError:
        return [Finding(path, 0, "manifest-personal", "manifest is not valid JSON")]

    def walk(node):
        if isinstance(node, dict):
            for key, value in node.items():
                low = str(key).lower()
                if low in PERSONAL_KEYS and value != {"name": GENERIC_OWNER}:
                    out.append(Finding(path, 0, "manifest-personal",
                                       f"{low} must be exactly the generic {GENERIC_OWNER!r}"))
                    continue
                if low in LINK_KEYS:
                    out.append(Finding(path, 0, "manifest-personal", f"{low} field: {value}"[:200]))
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str):
            if EMAIL.search(node):
                out.append(Finding(path, 0, "manifest-personal", "email address"))
            if LOCAL_PATH.search(node):
                out.append(Finding(path, 0, "manifest-personal", "local path"))
            m = re.fullmatch(r"warno-(\w+)", node)
            if m and m.group(1) != "modkit" and m.group(1) not in rules.components:
                out.append(Finding(path, 0, "private-ref", node))

    walk(data)
    return out


def _address(path: str, text: str, starts: list[int]) -> list[Finding]:
    """Hex literals of 5+ digits (``_`` separators and suffixes allowed), the words that name exe internals (as whole
    words or as identifier parts split on ``_`` and camelCase), and numbered slots (reported with the number)."""
    out, numbered = [], set()
    for m in HEX_LITERAL.finditer(text):
        if len(m.group(1).replace("_", "")) >= 5:
            out.append(Finding(path, _line_of(starts, m.start()), "address", m.group(0)))
    for m in NUMBERED_SLOT.finditer(text):
        numbered.add(m.start())
        out.append(Finding(path, _line_of(starts, m.start()), "address", f"{m.group(0)[:4].lower()} {m.group(1)}"))
    for ident in IDENTIFIER.finditer(text):
        if ident.group(0) == "__s" + "lots__":  # Python's own attribute
            continue
        parts = list(IDENT_PART.finditer(ident.group(0)))
        for i, part in enumerate(parts):
            word = part.group(0).lower()
            at = ident.start() + part.start()
            if word not in ADDRESS_WORDS or at in numbered:
                continue
            nxt = parts[i + 1].group(0) if i + 1 < len(parts) else ""
            if word.startswith("s" + "lot") and nxt.isdigit():
                word = f"{word[:4]} {nxt}"
            out.append(Finding(path, _line_of(starts, at), "address", word))
    return out


def is_screenshot(path: str) -> bool:
    """A ``.jpg`` directly inside ``docs/screenshots/`` (the one reviewed exception to the stock-image rule)."""
    p = Path(path)
    return p.parent.as_posix() == SCREENSHOT_DIR and p.suffix == SCREENSHOT_SUFFIX


def _jpeg_problem(data: bytes) -> str:
    """Why the bytes are not an acceptable screenshot JPEG, or "" when they are. They must start with FF D8 FF; every
    segment up to the final EOI is walked (entropy-coded data after each SOS is skipped, so a progressive file's later
    scans are checked too); only APP0 (JFIF), APP2 (ICC) and APP14 (Adobe) may appear among the APPn and COM segments;
    and nothing may follow the EOI."""
    if data[:3] != bytes([0xFF, 0xD8, 0xFF]):
        return "not a JPEG"
    bad = "malformed JPEG segments"
    pos, n = 2, len(data)
    while pos < n:
        if data[pos] != 0xFF:
            return bad
        while pos < n and data[pos] == 0xFF:  # fill bytes
            pos += 1
        if pos >= n:
            return bad
        marker = data[pos]
        pos += 1
        if marker == 0xD9:  # EOI: the end, with nothing after it
            return "data after EOI" if pos != n else ""
        if marker == 0x01 or 0xD0 <= marker <= 0xD8:  # standalone, no length
            continue
        if pos + 2 > n:
            return bad
        length = int.from_bytes(data[pos:pos + 2], "big")
        if length < 2 or pos + length > n:
            return bad
        if marker == 0xFE:
            return "metadata: COM segment"
        if 0xE0 <= marker <= 0xEF and marker not in JPEG_ALLOWED_APP:
            return f"metadata: APP{marker - 0xE0} segment"
        pos += length
        if marker == 0xDA:  # SOS: skip the entropy-coded data up to the next real marker
            while pos < n:
                if data[pos] != 0xFF:
                    pos += 1
                elif pos + 1 < n and (data[pos + 1] == 0 or 0xD0 <= data[pos + 1] <= 0xD7):
                    pos += 2  # a stuffed byte or a restart marker
                else:
                    break
    return bad


def _listed(name: str, readme: bytes | None) -> bool:
    """Whether the folder README has a line that names the file and gives it a caption."""
    if readme is None:
        return False
    pattern = re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(name) + r"(?![A-Za-z0-9_-])")
    for line in readme.decode("utf-8", "replace").splitlines():
        if pattern.search(line) and re.search(r"[A-Za-z0-9]", pattern.sub("", line, count=1)):
            return True
    return False


def _screenshot_findings(path: str, data: bytes, readme: bytes | None) -> list[Finding]:
    out = []
    problem = _jpeg_problem(data)
    if problem:
        out.append(Finding(path, 0, "screenshot", problem))
    if not _listed(Path(path).name, readme):
        out.append(Finding(path, 0, "screenshot", f"not listed in {SCREENSHOT_README}"))
    return out


def scan_content(path: str, data: bytes, rules: _Rules, readme: bytes | None = None) -> list[Finding]:
    """Every finding for one file's bytes (before the allowlist). ``readme`` is the bytes of the screenshot folder's
    README, which says whether a screenshot is listed."""
    out = _path_findings(path, len(data), rules)
    if is_screenshot(path):
        return _unique(out + _screenshot_findings(path, data, readme))
    if Path(path).name == paths.CONFIG_NAME:
        out.append(Finding(path, 0, "local-config-committed", Path(path).name))
    for full in _texts(data):
        # In the allowlist file the quoted text values are the things being excused, so only the rules they
        # excuse (addresses, words, private names) skip them; personal-data rules read the whole file.
        text = ALLOW_TEXT_FIELD.sub(lambda m: m.group(1) + chr(34) * 2, full) if path == ALLOW_FILE else full
        starts = _line_starts(full)
        for m in LOCAL_PATH.finditer(full):
            out.append(Finding(path, _line_of(starts, m.start()), "local-path", m.group(0)))
        if path == ALLOW_FILE:
            for m in EMAIL.finditer(full):
                out.append(Finding(path, _line_of(starts, m.start()), "manifest-personal", "email address"))
        out += _address(path, text, starts)
        for m in PRIVATE_DOT.finditer(text):
            if m.group(1).lower() not in rules.components:
                out.append(Finding(path, _line_of(starts, m.start()), "private-ref", m.group(0)))
        for m in PRIVATE_DASH.finditer(text):
            if m.group(0).isupper():  # an environment variable such as MODKIT_EXTRACTED
                continue
            if m.group(1).lower() not in rules.components and m.group(1).lower() not in NOT_COMPONENTS:
                out.append(Finding(path, _line_of(starts, m.start()), "private-ref", m.group(0)))
        out += _deny(path, full, rules, starts)
    if Path(path).name in MANIFEST_NAMES:
        out += _scan_manifest(path, data.decode("utf-8", "replace"), rules)
    return _unique(out)


def _path_findings(path: str, size: int, rules: _Rules) -> list[Finding]:
    p = Path(path)
    out = []
    if (p.suffix.lower() in STOCK_EXTENSIONS and not is_screenshot(path)) or p.name.lower() in STOCK_NAMES:
        out.append(Finding(path, 0, "stock-extension", p.name))
    if size > MAX_BYTES:
        out.append(Finding(path, 0, "size", SIZE_TEXT))
    out += _deny(path, path, rules)
    return [Finding(f.path, 0, f.rule, f.text) for f in out]


def _unique(findings: list[Finding]) -> list[Finding]:
    seen, out = set(), []
    for f in findings:
        key = (f.path, f.line, f.rule, f.text, f.commit)
        if key not in seen:
            seen.add(key)
            out.append(f)
    return out


def _git(root: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *args], cwd=root, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", check=True)


def _is_git(root: Path) -> bool:
    return subprocess.run(["git", "rev-parse", "--git-dir"], cwd=root, capture_output=True).returncode == 0


def tree_files(root: Path) -> list[str]:
    """Tracked files plus untracked files that are not ignored, as posix paths relative to ``root``. Untracked files
    under .venv, .git, build or modkit-data are skipped; an untracked ``modkit.local.toml`` is never scanned (a tracked one is a finding)."""
    root = Path(root)
    if _is_git(root):
        tracked = _git(root, "ls-files", "-z", "--cached").stdout.split("\0")
        others = _git(root, "ls-files", "-z", "--others", "--exclude-standard").stdout.split("\0")
        names = [n for n in tracked if n] + [n for n in others if n and n.split("/")[0] not in SKIP_TOP
                                            and Path(n).name != paths.CONFIG_NAME]
    else:
        names = [p.relative_to(root).as_posix() for p in root.rglob("*")
                 if p.is_file() and p.relative_to(root).parts[0] not in SKIP_TOP
                 and p.name != paths.CONFIG_NAME
                 and "__pycache__" not in p.parts and not any(x.endswith(".egg-info") for x in p.parts)]
    return sorted(n for n in set(names) if (root / n).is_file())


def scan_tree(root: Path, *, local_deny=None) -> list[Finding]:
    root = Path(root)
    rules = _Rules(root, local_deny)
    out = []
    readme = (root / SCREENSHOT_README).read_bytes() if (root / SCREENSHOT_README).is_file() else None
    for name in tree_files(root):
        out += scan_content(name, (root / name).read_bytes(), rules, readme)
    return rules.keep(out)


def _commit_text(root: Path) -> list[tuple[str, str]]:
    """(commit, author/committer/message text) for every commit."""
    raw = _git(root, "log", "--all", "--reverse", "-z", "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%B").stdout
    out = []
    for record in raw.split("\0"):
        if record.strip():
            sha, _, rest = record.lstrip("\n").partition("\x1f")
            out.append((sha[:12], rest.replace("\x1f", "\n")))
    return out


def load_identity(root: Path) -> dict | None:
    """The ``[identity]`` table of ``modkit.repo.toml`` (name, email, offset, allow), or None when it has none."""
    try:
        with open(Path(root) / components.REPO_FILE, "rb") as fh:
            table = tomllib.load(fh).get("identity")
    except (OSError, tomllib.TOMLDecodeError):
        return None
    return table if isinstance(table, dict) else None


def scan_identity(root: Path) -> list[Finding]:
    """Every commit's author and committer must be the configured identity (or an allowlisted one), the committer
    must equal the author, and both dates must carry the configured UTC offset. Does nothing without ``[identity]``."""
    root = Path(root)
    cfg = load_identity(root)
    if cfg is None or not _is_git(root):
        return []
    name, email, offset = cfg.get("name", ""), cfg.get("email", ""), cfg.get("offset", "+0000")
    allowed = {(name, email)} | {(a.get("name", ""), a.get("email", "")) for a in cfg.get("allow", [])}
    raw = _git(root, "log", "--all", "--reverse", "-z", "--date=raw",
               "--format=%H%x1f%an%x1f%ae%x1f%cn%x1f%ce%x1f%ad%x1f%cd").stdout
    out: list[Finding] = []
    for record in filter(str.strip, raw.split("\0")):
        sha, an, ae, cn, ce, ad, cd = record.lstrip("\n").split("\x1f")
        where = f"commit:{sha[:12]}"

        def bad(field: str, found: str) -> None:
            out.append(Finding(where, 0, "identity", f"{field} is {found}", sha[:12]))
        for who, n, e in (("author", an, ae), ("committer", cn, ce)):
            if (n, e) not in allowed:
                bad(who, f"{n} <{e}>, expected {name} <{email}> or an allowlisted identity")
        if (cn, ce) != (an, ae):
            bad("committer", f"{cn} <{ce}>, which differs from the author {an} <{ae}>")
        for field, date in (("author date", ad), ("committer date", cd)):
            if date.rpartition(" ")[2] != offset:
                bad(field, f"offset {date.rpartition(' ')[2]}, expected {offset}")
    return out


def scan_history(root: Path, *, local_deny=None) -> list[Finding]:
    """Every blob of every commit (oldest first, each distinct path+blob once, reported with the commit that first
    holds it), plus every commit's authors and message for personal strings."""
    root = Path(root)
    if not _is_git(root):
        return []
    rules = _Rules(root, local_deny)
    out: list[Finding] = []
    seen: set[tuple[str, str]] = set()
    commits = _git(root, "rev-list", "--reverse", "--all").stdout.split()
    wanted: list[tuple[str, str, str]] = []
    for commit in commits:
        listing = _git(root, "ls-tree", "-r", "-z", commit).stdout
        for entry in filter(None, listing.split("\0")):
            meta, _, name = entry.partition("\t")
            mode, kind, blob = meta.split()
            if kind != "blob" or (blob, name) in seen:
                continue
            seen.add((blob, name))
            wanted.append((commit[:12], blob, name))
    if wanted:
        proc = subprocess.run(["git", "cat-file", "--batch"], cwd=root, capture_output=True, check=True,
                              input="".join(f"{blob}\n" for _, blob, _ in wanted).encode())
        buf, pos = proc.stdout, 0
        readmes: dict[str, bytes | None] = {}
        for commit, blob, name in wanted:
            end = buf.index(b"\n", pos)
            _, _, size = buf[pos:end].decode().split()
            data = buf[end + 1:end + 1 + int(size)]
            pos = end + 1 + int(size) + 1
            if is_screenshot(name) and commit not in readmes:  # the README as that commit holds it
                shown = subprocess.run(["git", "show", f"{commit}:{SCREENSHOT_README}"], cwd=root, capture_output=True)
                readmes[commit] = shown.stdout if shown.returncode == 0 else None
            out += [Finding(f.path, f.line, f.rule, f.text, commit)
                    for f in scan_content(name, data, rules, readmes.get(commit))]
    for commit, text in _commit_text(root):
        for f in _deny(f"commit:{commit}", text, rules) + [
                Finding(f"commit:{commit}", 0, "local-path", m.group(0)) for m in LOCAL_PATH.finditer(text)]:
            out.append(Finding(f.path, 0, f.rule, f.text, commit))
    return rules.keep(_unique(out)) + scan_identity(root)


def stale_allowlist(root: Path) -> list[AllowEntry]:
    """Allowlist entries that no longer apply: the file is gone from the tree, or no longer contains the text."""
    root = Path(root)
    stale = []
    for e in load_allowlist(root):
        target = root / e.path
        if not target.is_file():
            stale.append(e)
        elif e.text != SIZE_TEXT and not e.text.startswith("sha256:"):
            body = target.read_bytes()
            if not any(e.text.lower() in t.lower() or e.text.lower() in re.sub(r"\s+", " ", t.lower())
                       for t in _texts(body)):
                stale.append(e)
    return stale


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if len(argv) >= 2 and argv[0] == "hash":
        print(phrase_hash(" ".join(argv[1:])))
        return 0
    print("usage: python -m modkit.core.hygiene hash PHRASE   (prints the SHA-256 for hygiene-deny.toml)")
    return 2


if __name__ == "__main__":
    sys.exit(main())
