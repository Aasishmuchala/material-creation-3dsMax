"""Apply FixActions to live 3ds Max nodes.

Every fix runs inside one undo record. A fix that can't be applied (unknown
property, unsupported class) returns a reason instead of guessing, and the UI
shows "fix manually".
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Optional

from ..core.model import Finding, MaterialRecord, TextureRef
from ..core.physics import matphys
from . import props as P


@dataclass
class FixResult:
    ok: bool
    message: str


class FixApplier:
    def __init__(self, rt: Any, undo_ctx=None):
        self.rt = rt
        self._undo = undo_ctx          # pymxs.undo in Max; None in tests

    # ------------------------------------------------------------ helpers
    def _set(self, obj, names: list[str], value) -> Optional[str]:
        for n in names:
            try:
                if self.rt.isProperty(obj, n):
                    self.rt.setProperty(obj, n, value)
                    return n
            except Exception:
                continue
        return None

    def _rgb(self, c):
        return self.rt.Color(c[0] * 255.0, c[1] * 255.0, c[2] * 255.0)

    # ------------------------------------------------------------ entry point
    def apply(self, finding: Finding, mat: MaterialRecord) -> FixResult:
        if finding.fix is None:
            return FixResult(False, "No automatic fix for this finding")
        if self._undo is not None:
            with self._undo(True, f"Material Inspector: {finding.rule_id}"):
                return self._apply(finding, mat)
        return self._apply(finding, mat)

    def _apply(self, f: Finding, mat: MaterialRecord) -> FixResult:
        fx = f.fix
        handler = getattr(self, f"_fix_{fx.kind}", None)
        if handler is None:
            return FixResult(False, f"Fix '{fx.kind}' not implemented yet — fix manually")
        try:
            return handler(fx, mat, f)
        except Exception as exc:
            return FixResult(False, f"Fix failed: {exc!r}")

    def _texture(self, mat: MaterialRecord, f: Finding) -> Optional[TextureRef]:
        for t in mat.textures:
            label = t.path.split("\\")[-1].split("/")[-1] if t.path else t.node_name
            if f.texture in (label, t.node_name, t.path):
                return t
        return None

    # ------------------------------------------------------------ fixes
    def _fix_set_color_space(self, fx, mat, f) -> FixResult:
        t = self._texture(mat, f)
        if t is None or t.handle is None:
            return FixResult(False, "Texture node not found")
        values = P.COLOR_SPACE_VALUES.get(t.node_class, {}).get(fx.value, [])
        names = P.BITMAP_CLASSES.get(t.node_class, {}).get("color_space", [])
        for v in values:
            used = self._set(t.handle, names, v)
            if used:
                return FixResult(True, f"{t.node_class}.{used} = {v!r}")
        if t.node_class == "Bitmaptexture" and t.path and hasattr(self.rt, "openBitMap"):
            try:
                return self._reopen_bitmap(t, linear=fx.value == "linear")
            except Exception as exc:
                return FixResult(False, f"openBitMap failed: {exc!r}")
        return FixResult(False, f"Don't know how to set colour space on {t.node_class} — fix manually")

    def _bitmap_gamma(self, tex):
        """What a Bitmaptexture's bitmap decodes as: its colorSpace name under OCIO,
        else its gamma (float); None when unreadable."""
        try:
            bm = self.rt.getProperty(tex, P.BITMAP_GAMMA["bitmap_prop"])
            if bm is None:
                return None
            if P.ocio_data_space(self.rt):
                return str(self.rt.getProperty(bm, P.BITMAP_COLORSPACE_PROP))
            return float(self.rt.getProperty(bm, P.BITMAP_GAMMA["gamma_prop"]))
        except Exception:
            return None

    def _decodes_linear(self, state) -> Optional[bool]:
        if state is None:
            return None
        if isinstance(state, str):
            kind = P.ocio_space_kind(state)
            return None if kind is None else kind == "linear"
        G = P.BITMAP_GAMMA
        if state <= G["linear_max"]:
            return True
        if state >= G["srgb_min"]:
            return False
        return None

    def _same_file_users(self, t: TextureRef) -> list:
        """Other Bitmaptexture nodes loading the same file, with their current gamma."""
        try:
            nodes = list(self.rt.getClassInstances(self.rt.Bitmaptexture))
        except Exception:
            return []
        def norm(p):                     # Windows paths, compared the same on any OS
            return str(p).replace("\\", "/").lower()
        key = norm(t.path)
        out = []
        for n in nodes:
            try:
                same = norm(self.rt.getProperty(n, "filename")) == key
            except Exception:
                continue
            if same and n != t.handle:
                out.append((n, self._bitmap_gamma(n)))
        return out

    def _reopen_bitmap(self, t: TextureRef, linear: bool) -> FixResult:
        """Reload the image at gamma 1.0 (linear) or the default input gamma (sRGB).

        3ds Max caches bitmaps per file: openBitMap(path, gamma=1.0) on a file that is
        already loaded returns the cached copy at its old gamma (verified on Max 2026.2).
        Detaching the bitmap and flushing the cache first makes the reload take. The
        cache keeps one copy per file, so other maps using the same file change too.
        """
        G = P.BITMAP_GAMMA
        others = self._same_file_users(t)
        self.rt.setProperty(t.handle, G["bitmap_prop"], None)
        if hasattr(self.rt, "freeSceneBitmaps"):
            self.rt.freeSceneBitmaps()
        if hasattr(self.rt, "gc"):
            self.rt.gc(light=True)
        data_cs = P.ocio_data_space(self.rt)
        if linear and data_cs:       # OCIO ignores gamma: open in the data colour space
            bm = self.rt.openBitMap(t.path, colorSpace=data_cs)
        elif linear:
            bm = self.rt.openBitMap(t.path, gamma=1.0)
        else:                        # input rules / default gamma decode sRGB
            bm = self.rt.openBitMap(t.path)
        self.rt.setProperty(t.handle, G["bitmap_prop"], bm)
        got = self._bitmap_gamma(t.handle)
        if self._decodes_linear(got) is not linear:
            shown = "unknown" if got is None else (got if isinstance(got, str) else f"gamma {got:.2f}")
            return FixResult(False, f"3ds Max kept this file as {shown}: another map outside the scene "
                                    "(e.g. a Material Editor slot) still holds it — fix manually")
        if data_cs:
            msg = "Bitmap reloaded as " + (data_cs if linear else "sRGB (colour-space rules)")
        else:
            msg = "Bitmap reloaded with gamma " + ("1.0" if linear else "default")
        changed = [str(getattr(n, "name", n)) for n, before in others if self._bitmap_gamma(n) != before]
        if changed:
            msg += f"; {len(changed)} other map(s) using the same file changed too: {', '.join(changed)}"
        return FixResult(True, msg)

    def _fix_set_param(self, fx, mat, f) -> FixResult:
        names = P.PARAMS.get(mat.material_class, {}).get(fx.target)
        if not names:
            return FixResult(False, f"No property for '{fx.target}' on {mat.material_class}")
        value = fx.value
        if fx.target == "base_color":
            value = self._rgb(value)
        elif fx.target == "brdf" and mat.material_class == "VRayMtl":
            value = P.VRAY_BRDF_REV.get(str(value), 3)
        used = self._set(mat.handle, names, value)
        return FixResult(bool(used), f"{mat.material_class}.{used} set" if used else "Property not found")

    def _fix_toggle_use_roughness(self, fx, mat, f) -> FixResult:
        used = self._set(mat.handle, P.PARAMS["VRayMtl"]["use_roughness"], bool(fx.value))
        return FixResult(bool(used), "VRayMtl 'Use roughness' switched" if used else "Property not found")

    def _fix_set_absorption(self, fx, mat, f) -> FixResult:
        color = fx.value["color"]; dist_mm = fx.value["distance_mm"]
        table = P.PARAMS.get(mat.material_class, {})
        mm_per_unit = self._mm_per_scene_unit()
        if "absorption_distance" in table:
            used = self._set(mat.handle, table.get("absorption_color", []), self._rgb(color))
            if not used:
                return FixResult(False, "Absorption property not found")
            self._set(mat.handle, table["absorption_distance"], dist_mm / mm_per_unit)
            return FixResult(True, "Absorption colour and distance set")
        # V-Ray fog: one conversion shared with MatForge (matphys). Colour is reached at
        # depth 1/multiplier (scene units). APPROXIMATE — see docs/VERIFY.md.
        sigma = tuple(-math.log(min(max(c, 1e-6), 1.0)) / dist_mm for c in color[:3])
        fog, mult = matphys.to_vray_fog(sigma, dist_mm, mm_per_unit)
        used = self._set(mat.handle, table.get("absorption_color", []), self._rgb(fog))
        if not used:
            return FixResult(False, "Absorption property not found")
        self._set(mat.handle, table.get("absorption_mult", []), mult)
        return FixResult(True, "Fog colour + multiplier set (approximate until Phase 2 mapping)")

    def _fix_insert_normal_node(self, fx, mat, f) -> FixResult:
        t = self._texture(mat, f)
        if t is None or t.handle is None:
            return FixResult(False, "Texture node not found")
        node_cls = {"vray": "VRayNormalMap", "corona": "CoronaNormal"}.get(mat.renderer.value, "Normal_Bump")
        ctor = getattr(self.rt, node_cls, None)
        if ctor is None:
            return FixResult(False, f"{node_cls} not available in this session")
        node = ctor()
        if not self._set(node, P.NORMAL_CLASSES[node_cls]["input"], t.handle):
            return FixResult(False, f"Could not connect bitmap to {node_cls}")
        slot_names = P.SLOTS.get(mat.material_class, {}).get(t.role, [])
        if not self._set(mat.handle, slot_names, node):
            return FixResult(False, "Could not plug the normal node into the slot")
        return FixResult(True, f"Inserted {node_cls}")

    def _fix_invert_map(self, fx, mat, f) -> FixResult:
        """Wrap the bitmap in a 3ds Max Output map with Invert on (roughness = 1 − gloss).

        Only handles a bitmap plugged directly into the slot; nested setups are left
        for the artist because rewiring them blindly could break a deliberate graph.
        """
        t = self._texture(mat, f)
        if t is None or t.handle is None:
            return FixResult(False, "Texture node not found")
        ctor = getattr(self.rt, "Output", None)
        if ctor is None:
            return FixResult(False, "Output map not available")
        slot_names = P.SLOTS.get(mat.material_class, {}).get(t.role, [])
        slot_names += P.SLOTS.get(mat.material_class, {}).get(
            {"roughness": P.SlotRole.GLOSSINESS, "glossiness": P.SlotRole.ROUGHNESS}.get(t.role.value, t.role), [])
        slot = next((n for n in slot_names if self.rt.isProperty(mat.handle, n)
                     and self.rt.getProperty(mat.handle, n) is t.handle), None)
        if slot is None:
            return FixResult(False, "Bitmap is not plugged directly into the slot — invert it manually")
        out = ctor()
        if not self._set(out, P.OUTPUT_MAP["input"], t.handle):
            return FixResult(False, "Could not connect bitmap to the Output map")
        try:
            settings = self.rt.getProperty(out, P.OUTPUT_MAP["settings"][0])
            if not self._set(settings, P.OUTPUT_MAP["invert"], True):
                return FixResult(False, "Output map has no invert setting")
        except Exception as exc:
            return FixResult(False, f"Could not enable invert: {exc!r}")
        self.rt.setProperty(mat.handle, slot, out)
        return FixResult(True, "Inserted Output map with Invert")

    def _mm_per_scene_unit(self) -> float:
        try:
            u = str(self.rt.units.SystemType).lower()
            scale = float(self.rt.units.SystemScale)
        except Exception:
            return 1.0
        per = {"millimeters": 1.0, "centimeters": 10.0, "meters": 1000.0, "kilometers": 1e6,
               "inches": 25.4, "feet": 304.8, "miles": 1609344.0}
        return per.get(u.replace("#", ""), 1.0) * scale
