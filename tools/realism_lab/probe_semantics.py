"""Does brdf_useRoughness flip coat / sheen / refraction glossiness? (3dsmaxbatch)

Renders six spheres in a row; each isolates one lobe on a black base:
  1 coat gloss 0.95, useRoughness OFF     2 same, useRoughness ON
  3 sheen gloss 0.95, useRoughness OFF    4 same, useRoughness ON
  5 refraction gloss 0.9, useRoughness OFF 6 same, useRoughness ON
Sharp sun highlights / clear refraction mean "glossiness"; blurry means "roughness".
"""
import os

from pymxs import runtime as rt

OUT = os.environ.get("MF_PROBE_OUT", r"C:\Users\aasis\matforge\tools\realism_lab\out\probe_semantics.png")
rt.resetMaxFile(rt.Name("noPrompt"))
rt.units.SystemType = rt.Name("centimeters")
vray = [c for c in rt.RendererClass.classes if "V_Ray" in str(c) and "GPU" not in str(c)][0]
r = vray()
rt.renderers.production = r
r.imageSampler_type = 3
r.progressive_max_render_time = 0.6
r.progressive_noise_threshold = 0.02

g = rt.Plane(width=2000, length=2000, pos=rt.Point3(0, 0, 0))
gm = rt.VRayMtl()
gm.diffuse = rt.Color(120, 120, 120)
g.material = gm


def mtl(i):
    m = rt.VRayMtl()
    m.diffuse = rt.Color(10, 10, 10)
    m.reflection = rt.Color(0, 0, 0)
    m.brdf_useRoughness = (i % 2 == 1)
    if i < 2:
        m.coat_amount = 1.0
        m.coat_glossiness = 0.95
        m.coat_ior = 1.5
    elif i < 4:
        m.sheen_color = rt.Color(255, 255, 255)
        m.sheen_glossiness = 0.95
    else:
        m.diffuse = rt.Color(0, 0, 0)
        m.refraction = rt.Color(255, 255, 255)
        m.refraction_ior = 1.5
        m.refraction_glossiness = 0.9
    return m


for i in range(6):
    s = rt.Sphere(radius=20, segs=64, pos=rt.Point3(-125 + i * 50, 0, 20))
    s.material = mtl(i)
# a striped backdrop so refraction blur is easy to read
for k in range(12):
    b = rt.Box(width=10, length=2, height=80, pos=rt.Point3(-165 + k * 30, 60, 0))
    bm = rt.VRayMtl()
    bm.diffuse = rt.Color(230, 230, 230) if k % 2 else rt.Color(20, 20, 20)
    b.material = bm
sun = rt.VRaySun(pos=rt.Point3(-500, -800, 600), target=rt.Targetobject(pos=rt.Point3(0, 0, 0)))
rt.environmentMap = rt.VRaySky()
cam = rt.VRayPhysicalCamera(pos=rt.Point3(0, -330, 60), target=rt.Targetobject(pos=rt.Point3(0, 0, 18)))
cam.focal_length = 35
cam.f_number = 8
cam.shutter_speed = 300
cam.ISO = 100
rt.render(camera=cam, outputwidth=1500, outputheight=420, outputfile=OUT, vfb=False, quiet=True)
