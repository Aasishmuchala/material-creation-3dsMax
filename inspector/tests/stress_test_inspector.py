"""STRESS SUITE B — Material Inspector (rules, pixel checks, scene walker, report, CLI, config).

Every defect the suite found is pinned by a regression test tagged STRESS-B<n> in its
docstring (see .router/stress/B_inspector.md; fixed in wave FX-B); everything that held
is a passing property test. Default run is small and fast; ``STRESS_FULL=1`` runs the heavy sweeps
(20k fuzz records, >= 300-map texture corpus, 50 broken maps, 8192² image, 3,000-file
CLI folder). ``STRESS_OUT=<dir>`` writes the sweep tables there as JSON.

Run: ``cd inspector && STRESS_FULL=1 python3 -m pytest -q tests/stress_test_inspector.py -s``
A bare ``python3 -m pytest -q`` collects it only when pytest.ini lists ``stress_test_*.py`` in
``python_files``; otherwise pass the path explicitly.
"""
from __future__ import annotations

import collections
import contextlib
import dataclasses
import io
import json
import math
import os
import subprocess
import sys
import textwrap
import time

import numpy as np
import pytest
from PIL import Image

from material_inspector import cli
from material_inspector.core import map_checks as mc
from material_inspector.core.config import load_options
from material_inspector.core.inspector import InspectorOptions, inspect, pixel_findings
from material_inspector.core.model import (ColorSpace, Finding, MaterialRecord, Renderer, Severity,
                                           SlotRole, TextureRef)
from material_inspector.core.report import to_html, to_json
from material_inspector.core.rules import DEFAULT_CONFIG, RuleConfig, all_rules, inspect_material
from material_inspector.max_adapter import props as P
from material_inspector.max_adapter.fixes import FixApplier
from material_inspector.max_adapter.scene import SceneReader
from tests.fake_pymxs import FakeMaxRuntime, _defaults
from tests.fakert import Color, FakeRT, Node

FULL = bool(os.environ.get("STRESS_FULL"))
OUT = os.environ.get("STRESS_OUT")
INSPECTOR_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _emit(name: str, data) -> None:
    """Write a sweep table to $STRESS_OUT/<name>.json (and print it under -s)."""
    print(f"\n[stress-B] {name}: {json.dumps(data, default=str)[:2000]}")
    if OUT:
        os.makedirs(OUT, exist_ok=True)
        with open(os.path.join(OUT, name + ".json"), "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, default=str)


def _strict_json(s: str):
    def bad(c):
        raise ValueError(f"non-standard JSON constant {c}")
    return json.loads(s, parse_constant=bad)


def _vray(name="m", **kw):
    base = dict(diffuse=Color(128, 128, 128), reflection_glossiness=0.6, brdf_useRoughness=True,
                brdf_type=3, reflection_metalness=0.0, reflection_ior=1.5, refraction=Color(0, 0, 0))
    base.update(kw)
    return Node("VRayMtl", name, **base)


def _save_u8(path, a):
    Image.fromarray((np.clip(a, 0, 1) * 255 + 0.5).astype(np.uint8)).save(path)


# =====================================================================================
# 1. Rule fuzz
# =====================================================================================
_VALID = {
    "base_color": lambda r: tuple(float(x) for x in r.random(3)),
    "roughness": lambda r: float(r.random()), "glossiness": lambda r: float(r.random()),
    "use_roughness": lambda r: bool(r.integers(2)),
    "brdf": lambda r: ["ggx", "blinn", "phong", "ward"][r.integers(4)],
    "metalness": lambda r: float(r.choice([0.0, 1.0, r.random()])),
    "ior": lambda r: float(1 + 2 * r.random()), "refraction_amount": lambda r: float(r.random()),
    "refraction_ior": lambda r: float(1 + r.random()),
    "absorption_color": lambda r: tuple(float(x) for x in r.random(3)),
    "absorption_distance": lambda r: float(100 * r.random()),
    "thin_walled": lambda r: bool(r.integers(2)), "complex_ior": lambda r: bool(r.integers(2)),
    "is_legacy": lambda r: bool(r.integers(2)),
}
_COLOR_KEYS = {"base_color", "absorption_color"}
_BOOL_KEYS = {"use_roughness", "thin_walled", "complex_ior", "is_legacy"}
_NAMES = ["Gold trim", "Steel <b>", "snow", "Alu_Panel", "", "x" * 10000, "Copper\u00e9 \u6728",
          "plaster white", "<script>alert(1)</script>", "Oak floor"]
_PATHS = [None, "", "C:/t/wood_Gloss.png", "C:/t/wood_normal.png", "C:/t/x_rough.png",
          "/nope/\u6728 a.png", "C:\\t\\Oak_NormalGL.png"]


def _hfloat(r):
    return float(r.choice([r.random(), math.nan, math.inf, -math.inf, -r.random() * 10, 1e300, 0.0, 1.0]))


def _hostile(key, r, typed):
    if typed:   # adapter-possible: right shape, hostile values (NaN, ±inf, negative, huge)
        if r.random() < 0.15:
            return None
        if key in _COLOR_KEYS:
            return tuple(_hfloat(r) for _ in range(3))
        if key in _BOOL_KEYS:
            return bool(r.integers(2))
        if key == "brdf":
            return ["ggx", "blinn", "phong", "ward", "GGX", "7", ""][r.integers(7)]
        return _hfloat(r)
    c = r.integers(8)   # anything at all, incl. wrong types
    return [lambda: _VALID[key](r), lambda: None, lambda: _hfloat(r), lambda: -1e9,
            lambda: (math.nan,) * 3, lambda: "abc", lambda: [1, "x"], lambda: (0.5,)][c]()


def _rand_record(r, typed=True) -> MaterialRecord:
    ren = list(Renderer)[r.integers(3)]
    cls = {"vray": "VRayMtl", "corona": "CoronaPhysicalMtl", "openpbr": "OpenPBRMaterial"}[ren.value]
    params = {k: _hostile(k, r, typed) for k in _VALID if r.random() < 0.7}
    texs = []
    for _ in range(int(r.integers(0, 5))):
        texs.append(TextureRef(
            list(SlotRole)[r.integers(len(SlotRole))], _PATHS[r.integers(len(_PATHS))],
            list(ColorSpace)[r.integers(3)],
            ["Bitmaptexture", "VRayBitmap", "CoronaBitmap", ""][r.integers(4)], ["", "bm"][r.integers(2)],
            [None, True, False][r.integers(3)], [None, True, False][r.integers(3)],
            [None, True, False][r.integers(3)]))
    return MaterialRecord(_NAMES[r.integers(len(_NAMES))], ren, cls, params, texs)


def _attach_fake_nodes(m: MaterialRecord, r) -> None:
    m.handle = Node(m.material_class, m.name, **_defaults(m.material_class))
    for t in m.textures:
        cls = t.node_class if t.node_class in P.BITMAP_CLASSES else "Bitmaptexture"
        t.node_class = cls
        t.handle = Node(cls, t.node_name or "bm", **_defaults(cls))
        slot = P.SLOTS.get(m.material_class, {}).get(t.role)
        if slot and r.random() < 0.7:
            m.handle._props[slot[0]] = t.handle


def test_rule_fuzz_never_raises_json_clean_and_one_undo_per_fix():
    n = 20000 if FULL else 2000
    r = np.random.default_rng(20261104)
    direct_raises = collections.Counter()      # adapter-possible values: must be 0
    wrongtype_raises = collections.Counter()   # wrong types: caught as R999 by inspect_material
    fix_outcomes = collections.Counter()
    undos: list = []

    @contextlib.contextmanager
    def undo(on, label):
        undos.append(label)
        yield

    rt = FakeMaxRuntime()
    t0 = time.time()
    for i in range(n):
        typed = i % 2 == 0
        m = _rand_record(r, typed)
        for rid, fn in all_rules():
            try:
                out = fn(m, DEFAULT_CONFIG)
            except Exception:
                (direct_raises if typed else wrongtype_raises)[rid] += 1
                continue
            assert isinstance(out, list) and all(isinstance(f, Finding) for f in out), rid
        found = inspect_material(m)                     # must never raise
        assert all(isinstance(f, Finding) and isinstance(f.severity, Severity) for f in found)
        if found:
            doc = _strict_json(to_json(found))          # serialisable, no NaN/Infinity tokens
            assert len(doc["findings"]) == len(found)
        _attach_fake_nodes(m, r)
        for f in found:
            if f.fix is None:
                continue
            before = len(undos)
            res = FixApplier(rt, undo).apply(f, m)      # must never raise
            assert len(undos) - before == 1, f
            fix_outcomes[f"{f.fix.kind}:{'ok' if res.ok else 'refused'}"] += 1
    _emit("B1_rule_fuzz", {"records": n, "seconds": round(time.time() - t0, 2),
                           "direct_raises_adapter_domain": dict(direct_raises),
                           "direct_raises_wrong_type(caught as R999)": dict(wrongtype_raises),
                           "fix_outcomes": dict(fix_outcomes)})
    assert not direct_raises, direct_raises


def test_disabling_R010_keeps_R011():
    """STRESS-B9: R011 is its own rule."""
    m = MaterialRecord("Dark metal", Renderer.VRAY, "VRayMtl", {"base_color": (0.05,) * 3, "metalness": 1.0})
    assert "R011" in {f.rule_id for f in inspect_material(m, disabled=["R010"])}


def test_disabling_R015_keeps_R016():
    """STRESS-B9: R016 is its own rule."""
    m = MaterialRecord("Mirror", Renderer.VRAY, "VRayMtl",
                       {"glossiness": 1.0, "use_roughness": False, "brdf": "ggx"})
    assert "R016" in {f.rule_id for f in inspect_material(m)}            # holds with nothing disabled
    m.params["brdf"] = "phong"
    assert "R016" in {f.rule_id for f in inspect_material(m, disabled=["R015"])}


@pytest.mark.parametrize("key,val", [("ior", math.nan), ("ior", math.inf), ("refraction_ior", -math.inf),
                                     ("metalness", math.nan), ("glossiness", math.nan),
                                     ("refraction_amount", math.nan)])
def test_nan_param_is_an_unreadable_value_not_a_range_finding(key, val):
    """STRESS-B13 (orchestrator: non-finite -> R008 info, never a silent pass or a fake range
    finding). A NaN IOR used to read as an 'unusual' R013 warning."""
    m = MaterialRecord("x", Renderer.VRAY, "VRayMtl", {key: val})
    got = inspect_material(m)
    r008 = [f for f in got if f.rule_id == "R008"]
    assert len(r008) == 1 and r008[0].severity == Severity.INFO and key.replace("_", " ") in r008[0].message
    assert not [f for f in got if f.rule_id in ("R012", "R013", "R014", "R016")], got


def test_nan_base_colour_is_reported():
    """STRESS-B13: a NaN base colour used to pass R010 silently."""
    m = MaterialRecord("x", Renderer.VRAY, "VRayMtl", {"base_color": (float("nan"),) * 3})
    ids = [f.rule_id for f in inspect_material(m)]
    assert ids == ["R008"], ids
    m.params["metalness"] = 1.0       # metal path (R011 / R018) skips it as well
    assert [f.rule_id for f in inspect_material(m)] == ["R008"]


def test_r011_fix_is_in_gamut():
    """STRESS-B13: the R011 fix is clamped to 0–1."""
    m = MaterialRecord("m", Renderer.VRAY, "VRayMtl", {"base_color": (-0.2, 0.3, 0.3), "metalness": 1.0})
    f = [f for f in inspect_material(m) if f.rule_id == "R011"][0]
    assert all(0.0 <= c <= 1.0 for c in f.fix.value)


# =====================================================================================
# 2. Texture corpus: false positives on correct maps, misses on broken maps
# =====================================================================================
def _torus(n):
    return np.meshgrid(np.arange(n) / n, np.arange(n) / n, indexing="xy")


def _fbm(n, rng, beta=2.0, fmin=1.0, aniso=(1.0, 1.0)):
    """Periodic (tileable) 1/f^beta noise, zero-mean, unit std."""
    fx = np.fft.fftfreq(n)[None, :] * n * aniso[0]
    fy = np.fft.fftfreq(n)[:, None] * n * aniso[1]
    f = np.sqrt(fx ** 2 + fy ** 2)
    amp = np.where(f >= fmin, (f + 1e-9) ** (-beta / 2), 0.0)
    x = np.real(np.fft.ifft2((rng.standard_normal((n, n)) + 1j * rng.standard_normal((n, n))) * amp))
    return (x - x.mean()) / (x.std() + 1e-12)


def _torus_voronoi(n, pts):
    u, v = _torus(n)
    d1 = np.full((n, n), 9.0); d2 = np.full((n, n), 9.0); idx = np.zeros((n, n), np.int32)
    for i, (px, py) in enumerate(pts):
        dx = np.abs(u - px); dx = np.minimum(dx, 1 - dx)
        dy = np.abs(v - py); dy = np.minimum(dy, 1 - dy)
        d = np.sqrt(dx * dx + dy * dy)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d)); idx = np.where(closer, i, idx); d1 = np.where(closer, d, d1)
    return d1, d2, idx


def _ss(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


TONES = {   # sRGB albedo swatches inside the 50–240 luminance band a careful artist would use
    "wood": [(176, 128, 84), (122, 84, 56), (196, 170, 134), (150, 96, 62), (98, 70, 50)],
    "brick": [(150, 70, 52), (172, 98, 72), (120, 60, 48), (180, 140, 110)],
    "tile": [(210, 205, 196), (90, 110, 128), (60, 120, 110), (200, 180, 150)],
    "hex": [(190, 190, 185), (70, 90, 110), (160, 120, 90)],
    "marble": [(222, 220, 214), (200, 196, 188), (110, 100, 96)],
    "concrete": [(150, 148, 142), (128, 126, 120), (170, 166, 158)],
    "fabric": [(60, 70, 110), (190, 170, 140), (150, 50, 50), (90, 120, 80)],
    "metal": [(196, 198, 200), (230, 200, 120), (200, 140, 110)],
    "leather": [(140, 90, 55), (100, 60, 40), (160, 120, 80), (110, 50, 45)],
    "terrazzo": [(200, 196, 188), (150, 150, 146), (210, 190, 170)],
    "carpet": [(120, 80, 90), (80, 100, 130), (170, 150, 120)],
}
FAMILIES = list(TONES)


def _texture(fam, n, rng, tone):
    """Tileable (h, rgb, roughness, metal) for one material family; all in [0, 1]."""
    u, v = _torus(n)
    tone = np.array(tone, np.float64) / 255.0
    metal = np.zeros((n, n)); colour = None
    sub = lambda: np.random.default_rng(int(rng.integers(1 << 30)))
    if fam == "wood":
        rows = int(rng.choice([4, 6, 8])); row = np.floor(v * rows).astype(int)
        offs = rng.random(rows); seg = int(rng.choice([1, 2]))
        pos = (u * seg + offs[row]) % 1.0
        plank = row * 7 + (np.floor(u * seg + offs[row]).astype(int) % seg)
        ptone = 1 + 0.08 * sub().standard_normal(rows * 7 + 20)[plank]
        warp = _fbm(n, rng, beta=3.0) * 0.6
        grain = np.sin(2 * np.pi * (v * rows * int(rng.choice([6, 9, 12])) + warp))
        var = ptone * (1 + 0.06 * grain + 0.03 * _fbm(n, rng, beta=1.0, fmin=4))
        dv = np.minimum((v * rows) % 1, 1 - (v * rows) % 1)
        du = np.minimum(pos, 1 - pos) * rows / seg
        h = 0.6 * _ss(0.0, 0.02, np.minimum(dv, du)) + 0.05 * grain + 0.2
        rough = 0.45 + 0.08 * grain + 0.05 * _fbm(n, rng, beta=1.5, fmin=2)
    elif fam == "brick":
        rows = int(rng.choice([8, 12, 16])); cols = rows // 2
        rr = np.floor(v * rows); x = u * cols + 0.5 * (rr % 2)
        bx = x % 1; by = (v * rows) % 1; bid = (rr * 31 + np.floor(x) % cols).astype(int) % 997
        mortar = 1 - _ss(0.03, 0.07, np.minimum(np.minimum(bx, 1 - bx) * 2, np.minimum(by, 1 - by)))
        noise = _fbm(n, rng, beta=1.2, fmin=8)
        var = (1 + 0.10 * sub().standard_normal(1000)[bid]) * (1 + 0.07 * noise)
        colour = np.where(mortar[..., None] > 0.5, np.array([0.62, 0.60, 0.56]), np.nan)
        h = 0.7 * (1 - mortar) + 0.04 * noise + 0.15
        rough = 0.78 + 0.08 * noise + 0.1 * mortar
    elif fam in ("tile", "hex"):
        if fam == "tile":
            k = int(rng.choice([4, 6, 8])); tx = (u * k) % 1; ty = (v * k) % 1
            e = np.minimum(np.minimum(tx, 1 - tx), np.minimum(ty, 1 - ty))
            tid = (np.floor(u * k) * 13 + np.floor(v * k)).astype(int)
            grout = 1 - _ss(0.015, 0.035, e)
        else:
            cols = int(rng.choice([4, 6])); rws = cols * 2
            pts = [((i + 0.5 * (j % 2)) / cols, (j + 0.5) / rws) for j in range(rws) for i in range(cols)]
            d1, d2, tid = _torus_voronoi(n, pts)
            grout = 1 - _ss(0.004, 0.010, d2 - d1)
        noise = _fbm(n, rng, beta=1.0, fmin=16)
        var = (1 + 0.03 * sub().standard_normal(5000)[tid % 5000]) * (1 + 0.02 * noise)
        colour = np.where(grout[..., None] > 0.5, np.array([0.55, 0.54, 0.52]), np.nan)
        h = 0.8 * (1 - grout) + 0.01 * noise + 0.1
        rough = 0.15 + 0.6 * grout + 0.03 * noise
    elif fam == "marble":
        turb = _fbm(n, rng, beta=2.6)
        f = int(rng.choice([2, 3, 4]))
        vein = np.abs(np.sin(2 * np.pi * (u * f + v + 0.35 * turb))) ** float(rng.choice([6, 10, 16]))
        cloud = _fbm(n, rng, beta=2.2, fmin=2)
        var = (1 - 0.55 * vein) * (1 + 0.03 * cloud)
        h = 0.5 + 0.03 * cloud - 0.05 * vein
        rough = 0.12 + 0.04 * vein + 0.02 * _fbm(n, rng, beta=1.0, fmin=8)
    elif fam == "concrete":
        mott = _fbm(n, rng, beta=2.2, fmin=3); fine = _fbm(n, rng, beta=0.8, fmin=32)
        pores = (_fbm(n, rng, beta=0.5, fmin=64) > 2.6).astype(float)
        var = (1 + 0.06 * mott + 0.04 * fine) * (1 - 0.3 * pores)
        h = 0.5 + 0.05 * mott + 0.05 * fine - 0.3 * pores
        rough = 0.82 + 0.05 * mott + 0.04 * fine
    elif fam == "fabric":
        k = int(rng.choice([32, 48, 64])) * max(1, n // 512)
        warp = 0.5 + 0.5 * np.sin(2 * np.pi * u * k); weft = 0.5 + 0.5 * np.sin(2 * np.pi * v * k)
        thread = np.where((np.floor(u * k) + np.floor(v * k)) % 2 > 0, warp, weft)
        fib = _fbm(n, rng, beta=1.0, fmin=32)
        var = (0.85 + 0.25 * thread) * (1 + 0.03 * fib)
        h = 0.3 + 0.5 * thread + 0.03 * fib
        rough = 0.85 + 0.06 * thread + 0.03 * fib
    elif fam == "metal":     # brushed: streaks along x, metalness all 1
        streak = _fbm(n, rng, beta=1.3, fmin=2, aniso=(0.05, 1.0))
        var = 1 + 0.03 * streak + 0.01 * _fbm(n, rng, beta=1.0, fmin=32)
        h = 0.5 + 0.03 * streak
        rough = 0.30 + 0.06 * streak
        metal = np.ones((n, n))
    elif fam == "leather":
        k = int(rng.choice([60, 100, 140]))
        d1, d2, _ = _torus_voronoi(n, rng.random((k, 2)))
        crease = _ss(0.0, 0.012, d2 - d1)
        pore = (_fbm(n, rng, beta=0.6, fmin=48) > 2.4).astype(float)
        mott = _fbm(n, rng, beta=2.0, fmin=2)
        var = (0.9 + 0.1 * crease) * (1 + 0.05 * mott) * (1 - 0.2 * pore)
        h = 0.4 + 0.4 * crease - 0.2 * pore
        rough = 0.55 + 0.1 * (1 - crease) + 0.05 * mott
    elif fam == "terrazzo":
        k = int(rng.choice([80, 140])); pts = rng.random((k, 2))
        d1, _, idx = _torus_voronoi(n, pts)
        chip = (d1 < (0.012 + 0.02 * sub().random(k))[idx]).astype(float)
        cols = sub().uniform(0.25, 0.85, (k, 3))
        base = _fbm(n, rng, beta=1.0, fmin=16)
        var = 1 + 0.03 * base
        colour = np.where(chip[..., None] > 0.5, cols[idx], np.nan)
        h = 0.5 + 0.02 * chip + 0.01 * base
        rough = 0.25 + 0.05 * base + 0.05 * chip
        if rng.random() < 0.5:   # brass divider strips -> bimodal metalness
            strip = ((u * 2) % 1 < 0.008) | ((v * 2) % 1 < 0.008)
            metal = strip.astype(float)
            colour = np.where(strip[..., None], np.array([0.85, 0.72, 0.45]), colour)
    elif fam == "carpet":
        k = int(rng.choice([4, 6, 8]))
        pat = ((np.abs((u * k) % 1 - 0.5) + np.abs((v * k) % 1 - 0.5)) < 0.25).astype(float)
        fib = _fbm(n, rng, beta=0.5, fmin=64)
        var = (1 + 0.35 * pat) * (1 + 0.08 * fib)
        h = 0.5 + 0.08 * fib
        rough = 0.9 + 0.04 * fib
    else:
        raise ValueError(fam)
    rgb = tone[None, None, :] * var[..., None]
    if colour is not None:
        msk = ~np.isnan(colour[..., 0])
        rgb[msk] = colour[msk] * var[msk][..., None]
    return np.clip(h, 0, 1), np.clip(rgb, 0, 1), np.clip(rough, 0, 1), metal


def _normal_from_height(h, strength=6.0, directx=False):
    """Tangent-space normal from a periodic height (Sobel with wrap). OpenGL = +Y up."""
    r = lambda a, dy, dx: np.roll(np.roll(a, dy, 0), dx, 1)
    gx = ((r(h, 0, -1) - r(h, 0, 1)) * 2 + (r(h, 1, -1) - r(h, 1, 1)) + (r(h, -1, -1) - r(h, -1, 1))) / 8
    gy = ((r(h, -1, 0) - r(h, 1, 0)) * 2 + (r(h, -1, 1) - r(h, 1, 1)) + (r(h, -1, -1) - r(h, 1, -1))) / 8
    s = strength * h.shape[0] / 64.0
    nx, ny = -gx * s, (-gy if directx else gy) * s
    ln = np.sqrt(nx * nx + ny * ny + 1)
    return np.stack([nx / ln, ny / ln, 1 / ln], -1) * 0.5 + 0.5


def _write_set(folder, fam, idx, n, rng, zero_metal=False, roll=0):
    tone = TONES[fam][int(rng.integers(len(TONES[fam])))]
    h, rgb, rough, metal = _texture(fam, n, rng, tone)
    if zero_metal:
        metal = np.zeros_like(metal)
    nrm = _normal_from_height(h)
    if roll:   # a cyclic shift keeps a tileable map tileable
        h, rgb, rough, metal, nrm = (np.roll(np.roll(a, roll, 0), roll, 1) for a in (h, rgb, rough, metal, nrm))
    stem = os.path.join(folder, f"{fam}{idx:03d}_{n}")
    _save_u8(stem + "_Color.png", rgb)
    _save_u8(stem + "_Roughness.png", rough)
    _save_u8(stem + "_Metalness.png", metal)
    _save_u8(stem + "_NormalGL.png", nrm)
    if idx % 2:
        Image.fromarray((h * 65535 + 0.5).astype(np.uint16)).save(stem + "_Height.png")
    else:
        _save_u8(stem + "_Height.png", h)
    return os.path.basename(stem)


#: Which role each M-check applies to (denominator of the false-positive rate).
_CHECK_ROLE = {"M001": "Color", "M002": "Color", "M010": "Color", "M003": "Roughness",
               "M004": "Metalness", "M006": "NormalGL", "M007": "NormalGL", "M008dx": "NormalGL",
               "M012": "Height", "M900": "any", "M005": "any", "M013": "rough/normal/height"}


def test_texture_corpus_false_positive_rates(tmp_path):
    per_family = 6 if FULL else 1
    sizes = (512, 1024, 2048) if FULL else (512,)
    rng = np.random.default_rng(42)
    t0 = time.time()
    idx = 0
    for fam in FAMILIES:
        for j in range(per_family):
            n = sizes[j % len(sizes)]
            roll = int(rng.integers(1, n)) if j % 2 else 0
            _write_set(str(tmp_path), fam, idx, n, rng, zero_metal=(fam != "metal" and j % 3 == 1), roll=roll)
            idx += 1
    gen_s = time.time() - t0
    mats = cli.materials_from_folder(str(tmp_path))
    nmaps = sum(len(m.textures) for m in mats)
    t0 = time.time()
    findings = inspect(mats, InspectorOptions(normal_convention={"other": "opengl"}))
    insp_s = time.time() - t0
    fires = collections.defaultdict(list)
    for f in findings:
        rid = f.rule_id
        if rid == "M008":
            if "OPENGL" in f.message:
                continue      # correct detection
            rid = "M008dx"    # wrong detection
        fires[rid].append({"material": f.material, "texture": f.texture, "msg": f.message})
    nsets = len(mats)
    denom = {"Color": nsets, "Roughness": nsets, "Metalness": nsets, "NormalGL": nsets, "Height": nsets,
             "any": nmaps, "rough/normal/height": 3 * nsets}
    table = {}
    for rid, rows in sorted(fires.items()):
        d = denom[_CHECK_ROLE.get(rid, "any")]
        fams = collections.Counter(r["material"].rstrip("0123456789_").rstrip("0123456789") for r in rows)
        table[rid] = {"fires": len(rows), "of": d, "rate": round(len(rows) / d, 3),
                      "by_family": dict(collections.Counter(
                          "".join(ch for ch in r["material"].split("_")[0] if ch.isalpha()) for r in rows)),
                      "top": sorted(rows, key=lambda r: -float(_score(r["msg"])))[:6]}
    _emit("B2_fp_table", {"sets": nsets, "maps": nmaps, "gen_s": round(gen_s, 1),
                          "inspect_s": round(insp_s, 1), "rules": table})
    assert nmaps == 5 * nsets
    if FULL:
        assert nmaps >= 300
    # What held: none of these fire on correct maps.
    for rid in ("M001", "M002", "M003", "M004", "M007", "M008dx", "M010", "M012", "M900"):
        assert rid not in table, (rid, table.get(rid))


def _score(msg: str) -> float:
    import re
    m = re.search(r"score ([0-9.e+-]+)", msg)
    try:
        return float(m.group(1)) if m else 0.0
    except ValueError:
        return 0.0


def test_m005_seam_score_is_shift_invariant_for_tiles_without_line_features():
    """Held: plain tileable noise and a grout grid score the same at every cyclic offset."""
    rng = np.random.default_rng(5)
    noise = (_fbm(512, rng, beta=1.5, fmin=2)[..., None] * 0.1 + 0.5) * np.ones(3)
    for s in (0, 7, 100, 256):
        assert mc.seam_score(np.roll(np.roll(noise, s, 0), s, 1)) < 4


def test_m005_does_not_fire_on_tileable_planks_at_any_offset():
    """STRESS-B1: plank edges / grout on the border recur inside the tile -> no seam."""
    rng = np.random.default_rng(3)
    h, rgb, _, _ = _texture("wood", 512, rng, (150, 110, 80))
    a = (np.round(rgb * 255) / 255).astype(np.float32)
    nrm = _normal_from_height(h).astype(np.float32)
    scores = [mc.seam_score(np.roll(np.roll(x, s, 0), s, 1)) for x in (a, nrm) for s in (0, 64, 128, 7)]
    assert max(scores) <= 4.0, scores


def test_m005_quiet_on_seamless_2048_map(tmp_path):
    """STRESS-B1: the seam test runs at native resolution (no downsampling across the wrap)."""
    rng = np.random.default_rng(0)
    a = np.clip(_fbm(2048, rng, beta=1.0, fmin=2) * 0.08 + 0.5, 0, 1)
    p = str(tmp_path / "seamless_Roughness.png"); _save_u8(p, a)
    assert mc.seam_score(mc.load_map(p, 4096)) < 4          # native pixels: seamless
    ids = {f.rule_id for f in pixel_findings(_rec_for(SlotRole.ROUGHNESS, p), InspectorOptions())}
    assert "M005" not in ids


def test_m005_seamless_corpus_2048_zero_fires_and_shift_invariant(tmp_path):
    """STRESS-B1 acceptance: 0/10 seamless 2048² maps fire; rolling moves the score by ≤ 1."""
    n_maps = 10 if FULL else 3
    fires, spread = 0, []
    for i in range(n_maps):
        rng = np.random.default_rng(100 + i)
        a = np.clip(_fbm(2048, rng, beta=float(rng.choice([1.0, 1.5, 2.0])), fmin=2) * 0.08 + 0.5, 0, 1)
        p = str(tmp_path / f"s{i}_Roughness.png"); _save_u8(p, a)
        fires += "M005" in {f.rule_id for f in pixel_findings(_rec_for(SlotRole.ROUGHNESS, p), InspectorOptions())}
        q = (np.round(a * 255) / 255).astype(np.float32)
        scores = [mc.seam_score(np.roll(np.roll(q, s, 0), s // 2, 1)) for s in (0, 1, 333, 1024)]
        spread.append(max(scores) - min(scores))
    _emit("B1_seamless_2048", {"maps": n_maps, "fires": fires, "max_roll_spread": max(spread)})
    assert fires == 0 and max(spread) <= 1.0


@pytest.mark.parametrize("kind", ["ramp-to-edge", "non-tileable-crop", "pasted-strip"])
def test_m005_still_fires_on_hard_seam(tmp_path, kind):
    """STRESS-B1: a step the tile has nowhere else (a non-tileable edge) is still an ERROR,
    at native resolution, also on a 2048² map that load_map would downsample."""
    rng = np.random.default_rng(7)
    a = np.clip(_fbm(2048, rng, beta=1.5, fmin=2) * 0.08 + 0.5, 0, 1)
    if kind == "ramp-to-edge":
        a = a + 0.15 * np.linspace(0, 1, 2048)[None, :]
    elif kind == "non-tileable-crop":
        a = np.clip(_fbm(4096, rng, beta=2.0, fmin=1) * 0.08 + 0.5, 0, 1)[:2048, :2048]
    else:   # a 300 px strip from another image, feathered on its inner edge only
        b = np.clip(_fbm(2048, rng, beta=1.5, fmin=2) * 0.08 + 0.35, 0, 1)
        w = np.clip(np.arange(2048) / 300.0, 0, 1)[None, :]
        a = b * (1 - w) + a * w
    p = str(tmp_path / "seam_Roughness.png"); _save_u8(p, a)
    f = [f for f in pixel_findings(_rec_for(SlotRole.ROUGHNESS, p), InspectorOptions()) if f.rule_id == "M005"]
    assert f and f[0].severity == Severity.ERROR


def test_m013_is_experimental_and_off_by_default(tmp_path):
    """STRESS-B5 (orchestrator: M013 stays implemented, off by default until calibrated).
    Native brick heights used to be flagged; with the defaults nothing fires. Enabling it
    via ``experimental_off=()`` runs the check again (calibration: docs/VERIFY.md row 12)."""
    rng = np.random.default_rng(11)
    on = InspectorOptions(config=dataclasses.replace(DEFAULT_CONFIG, experimental_off=()))
    assert "M013" in DEFAULT_CONFIG.experimental_off
    default_fires = 0
    for i in range(6 if FULL else 2):
        h, _, _, _ = _texture("brick", 1024, rng, (150, 70, 52))
        p = str(tmp_path / f"b{i}_Height.png")
        Image.fromarray((h * 65535 + 0.5).astype(np.uint16)).save(p)
        default_fires += "M013" in {f.rule_id for f in inspect([_rec_for(SlotRole.DISPLACEMENT, p)])}
    assert default_fires == 0
    up = str(tmp_path / "u_Roughness.png")
    _save_u8(up, _upscale(np.random.default_rng(2).random((1024, 1024)), 4, rng))
    assert "M013" not in {f.rule_id for f in inspect([_rec_for(SlotRole.ROUGHNESS, up)])}
    assert "M013" in {f.rule_id for f in inspect([_rec_for(SlotRole.ROUGHNESS, up)], on)}


def _upscale(a, k, rng):
    n = a.shape[0]
    small = Image.fromarray((np.clip(a[::k, ::k], 0, 1) * 255).astype(np.uint8))
    return np.asarray(small.resize((n, n), Image.BICUBIC)).astype(np.float32) / 255


def test_broken_maps_miss_rate(tmp_path):
    per = 10 if FULL else 3
    rng = np.random.default_rng(99)
    results = collections.defaultdict(lambda: [0, 0])     # category -> [caught, total]
    fams = ["wood", "brick", "concrete", "marble", "leather", "tile", "fabric", "terrazzo", "carpet", "hex"]
    for i in range(per):
        fam = fams[i % len(fams)]
        n = 512
        h, rgb, rough, _ = _texture(fam, n, rng, TONES[fam][0])
        d = tmp_path / f"s{i}"; d.mkdir()
        # (a) roughness loaded as sRGB (scene metadata)
        rp = str(d / "x_Roughness.png"); _save_u8(rp, rough)
        m = MaterialRecord("a", Renderer.VRAY, "VRayMtl", {}, [TextureRef(SlotRole.ROUGHNESS, rp, ColorSpace.SRGB,
                                                                         "Bitmaptexture", "r", file_exists=True)])
        results["sRGB-loaded roughness (R001)"][0] += any(f.rule_id == "R001" for f in inspect([m]))
        # (b) inverted green (DirectX map, OpenGL expected) — and with the shipped defaults
        npth = str(d / "x_NormalGL.png"); _save_u8(npth, _normal_from_height(h, directx=True))
        hp = str(d / "x_Height.png"); _save_u8(hp, h)
        m = MaterialRecord("b", Renderer.VRAY, "VRayMtl", {}, [
            TextureRef(SlotRole.NORMAL, npth, ColorSpace.LINEAR, via_normal_node=True, file_exists=True),
            TextureRef(SlotRole.DISPLACEMENT, hp, ColorSpace.LINEAR, file_exists=True)])
        results["inverted green, expected=opengl (M007)"][0] += any(
            f.rule_id == "M007" for f in inspect([m], InspectorOptions(normal_convention={"vray": "opengl"})))
        results["inverted green, shipped defaults (M007)"][0] += any(f.rule_id == "M007" for f in inspect([m]))
        # shipped defaults can't flag it, but the scan now says M007 is inactive (one M009)
        assert [f.rule_id for f in inspect([m, m])].count("M009") == 1
        # (c) gloss map in the roughness slot (named *_Gloss)
        gp = str(d / "x_Gloss.png"); _save_u8(gp, 1 - rough)
        m = MaterialRecord("c", Renderer.VRAY, "VRayMtl", {}, [TextureRef(SlotRole.ROUGHNESS, gp, ColorSpace.LINEAR,
                                                                         file_exists=True)])
        results["gloss file in roughness slot (R005)"][0] += any(f.rule_id == "R005" for f in inspect([m]))
        # (c') same pixels, file named *_Roughness: nothing can see it from pixels alone
        gp2 = str(d / "y_Roughness.png"); _save_u8(gp2, 1 - rough)
        m = MaterialRecord("c2", Renderer.VRAY, "VRayMtl", {}, [TextureRef(SlotRole.ROUGHNESS, gp2,
                                                                          ColorSpace.LINEAR, file_exists=True)])
        results["gloss pixels named Roughness (any)"][0] += any(f.severity != Severity.INFO for f in inspect([m]))
        # (d) baked vignette on the albedo
        u, v = _torus(n)
        vig = 1 - float(rng.uniform(0.35, 0.5)) * ((u - 0.5) ** 2 + (v - 0.5) ** 2) / 0.5
        ap = str(d / "x_Color.png"); _save_u8(ap, rgb * vig[..., None])
        m = MaterialRecord("d", Renderer.VRAY, "VRayMtl", {}, [TextureRef(SlotRole.BASE_COLOR, ap, ColorSpace.SRGB,
                                                                         file_exists=True)])
        results["baked vignette (M010)"][0] += any(f.rule_id == "M010" for f in inspect([m]))
        # (e) 4x / 8x upscaled data maps
        k = 4 if i % 2 == 0 else 8
        n2 = 1024
        h2, _, r2, _ = _texture("concrete", n2, rng, (150, 148, 142))
        for nm, arr in (("Roughness", r2), ("Height", h2)):
            up = str(d / f"u_{nm}.png"); _save_u8(up, _upscale(arr, k, rng))
            role = SlotRole.ROUGHNESS if nm == "Roughness" else SlotRole.DISPLACEMENT
            m = MaterialRecord("e", Renderer.VRAY, "VRayMtl", {}, [TextureRef(role, up, ColorSpace.LINEAR,
                                                                             file_exists=True)])
            m013_on = InspectorOptions(config=dataclasses.replace(DEFAULT_CONFIG, experimental_off=()))
            results[f"{k}x upscale (M013)"][0] += any(f.rule_id == "M013" for f in inspect([m], m013_on))
            results[f"{k}x upscale (M013)"][1] += 1
        for key in list(results):
            if "upscale" not in key:
                results[key][1] = i + 1
    table = {k: {"caught": c, "of": t, "miss_rate": round(1 - c / t, 3)} for k, (c, t) in results.items()}
    _emit("B2_miss_table", table)
    for k in ("sRGB-loaded roughness (R001)", "inverted green, expected=opengl (M007)",
              "gloss file in roughness slot (R005)", "baked vignette (M010)"):
        assert table[k]["miss_rate"] == 0.0, (k, table[k])


# =====================================================================================
# 3. Hostile images
# =====================================================================================
def _hostile_files(d):
    rng = np.random.default_rng(1)
    P_ = lambda n: os.path.join(d, n)
    out = {}
    Image.new("RGB", (1, 1), (128, 128, 128)).save(P_("a1x1.png")); out["1x1"] = "a1x1.png"
    Image.new("RGB", (2, 1), (128, 128, 128)).save(P_("a2x1.png")); out["2x1"] = "a2x1.png"
    Image.fromarray((rng.random((64, 64)) * 255).astype(np.uint8)).save(P_("l.png")); out["L"] = "l.png"
    Image.fromarray((rng.random((600, 600)) * 65535).astype(np.uint16)).save(P_("i16.png")); out["I;16"] = "i16.png"
    a = np.zeros((64, 64, 4), np.uint8); a[..., :3] = 128; a[..., 3] = np.linspace(0, 255, 64)[None, :]
    Image.fromarray(a).save(P_("rgba.png")); out["RGBA alpha ramp"] = "rgba.png"
    Image.fromarray((rng.random((64, 64, 3)) * 255).astype(np.uint8)).convert("P").save(P_("pal.png"))
    out["palette P"] = "pal.png"
    Image.fromarray((rng.random((64, 64, 3)) * 255).astype(np.uint8)).convert("CMYK").save(P_("cmyk.jpg"))
    out["CMYK jpeg"] = "cmyk.jpg"
    Image.fromarray((rng.random((32, 4096, 3)) * 255).astype(np.uint8)).save(P_("wide.png")); out["4096x32"] = "wide.png"
    Image.new("RGB", (512, 512), (90, 90, 90)).save(P_("flat.png")); out["zero variance"] = "flat.png"
    b = io.BytesIO(); Image.fromarray((rng.random((256, 256, 3)) * 255).astype(np.uint8)).save(b, "PNG")
    with open(P_("trunc.png"), "wb") as fh:
        fh.write(b.getvalue()[: len(b.getvalue()) // 2])
    out["truncated png"] = "trunc.png"
    open(P_("zero.png"), "wb").close(); out["0-byte"] = "zero.png"
    b = io.BytesIO(); Image.fromarray((rng.random((64, 64, 3)) * 255).astype(np.uint8)).save(b, "JPEG")
    with open(P_("fake.png"), "wb") as fh:
        fh.write(b.getvalue())
    out["jpeg bytes in .png"] = "fake.png"
    with open(P_("text.png"), "w") as fh:
        fh.write("not an image")
    out["text in .png"] = "text.png"
    Image.fromarray((rng.random((2600, 2600, 3)) * 255).astype(np.uint8)).save(P_("big.bmp"))
    out["20 MB BMP"] = "big.bmp"
    Image.fromarray((rng.random((64, 64)) > 0.5)).save(P_("one.png")); out["1-bit"] = "one.png"
    nm = "wood <>\"' \u00fcn\u00efc\u00f8d\u00e9 \u6728.png"
    Image.new("RGB", (8, 8)).save(P_(nm)); out["unicode/spaces/<>"] = nm
    return out


_ROLES = (SlotRole.BASE_COLOR, SlotRole.ROUGHNESS, SlotRole.METALNESS, SlotRole.NORMAL, SlotRole.DISPLACEMENT)


def _rec_for(role, path):
    cs = ColorSpace.SRGB if role == SlotRole.BASE_COLOR else ColorSpace.LINEAR
    return MaterialRecord("m", Renderer.VRAY, "VRayMtl", {}, [TextureRef(role, path, cs, file_exists=True,
                                                                        via_normal_node=True)])


def test_hostile_images_never_raise(tmp_path):
    files = _hostile_files(str(tmp_path))
    unreadable = {"truncated png", "0-byte", "text in .png"}
    rows = {}
    for label, fn in files.items():
        for role in _ROLES:
            p = os.path.join(str(tmp_path), fn)
            t0 = time.time()
            fs = pixel_findings(_rec_for(role, p), InspectorOptions())
            dt = time.time() - t0
            assert dt < 30, (label, role, dt)
            ids = sorted({f.rule_id for f in fs})
            rows[f"{label}/{role.value}"] = ids
            if label in unreadable:
                assert "M900" in ids, (label, role, ids)
            # inspect() on the same record also never raises and orders cleanly
            inspect([_rec_for(role, p)])
        # also a normal + height pair of this hostile file (1-pixel-wide images: STRESS-B2)
        if label in ("1x1", "2x1"):
            continue
        p = os.path.join(str(tmp_path), fn)
        m = MaterialRecord("m", Renderer.VRAY, "VRayMtl", {}, [
            TextureRef(SlotRole.NORMAL, p, ColorSpace.LINEAR, via_normal_node=True, file_exists=True),
            TextureRef(SlotRole.DISPLACEMENT, p, ColorSpace.LINEAR, file_exists=True)])
        rows[f"{label}/normal+height"] = sorted({f.rule_id for f in inspect(
            [m], InspectorOptions(normal_convention={"vray": "opengl"}))})
    _emit("B3_hostile", rows)


def test_1x1_normal_placeholder_with_height_does_not_crash_scan(tmp_path):
    """STRESS-B2: tiny maps give an M900 info; the scan survives."""
    n = str(tmp_path / "flat_Normal.png"); Image.new("RGB", (1, 1), (128, 128, 255)).save(n)
    h = str(tmp_path / "x_Height.png"); _save_u8(h, np.random.default_rng(0).random((256, 256)))
    m = MaterialRecord("m", Renderer.VRAY, "VRayMtl", {}, [
        TextureRef(SlotRole.NORMAL, n, ColorSpace.LINEAR, via_normal_node=True, file_exists=True),
        TextureRef(SlotRole.DISPLACEMENT, h, ColorSpace.LINEAR, file_exists=True)])
    got = inspect([m])
    assert any(f.rule_id == "M900" and "too small" in f.message for f in got)


def test_one_broken_check_becomes_m900_not_a_failed_scan(tmp_path, monkeypatch):
    """STRESS-B2: any unexpected exception inside a per-map check is contained."""
    def boom(*a, **k):
        raise RuntimeError("kaboom")
    monkeypatch.setattr(mc, "check_constant", boom)
    p = str(tmp_path / "x_Roughness.png"); _save_u8(p, np.random.default_rng(0).random((64, 64)))
    good = _dark_albedo_rec(tmp_path)
    got = inspect([_rec_for(SlotRole.ROUGHNESS, p), good])
    m900 = [f for f in got if f.rule_id == "M900"]
    assert len(m900) == 1 and "kaboom" in m900[0].detail
    assert any(f.rule_id == "M001" for f in got)      # the next material was still inspected


@pytest.mark.parametrize("kind", ["directory", "symlink loop"])
def test_unreadable_path_kinds_give_a_finding(tmp_path, kind):
    """STRESS-B11: directory / symlink loop -> R004 error."""
    if kind == "directory":
        p = tmp_path / "dir.png"; p.mkdir()
    else:
        a, b = tmp_path / "loopA.png", tmp_path / "loopB.png"
        os.symlink(b, a); os.symlink(a, b); p = a
    m = _rec_for(SlotRole.ROUGHNESS, str(p))
    r004 = [f for f in inspect([m]) if f.rule_id == "R004"]
    assert len(r004) == 1 and r004[0].severity == Severity.ERROR


def test_unreadable_file_permission_gives_r004(tmp_path):
    """STRESS-B11: a file without read permission is an R004, not a silent skip."""
    p = tmp_path / "x_Roughness.png"; _save_u8(str(p), np.full((8, 8), 0.5))
    os.chmod(p, 0)
    try:
        if os.access(p, os.R_OK):
            pytest.skip("running with permission override (root)")
        assert any(f.rule_id == "R004" for f in inspect([_rec_for(SlotRole.ROUGHNESS, str(p))]))
    finally:
        os.chmod(p, 0o644)


@pytest.mark.parametrize("scale,offset", [(1.0, 0.0), (12.5, -3.0)], ids=["0-1", "scene-units"])
def test_float_tiff_height_is_read_correctly(tmp_path, scale, offset):
    """STRESS-B6: 32-bit float heights are normalised, not clipped to black/white."""
    h = np.linspace(0, 1, 256, dtype=np.float32)[None, :].repeat(64, 0) * scale + offset
    p = str(tmp_path / "h_Height.tif")
    Image.fromarray(h.astype(np.float32)).save(p)
    for a in (mc.load_map(p), mc.load_crop(p), mc.load_map_and_seam(p)[0]):
        assert abs(float(a[..., 0].max()) - 1.0) < 0.02 and abs(float(a.mean()) - 0.5) < 0.05


def test_int32_height_is_normalised(tmp_path):
    """STRESS-B6: mode-I maps above 16-bit range are scaled by their range."""
    p = str(tmp_path / "h_Height.png")
    Image.fromarray((np.linspace(0, 1, 256)[None, :].repeat(16, 0) * 65535).astype(np.uint16)).save(p)
    a = mc.load_map(p)
    assert abs(float(a.max()) - 1.0) < 0.01 and abs(float(a.mean()) - 0.5) < 0.02
    im = Image.fromarray((np.linspace(0, 1, 64)[None, :].repeat(8, 0) * 1e6).astype(np.int32))
    b = mc._to_float(im)
    assert abs(float(b.max()) - 1.0) < 1e-6 and float(b.min()) == 0.0


_BIG_SCRIPT = textwrap.dedent("""
    import os, sys, time, json
    try:
        import resource            # Unix only; Windows reports peak_rss_mb 0
    except ImportError:
        resource = None
    sys.path.insert(0, %(root)r)
    import numpy as np
    from PIL import Image
    from material_inspector.core.inspector import InspectorOptions, pixel_findings
    from material_inspector.core.model import *
    p = %(path)r
    t0 = time.time()
    m = MaterialRecord("big", Renderer.VRAY, "VRayMtl", {}, [
        TextureRef(SlotRole.BASE_COLOR, p, ColorSpace.SRGB, file_exists=True),
        TextureRef(SlotRole.ROUGHNESS, p, ColorSpace.LINEAR, file_exists=True),
        TextureRef(SlotRole.NORMAL, p, ColorSpace.LINEAR, via_normal_node=True, file_exists=True),
        TextureRef(SlotRole.DISPLACEMENT, p, ColorSpace.LINEAR, file_exists=True)])
    ids = sorted({f.rule_id for f in pixel_findings(m, InspectorOptions())})
    if resource is None:
        rss = 0
    else:
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        rss = rss if sys.platform == "darwin" else rss * 1024
    print(json.dumps({"seconds": round(time.time() - t0, 2), "peak_rss_mb": round(rss / 2**20), "ids": ids}))
""")


@pytest.mark.skipif(not FULL, reason="8192² image only in STRESS_FULL")
def test_8192_square_time_and_rss(tmp_path):
    n = 8192
    rng = np.random.default_rng(8)
    base = _fbm(1024, rng, beta=1.5, fmin=2)
    img = np.tile(base, (8, 8))[..., None] * np.array([0.1, 0.09, 0.08]) + 0.5
    img += rng.standard_normal((n, n, 1)).astype(np.float32) * 0.02
    p = str(tmp_path / "huge_8192.png")
    Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8)).save(p, compress_level=1)
    del img
    code = _BIG_SCRIPT % {"root": INSPECTOR_DIR, "path": p}
    t0 = time.time()
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=300)
    assert out.returncode == 0, out.stderr[-2000:]
    res = json.loads(out.stdout.strip().splitlines()[-1])
    res["wall_s"] = round(time.time() - t0, 2); res["file_mb"] = round(os.path.getsize(p) / 2**20, 1)
    _emit("B3_8192", res)
    assert res["seconds"] < 30 and res["peak_rss_mb"] < 3 * 1024, res


# =====================================================================================
# 4. Scene walker on the fake runtime
# =====================================================================================
def test_walker_self_containing_multi_and_repeated_material():
    multi = Node("Multimaterial", "M"); multi._subs = [multi, _vray("a")]
    assert [m.name for m in SceneReader(FakeRT([multi])).materials()] == ["a"]
    shared = _vray("shared")
    assert len(SceneReader(FakeRT([Node("Multimaterial", "MM", subs=[shared] * 1000)])).materials()) == 1


def test_walker_depth_500_ok():
    cur = _vray("leaf")
    for i in range(500):
        cur = Node("Multimaterial", f"L{i}", subs=[cur])
    mats = SceneReader(FakeRT([cur])).materials()
    assert [m.name for m in mats] == ["leaf"]
    assert mats[0].scene_path.count("/") == 500


def test_walker_depth_1500_not_silently_dropped():
    """STRESS-B10: the material walk is iterative."""
    cur = _vray("leaf")
    for i in range(1500):
        cur = Node("Multimaterial", f"L{i}", subs=[cur])
    assert [m.name for m in SceneReader(FakeRT([cur])).materials()] == ["leaf"]


def test_walker_texmap_cycle_terminates():
    bm = Node("Bitmaptexture", "bm", filename="C:/x_rough.png", colorspace="raw")
    mix = Node("Mix", "mix"); comp = Node("CompositeTexturemap", "comp", subtex=[mix, bm])
    mix._subtex = [mix, comp, bm]          # references itself and its ancestor
    t0 = time.time()
    mats = SceneReader(FakeRT([_vray("cyc", texmap_reflectionGlossiness=comp)])).materials()
    assert time.time() - t0 < 5 and len(mats) == 1   # MAX_TEXMAP_DEPTH stops it (no RecursionError)


def test_walker_dedups_instanced_texmaps():
    """STRESS-B7: one instanced bitmap -> one TextureRef / one finding per material."""
    bm = Node("Bitmaptexture", "bm2", filename="C:/x_rough.png", colorspace="sRGB")
    mix = Node("Mix", "mix2", subtex=[bm, bm, None])
    mats = SceneReader(FakeRT([_vray("dag", texmap_reflectionGlossiness=mix)])).materials()
    assert len(mats[0].textures) == 1
    assert [f.rule_id for f in inspect(mats, InspectorOptions(check_pixels=False))].count("R001") == 1


def test_walker_fanout_is_bounded():
    """STRESS-B7: shared sub-graphs are read once (was 21,845 refs)."""
    bm = Node("Bitmaptexture", "bm", filename="C:/x_rough.png", colorspace="raw")
    node = Node("CompositeTexturemap", "c"); node._subtex = [node] * 4 + [bm]
    refs = SceneReader(FakeRT([])).read_texmap(node, SlotRole.ROUGHNESS)
    assert len(refs) <= 10, len(refs)


def test_walker_with_fresh_wrappers_reads_every_group():
    """STRESS-B4: pymxs-style fresh proxies (ids reused once freed); identity is getHandleByAnim."""
    groups = [Node("Multimaterial", f"G{i}", subs=[_vray(f"g{i}")]) for i in range(20)]
    root = Node("Multimaterial", "root", subs=groups)
    rt = FakeRT([root], fresh_wrappers=True)
    assert rt.getSubMtl(root, 1) is not rt.getSubMtl(root, 1)        # really fresh per access
    names = [m.name for m in SceneReader(rt).materials()]
    assert names == [f"g{i}" for i in range(20)], names


def test_walker_fresh_wrappers_instanced_texmap_once_per_material():
    """STRESS-B4/B7: an instanced texmap behind fresh wrappers -> one finding per material, not k^n."""
    bm = Node("Bitmaptexture", "bm", filename="C:/x_rough.png", colorspace="sRGB")
    layer = Node("CompositeTexturemap", "c"); layer._subtex = [layer] * 4 + [bm]
    mats = [_vray(f"m{i}", texmap_reflectionGlossiness=layer) for i in range(3)]
    recs = SceneReader(FakeRT([Node("Multimaterial", "root", subs=mats)], fresh_wrappers=True)).materials()
    assert [len(r.textures) for r in recs] == [1, 1, 1]
    got = inspect(recs, InspectorOptions(check_pixels=False))
    assert sorted(f.material for f in got if f.rule_id == "R001") == ["m0", "m1", "m2"]


def test_walker_falls_back_to_id_when_handles_unavailable(caplog):
    """STRESS-B4: no getHandleByAnim -> id() with the proxies kept alive, logged once."""
    class NoHandleRT(FakeRT):
        def getHandleByAnim(self, obj):
            raise AttributeError("getHandleByAnim")
    groups = [Node("Multimaterial", f"G{i}", subs=[_vray(f"g{i}")]) for i in range(20)]
    with caplog.at_level("WARNING", logger="material_inspector"):
        names = [m.name for m in SceneReader(NoHandleRT([Node("Multimaterial", "r", subs=groups)],
                                                       fresh_wrappers=True)).materials()]
    assert names == [f"g{i}" for i in range(20)]
    assert sum("getHandleByAnim" in r.getMessage() for r in caplog.records) == 1


def test_deep_texmap_graph_emits_r007():
    """STRESS-B10: MAX_TEXMAP_DEPTH truncation is reported, not silent."""
    cur = Node("Bitmaptexture", "deep", filename="C:/deep_rough.png", colorspace="raw")
    for i in range(P.MAX_TEXMAP_DEPTH + 3):
        cur = Node("Output", f"o{i}", subtex=[cur])
    recs = SceneReader(FakeRT([_vray("deep", texmap_reflectionGlossiness=cur)])).materials()
    r007 = [f for f in inspect(recs, InspectorOptions(check_pixels=False)) if f.rule_id == "R007"]
    assert len(r007) == 1 and r007[0].severity == Severity.INFO
    shallow = SceneReader(FakeRT([_vray("ok", texmap_reflectionGlossiness=Node("Output", "o", subtex=[
        Node("Bitmaptexture", "b", filename="C:/b_rough.png", colorspace="raw")]))])).materials()
    assert "R007" not in {f.rule_id for f in inspect(shallow, InspectorOptions(check_pixels=False))}


def test_walker_5000_materials_x_20_texmaps_perf():
    n = 5000 if FULL else 500
    mats = []
    for i in range(n):
        bms = [Node("Bitmaptexture", f"b{i}_{j}", filename=f"C:/t/m{i}_{j}_Color.png", colorspace="sRGB")
               for j in range(20)]
        mats.append(_vray(f"m{i}", texmap_diffuse=Node("CompositeTexturemap", f"c{i}", subtex=bms)))
    rt = FakeRT([Node("Multimaterial", "root", subs=mats)])
    t0 = time.time()
    recs = SceneReader(rt).materials()
    walk_s = time.time() - t0
    t0 = time.time()
    fs = inspect(recs, InspectorOptions(check_pixels=False))
    insp_s = time.time() - t0
    _emit("B4_walk_perf", {"materials": n, "texmaps_each": 20, "walk_s": round(walk_s, 2),
                           "inspect_s": round(insp_s, 2), "findings": len(fs)})
    assert len(recs) == n and all(len(r.textures) == 20 for r in recs)
    assert walk_s < 60


# =====================================================================================
# 5. Report
# =====================================================================================
_EVIL = ["<script>alert(1)</script>", "\"'&<>", "\u6728\u76ee \u00e9\u00e8 \U0001F600", "x" * 10000,
         "</td></tr><img src=x onerror=alert(1)>"]


def test_report_escapes_and_roundtrips():
    fs = []
    for i, s in enumerate(_EVIL):
        tex = f"C:/t/{s}.png"
        m = MaterialRecord(s, Renderer.VRAY, "VRayMtl", {"base_color": (0.01,) * 3, "brdf": s},
                           [TextureRef(SlotRole.ROUGHNESS, tex, ColorSpace.SRGB, "Bitmaptexture", s)])
        fs += inspect_material(m)
    html_ = to_html(fs, scene="<script>alert('scene')</script>")
    assert "<script>" not in html_ and "<img" not in html_ and "onerror=alert(1)>" not in html_
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in html_
    doc = _strict_json(to_json(fs, scene=_EVIL[0]))
    assert {f["material"] for f in doc["findings"]} == set(_EVIL)
    assert any(f["texture"] == _EVIL[1] + ".png" for f in doc["findings"])   # no '/' in it: basename intact


def test_report_5000_materials_size_time():
    n = 5000 if FULL else 500
    r = np.random.default_rng(3)
    fs = []
    for i in range(n):
        fs += inspect_material(_rand_record(r, typed=True))
    t0 = time.time(); h = to_html(fs); th = time.time() - t0
    t0 = time.time(); j = to_json(fs); tj = time.time() - t0
    _strict_json(j)
    _emit("B5_report_perf", {"materials": n, "findings": len(fs), "html_mb": round(len(h) / 2**20, 2),
                             "html_s": round(th, 2), "json_mb": round(len(j) / 2**20, 2), "json_s": round(tj, 2)})
    assert th < 30 and tj < 30


# =====================================================================================
# 6. CLI
# =====================================================================================
def test_cli_exit_1_on_findings(tmp_path, capsys):
    """STRESS-B12: exit codes stay distinct: 1 = errors found."""
    _save_u8(str(tmp_path / "x_Color.png"), np.full((16, 16, 3), 0.02))
    assert cli.main(["check-folder", str(tmp_path)]) == 1
    capsys.readouterr()


def test_cli_mixed_folder(tmp_path, capsys):
    n_files = 3000 if FULL else 300
    rng = np.random.default_rng(6)
    root = tmp_path / "tex"; root.mkdir()
    roles = ["Color", "Roughness", "Metalness", "NormalGL", "Height"]
    made = 0
    i = 0
    while made < n_files:
        sub = root / f"batch{i // 100}"; sub.mkdir(exist_ok=True)
        if i % 5 == 4:   # garbage set
            for k, role in enumerate(roles):
                p = sub / f"junk{i:04d}_{role}.png"
                [lambda: p.write_bytes(b""), lambda: p.write_text("hello"),
                 lambda: p.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes(40)),
                 lambda: p.write_bytes(os.urandom(300)), lambda: p.write_bytes(b"BM" + bytes(10))][k]()
        else:
            s = 64
            h, rgb, rough, metal = _texture(FAMILIES[i % len(FAMILIES)], s, rng, TONES[FAMILIES[i % len(FAMILIES)]][0])
            stem = str(sub / f"set{i:04d}")
            _save_u8(stem + "_Color.png", rgb); _save_u8(stem + "_Roughness.png", rough)
            _save_u8(stem + "_Metalness.png", metal); _save_u8(stem + "_NormalGL.png", _normal_from_height(h))
            _save_u8(stem + "_Height.png", h)
        made += 5; i += 1
    rep, js = tmp_path / "r.html", tmp_path / "r.json"
    t0 = time.time()
    code = cli.main(["check-folder", str(root), "--report", str(rep), "--json", str(js)])
    dt = time.time() - t0
    capsys.readouterr()
    doc = _strict_json(js.read_text(encoding="utf-8"))
    m900 = sum(1 for f in doc["findings"] if f["rule_id"] == "M900")
    _emit("B6_cli", {"files": made, "exit": code, "seconds": round(dt, 2),
                     "html_mb": round(rep.stat().st_size / 2**20, 2), "json_mb": round(js.stat().st_size / 2**20, 2),
                     "findings": len(doc["findings"]), "M900": m900})
    assert code in (0, 1) and m900 == made // 5   # every garbage file -> one clean M900
    assert dt < (600 if FULL else 60)


def test_cli_unreadable_folder_and_file(tmp_path, capsys):
    locked = tmp_path / "locked"; locked.mkdir()
    _save_u8(str(locked / "a_Color.png"), np.full((8, 8, 3), 0.5))
    os.chmod(locked, 0)
    try:
        assert cli.main(["check-folder", str(tmp_path)]) == 2     # skipped, no crash
    finally:
        os.chmod(locked, 0o755)
    f = tmp_path / "b_Roughness.png"; _save_u8(str(f), np.full((8, 8), 0.5))
    os.chmod(f, 0)
    try:
        assert cli.main(["check-folder", str(tmp_path)]) in (0, 1)   # unreadable file -> M900, no crash
    finally:
        os.chmod(f, 0o644)
    capsys.readouterr()


@pytest.mark.parametrize("kind", ["missing", "file", "unreadable"])
def test_cli_reports_bad_folder_argument(tmp_path, capsys, kind):
    """STRESS-B12: a bad folder argument is a clear error, exit 2 (findings exit 1)."""
    target = tmp_path / "nope"
    if kind == "file":
        target = tmp_path / "x_Color.png"; _save_u8(str(target), np.full((8, 8, 3), 0.5))
    if kind == "unreadable":
        target = tmp_path / "locked"; target.mkdir(); os.chmod(target, 0)
        if os.access(target, os.R_OK):
            os.chmod(target, 0o755); pytest.skip("running with permission override (root)")
    try:
        code = cli.main(["check-folder", str(target)])
    finally:
        if kind == "unreadable":
            os.chmod(target, 0o755)
    err = capsys.readouterr().err.lower()
    assert code == 2 and err.startswith("error:")
    assert {"missing": "does not exist", "file": "not a folder", "unreadable": "cannot read"}[kind] in err


# =====================================================================================
# 7. Config
# =====================================================================================
def _cfg(tmp_path, raw):
    p = tmp_path / "inspector.json"
    p.write_text(raw if isinstance(raw, str) else json.dumps(raw), encoding="utf-8")
    return str(p)


def test_config_valid_and_malformed_json_hold(tmp_path):
    opt, w = load_options(_cfg(tmp_path, {"disabled_rules": ["R015"], "max_side": 512}))
    assert opt.disabled_rules == ("R015",) and opt.max_side == 512 and not w
    for raw in ("{not json", "", "\x00\x01", '{"a": 1'):
        opt, w = load_options(_cfg(tmp_path, raw))
        assert w and isinstance(opt, InspectorOptions)
    opt, w = load_options(_cfg(tmp_path, {"normal_convention": {"vray": "OpenGL!"}}))
    assert w and opt.normal_convention["vray"] is None


@pytest.mark.parametrize("raw", ["[]", '"x"', "null", '{"rules": "x"}', '{"normal_convention": "opengl"}',
                                 '{"max_side": "big"}', '{"max_side": NaN}', '{"disabled_rules": 5}'],
                         ids=["list", "string", "null", "rules-str", "nc-str", "max_side-str", "max_side-nan",
                              "disabled-int"])
def test_config_wrong_types_warn_not_raise(tmp_path, raw):
    """STRESS-B3: wrong types warn and fall back per key."""
    opt, w = load_options(_cfg(tmp_path, raw))
    assert w and isinstance(opt, InspectorOptions)
    d = InspectorOptions()
    assert opt.max_side == d.max_side and opt.disabled_rules == d.disabled_rules and opt.config == d.config


def test_config_falls_back_per_key(tmp_path):
    """STRESS-B3: one bad key does not throw away the good ones."""
    opt, w = load_options(_cfg(tmp_path, {"max_side": "big", "disabled_rules": ["R015"],
                                          "rules": {"albedo_ceiling": 230, "albedo_floor_error": "30"},
                                          "check_pixels": "yes", "normal_convention": {"vray": "opengl"}}))
    assert len(w) == 3
    assert opt.max_side == 1024 and opt.disabled_rules == ("R015",) and opt.check_pixels is True
    assert opt.config.albedo_ceiling == 230 and opt.config.albedo_floor_error == DEFAULT_CONFIG.albedo_floor_error
    assert opt.normal_convention["vray"] == "opengl"


def _albedo_rec(tmp_path):
    p = str(tmp_path / "w_Color.png")
    _save_u8(p, np.random.default_rng(0).random((64, 64, 3)) * 0.8)
    return MaterialRecord("Wood", Renderer.VRAY, "VRayMtl", {"base_color": (0.002,) * 3},
                          [TextureRef(SlotRole.BASE_COLOR, p, ColorSpace.SRGB, file_exists=True)])


def _dark_albedo_rec(tmp_path):
    p = str(tmp_path / "d_Color.png")
    _save_u8(p, np.full((64, 64, 3), 0.03))
    return MaterialRecord("Dark", Renderer.VRAY, "VRayMtl", {},
                          [TextureRef(SlotRole.BASE_COLOR, p, ColorSpace.SRGB, file_exists=True)])


def test_string_threshold_rejected_or_scan_survives(tmp_path):
    """STRESS-B3: a string threshold is rejected with a warning; the scan runs."""
    opt, w = load_options(_cfg(tmp_path, {"rules": {"albedo_floor_error": "30"}}))
    inspect([_albedo_rec(tmp_path)], opt)
    assert w


@pytest.mark.parametrize("raw", ['{"rules": {"albedo_floor_error": NaN, "albedo_floor_strict": NaN}}',
                                 '{"rules": {"albedo_floor_error": -1, "albedo_floor_strict": -1}}'])
def test_bad_threshold_warns(tmp_path, raw):
    """STRESS-B8: NaN / negative thresholds warn and keep the default (R010 still fires)."""
    opt, w = load_options(_cfg(tmp_path, raw))
    fired = any(f.rule_id == "M001" for f in inspect([_dark_albedo_rec(tmp_path)], opt))   # uses the floors
    assert w and fired


@pytest.mark.parametrize("ms", [0, -5])
def test_max_side_nonpositive_warns(tmp_path, ms):
    """STRESS-B8: max_side <= 0 warns and keeps 1024."""
    opt, w = load_options(_cfg(tmp_path, {"max_side": ms}))
    ids = {f.rule_id for f in inspect([_albedo_rec(tmp_path)], opt)}
    assert w and "M900" not in ids and opt.max_side == 1024


def test_whitelist_string_does_not_disable_ceiling(tmp_path):
    """STRESS-B8: a bare string is not iterated per character."""
    opt, w = load_options(_cfg(tmp_path, {"rules": {"bright_whitelist": "snow"}}))
    m = MaterialRecord("Plaster wall", Renderer.VRAY, "VRayMtl", {"base_color": (1.0, 1.0, 1.0)})
    assert w and any(f.rule_id == "R010" for f in inspect_material(m, opt.config))
    opt, w = load_options(_cfg(tmp_path, {"rules": {"bright_whitelist": ["snow"]}}))
    assert not w and opt.config.bright_whitelist == ("snow",)


@pytest.mark.parametrize("val", [["R0O1"], "R001"])
def test_disabled_rules_typos_warn(tmp_path, val):
    """STRESS-B8: typos and a bare string warn; nothing gets disabled by accident."""
    opt, w = load_options(_cfg(tmp_path, {"disabled_rules": val}))
    assert w and opt.disabled_rules == ()


def _every_rule_scenario(tmp_path):
    """Materials + maps that trigger as many rule IDs as the synthetic data allows."""
    d = tmp_path / "every"; d.mkdir()
    rng = np.random.default_rng(0)
    p = lambda n: str(d / n)
    _save_u8(p("dark_Color.png"), np.full((64, 64, 3), 0.03))
    _save_u8(p("flat_Roughness.png"), np.full((64, 64), 0.5))
    _save_u8(p("grey_Metalness.png"), np.full((64, 64), 0.5))
    h = np.clip(_fbm(128, rng, beta=2.0, fmin=2) * 0.15 + 0.5, 0, 1)
    _save_u8(p("x_Height.png"), h)
    _save_u8(p("x_NormalGL.png"), _normal_from_height(h, directx=True))
    seam = np.clip(_fbm(128, rng, beta=1.5, fmin=2) * 0.05 + 0.5, 0, 1) + 0.3 * np.linspace(0, 1, 128)[None, :]
    _save_u8(p("seam_Roughness.png"), seam)
    tex = lambda role, fn, cs=ColorSpace.LINEAR, **kw: TextureRef(role, p(fn), cs, "Bitmaptexture", fn,
                                                                  file_exists=True, **kw)
    return [
        MaterialRecord("A", Renderer.VRAY, "VRayMtl",
                       {"base_color": (0.01,) * 3, "brdf": "phong", "glossiness": 1.0, "use_roughness": False,
                        "ior": 5.0, "refraction_amount": 1.0, "metalness": 0.5, "is_legacy": True,
                        "texmap_truncated": 8, "absorption_distance": math.nan},
                       [tex(SlotRole.ROUGHNESS, "flat_Roughness.png", ColorSpace.SRGB),
                        tex(SlotRole.BASE_COLOR, "dark_Color.png", ColorSpace.LINEAR),
                        TextureRef(SlotRole.ROUGHNESS, "C:/nope/w_Gloss.png", ColorSpace.UNKNOWN, file_exists=False),
                        TextureRef(SlotRole.BUMP, p("x_NormalGL.png"), ColorSpace.LINEAR, via_normal_node=False,
                                   file_exists=True)]),
        MaterialRecord("Gold dark", Renderer.VRAY, "VRayMtl", {"base_color": (0.05, 0.05, 0.05), "metalness": 1.0}),
        MaterialRecord("Mirror coal", Renderer.VRAY, "VRayMtl",
                       {"base_color": (0.01,) * 3, "glossiness": 1.0, "use_roughness": False}),
        MaterialRecord("B", Renderer.VRAY, "VRayMtl", {}, [
            tex(SlotRole.ROUGHNESS, "flat_Roughness.png"), tex(SlotRole.METALNESS, "grey_Metalness.png"),
            tex(SlotRole.ROUGHNESS, "seam_Roughness.png")]),
        MaterialRecord("D", Renderer.VRAY, "VRayMtl", {}, [tex(SlotRole.BASE_COLOR, "dark_Color.png", ColorSpace.SRGB)]),
        MaterialRecord("C", Renderer.VRAY, "VRayMtl", {}, [
            tex(SlotRole.NORMAL, "x_NormalGL.png", via_normal_node=True), tex(SlotRole.DISPLACEMENT, "x_Height.png")]),
    ]


def test_every_rule_id_can_be_disabled_alone(tmp_path):
    """STRESS-B8/B9: disabling one rule ID removes exactly that ID and nothing else."""
    from material_inspector.core.inspector import known_rule_ids
    mats = _every_rule_scenario(tmp_path)
    opt = InspectorOptions(normal_convention={"vray": "opengl"})
    base = collections.Counter(f.rule_id for f in inspect(mats, opt))
    expected = {"R001", "R002", "R003", "R004", "R005", "R006", "R007", "R008", "R010", "R011", "R012",
                "R013", "R014", "R015", "R016", "R017", "R018", "R020", "M001", "M003", "M004", "M005", "M007"}
    assert expected <= set(base), expected - set(base)
    for rid in sorted(known_rule_ids()):
        got = collections.Counter(f.rule_id for f in inspect(mats, dataclasses.replace(opt, disabled_rules=(rid,))))
        want = collections.Counter({k: v for k, v in base.items() if k != rid})
        if rid in ("M003", "M004"):
            want.pop("R020", None)        # R020 aggregates M003 + M004: by design it needs both
        assert got == want, (rid, got - want, want - got)
    # M009 is the shipped-defaults note: only when normal_convention is unset
    plain = [f for f in inspect(mats) if f.rule_id == "M009"]
    assert len(plain) == 1 and "FIRST_WINDOWS_SESSION" in plain[0].detail
    assert "M009" not in {f.rule_id for f in inspect(mats, InspectorOptions(disabled_rules=("M009",)))}


def test_config_cannot_disable_everything_silently(tmp_path):
    """Held: listing every rule disables them (explicit), but a config with only junk keys keeps all rules."""
    opt, w = load_options(_cfg(tmp_path, {"bogus": 1, "rules": {"nope": 2}, "normal_convention": {"vray": 7}}))
    assert len(w) == 3 and opt.disabled_rules == () and opt.check_pixels is True
    m = MaterialRecord("x", Renderer.VRAY, "VRayMtl", {"base_color": (0.01,) * 3, "ior": 5.0, "brdf": "phong"})
    assert {"R010", "R013", "R015"} <= {f.rule_id for f in inspect([m], opt)}
