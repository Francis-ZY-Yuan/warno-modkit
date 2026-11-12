"""The Operation build driver: one content of one profile (``modkit.ops.profile``) in, a gated mod folder out.

A build re-keys the profile's template to the content's scenario, generates the content's GDScript, LevelDesign and
zone files (or ships the template's script and Details as they are), packs its string table, and writes::

    <out>/<mod_name>/Config.ini, Gen/Version.ndf, Scenarios/<scenario>_<pack>.dat, the profile's loose files
    <out>/MANIFEST.tsv     one row per shipped entry, the profile's extra rows, then the dropped template files
    <out>/dumps/<file>.txt typed dumps of the generated ndfbins, when the profile asks (not shipped)

and whatever review files the profile's extra outputs write. Gates 1-6 (``modkit.ops.gates``) run in order, each
through ``modkit.core.gates.run_gate``: a failure stops the build unless the profile's ``reviewed_pending`` holds
that gate's exact message, in which case it is reported as ``REVIEW PENDING`` and the build goes on. The entry covers
the first failure that gate call raised, and the rest of that gate call did not run, so a later fault it would have
found stays hidden until the reviewed one is fixed. A pending entry that never fired is logged at the end.

``run`` builds and turns any failure into one ``FAILED:`` line and exit code 1, for any front end; ``cli`` is the
shared command line, ``--content NAME --out DIR``, on top of it.
"""
from __future__ import annotations

import argparse
import functools
import glob
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Mapping, Sequence

from modkit.core import edat, gamebuild, ndfbin, ndfrules, paths, trad
from modkit.core.gates import CheckError, check, run_gate, unfired
from modkit.core.ndfbin import Value
from modkit.core.packaging import clean_out, write_manifest, write_mod_files
from modkit.ops import INGAME_DIC
from modkit.ops import gates
from modkit.ops import items as ops_items
from modkit.ops.files import read_file, rel_source
from modkit.ops.graph import Node, build_graph, decode, encode, nodes_of, walk
from modkit.ops.items import Item, payload, read_provenance
from modkit.ops.leveldesign import (
    LD_FILE, LD_SHARED, ZONE_FILES, LdItem, derived_menu_order, leveldesign_graph, scenario_guid, zone_area,
)
from modkit.ops.packs import verify_packs, write_loose, write_packs
from modkit.ops.profile import STOCK_ASSETS, Content, OpProfile, extracted
from modkit.ops.rekey import DEF_EXTS, TXN, Rekey, ScalarEdit, def_path, dump_rows
from modkit.ops.script import BRICK_DEFAULT
from modkit.ops.strings import LANGS, StringError, payloads
from modkit.ops.zones import zone_areas_graph

PENDING = "review pending"


@dataclass
class Plan:
    """What a build ships, before it is written: the planned items, the dropped template files (inner path, why)
    and the script's roots for the script gates (the content's, or the shipped template script decoded)."""
    items: list[Item]
    dropped: list[tuple[str, str]]
    roots: list[Node]


class GateRun:
    """One build's gates under the profile's reviewed_pending: each runs through run_gate, and the pending entries
    that fired are kept, so the build can log those that did not."""

    def __init__(self, profile: OpProfile):
        self.pending = profile.reviewed_pending
        self.fired: list[tuple[str, str]] = []

    def __call__(self, name: str, fn: Callable, *args, pending=PENDING):
        """run_gate(name, fn, *args); a reviewed failure gives `pending` (for the build log)."""
        before = len(self.fired)
        out = run_gate(name, fn, *args, pending=self.pending, fired=self.fired)
        return pending if len(self.fired) > before else out

    def unfired(self) -> list[tuple[str, str]]:
        """The pending entries that never fired in this run."""
        return unfired(self.pending, self.fired)


# --------------------------------------------------------------------------- planning

MENU_ORDER_EDIT = ("MapConfiguration", "TChallengeMapInfo", "OrderToChainMission")  # (kind, class, property)


def scalar_edits(profile: OpProfile, content: Content) -> tuple[ScalarEdit, ...]:
    """The scalar edits a build applies: the content's own, else the profile's; and when none of them moves the menu
    order (MENU_ORDER_EDIT) and the template declares its own (Template.menu_order), one more that moves it to the
    content's derived order (modkit.ops.leveldesign.derived_menu_order) [[content-identity-unique]]."""
    edits = profile.scalar_edits if content.scalar_edits is None else content.scalar_edits
    t = profile.template
    if t.menu_order is None or any((e.kind, e.cls, e.prop) == MENU_ORDER_EDIT for e in edits):
        return tuple(edits)
    order = derived_menu_order(content.scenario, profile.guid_namespace)
    return (*edits, ScalarEdit(*MENU_ORDER_EDIT, Value(0x03, t.menu_order), Value(0x03, order)))


def rekey_table(profile: OpProfile, content: Content) -> Rekey:
    """The template re-keyed to the content's scenario and its GUID under the profile's namespace, menu tokens by
    the content's menu_renames, the scalar edits and the deck swap (each the content's own, else the profile's; the
    edits with the derived menu order when they move none: scalar_edits), and the profile's map swaps."""
    t = profile.template
    decks = profile.deck_swap if content.deck_swap is None else content.deck_swap
    edits = scalar_edits(profile, content)
    return Rekey(t.source, content.scenario, t.guid, scenario_guid(content.scenario, profile.guid_namespace),
                 dict(content.menu_renames), t.token_prefix, edits, profile.map_strings,
                 profile.map_trans, decks, t.kinds)


def details_files(profile: OpProfile, items: Sequence[LdItem], scenario: str) -> dict[str, bytes]:
    """The generated Details files of `items`: LD_FILE, and the zone file (ZONE_FILES) of each kind of zone the items
    hold (plan_details ships the template's otherwise). Item GUIDs are keyed by `scenario` under the profile's
    namespace; zone areas stand at the profile's ground_z."""
    ns = profile.guid_namespace
    out = {LD_FILE: encode(build_graph(leveldesign_graph(items, scenario, ns), [], LD_SHARED), "LevelDesign")}
    for addon, inner in ZONE_FILES.items():
        if any(it.addon == addon for it in items):
            out[inner] = encode(build_graph(zone_areas_graph([
                zone_area(it, scenario, ns, profile.ground_z) for it in items if it.addon == addon]), []), inner)
    return out


def plan_details(profile: OpProfile, content: Content) -> list[Item]:
    """The Details pack. With profile.details_from_template, the template's Details whole, byte for byte. Otherwise
    the LevelDesign generated from the content's items; each zone file generated (zone items) or else the
    template's; the map's copies byte for byte (modkit.ops.items). Generated files are named by content.sources."""
    t = profile.template
    if profile.details_from_template:
        check(not content.items, f"{content.name}: {len(content.items)} LevelDesign items, but the profile ships the "
                                 f"template's Details whole (details_from_template)")
        folder = t.path("details")
        return ops_items.plan_details([(inner, folder) for inner in dict(read_provenance(folder))], {})
    src = content.sources
    made = {inner: (raw, src.label(inner), src.fixture(inner))
            for inner, raw in details_files(profile, content.items, content.scenario).items()}
    details, copies = t.path("details"), extracted(profile.map_details)
    layout = [(LD_FILE, None), *((inner, details) for inner in ZONE_FILES.values()),
              *((inner, copies) for inner in profile.map_copies)]
    return ops_items.plan_details(layout, made)


def plan_assets(profile: OpProfile, content: Content) -> tuple[list[Item], list[tuple[str, str]]]:
    """Each of the profile's dictionaries in every language from the content's string table (SC from the Chinese
    column, the other seven from the English; named by content.sources), plus the template's files by the profile's
    asset rules, each menu picture of the profile's menu art taken from its stock scenario, or generated, instead
    (modkit.ops.items.menu_art). Returns (items, dropped: the template's files not shipped)."""
    t, blobs = profile.template, payloads(content.strings)
    dics = [(f"Localisation/{content.scenario}/{name}-{lang}.dic", blobs[(name, lang)], content.sources.dic(name, lang))
            for name in profile.dictionaries for lang in LANGS]
    items, dropped = ops_items.plan_assets(dics, t.path("assets"), t.asset_subtrees, profile.asset_rules, t.source,
                                           content.scenario)
    art = {name: (stock, extracted(STOCK_ASSETS.format(stock)))
           for name, stock in profile.menu_art.items() if isinstance(stock, str)}
    made = {name: make(content) for name, make in profile.menu_art.items() if not isinstance(make, str)}
    items, given_up = ops_items.menu_art(items, art, t.source, content.scenario, made)
    return items, dropped + given_up


def pack_order(profile: OpProfile) -> tuple[str, ...]:
    """The profile's packs, then its extra packs, each once: an extra pack names a new pack (extra_items adds to the
    profile's own)."""
    names = (*profile.packs, *(pack.name for pack in profile.extra_packs))
    check(len(set(names)) == len(names), f"pack names repeat: {list(names)}; an extra pack must name a new pack "
                                         f"(extra_items adds files to the profile's own packs)")
    return names


def extra_items(profile: OpProfile, content: Content) -> list[Item]:
    """The profile's extra items (into its own packs), its extra packs' items, then its loose files, each held to
    its pack."""
    pack_order(profile)
    out: list[Item] = []
    for more in profile.extra_items:
        planned = list(more(content))
        for it in planned:
            check(it.pack in profile.packs, f"extra items planned an item for pack {it.pack}, not one of the "
                                            f"profile's packs {list(profile.packs)}: {it.path}")
        out += planned
    for pack in profile.extra_packs:
        planned = list(pack.plan(content))
        for it in planned:
            check(it.pack == pack.name, f"extra pack {pack.name} planned an item for pack {it.pack}: {it.path}")
        out += planned
    for loose in profile.extra_loose_files:
        planned = list(loose(content))
        for it in planned:
            check(it.pack == "Loose", f"loose files planned an item for pack {it.pack}: {it.path}")
        out += planned
    return out


def plan(profile: OpProfile, content: Content) -> Plan:
    """Everything the build ships: Definition (the template re-keyed, the GDScript the content's unless its script is
    None), Details and Assets, then the profile's extra items; and the dropped template files."""
    t, src = profile.template, content.sources
    generated, roots = {}, None
    if content.script is not None:
        tpl, _, _ = decode(read_file(t.gdscript()))
        roots, exports = content.script(tpl)
        generated["GDScript"] = (encode(build_graph(roots, exports), "GDScript"), src.label("GDScript"),
                                 src.fixture("GDScript"))
    items = ops_items.plan_definition(rekey_table(profile, content), t.path("definition"), generated)
    items += plan_details(profile, content)
    assets, dropped = plan_assets(profile, content)
    items += assets + extra_items(profile, content)
    seen: set[tuple[str, str]] = set()
    for it in items:
        check((it.pack, it.path) not in seen, f"{it.pack}:{it.path} is planned twice")
        seen.add((it.pack, it.path))
    if roots is None:  # the template's script, re-keyed: the script gates read it decoded
        gd = next(it for it in items if it.path == def_path("GDScript", TXN, content.scenario))
        roots = nodes_of(decode(payload(gd))[0])
    dropped = [(rel_source(t.path("definition"), def_path(kind, ext, t.source)), why)
               for kind, why in t.dropped for ext in DEF_EXTS] \
        + [(rel_source(t.path("assets"), p), why) for p, why in dropped]
    return Plan(items, dropped, list(roots))


# --------------------------------------------------------------------------- gates

def sc_dictionaries() -> list[str]:
    """Every stock Simplified-Chinese dictionary of the extraction: the characters the game's font has."""
    return sorted(glob.glob(os.path.join(str(paths.extracted_root()), "**", "*-SC.dic"), recursive=True))


def check_generated(profile: OpProfile, content: Content, items: list[Item], run: GateRun | None = None) -> str:
    """Gate 2 on every generated ndfbin: canonical layout, only stock shapes (plus the content's admitted ones on
    its script), and the game's load-time property rules."""
    g = run or GateRun(profile)
    gd_path = def_path("GDScript", TXN, content.scenario)
    generated = [it for it in items if it.fixture is not None]
    canonical = functools.partial(gates.check_canonical, import_rule=profile.import_rule)
    shapes, game_checked = [], 0
    for it in generated:
        raw = payload(it)
        g("canonical", canonical, raw, LD_SHARED if it.path == LD_FILE else frozenset(), it.path)
        stock, n = gates.survey_shapes(profile.shape_globs("GDScript" if it.path == gd_path else it.path), 16)
        extra = ""
        if it.path == gd_path and content.extra_shapes:
            stock.classes |= {cls for cls, _, _, _ in content.extra_shapes}
            stock.props |= {(cls, name, tag) for cls, name, tag, _ in content.extra_shapes}
            stock.targets |= {(cls, name, to) for cls, name, _, to in content.extra_shapes if to is not None}
            extra = f" + {len(content.extra_shapes)} admitted"
        objects = g("shapes", gates.check_shapes, raw, stock, it.path)
        shapes.append(f"{it.fixture.removesuffix('.txt')} {objects} objects vs {n} stock files{extra}")
        checked = g("ndfrules", ndfrules.check_file, raw, it.path)
        game_checked += checked if isinstance(checked, int) else 0
    return (f"{len(generated)} files canonical, only stock shapes ({'; '.join(shapes)}); all {game_checked} objects "
            f"pass the game's load-time property checks (ndfrules)")


def check_script(profile: OpProfile, content: Content, p: Plan, run: GateRun | None = None) -> list[str]:
    """Gate 3: bindings, tokens, references, arrivals, tiers and the script's mission gates, then the profile's extra
    gates. Returns the log lines: bindings, tiers, mission, then one per extra gate."""
    g = run or GateRun(profile)
    items, roots, scenario = p.items, p.roots, content.scenario
    gd = next(it for it in items if it.path == def_path("GDScript", TXN, scenario))
    ld = next((it for it in items if it.path == LD_FILE), None)
    details = {it.path: payload(it) for it in items if it.pack == "Details"}
    deploy = gates.has_deployment_phase(content.items)
    ingame = extracted(INGAME_DIC)
    tokens = functools.partial(gates.check_tokens, global_tokens=profile.template.global_tokens, ingame_dic=ingame)
    bound = (g("binding", gates.check_binding, payload(gd), payload(ld)) if ld is not None
             else "0 (no LevelDesign shipped)")
    toks, buttons = g("tokens", tokens, items, scenario, LANGS, pending=(PENDING, PENDING))
    refs = g("references", gates.check_references, items, scenario, LANGS)
    rl, ac = g("arrivals", gates.check_arrivals, content.items, details, content.tiered_arrivals,
               pending=(PENDING, PENDING))
    tiers = g("tiers", gates.check_tiers, content, roots, details, profile.player_camp, profile.enemy_camp)
    pins = g("objective-pins", gates.check_objective_pins, roots)
    lasting = g("never-finishing", gates.check_never_finishing, roots, content.blocking_objectives)
    objectives = sum(nd.cls in gates.OBJECTIVES for nd in walk(roots))
    lines = [f"{bound} GdItems tags bind 1:1; {rl} player reinforcement locations and {ac} aerial corridors for units "
             f"bought after the launch, each ending in a player deployment zone of the shipped Details or tiered "
             f"({tiers}; gate 3 tiers); {pins} objective map pins, each on a place; {lasting} never-finishing script "
             f"actions, {gates.stalling_containers(roots)} containers that never finish and {objectives} objectives "
             f"({len(content.blocking_objectives)} reviewed to hold their Sequential), none with a node after it in a "
             f"Sequential or beside others in a loop, and no ModifyUnit* in a Sequential; {toks} loc tokens in all "
             f"{len(LANGS)} languages ({buttons} dialog-button tokens in the game's INGAME dictionary); {refs} new-id "
             f"references resolve",
             f"{tiers} tiered reinforcement locations, each ending in one command zone forced to {profile.player_camp} "
             f"at load and handed to {profile.enemy_camp} later; every other player arrival ends in a player "
             f"deployment zone" if deploy else "no deployment phase (not checked)"]
    ends, funnel = g("end-funnel", gates.check_end_funnel, roots, profile.end_exports, pending=(PENDING, True))
    guarded = g("empty-group-guard", gates.check_empty_group_guard, roots) if deploy else None
    zone = g("zone-tags", gates.check_zone_tags, roots, details, pending=defaultdict(lambda: PENDING))
    lines.append(
        f"{ends} TriggerEndGame, "
        + (f"each under {' or '.join(profile.end_exports)}" if funnel else "no end funnel (not checked)") + "; "
        + (f"{guarded} objective failure tests on an empty unit group, each after a WaitCondition that it holds a "
           f"unit" if guarded is not None else "no deployment phase (empty-group guard not checked)") + "; "
        f"{g('dialog-text', gates.check_dialog_text, roots, content.strings)} dialog texts without %1..%9; "
        f"{g('rules', gates.check_rules, roots)} game rules without {', '.join(gates.RULES_OMITTED)}; "
        f"{zone['zone lookups']} zone lookups each in exactly one shipped polygon, {zone['detectors']} detectors on "
        f"circles, {zone['zone items']} zone items inside their own polygon, {zone['command zones']} command zones "
        f"apart; {g('smart-orders', gates.check_smart_orders, roots)} smart-ordered groups, none ordered again after "
        f"its smart order in a Sequential; {g('prod-menu-switch', gates.check_prod_menu_switch, content, roots)} HUD "
        f"restores with the buy-menu switch "
        f"{'Default' if content.prod_menu_switch == BRICK_DEFAULT else 'ForceHide'} (Content.prod_menu_switch); "
        f"{g('script-effects', gates.check_script_effects, payload(gd))} script effect launches, each a "
        f"self-contained GameFx effect; {g('created-in-zone', gates.check_created_in_zone, roots, details)} "
        f"CreateUnitOnPosition, each inside the shipped playable zone")
    lines += run_extra_gates(profile, items, content, g)
    return lines


def run_extra_gates(profile: OpProfile, items: list[Item], content: Content, run: GateRun | None = None) -> list[str]:
    """The profile's extra gates, in order, each through run_gate. Returns one log line each."""
    g = run or GateRun(profile)
    return [f"{gate.name}: {g(gate.name, gate.check, items, content)}" for gate in profile.extra_gates]


def check_dump_rows(profile: OpProfile, content: Content, items: list[Item], run: GateRun | None = None) -> str:
    """Gate 4: every re-keyed file's typed dump differs from stock only by the dump rows, and every row fires."""
    g = run or GateRun(profile)
    rows, fired_all, rekeyed, changed = dump_rows(rekey_table(profile, content)), set(), 0, 0
    for it in items:
        if it.stock is None:
            continue
        report, fired = g("dump-diff", gates.check_dump_diff, it, rows, pending=([], set()))
        fired_all |= fired
        rekeyed, changed = rekeyed + 1, changed + len(report)

    def every_row_fires() -> None:
        unfired_rows = [r.label for r in rows if r.label not in fired_all]
        check(not unfired_rows, f"dump rows that changed nothing: {unfired_rows}")

    g("dump-rows", every_row_fires)
    return f"{rekeyed} re-keyed files differ from stock only by the {len(rows)} dump rows ({changed} lines changed)"


def check_definition(profile: OpProfile, content: Content, items: list[Item], run: GateRun | None = None) -> str:
    """Gate 5's game-build checks: the Definition pack in build 210942's layout (gates.check_definition_layout), and
    every class and property of every CNDF entry the build ships in stock's (gates.check_stock_classes; the content's
    admitted shapes pass too)."""
    g = run or GateRun(profile)
    definition = {it.path: payload(it) for it in items if it.pack == "Definition"}
    kinds = g("definition-layout", gates.check_definition_layout, definition, content.scenario)
    stock = gates.stock_classes()
    admitted = {(cls, prop) for cls, prop, _, _ in content.extra_shapes}
    shipped = [(f"{it.pack}:{it.path}", payload(it)) for it in items]
    read = g("stock-classes", gates.check_stock_classes, shipped, stock, admitted, pending=(PENDING, PENDING))
    files, objects = read
    return (f"{kinds} kinds in NDF/Scenarios/{content.scenario}/, each .txn with its .txn.tag and a .dbg of one line "
            f"per object; every class and property of {files} files ({objects} objects) is in the {stock.files} stock "
            f"files'" + (f" or among {len(admitted)} admitted" if admitted else ""))


# --------------------------------------------------------------------------- writing

def write_dumps(items: list[Item], out_dir: str) -> list[str]:
    """dumps/<fixture>: the typed dump of every generated ndfbin (an Item's `fixture` names it), for review."""
    folder = os.path.join(out_dir, "dumps")
    os.makedirs(folder, exist_ok=True)
    out = []
    for it in items:
        if it.fixture is None:
            continue
        nb, hdr, _ = decode(payload(it))
        path = os.path.join(folder, it.fixture)
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(ndfbin.Dumper(nb, typed=True).dump(it.path, hdr))
        out.append(path)
    return out


def write(profile: OpProfile, content: Content, p: Plan, out_dir: str, run: GateRun | None = None) -> list[str]:
    """The mod folder, the manifest, the loose files, the dumps and the review outputs under `out_dir`, a previous
    build's folders removed first (only inside the profile's build_root); then gate 6, every pack read back. Returns
    the log lines."""
    g = run or GateRun(profile)
    packs = pack_order(profile)
    clean_out(out_dir, (content.mod_name, "dumps") if profile.dumps else (content.mod_name,), profile.build_root)
    mod_root = os.path.join(out_dir, content.mod_name)
    pack_paths = write_packs(p.items, mod_root, content.scenario, packs)
    write_mod_files(mod_root, content.mod_name, mod_id=profile.mod_id, extra_config_rows=profile.extra_config_rows)
    manifest = write_manifest(p.items, p.dropped, out_dir, packs=packs, extra_manifest_rows=profile.extra_manifest_rows)
    loose = write_loose(p.items, mod_root)
    log = [f"wrote {mod_root} (Config.ini, Gen/Version.ndf, {len(pack_paths)} packs"
           + (f", {len(loose)} loose files)" if loose else ")"),
           f"wrote {manifest} ({len(p.items)} entries, {len(p.dropped)} dropped sources)"]
    if profile.dumps:
        log.append(f"wrote {len(write_dumps(p.items, out_dir))} dumps in {os.path.join(out_dir, 'dumps')}")
    log += [f"wrote {output(content, out_dir)}" for output in profile.extra_outputs]
    print("gate 6 packs read back:")
    g("read-back", verify_packs, p.items, pack_paths)
    return log


# --------------------------------------------------------------------------- the build

def build(profile: OpProfile, content: Content, out_dir: str) -> list[Item]:
    """Gates 1-5, then the mod folder under `out_dir`, then gate 6; then a line for each reviewed-pending entry that
    did not fire. Returns the planned items."""
    warning = gamebuild.build_warning()
    if warning:
        print(warning, file=sys.stderr)  # the console only; never a file of the output
    g, scenario = GateRun(profile), content.scenario
    print(f"{content.name}: {scenario} (GUID {ndfbin.fmt_guid(scenario_guid(scenario, profile.guid_namespace))}, mod "
          f"{content.mod_name}), {len(content.items)} LevelDesign items"
          + ("" if content.script is not None else "; the template's script"))
    print("gate 1 strings: " + str(g("strings", gates.check_strings, content.name, content.strings,
                                     profile.dictionaries, content.menu_tokens, sc_dictionaries())))
    p = plan(profile, content)
    print(f"gate 2 generated: {check_generated(profile, content, p.items, g)}")
    script = check_script(profile, content, p, g)
    print(f"gate 3 bindings: {script[0]}")
    print(f"gate 3 tiers: {script[1]}")
    print(f"gate 3 mission: {script[2]}")
    for line in script[3:]:
        print(f"gate 3 {line}")
    print(f"gate 4 dump diff: {check_dump_rows(profile, content, p.items, g)}")
    package = g("package", gates.check_package, p.items, scenario)
    print("gate 5 package: " + (PENDING if package == PENDING else
                                f"all {package} entries lie under {scenario}; no Gameplay file"))
    print(f"gate 5 definition: {check_definition(profile, content, p.items, g)}")
    for line in write(profile, content, p, out_dir, g):
        print(line)
    for name, message in g.unfired():
        print(f"REVIEW PENDING, did not fire: {name}: {message} (the gate passes, or fails another way: close or "
              f"update the review)")
    return p.items


# --------------------------------------------------------------------------- front ends

FAILURES = (CheckError, edat.EdatError, trad.TradError, StringError, OSError, ValueError, paths.NotConfigured)


def _utf8_streams() -> None:
    for stream in (sys.stdout, sys.stderr):  # gate messages carry Chinese; the console may be cp1252
        try:
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")
        except (AttributeError, ValueError):
            pass


def run(profile_factory: Callable[[], OpProfile], content_factory: Callable[[], Content], out_dir: str) -> int:
    """build(profile_factory(), content_factory(), out_dir) for any front end: 0 on success; a failed gate, a missing
    source or an unconfigured extraction prints one 'FAILED: ...' line and gives 1, never a traceback."""
    _utf8_streams()
    try:
        build(profile_factory(), content_factory(), out_dir)
        return 0
    except FAILURES as exc:
        return _failed(exc)


def _failed(exc: BaseException) -> int:
    """The one 'FAILED: ...' line every front end prints for an expected failure; gives the exit code 1."""
    print(f"FAILED: {exc}", file=sys.stderr)
    return 1


def cli(profile_factory: Callable[[], OpProfile], contents: Mapping[str, Callable[[], Content]],
        argv: Sequence[str] | None = None, *, description: str = "Build an Operation mod.",
        default_out: Callable[[str], str] | None = None) -> int:
    """`--content NAME --out DIR`: run(profile_factory, contents[NAME], DIR), DIR defaulting to default_out(NAME)
    when given (else --out is required). A default that cannot be resolved prints the same one FAILED line as run
    and gives 1."""
    _utf8_streams()
    ap = argparse.ArgumentParser(description=description)
    ap.add_argument("--content", choices=sorted(contents), required=True, help="what to build")
    ap.add_argument("--out", required=default_out is None,
                    help="output directory" + ("" if default_out is None else " (default: the op's build folder)"))
    args = ap.parse_args(argv)
    try:
        out_dir = os.path.abspath(args.out or default_out(args.content))
    except FAILURES as exc:
        return _failed(exc)
    return run(profile_factory, contents[args.content], out_dir)
