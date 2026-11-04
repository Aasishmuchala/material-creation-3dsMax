"""A minimal stand-in for pymxs.runtime, enough to exercise the scene walker and fixes."""
from __future__ import annotations


class Color:
    def __init__(self, r, g, b):
        self.r, self.g, self.b = float(r), float(g), float(b)

    def __repr__(self):
        return f"Color({self.r:.0f},{self.g:.0f},{self.b:.0f})"


class Node:
    def __init__(self, cls: str, name: str = "", subs=None, subtex=None, **props):
        self._cls, self.name, self._props = cls, name or cls, dict(props)
        self._subs = list(subs or [])        # sub-materials
        self._subtex = list(subtex or [])    # generic sub-texmaps


class FakeRT:
    def __init__(self, materials=(), existing_files=()):
        self.sceneMaterials = list(materials)
        self._files = set(existing_files)
        self.Color = Color

        class _Units:
            SystemType = "#millimeters"
            SystemScale = 1.0
        self.units = _Units()

    def classOf(self, obj):
        return obj._cls

    def isProperty(self, obj, name):
        return name in obj._props

    def getProperty(self, obj, name):
        return obj._props[name]

    def setProperty(self, obj, name, value):
        if name not in obj._props:
            raise KeyError(name)
        obj._props[name] = value

    def getNumSubMtls(self, m):
        return len(m._subs)

    def getSubMtl(self, m, i):
        return m._subs[i - 1]

    def getNumSubTexmaps(self, t):
        return len(t._subtex)

    def getSubTexmap(self, t, i):
        return t._subtex[i - 1]

    def doesFileExist(self, p):
        return p in self._files

    # constructors used by fixes
    def VRayNormalMap(self):
        return Node("VRayNormalMap", normal_map=None, flip_green=False)

    def CoronaNormal(self):
        return Node("CoronaNormal", normalMap=None, flipgreen=False)

    def openBitMap(self, path, gamma=None):
        return Node("Bitmap", gamma=2.2 if gamma is None else float(gamma), filename=path)

    def Output(self):
        return Node("Output", map1=None, output=Node("StandardTextureOutput", invert=False))
