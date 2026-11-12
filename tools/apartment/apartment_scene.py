"""MatForge test apartment — builds the whole flat in 3ds Max and renders it.

The architecture comes from plan.py (Schematex two-bedroom plan, 68.8 m2):
walls split around every door/window, room floors, ceilings, skirting,
finish cladding, windows, doors, curtains. Furniture comes from the
furn_*.py modules (built on kit.py). EVERY material is made by MatForge
(maxplugin.builder) from a Runway reference in tools/realism_lab/out/maps.

Environment:
  MF_APT_CAMS   comma list of camera keys to render (default: all)
  MF_APT_OUT    output folder (default tools/apartment/out/renders)
  MF_APT_QUALITY  "draft" | "final" | "preview"
  MF_APT_SAVE   optional .max path to save the built scene
  MF_APT_PROBE  .json path: build doors + furniture only and dump their
                world boxes there (layout_check.py)
"""
import importlib
import json
import math
import os
import random
import sys
import time
import traceback

from pymxs import runtime as rt

ROOT = r"C:\Users\aasis\matforge"
HERE = os.path.join(ROOT, "tools", "apartment")
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

MAPS = os.path.join(ROOT, "tools", "realism_lab", "out", "maps")
OUT = os.environ.get("MF_APT_OUT", os.path.join(HERE, "out", "renders"))
QUALITY = os.environ.get("MF_APT_QUALITY", "draft")
os.makedirs(OUT, exist_ok=True)

try:
    from maxplugin import builder  # noqa: E402
    import kit  # noqa: E402
    import plan as planmod  # noqa: E402

    for m in (builder, kit, planmod):
        importlib.reload(m)
except Exception:
    # an import or syntax error would otherwise leave run_apartment.py no trail
    with open(os.path.join(OUT, "_apartment_log.json"), "w", encoding="utf-8") as fh:
        json.dump({"fatal": traceback.format_exc(), "log": []}, fh, indent=1)
    raise
H = 270.0                      # ceiling height, cm
LOG = []


def log(msg):
    LOG.append(str(msg))
    print("[apt] " + str(msg))
    # rewritten on every line so a crash inside Max (e.g. out of memory)
    # still leaves the trail up to it
    try:
        with open(os.path.join(OUT, "_apartment_log.json"), "w", encoding="utf-8") as fh:
            json.dump({"log": LOG, "running": True}, fh, indent=1)
    except OSError:
        pass


# ------------------------------------------------------------ MatForge materials
# material key -> (lab material id, metal override[, MatForge class override]):
# the class override builds the same forged maps with another MatForge recipe
# (sheer cloth, solid glass, lacquered boards, boucle) - every material and
# texture comes from the plugin, the scene only picks the recipe
MATS = {
    # architecture
    "floor_oak": ("oak_floor", None), "floor_terrazzo": ("terrazzo_floor", None),
    "planks_oak": ("oak_floor", None, "wood_floor"), "subfloor": ("black_plastic", None),
    "wall_paint": ("white_paint_wall", None), "wall_limewash": ("limewash_warm", None),
    "wall_zellige": ("zellige_wall", None), "ceiling": ("white_paint_wall", None),
    "frame": ("black_powder_coat", None), "window_glass": ("clear_glass", None),
    "door": ("paint_white_joinery", None), "skirting": ("paint_white_joinery", None),
    "curtain": ("linen_sofa", None, "fabric_sheer"), "sill": ("calacatta_table", None),
    "ground": ("asphalt", None),
    # furniture (kit.MAT_KEYS)
    "upholstery": ("linen_sofa", None), "upholstery_alt": ("boucle_sofa", None, "boucle"),
    "velvet": ("velvet_sofa", None), "leather": ("leather_sofa", None),
    "cushion": ("rust_velvet", None), "wood_dark": ("walnut_table", None),
    "wood_light": ("oak_board", None), "metal_brass": ("brass", "brass"),
    "metal_black": ("black_powder_coat", None), "metal_steel": ("satin_stainless", None),
    "metal_chrome": ("chrome", None), "glass": ("clear_glass", None),
    "glass_frosted": ("frosted_glass", None), "ceramic_white": ("white_porcelain", None),
    "stone_worktop": ("calacatta_table", None), "stone_dark": ("black_granite", None),
    "paint_white": ("paint_white_joinery", None), "paint_sage": ("paint_sage_joinery", None),
    "bedding": ("white_cotton", None), "linen": ("linen_sofa", None),
    "shade": ("linen_sofa", None, "fabric_sheer"), "glass_solid": ("clear_glass", None, "glass_object"),
    "twig": ("plant_stem", None, "foliage"), "water": ("clear_glass", None, "water"),
    "rug": ("wool_rug", None), "plant_leaf": ("monstera_leaf", None),
    "stem": ("plant_stem", None), "plant_pot": ("terracotta_pot", None),
    "plastic_black": ("black_plastic", None), "screen": ("black_screen", None),
    "rubber": ("rubber", None), "paper": ("kraft_paper", None), "wax": ("beeswax", None),
    "emissive_warm": ("led_panel", None), "mirror": ("chrome", "silver"),
    "soil": ("potting_soil", None),
    "art_canvas": ("art_canvas", None), "art_paper": ("art_paper", None),
}
_MAT_CACHE = {}
_MANIFEST = {}


def matforge(key):
    """Build (once) the MatForge VRayMtl for a material key."""
    if key in _MAT_CACHE:
        return _MAT_CACHE[key]
    lab_id, metal = MATS[key][:2]
    mf_path = os.path.join(MAPS, lab_id, "manifest.json")
    with open(mf_path, encoding="utf-8") as fh:
        mf = json.load(fh)
    mclass = MATS[key][2] if len(MATS[key]) > 2 else mf["class"]
    mf = dict(mf, **{"class": mclass})
    mat = builder.build_material(mf["maps"], "MF_" + key, mclass, metal=metal,
                                 tint=mf.get("transmission_tint"),
                                 anti_tile=mf.get("seamless", True),
                                 roughness_base=mf.get("roughness_base"))
    misses = [l for l in builder.LOG if "MISS" in l]
    if misses:
        log("material %s: %s" % (key, "; ".join(misses)))
    _MAT_CACHE[key] = mat
    _MANIFEST[key] = mf
    return mat


ASSIGN = []      # (node, key, tile, maptype)


def finish(node, key, tile=100.0, maptype=4):
    ASSIGN.append((node, key, tile, maptype))
    return node


# Laid tiles: their panels are welded into one mesh before mapping so a single
# box-map gizmo carries the grout grid across split panels and round corners
# (each panel's own gizmo sat on its own centre, so joints jumped at every
# split around a window or door).
WELD_KEYS = ("wall_zellige",)


def _weld(items):
    """Attach every node of `items` to the first; returns the one-node list."""
    first, tile, maptype = items[0]
    rt.convertToMesh(first)
    for node, _, _ in items[1:]:
        rt.meshop.attach(first, node)
    return [(first, tile, maptype)]


# Horizontal oak members whose grain should run along their width: the box
# gizmo's default stood the grain upright on drawer fronts and ran it
# front-to-back on tops. Aligning the gizmo to X turns both.
GRAIN_X = ("Nightstand_Top", "Nightstand_Bottom", "Nightstand_Shelf", "Nightstand_DrawerFront",
           "Nightstand_DrawerBox", "Nightstand_Back")


def apply_materials():
    """Material + real-world UVW + MatForge displacement for every node."""
    by_key = {}
    for node, key, tile, maptype in ASSIGN:
        by_key.setdefault(key, []).append((node, tile, maptype))
    for key, items in by_key.items():
        try:
            mat = matforge(key)
        except Exception as exc:
            log("material %s failed: %s" % (key, exc))
            continue
        if key in WELD_KEYS and len(items) > 1:
            try:
                items = _weld(items)
            except Exception as exc:
                log("weld %s failed: %s" % (key, exc))
        nodes = []
        for node, tile, maptype in items:
            if maptype is not None and tile:
                u = rt.Uvwmap()
                u.maptype = maptype
                u.length = u.width = u.height = float(tile)
                if str(node.name) in GRAIN_X:
                    kit.setp(u, "axis", 0)
                rt.addModifier(node, u)
            nodes.append(node)
        rt.select(nodes)
        mf = _MANIFEST[key]
        # MatForge displacement (assign_to_selection adds it as the recipe asks)
        # only where it pays: floors, rugs (felt with bump alone) and the
        # boucle (smooth fleece with bump alone); other furniture relies on bump
        if key.startswith("floor") or key in ("rug", "upholstery_alt"):
            builder.assign_to_selection(mat, mf["class"], height_map=mf["maps"].get("height"))
        else:
            for n in nodes:
                n.material = mat
    rt.clearSelection()


# ------------------------------------------------------------ geometry helpers
def mbox(x0, x1, y0, y1, z0, z1):
    """Axis-aligned box from plan-metre x/y ranges and cm z range."""
    X0, X1 = sorted((x0 * 100.0, x1 * 100.0))
    Y0, Y1 = sorted((-y0 * 100.0, -y1 * 100.0))
    return rt.Box(width=X1 - X0, length=Y1 - Y0, height=z1 - z0,
                  pos=rt.Point3((X0 + X1) / 2, (Y0 + Y1) / 2, z0), mapcoords=True)


def wall_box(w):
    if w.axis == "h":
        return mbox(w.a, w.b, w.c0, w.c1, w.z0 * 100, w.z1 * 100)
    return mbox(w.c0, w.c1, w.a, w.b, w.z0 * 100, w.z1 * 100)


def side_runs(pl, room, edge, z0, z1):
    """Pieces of one room edge minus the openings in it: [(a, b, z0, z1)]."""
    ops = sorted((o for o in pl.openings if o.edge is edge), key=lambda o: o.a)
    runs, cur = [], edge.a
    for o in ops:
        if o.a > cur:
            runs.append((cur, o.a, z0, z1))
        if o.sill * 100 > z0:
            runs.append((o.a, o.b, z0, min(z1, o.sill * 100)))
        if o.head * 100 < z1:
            runs.append((o.a, o.b, max(z0, o.head * 100), z1))
        cur = o.b
    if edge.b > cur:
        runs.append((cur, edge.b, z0, z1))
    return [r for r in runs if r[1] - r[0] > 0.005 and r[3] - r[2] > 0.5]


def room_edges(pl, room):
    """(edge, inward direction sign in c, face c) for every edge bounding room."""
    r = pl.rooms[room]
    out = []
    for e in pl.edges:
        if room not in e.rooms:
            continue
        if e.axis == "h":
            inward = 1 if abs(e.c - r.y) < 1e-6 else -1
        else:
            inward = 1 if abs(e.c - r.x) < 1e-6 else -1
        t = 0.0 if e.kind == "ext" else pl.int_t / 2.0
        out.append((e, inward, e.c + inward * t))
    return out


def clad(pl, room, key, z0, z1, depth=0.6, tile=100.0, edge_filter=None):
    """Thin finish panels on the room side of its walls (tiles, limewash)."""
    for e, inward, face in room_edges(pl, room):
        if edge_filter and not edge_filter(e):
            continue
        for a, b, za, zb in side_runs(pl, room, e, z0, z1):
            c0, c1 = sorted((face, face + inward * depth / 100.0))
            n = mbox(a, b, c0, c1, za, zb) if e.axis == "h" else mbox(c0, c1, a, b, za, zb)
            finish(n, key, tile)


def skirting(pl, room, h=8.0, d=1.6):
    for e, inward, face in room_edges(pl, room):
        for a, b, za, zb in side_runs(pl, room, e, 0.0, h):
            if za > 0.5:
                continue
            c0, c1 = sorted((face, face + inward * d / 100.0))
            n = mbox(a, b, c0, c1, 0, h) if e.axis == "h" else mbox(c0, c1, a, b, 0, h)
            finish(n, "skirting", 60)


# ------------------------------------------------------------ architecture
# Oak boards. The oak_floor photo holds five 18 cm boards per 90 cm repeat,
# each column with one end joint per repeat at these heights (v, measured off
# the albedo: columns split at 409/817/1230/1641 px of 2048). Each built board
# takes a joint-free run of one column at a random offset, the photo stretched
# along the grain so a repeat spans PLANK_V_M and boards can run 1-2 m.
PLANK_W = 0.18                       # m: one photo column at the 90 cm repeat
PLANK_JOINT_V = (0.0, 0.5, 0.75, 0.346, 0.5)
PLANK_V_M = 2.1
# per-board tint variants (brightness %, saturation %, hue shift deg): real
# boards differ; one photo laid edge to edge reads as laminate
PLANK_TINTS = ((0.0, 0.0, 0.0), (-4.0, 3.0, 1.0), (3.0, -4.0, -1.0), (-6.0, 2.0, 0.5), (2.0, 5.0, 1.5))
# (their lacquer is the MatForge wood_floor recipe; the variants are
# builder.build_variants on the forged albedo)


def _quad(faces, a, b, c, d, verts, out):
    """Two triangles a-b-c, a-c-d (0-based vertex ids) wound to face `out`."""
    pa, pb, pc = verts[a], verts[b], verts[c]
    u = [pb[i] - pa[i] for i in range(3)]
    v = [pc[i] - pa[i] for i in range(3)]
    n = (u[1] * v[2] - u[2] * v[1], u[2] * v[0] - u[0] * v[2], u[0] * v[1] - u[1] * v[0])
    if n[0] * out[0] + n[1] * out[1] + n[2] * out[2] >= 0.0:
        faces += [(a, b, c), (a, c, d)]
    else:
        faces += [(a, c, b), (a, d, c)]


def build_floor_planks(r, seed):
    """One room's oak floor as separate boards: 18 cm wide, 1.0-2.0 m long,
    staggered, 1 mm gaps over a dark subfloor, 1.5 mm bevels on the top edges,
    each mapped to its own run of one board in the photo, turned 180 degrees
    at random and given one of five tints. The photo laid as one texture
    repeated its painted joints every 90 cm and had no bevels: it read as
    laminate next to reference renders' floors of real, varied boards."""
    rnd = random.Random(seed)
    c, g = 0.15, 0.05                          # cm: bevel, half the gap
    verts, tvs, faces, ids = [], [], [], []
    x = r.x
    while x < r.x1 - 1e-6:
        x1 = min(x + PLANK_W, r.x1)
        y = r.y
        L = rnd.uniform(0.2, 2.0)              # the first board in each row staggers the joints
        while y < r.y1 - 1e-6:
            y1 = min(y + L, r.y1)
            k = rnd.randrange(5)
            span = (y1 - y) / PLANK_V_M
            j = PLANK_JOINT_V[k]
            v0 = j + 0.012 + rnd.uniform(0.0, max(0.0, 0.976 - span))
            v1 = v0 + span
            u0 = 0.2 * k + 0.007
            u1 = u0 + (0.2 - 0.014) * (x1 - x) / PLANK_W
            if rnd.random() < 0.5:
                u0, u1, v0, v1 = u1, u0, v1, v0
            du = c / 90.0 * (1.0 if u1 > u0 else -1.0)
            dv = c / (PLANK_V_M * 100.0) * (1.0 if v1 > v0 else -1.0)
            X0, X1 = x * 100.0 + g, x1 * 100.0 - g
            YA, YB = -y * 100.0 - g, -y1 * 100.0 + g       # plan y -> Max -Y
            base = len(verts)
            verts += [(X0 + c, YA - c, 0.0), (X1 - c, YA - c, 0.0), (X1 - c, YB + c, 0.0), (X0 + c, YB + c, 0.0),
                      (X0, YA, -c), (X1, YA, -c), (X1, YB, -c), (X0, YB, -c),
                      (X0, YA, -2.0), (X1, YA, -2.0), (X1, YB, -2.0), (X0, YB, -2.0)]
            uv_out = [(u0, v0), (u1, v0), (u1, v1), (u0, v1)]
            tvs += [(u0 + du, v0 + dv), (u1 - du, v0 + dv), (u1 - du, v1 - dv), (u0 + du, v1 - dv)]
            tvs += uv_out + uv_out
            t, m, b = base, base + 4, base + 8
            n0 = len(faces)
            _quad(faces, t, t + 1, t + 2, t + 3, verts, (0, 0, 1))
            for i, out in ((0, (0, 1, 1)), (1, (1, 0, 1)), (2, (0, -1, 1)), (3, (-1, 0, 1))):
                i2 = (i + 1) % 4
                _quad(faces, t + i, t + i2, m + i2, m + i, verts, out)                    # bevel
                _quad(faces, m + i, m + i2, b + i2, b + i, verts, (out[0], out[1], 0))    # side
            _quad(faces, b, b + 3, b + 2, b + 1, verts, (0, 0, -1))
            ids += [1 + rnd.randrange(len(PLANK_TINTS))] * (len(faces) - n0)
            y = y1
            L = rnd.uniform(1.0, 2.0)
        x = x1
    fmt = lambda pts: ",".join("[%.3f,%.3f,%.3f]" % tuple(p) for p in pts)
    node = rt.execute(
        '(m = mesh name:"FloorPlanks_%s" vertices:#(%s) faces:#(%s) tverts:#(%s)\n'
        'buildTVFaces m\nids = #(%s)\n'
        'for f = 1 to m.numfaces do (setTVFace m f (getFace m f); setFaceMatID m f ids[f]; '
        'setFaceSmoothGroup m f 0)\nupdate m\nm)'
        % (r.id, fmt(verts), ",".join("[%d,%d,%d]" % (a + 1, b_ + 1, c_ + 1) for a, b_, c_ in faces),
           ",".join("[%.5f,%.5f,0]" % tv for tv in tvs), ",".join(str(i) for i in ids)))
    finish(node, "planks_oak", None, None)
    sub = mbox(r.x, r.x1, r.y, r.y1, -2.4, -2.0)
    sub.name = "Subfloor_" + r.id
    finish(sub, "subfloor", 100)
    return node


def build_architecture(pl):
    for w in pl.walls:
        n = wall_box(w)
        n.name = "Wall_%s" % w.kind
        finish(n, "wall_paint", 150)
    for n_r, r in enumerate(pl.rooms.values()):
        if r.id in ("kitchen", "bath"):
            fl = mbox(r.x, r.x1, r.y, r.y1, -2.0, 0.0)
            fl.name = "Floor_" + r.id
            # the reference drew ~4 cm chips in its 1 m frame; 70 cm brings them to 2-3 cm
            finish(fl, "floor_terrazzo", 70)
        else:
            build_floor_planks(r, 17 + 31 * n_r)
        ce = mbox(r.x, r.x1, r.y, r.y1, H, H + 8)
        ce.name = "Ceiling_" + r.id
        finish(ce, "ceiling", 150)
        if r.id not in ("bath",):
            skirting(pl, r.id)
    clad(pl, "living", "wall_limewash", 8.0, H, tile=150)
    clad(pl, "bath", "wall_zellige", 0.0, 240.0, tile=90)    # 9 x 9 tiles of 10 cm
    # kitchen splashback between worktop and shelf on the north wall
    clad(pl, "kitchen", "wall_zellige", 91.0, 131.0, tile=90,
         edge_filter=lambda e: e.axis == "h" and abs(e.c) < 1e-6)
    for o in pl.openings:
        if o.kind == "window":
            build_window(pl, o)
        elif o.kind == "door":
            build_door(pl, o)
        if o.kind in ("door", "opening"):
            build_threshold(pl, o)
            build_casings(pl, o)
    # paving 4 m round the building; beyond it the backdrop photo carries on.
    # The wide ground only shows in the cut-away overview.
    near = rt.Plane(width=1700, length=1850, pos=rt.Point3(410, -490, -15))
    near.name = "Ground_Near"
    finish(near, "ground", 150)
    far = rt.Plane(width=6000, length=6000, pos=rt.Point3(410, -490, -16))
    far.name = "Ground_Far"
    finish(far, "ground", 150)


BACKDROP = os.path.join(HERE, "assets", "backdrop_street_crop.png")   # window jambs cropped off


# Foliage outside the living-room windows that only casts shadows (invisible
# to the camera and to reflections): the sun came through as clean hard-edged
# rectangles; through leaves it lands dappled, as in sunlit reference photos.
# Each cluster sits LEAF_OUT cm beyond the window on the sun ray that lands on
# the given floor/wall point (Max cm): 3-4 m out, the first set blurred away
# under the sun's own penumbra.
SUN_DIR = (-2050.0, 2800.0, 1500.0)          # toward the sun (the VRaySun's position minus its target)
LEAF_TARGETS = [((250.0, -200.0, 0.0), 55.0), ((330.0, -265.0, 0.0), 50.0), ((190.0, -300.0, 0.0), 45.0),
                ((300.0, -150.0, 0.0), 40.0), ((519.0, -88.0, 84.0), 45.0), ((519.0, -140.0, 40.0), 40.0)]
LEAF_OUT = 110.0


def _leaf_clusters():
    n = math.sqrt(sum(c * c for c in SUN_DIR))
    u = [c / n for c in SUN_DIR]
    out = []
    for (tx, ty, tz), rad in LEAF_TARGETS:
        t = (35.0 - ty) / u[1] + LEAF_OUT          # past the north wall's outer face
        out.append(((tx + t * u[0], ty + t * u[1], tz + t * u[2]), rad))
    return out


def build_leaf_casters(seed=7):
    rnd = random.Random(seed)
    verts, faces = [], []
    clusters = _leaf_clusters()
    for (cx, cy, cz), rad in clusters:
        for _ in range(int(rad * 7.0)):
            # leaves fill an irregular blob, thinner toward its edge
            while True:
                ox, oy, oz = (rnd.uniform(-1, 1) for _ in range(3))
                if ox * ox + oy * oy + oz * oz < 1.0:
                    break
            px, py, pz = cx + ox * rad, cy + oy * rad * 0.7, cz + oz * rad * 0.6
            L, W = rnd.uniform(7.0, 12.0), rnd.uniform(3.5, 6.0)
            a = rnd.uniform(0.0, 2.0 * math.pi)
            tilt = rnd.uniform(-0.9, 0.9)
            ux, uy = math.cos(a), math.sin(a)                   # leaf axis (mostly flat)
            vx, vy, vz = -uy * math.cos(tilt), ux * math.cos(tilt), math.sin(tilt)
            b = len(verts)
            verts += [(px - ux * L / 2, py - uy * L / 2, pz), (px + vx * W / 2, py + vy * W / 2, pz + vz * W / 2),
                      (px + ux * L / 2, py + uy * L / 2, pz), (px - vx * W / 2, py - vy * W / 2, pz - vz * W / 2)]
            faces += [(b + 1, b + 2, b + 3), (b + 1, b + 3, b + 4)]
    fmt = lambda pts: ",".join("[%.2f,%.2f,%.2f]" % p for p in pts)
    node = rt.execute('(m = mesh name:"LeafShadows" vertices:#(%s) faces:#(%s)\nupdate m\nm)'
                      % (fmt(verts), ",".join("[%d,%d,%d]" % f for f in faces)))
    node.primaryVisibility = False          # the camera never sees it
    node.secondaryVisibility = False        # nor do reflections and refractions
    node.castShadows = True
    mtl = rt.VRayMtl()
    mtl.name = "LeafShadows"
    node.material = mtl
    rt.setUserProp(node, "VRay_GI_VisibleToGI", False)
    log("leaf casters: %d leaves in %d clusters" % (len(faces) // 2, len(clusters)))
    return node


def build_backdrop():
    """A photo of a leafy street on a ring 25 m out, seen through the windows.

    Without it every window looked onto a flat plain running to the horizon.
    The ring is self-lit (VRayLightMtl, compensated for each camera's exposure
    so it reads as a bright daylit exterior), casts no shadow and is invisible
    to GI, so the sun and sky still light the flat. The photo spans 90 degrees
    (its own field of view) and is mirrored every quarter, so there is no seam;
    its horizon sits at eye height."""
    if not os.path.isfile(BACKDROP):
        log("no backdrop photo at %s" % BACKDROP)
        return None
    # a 90 degree arc at R is 3927 cm wide; the photo is 1.98:1, so 1983 cm tall
    # with its horizon (mid height) at eye height, 140 cm
    R, z0, z1, n = 2500.0, -852.0, 1131.0, 192
    cx, cy = 410.0, -490.0
    verts, tverts, faces = [], [], []
    for i in range(n + 1):
        a = 2.0 * math.pi * i / n
        x, y = cx + R * math.cos(a), cy + R * math.sin(a)
        q = (4.0 * i / n) % 2.0
        u = q if q <= 1.0 else 2.0 - q
        verts += [(x, y, z0), (x, y, z1)]
        tverts += [(u, 0.0, 0.0), (u, 1.0, 0.0)]
    for i in range(n):
        b0, t0, b1, t1 = 2 * i + 1, 2 * i + 2, 2 * i + 3, 2 * i + 4
        faces += [(b0, t1, b1), (b0, t0, t1)]          # normals face the flat
    fmt = lambda pts: ",".join("[%.3f,%.3f,%.3f]" % p for p in pts)
    node = rt.execute('(m = mesh name:"Backdrop" vertices:#(%s) faces:#(%s) tverts:#(%s)\n'
                      'buildTVFaces m\nfor f = 1 to m.numfaces do setTVFace m f (getFace m f)\n'
                      'update m\nm)' % (fmt(verts), ",".join("[%d,%d,%d]" % f for f in faces),
                                        fmt(tverts)))
    tex = rt.Bitmaptexture()
    tex.filename = BACKDROP
    mtl = rt.VRayLightMtl()
    mtl.name = "Backdrop_street"
    mtl.texmap = tex
    # a sunlit street is about as bright as the sun patches indoors (both in
    # direct sun), so the photo runs ~2.3 stops hot; at 1.6x and 3x the room's
    # warm reflection in the window glass outshone the shaded tree canopy and
    # turned it red-brown
    mtl.multiplier = 5.0
    mtl.compensate_exposure = True
    node.material = mtl
    node.castShadows = False
    node.receiveShadows = False
    rt.setUserProp(node, "VRay_GI_VisibleToGI", False)
    return node


def _opening_frame(pl, o):
    """Plan geometry of an opening: axis, along range, wall slab c0..c1."""
    e = o.edge
    t = pl.ext_t if e.kind == "ext" else pl.int_t
    if e.kind == "ext":
        c0, c1 = sorted((e.c, e.c + e.outward * t))
    else:
        c0, c1 = e.c - t / 2.0, e.c + t / 2.0
    return e.axis, o.a, o.b, c0, c1


def _abox(axis, a0, a1, c0, c1, z0, z1):
    return mbox(a0, a1, c0, c1, z0, z1) if axis == "h" else mbox(c0, c1, a0, a1, z0, z1)


def build_window(pl, o):
    axis, a, b, c0, c1 = _opening_frame(pl, o)
    e = o.edge
    sill, head = o.sill * 100.0, o.head * 100.0
    inward = -e.outward
    if "kitchen" in o.rooms and axis == "h" and abs(e.c) < 1e-6:
        sill = 105.0                            # above the worktop
        # raise the wall below to the new sill, tiled like the splashback
        n = _abox(axis, a, b, c0, c1, o.sill * 100.0, sill)
        finish(n, "wall_paint", 150)
        n = _abox(axis, a, b, e.c, e.c + inward * 0.006, 91.0, sill - 3.0)
        finish(n, "wall_zellige", 90)
    # frame sits 12 cm in from the outside face
    out_face = c0 if e.outward < 0 else c1
    f0 = out_face + inward * 0.12
    f1 = f0 + inward * 0.07
    fc0, fc1 = sorted((f0, f1))
    fw = 0.05                                   # frame profile 5 cm
    parts = [
        _abox(axis, a, b, fc0, fc1, sill, sill + fw * 100),
        _abox(axis, a, b, fc0, fc1, head - fw * 100, head),
        _abox(axis, a, a + fw, fc0, fc1, sill, head),
        _abox(axis, b - fw, b, fc0, fc1, sill, head),
    ]
    if b - a > 1.3:                             # two sashes
        mid = (a + b) / 2.0
        parts.append(_abox(axis, mid - fw / 2, mid + fw / 2, fc0, fc1, sill, head))
    for n in parts:
        n.name = "WinFrame"
        finish(n, "frame", 30)
    # sashes: a 4 cm frame in each bay, 1 cm proud of the outer frame on the
    # room side, with a handle on its meeting stile. One box profile and no
    # hardware read as a picture frame round a print.
    s0, s1 = sorted((f1 - inward * 0.05, f1 + inward * 0.01))
    sw = 0.04
    zb, zt = sill + fw * 100, head - fw * 100
    mid = (a + b) / 2.0
    bays = [(a + fw, mid - fw / 2.0), (mid + fw / 2.0, b - fw)] if b - a > 1.3 else [(a + fw, b - fw)]
    face = s1 if inward > 0 else s0                # room-side face of the sashes
    zc = (zb + zt) / 2.0
    for k, (u0, u1) in enumerate(bays):
        for n in (_abox(axis, u0, u1, s0, s1, zb, zb + sw * 100), _abox(axis, u0, u1, s0, s1, zt - sw * 100, zt),
                  _abox(axis, u0, u0 + sw, s0, s1, zb + sw * 100, zt - sw * 100),
                  _abox(axis, u1 - sw, u1, s0, s1, zb + sw * 100, zt - sw * 100)):
            n.name = "WinSash"
            finish(n, "frame", 30)
        hu = u1 - sw / 2.0 if k == 0 else u0 + sw / 2.0
        plate = _abox(axis, hu - 0.014, hu + 0.014, face, face + inward * 0.009, zc - 3.5, zc + 3.5)
        lever = _abox(axis, hu - 0.007, hu + 0.007, face + inward * 0.009, face + inward * 0.026,
                      zc - 11.0, zc + 1.5)
        for n in (plate, lever):
            n.name = "WinHandle"
            finish(n, "metal_steel", None, None)
    gc = (fc0 + fc1) / 2.0
    g = _abox(axis, a + fw, b - fw, gc - 0.004, gc + 0.004, sill + fw * 100, head - fw * 100)
    g.name = "WinGlass"
    finish(g, "window_glass", 100)
    # interior marble sill board: from the glass to 3 cm proud of the wall
    s0, s1 = sorted((gc, e.c + inward * 0.03))
    sb = _abox(axis, a - 0.03, b + 0.03, s0, s1, sill - 3.0, sill)
    sb.name = "Sill"
    finish(sb, "sill", 200)      # same marble scale as the kitchen worktop


def build_casings(pl, o):
    """Architraves round a door or opening on each room face of its wall: 7 cm
    wide, 1.8 cm proud, over the lining joint and the skirting ends. Without
    them every doorway read as a hole cut in the wall."""
    axis, a, b, c0, c1 = _opening_frame(pl, o)
    e = o.edge
    head = o.head * 100.0
    if e.kind == "ext":
        faces = [(e.c, -e.outward)]
    else:
        faces = [(c0, -1), (c1, 1)]
    cw, ct = 0.07, 0.018
    for face, d in faces:
        k0, k1 = sorted((face, face + d * ct))
        # legs stop under the head piece: overlapping boxes share a front face
        for n in (_abox(axis, a - cw + 0.01, a + 0.01, k0, k1, 0.0, head - 1.0),
                  _abox(axis, b - 0.01, b + cw - 0.01, k0, k1, 0.0, head - 1.0),
                  _abox(axis, a - cw + 0.01, b + cw - 0.01, k0, k1, head - 1.0, head + cw * 100.0 - 1.0)):
            n.name = "Casing"
            finish(n, "door", 60)


def build_threshold(pl, o):
    """Floor across the wall slab under a door or opening. Room floors stop at
    the wall faces, so every doorway had a hole down to the sunlit paving: a
    bright speckled strip under the front door. Marble at the bathroom, oak
    elsewhere."""
    axis, a, b, c0, c1 = _opening_frame(pl, o)
    n = _abox(axis, a, b, c0, c1, -2.0, 0.0)
    n.name = "Threshold_" + "_".join(o.rooms)
    key = "sill" if "bath" in o.rooms else "floor_oak"
    finish(n, key, 60 if key == "sill" else 90)


def build_door(pl, o):
    axis, a, b, c0, c1 = _opening_frame(pl, o)
    head = o.head * 100.0
    jt = 0.04                                    # jamb lining
    for n in (_abox(axis, a, a + jt, c0 - 0.01, c1 + 0.01, 0, head),
              _abox(axis, b - jt, b, c0 - 0.01, c1 + 0.01, 0, head),
              _abox(axis, a, b, c0 - 0.01, c1 + 0.01, head - 4.0, head)):
        n.name = "DoorJamb"
        finish(n, "door", 60)
    width = (b - a - 2 * jt) * 100.0
    # leaf built with its hinge edge on the local origin, extending along +X
    leaf = kit.cbox(width - 0.6, 4.0, head - 4.6, 0.3, (width - 0.6) / 2.0, 0, 0.6, segs=2)
    leaf.name = "DoorLeaf"
    # the oak front door is mapped as one veneer (at 60 cm its figure repeated
    # three times up the leaf)
    finish(leaf, "door" if o.rooms != ("hall",) else "wood_light", 60 if o.rooms != ("hall",) else 220)
    nodes = [leaf]
    for side in (-1, 1):                       # lever handle on both faces
        rose = kit.cyl(2.6, 1.2, width - 8.0, side * 2.0, 100.0, sides=24)
        kit.rotate(rose, 90 * side, (1, 0, 0))
        lever = kit.cbox(12.0, 1.8, 1.8, 0.6, width - 14.0, side * 4.0, 99.0, segs=2)
        parts = [rose, lever]
        if o.rooms == ("hall",):               # the front door's lock: a key plate
            parts.append(kit.cbox(3.4, 1.0, 7.5, 0.4, width - 8.0, side * 2.45, 84.0, segs=2))
        for n in parts:
            finish(n, "metal_brass", None, None)
            nodes.append(n)
    for hz in (18.0, 100.0, head - 30.0):      # three butt hinges' barrels
        hinge = kit.cyl(0.6, 9.0, 0.0, 2.55, hz, sides=16)
        finish(hinge, "metal_brass", None, None)
        nodes.append(hinge)
    g = kit.group("Door_" + "_".join(o.rooms), nodes)
    # swing (degrees, CCW from above) chosen per door so leaves clear furniture
    # the front door stays shut: open, it showed the street through the hall
    swing = {("hall",): 0.0, ("hall", "bed1"): -80.0, ("bed1", "bath"): 35.0,
             ("hall", "bed2"): -75.0}.get(tuple(o.rooms), 0.0)
    base_rot = 0.0 if axis == "h" else -90.0   # along +X for h walls, -Y for v walls
    centre = (c0 + c1) / 2.0
    if axis == "h":
        hx, hy = P(a + jt, centre)
    else:
        hx, hy = P(centre, a + jt)
    kit.place(g, hx, hy, 0.0, base_rot + swing)
    DOORS.append((g, width, o.rooms))
    SWING[tuple(o.rooms)] = [g, swing, swing]


DOORS = []       # (door dummy, leaf width cm, rooms) for the layout probe
SWING = {}       # rooms -> [door dummy, layout swing, current swing] (degrees)

# Doors a camera wants in another position than the layout's, as a
# photographer would set them: open into the hall, the bedroom 1 leaf filled a
# third of the hall view with a blank white panel.
CAM_DOORS = {"hall": {("hall", "bed1"): 0.0}}


def set_doors(key):
    want = CAM_DOORS.get(key, {})
    for rooms, st in SWING.items():
        g, layout, cur = st
        ang = want.get(rooms, layout)
        if ang != cur:
            rt.rotate(g, rt.angleaxis(ang - cur, rt.Point3(0, 0, 1)))
            st[2] = ang


def _wall_item(w, h, d, px, py, z, facing):
    """A thin box on a wall face. facing: +1 = faces +Y (north wall item seen
    from the south... i.e. normal toward +Y), -1 faces -Y, 'e'/'w' face +X/-X."""
    x, y = P(px, py)
    if facing in ("e", "w"):
        n = kit.cbox(d, w, h, 0.25, x, y, z, segs=1)
    else:
        n = kit.cbox(w, d, h, 0.25, x, y, z, segs=1)
    return n


def _art(key, size, px, py, zc, facing):
    """A framed piece on a wall face (plan px, py), built facing -Y and turned
    to face the room ("n": the piece faces north). The canvas sits 2.5 cm deep
    in an oak floater frame with a dark shadow gap; the print sits on a white
    mat behind glass in a moulded frame. A solid block with the image glued on
    its face read as a sticker."""
    parts = []

    def add(n, k, tile=None):
        finish(n, k, tile, None if tile is None else 4)
        parts.append(n)

    def ring(inner, m, depth):                     # four mouldings round an opening
        o = inner + 2.0 * m
        for w, h, x, z in ((o, m, 0.0, zc + inner / 2.0), (o, m, 0.0, zc - inner / 2.0 - m),
                           (m, inner, -(inner + m) / 2.0, zc - inner / 2.0),
                           (m, inner, (inner + m) / 2.0, zc - inner / 2.0)):
            add(kit.cbox(w, depth, h, 0.25, x, -depth / 2.0, z, segs=2), "wood_light", 60)

    def plane(w, y, k, tile=None):
        pl_ = rt.Plane(width=w, length=w, widthsegs=1, lengthsegs=1, pos=rt.Point3(0, 0, 0))
        kit.rotate(pl_, 90.0, (1, 0, 0))           # stand it up, front toward -Y
        pl_.pos = rt.Point3(0.0, y, zc)
        add(pl_, k, tile)

    def pane(w, y):                                # 2 mm low-iron glass, not a tinted plane
        add(kit.box(w, 0.2, w, 0.0, y, zc - w / 2.0), "glass_solid", 30)

    if key == "art_canvas":
        gap = 1.0
        inner = size + 2.0 * gap
        add(kit.box(inner, 0.6, inner, 0.0, -0.3, zc - inner / 2.0), "wood_dark", 60)      # back board
        add(kit.cbox(size, 2.5, size, 0.3, 0.0, -1.85, zc - size / 2.0, segs=2), "linen", 25)  # stretcher
        plane(size, -3.12, key)
        ring(inner, 1.8, 4.2)
    else:
        mat = 6.0
        inner = size + 2.0 * mat
        add(kit.box(inner, 0.4, inner, 0.0, -0.6, zc - inner / 2.0), "bedding", 30)      # white mat
        plane(size, -0.83, key)
        pane(inner, -1.9)
        ring(inner, 2.4, 3.0)
    g = kit.group("Art_" + key, parts)
    x, y = P(px, py)
    kit.place(g, x, y, 0.0, {"n": 180.0, "s": 0.0, "e": 90.0, "w": -90.0}[facing])


def build_details(pl):
    """Lived-in details: framed art, switches, sockets, curtain rails."""
    art = [  # key, size cm, plan x, plan y (wall face), centre z, facing
        ("art_canvas", 90.0, 2.9, 4.14, 155.0, "n"),
        ("art_paper", 60.0, 1.895, 6.86, 168.0, "s"),        # centred on bed 2 (1.895)
        # the bare west wall over the sideboard and the blank wall over bed 1
        ("art_paper", 70.0, 0.0, 3.2, 150.0, "e"),
        ("art_canvas", 75.0, 3.5, 4.26, 165.0, "s"),
    ]
    for key, size, px, py, zc, facing in art:
        _art(key, size, px, py, zc, facing)
    # light switches (latch side of each door, 105 cm) and a few sockets (30 cm)
    # positions sit ON the wall faces (exterior faces at the room edge,
    # interior faces 6 cm either side of the shared edge)
    # beside the new door casings (they sat on them: 2.065/5.98 and 0.95/6.74)
    for px, py, facing in ((0.005, 6.15, "e"), (1.935, 6.20, "w"), (2.065, 6.20, "e"),
                           (1.03, 6.74, "n"), (5.26, 4.45, "e"), (4.92, 0.005, "s")):
        x, y = P(px, py)
        n = _wall_item(8.5, 8.5, 1.0, px, py, 101.0, facing)
        finish(n, "paint_white", 30)
        n = _wall_item(2.6, 4.4, 1.6, px, py, 103.05, facing)      # the rocker
        finish(n, "paint_white", 30)
    for px, py, facing in ((0.005, 3.6, "e"), (4.9, 4.14, "n"), (5.26, 3.2, "e"),
                           (0.005, 9.3, "e"), (3.2, 6.86, "s")):
        n = _wall_item(8.5, 8.5, 1.0, px, py, 26.0, facing)
        finish(n, "paint_white", 30)


def _pleated_curtain_mesh(w, h, depth=4.0, seed=0, nu=120, nv=48, fold_w=(8.0, 15.0),
                          merge=0.0, amp=(0.6, 1.3), sway=None, drift=0.0, rings=0,
                          ring_inset=3.0, dip=(1.0, 1.5), floor_break=0.0):
    """The cloth of _pleated_curtain in plain Python (no pymxs): (verts,
    faces), (x, y, z) in cm and 1-based triangles over nu x nv quads. x runs
    across the panel centred on 0, y is its depth (the room lies toward -y),
    z rises from the hem line at 0 to the heading at h.

    The defaults are the apartment's panels vertex for vertex: S-folds (a
    pleat forward and one back) 8-15 cm wide and depth x 0.6-1.3 deep, each
    swaying up to 1.8 cm (switched at mid-fold: a step on the flank), the
    hem lifting or dropping 0.9 cm round z = 0 so the scenes hang it 1.5-2 cm
    up. Evenly spaced, plumb and parallel, that reads as a stiff blind beside
    a real sheer, which wants the options:
      fold_w, amp  fold width (cm) and depth (x depth) ranges
      merge        chance a fold joins its right-hand neighbour: the two hang
                   apart under the heading and run into one deep fold lower
                   down, each pair at its own height (no fold joins twice)
      sway         cm the folds wander sideways, growing toward the hem and
                   blended across each fold, a fold narrowing to half its
                   width at most (None: the 1.8 cm step)
      drift        cm the hem fans out toward +x (> 0) or -x (< 0), as a
                   drawn-back panel does: the leading edge the full amount,
                   the far edge a quarter
      rings        ring count (>= 2), the outer two ring_inset cm in from the
                   edges as both scenes hang them: the heading is held on the
                   rail line at each ring and dips `dip` cm between them
      floor_break  cm the panel hangs longer than heading-to-floor: z = 0 is
                   then the floor, the cloth below z 0.2 lies on it pushed out
                   toward the room by 0.2-1 x (floor_break + 0.2) cm (most
                   under the folds facing the room), and the hem only flares
    Rows crowd 3x toward the heading with rings and toward the floor with a
    break. Every random choice of an option has its own stream: the fold
    layout of a seed stays put while they are tuned."""
    rnd = random.Random(1000 + seed)
    edges = [0.0]                                  # fold boundaries across x
    while edges[-1] < w:
        edges.append(edges[-1] + rnd.uniform(fold_w[0], fold_w[1]))
    edges = [e * w / edges[-1] for e in edges]
    nk = len(edges) - 1
    amps = [rnd.uniform(amp[0], amp[1]) for _ in range(nk + 1)]
    sw = 1.8 if sway is None else sway
    sways = [(rnd.uniform(-sw, sw), rnd.uniform(0.0, 2.0 * math.pi)) for _ in range(nk + 1)]

    def fold(x0):
        for k in range(nk):
            if x0 <= edges[k + 1] + 1e-9:
                return k, (x0 - edges[k]) / (edges[k + 1] - edges[k])
        return nk - 1, 1.0

    # merged pairs (first fold, merging from f, merged by f, deep fold's amp),
    # f 1 at the heading and 0 at the hem; capped at the widest depth so a
    # deep fold reaches no nearer the wall than a plain one could
    pair, rm, k = [None] * nk, random.Random(2000 + seed), 0
    while merge > 0.0 and k < nk - 1:
        if rm.random() < merge:
            top = rm.uniform(0.55, 0.9)
            pair[k] = pair[k + 1] = (k, top, top - rm.uniform(0.15, 0.35),
                                     min(amp[1], 1.35 * max(amps[k:k + 3])))
            k += 2
        else:
            k += 1
    pairs = sorted({p for p in pair if p})
    pitch = (w - 2.0 * ring_inset) / (rings - 1) if rings >= 2 and w > 2.0 * ring_inset else 0.0
    if pitch:
        rd = random.Random(3000 + seed)
        dips = [rd.uniform(dip[0], dip[1]) for _ in range(rings - 1)]
        reach = max(6.0, 1.2 * pitch)              # how far down the rings' pull shows
    brk = floor_break > 0.0
    lo, hi = (0.35 if brk else 1.0), (0.35 if pitch else 1.0)

    def ease(t):                                   # row spacing x lo at the hem, x hi at the heading
        return 1.0 if t >= 1.0 else ((lo + hi - 2.0) * t + 3.0 - 2.0 * lo - hi) * t * t + lo * t

    if brk:                                        # from the floor contact; the lying row comes later
        zs = [0.2 + (h - 0.2) * ease(j / max(nv - 1.0, 1.0)) for j in range(nv)]
        zs[-1] = h
    elif pitch:
        zs = [h * ease(j / float(nv)) for j in range(nv + 1)]
    else:
        zs = [h * j / nv for j in range(nv + 1)]

    cols = []                                      # per column: everything but the height
    for i in range(nu + 1):
        x0 = w * i / nu
        k, u = fold(x0)
        s = 0.5 - 0.5 * math.cos(math.pi * u)      # smooth blend to the next fold
        p = pair[k]
        tp = p and 2.0 * math.pi * (x0 - edges[p[0]]) / (edges[p[0] + 2] - edges[p[0]])
        tau = 0.25 + 0.75 * (x0 / w if drift > 0.0 else 1.0 - x0 / w)     # share of the drift
        ring = None
        if pitch:                                  # (dip below the heading, 1 at a ring .. 0 between)
            t = (x0 - ring_inset) / pitch
            ring = (dips[min(max(int(math.floor(t)), 0), rings - 2)] * abs(math.sin(math.pi * t)),
                    math.cos(math.pi * t) ** 2)
        cols.append((x0, k, u, s, p, tp, tau, ring))

    rows = []
    for z in zs:
        f = min(z / h, 1.0)                        # 0 at the hem, 1 at the heading
        g = 1.0 - f
        flare = 0.72 + 0.6 * (1.0 - f) ** 1.3      # folds open up toward the floor
        if sway is not None:                       # each fold boundary's sway at this height
            D = [dx * g * math.sin(2.2 * g + ph) for dx, ph in sways]
            for b in range(nk):
                D[b + 1] = max(D[b + 1], D[b] - 0.5 * (edges[b + 1] - edges[b]))
        mrow = {}
        for p in pairs:                            # smoothstep from two folds to one
            q = min(max((p[1] - f) / (p[1] - p[2]), 0.0), 1.0)
            mrow[p[0]] = q * q * (3.0 - 2.0 * q)
        row, sns = [], []
        for x0, k, u, s, p, tp, tau, ring in cols:
            amp_k = amps[k] + (amps[k + 1] - amps[k]) * s
            if sway is None:
                dx, ph = sway_k = sways[k] if u < 0.5 else sways[k + 1]
                x = x0 - w / 2.0 + dx * (1.0 - f) * math.sin(2.2 * (1.0 - f) + ph)
            else:
                x = x0 - w / 2.0 + D[k] + (D[k + 1] - D[k]) * s
            a = 2.0 * math.pi * (k + u)
            m = mrow[p[0]] if p else 0.0
            if m > 0.0:
                sn = (1.0 - m) * math.sin(a) + m * math.sin(tp)          # where in its fold
                y = depth * flare * ((1.0 - m) * amp_k * math.sin(a) + m * p[3] * math.sin(tp))
                kick = (1.0 - m) * math.sin(a + 0.6) + m * math.sin(tp + 0.6)
                lift = (1.0 - m) * math.cos(a) + m * math.cos(tp)
            else:
                sn = math.sin(a)
                y = depth * flare * amp_k * sn
                kick, lift = math.sin(a + 0.6), math.cos(a)
            if brk:                                # standing on the floor: the hem only flares
                hem = max(0.0, 1.0 - (z - 0.2) / 6.0) ** 2
                y += 1.4 * hem * kick
                zz = z
            else:
                hem = max(0.0, 1.0 - z / 6.0) ** 2     # bottom 6 cm: the hem kicks out
                y += 1.4 * hem * kick
                zz = z + 0.9 * hem * lift
            if ring and h - z < reach:
                fall = (1.0 - (h - z) / reach) ** 2
                y *= 1.0 - ring[1] * fall          # held on the rail line at each ring,
                zz -= ring[0] * fall               # dipping between them
            if drift:
                x += drift * g ** 1.5 * tau
            row.append((x, y, zz))
            sns.append(sn)
        rows.append(row)
        if brk and len(rows) == 1:                 # the cloth below z 0.2 laid on the floor
            e = floor_break + 0.2
            rows.insert(0, [(x, y - e * (0.6 - 0.4 * q), zz) for (x, y, zz), q in zip(row, sns)])
    verts = [v for row in rows for v in row]
    faces = []
    for j in range(nv):
        for i in range(nu):
            a = j * (nu + 1) + i + 1
            b, c, d = a + 1, a + nu + 1, a + nu + 2
            faces += [(a, b, d), (a, d, c)]
    return verts, faces


def _pleated_curtain(name, w, h, depth=4.0, seed=0, nu=120, nv=48, shell=True, **cloth):
    """A gathered curtain panel: folds of uneven width (8-15 cm) and depth,
    tighter at the heading and opening toward the floor, each wandering a
    little off vertical, with a hem that kicks and lifts unevenly. Built
    directly as a mesh: a Wave modifier on a plane ran along the panel's
    length, which made horizontal folds that aliased into a sawtooth; and
    identical sine pleats over the whole drop read as corrugated board.
    `cloth` takes _pleated_curtain_mesh's options for a sheer (varied and
    merging folds, a ring heading, a fanned hem, a floor break); shell=False
    leaves a single layer: a voile's see-through is per surface, and the
    Shell's two faces passed only 0.45 x 0.45 of the light."""
    verts, faces = _pleated_curtain_mesh(w, h, depth, seed, nu, nv, **cloth)
    vs = ",".join("[%.3f,%.3f,%.3f]" % v for v in verts)
    fs = ",".join("[%d,%d,%d]" % f for f in faces)
    node = rt.execute('(m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
                      'for f = 1 to m.numfaces do setFaceSmoothGroup m f 1\nupdate m\nm)'
                      % (name, vs, fs))
    if shell:
        sh = rt.Shell()
        kit.setp(sh, "outerAmount", 0.15)
        rt.addModifier(node, sh)
    return node


RAIL_OFF, RAIL_Z = 9.0, 259.0         # rail axis: cm off the wall face, height
CURTAIN_OFF = 12.0                    # panel plane: its folds clear the 3 cm sill board
# (room, wall of that room, panels): "outer" hangs one panel on the outer side
# of each window (the living room's two windows share a wall whose pier
# carries the TV: panels there went through the console), "both" one each side.
CURTAINS = [("living", "n", "outer"), ("bed2", "w", "both")]


def _wall_frame(side, c, room):
    """A local frame for one wall of a room: local x runs along the wall, the
    wall face is local y = 0 and the room lies toward -y. Returns the dummy's
    rotation (deg) and origin (Max x, y), plan (a, b) along the wall -> local
    (la, lb), and the room's extent along the wall in local x."""
    C = 100.0 * c
    if side == "n":
        return 0.0, (0.0, -C), lambda a, b: (100.0 * a, 100.0 * b), (100.0 * room.x, 100.0 * room.x1)
    if side == "s":
        return 180.0, (0.0, -C), lambda a, b: (-100.0 * b, -100.0 * a), (-100.0 * room.x1, -100.0 * room.x)
    if side == "w":
        return 90.0, (C, 0.0), lambda a, b: (-100.0 * b, -100.0 * a), (-100.0 * room.y1, -100.0 * room.y)
    return -90.0, (C, 0.0), lambda a, b: (100.0 * a, 100.0 * b), (100.0 * room.y, 100.0 * room.y1)


def _side_of(o):
    inward = -o.edge.outward                       # +1: the room lies at larger plan c
    if o.edge.axis == "h":
        return "n" if inward > 0 else "s"
    return "w" if inward > 0 else "e"


def build_curtains(pl):
    """Linen curtains on rings round a black rail with wall brackets and end
    caps, drawn to the sides of the windows listed in CURTAINS (bedroom 2's
    street-facing window was bare). Each panel is mapped flat from the front:
    box mapping seamed across the fold flanks."""
    seed = 0
    for room_id, side, mode in CURTAINS:
        room = pl.rooms[room_id]
        wins = [o for o in pl.openings if o.kind == "window" and room_id in o.rooms
                and _side_of(o) == side]
        if not wins:
            continue
        rot, (ox, oy), to_local, (lo, hi) = _wall_frame(side, wins[0].edge.c, room)
        spans = sorted(to_local(o.a, o.b) for o in wins)
        panels = []
        for k, (la, lb) in enumerate(spans):
            w = 55.0 if lb - la > 140.0 else 50.0
            if mode == "both" or k == 0:
                panels.append((la - w / 2.0 + 8.0, w))
            if mode == "both" or k == len(spans) - 1:
                panels.append((lb + w / 2.0 - 8.0, w))
        parts = []
        top = RAIL_Z - 4.0
        placed = []
        for x, w in panels:
            x = min(max(x, lo + 1.0 + w / 2.0), hi - 1.0 - w / 2.0)
            placed.append((x, w))
            cur = _pleated_curtain("Curtain", w, top - 2.0, seed=seed)
            seed += 1
            cur.pos = rt.Point3(x, -CURTAIN_OFF, 2.0)
            u = rt.Uvwmap()
            u.maptype = 0
            kit.setp(u, "axis", 1)                 # planar, facing the room
            u.length = u.width = u.height = 14.0   # fine linen, not 40 cm slubs
            rt.addModifier(cur, u)
            finish(cur, "curtain", None, None)
            parts.append(cur)
            for k in range(6):                     # rings on the rail
                ring = rt.Torus(radius1=2.3, radius2=0.28, segs=20, sides=8)
                kit.rotate(ring, 90.0, (0, 1, 0))
                ring.pos = rt.Point3(x - w / 2.0 + 3.0 + k * (w - 6.0) / 5.0, -RAIL_OFF, RAIL_Z)
                finish(ring, "metal_black", None, None)
                parts.append(ring)
        x0 = max(lo + 4.0, min(x - w / 2.0 for x, w in placed) - 4.0)
        x1 = min(hi - 4.0, max(x + w / 2.0 for x, w in placed) + 4.0)
        rail = kit.cyl(1.1, x1 - x0, 0.0, 0.0, 0.0, sides=20)
        kit.rotate(rail, 90.0, (0, 1, 0))
        rail.pos = rt.Point3(x0, -RAIL_OFF, RAIL_Z)
        finish(rail, "metal_black", None, None)
        parts.append(rail)
        for bx in (x0 + 6.0, (x0 + x1) / 2.0, x1 - 6.0):     # wall brackets
            br = kit.cbox(1.6, RAIL_OFF, 2.4, 0.3, bx, -RAIL_OFF / 2.0, RAIL_Z - 1.2, segs=1)
            finish(br, "metal_black", None, None)
            parts.append(br)
        for ex in (x0 - 2.2, x1 + 0.2):                      # end caps
            cap = kit.cyl(1.5, 2.0, 0.0, 0.0, 0.0, sides=20)
            kit.rotate(cap, 90.0, (0, 1, 0))
            cap.pos = rt.Point3(ex, -RAIL_OFF, RAIL_Z)
            finish(cap, "metal_black", None, None)
            parts.append(cap)
        g = kit.group("Curtains_%s_%s" % (room_id, side), parts)
        kit.place(g, ox, oy, 0.0, rot)


# ------------------------------------------------------------ furniture
def P(x, y):
    """plan metres -> Max cm (x, y)"""
    return x * 100.0, -y * 100.0


LAYOUT = [
    # module, function, kwargs, plan x, plan y, rot_deg (counter-clockwise from
    # above; the front faces -Y = plan south at 0), optional z. Checked with
    # layout_check.py: backs ~1 cm off their walls, door swings left clear.
    # living: TV on the pier between the windows, sofa facing it
    ("furn_bedroom", "build_bedroom_rug", {"w": 260, "l": 190}, 2.9, 2.6, 0),
    ("furn_living", "build_sofa", {}, 2.9, 3.5, 180),
    ("furn_living", "build_coffee_table", {}, 2.9, 2.31, 0),
    ("furn_living", "build_armchair", {}, 4.5, 2.6, -100),
    ("furn_living", "build_side_table", {}, 4.3, 3.55, 0),
    ("furn_living", "build_floor_lamp", {}, 4.85, 3.85, 0),
    ("furn_living", "build_tv_console", {}, 2.9, 0.225, 0),
    ("furn_living", "build_tv", {}, 2.9, 0.24, 0, 48.0),
    ("furn_living", "build_plant", {}, 0.52, 0.5, 20),
    ("furn_living", "build_decor_books", {}, 2.65, 2.28, 10, 38.0),
    ("furn_living", "build_decor_vase", {}, 3.25, 2.36, 0, 38.0),
    # west wall: a low walnut sideboard with a lamp, a vase and books (it was
    # bare in the main view); north of the living2 camera at (0.55, 2.0)
    ("furn_living", "build_tv_console", {}, 0.21, 3.2, 90),
    ("furn_bedroom", "build_table_lamp", {}, 0.21, 3.7, 0, 48.0),
    # a different set from the coffee table's: the same vase, books, bowl and
    # candle twice in one frame read as copy-paste
    ("furn_living", "build_decor_books", {"variant": 1}, 0.2, 2.85, 95, 48.0),
    # kitchen: wall-to-wall run, sink centred under the window
    ("furn_kitchen", "build_kitchen_run",
     {"length": 290, "sink_at": 142, "cook_at": 245, "shelf": (0, 60)}, 6.73, 0.31, 0),
    ("furn_kitchen", "build_fridge", {}, 7.83, 3.84, 180),
    ("furn_kitchen", "build_dining_table", {}, 6.45, 2.15, 0),
    ("furn_kitchen", "build_dining_chair", {}, 6.1, 1.55, 0),
    ("furn_kitchen", "build_dining_chair", {}, 6.8, 1.55, 0),
    ("furn_kitchen", "build_dining_chair", {}, 6.1, 2.75, 180),
    ("furn_kitchen", "build_dining_chair", {}, 6.8, 2.75, 180),
    ("furn_kitchen", "build_pendant_lamp", {"drop": 80}, 6.45, 2.15, 0),
    ("furn_kitchen", "build_table_decor", {}, 6.45, 2.15, 0, 75.0),
    # lived-in touches: a mug on the coffee table, things left on nightstands
    ("furn_living", "build_mug", {"yaw": -35.0}, 2.43, 2.42, 0, 38.0),
    ("furn_living", "build_bedside_props", {"book": True, "glass": False}, 2.36, 4.47, 0, 50.0),
    ("furn_living", "build_bedside_props", {"book": False, "glass": True}, 4.64, 4.47, 0, 50.0),
    ("furn_living", "build_bedside_props", {"book": True, "glass": True, "seed": 1}, 3.095, 7.07, 0, 50.0),
    # bedroom 1: bed between the hall and bathroom doors (too shallow for a wardrobe)
    ("furn_bedroom", "build_bed", {"width": 150}, 3.5, 5.355, 0),
    ("furn_bedroom", "build_nightstand", {}, 2.36, 4.47, 0),
    ("furn_bedroom", "build_nightstand", {}, 4.64, 4.47, 0),
    ("furn_bedroom", "build_table_lamp", {}, 2.36, 4.47, 0, 50.0),
    ("furn_bedroom", "build_table_lamp", {}, 4.64, 4.47, 0, 50.0),
    # bedroom 2: bed east of the door's swing, one nightstand
    ("furn_bedroom", "build_bed", {"width": 160}, 1.895, 7.955, 0),
    ("furn_bedroom", "build_nightstand", {}, 3.095, 7.07, 0),
    ("furn_bedroom", "build_table_lamp", {}, 3.095, 7.07, 0, 50.0),
    ("furn_bedroom", "build_bench", {}, 1.895, 9.33, 0),   # 4 cm clear of the duvet hem
    ("furn_bedroom", "build_bedroom_rug", {"w": 240, "l": 200}, 1.895, 8.75, 0),
    ("furn_bedroom", "build_wardrobe", {"length": 260, "depth": 60}, 4.87, 8.3, -90),
    # bathroom: shower in the outer corner, WC on the outer wall clear of the door
    ("furn_bathroom", "build_shower", {"size": 90}, 6.745, 6.345, 180),
    ("furn_bathroom", "build_toilet", {}, 6.82, 5.35, -90),
    ("furn_bathroom", "build_vanity", {"width": 80}, 6.6, 4.495, 0),
    ("furn_bathroom", "build_mirror", {}, 6.6, 4.272, 0),
    ("furn_bathroom", "build_towel_rail", {}, 5.6, 4.32, 0),
    ("furn_bathroom", "build_bath_decor", {}, 7.095, 5.35, -90, 112.0),
]


PLACED = []      # (LAYOUT index, function, dummy, [nodes]) for the layout probe


def build_furniture():
    mods = {}
    for i, item in enumerate(LAYOUT):
        modname, fn, kw, px, py, rot = item[:6]
        z = item[6] if len(item) > 6 else 0.0
        x, y = P(px, py)
        try:
            if modname not in mods:
                mods[modname] = importlib.import_module(modname)
                importlib.reload(mods[modname])
            start = len(kit.PARTS)
            g = getattr(mods[modname], fn)(**kw)
            kit.place(g, x, y, z, rot)
            nodes = []
            for node, key, tile, maptype in kit.PARTS[start:]:
                finish(node, key, tile or 100.0, maptype)
                nodes.append(node)
            PLACED.append((i, fn, g, nodes))
        except Exception:
            log("furniture %s.%s failed: %s" % (modname, fn, traceback.format_exc().splitlines()[-1]))


def dump_layout(path):
    """World AABB and facing of every placed piece, for layout_check.py."""
    items = []
    for i, fn, g, nodes in PLACED:
        lo = [1e9] * 3
        hi = [-1e9] * 3
        for n in nodes:
            for k, (a, b) in enumerate(zip((n.min.x, n.min.y, n.min.z), (n.max.x, n.max.y, n.max.z))):
                lo[k] = min(lo[k], float(a))
                hi[k] = max(hi[k], float(b))
        row = g.transform.row2                    # local +Y in world
        items.append({"index": i, "fn": fn, "rot": LAYOUT[i][5], "min": lo, "max": hi,
                      "front": [-float(row.x), -float(row.y)]})
    doors = []
    for g, width, rooms in DOORS:
        row = g.transform.row1                    # the leaf runs along local +X
        doors.append({"rooms": list(rooms), "hinge": [float(g.pos.x), float(g.pos.y)],
                      "dir": [float(row.x), float(row.y)], "len": float(width)})
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"items": items, "doors": doors, "log": LOG}, fh, indent=1)


# ------------------------------------------------------------ lighting, cameras, render
def setup_renderer():
    vray = [c for c in rt.RendererClass.classes if "V_Ray" in str(c) and "GPU" not in str(c)][0]
    r = vray()
    rt.renderers.production = r
    r.imageSampler_type = 3
    final = QUALITY == "final"
    quick = QUALITY == "preview"                 # 640 x 400 look checks
    r.progressive_noise_threshold = 0.006 if final else 0.03 if quick else 0.02
    # minutes, a safety net: the noise threshold sets the quality, so a busy
    # CPU costs time instead of handing the denoiser half-converged frames
    r.progressive_max_render_time = 30.0 if final else 1.5 if quick else 5.0
    r.progressive_maxSamples = 400 if final else 150
    r.gi_on = True
    r.gi_primary_type = 2
    r.gi_secondary_type = 3
    r.lightcache_subdivs = 2500 if final else 1200
    r.lightcache_useForGlossyRays = False      # LC blotches in satin wall sheen
    # Reinhard with burn 0.55, as in the realism lab: sunlit floor patches and
    # windows roll off softly instead of clipping flat white
    r.colorMapping_type = 6
    r.colorMapping_darkMult = 1.0
    r.colorMapping_brightMult = 0.4        # 0.55 clipped sunlit white fabric to paper
    r.colorMapping_gamma = 2.2
    # 16-bit PNGs: denoised walls band in 8 bits; run_apartment.py dithers them
    rt.pngio.setType(rt.Name("true48"))
    rt.pngio.setAlpha(False)
    try:
        rem = rt.maxOps.GetCurRenderElementMgr()
        rem.RemoveAllRenderElements()
        den = rt.VRayDenoiser()
        den.mode = 2
        kit.setp(den, "preSet", 0)          # mild: keeps wood grain and weave
        rem.AddRenderElement(den)
    except Exception as exc:
        log("denoiser: %s" % exc)


def setup_lights():
    # late-morning sun from the north-west so it rakes through the living windows
    sun = rt.VRaySun(pos=rt.Point3(-1800, 2600, 1500), target=rt.Targetobject(pos=rt.Point3(250, -200, 0)))
    sun.name = "Sun"
    kit.setp(sun, "size_multiplier", 2.0)
    kit.setp(sun, "turbidity", 3.6)          # a warmer sun: at 2.6 the patches read cold white
    sky = rt.VRaySky()
    rt.environmentMap = sky
    rt.useEnvironmentMap = True
    dome = rt.VRayLight()
    dome.name = "SkyDome"
    dome.type = 1
    dome.texmap = rt.VRaySky()
    kit.setp(dome, "texmap_on", True)
    kit.setp(dome, "dome_adaptive", True)
    kit.setp(dome, "multiplier", 1.0)
    kit.setp(dome, "invisible", True)
    # windowless rooms get warm 3500 K ceiling downlights (disc lights face -Z)
    for name, (px, py) in (("bath", (6.2, 5.4)), ("hall", (1.0, 5.5)), ("bed1", (3.6, 5.3))):
        lt = rt.VRayLight()
        lt.name = "Downlight_" + name
        lt.type = 4
        kit.setp(lt, "size0", 9.0)
        kit.setp(lt, "color_mode", 1)              # temperature
        kit.setp(lt, "color_temperature", 3500.0)         # 3000 K turned the white hall door orange
        kit.setp(lt, "multiplier", 40.0)
        kit.setp(lt, "invisible", False)
        x, y = P(px, py)
        lt.pos = rt.Point3(x, y, H - 1.0)


def special_materials():
    """Per-board tint variants for the oak floors (MatForge build_variants on
    the forged albedo; the faces carry the variant IDs). Curtains, shades,
    solid glass and sprigs are MatForge recipes picked in MATS."""
    boards = 0
    for n in list(rt.objects):
        if str(n.name).startswith("FloorPlanks_") and n.material is not None:
            n.material = builder.build_variants(n.material, PLANK_TINTS)
            boards += 1
    log("oak boards: %d rooms, %d tint variants" % (boards, len(PLANK_TINTS)))


# Wool pile on the rugs (VRayFur on their top faces, ID 1): with bump, and
# even with displacement, they read as felt with no tufts or pile shadows.
# Per cm2: 10 tufts 0.5 mm thick, 1.1 cm long, leaning at random and drooping
# a little, coloured from the rug's own map at the root.
RUG_PILE = {"length": 1.1, "lengthVar": 0.25, "thickness": 0.05, "thicknessVar": 0.3,
            "gravity": -0.35, "gravityVar": 0.4, "Bend": 0.7, "Taper": 0.55, "directionVar": 0.45,
            "distribution": 1, "perArea": 10.0, "numKnots": 5, "numSides": 3, "lod_on": False,
            "placement": 2, "materialID": 1, "map_base_chan": 1}


def rug_pile():
    n_fur = 0
    for n in list(rt.objects):
        if str(n.name) != "Rug" or n.material is None:
            continue
        fur = rt.VRayFur()
        fur.sourceNode = n
        miss = [k for k, v in RUG_PILE.items() if not kit.setp(fur, k, v)]
        fur.material = n.material
        fur.name = "RugPile"
        n_fur += 1
        if miss:
            log("rug pile: not set %s" % miss)
    log("rug pile: %d rugs" % n_fur)


# The street photo outside is self-lit and compensates the camera exposure,
# so it kept one on-screen brightness while the rooms were re-exposed for
# their walls: the sunlit street came out no brighter than the room, a backlit
# poster tinted red-brown by the glass's reflection of the room. Its
# multiplier now follows each camera's exposure time, as a real exterior's
# brightness would.
BACKDROP_K = float(os.environ.get("MF_APT_BACKDROP_K", "550"))   # multiplier x (1/shutter)
BACKDROP_MAX = 30.0       # at 60 the views blew out to a glowing white poster


def set_backdrop(cam):
    n = rt.getNodeByName("Backdrop")
    if n is None or n.material is None:
        return
    m = min(BACKDROP_MAX, BACKDROP_K / max(float(cam.shutter_speed), 1e-3))
    n.material.multiplier = m
    log("backdrop x%.1f" % m)


# Camera -> rooms whose table lamps are on for it, as a photographer would
# switch them on: windowless bedroom 1 under one ceiling downlight read flat.
CAM_LAMPS = {"bedroom1": ("bed1",), "bedroom": ("bed2",)}
LAMPS = []       # (room id, VRayLight)


def build_lamp_lights(pl):
    """A 2700 K sphere light in every table lamp's bulb, off until a camera
    asks for its room, and translucent shades so a lit lamp glows through its
    linen (MatForge fabric_sheer: an opaque shade only threw light out of its
    top and bottom)."""
    for i, fn, g, nodes in PLACED:
        if fn != "build_table_lamp":
            continue
        px, py = float(g.pos.x) / 100.0, -float(g.pos.y) / 100.0
        room = next((r.id for r in pl.rooms.values()
                     if r.x <= px <= r.x1 and r.y <= py <= r.y1), None)
        lt = rt.VRayLight()
        lt.name = "LampBulb_%d_%s" % (i, room)
        lt.type = 2                                   # sphere
        kit.setp(lt, "size0", 2.6)                    # inside the 3 cm globe
        if not kit.setp(lt, "normalizeColor", 1):     # luminous power, lm
            log("lamp lights: no lm units on VRayLight; left off")
            return
        kit.setp(lt, "multiplier", 470.0)             # a 40 W-equivalent bulb
        kit.setp(lt, "color_mode", 1)
        kit.setp(lt, "color_temperature", 2700.0)
        kit.setp(lt, "invisible", True)               # the bulb mesh shows instead
        lt.pos = rt.Point3(float(g.pos.x), float(g.pos.y), float(g.pos.z) + 36.8)
        lt.on = False
        LAMPS.append((room, lt))
        for n in nodes:
            nm = str(n.name)
            if nm == "Lamp_Bulb":
                n.castShadows = False                 # lets the sphere light out
    log("lamp lights: %s" % ", ".join("%s %s" % (room, str(lt.name)) for room, lt in LAMPS))


def set_lamps(key):
    rooms = CAM_LAMPS.get(key, ())
    for room, lt in LAMPS:
        lt.on = room in rooms


CAMS = {
    #             plan pos (x, y), height cm, plan target (x, y), target z, focal mm
    "living":   ((4.85, 0.75), 135, (2.0, 3.7), 85, 20),
    "living2":  ((0.55, 2.0), 140, (5.0, 1.7), 100, 22),
    "sofa":     ((3.9, 1.0), 115, (2.6, 3.5), 88, 28),
    "kitchen":  ((5.7, 3.7), 145, (7.0, 0.5), 100, 20),
    "bedroom":  ((3.24, 9.70), 125, (1.5, 7.2), 75, 22),
    "bedroom1": ((4.9, 6.4), 145, (3.1, 4.3), 80, 18),
    "bath":     ((5.45, 6.6), 150, (6.8, 4.4), 110, 18),
    "hall":     ((1.7, 6.6), 145, (0.3, 4.4), 110, 20),
    "overview": ((13.5, 15.0), 1400, (4.1, 4.9), 0, 30),
}


def camera(key):
    (px, py), h, (tx, ty), tz, f = CAMS[key]
    x, y = P(px, py)
    t = P(tx, ty)
    cam = rt.VRayPhysicalCamera(pos=rt.Point3(x, y, h), target=rt.Targetobject(pos=rt.Point3(t[0], t[1], tz)))
    cam.name = "Cam_" + key
    cam.film_width = 36.0
    cam.focal_length = float(f)
    cam.f_number = 8.0
    cam.ISO = 200.0
    cam.shutter_speed = 60.0
    kit.setp(cam, "lens_tilt_auto", key != "overview")   # straight verticals
    kit.setp(cam, "whiteBalance_preset", 4)              # D65 for the daylit rooms
    if key in WHITE_BALANCE_K:
        # setting a temperature switches the preset to Temperature (7, verified)
        cam.temperature = WHITE_BALANCE_K[key]
    return cam


# The bathroom, lit by its 3500 K downlight, is white-balanced toward it, as a
# photographer would: under D65 it came out yellow-green. (Bedroom 1 and the
# hall had 4000 K and 5000 K here; WB_PATCH below now balances them.)
WHITE_BALANCE_K = {"bath": 4000.0}

# Views with no sun in them are white-balanced on a plain wall, as a
# photographer would on a grey card: the soda-lime window glass absorbs red,
# so sky light comes in cyan, and warm white paint turns cyan light green.
# Under the D65 preset (no correction in V-Ray) bedroom 2 came out green, and
# the hall yellow-green at 5000 K. Frame fractions (x0, y0, x1, y1) of the
# wall patch, the wall's material key, and a warmth kept on top of the
# paint's own albedo (r, b factors): the downlit rooms stay a little warm.
# Measured with the table lamps off; they are switched on after.
WB_PATCH = {
    "living": ((0.62, 0.15, 0.90, 0.45), "wall_limewash", (1.0, 1.0)),
    "living2": ((0.58, 0.08, 0.82, 0.35), "wall_limewash", (1.0, 1.0)),
    "sofa": ((0.03, 0.05, 0.20, 0.35), "wall_limewash", (1.0, 1.0)),
    "bedroom": ((0.71, 0.04, 0.97, 0.31), "wall_paint", (1.0, 1.0)),
    "bedroom1": ((0.42, 0.04, 0.62, 0.30), "wall_paint", (1.03, 0.90)),
    "hall": ((0.36, 0.15, 0.45, 0.70), "wall_paint", (1.03, 0.90)),
    "kitchen": ((0.58, 0.05, 0.74, 0.40), "wall_paint", (1.0, 1.0)),       # wall between the windows
    "bath": ((0.08, 0.25, 0.20, 0.75), "door", (1.03, 0.92)),              # the white door leaf
}
# Views with a wall patch are exposed for it, as an interior photographer
# exposes for the white walls and lets windows and sun patches go bright:
# metered on the frame mean (0.19, like a camera's average metering) the
# white rooms came out a stop or more under, grey-khaki with no true whites.
# Target: the patch's luminance in the saved image, linear.
PATCH_EXPOSURE = 0.42     # 0.5 read high-key and washed out; 0.45 still clipped sunlit fabric


def _lin8(v):
    v = float(v) / 255.0
    return v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4


def mean_rgb(path, box=(0.0, 0.0, 1.0, 1.0), rows=20, cols=28):
    """Mean linear RGB over a frame-fraction box of an image, sampled on a
    rows x cols grid (sRGB-encoded files, as the renders and albedo maps are)."""
    cs = builder._data_color_space()
    bm = rt.openBitMap(path, colorSpace=cs) if cs else rt.openBitMap(path, gamma=1.0)
    w, h = int(bm.width), int(bm.height)
    x0, x1 = int(box[0] * w), max(int(box[0] * w) + 1, int(box[2] * w))
    y0, y1 = int(box[1] * h), max(int(box[1] * h) + 1, int(box[3] * h))
    acc, n = [0.0, 0.0, 0.0], 0
    for yy in range(y0, y1, max(1, (y1 - y0) // rows)):
        for px in list(rt.getPixels(bm, rt.Point2(x0, yy), x1 - x0))[::max(1, (x1 - x0) // cols)]:
            acc[0] += _lin8(px.r)
            acc[1] += _lin8(px.g)
            acc[2] += _lin8(px.b)
            n += 1
    rt.close(bm)
    return [a / max(n, 1) for a in acc]


def lin_mean(path):
    r, g, b = mean_rgb(path)
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def _quick(cam, tag, key, i):
    p = os.path.join(OUT, "_%s_%s_%d_%d.png" % (tag, key, i, int(time.time())))
    rt.render(camera=cam, outputwidth=320, outputheight=200, outputfile=p, vfb=False, quiet=True)
    return p


def white_balance(cam, key):
    """Custom white balance from a wall patch; three feedback steps. V-Ray's
    response to the swatch is about its 1.5 power (measured: a linear swatch
    over-corrected, an sRGB-encoded one under-corrected), so each step takes
    the 2/3 power of the error."""
    box, mkey, (warm_r, warm_b) = WB_PATCH[key]
    matforge(mkey)
    alb = mean_rgb(_MANIFEST[mkey]["maps"]["albedo"], rows=32, cols=32)
    want = [warm_r * alb[0] / alb[1], 1.0, warm_b * alb[2] / alb[1]]
    kit.setp(cam, "whiteBalance_preset", 0)            # custom
    lamps = [(lt, lt.on) for _, lt in LAMPS]
    for lt, _ in lamps:
        lt.on = False                                   # balance on daylight alone
    wb = [1.0, 1.0, 1.0]
    steps = 0
    for i in range(6):
        if steps == 3:
            break
        cam.white_balance = rt.Color(*[255.0 * c for c in wb])
        m = mean_rgb(_quick(cam, "wb", key, i), box)
        lum = 0.2126 * m[0] + 0.7152 * m[1] + 0.0722 * m[2]
        if not 0.06 < lum < 0.6:
            # expose the patch first: with its lamps off bedroom 1 read 0.005
            # at 1/60, too dark to read a colour from
            cam.shutter_speed = max(0.25, min(4000.0, float(cam.shutter_speed) * max(lum, 1e-4) / 0.2))
            log("white balance %s: patch %.3f, shutter -> 1/%.0f" % (key, lum, float(cam.shutter_speed)))
            continue
        steps += 1
        got = [c / max(m[1], 1e-6) for c in m]
        wb = [w * (g / t) ** 0.67 for w, g, t in zip(wb, got, want)]
        top = max(wb)
        wb = [c / top for c in wb]
        log("white balance %s: wall r/g %.3f b/g %.3f (want %.3f %.3f) -> %s" % (
            key, got[0], got[2], want[0], want[2], [round(c, 3) for c in wb]))
    cam.white_balance = rt.Color(*[255.0 * c for c in wb])
    for lt, on in lamps:
        lt.on = on


def expose(cam, key, target=0.19):
    r = rt.renderers.production
    keep = (r.progressive_noise_threshold, r.progressive_max_render_time)
    r.progressive_noise_threshold, r.progressive_max_render_time = 0.1, 0.2
    patch = WB_PATCH.get(key)
    if patch:
        # expose the patch first: V-Ray's colour mapping (Reinhard, burn
        # 0.4) pulls bright channels together, so a balance struck on a
        # patch metered at 0.06 lost about a third of its warmth by the
        # final exposure (benchmark 1: r/g 1.07 -> 1.02, b/g 0.91 -> 0.97)
        for i in range(2):
            p = _quick(cam, "pre", key, i)
            r_, g_, b_ = mean_rgb(p, patch[0])
            m = 0.2126 * r_ + 0.7152 * g_ + 0.0722 * b_
            cam.shutter_speed = max(0.25, min(4000.0, float(cam.shutter_speed) * m / PATCH_EXPOSURE))
            log("pre-exposure %s: wall %.3f -> 1/%.0f" % (key, m, float(cam.shutter_speed)))
        white_balance(cam, key)
        target = PATCH_EXPOSURE
    for i in range(3 if patch else 2):
        p = os.path.join(OUT, "_exp_%s_%d_%d.png" % (key, i, int(time.time())))
        rt.render(camera=cam, outputwidth=320, outputheight=200, outputfile=p, vfb=False, quiet=True)
        if patch:
            r_, g_, b_ = mean_rgb(p, patch[0])
            m = 0.2126 * r_ + 0.7152 * g_ + 0.0722 * b_
        else:
            m = lin_mean(p)
        # down to 1/0.25 (4 s): the lamp-lit bathroom stayed under-exposed at 1 s
        cam.shutter_speed = max(0.25, min(4000.0, float(cam.shutter_speed) * m / target))
        log("exposure %s: %s %.3f -> 1/%.0f" % (key, "wall" if patch else "mean", m,
                                               float(cam.shutter_speed)))
    r.progressive_noise_threshold, r.progressive_max_render_time = keep


def main():
    t0 = time.time()
    rt.resetMaxFile(rt.Name("noPrompt"))
    rt.units.SystemType = rt.Name("centimeters")
    rt.units.DisplayType = rt.Name("metric")
    rt.units.MetricType = rt.Name("centimeters")
    setup_renderer()
    pl = planmod.load(os.path.join(HERE, "plan_two_bed.txt"), H / 100.0)
    kit.PARTS.clear()
    build_architecture(pl)
    build_curtains(pl)
    build_details(pl)
    build_backdrop()
    build_leaf_casters()
    log("architecture built in %.0fs" % (time.time() - t0))
    build_furniture()
    log("furniture built in %.0fs: %d nodes" % (time.time() - t0, len(rt.objects)))
    probe = os.environ.get("MF_APT_PROBE")
    if probe:                                    # layout check only: no materials, no renders
        dump_layout(probe)
        return
    apply_materials()
    special_materials()
    rug_pile()
    setup_lights()
    build_lamp_lights(pl)
    log("scene built in %.0fs: %d nodes, %d MatForge materials" % (
        time.time() - t0, len(rt.objects), len(_MAT_CACHE)))
    save = os.environ.get("MF_APT_SAVE")
    if save:
        rt.saveMaxFile(save, quiet=True)
        log("saved " + save)
    keys = [k for k in os.environ.get("MF_APT_CAMS", "").split(",") if k] or list(CAMS)
    keys = sorted(keys, key=lambda k: k == "overview")   # cut-away last
    w, h = {"final": (2400, 1500), "preview": (640, 400)}.get(QUALITY, (1280, 800))
    for key in keys:
        try:
            for n in rt.objects:                 # the cut-away: no ceilings, no backdrop ring
                nm = str(n.name)
                if nm.startswith("Ceiling_") or nm == "Backdrop":
                    n.isHidden = key == "overview"
                elif nm == "Ground_Far":
                    n.isHidden = key != "overview"
            set_doors(key)
            set_lamps(key)
            bd = rt.getNodeByName("Backdrop")
            if bd is not None and bd.material is not None:
                bd.material.multiplier = 5.0       # the metering baseline for every view
            cam = camera(key)
            expose(cam, key)
            set_backdrop(cam)
            log("render %s started" % key)
            t1 = time.time()
            out = os.path.join(OUT, "%s.png" % key)
            rt.render(camera=cam, outputwidth=w, outputheight=h, outputfile=out, vfb=False, quiet=True)
            log("render %s %.0fs -> %s" % (key, time.time() - t1, out))
        except Exception:
            log("render %s failed: %s" % (key, traceback.format_exc()))
    with open(os.path.join(OUT, "_apartment_log.json"), "w", encoding="utf-8") as fh:
        json.dump({"log": LOG, "seconds": round(time.time() - t0)}, fh, indent=1)


# MF_APT_LIBRARY: import the builders without building or rendering (experiments)
if not os.environ.get("MF_APT_LIBRARY"):
    try:
        main()
    except Exception:
        LOG.append(traceback.format_exc())
        with open(os.path.join(OUT, "_apartment_log.json"), "w", encoding="utf-8") as fh:
            json.dump({"fatal": traceback.format_exc(), "log": LOG}, fh, indent=1)
