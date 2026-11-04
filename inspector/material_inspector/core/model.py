"""Renderer-neutral description of a material as the Inspector sees it.

The 3ds Max adapter fills these records from VRayMtl / CoronaPhysicalMtl nodes;
the rule engine only ever sees these records, so it is testable without Max.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class Renderer(str, Enum):
    VRAY = "vray"
    CORONA = "corona"
    OPENPBR = "openpbr"
    OTHER = "other"


class SlotRole(str, Enum):
    BASE_COLOR = "base_color"
    ROUGHNESS = "roughness"
    GLOSSINESS = "glossiness"
    METALNESS = "metalness"
    NORMAL = "normal"
    BUMP = "bump"
    DISPLACEMENT = "displacement"
    OPACITY = "opacity"
    REFLECTION_COLOR = "reflection_color"
    REFRACTION = "refraction"
    IOR = "ior"
    TRANSLUCENCY = "translucency"
    COAT = "coat"
    SHEEN = "sheen"
    EMISSION = "emission"
    OTHER = "other"


#: Slots whose pixels are numbers, not colours: they must be loaded linear (no gamma).
DATA_ROLES = frozenset({
    SlotRole.ROUGHNESS, SlotRole.GLOSSINESS, SlotRole.METALNESS, SlotRole.NORMAL,
    SlotRole.BUMP, SlotRole.DISPLACEMENT, SlotRole.OPACITY, SlotRole.IOR,
})

#: Slots whose pixels are colours: they must be loaded as sRGB (8/16-bit files).
COLOR_ROLES = frozenset({
    SlotRole.BASE_COLOR, SlotRole.REFLECTION_COLOR, SlotRole.TRANSLUCENCY,
    SlotRole.SHEEN, SlotRole.EMISSION,
})


class ColorSpace(str, Enum):
    SRGB = "srgb"
    LINEAR = "linear"
    UNKNOWN = "unknown"   # adapter could not read it: reported, never guessed


class Severity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class TextureRef:
    """One bitmap feeding one material slot."""
    role: SlotRole
    path: Optional[str]
    color_space: ColorSpace = ColorSpace.UNKNOWN
    node_class: str = ""
    node_name: str = ""
    #: For NORMAL / BUMP slots: True if a normal-map node (VRayNormalMap,
    #: CoronaNormal, Normal Bump) sits between the bitmap and the slot.
    via_normal_node: Optional[bool] = None
    #: True / False when the normal node's green-flip setting is known.
    normal_flip_green: Optional[bool] = None
    file_exists: Optional[bool] = None
    handle: Any = field(default=None, repr=False, compare=False)


@dataclass
class MaterialRecord:
    """Canonical view of one material.

    ``params`` uses canonical keys (see ``PARAM_KEYS``). Colours are the raw 0–1
    stored swatch values (stored/255). 3ds Max stores these scene-linear; the
    rules that read them document their own convention (R010 reads albedo as
    8-bit sRGB by design; R011/R018 treat metal swatches as linear F0).
    Missing keys mean "not applicable or not read", never a default.
    """
    name: str
    renderer: Renderer
    material_class: str
    params: dict[str, Any] = field(default_factory=dict)
    textures: list[TextureRef] = field(default_factory=list)
    scene_path: str = ""
    handle: Any = field(default=None, repr=False, compare=False)

    def textures_for(self, role: SlotRole) -> list[TextureRef]:
        return [t for t in self.textures if t.role == role]

    def has_texture(self, role: SlotRole) -> bool:
        return any(t.role == role and t.path for t in self.textures)


PARAM_KEYS = {
    "base_color": "rgb tuple 0–1 (raw stored swatch value; Max stores it scene-linear)",
    "roughness": "float 0–1 when the material is in roughness mode",
    "glossiness": "float 0–1 when the material is in glossiness mode",
    "use_roughness": "bool — V-Ray: BRDF 'Use roughness'",
    "brdf": "str — e.g. 'ggx', 'blinn', 'phong', 'ward'",
    "metalness": "float 0–1",
    "ior": "float — reflection / Fresnel IOR",
    "refraction_amount": "float 0–1 (V-Ray: refract colour value; Corona: refraction amount)",
    "refraction_ior": "float",
    "absorption_color": "rgb tuple 0–1 or None (V-Ray fog colour / Corona absorption colour)",
    "absorption_distance": "float scene units or None",
    "thin_walled": "bool",
    "complex_ior": "bool — Corona: Complex IOR (n,k) on; base colour then unused (R011/R018 skip)",
    "is_legacy": "bool — Corona Legacy Mtl or other superseded type",
}


@dataclass
class FixAction:
    """A renderer-neutral change the adapter knows how to apply (with undo)."""
    kind: str                     # e.g. "set_color_space", "set_param", "toggle_use_roughness"
    target: str                   # param key or texture node name
    value: Any = None
    description: str = ""


@dataclass
class Finding:
    rule_id: str
    severity: Severity
    material: str
    message: str
    detail: str = ""
    fix: Optional[FixAction] = None
    texture: Optional[str] = None

    @property
    def fixable(self) -> bool:
        return self.fix is not None
