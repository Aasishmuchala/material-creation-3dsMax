"""A fake `pymxs.runtime` good enough to exercise builder.py's wiring LOGIC
off-Max.

It records every property set, answers isProperty() from a per-class schema
of valid V-Ray property names, and models the handful of runtime calls the
builder makes (Color, Name, classOf, openBitMap, meditMaterials, medit,
selection, addModifier). This lets pytest verify — deterministically, with no
3ds Max — that:
  * each material class produces the right node graph (e.g. foliage -> a
    VRay2SidedMtl wrapper with NO refraction; glass -> thin-walled refraction)
  * data maps load linear and albedo does not
  * the defensive _set_first fallback and MISS-logging actually work

The schemas mirror real V-Ray 6/7 property names (the FIRST candidate in each
builder list). If the builder's primary candidate ever drifts from a real
name, these tests surface it as a logged MISS.
"""

# Valid property names per node class (isProperty answers from these).
VRAYMTL_PROPS = frozenset({
    "diffuse", "texmap_diffuse",
    "reflection", "reflection_fresnel", "brdf_useRoughness",
    "texmap_reflectionGlossiness", "reflection_glossiness",
    "reflection_metalness", "texmap_metalness", "anisotropy",
    "reflection_lockIOR",
    "refraction_ior", "refraction", "refraction_fogColor",
    "refraction_fogMult", "refraction_affectShadows", "refraction_thinWalled",
    "refraction_glossiness",  # frosted/etched glass (rough refraction)
    "texmap_opacity", "opacity_mode", "texmap_bump", "texmap_bump_multiplier",
    "texmap_displacement", "texmap_displacement_multiplier",
    "sheen_color", "sheen_glossiness", "coat_amount", "coat_glossiness",
    "translucency_on", "translucency_color",
    "texmap_self_illumination", "selfIllumination",  # emissive / LED
    "selfIllumination_multiplier",
    "name",  # V-Ray 7: _on, not bare
})
TWOSIDED_PROPS = frozenset({"frontMtl", "translucency", "name"})
NORMALMAP_PROPS = frozenset({"normal_map", "name"})
BITMAP_PROPS = frozenset({"filename", "fileName", "bitmap", "name"})
DISP_PROPS = frozenset({"type", "amount", "texmap", "name"})

_SCHEMAS = {
    "VRayMtl": VRAYMTL_PROPS,
    "VRay2SidedMtl": TWOSIDED_PROPS,
    "VRayNormalMap": NORMALMAP_PROPS,
    "Bitmaptexture": BITMAP_PROPS,
    "VRayDisplacementMod": DISP_PROPS,
}


class MockName:
    def __init__(self, s):
        self._s = str(s)

    def __str__(self):
        return self._s

    def __repr__(self):
        return "Name('%s')" % self._s

    def __eq__(self, other):
        return str(other) == self._s

    def __hash__(self):
        return hash(self._s)


class MockColor:
    def __init__(self, r, g, b):
        self.r, self.g, self.b = r, g, b

    def as_unit(self):
        return (self.r / 255.0, self.g / 255.0, self.b / 255.0)

    def __repr__(self):
        return "Color(%.1f,%.1f,%.1f)" % (self.r, self.g, self.b)


class MockBitmap:
    def __init__(self, path, gamma=None):
        self.path = path
        self.gamma = gamma

    def __repr__(self):
        return "Bitmap(%r, gamma=%r)" % (self.path, self.gamma)


class MockNode:
    """Records attribute writes into .props; isProperty via .schema."""

    def __init__(self, cls, schema):
        object.__setattr__(self, "cls", cls)
        object.__setattr__(self, "schema", schema)
        object.__setattr__(self, "props", {})
        object.__setattr__(self, "modifiers", [])

    def __setattr__(self, key, value):
        self.props[key] = value

    def __getattr__(self, key):
        props = object.__getattribute__(self, "props")
        if key in props:
            return props[key]
        raise AttributeError(key)

    def has_prop(self, name):
        return str(name) in object.__getattribute__(self, "schema")

    def __repr__(self):
        return "<%s %s>" % (self.cls, sorted(self.props))


class MockMeditArray:
    def __init__(self, count=24):
        self._slots = [MockNode("PhysicalMaterial", frozenset())
                       for _ in range(count)]
        for i, m in enumerate(self._slots):
            m.props["name"] = "%02d - Default" % (i + 1)

    @property
    def count(self):
        return len(self._slots)

    def __getitem__(self, i):
        return self._slots[i]

    def __setitem__(self, i, v):
        self._slots[i] = v


class MockMedit:
    def __init__(self, active_slot=1):
        self._active = active_slot
        self.calls = []

    def GetActiveMtlSlot(self):
        return self._active

    def SetActiveMtlSlot(self, slot, update):
        self.calls.append((slot, update))
        self._active = slot


class MockMatEditor:
    def __init__(self):
        self.opened = False

    def Open(self):
        self.opened = True


_UNIT_MM = {"mm": 1.0, "cm": 10.0, "m": 1000.0, "in": 25.4, "ft": 304.8}


class MockUnits:
    """Models rt.units.decodeValue: parse '<n>mm' and return the value in the
    scene's SYSTEM units (so mm -> system-units conversion is testable)."""

    def __init__(self, system_unit="mm"):
        self.system_unit = system_unit
        self.SystemType = system_unit

    def decodeValue(self, s):
        s = str(s).strip().lower()
        for suffix, mm in _UNIT_MM.items():
            if s.endswith(suffix):
                val_mm = float(s[: -len(suffix)]) * mm
                return val_mm / _UNIT_MM[self.system_unit]
        return float(s)


class MockUndo:
    """Context-manager stand-in for pymxs.undo(True, label)."""

    def __init__(self, enabled=True, label=""):
        self.enabled = enabled
        self.label = label

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class MockRuntime:
    def __init__(self, selection=None, active_slot=1, drop=frozenset(),
                 system_unit="mm"):
        self._drop = frozenset(drop)
        self.meditMaterials = MockMeditArray()
        self.medit = MockMedit(active_slot)
        self.MatEditor = MockMatEditor()
        self.units = MockUnits(system_unit)
        self.selection = list(selection or [])
        self.added_modifiers = []
        self.deleted_modifiers = []

    # --- node factories ---
    def _node(self, cls):
        schema = _SCHEMAS[cls] - self._drop
        return MockNode(cls, schema)

    def VRayMtl(self):
        return self._node("VRayMtl")

    def VRay2SidedMtl(self):
        return self._node("VRay2SidedMtl")

    def VRayNormalMap(self):
        return self._node("VRayNormalMap")

    def Bitmaptexture(self):
        return self._node("Bitmaptexture")

    def VRayDisplacementMod(self):
        return self._node("VRayDisplacementMod")

    # --- runtime helpers ---
    def Name(self, s):
        return MockName(s)

    def Color(self, r, g, b):
        return MockColor(r, g, b)

    def classOf(self, obj):
        return MockName(getattr(obj, "cls", type(obj).__name__))

    def isProperty(self, obj, name):
        return hasattr(obj, "has_prop") and obj.has_prop(name)

    def openBitMap(self, path, gamma=None):
        return MockBitmap(path, gamma)

    def addModifier(self, node, mod):
        node.modifiers.append(mod)
        self.added_modifiers.append((node, mod))

    def deleteModifier(self, node, mod):
        if mod in node.modifiers:
            node.modifiers.remove(mod)
        self.deleted_modifiers.append((node, mod))


def make_scene_nodes(n):
    """n selectable scene objects."""
    nodes = []
    for i in range(n):
        node = MockNode("Editable_Poly", frozenset())
        node.props["name"] = "Object%02d" % (i + 1)
        nodes.append(node)
    return nodes


def install(selection=None, active_slot=1, drop=frozenset(), system_unit="mm"):
    """Inject a fresh fake `pymxs` into sys.modules and (re)load builder.

    Returns (builder_module, runtime). Call once per test for isolation.
    """
    import importlib
    import sys
    import types

    rt = MockRuntime(selection=selection, active_slot=active_slot, drop=drop,
                     system_unit=system_unit)
    fake = types.ModuleType("pymxs")
    fake.runtime = rt
    fake.undo = MockUndo  # pymxs.undo(True, label) -> context manager
    sys.modules["pymxs"] = fake

    import maxplugin.builder as builder
    importlib.reload(builder)
    return builder, rt
