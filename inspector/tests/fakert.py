"""A minimal stand-in for pymxs.runtime, enough to exercise the scene walker and fixes.

``FakeRT(fresh_wrappers=True)`` mimics pymxs object identity: every access returns a
NEW Python proxy (so ``id()`` is meaningless and gets reused once a proxy is freed),
while ``getHandleByAnim`` returns the underlying node's stable handle.
"""
from __future__ import annotations

import itertools

_HANDLES = itertools.count(1)


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
        self._handle = next(_HANDLES)        # MAXScript anim handle: stable for the session


class Wrapper:
    """pymxs-like proxy: a fresh Python object per access; equal by the underlying node."""
    __slots__ = ("_n",)

    def __init__(self, n):
        object.__setattr__(self, "_n", n)

    def __getattr__(self, k):
        return getattr(self._n, k)

    def __eq__(self, o):
        return isinstance(o, Wrapper) and o._n is self._n

    def __hash__(self):
        return id(self._n)


def unwrap(o):
    return o._n if isinstance(o, Wrapper) else o


class FakeRT:
    def __init__(self, materials=(), existing_files=(), fresh_wrappers=False):
        self._fresh = fresh_wrappers
        self.sceneMaterials = list(materials)
        self._files = set(existing_files)
        self.Color = Color

        class _Units:
            SystemType = "#millimeters"
            SystemScale = 1.0
        self.units = _Units()

    def _w(self, v):
        return Wrapper(v) if self._fresh and isinstance(v, Node) else v

    @property
    def sceneMaterials(self):
        return [self._w(m) for m in self._mats]

    @sceneMaterials.setter
    def sceneMaterials(self, v):
        self._mats = [unwrap(m) for m in v]

    def classOf(self, obj):
        return unwrap(obj)._cls

    def isProperty(self, obj, name):
        return name in unwrap(obj)._props

    def getProperty(self, obj, name):
        return self._w(unwrap(obj)._props[name])

    def setProperty(self, obj, name, value):
        obj = unwrap(obj)
        if name not in obj._props:
            raise KeyError(name)
        obj._props[name] = unwrap(value)

    def getNumSubMtls(self, m):
        return len(unwrap(m)._subs)

    def getSubMtl(self, m, i):
        return self._w(unwrap(m)._subs[i - 1])

    def getNumSubTexmaps(self, t):
        return len(unwrap(t)._subtex)

    def getSubTexmap(self, t, i):
        return self._w(unwrap(t)._subtex[i - 1])

    def getHandleByAnim(self, obj):
        n = unwrap(obj)
        if not isinstance(n, Node):
            raise TypeError(f"getHandleByAnim: not an animatable: {obj!r}")
        return n._handle

    def doesFileExist(self, p):
        return p in self._files

    # constructors used by fixes
    def VRayNormalMap(self):
        return Node("VRayNormalMap", normal_map=None, flip_green=False)

    def CoronaNormal(self):
        return Node("CoronaNormal", normalMap=None, flipgreen=False)

    def Normal_Bump(self):
        return Node("Normal_Bump", normal_map=None, flipgreen=False)

    def openBitMap(self, path, gamma=None):
        return Node("Bitmap", gamma=2.2 if gamma is None else float(gamma), filename=path)

    def Output(self):
        return Node("Output", map1=None, output=Node("StandardTextureOutput", invert=False))
