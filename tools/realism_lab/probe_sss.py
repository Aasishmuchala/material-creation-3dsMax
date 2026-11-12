"""V-Ray 7 probe #2 (3dsmaxbatch): refraction-glossiness flip and translucency modes.

Spheres, left to right, back-lit by a low sun so subsurface glow is obvious:
  1 refraction gloss 0.5, useRoughness OFF   2 same, ON
  3 SSS (translucency_on=6), translucency_amount 0.2
  4 SSS (6), amount 1.0                     5 SSS (6), amount 5.0
  6 current MatForge marble: hard wax (1) + 0.06 grey refraction
  7 plain diffuse marble (no translucency)
"""
import os

from pymxs import runtime as rt

OUT = r"C:\Users\aasis\matforge\tools\realism_lab\out\probe_sss.png"
rt.resetMaxFile(rt.Name("noPrompt"))
rt.units.SystemType = rt.Name("centimeters")
vray = [c for c in rt.RendererClass.classes if "V_Ray" in str(c) and "GPU" not in str(c)][0]
r = vray()
rt.renderers.production = r
r.imageSampler_type = 3
r.progressive_max_render_time = 1.0
r.progressive_noise_threshold = 0.02

g = rt.Plane(width=3000, length=3000, pos=rt.Point3(0, 0, 0))
gm = rt.VRayMtl()
gm.diffuse = rt.Color(90, 90, 90)
g.material = gm
for k in range(14):
    b = rt.Box(width=12, length=2, height=90, pos=rt.Point3(-190 + k * 30, 70, 0))
    bm = rt.VRayMtl()
    bm.diffuse = rt.Color(230, 230, 230) if k % 2 else rt.Color(20, 20, 20)
    b.material = bm

MARBLE = rt.Color(0.83 * 255, 0.79 * 255, 0.75 * 255)


def make(i):
    m = rt.VRayMtl()
    m.brdf_useRoughness = True
    m.reflection = rt.Color(255, 255, 255)
    m.reflection_glossiness = 0.12
    if i in (0, 1):
        m.brdf_useRoughness = (i == 1)
        m.reflection_glossiness = 1.0 if i == 0 else 0.0
        m.diffuse = rt.Color(0, 0, 0)
        m.refraction = rt.Color(255, 255, 255)
        m.refraction_ior = 1.5
        m.refraction_glossiness = 0.5
        return m
    m.diffuse = MARBLE
    if i in (2, 3, 4):
        m.translucency_on = 6
        m.translucency_color = rt.Color(0.85 * 255, 0.56 * 255, 0.40 * 255)
        m.translucency_amount = (0.2, 1.0, 5.0)[i - 2]
    elif i == 5:
        m.refraction = rt.Color(15, 15, 15)
        m.refraction_fogColor = rt.Color(0.93 * 255, 0.91 * 255, 0.88 * 255)
        m.translucency_on = 1
        m.translucency_color = rt.Color(0.93 * 255, 0.91 * 255, 0.88 * 255)
    return m


for i in range(7):
    s = rt.Sphere(radius=18, segs=64, pos=rt.Point3(-150 + i * 50, 0, 18))
    s.material = make(i)
sun = rt.VRaySun(pos=rt.Point3(200, 900, 160), target=rt.Targetobject(pos=rt.Point3(0, 0, 0)))
rt.environmentMap = rt.VRaySky()
cam = rt.VRayPhysicalCamera(pos=rt.Point3(0, -360, 55), target=rt.Targetobject(pos=rt.Point3(0, 0, 18)))
cam.focal_length = 35
cam.f_number = 8
cam.shutter_speed = 120
cam.ISO = 100
rt.render(camera=cam, outputwidth=1750, outputheight=440, outputfile=OUT, vfb=False, quiet=True)
