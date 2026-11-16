"""Modelling kit shared by the apartment furniture modules (runs inside 3ds Max).

Conventions (every furniture module must follow them):
  * units: centimetres, Z up; build each piece at the local origin with its
    FRONT facing -Y and its base on z = 0, then return group(...) — the
    caller places and rotates the returned Dummy.
  * every visible node goes through part(node, mat_key, tile_cm) so the scene
    can give it a MatForge material at real-world texture scale.
  * soft goods (cushions, duvets, pillows) get soften() noise + TurboSmooth;
    hard goods get real bevels (ChamferBox fillet >= 0.2 cm) — nothing with
    a razor-sharp 90-degree edge.
MAT_KEYS lists the allowed material keys.
"""
import math

from pymxs import runtime as rt

MAT_KEYS = {
    "upholstery": "sofa / headboard fabric (linen)",
    "upholstery_alt": "armchair fabric (boucle)",
    "velvet": "accent cushions, ottoman",
    "leather": "chair seats, straps",
    "cushion": "scatter cushions (velvet or linen)",
    "wood_dark": "walnut furniture",
    "wood_light": "oak furniture, shelves, bed frames",
    "metal_brass": "brushed brass legs, lamp parts",
    "metal_black": "matte black powder-coated metal",
    "metal_steel": "brushed / satin stainless (appliances, sink)",
    "metal_chrome": "polished chrome taps, shower",
    "glass": "clear glass panes (shower screen, picture glass)",
    "glass_solid": "solid glass objects (vases, tumblers; MatForge glass_object)",
    "glass_frosted": "frosted glass (lamp diffuser)",
    "ceramic_white": "glazed white porcelain (toilet, basin, mugs)",
    "stone_worktop": "polished Calacatta marble (worktops, vanity top)",
    "stone_dark": "polished black granite / black glass cooktop",
    "paint_white": "satin white painted joinery (cabinets, wardrobes, doors)",
    "paint_sage": "satin sage-green painted joinery (accent cabinets)",
    "bedding": "white cotton (sheets, pillows)",
    "linen": "linen duvet, throws, upholstery details",
    "shade": "thin linen lamp shades (MatForge fabric_sheer: glows when lit)",
    "rug": "wool rug",
    "plant_leaf": "leaf cards (cut-out, keep the plane's own 0-1 UVs)",
    "stem": "plant stems and branches (plain green, no cut-out)",
    "twig": "small leafy sprigs in vases (MatForge foliage: translucent)",
    "water": "water in vases (MatForge water)",
    "pot_matte": "matte white stoneware planters (benchmark scenes)",
    "canvas_bag": "waxed canvas bags (benchmark scenes)",
    "leaf_card": "large cut-out leaf cards with the plant photo on 0-1 UVs (MatForge foliage)",
    "plant_pot": "terracotta pot",
    "plastic_black": "black plastic (TV body, remote, cables)",
    "screen": "TV / appliance black glass screen",
    "rubber": "rubber feet, seals",
    "paper": "books, boxes",
    "art_paper": "printed paper (a book's dust jacket)",
    "wax": "candles",
    "emissive_warm": "glowing bulbs / lamp diffusers",
    "mirror": "mirror glass",
    "soil": "potting soil",
}

PARTS = []        # [(node, mat_key, tile_cm, maptype)]


def part(node, mat, tile=None, maptype=4):
    """Register a visible node. tile = real-world size (cm) of one texture
    repeat for UVW box mapping; maptype None keeps the node's own UVs."""
    if mat not in MAT_KEYS:
        raise KeyError("unknown material key %r" % mat)
    PARTS.append((node, mat, tile, maptype))
    return node


def setp(obj, name, value):
    try:
        if rt.isProperty(obj, rt.Name(name)):
            setattr(obj, name, value)
            return True
    except Exception:
        pass
    return False


def cbox(w, l, h, fillet, x=0.0, y=0.0, z=0.0, segs=3):
    """ChamferBox: width along X, length along Y, height along Z, base at z.
    ChamferBox silently ignores filletSegs / widthsegs keywords (every box
    came out with 3 fillet segments); its names are Fillet_Segments etc."""
    return rt.ChamferBox(width=w, length=l, height=h, fillet=fillet, Fillet_Segments=segs,
                         Width_Segments=1, Length_Segments=1, Height_Segments=1,
                         pos=rt.Point3(x, y, z), mapcoords=True)


def box(w, l, h, x=0.0, y=0.0, z=0.0):
    return rt.Box(width=w, length=l, height=h, pos=rt.Point3(x, y, z), mapcoords=True)


def cyl(r, h, x=0.0, y=0.0, z=0.0, sides=32):
    return rt.Cylinder(radius=r, height=h, sides=sides, heightsegs=1,
                       pos=rt.Point3(x, y, z), mapcoords=True)


def sphere(r, x=0.0, y=0.0, z=0.0, segs=48):
    return rt.Sphere(radius=r, segs=segs, pos=rt.Point3(x, y, z), mapcoords=True)


def revolve(pts, x=0.0, y=0.0, z=0.0, segs=48, shell=None, smooth=1, name="rev"):
    """Revolve an (r, z) profile around Z. Open profile -> vessel, closed -> solid."""
    verts = []
    for r, zz in pts:
        for j in range(segs):
            a = 2.0 * math.pi * j / segs
            verts.append((x + r * math.cos(a), y + r * math.sin(a), z + zz))
    faces = []
    for i in range(len(pts) - 1):
        for j in range(segs):
            a = i * segs + j + 1
            b = i * segs + (j + 1) % segs + 1
            c = (i + 1) * segs + j + 1
            d = (i + 1) * segs + (j + 1) % segs + 1
            faces.append((a, b, c))
            faces.append((b, d, c))
    vs = ",".join("[%.4f,%.4f,%.4f]" % v for v in verts)
    fs = ",".join("[%d,%d,%d]" % f for f in faces)
    node = rt.execute('(m = mesh name:"%s" vertices:#(%s) faces:#(%s)\n'
                      'for f = 1 to m.numfaces do setFaceSmoothGroup m f 1\nupdate m\nm)'
                      % (name, vs, fs))
    if shell:
        sm = rt.Shell()
        setp(sm, "outerAmount", float(shell))
        setp(sm, "innerAmount", 0.0)
        rt.addModifier(node, sm)
    if smooth:
        ts = rt.TurboSmooth()
        ts.iterations = smooth
        rt.addModifier(node, ts)
    return node


def soften(node, noise=None, smooth=1, seed=0):
    """Soft-goods look: fractal Noise (scale, xy strength, z strength) then
    TurboSmooth. Use on cushions, mattresses, duvets, pillows."""
    if noise:
        nm = rt.Noisemodifier()
        setp(nm, "seed", seed)
        setp(nm, "scale", noise[0])
        setp(nm, "strength", rt.Point3(noise[1], noise[1], noise[2]))
        setp(nm, "fractal", True)
        rt.addModifier(node, nm)
    if smooth:
        ts = rt.TurboSmooth()
        ts.iterations = smooth
        rt.addModifier(node, ts)
    return node


def bend(node, angle, axis=2, direction=0.0):
    b = rt.Bend()
    setp(b, "BendAngle", float(angle))
    setp(b, "BendAxis", axis)
    setp(b, "BendDir", float(direction))
    rt.addModifier(node, b)
    return node


def taper(node, amount, curve=0.0):
    t = rt.Taper()
    setp(t, "amount", float(amount))
    setp(t, "curve", float(curve))
    rt.addModifier(node, t)
    return node


def rotate(node, deg, axis=(0, 0, 1)):
    rt.rotate(node, rt.angleaxis(deg, rt.Point3(*axis)))
    return node


def group(name, nodes):
    """Parent nodes to a Dummy at the origin; returns the Dummy."""
    d = rt.Dummy()
    d.name = name
    for n in nodes:
        n.parent = d
    return d


def place(dummy, x, y, z=0.0, rot_deg=0.0):
    """Rotate a group about Z (degrees, counter-clockwise from above) and move it."""
    if rot_deg:
        rt.rotate(dummy, rt.angleaxis(rot_deg, rt.Point3(0, 0, 1)))
    dummy.pos = rt.Point3(x, y, z)
    return dummy
