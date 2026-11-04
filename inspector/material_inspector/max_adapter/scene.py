"""Walk the 3ds Max scene and turn materials into MaterialRecords.

Takes the MAXScript runtime ``rt`` as an argument (``pymxs.runtime`` in Max,
a fake in tests), so this module has no import-time dependency on 3ds Max.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from ..core.model import ColorSpace, MaterialRecord, Renderer, SlotRole, TextureRef
from . import props as P


@dataclass
class ReadLog:
    """Which candidate property names actually resolved — exposes a wrong props table."""
    used: dict = field(default_factory=dict)       # (class, canonical) -> property name
    missing: set = field(default_factory=set)      # (class, canonical) never resolved

    def as_dict(self) -> dict:
        return {"used": {f"{c}.{k}": v for (c, k), v in sorted(self.used.items())},
                "missing": sorted(f"{c}.{k}" for c, k in self.missing)}


class SceneReader:
    def __init__(self, rt: Any):
        self.rt = rt
        self.log = ReadLog()
        self._handles_ok = True
        self._keepalive: list = []     # id() fallback: keep visited proxies alive so ids stay unique
        self._truncated = 0

    def key(self, obj):
        """Stable identity of a Max object for de-duplication.

        pymxs hands out a FRESH Python wrapper on every access, so ``id()`` of a freed
        wrapper is reused by the next one and would make the walker skip unrelated
        materials. ``getHandleByAnim`` returns the animatable's handle, which is stable
        for the session (docs/VERIFY.md row 15). Falls back to ``id()`` — with the
        wrapper kept alive — only when the call is unavailable, and logs that once.
        """
        if self._handles_ok:
            try:
                return ("h", int(self.rt.getHandleByAnim(obj)))
            except Exception as exc:
                self._handles_ok = False
                logging.getLogger("material_inspector").warning(
                    "getHandleByAnim unavailable (%r): de-duplicating by id(), wrappers kept alive", exc)
        self._keepalive.append(obj)
        return ("id", id(obj))

    # ------------------------------------------------------------ primitives
    def cls(self, obj) -> str:
        return str(self.rt.classOf(obj))

    def _get(self, obj, cls: str, canonical: str, names: list[str]):
        for n in names:
            try:
                if self.rt.isProperty(obj, n):
                    self.log.used[(cls, canonical)] = n
                    self.log.missing.discard((cls, canonical))
                    return self.rt.getProperty(obj, n), n
            except Exception:
                continue
        if (cls, canonical) not in self.log.used:
            self.log.missing.add((cls, canonical))
        return None, None

    @staticmethod
    def _color(v) -> Optional[tuple]:
        if v is None:
            return None
        try:
            return (float(v.r) / 255.0, float(v.g) / 255.0, float(v.b) / 255.0)
        except AttributeError:
            return None

    # ------------------------------------------------------------ materials
    def materials(self) -> list[MaterialRecord]:
        out: list[MaterialRecord] = []
        seen: set = set()
        # explicit stack, depth-first pre-order: nesting depth is not bounded by Python's
        # recursion limit (a RecursionError used to drop deep materials silently)
        stack = [(m, "") for m in reversed(list(self.rt.sceneMaterials))]
        while stack:
            m, path = stack.pop()
            if m is None:
                continue
            k = self.key(m)
            if k in seen:
                continue
            seen.add(k)
            cls = self.cls(m)
            name = str(getattr(m, "name", "") or cls)
            here = f"{path}/{name}" if path else name
            if cls in P.MATERIAL_CLASSES:
                out.append(self.read_material(m, cls, here))
            # descend into Multi/Sub, Blend, VRayBlendMtl, Corona layered, etc.
            try:
                n = int(self.rt.getNumSubMtls(m))
            except Exception:
                n = 0
            subs = []
            for i in range(1, n + 1):
                try:
                    subs.append((self.rt.getSubMtl(m, i), here))
                except Exception:
                    continue
            stack.extend(reversed(subs))
        return out

    def read_material(self, m, cls: str, scene_path: str) -> MaterialRecord:
        rec = MaterialRecord(name=str(getattr(m, "name", cls)), renderer=P.MATERIAL_CLASSES[cls],
                             material_class=cls, scene_path=scene_path, handle=m)
        table = P.PARAMS.get(cls, {})
        raw = {k: self._get(m, cls, k, names)[0] for k, names in table.items()}
        p = rec.params
        if raw.get("base_color") is not None:
            p["base_color"] = self._color(raw["base_color"])
        for k in ("roughness", "glossiness", "ior", "refraction_ior", "absorption_distance"):
            if raw.get(k) is not None:
                p[k] = float(raw[k])
        if cls == "VRayMtl":
            if raw.get("use_roughness") is not None:
                p["use_roughness"] = bool(raw["use_roughness"])
                if p["use_roughness"] and "glossiness" in p:
                    p["roughness"] = p.pop("glossiness")   # V-Ray reuses the same spinner
            if raw.get("brdf") is not None:
                p["brdf"] = P.VRAY_BRDF.get(int(raw["brdf"]), str(raw["brdf"]))
            if raw.get("metalness") is not None:
                p["metalness"] = float(raw["metalness"])
            rc = self._color(raw.get("refraction_color"))
            if rc is not None:
                p["refraction_amount"] = max(rc)
            if raw.get("absorption_color") is not None:
                p["absorption_color"] = self._color(raw["absorption_color"])
        else:
            if raw.get("metalness_mode") is not None:
                p["metalness"] = 1.0 if int(raw["metalness_mode"]) == 1 else 0.0
            elif raw.get("metalness") is not None and not isinstance(raw["metalness"], bool):
                try:   # OpenPBR has no mode enum: the value itself is the metalness
                    p["metalness"] = float(raw["metalness"])
                except (TypeError, ValueError):
                    pass
            if raw.get("refraction_amount") is not None:
                p["refraction_amount"] = float(raw["refraction_amount"])
            if raw.get("absorption_color") is not None:
                p["absorption_color"] = self._color(raw["absorption_color"])
        if raw.get("thin_walled") is not None:
            p["thin_walled"] = bool(raw["thin_walled"])
        if raw.get("complex_ior") is not None:
            p["complex_ior"] = bool(raw["complex_ior"])
        p["is_legacy"] = cls in P.LEGACY_CLASSES

        seen: set = set()          # texmaps already read for this material (instances, DAGs)
        self._truncated = 0
        for role, names in P.SLOTS.get(cls, {}).items():
            tex, used = self._get(m, cls, f"slot:{role.value}", names)
            if tex is None:
                continue
            if used in P.NORMAL_INPUT_SLOTS.get(cls, ()):
                rec.textures += self.read_texmap(tex, SlotRole.NORMAL, via_normal=True, seen=seen)
                continue
            eff_role = role
            if cls == "VRayMtl" and role == SlotRole.GLOSSINESS and p.get("use_roughness"):
                eff_role = SlotRole.ROUGHNESS
            rec.textures += self.read_texmap(tex, eff_role, seen=seen)
        if self._truncated:
            p["texmap_truncated"] = P.MAX_TEXMAP_DEPTH   # R007
        return rec

    # ------------------------------------------------------------ texmaps
    def read_texmap(self, tex, role: SlotRole, depth: int = 0, via_normal: Optional[bool] = None,
                    flip: Optional[bool] = None, seen: Optional[set] = None) -> list[TextureRef]:
        """Bitmaps feeding one slot. ``seen`` (per material) holds (handle, role, via_normal,
        flip): an instanced texmap is read once, so shared sub-graphs cost O(nodes), not k^depth."""
        if tex is None:
            return []
        if depth > P.MAX_TEXMAP_DEPTH:
            self._truncated += 1
            return []
        seen = set() if seen is None else seen
        k = (self.key(tex), role, via_normal, flip)
        if k in seen:
            return []
        seen.add(k)
        cls = self.cls(tex)
        if cls in P.BITMAP_CLASSES:
            spec = P.BITMAP_CLASSES[cls]
            path, _ = self._get(tex, cls, "path", spec["path"])
            cs_raw, _ = self._get(tex, cls, "color_space", spec["color_space"])
            cs = self.color_space(cls, cs_raw)
            if cs == ColorSpace.UNKNOWN and cls == "Bitmaptexture":
                cs = self._bitmap_gamma_space(tex)
            path = str(path) if path else None
            exists = None
            if path:
                try:
                    exists = bool(self.rt.doesFileExist(path))
                except Exception:
                    exists = os.path.isfile(path)
            if role in (SlotRole.BUMP, SlotRole.NORMAL) and via_normal is None:
                via_normal = False
            return [TextureRef(role, path, cs, cls,
                               str(getattr(tex, "name", "")), via_normal, flip, exists, tex)]
        if cls in P.NORMAL_CLASSES:
            spec = P.NORMAL_CLASSES[cls]
            inp, _ = self._get(tex, cls, "input", spec["input"])
            fl, _ = self._get(tex, cls, "flip_green", spec["flip_green"])
            return self.read_texmap(inp, SlotRole.NORMAL, depth + 1, True,
                                    None if fl is None else bool(fl), seen)
        # any other texmap (Output, ColorCorrection, Mix, VRayColor2Bump, ...): descend
        out: list[TextureRef] = []
        try:
            n = int(self.rt.getNumSubTexmaps(tex))
        except Exception:
            n = 0
        for i in range(1, n + 1):
            try:
                out += self.read_texmap(self.rt.getSubTexmap(tex, i), role, depth + 1, via_normal, flip, seen)
            except Exception:
                continue
        return out

    def _bitmap_gamma_space(self, tex) -> ColorSpace:
        """Read the gamma the bitmap was opened with (openBitMap(path, gamma=...))."""
        g = P.BITMAP_GAMMA
        try:
            bm = self.rt.getProperty(tex, g["bitmap_prop"]) if self.rt.isProperty(tex, g["bitmap_prop"]) else None
            if bm is None or not self.rt.isProperty(bm, g["gamma_prop"]):
                return ColorSpace.UNKNOWN
            gamma = float(self.rt.getProperty(bm, g["gamma_prop"]))
        except Exception:
            return ColorSpace.UNKNOWN
        self.log.used[("Bitmaptexture", "color_space")] = "bitmap.gamma"
        self.log.missing.discard(("Bitmaptexture", "color_space"))
        if gamma <= g["linear_max"]:
            return ColorSpace.LINEAR
        if gamma >= g["srgb_min"]:
            return ColorSpace.SRGB
        return ColorSpace.UNKNOWN

    @staticmethod
    def color_space(cls: str, raw) -> ColorSpace:
        if raw is None:
            return ColorSpace.UNKNOWN
        vals = P.COLOR_SPACE_VALUES.get(cls, {})
        key = raw.lower().strip() if isinstance(raw, str) else raw
        def match(cands):
            for c in cands:
                if isinstance(c, str) and isinstance(key, str) and key == c:
                    return True
                if not isinstance(c, str) and not isinstance(key, str):
                    try:
                        if abs(float(key) - float(c)) < 1e-6:
                            return True
                    except (TypeError, ValueError):
                        pass
            return False
        if match(vals.get("linear", [])):
            return ColorSpace.LINEAR
        if match(vals.get("srgb", [])):
            return ColorSpace.SRGB
        if isinstance(key, str) and ("raw" in key or "linear" in key):
            return ColorSpace.LINEAR
        if isinstance(key, str) and "srgb" in key:
            return ColorSpace.SRGB
        return ColorSpace.UNKNOWN
