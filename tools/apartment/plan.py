"""Floor-plan parser + wall solver (pure Python, no Max).

Reads the Schematex-style plan (plan_two_bed.txt) and resolves it into
geometry in plan metres (origin top-left, y down):
  rooms      {id: Room}
  walls      [WallSeg]  exterior (outside the room edge) and interior
                         (centred on the shared edge), already split around
                         every door, opening and window
  openings   [Opening]  doors / openings / windows with their wall segment
  furniture  [Furniture]
Convert to 3ds Max centimetres with to_max(x, y) -> (x*100, -y*100).
"""
import math
import re
from dataclasses import dataclass, field

DOOR_W, BETWEEN_W, WINDOW_W = 0.9, 0.8, 1.2


@dataclass
class Room:
    id: str
    name: str
    x: float
    y: float
    w: float
    d: float

    @property
    def x1(self):
        return self.x + self.w

    @property
    def y1(self):
        return self.y + self.d

    def contains(self, px, py):
        return self.x < px < self.x1 and self.y < py < self.y1


@dataclass
class Edge:
    """A straight piece of room boundary. axis 'h' (constant y) or 'v'."""
    axis: str
    c: float             # the constant coordinate
    a: float             # start along the edge
    b: float             # end along the edge
    kind: str            # 'ext' | 'int'
    rooms: tuple         # one room (ext) or two (int)
    outward: int = 0     # ext only: +1 / -1, direction (in c) away from the room


@dataclass
class Opening:
    kind: str            # 'door' | 'opening' | 'window'
    edge: Edge
    a: float
    b: float
    sill: float
    head: float
    style: str = ""      # 'bifold', 'sliding', 'swing in', hinge side...
    rooms: tuple = ()
    id: str = ""


@dataclass
class WallSeg:
    axis: str
    c0: float            # wall slab extent across (min, max) in the constant axis
    c1: float
    a: float
    b: float
    z0: float
    z1: float
    kind: str


@dataclass
class Furniture:
    kind: str
    room: str
    x: float
    y: float
    size: tuple = None


@dataclass
class Plan:
    title: str = ""
    ext_t: float = 0.20
    int_t: float = 0.20
    rooms: dict = field(default_factory=dict)
    edges: list = field(default_factory=list)
    openings: list = field(default_factory=list)
    walls: list = field(default_factory=list)
    furniture: list = field(default_factory=list)

    # ------------------------------------------------------------ queries
    def inside(self, px, py):
        return any(r.contains(px, py) for r in self.rooms.values())

    def footprint(self):
        xs = [r.x for r in self.rooms.values()] + [r.x1 for r in self.rooms.values()]
        ys = [r.y for r in self.rooms.values()] + [r.y1 for r in self.rooms.values()]
        return min(xs), min(ys), max(xs), max(ys)


def to_max(x, y):
    return x * 100.0, -y * 100.0


def _overlap(a0, a1, b0, b1):
    lo, hi = max(a0, b0), min(a1, b1)
    return (lo, hi) if hi - lo > 1e-6 else None


def parse(text, height=2.7):
    p = Plan()
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        tok = re.findall(r'"[^"]*"|\S+', line)
        head = tok[0]
        if head == "floorplan":
            p.title = tok[1].strip('"')
        elif head == "wall":
            t = float(tok[tok.index("thickness") + 1])
            if tok[1] == "exterior":
                p.ext_t = t
            else:
                p.int_t = t
        elif head == "room":
            rid, name = tok[1], tok[2].strip('"')
            w, d = (float(v) for v in tok[tok.index("size") + 1].split("x"))
            if tok[3] == "at":
                x, y = (float(v) for v in tok[4].split(","))
            else:
                rel, ref = tok[3], p.rooms[tok[4]]
                x, y = {"right-of": (ref.x1, ref.y), "below": (ref.x, ref.y1),
                        "left-of": (ref.x - w, ref.y), "above": (ref.x, ref.y - d)}[rel]
            p.rooms[rid] = Room(rid, name, x, y, w, d)
        elif head == "furniture":
            kind, room = tok[1], tok[3]
            x, y = (float(v) for v in tok[5].split(","))
            size = None
            if "size" in tok:
                size = tuple(float(v) for v in tok[tok.index("size") + 1].split("x"))
            p.furniture.append(Furniture(kind, room, x, y, size))
    _solve_edges(p)
    _place_openings(p, text, height)
    _build_walls(p, height)
    return p


def _room_edges(r):
    # (side, axis, c, a, b, outward sign in c)
    return [("north", "h", r.y, r.x, r.x1, -1), ("south", "h", r.y1, r.x, r.x1, +1),
            ("west", "v", r.x, r.y, r.y1, -1), ("east", "v", r.x1, r.y, r.y1, +1)]


def _solve_edges(p):
    """Split every room side into shared (interior) and outside (exterior) pieces."""
    rooms = list(p.rooms.values())
    seen_int = set()
    for r in rooms:
        for side, axis, c, a, b, out in _room_edges(r):
            shared = []
            for o in rooms:
                if o is r:
                    continue
                for oside, oaxis, oc, oa, ob, oout in _room_edges(o):
                    if oaxis == axis and abs(oc - c) < 1e-6 and oout == -out:
                        ov = _overlap(a, b, oa, ob)
                        if ov:
                            shared.append((ov, o))
            shared.sort(key=lambda s: s[0][0])
            cur = a
            for (lo, hi), o in shared:
                if lo - cur > 1e-6:
                    p.edges.append(Edge(axis, c, cur, lo, "ext", (r.id,), out))
                key = (axis, round(c, 4), round(lo, 4), round(hi, 4))
                if key not in seen_int:
                    seen_int.add(key)
                    p.edges.append(Edge(axis, c, lo, hi, "int", tuple(sorted((r.id, o.id)))))
                cur = hi
            if b - cur > 1e-6:
                p.edges.append(Edge(axis, c, cur, b, "ext", (r.id,), out))


def _edge_for(p, room, side=None, other=None):
    r = p.rooms[room]
    if other:
        pair = tuple(sorted((room, other)))
        for e in p.edges:
            if e.kind == "int" and e.rooms == pair:
                return e
        raise ValueError("no shared wall between %s and %s" % (room, other))
    for s, axis, c, a, b, out in _room_edges(r):
        if s == side:
            for e in p.edges:
                if (e.kind == "ext" and e.rooms == (room,) and e.axis == axis
                        and abs(e.c - c) < 1e-6 and e.a >= a - 1e-6 and e.b <= b + 1e-6):
                    return e
    return None          # the side is interior (e.g. a window on a shared wall)


def _place_openings(p, text, height):
    windows = {}
    for raw in text.splitlines():
        line = raw.split("#", 1)[0].strip()
        tok = line.split()
        if not tok or tok[0] not in ("door", "opening", "window"):
            continue
        kind = tok[0]
        if tok[1] == "between":
            e = _edge_for(p, tok[2], other=tok[3])
            rest, rooms = tok[4:], (tok[2], tok[3])
            width = BETWEEN_W if kind == "door" else WINDOW_W
        else:
            e = _edge_for(p, tok[1], side=tok[2])
            rest, rooms = tok[3:], (tok[1],)
            width = DOOR_W if kind == "door" else WINDOW_W
        if "width" in rest:
            width = float(rest[rest.index("width") + 1])
        if e is None:
            print("plan: %s on %s %s is on an interior wall -- skipped" % (kind, tok[1], tok[2]))
            continue
        L = e.b - e.a
        if "at" in rest:
            frac = float(rest[rest.index("at") + 1].rstrip("%")) / 100.0
            a0 = e.a + frac * L - width / 2.0
        elif "from" in rest:
            a0 = e.a + float(rest[rest.index("start") + 1])
        elif "after" in rest:
            prev = windows[rest[rest.index("after") + 1]]
            a0 = prev.b + float(rest[rest.index("gap") + 1])
        else:
            a0 = e.a + (L - width) / 2.0
        a0 = max(e.a + 0.05, min(a0, e.b - 0.05 - width))
        style = " ".join(t for t in rest if t in ("bifold", "sliding", "in", "right", "left"))
        if kind == "window":
            sill, head = 0.9, 2.3
        else:
            sill, head = 0.0, 2.1 if kind == "door" else 2.3
        o = Opening(kind, e, a0, a0 + width, sill, min(head, height - 0.05), style, rooms)
        if "id" in rest:
            o.id = rest[rest.index("id") + 1]
            windows[o.id] = o
        p.openings.append(o)


def _ext_extend(p, e, at_start):
    """Exterior walls extend by their thickness at convex outline corners."""
    eps = 0.01
    end = e.a if at_start else e.b
    d = -1 if at_start else 1
    inward = -e.outward
    if e.axis == "h":
        qx, qy = end + d * eps, e.c + inward * eps
    else:
        qx, qy = e.c + inward * eps, end + d * eps
    return 0.0 if p.inside(qx, qy) else p.ext_t


def _build_walls(p, height):
    for e in p.edges:
        t = p.ext_t if e.kind == "ext" else p.int_t
        if e.kind == "ext":
            c0, c1 = sorted((e.c, e.c + e.outward * t))
            a = e.a - _ext_extend(p, e, True)
            b = e.b + _ext_extend(p, e, False)
        else:
            c0, c1 = e.c - t / 2.0, e.c + t / 2.0
            a, b = e.a - t / 2.0, e.b + t / 2.0
        ops = sorted((o for o in p.openings if o.edge is e), key=lambda o: o.a)
        cur = a
        for o in ops:
            if o.a > cur:
                p.walls.append(WallSeg(e.axis, c0, c1, cur, o.a, 0.0, height, e.kind))
            if o.sill > 0:
                p.walls.append(WallSeg(e.axis, c0, c1, o.a, o.b, 0.0, o.sill, e.kind))
            if o.head < height:
                p.walls.append(WallSeg(e.axis, c0, c1, o.a, o.b, o.head, height, e.kind))
            cur = o.b
        if b > cur:
            p.walls.append(WallSeg(e.axis, c0, c1, cur, b, 0.0, height, e.kind))


def load(path, height=2.7):
    with open(path, encoding="utf-8") as fh:
        return parse(fh.read(), height)


if __name__ == "__main__":
    import os
    import sys
    pl = load(sys.argv[1] if len(sys.argv) > 1 else
              os.path.join(os.path.dirname(os.path.abspath(__file__)), "plan_two_bed.txt"))
    print(pl.title, "ext %.2f int %.2f" % (pl.ext_t, pl.int_t))
    for r in pl.rooms.values():
        print("  room %-8s %-12s x %.2f..%.2f y %.2f..%.2f  %.1f m2" % (
            r.id, r.name, r.x, r.x1, r.y, r.y1, r.w * r.d))
    for e in pl.edges:
        print("  edge %s %-3s c=%.2f %.2f..%.2f %s" % (e.axis, e.kind, e.c, e.a, e.b, "/".join(e.rooms)))
    for o in pl.openings:
        print("  %-7s %s c=%.2f %.2f..%.2f sill %.2f head %.2f %s %s" % (
            o.kind, o.edge.axis, o.edge.c, o.a, o.b, o.sill, o.head, "/".join(o.rooms), o.style))
    print("  %d wall segments, %d furniture items, area %.1f m2" % (
        len(pl.walls), len(pl.furniture), sum(r.w * r.d for r in pl.rooms.values())))
