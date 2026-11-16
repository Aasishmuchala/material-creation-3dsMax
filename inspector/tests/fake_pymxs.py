"""A fake `pymxs` module: enough of 3ds Max to execute tools/max_selftest.py end to end."""
import contextlib
import types

from material_inspector.max_adapter import props as P
from tests.fakert import Color, FakeRT, Node


def _defaults(cls):
    d = {}
    for names in P.PARAMS.get(cls, {}).values():
        n0 = names[0]
        if "color" in n0.lower() or n0 in ("diffuse", "refraction"):
            d[n0] = Color(128, 128, 128)
        elif "ior" in n0.lower():
            d[n0] = 1.5          # V-Ray / Corona ship IOR ≈ 1.5–1.6 by default
        elif n0 == "brdf_type":
            d[n0] = 3
        else:
            d[n0] = 0.0
    for names in P.SLOTS.get(cls, {}).values():
        d[names[0]] = None
    if cls in P.BITMAP_CLASSES:
        spec = P.BITMAP_CLASSES[cls]
        d[spec["path"][0]] = ""; d[spec["color_space"][0]] = "sRGB" if cls == "Bitmaptexture" else 2
    if cls in P.NORMAL_CLASSES:
        spec = P.NORMAL_CLASSES[cls]
        d[spec["input"][0]] = None; d[spec["flip_green"][0]] = False
    return d


class FakeMaxRuntime(FakeRT):
    def __init__(self):
        super().__init__()
        self.objects = []
        self.Point3 = lambda *a: tuple(a)
        self.messages = []

    @property
    def sceneMaterials(self):
        seen = []
        for o in self.objects:
            if o.material is not None and o.material not in seen:
                seen.append(o.material)
        return seen

    @sceneMaterials.setter
    def sceneMaterials(self, v):
        pass

    def _ctor(self, cls):
        def make(name="", **kw):
            n = Node(cls, name or cls, **_defaults(cls)); n._props.update(kw); return n
        return make

    def __getattr__(self, item):
        if item in P.PARAMS or item in P.BITMAP_CLASSES or item in ("Output",):
            return self._ctor(item)
        raise AttributeError(item)

    def execute(self, expr):
        known = {"maxVersion()": "#(28000, 0, 0)", "vrayVersion()": "#(\"7.00.00\")"}
        if expr in known:
            return known[expr]
        if expr in P.PARAMS or expr in P.BITMAP_CLASSES or expr in P.NORMAL_CLASSES or expr == "Output":
            return self.Output if expr == "Output" else (
                self._ctor(expr) if expr not in P.NORMAL_CLASSES else getattr(self, expr))
        return None

    def getPropNames(self, obj):
        return list(obj._props)

    def Box(self, **kw):
        b = Node("Box"); b.material = None; self.objects.append(b); return b

    def doesFileExist(self, p):
        import os
        return os.path.isfile(p)

    def messageBox(self, msg, title=""):
        self.messages.append(msg)


def install():
    mod = types.ModuleType("pymxs")
    mod.runtime = FakeMaxRuntime()
    mod.undo = lambda *a, **k: contextlib.nullcontext()
    return mod
