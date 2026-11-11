"""Package a built scenario mod as a zip with a one-click .cmd installer (for sharing without the Workshop).

  python -m modkit.core.install <built_mod_dir> --title "<menu title>" [--out DIR]

Writes <out>/<ModName>-share.zip (default out: share/ in the build folder, modkit.core.paths.build_root) holding:
  Install <ModName>.cmd   self-contained installer, the mod is embedded in it as base64
  <ModName>/...           the mod folder, byte-identical to the source, for a manual install
  README.txt              plain-text instructions for the friend
and the same installer beside it, <out>/Install <ModName>.cmd, to send on its own.

The installer copies the mod into <Saved Games>\\EugenSystems\\WARNO\\mod\\ and adds it to ActivatedMods in the
shared mod\\Config.ini, as the game's Mod Center does, in the form the game itself writes there: the mod's ID when it
has a non-zero one (a Workshop item), else its folder name. Either form already in the list, or the ID of the copy it
replaces, counts as the mod, so a reinstall keeps one entry in its place. A build ships ID = 0, but an upload to
the Workshop writes the item's ID into the installed Config.ini: when the installed copy has a non-zero ID and the
incoming one has 0, the installer carries the installed ID into the new Config.ini (that one line only) and says so;
when both are non-zero and differ it refuses, naming both. Refuses (exit 1) a mod with no Config.ini, a
Gameplay mod (cluster lines under [Config], or a file under Gen/ that the game's Gameplay tag lists:
packaging.is_gameplay_file) or a mod whose MANIFEST.tsv lists `requires` rows.

Extension point: a component may register an `InstallHook`. Each one is called with the built mod folder and the
files the installer is about to write, after the checks above and before anything is written; it may refuse the mod
by raising `ShareError`.

Where the installer puts a mod is defined here once: the environment variables it reads (ENV_*), the Saved Games
lookup (SHELL_FOLDERS, SAVED_GAMES_ID) and the folders below it (WARNO_FOLDER, MOD_FOLDER). The .cmd's script is
formatted from these constants, and `saved_games()` / `mod_root()` are the same lookup in Python, for code that
works on the installed mods.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import os
import re
import sys
import zipfile
from pathlib import Path
from typing import Protocol, Sequence

from modkit.core import paths
from modkit.core.packaging import is_gameplay_file

MARKER = ".modinstall"  # a local installer's bookkeeping file: never packed
SHARE_FOLDER = "share"  # the default --out: this folder in the build folder (paths.build_root)
_STAMP = (2026, 1, 1, 0, 0, 0)  # fixed zip timestamp, so the same mod always packs to the same bytes
_NAME_OK = re.compile(r"[A-Za-z0-9_. -]+")

# The installer's environment variables (their names are in every .cmd already shared, so they stay).
ENV_SELF = "OD_SELF"                # the .cmd's own path, which its batch header hands to the PowerShell part
ENV_SAVED_GAMES = "OD_SAVED_GAMES"  # when set: the Saved Games folder to install into (tests point it elsewhere)
ENV_NO_PAUSE = "OD_NO_PAUSE"        # when set: no pause at the end, and refuse instead of waiting while WARNO runs
# Without ENV_SAVED_GAMES, Saved Games is this known folder of the user's shell folders (HKCU), environment variables
# expanded, else %USERPROFILE%\Saved Games.
SHELL_FOLDERS = r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders"
SAVED_GAMES_ID = "{4C5C32FF-BB9D-43b0-B5B4-2D72E54EAAA4}"
WARNO_FOLDER = ("EugenSystems", "WARNO")  # WARNO's folder, below Saved Games
MOD_FOLDER = "mod"                       # below WARNO's folder: the installed mods and their shared Config.ini


def saved_games() -> Path:
    """The Saved Games folder, found as the .cmd's Get-SavedGames finds it: ENV_SAVED_GAMES, else the known folder
    SAVED_GAMES_ID under HKCU's SHELL_FOLDERS (environment variables expanded), else %USERPROFILE%\\Saved Games."""
    if os.environ.get(ENV_SAVED_GAMES):
        return Path(os.environ[ENV_SAVED_GAMES])
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, SHELL_FOLDERS) as key:
            raw = winreg.QueryValueEx(key, SAVED_GAMES_ID)[0]
        if raw:
            return Path(os.path.expandvars(raw))
    except (ImportError, OSError):
        pass
    return Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Saved Games"


def mod_root() -> Path:
    """The installed mods' folder, where the .cmd installs: <Saved Games>/EugenSystems/WARNO/mod."""
    return saved_games().joinpath(*WARNO_FOLDER, MOD_FOLDER)


class ShareError(RuntimeError):
    pass


class InstallHook(Protocol):
    """An addition to the installer, called with the built mod folder and the files about to be written."""

    def __call__(self, mod_dir: Path, targets: Sequence[Path]) -> None: ...


HOOKS: list[InstallHook] = []  # called in registration order


def register_hook(hook: InstallHook) -> InstallHook:
    """Add `hook` to every later `package` call; returns it, so it can decorate a function."""
    HOOKS.append(hook)
    return hook


def overrides_clusters(mod_dir: Path) -> bool:
    """Any key=value line under [Config] (a cluster md5 line) marks a mod that replaces game data."""
    _, sep, tail = (mod_dir / "Config.ini").read_text(encoding="utf-8", errors="replace").partition("[Config]")
    return bool(sep) and any("=" in ln.split(";")[0] for ln in tail.splitlines()[1:])


def gameplay_files(mod_dir: Path) -> list[str]:
    """The files of the mod that make the game tag it Gameplay (packaging.is_gameplay_file), '/'-separated, sorted."""
    return [rel for rel, _ in mod_files(mod_dir) if is_gameplay_file(rel)]


def is_gameplay(mod_dir: Path) -> bool:
    """A Gameplay mod: it replaces game data ([Config] cluster lines) or ships a Gameplay file under Gen/."""
    return overrides_clusters(mod_dir) or bool(gameplay_files(mod_dir))


def required_mods(src: Path) -> list[str]:
    """Mods the build needs alongside it: `requires` rows of the MANIFEST.tsv beside the built folder."""
    manifest = src.parent / "MANIFEST.tsv"
    if not manifest.is_file():
        return []
    rows = [ln.split("\t") for ln in manifest.read_text(encoding="utf-8").splitlines()[1:]]
    return [r[1] for r in rows if len(r) >= 4 and r[3] == "requires"]


def mod_files(src: Path) -> list[tuple[str, Path]]:
    """(relative path with '/', file) for every mod file in sorted order, minus the .modinstall marker."""
    return sorted((p.relative_to(src).as_posix(), p) for p in src.rglob("*") if p.is_file() and p.name != MARKER)


def check(src: Path, title: str) -> None:
    if not (src / "Config.ini").is_file():
        raise ShareError(f"{src} has no Config.ini; not a built mod folder")
    if not _NAME_OK.fullmatch(src.name):
        raise ShareError(f"mod folder name {src.name!r} must be letters, digits, space, '.', '_' or '-'")
    if not title or not title.isascii() or not title.isprintable():
        raise ShareError("--title must be plain printable ASCII")
    if overrides_clusters(src):
        raise ShareError(f"{src.name} changes game data (a Gameplay mod); only scenario mods can be shared this way")
    shipped = gameplay_files(src)
    if shipped:
        raise ShareError(f"{src.name} is a Gameplay mod: it ships {shipped[0]}, a file the game's Gameplay tag lists; "
                         f"only scenario mods can be shared this way")
    req = required_mods(src)
    if req:
        raise ShareError(f"{src.name} requires other mods ({', '.join(req)}); the friend would need them too")


def _entry(z: zipfile.ZipFile, arc: str, data: bytes) -> None:
    zi = zipfile.ZipInfo(arc, _STAMP)
    zi.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(zi, data)


def payload_zip(src: Path, files: list[tuple[str, Path]]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel, p in files:
            _entry(z, f"{src.name}/{rel}", p.read_bytes())
    return buf.getvalue()


def _q(s: str) -> str:
    """A PowerShell single-quoted string."""
    return "'" + s.replace("'", "''") + "'"


# The batch header. The builder fills the {names} (the environment variables from the ENV_* constants).
HEADER = r"""@echo off
setlocal
title Install {name}
set "{env_self}=%~f0"
powershell.exe -NoProfile -Command "$t=[IO.File]::ReadAllText($env:{env_self});$a=$t.IndexOf('::PS-'+'BEGIN')+10;$b=$t.IndexOf('::PS-'+'END');iex $t.Substring($a,$b-$a)"
set "RC=%ERRORLEVEL%"
if not defined {env_no_pause} pause
exit /b %RC%
::PS-BEGIN
"""

# Plain PowerShell 5.1. The builder fills the {names} (the mod, and where it goes from the module's constants);
# every other brace of the script is doubled.
SCRIPT = r"""$ErrorActionPreference = 'Stop'
$ModName = {modname}
$Title = {title}
# relative path -> SHA256 of every file in the mod, in order
$Hashes = [ordered]@{{
{hashes}
}}

function Get-SavedGames {{
    if ($env:{env_saved_games}) {{ return $env:{env_saved_games} }}
    $key = 'HKCU:\{shell_folders}'
    $id = '{saved_games_id}'
    $raw = (Get-ItemProperty -Path $key -Name $id -ErrorAction SilentlyContinue).$id
    if ($raw) {{ return [Environment]::ExpandEnvironmentVariables($raw) }}
    return (Join-Path $env:USERPROFILE 'Saved Games')
}}

function Get-ModId($dir) {{
    # The [Properties] ID of the mod in $dir without leading zeros; '' for ID 0, no ID or no Config.ini
    $file = Join-Path $dir 'Config.ini'
    if (-not (Test-Path -LiteralPath $file)) {{ return '' }}
    $m = [regex]::Match([IO.File]::ReadAllText($file), '(?m)^[ \t]*ID[ \t]*=[ \t]*([0-9]+)')
    if (-not $m.Success) {{ return '' }}
    return $m.Groups[1].Value.TrimStart('0')
}}

function Test-Hashes($root) {{
    foreach ($rel in $Hashes.Keys) {{
        $file = Join-Path $root ($rel -replace '/', '\')
        if (-not (Test-Path -LiteralPath $file) -or (Get-FileHash -LiteralPath $file -Algorithm SHA256).Hash -ne $Hashes[$rel]) {{
            throw 'the installer file looks damaged; download it again.'
        }}
    }}
}}

$tmp = Join-Path ([IO.Path]::GetTempPath()) ('od-share-' + [guid]::NewGuid().ToString('N'))
try {{
    # 1. Find Saved Games and WARNO's folder
    $warnoDir = Join-Path (Get-SavedGames) '{warno_folder}'
    if (-not (Test-Path -LiteralPath $warnoDir)) {{
        throw "Couldn't find WARNO's folder at $warnoDir. Start WARNO once, close it, and run this again."
    }}

    # 2. WARNO must be closed: it reads mods at startup and rewrites mod\Config.ini on exit
    while (Get-Process -Name WARNO -ErrorAction SilentlyContinue) {{
        if ($env:{env_no_pause}) {{ throw 'WARNO is running. Close it and run this again.' }}
        Write-Host 'WARNO is running. Close it, then press Enter.'
        [void](Read-Host)
    }}

    # 3. Unpack the embedded mod into a temp folder and check it
    $modRoot = Join-Path $warnoDir '{mod_folder}'
    if (-not (Test-Path -LiteralPath $modRoot)) {{ [void](New-Item -ItemType Directory -Path $modRoot) }}
    $text = [IO.File]::ReadAllText($env:{env_self})
    $start = $text.IndexOf('::PAYLOAD-' + 'BEGIN')
    $start = $text.IndexOf("`n", $start) + 1
    $end = $text.IndexOf('::PAYLOAD-' + 'END')
    $b64 = $text.Substring($start, $end - $start) -replace '\s', ''
    [void](New-Item -ItemType Directory -Path $tmp)
    $zip = Join-Path $tmp 'mod.zip'
    [IO.File]::WriteAllBytes($zip, [Convert]::FromBase64String($b64))
    $stage = Join-Path $tmp 'stage'
    Expand-Archive -LiteralPath $zip -DestinationPath $stage
    Test-Hashes (Join-Path $stage $ModName)

    # 4. Replace any older copy, then check what landed
    $dest = Join-Path $modRoot $ModName
    $forms = @($ModName)  # every ActivatedMods entry that names this mod
    $oldId = ''
    if (Test-Path -LiteralPath $dest) {{
        $oldId = Get-ModId $dest  # the copy being replaced may have another ID than this one
        $inId = Get-ModId (Join-Path $stage $ModName)
        if ($oldId -and $inId -and $oldId -ne $inId) {{
            throw ('the installed copy has Workshop ID ' + $oldId + ' but this build has ID ' + $inId + '; not replacing one Workshop item with another. Remove the installed copy first if you mean to.')
        }}
        if ($oldId) {{ $forms += $oldId }}
        Remove-Item -LiteralPath $dest -Recurse -Force
    }}
    Copy-Item -LiteralPath (Join-Path $stage $ModName) -Destination $modRoot -Recurse
    Test-Hashes $dest
    # An upload writes the new Workshop item's ID into the installed Config.ini; a build ships ID = 0. Keep the
    # installed ID (rewriting that one line only), or the next upload would create a second Workshop item.
    if ($oldId -and -not (Get-ModId $dest)) {{
        $cfg = Join-Path $dest 'Config.ini'
        $utf8cfg = New-Object Text.UTF8Encoding($false)
        $cfgText = [IO.File]::ReadAllText($cfg, $utf8cfg)
        $im = [regex]::Match($cfgText, '(?m)^([ \t]*ID[ \t]*=[ \t]*)[0-9]+')
        if ($im.Success) {{
            $cfgText = $cfgText.Substring(0, $im.Index) + $im.Groups[1].Value + $oldId + $cfgText.Substring($im.Index + $im.Length)
            [IO.File]::WriteAllText($cfg, $cfgText, $utf8cfg)
            Write-Host ('Kept the installed Workshop ID ' + $oldId + ' in Config.ini (this build has ID 0).')
        }}
    }}

    # 5. Switch it on: add it to ActivatedMods in mod\Config.ini, like the game does. The game rewrites the list at
    #    startup, naming a mod with a non-zero ID by that ID and any other by its folder name, so the entry takes
    #    that form; any form already listed is this mod, which keeps its place, once.
    $newId = Get-ModId $dest
    $entry = $ModName
    if ($newId) {{ $entry = $newId; $forms += $newId }}
    $ini = Join-Path $modRoot 'Config.ini'
    $utf8 = New-Object Text.UTF8Encoding($false)
    $old = $null
    if (Test-Path -LiteralPath $ini) {{ $old = [IO.File]::ReadAllText($ini, $utf8) }}
    $nl = "`n"
    if ($old -and $old.Contains("`r`n")) {{ $nl = "`r`n" }}
    $new = $old
    $m = [regex]::Match([string]$old, '(?m)^(?<pre>[ \t]*ActivatedMods[ \t]*=[ \t]*)(?<val>[^;\r\n]*?)[ \t]*(?<cmt>;[^\r\n]*)?(?=\r?$)')
    if ($m.Success) {{
        $names = @($m.Groups['val'].Value.Split('|') | ForEach-Object {{ $_.Trim() }} | Where-Object {{ $_ }})
        $list = @()
        $placed = $false
        foreach ($n in $names) {{
            if ($forms -notcontains $n) {{ $list += $n }} elseif (-not $placed) {{ $list += $entry; $placed = $true }}
        }}
        if (-not $placed) {{ $list += $entry }}
        if (($list -join '|') -ne ($names -join '|')) {{
            $line = $m.Groups['pre'].Value + ($list -join '|')
            $cmt = $m.Groups['cmt'].Value
            if ($cmt) {{ $line += ' ' + $cmt }}
            $new = $old.Substring(0, $m.Index) + $line + $old.Substring($m.Index + $m.Length)
        }}
    }} else {{
        $c = [regex]::Match([string]$old, '(?m)^\[Config\][^\r\n]*')
        if ($c.Success) {{
            $at = $c.Index + $c.Length
            $new = $old.Substring(0, $at) + $nl + 'ActivatedMods = ' + $entry + $old.Substring($at)
        }} else {{
            $new = '[Config]' + $nl + 'ActivatedMods = ' + $entry + $nl + $old
        }}
    }}
    if ($new -cne $old) {{
        $backup = Join-Path $modRoot ('Config.ini.before-' + $ModName + '.bak')
        if ((Test-Path -LiteralPath $ini) -and -not (Test-Path -LiteralPath $backup)) {{
            Copy-Item -LiteralPath $ini -Destination $backup
        }}
        [IO.File]::WriteAllText($ini, $new, $utf8)
    }}

    # 6. Done
    Write-Host ('Installed ' + $Title + ' and switched it on.')
    Write-Host ('Start WARNO, open Operations, and pick ' + $Title + '.')
    Write-Host ("To remove it: turn it off in WARNO's Mod Center, or delete " + $dest)
}} catch {{
    Write-Host ('Install failed: ' + $_.Exception.Message) -ForegroundColor Red
    exit 1
}} finally {{
    if (Test-Path -LiteralPath $tmp) {{ Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue }}
}}
exit 0
"""


def _where() -> dict[str, str]:
    """The template fields that say where the mod goes, from the module's constants (read at each build)."""
    return dict(env_self=ENV_SELF, env_saved_games=ENV_SAVED_GAMES, env_no_pause=ENV_NO_PAUSE,
                shell_folders=SHELL_FOLDERS, saved_games_id=SAVED_GAMES_ID, warno_folder="\\".join(WARNO_FOLDER),
                mod_folder=MOD_FOLDER)


def build_cmd(name: str, title: str, files: list[tuple[str, Path]], payload: bytes) -> bytes:
    hashes = "\n".join(f"    {_q(rel)} = '{hashlib.sha256(p.read_bytes()).hexdigest().upper()}'" for rel, p in files)
    where = _where()
    script = SCRIPT.format(modname=_q(name), title=_q(title), hashes=hashes, **where)
    b64 = base64.b64encode(payload).decode("ascii")
    lines = [b64[i:i + 76] for i in range(0, len(b64), 76)]
    text = (HEADER.format(name=name, env_self=where["env_self"], env_no_pause=where["env_no_pause"]) + script
            + "::PS-END\n::PAYLOAD-BEGIN\n" + "\n".join(lines) + "\n::PAYLOAD-END\n")
    return text.replace("\n", "\r\n").encode("ascii")  # raises on any stray non-ASCII character


def readme(name: str, title: str, gen: str) -> bytes:
    text = f"""{title}
{'=' * len(title)}

Quick install (one click)
  1. Close WARNO.
  2. Double-click "Install {name}.cmd". If nothing happens when you double-click
     it inside the zip, extract the zip first (right-click, Extract All).
     If Windows warns that the file came from the internet, choose Run
     (or More info, then Run anyway).
  3. Start WARNO, open Operations and pick "{title}".

Manual install
  1. Close WARNO.
  2. Copy the "{name}" folder from this zip into
     %USERPROFILE%\\Saved Games\\EugenSystems\\WARNO\\mod\\
  3. Start WARNO, enable the mod in the Mod Center and restart the game.

How to remove it
  Turn it off in WARNO's Mod Center, or delete the folder
  %USERPROFILE%\\Saved Games\\EugenSystems\\WARNO\\mod\\{name}

Built for WARNO data version {gen}
"""
    return text.replace("\n", "\r\n").encode("ascii")


def package(src: Path, title: str, out: Path) -> Path:
    src = src.resolve()
    check(src, title)
    lone, dest = out / f"Install {src.name}.cmd", out / f"{src.name}-share.zip"
    for hook in HOOKS:
        hook(src, (lone, dest))
    files = mod_files(src)
    ini = (src / "Config.ini").read_text(encoding="utf-8", errors="replace")
    m = re.search(r"^[ \t]*ModGenVersion[ \t]*=[ \t]*(\d+)", ini, re.MULTILINE)
    cmd = build_cmd(src.name, title, files, payload_zip(src, files))
    out.mkdir(parents=True, exist_ok=True)
    lone.write_bytes(cmd)  # the one file to send when the zip isn't needed
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
        _entry(z, f"Install {src.name}.cmd", cmd)
        _entry(z, "README.txt", readme(src.name, title, m[1] if m else "unknown"))
        for rel, p in files:
            _entry(z, f"{src.name}/{rel}", p.read_bytes())
    return dest


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("built_mod_dir", type=Path)
    ap.add_argument("--title", required=True, help="the mod's title in WARNO's menu")
    ap.add_argument("--out", type=Path, help="default: share/ in the build folder (modkit.core.paths.build_root)")
    args = ap.parse_args(argv)
    try:
        dest = package(args.built_mod_dir, args.title, args.out or paths.build_root() / SHARE_FOLDER)
    except ShareError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
    lone = dest.with_name(f"Install {args.built_mod_dir.resolve().name}.cmd")
    for p in (lone, dest):
        print(f"{p} ({p.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
