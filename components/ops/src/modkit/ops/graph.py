"""The object-graph builder: describe ndfbin objects as Python nodes, encode them the way Eugen's files are laid out.

A graph is a list of ``Node`` objects (class name, ``(property, value spec)`` pairs in stock order, optional export
path). ``build_graph`` turns roots and exports into an ``ndfbin.NdfBin`` with stock table order (CLAS/PROP/STRG and
import indices in first-use order, TRAN = IMPR then EXPR preorder, TOPO = exported + unreferenced, one CHNK), and
``encode`` writes it and proves it decodes back. ``template_scalars`` and ``with_scalars`` copy scalar properties from
a stock template object.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Iterable, Iterator

from modkit.core import ndfbin
from modkit.core.gates import check
from modkit.core.ndfbin import Value, decode  # noqa: F401 - decode is core's; the ops modules import it from here

# --------------------------------------------------------------------------- ndfbin helpers


def encode(nb: ndfbin.NdfBin, what: str) -> bytes:
    """Encode `nb` with its own compression mode and prove the file decodes back to it."""
    image = ndfbin.encode_image(nb)
    raw = ndfbin.encode_file(nb)
    _, back = ndfbin.decompress(raw)
    check(back == image, f"{what}: encoded file does not decode to its image")
    return raw


def all_values(nb: ndfbin.NdfBin) -> Iterable[tuple[ndfbin.Obj, int, Value]]:
    for ob in nb.objects:
        for pi, v in ob.props:
            for x in ndfbin.iter_values(v):
                yield ob, pi, x


# --------------------------------------------------------------------------- object-graph builder

class Node:
    """An object to emit: class name, (property, value spec) pairs in stock order, export path.

    Value specs: a Node (object reference), Imp (import reference), Str (STRG entry),
    a ndfbin.Value (scalar, written as is), a list of specs (0x11 list) or a Map of spec pairs (0x12, an NDF MAP).
    """

    def __init__(self, cls: str, props: Iterable[tuple[str, object]] = (), export: str | None = None):
        self.cls = cls
        self.props = list(props)
        self.export = export


def prop_nodes(spec: object) -> Iterator[Node]:
    """The nodes a property value spec references: itself if a Node, the Nodes of a list (nested lists included)."""
    if isinstance(spec, Node):
        yield spec
    elif isinstance(spec, list):
        for x in spec:
            yield from prop_nodes(x)
    elif isinstance(spec, Map):
        for k, x in spec.pairs:
            yield from prop_nodes(k)
            yield from prop_nodes(x)


def walk(roots: Iterable[Node]) -> Iterator[Node]:
    """Every node reachable from `roots` through properties (lists included), each once, depth first in order."""
    seen: set[int] = set()
    stack = list(roots)[::-1]
    while stack:
        nd = stack.pop()
        if id(nd) in seen:
            continue
        seen.add(id(nd))
        yield nd
        stack += [k for _, spec in nd.props for k in prop_nodes(spec)][::-1]


def nodes_of(nb: ndfbin.NdfBin) -> list[Node]:
    """A decoded file as Nodes, one per object in index order: object references become the Nodes, import references
    Imp(path), lists lists, and every other value stays as it is; exported objects get their export path. The gates
    read a stock or re-keyed script this way."""
    nodes = [Node(nb.cname(ob.cls)) for ob in nb.objects]
    imports = {i: path for path, i in ndfbin.tree_paths(nb, nb.imports)}
    for path, i in ndfbin.tree_paths(nb, nb.exports):
        nodes[i].export = path

    def spec(v: Value) -> object:
        if v.tag == 0x09 and v.v.kind == ndfbin.REF_OBJECT:
            return nodes[v.v.index]
        if v.tag == 0x09 and v.v.kind == ndfbin.REF_IMPORT:
            return Imp(imports[v.v.index])
        return [spec(x) for x in v.v] if v.tag == 0x11 else v

    for nd, ob in zip(nodes, nb.objects):
        nd.props = [(nb.pname(pi), spec(v)) for pi, v in ob.props]
    return nodes


@dataclass(frozen=True)
class Imp:
    path: str  # '$/GFX/Unit/Descriptor_Unit_X'


@dataclass(frozen=True)
class Str:
    text: str
    tag: int = 0x07  # 0x1C for a resource path


@dataclass(frozen=True)
class Map:
    """An NDF MAP value (0x12): (key, value) spec pairs in file order, as a TActionCall's NamedParams
    (('parDuration', a TConstantInteger) in GameFx's FX_Vehicule_Dest_Fire_FireAndForget)."""
    pairs: tuple[tuple[object, object], ...]


def i32(n: int) -> Value:
    return Value(0x02, n)


def u32(n: int) -> Value:
    return Value(0x03, n)


def f32(x: float) -> Value:
    return Value(0x05, float(x))


def loc(token: str) -> Value:
    return ndfbin.loc_value(token)


TRUE = Value(0x00, 1)
SECTIONS = ("OBJE", "TOPO", "CHNK", "CLAS", "PROP", "STRG", "TRAN", "IMPR", "EXPR")


@dataclass
class _T:
    """Path-tree node used for both IMPR and EXPR before encoding."""
    obj: object = None  # Node (EXPR), import index (IMPR) or None
    kids: dict[str, "_T"] = field(default_factory=dict)


def _node_refs(spec: object) -> Iterable[Node]:
    if isinstance(spec, Node):
        yield spec
    elif isinstance(spec, list):
        for x in spec:
            yield from _node_refs(x)
    elif isinstance(spec, Map):
        for k, x in spec.pairs:
            yield from _node_refs(k)
            yield from _node_refs(x)


def _export_tree(exports: list[Node]) -> _T:
    """EXPR tree in the given order; a property-less TBaseClass for every folder node
    except `$` and `$/GDScript` (the Eugen convention)."""
    top = _T()
    for nd in exports:
        parts = nd.export.split("/")
        check(parts[0] == "$", f"export {nd.export} does not start at $")
        cur = top
        for part in parts[1:]:
            cur = cur.kids.setdefault(part, _T())
        check(cur.obj is None, f"duplicate export {nd.export}")
        cur.obj = nd

    def fill(t: _T, path: str) -> None:
        if t.obj is None and path not in ("$", "$/GDScript", "$/GDScript/Resources"):  # stock: no object
            t.obj = Node("TBaseClass", (), export=path)
        for name, kid in t.kids.items():
            fill(kid, f"{path}/{name}")

    fill(top, "$")
    return top


def _tree_objects(t: _T) -> Iterable[Node]:
    if isinstance(t.obj, Node):
        yield t.obj
    for kid in t.kids.values():
        yield from _tree_objects(kid)


def _object_order(roots: list[Node], tree: _T | None) -> list[Node]:
    """Breadth-first from each root in turn, then still-unreached exports in EXPR order (stock layout)."""
    order: list[Node] = []
    seen: set[int] = set()

    def bfs(start: Node) -> None:
        if id(start) in seen:
            return
        seen.add(id(start))
        queue = deque([start])
        while queue:
            nd = queue.popleft()
            order.append(nd)
            for _, spec in nd.props:
                for kid in _node_refs(spec):
                    if id(kid) not in seen:
                        seen.add(id(kid))
                        queue.append(kid)

    for r in roots:
        bfs(r)
    for nd in _tree_objects(tree) if tree else ():
        bfs(nd)
    return order


def build_graph(roots: list[Node], exports: list[Node],
                shared_props: frozenset[str] = frozenset()) -> ndfbin.NdfBin:
    """Encode an object graph the way Eugen's files are laid out (rules checked on stock files):
    CLAS/PROP/STRG and import indices in first-use order, TRAN = IMPR then EXPR preorder,
    one PROP per (name, class) except `shared_props` (owned by the first class using them),
    TOPO = exported + unreferenced, one CHNK."""
    tree = _export_tree(exports) if exports else None
    order = _object_order(roots, tree)
    index = {id(nd): k for k, nd in enumerate(order)}
    nb = ndfbin.NdfBin(mode=ndfbin.MODE_ZSTD, sections=list(SECTIONS), section_layout=list(SECTIONS))
    for nd in order:
        nb.intern_class(nd.cls)
    imports: list[str] = []
    owners: dict[str, int] = {}

    def resolve(spec: object) -> Value:
        if isinstance(spec, Value):
            return Value(spec.tag, spec.v, spec.extra)
        if isinstance(spec, Node):
            k = index[id(spec)]
            return Value(0x09, ndfbin.Ref(ndfbin.REF_OBJECT, k, nb.intern_class(order[k].cls)))
        if isinstance(spec, Imp):
            if spec.path not in imports:
                imports.append(spec.path)
            return Value(0x09, ndfbin.Ref(ndfbin.REF_IMPORT, imports.index(spec.path)))
        if isinstance(spec, Str):
            return Value(spec.tag, nb.intern_string(spec.text))
        if isinstance(spec, list):
            return Value(0x11, [resolve(x) for x in spec])
        if isinstance(spec, Map):
            return Value(0x12, [(resolve(k), resolve(x)) for k, x in spec.pairs])
        raise TypeError(f"bad value spec {spec!r}")

    for nd in order:
        ci = nb.intern_class(nd.cls)
        ob = ndfbin.Obj(ci)
        for name, spec in nd.props:
            owner = owners.setdefault(name, ci) if name in shared_props else ci
            ob.props.append((nb.intern_prop(name, owner), resolve(spec)))
        nb.objects.append(ob)

    def encode_tree(t: _T, name: str, obj_index: Callable[[object], int]) -> ndfbin.Node:
        node = ndfbin.Node(nb.intern_tran(name), obj_index(t.obj))
        node.children = [encode_tree(kid, kname, obj_index) for kname, kid in t.kids.items()]
        return node

    if imports:  # IMPR first: its names come first in TRAN
        itree = _T()
        for k, path in enumerate(imports):
            cur = itree
            for part in path.split("/")[1:]:
                cur = cur.kids.setdefault(part, _T())
            cur.obj = k
        nb.imports = encode_tree(itree, "$", lambda o: ndfbin.NONE_IDX if o is None else o)
    if tree:
        nb.exports = encode_tree(tree, "$", lambda o: ndfbin.NONE_IDX if o is None else index[id(o)])
    referenced = {x.v.index for _, _, x in all_values(nb) if x.tag == 0x09 and x.v.kind == ndfbin.REF_OBJECT}
    exported = {index[id(nd)] for nd in order if nd.export}
    nb.topo = sorted(exported | (set(range(len(order))) - referenced))
    nb.chnk = [(0, len(order))]
    return nb


# --------------------------------------------------------------------------- stock templates

def template_scalars(tpl: ndfbin.NdfBin, spec: tuple[int, str, tuple[str, ...]]) -> list[tuple[str, Value]]:
    """Scalar properties of a stock template object, value tags and order kept."""
    idx, cls, drop = spec
    ob = tpl.objects[idx]
    check(tpl.cname(ob.cls) == cls, f"template #{idx} is {tpl.cname(ob.cls)}, expected {cls}")
    out = []
    for pi, v in ob.props:
        name = tpl.pname(pi)
        check(v.tag not in (0x07, 0x09, 0x11, 0x12, 0x1C, 0x22), f"template #{idx}.{name} is not a scalar")
        if name not in drop:
            out.append((name, Value(v.tag, v.v)))
    check(len(out) == len(ob.props) - len(drop), f"template #{idx}: cannot drop {drop}")
    return out


def with_scalars(props: list[tuple[str, Value]], overrides: Iterable[tuple[str, int]],
                 order: list[str] = ()) -> list[tuple[str, Value]]:
    """`props` with each (name, value) override as an int32: replaced in place, or inserted before the first
    property that follows `name` in `order` (a stock object's property order)."""
    out = list(props)
    for name, value in overrides:
        k = next((i for i, (n, _) in enumerate(out) if n == name), None)
        if k is not None:
            check(out[k][1].tag == 0x02, f"override {name}: not an int32 property")
            out[k] = (name, i32(value))
            continue
        check(name in order, f"override {name}: no stock position for a new property")
        later = order[order.index(name) + 1:]
        out.insert(next((i for i, (n, _) in enumerate(out) if n in later), len(out)), (name, i32(value)))
    return out
