"""Lights for the MatForge benchmark-2 living room (moody contemporary: copper
Venetian plaster, grey microcement, white marble): a modern branch chandelier
of clear blown-glass globes and a slim spotlight for a recessed ceiling track.

Both hang from the ceiling, so - unlike the floor pieces - each is built round
its own mounting point ON THE CEILING: x = y = 0 there, z = 0 at the ceiling
plane, the piece hanging down -Z (centimetres, Z up), FRONT facing -Y at
rotation 0. Every visible node goes through kit.part and the piece comes back
as kit.group: kit.place(group, x, y, ceiling_z, rot_deg).

  build_chandelier(drop=80, seed=0) -> (group, bulb_positions)
      12 cm round canopy with a collar, a 1.2 cm drop rod `drop` cm long
      (30-300) to an upper hub, a 22 cm stem to a lower hub and a drop finial.
      Six arms of 1.2 cm round black rod (metal_black, domed soft ends, 2.4 cm
      bends) leave the hubs at right angles - three per tier, in different
      directions - and branch again at right angles into upward, hanging and
      sideways sockets. Runs of 25-45 cm make an asymmetric composition whose
      six globes balance within 1 cm of the drop rod in plan; about 109 x 59 cm
      in plan, 82 cm from the top of the highest globe to the bottom of the
      lowest. Each arm ends in a fitter cup (5.1 cm, 2.2 mm wall, three
      thumbscrews) holding a clear blown globe (glass_solid): a real hollow
      20 cm sphere with a 2.5 mm wall and a 4.4 cm neck opening in the cup,
      fire-polished rim. In each globe a slim LED filament bulb: lampholder,
      nickel cap, 2.2 cm tubular envelope with a 0.7 mm wall, glass stem, two
      lead wires and a coiled filament (emissive_warm). bulb_positions are the
      six filament centres (x, y, z) relative to the origin, for the scene's
      lights. `seed` gives each globe its hand-blown irregularity (size +-1.5 %,
      ovality, up to 1.2 degrees of tilt in its cup) and turns the filaments
      and thumbscrews; the layout and the bulb positions do not change.
  build_track_spot(tilt_deg=30)
      slim black cylinder spot, 6 x 12 cm, on a short adapter for a recessed
      track running along X (the adapter body sits 2.8 cm up in the track and
      0.7 cm below the ceiling): swivel collar, stem, horizontal knuckle with
      pivot screws, the body tilted tilt_deg (0-90) from straight down towards
      the front (-Y); a dark stepped baffle inside the front ring and a
      recessed LED face (emissive_warm). track_spot_aim(tilt_deg) gives the LED
      face centre and the beam direction for the scene's light.

All geometry is pure Python (furn_living._MD cages): chandelier_layout,
bulb_positions, chandelier_parts, globe_profile, bulb_profile, cup_profile,
track_spot_parts, track_spot_aim... return points or lists of
(name, material key, _MD, tile cm, TurboSmooth iterations), tested off-Max in
tests/test_bench2_lights_geom.py; the build_* wrappers only make the nodes.
"""
import math

import kit
from furn_living import (_MD, _hard, _fillet2d, _revolve_md, _tube_md, _slab, _Rand, _rot_axis,
                         _add, _sub, _mul, _dot, _cross, _norm)

METAL = 25.0        # cm per texture repeat: powder coat, nickel
GLASS = 30.0
GLOW = 10.0
STEP = math.radians(22.5)

# ----------------------------------------------------------- chandelier frame
CANOPY_R, CANOPY_H = 6.0, 2.4
COLLAR_R, COLLAR_H = 1.1, 2.2
ROD_R = 0.6                     # 1.2 cm round rod
HUB_R, HUB_H = 1.15, 3.6        # cylindrical couplers at the two tiers
TIER = 22.0                     # upper hub to lower hub
BEND_R = 2.4                    # centre-line radius of the rod bends
FINIAL_L = 6.8
DROP_MIN, DROP_MAX = 30.0, 300.0

_DIRS = {"+x": (1.0, 0.0, 0.0), "-x": (-1.0, 0.0, 0.0), "+y": (0.0, 1.0, 0.0),
         "-y": (0.0, -1.0, 0.0), "+z": (0.0, 0.0, 1.0), "-z": (0.0, 0.0, -1.0)}

# (tier, runs): each run (direction, cm) from the hub axis or the previous
# corner; the last run points the socket (up, down or sideways).
ARMS = (
    (0, (("+x", 31.0),)),                               # long sideways arm, right
    (0, (("-x", 38.0), ("+z", 7.0))),                   # left, globe standing up
    (0, (("-y", 19.0), ("-z", 6.0))),                   # front, globe hanging
    (1, (("-x", 30.0),)),                               # sideways arm, left
    (1, (("+x", 21.0), ("-z", 5.0))),                   # right, globe hanging lowest
    (1, (("+y", 20.0), ("+x", 13.0), ("+z", 7.0))),     # back, branching right, up
)

# --------------------------------------------- socket cup (cup-local w, 0 = lip)
CUP_RO, CUP_RI = 2.55, 2.33     # 2.2 mm wall
CUP_FLOOR = -1.9
CUP_DEPTH = 3.1                 # rod end (back of the boss) to the lip
SCREW_W = -0.75                 # thumbscrew plane = pivot of a globe's tilt

# ------------------------------------------------------------ blown globe
GLOBE_R = 10.0
GLOBE_WALL = 0.25
NECK_RO = 2.2
NECK_RI = NECK_RO - GLOBE_WALL  # the opening at the socket
NECK_RIM = -1.2                 # the neck reaches 1.2 cm into the cup
NECK_TOP = 1.0                  # where the neck meets the sphere

# ------------------------------------------------- LED filament bulb (T22)
BULB_R, BULB_WALL, BULB_TIP = 1.1, 0.07, 8.0
COIL_W0, COIL_W1 = 2.6, 5.8
COIL_R, COIL_WIRE, COIL_TURNS = 0.42, 0.055, 5.5
BULB_W = 0.5 * (COIL_W0 + COIL_W1)     # lip to the filament centre


# ===================================================================== helpers
def _prof(pts, radii, closed=False, step=STEP):
    """_fillet2d, then drop points that coincide with their neighbour."""
    out = []
    for p in _fillet2d(pts, radii, closed=closed, step=step):
        if out and math.hypot(p[0] - out[-1][0], p[1] - out[-1][1]) < 1e-6:
            continue
        out.append((p[0], p[1]))
    if closed and len(out) > 2 and math.hypot(out[0][0] - out[-1][0], out[0][1] - out[-1][1]) < 1e-6:
        out.pop()
    return out


def _volume(md):
    """Signed volume: > 0 when a closed mesh faces outwards."""
    v, tot = md.v, 0.0
    for f in md.f:
        a = v[f[0]]
        for k in range(1, len(f) - 1):
            b, c = v[f[k]], v[f[k + 1]]
            tot += (a[0] * (b[1] * c[2] - b[2] * c[1]) + a[1] * (b[2] * c[0] - b[0] * c[2])
                    + a[2] * (b[0] * c[1] - b[1] * c[0]))
    return tot / 6.0


def _outward(md):
    if _volume(md) < 0.0:
        md.f = [tuple(reversed(f)) for f in md.f]
        md.fuv = [None if u is None else tuple(reversed(u)) for u in md.fuv]
    return md


def _frame(z_axis):
    """Right-handed orthonormal axes (X, Y, Z) with Z along z_axis."""
    z = _norm(z_axis)
    ref = (0.0, 0.0, 1.0) if abs(z[2]) < 0.9 else (1.0, 0.0, 0.0)
    x = _norm(_cross(ref, z))
    return x, _cross(z, x), z


def _to(md, origin, axes=None):
    """Move a cage from a local frame (axes X, Y, Z; origin) into its parent."""
    o = origin
    if axes is None:
        return md.map(lambda p: (p[0] + o[0], p[1] + o[1], p[2] + o[2]))
    X, Y, Z = axes
    return md.map(lambda p: (o[0] + X[0] * p[0] + Y[0] * p[1] + Z[0] * p[2],
                             o[1] + X[1] * p[0] + Y[1] * p[1] + Z[1] * p[2],
                             o[2] + X[2] * p[0] + Y[2] * p[1] + Z[2] * p[2]))


def _spin(profile, segs, origin=(0.0, 0.0, 0.0), axes=None, closed=False, phase=0.0):
    """Revolve an (r, w) section (counter-clockwise round the material) about
    the local Z axis and move it into place."""
    return _to(_revolve_md(profile, segs, closed=closed, phase=phase), origin, axes)


def _lathe(pts, radii, segs, origin=(0.0, 0.0, 0.0), axes=None, closed=False, step=STEP):
    return _spin(_prof(pts, radii, closed, step), segs, origin, axes, closed)


def _fillet3d(pts, radius, step=math.radians(15.0)):
    """Round the interior corners of a 3-D polyline with arcs of `radius`
    (smaller where a run is too short), as a rod is bent round a former."""
    out = [tuple(pts[0])]
    for i in range(1, len(pts) - 1):
        p = pts[i]
        a, b = _norm(_sub(p, pts[i - 1])), _norm(_sub(pts[i + 1], p))
        cs = max(-1.0, min(1.0, _dot(a, b)))
        turn = math.acos(cs)
        if turn < 1e-6:
            out.append(tuple(p))
            continue
        l1 = math.sqrt(_dot(_sub(p, pts[i - 1]), _sub(p, pts[i - 1])))
        l2 = math.sqrt(_dot(_sub(pts[i + 1], p), _sub(pts[i + 1], p)))
        r = radius
        tl = r * math.tan(0.5 * turn)
        lim = 0.45 * min(l1, l2)
        if tl > lim:
            tl = lim
            r = tl / math.tan(0.5 * turn)
        n = _norm(_sub(b, _mul(a, cs)))
        c = _add(_sub(p, _mul(a, tl)), _mul(n, r))
        k = max(2, int(math.ceil(turn / step)))
        for j in range(k + 1):
            ph = turn * j / k
            out.append(_add(c, _add(_mul(n, -r * math.cos(ph)), _mul(a, r * math.sin(ph)))))
    out.append(tuple(pts[-1]))
    return out


def _rod_md(path, r=ROD_R, sides=12, seg=4):
    """Round rod along a 3-D polyline with domed (soft) ends: a closed solid.
    r may be a per-point list."""
    rad = list(r) if isinstance(r, (list, tuple)) else [float(r)] * len(path)
    t0 = _norm(_sub(path[1], path[0]))
    t1 = _norm(_sub(path[-1], path[-2]))
    pts, rr = [], []
    for k in range(seg, 0, -1):
        th = 0.5 * math.pi * k / (seg + 0.4)
        pts.append(_sub(path[0], _mul(t0, rad[0] * math.sin(th))))
        rr.append(rad[0] * math.cos(th))
    pts += [tuple(p) for p in path]
    rr += rad
    for k in range(1, seg + 1):
        th = 0.5 * math.pi * k / (seg + 0.4)
        pts.append(_add(path[-1], _mul(t1, rad[-1] * math.sin(th))))
        rr.append(rad[-1] * math.cos(th))
    return _outward(_tube_md(pts, rr, sides))


def _nodes(parts):
    """Max nodes for (name, mat, md, tile, smooth) parts."""
    return [_hard(md, name, mat, tile, smooth) for name, mat, md, tile, smooth in parts]


# ================================================================ chandelier
def globe_centre_w(R=GLOBE_R, k_axial=1.0):
    """Cup-local w of the centre of a globe of outer radius R (lip at w = 0)."""
    return NECK_TOP + math.sqrt(R * R - NECK_RO * NECK_RO) * k_axial


def chandelier_layout(drop=80.0):
    """Key points of the chandelier (origin: canopy centre on the ceiling).
    Returns {"drop", "z_collar", "hubs": [upper, lower], "finial_tip", "arms":
    [{"tier", "runs", "corners" (hub axis .. rod end), "dir" (socket axis),
    "socket" (rod end = back of the cup), "lip", "bulb" (filament centre),
    "globe" (nominal globe centre)}]}."""
    drop = float(drop)
    if not DROP_MIN <= drop <= DROP_MAX:
        raise ValueError("drop %.1f cm outside %.0f-%.0f cm" % (drop, DROP_MIN, DROP_MAX))
    z_col = -(CANOPY_H + COLLAR_H)                     # underside of the collar
    z1 = z_col - drop - 0.5 * HUB_H
    hubs = [(0.0, 0.0, z1), (0.0, 0.0, z1 - TIER)]
    gc = globe_centre_w()
    arms = []
    for tier, runs in ARMS:
        p = hubs[tier]
        corners = [p]
        for name, ln in runs:
            p = _add(p, _mul(_DIRS[name], ln))
            corners.append(p)
        d = _DIRS[runs[-1][0]]
        s = corners[-1]
        arms.append({"tier": tier, "runs": runs, "corners": corners, "dir": d, "socket": s,
                     "lip": _add(s, _mul(d, CUP_DEPTH)),
                     "bulb": _add(s, _mul(d, CUP_DEPTH + BULB_W)),
                     "globe": _add(s, _mul(d, CUP_DEPTH + gc))})
    return {"drop": drop, "z_collar": z_col, "hubs": hubs, "arms": arms,
            "finial_tip": (0.0, 0.0, hubs[1][2] - 0.5 * HUB_H - FINIAL_L)}


def bulb_positions(drop=80.0):
    """Filament centres of the six bulbs, relative to the chandelier origin."""
    return [a["bulb"] for a in chandelier_layout(drop)["arms"]]


def arm_path(arm):
    """Centre line of an arm's rod: from inside its hub, round 2.4 cm bends,
    into the boss of its cup."""
    cs = arm["corners"]
    d0 = _norm(_sub(cs[1], cs[0]))
    pts = [_add(cs[0], _mul(d0, 0.3))] + list(cs[1:-1]) + [_add(cs[-1], _mul(arm["dir"], 0.35))]
    return _fillet3d(pts, BEND_R)


def canopy_md():
    """Round canopy against the ceiling (6 mm eased bottom edge, slight taper)
    and the stepped collar under it that grips the drop rod."""
    md = _lathe([(0.0, -CANOPY_H), (CANOPY_R - 0.3, -CANOPY_H), (CANOPY_R, 0.0), (0.0, 0.0)],
                [0.0, 0.6, 0.08, 0.0], 48, step=math.radians(15.0))
    zc = -(CANOPY_H + COLLAR_H)
    md.merge(_lathe([(0.0, zc), (COLLAR_R, zc), (COLLAR_R, zc + 1.6), (COLLAR_R - 0.12, zc + 1.75),
                     (COLLAR_R - 0.12, -CANOPY_H + 0.05), (0.0, -CANOPY_H + 0.05)],
                    [0.0, 0.18, 0.06, 0.04, 0.0, 0.0], 24))
    return md


def frame_md(L):
    """Drop rod, stem, the two hubs, the finial and the six bent arms."""
    h1, h2 = L["hubs"]
    hh = 0.5 * HUB_H
    md = _MD()
    md.merge(_rod_md([(0.0, 0.0, L["z_collar"] + 0.4), (0.0, 0.0, h1[2] + hh - 0.4)]))
    md.merge(_rod_md([(0.0, 0.0, h1[2] - hh + 0.4), (0.0, 0.0, h2[2] + hh - 0.4)]))
    for h in (h1, h2):
        md.merge(_lathe([(0.0, -hh), (HUB_R, -hh), (HUB_R, hh), (0.0, hh)], [0.0, 0.25, 0.25, 0.0], 24,
                        origin=h))
    md.merge(_lathe([(0.0, -hh - FINIAL_L), (0.85, -hh - FINIAL_L), (0.85, -hh - 1.3), (0.55, -hh - 0.9),
                     (0.55, -hh + 0.3), (0.0, -hh + 0.3)], [0.0, 0.4, 0.15, 0.12, 0.0, 0.0], 24, origin=h2))
    for arm in L["arms"]:
        md.merge(_rod_md(arm_path(arm)))
    return md


def cup_profile():
    """(r, w) section of the fitter cup: boss for the rod, back plate, 2.2 mm
    wall, rounded lip at w = 0, floor at CUP_FLOOR."""
    return _prof([(0.0, -CUP_DEPTH), (0.95, -CUP_DEPTH), (0.95, -2.6), (CUP_RO, -2.6), (CUP_RO, 0.0),
                  (CUP_RI, 0.0), (CUP_RI, CUP_FLOOR), (0.0, CUP_FLOOR)],
                 [0.0, 0.15, 0.2, 0.6, 0.1, 0.1, 0.15, 0.0])


def socket_md(screw_phase=0.0):
    """Cup-local fitter: the cup, an E14 lampholder on its floor and three
    knurled thumbscrews whose tips stop 0.1 mm off the globe neck."""
    md = _spin(cup_profile(), 32)
    md.merge(_lathe([(0.0, CUP_FLOOR - 0.05), (1.25, CUP_FLOOR - 0.05), (1.25, -0.55), (0.0, -0.55)],
                    [0.0, 0.03, 0.15, 0.0], 24))
    screw = ([(0.0, NECK_RO + 0.01), (0.16, NECK_RO + 0.01), (0.16, 2.95), (0.38, 2.95), (0.38, 3.35),
              (0.0, 3.35)], [0.0, 0.04, 0.03, 0.08, 0.12, 0.0])
    for k in range(3):
        a = screw_phase + 2.0 * math.pi * k / 3.0
        zs = (math.cos(a), math.sin(a), 0.0)
        xs = (0.0, 0.0, 1.0)
        md.merge(_lathe(screw[0], screw[1], 12, origin=(0.0, 0.0, SCREW_W), axes=(xs, _cross(zs, xs), zs)))
    return md


def globe_profile(R=GLOBE_R, wall=GLOBE_WALL, k_axial=1.0, n_arc=26):
    """Closed (r, w) section of a blown globe in cup-local w: the neck (outer
    radius NECK_RO, its fire-polished rim at NECK_RIM inside the cup) flaring
    through a 6 mm fillet into a hollow sphere of outer radius R and wall
    `wall`. k_axial stretches the sphere along its axis (from the neck)."""
    b0 = math.asin(NECK_RO / R)
    c = NECK_TOP + R * math.cos(b0)
    ri = R - wall
    b1 = math.asin(NECK_RI / ri)

    def ov(w):
        return NECK_TOP + (w - NECK_TOP) * k_axial
    pts, rad = [(NECK_RO, NECK_RIM), (NECK_RO, NECK_TOP)], [0.11, 0.6]
    for i in range(1, n_arc):
        b = b0 + (math.pi - b0) * i / n_arc
        pts.append((R * math.sin(b), ov(c - R * math.cos(b))))
        rad.append(0.0)
    pts += [(0.0, ov(c + R)), (0.0, ov(c + ri))]
    rad += [0.0, 0.0]
    for i in range(n_arc - 1, -1, -1):
        b = b1 + (math.pi - b1) * i / n_arc
        pts.append((ri * math.sin(b), ov(c - ri * math.cos(b))))
        rad.append(0.4 if i == 0 else 0.0)
    pts.append((NECK_RI, NECK_RIM))
    rad.append(0.11)
    return _prof(pts, rad, closed=True, step=math.radians(18.0))


def bulb_profile(wall=BULB_WALL):
    """Closed (r, w) section of the tubular glass envelope (cup-local): narrow
    sealed base in the cap, flare, 2.2 cm tube, round tip at BULB_TIP."""
    R, ri, r0, wd = BULB_R, BULB_R - wall, 0.62, BULB_TIP - BULB_R
    pts, rad = [(r0, 0.05), (r0, 0.35), (R, 1.15), (R, wd)], [0.02, 0.2, 0.45, 0.0]
    for k in range(1, 8):
        a = 0.5 * math.pi * k / 8.0
        pts.append((R * math.cos(a), wd + R * math.sin(a)))
        rad.append(0.0)
    pts += [(0.0, BULB_TIP), (0.0, BULB_TIP - wall)]
    rad += [0.0, 0.0]
    for k in range(7, -1, -1):
        a = 0.5 * math.pi * k / 8.0
        pts.append((ri * math.cos(a), wd + ri * math.sin(a)))
        rad.append(0.0)
    pts += [(ri, 1.18), (r0 - wall, 0.38), (r0 - wall, 0.05)]
    rad += [0.38, 0.13, 0.02]
    return _prof(pts, rad, closed=True, step=math.radians(15.0))


def _cyl(r, a, w):
    return (r * math.cos(a), r * math.sin(a), w)


def coil_path(phase=0.0, per_turn=18):
    """Helix of the LED filament (cup-local), COIL_TURNS turns."""
    n = int(round(COIL_TURNS * per_turn))
    return [_cyl(COIL_R, phase + 2.0 * math.pi * COIL_TURNS * i / n, COIL_W0 + (COIL_W1 - COIL_W0) * i / n)
            for i in range(n + 1)]


def bulb_md(coil_phase=0.0):
    """Cup-local (glass, metal, filament) cages of one bulb: envelope + glass
    stem; nickel cap + two lead wires; the coiled filament."""
    glass = _spin(bulb_profile(), 24, closed=True)
    glass.merge(_lathe([(0.0, 0.08), (0.2, 0.08), (0.2, 1.72), (0.0, 1.9)], [0.0, 0.02, 0.1, 0.0], 12))
    metal = _lathe([(0.0, -0.75), (0.72, -0.75), (0.72, 0.0), (0.6, 0.15), (0.0, 0.15)],
                   [0.0, 0.03, 0.06, 0.04, 0.0], 24)
    a, b = coil_phase, coil_phase + math.pi            # the coil ends half a turn apart
    lead_a = [_cyl(0.12, a, 1.7), _cyl(0.3, a, 2.25), _cyl(COIL_R, a, COIL_W0)]
    lead_b = [_cyl(0.12, b, 1.7), _cyl(0.75, b, 2.15), _cyl(0.75, b, COIL_W1 - 0.25), _cyl(COIL_R, b, COIL_W1)]
    for lead in (lead_a, lead_b):
        metal.merge(_rod_md(_fillet3d(lead, 0.12), 0.025, 6, 2))
    coil = _rod_md(coil_path(coil_phase), COIL_WIRE, 8, 3)
    return glass, metal, coil


def globe_variation(seed, k):
    """Hand-blown irregularity of globe k for a seed."""
    rnd = _Rand(seed * 131 + 7 * k + 11)
    return {"R": GLOBE_R * rnd.uniform(0.985, 1.015), "k_axial": rnd.uniform(0.988, 1.012),
            "phase": rnd.uniform(0.0, 2.0 * math.pi), "tilt": math.radians(rnd.uniform(0.3, 1.2)),
            "tilt_az": rnd.uniform(0.0, 2.0 * math.pi), "coil_phase": rnd.uniform(0.0, 2.0 * math.pi),
            "screw_phase": rnd.uniform(0.0, 2.0 * math.pi)}


def _tilt(md, ang, az, pivot_w):
    """Tip a cup-local cage by ang about a horizontal axis (azimuth az)
    through the point (0, 0, pivot_w)."""
    ax = (math.cos(az), math.sin(az), 0.0)
    o = (0.0, 0.0, pivot_w)
    return md.map(lambda p: _add(_rot_axis(_sub(p, o), ax, ang), o))


def chandelier_parts(drop=80.0, seed=0):
    """[(name, mat, md, tile, smooth)] of the chandelier (see build_chandelier)."""
    L = chandelier_layout(drop)
    sockets, bglass, bmetal, coils, globes = _MD(), _MD(), _MD(), _MD(), []
    for k, arm in enumerate(L["arms"]):
        g = globe_variation(seed, k)
        axes, lip = _frame(arm["dir"]), arm["lip"]
        sockets.merge(_to(socket_md(g["screw_phase"]), lip, axes))
        globe = _revolve_md(globe_profile(g["R"], GLOBE_WALL, g["k_axial"]), 40, closed=True, phase=g["phase"])
        globes.append(_to(_tilt(globe, g["tilt"], g["tilt_az"], SCREW_W), lip, axes))
        gl, mt, co = bulb_md(g["coil_phase"])
        bglass.merge(_to(gl, lip, axes))
        bmetal.merge(_to(mt, lip, axes))
        coils.merge(_to(co, lip, axes))
    parts = [("Chandelier_Canopy", "metal_black", canopy_md(), METAL, 1),
             ("Chandelier_Frame", "metal_black", frame_md(L), METAL, 1),
             ("Chandelier_Sockets", "metal_black", sockets, METAL, 1)]
    parts += [("Chandelier_Globe%d" % (k + 1), "glass_solid", g, GLASS, 1) for k, g in enumerate(globes)]
    parts += [("Chandelier_BulbGlass", "glass_solid", bglass, GLASS, 1),
              ("Chandelier_BulbMetal", "metal_steel", bmetal, METAL, 1),
              ("Chandelier_Filament", "emissive_warm", coils, GLOW, 0)]
    return parts


def build_chandelier(drop=80.0, seed=0):
    """Branch chandelier hanging from its canopy at the origin (ceiling, z = 0).
    Returns (group, bulb_positions): the six filament centres relative to the
    origin, for the scene's lights (turn them with the group if it is rotated)."""
    group = kit.group("Chandelier", _nodes(chandelier_parts(drop, seed)))
    return group, bulb_positions(drop)


# ================================================================ track spot
SPOT_R, SPOT_LEN = 3.0, 12.0     # body: 6 cm across, 12 cm long
SPOT_RI = 2.72                   # inside of the front ring
SPOT_FLOOR = 9.2                 # body-local w of the floor of the front cavity
SPOT_KZ = -3.8                   # knuckle axis below the ceiling
SPOT_NECK = 1.7                  # knuckle axis to the back of the body
BAFFLE_TOP = 11.75               # baffle stops 2.5 mm inside the front ring
BAFFLE_HOLE = 1.36
LED_FACE = 9.42
ADAPTER_X, ADAPTER_Y = 4.5, 1.6  # half length (along the track) and half width
ADAPTER_UP, ADAPTER_DOWN = 2.8, 0.7


def _spot_tilt(tilt_deg):
    t = float(tilt_deg)
    if not 0.0 <= t <= 90.0:
        raise ValueError("tilt %.1f deg outside 0-90" % t)
    return math.radians(t)


def _spot_axes(t):
    """Body frame for a tilt t (rad): X = the knuckle axis, Z = the beam."""
    d = (0.0, -math.sin(t), -math.cos(t))
    x = (1.0, 0.0, 0.0)
    return x, _cross(d, x), d


def _pan(pan_deg):
    """Rotation about the stem (Z) by pan_deg: the swivel under the adapter."""
    a = math.radians(float(pan_deg))
    c, s = math.cos(a), math.sin(a)
    return lambda p: (p[0] * c - p[1] * s, p[0] * s + p[1] * c, p[2])


def track_spot_aim(tilt_deg=30.0, pan_deg=0.0):
    """(centre of the LED face, unit beam direction) relative to the spot's
    origin, for the scene's light."""
    d = _spot_axes(_spot_tilt(tilt_deg))[2]
    rz = _pan(pan_deg)
    return rz(_add((0.0, 0.0, SPOT_KZ), _mul(d, SPOT_NECK + LED_FACE))), rz(d)


def _rbox_md(x0, x1, y0, y1, z0, z1, r, rv=(0.15, 0.15), p=8, q=4, m=2):
    """Rounded box (furn_living._slab cage): r rounds the vertical edges,
    rv = (bottom, top) the horizontal ones."""
    return _slab(0.5 * (x1 - x0), 0.5 * (y1 - y0), z0, z1, r, p=p, q=q, rb=(rv[0], rv[0]), rt_=(rv[1], rv[1]),
                 mb=m, ms=1, mt=m, cx=0.5 * (x0 + x1), cy=0.5 * (y0 + y1), amin=1)


def spot_body_profile():
    """(r, w) section of the body from its back face (w = 0): 4.5 mm eased
    back edge, a 0.7 mm shadow groove setting off the front ring, 2.8 mm
    ring wall with a rounded lip, the front cavity down to SPOT_FLOOR."""
    R, Ri = SPOT_R, SPOT_RI
    return _prof([(0.0, 0.0), (R, 0.0), (R, 10.85), (R - 0.07, 10.89), (R - 0.07, 10.95), (R, 10.99),
                  (R, SPOT_LEN), (Ri, SPOT_LEN), (Ri, SPOT_FLOOR), (0.0, SPOT_FLOOR)],
                 [0.0, 0.45, 0.02, 0.015, 0.015, 0.02, 0.13, 0.1, 0.08, 0.0])


def spot_baffle_profile(teeth=5):
    """Closed (r, w) section of the dark anti-glare baffle: a ring filling the
    front cavity, its bore stepping down in `teeth` undercut rings from 2.45
    to BAFFLE_HOLE around the LED."""
    ro = SPOT_RI - 0.02
    r, w = 2.45, BAFFLE_TOP
    h = (BAFFLE_TOP - 9.5) / teeth
    inset = (r - BAFFLE_HOLE) / teeth
    pts, rad = [(ro, SPOT_FLOOR + 0.02), (ro, BAFFLE_TOP), (r, BAFFLE_TOP)], [0.02, 0.06, 0.04]
    for _ in range(teeth):
        pts.append((r + 0.06, w - h))
        r, w = r - inset, w - h
        pts.append((r, w))
        rad += [0.03, 0.03]
    pts.append((BAFFLE_HOLE, SPOT_FLOOR + 0.02))
    rad.append(0.02)
    return _prof(pts, rad, closed=True)


def track_spot_parts(tilt_deg=30.0, pan_deg=0.0):
    """[(name, mat, md, tile, smooth)] of the track spot (see build_track_spot).
    pan_deg swivels everything below the collar about the stem, so the
    adapter stays along the track (X) whichever way the spot points."""
    t = _spot_tilt(tilt_deg)
    axes = _spot_axes(t)
    knuckle = (0.0, 0.0, SPOT_KZ)
    adapter = _rbox_md(-ADAPTER_X, ADAPTER_X, -ADAPTER_Y, ADAPTER_Y, -ADAPTER_DOWN, ADAPTER_UP, 0.5)
    adapter.merge(_rbox_md(2.3, 3.9, -0.35, 0.35, -ADAPTER_DOWN - 0.3, -ADAPTER_DOWN + 0.05, 0.3, (0.1, 0.05),
                           p=6, q=4))                                    # locking lever
    adapter.merge(_lathe([(0.0, SPOT_KZ + 0.3), (0.55, SPOT_KZ + 0.3), (0.55, -1.25), (0.9, -1.1),
                          (0.9, -ADAPTER_DOWN + 0.1), (0.0, -ADAPTER_DOWN + 0.1)],
                         [0.0, 0.0, 0.1, 0.06, 0.0, 0.0], 24))           # stem and swivel collar
    swivel = _lathe([(0.0, -1.15), (0.95, -1.15), (0.95, 1.15), (0.0, 1.15)], [0.0, 0.25, 0.25, 0.0], 24,
                    origin=knuckle, axes=_frame((1.0, 0.0, 0.0)))
    for sx in (1.0, -1.0):                                               # pivot screw and nut
        swivel.merge(_lathe([(0.0, 1.1), (0.45, 1.1), (0.45, 1.33), (0.0, 1.4)], [0.0, 0.0, 0.1, 0.0], 16,
                            origin=knuckle, axes=_frame((sx, 0.0, 0.0))))
    back = _add(knuckle, _mul(axes[2], SPOT_NECK))
    body = _spin(spot_body_profile(), 48, back, axes)
    body.merge(_lathe([(0.0, 0.0), (0.6, 0.0), (0.6, SPOT_NECK + 0.25), (0.0, SPOT_NECK + 0.25)],
                      [0.0, 0.0, 0.0, 0.0], 16, origin=knuckle, axes=axes))   # neck into the knuckle
    baffle = _spin(spot_baffle_profile(), 48, back, axes, closed=True)
    led = _lathe([(0.0, SPOT_FLOOR + 0.04), (BAFFLE_HOLE - 0.03, SPOT_FLOOR + 0.04), (BAFFLE_HOLE - 0.03, LED_FACE),
                  (0.0, LED_FACE)], [0.0, 0.03, 0.05, 0.0], 32, origin=back, axes=axes)
    if pan_deg:
        rz = _pan(pan_deg)
        for m in (swivel, body, baffle, led):
            m.map(rz)
    adapter.merge(swivel)
    return [("TrackSpot_Adapter", "metal_black", adapter, METAL, 1),
            ("TrackSpot_Body", "metal_black", body, METAL, 1),
            ("TrackSpot_Baffle", "metal_black", baffle, METAL, 1),
            ("TrackSpot_LED", "emissive_warm", led, GLOW, 1)]


def build_track_spot(tilt_deg=30.0, pan_deg=0.0):
    """Slim black track spot (6 x 12 cm body) hanging from its adapter at the
    origin (ceiling, z = 0; the track runs along X), aimed tilt_deg from
    straight down towards -Y, swivelled pan_deg about its stem (counter-
    clockwise from above). track_spot_aim() gives its light."""
    return kit.group("TrackSpot", _nodes(track_spot_parts(tilt_deg, pan_deg)))


# ================================================================= preview
def preview():
    """Chandelier at the origin under a 280 cm ceiling and a track spot beside
    it (run inside 3ds Max)."""
    chand, _bulbs = build_chandelier()
    kit.place(chand, 0.0, 0.0, 280.0)
    kit.place(build_track_spot(), 90.0, 0.0, 280.0)
    return chand
