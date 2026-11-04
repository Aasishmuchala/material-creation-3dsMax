"""STRESS SUITE A — physics layer (matphys) + both material builders.

Off-Max, through tests/mock_pymxs.py. Two kinds of tests live here:

  * passing property tests: invariants that held under a seeded random sweep
    (these are permanent regression tests);
  * regression tests, one per defect found and fixed in wave FX-A, tagged
    ``STRESS-A<n>`` (see .router/stress/A_builders.md for severity + fix).

Heavy sweeps are sampled by default (whole file < 60 s); set STRESS_FULL=1 to
run the full matrices.
"""
import ast
import contextlib
import io
import itertools
import json
import math
import os
import random
import re
import sys

import numpy as np
import pytest
from PIL import Image

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TESTS = os.path.dirname(os.path.abspath(__file__))
for _p in (REPO, TESTS):
    if _p not in sys.path:
        sys.path.insert(0, _p)

import matphys  # noqa: E402
import mock_pymxs  # noqa: E402
from core import maps as core_maps  # noqa: E402
from core.recipes import RECIPES  # noqa: E402

FULL = bool(os.environ.get("STRESS_FULL"))
SEED = 20261104

CLASSES = list(RECIPES)
METALS = list(matphys.METALS)
METAL_OPTS = [None] + METALS + ["bogus"]
# scene unit -> mock system unit key, mm per unit
UNITS = {"mm": ("mm", 1.0), "cm": ("cm", 10.0), "m": ("m", 1000.0),
         "inch": ("in", 25.4), "ft": ("ft", 304.8)}
BUILD_UNITS = ("mm", "cm", "m", "inch")
DATA_KEYS = {"roughness", "normal", "height", "metalness", "opacity"}
ALL_MAP_KEYS = ("albedo", "roughness", "normal", "height", "ao", "opacity",
                "metalness")
SECRET = "sk-STRESS-A-SECRET-0xDEADBEEF"


class _Null(io.TextIOBase):
    def write(self, s):
        return len(s)


@contextlib.contextmanager
def _quiet():
    with contextlib.redirect_stdout(_Null()):
        yield


def _install(**kw):
    kw = dict(kw)
    if "system_unit" in kw:
        kw["system_unit"] = UNITS.get(kw["system_unit"],
                                      (kw["system_unit"],))[0]
    b, rt = mock_pymxs.install(**kw)
    import maxplugin.builder_corona as bc
    return b, bc, rt


def _misses(log):
    return [l for l in log if "MISS" in l]


def _walk(node, seen=None):
    """Every MockNode reachable from node through props (incl. node)."""
    seen = set() if seen is None else seen
    if id(node) in seen:
        return []
    seen.add(id(node))
    out = [node]
    for v in list(object.__getattribute__(node, "props").values()):
        if isinstance(v, mock_pymxs.MockNode):
            out.extend(_walk(v, seen))
    return out


def _tex_path_gamma(n):
    """(path, gamma) for a Bitmaptexture / CoronaBitmap node, else None."""
    p = n.props
    if n.cls == "Bitmaptexture":
        if "bitmap" in p:
            return p["bitmap"].path, p["bitmap"].gamma
        return p.get("filename", p.get("fileName")), None
    if n.cls == "CoronaBitmap":
        return p.get("filename"), p.get("gamma")
    return None


def _map_key(path):
    return os.path.splitext(os.path.basename(str(path)))[0].split("__")[0]


def _check_gamma(mat):
    """Data maps gamma 1.0; albedo never forced to 1.0."""
    for n in _walk(mat):
        pg = _tex_path_gamma(n)
        if pg is None:
            continue
        key = _map_key(pg[0])
        if key in DATA_KEYS:
            assert pg[1] == 1.0, "data map %s not linear: %r" % (key, pg)
        elif key == "albedo":
            assert pg[1] != 1.0, "albedo forced linear: %r" % (pg,)


def _check_material(kind, mclass, mat, rt, log, maps):
    recipe = RECIPES[mclass]
    _check_gamma(mat)
    nodes = _walk(mat)
    cls = str(rt.classOf(mat))
    if kind == "vray":
        assert cls in ("VRayMtl", "VRay2SidedMtl")
        core = mat.props["frontMtl"] if cls == "VRay2SidedMtl" else mat
        if recipe.get("two_sided"):
            assert cls == "VRay2SidedMtl"
            assert not any(k.startswith("refraction")
                           and k != "refraction_ior"
                           for k in core.props), "foliage refracts"
        m = core.props.get("reflection_metalness")
        if m is not None and "texmap_metalness" not in core.props:
            assert m in (0.0, 1.0), "fractional metalness %r" % m
    else:
        assert cls == "CoronaPhysicalMtl"
        if recipe.get("two_sided"):
            assert not any(k in mat.props for k in (
                "refractionAmount", "useThinMode",
                "volumetricAbsorptionColor", "volumetricAbsorptionDistance"))
        m = mat.props.get("metalnessMode")
        if m is not None:
            assert m in (0, 1)
    for n in nodes:
        for k, v in n.props.items():
            if isinstance(v, float):
                assert math.isfinite(v), "%s.%s = %r" % (n.cls, k, v)
    assert not _misses(log), _misses(log)
    assert SECRET not in "\n".join(log)


# =====================================================================
# 1. matphys
# =====================================================================

def _dielectric_fresnel(n, c):
    s2 = (1.0 - c * c) / (n * n)
    if s2 >= 1.0:
        return 1.0
    ct = math.sqrt(1.0 - s2)
    rs = ((c - n * ct) / (c + n * ct)) ** 2
    rp = ((n * c - ct) / (n * c + ct)) ** 2
    return 0.5 * (rs + rp)


def test_fresnel_random_nk_bounded_and_consistent():
    rng = random.Random(SEED)
    count = 50000 if FULL else 5000
    for _ in range(count):
        n = rng.uniform(0.01, 20.0)
        k = rng.uniform(0.0, 30.0) if rng.random() > 0.1 else 0.0
        f = matphys.f0(n, k)
        g = matphys.edge_tint(n, k)
        c = rng.random()
        r = matphys.fresnel_conductor(n, k, c)
        for v in (f, g, r):
            assert math.isfinite(v) and 0.0 <= v <= 1.0, (n, k, c, f, g, r)
        assert abs(matphys.fresnel_conductor(n, k, 1.0) - f) < 1e-9
        assert abs(matphys.reflectance_at(n, k, 90.0) - 1.0) < 1e-6


def test_fresnel_corners():
    assert matphys.f0(1.0, 0.0) == 0.0
    assert matphys.edge_tint(1.0, 0.0) == 0.0
    for deg in (0, 30, 60, 89):
        assert matphys.reflectance_at(1.0, 0.0, deg) < 1e-12
    for n in (1e-12, 1e-6, 1e-3):
        for k in (0.0, 1e-9, 5.0):
            for v in (matphys.f0(n, k), matphys.edge_tint(n, k),
                      matphys.fresnel_conductor(n, k, 0.3)):
                assert math.isfinite(v) and 0.0 <= v <= 1.0
    for n, k in ((1e6, 0.0), (1e6, 1e6), (1e-3, 1e6), (1e30, 1e30)):
        for v in (matphys.f0(n, k), matphys.edge_tint(n, k)):
            assert math.isfinite(v) and 0.0 <= v <= 1.0
    assert matphys.fresnel_conductor(1.5, 0.0, 0.0) == 1.0
    assert matphys.fresnel_conductor(1.5, 0.0, -0.5) == 1.0
    assert matphys.fresnel_conductor(1.5, 0.0, 2.0) == matphys.f0(1.5, 0.0)


def test_k0_matches_dielectric_fresnel_incl_tir():
    rng = random.Random(SEED + 1)
    for _ in range(20000 if FULL else 3000):
        n = rng.uniform(0.01, 20.0)
        c = rng.uniform(1e-4, 1.0)
        got = matphys.fresnel_conductor(n, 0.0, c)
        assert abs(got - _dielectric_fresnel(n, c)) < 1e-7, (n, c)


def test_edge_tint_inverts_gulbrandsen():
    """n,k built from Gulbrandsen's forward map (r, g) -> edge_tint gives g."""
    rng = random.Random(SEED + 2)
    for _ in range(20000 if FULL else 3000):
        r = rng.uniform(0.001, 0.99)
        g = rng.random()
        sr = math.sqrt(r)
        n_min = (1 - r) / (1 + r)
        n_max = (1 + sr) / (1 - sr)
        n = g * n_min + (1 - g) * n_max
        k2 = ((n + 1) ** 2 * r - (n - 1) ** 2) / (1 - r)
        k = math.sqrt(max(k2, 0.0))
        assert abs(matphys.f0(n, k) - r) < 1e-9
        assert abs(matphys.edge_tint(n, k) - g) < 1e-6, (r, g)


def test_fresnel_huge_values_finite():
    """STRESS-A11: n,k clamp to matphys.fresnel.NK_MAX; never NaN/overflow."""
    nan, inf = float("nan"), float("inf")
    for n, k in ((1e200, 1e200), (1e200, 0.0), (inf, inf), (nan, 1.0),
                 (1.0, nan), (-5.0, 2.0)):
        assert 0.0 <= matphys.f0(n, k) <= 1.0
        assert 0.0 <= matphys.edge_tint(n, k) <= 1.0
        assert math.isfinite(matphys.fresnel_conductor(n, k, 0.5))


def test_glass_sigma_transmittance_roundtrip(monkeypatch):
    rng = random.Random(SEED + 3)
    for i in range(20000 if FULL else 2000):
        t = tuple(math.exp(rng.uniform(math.log(1e-6), math.log(0.999999)))
                  for _ in range(3))
        d = math.exp(rng.uniform(math.log(0.01), math.log(1000.0)))
        monkeypatch.setitem(matphys.GLASS, "_stress", {
            "label": "s", "ior": 1.5, "transmittance": t, "thickness_mm": d,
            "source": "stress", "approx": True})
        sig = matphys.glass_sigma_mm("_stress")
        back = matphys.transmittance(sig, d)
        for a, b in zip(t, back):
            assert abs(a - b) <= 1e-9 * max(a, 1e-6) + 1e-15, (t, d)
        # renderer converters reproduce T at the stated thickness, any units
        for _unit, (_k, mmpu) in UNITS.items():
            fog, mult = matphys.to_vray_fog(sig, d, mmpu)
            depth = d / mmpu                      # one pane, scene units
            for a, f in zip(t, fog):
                assert abs(f ** (mult * depth) - a) <= 1e-9 * a + 1e-15
            col, dist = matphys.to_corona_absorption(sig, d, mmpu)
            assert abs(dist - depth) <= 1e-12 * depth
            for a, c in zip(t, col):
                assert abs(c ** (depth / dist) - a) <= 1e-9 * a + 1e-15


@pytest.mark.parametrize("mclass", ["glass_clear", "glass_frosted", "water"])
@pytest.mark.parametrize("unit", list(UNITS))
def test_builders_glass_transmittance_unit_invariant(mclass, unit):
    refr = RECIPES[mclass]["refraction"]
    d = refr["thickness_mm"]
    want = matphys.transmittance(matphys.glass_sigma_mm(refr["glass"]), d)
    mmpu = UNITS[unit][1]
    depth = d / mmpu
    with _quiet():
        b, bc, rt = _install(system_unit=unit)
        pv = b.build_material({}, "G", mclass).props
        pc = bc.build_material({}, "G", mclass).props
    fog = pv["refraction_fogColor"].as_unit()
    t_v = [f ** (pv["refraction_fogMult"] * depth) for f in fog]
    col = pc["volumetricAbsorptionColor"].as_unit()
    t_c = [c ** (depth / pc["volumetricAbsorptionDistance"]) for c in col]
    for a, x, y in zip(want, t_v, t_c):
        assert abs(a - x) < 1e-6 and abs(a - y) < 1e-6


def test_vray_gemstone_fog_unit_invariant():
    """STRESS-A2: gemstone fog goes through matphys (recipe fog_color = T at
    thickness_mm), so T at 10 mm is the same in every unit and renderer."""
    refr = RECIPES["gemstone"]["refraction"]
    d = refr["thickness_mm"]
    want = tuple(refr["fog_color"])
    effs = []
    for unit in ("mm", "cm", "m", "inch"):
        mmpu = UNITS[unit][1]
        with _quiet():
            b, bc, rt = _install(system_unit=unit)
            pv = b.build_material({}, "G", "gemstone").props
            pc = bc.build_material({}, "G", "gemstone").props
        depth = d / mmpu
        t_v = [f ** (pv["refraction_fogMult"] * depth)
               for f in pv["refraction_fogColor"].as_unit()]
        t_c = [c ** (depth / pc["volumetricAbsorptionDistance"])
               for c in pc["volumetricAbsorptionColor"].as_unit()]
        assert all(abs(x - y) < 1e-6 for x, y in zip(t_v, t_c)), (unit, t_v,
                                                                  t_c)
        assert all(abs(x - w) < 1e-6 for x, w in zip(t_v, want)), (unit, t_v)
        effs.append(t_v)
    for e in effs[1:]:
        assert all(abs(x - y) < 1e-6 for x, y in zip(effs[0], e))


# ---------- albedo clamp ----------

def _lum8(lin):
    y = lin[..., 0] * 0.2126 + lin[..., 1] * 0.7152 + lin[..., 2] * 0.0722
    return core_maps._lin_to_srgb(y) * 255.0


def test_albedo_clamp_random_images_range_and_hue():
    rng = np.random.default_rng(SEED)
    shapes = [(1, 1), (2, 3), (64, 64)] + ([(512, 512)] if FULL else [])
    for shape in shapes:
        for scale in (0.02, 0.2, 1.0, 1.2):
            img = (rng.random(shape + (3,)) * scale).astype(np.float32)
            out, frac = core_maps.clamp_albedo(img)
            assert out.shape == img.shape and np.isfinite(out).all()
            assert out.min() >= 0.0 and out.max() <= 1.0
            assert 0.0 <= frac <= 1.0
            lum = _lum8(core_maps._srgb_to_lin(out))
            assert lum.min() >= 30.0 - 0.6 and lum.max() <= 240.0 + 0.6
            # hue: chroma direction in linear unchanged for non-black pixels
            lin_in = core_maps._srgb_to_lin(np.clip(img, 0, 1))
            lin_out = core_maps._srgb_to_lin(out)
            ni = np.linalg.norm(lin_in, axis=-1)
            no = np.linalg.norm(lin_out, axis=-1)
            ok = ni > 1e-4
            cos = (lin_in * lin_out).sum(-1)[ok] / (ni[ok] * no[ok])
            assert cos.size == 0 or cos.min() > 0.9999


def test_albedo_clamp_corners():
    for v, lo, hi in ((0.0, 29.4, 30.6), (1.0, 239.4, 240.6),
                      (0.5, 0, 255)):
        img = np.full((1, 1, 3), v, np.float32)
        out, frac = core_maps.clamp_albedo(img)
        lum = float(_lum8(core_maps._srgb_to_lin(out))[0, 0])
        assert lo <= lum <= hi
        assert frac == (0.0 if v == 0.5 else 1.0)
    # all-black lifts to a neutral grey
    out, _ = core_maps.clamp_albedo(np.zeros((4, 4, 3), np.float32))
    assert np.allclose(out[..., 0], out[..., 1]) and np.allclose(
        out[..., 1], out[..., 2])
    # +/-inf clip into range (16-bit normalised input behaves like 8-bit)
    out, _ = core_maps.clamp_albedo(np.array(
        [[[np.inf, 0, 0], [-np.inf, 0.3, 0.3]]], np.float32))
    assert np.isfinite(out).all()
    u16 = (np.arange(48, dtype=np.float64).reshape(4, 4, 3) * 1365.0
           / 65535.0).astype(np.float32)
    out16, _ = core_maps.clamp_albedo(u16)
    out8, _ = core_maps.clamp_albedo((np.round(u16 * 255) / 255).astype(
        np.float32))
    assert np.abs(out16 - out8).max() < 0.02


def test_albedo_clamp_scalar_matches_bounds():
    rng = random.Random(SEED + 4)
    for _ in range(5000 if FULL else 1000):
        rgb = tuple(rng.random() ** 3 for _ in range(3))
        out, changed = matphys.clamp_albedo_srgb(rgb)
        lum = matphys.srgb_luminance_8bit(out)
        assert 29.5 <= lum <= 240.5 or not changed
        assert all(0.0 <= c <= 1.0 for c in out)


def test_albedo_clamp_nan_sanitised():
    img = np.array([[[np.nan, 0.5, 0.5], [0.5, 0.5, 0.5]]], np.float32)
    out, frac = core_maps.clamp_albedo(img)
    assert np.isfinite(out).all()
    # NaN pixel -> neutral floor grey; the other pixel is untouched
    assert np.allclose(out[0, 0, 0], out[0, 0, 1]) and np.allclose(
        out[0, 0, 1], out[0, 0, 2])
    lum = float(_lum8(core_maps._srgb_to_lin(out))[0, 0])
    assert 29.4 <= lum <= 30.6
    assert np.allclose(out[0, 1], 0.5, atol=1e-4)
    assert frac == 0.5


def test_albedo_clamp_rgba_keeps_alpha():
    img = np.full((2, 2, 4), 0.02, np.float32)
    img[..., 3] = 0.7
    out, _ = core_maps.clamp_albedo(img)
    assert np.allclose(out[..., 3], 0.7)


def _write_png16_gray(path, value):
    Image.fromarray(np.full((32, 32), value, np.uint16)).save(path)


@pytest.mark.parametrize("kind", ["png16", "tif_float"])
def test_generate_maps_high_bitdepth_gray(tmp_path, kind):
    p = str(tmp_path / ("ref." + ("png" if kind == "png16" else "tif")))
    if kind == "png16":
        _write_png16_gray(p, 20000)            # ~0.305 -> ~78/255
    else:
        Image.fromarray(np.full((32, 32), 0.305, np.float32)).save(p)
    out = core_maps.generate_maps(p, str(tmp_path / "o"), mclass="generic",
                                  resolution="2k", seamless=False)
    alb = np.asarray(Image.open(out["albedo"]), dtype=np.float32)
    assert 50.0 < alb.mean() < 110.0, alb.mean()


# =====================================================================
# 2. builders — full matrix
# =====================================================================

def _fake_maps(variant, mclass, root="C:/fake"):
    full = {k: "%s/%s.png" % (root, k) for k in ALL_MAP_KEYS}
    if variant == "full":
        return full
    if variant == "full_nometal":
        return {k: v for k, v in full.items() if k != "metalness"}
    if variant == "empty":
        return {}
    if variant == "missing":
        return {k: "/nonexistent/%s.png" % k for k in ALL_MAP_KEYS}
    if variant == "extra":
        d = dict(full)
        d.update({"specular": root + "/specular.png", "ao2": root + "/x.png",
                  "keys": root + "/fal_keys.json"})
        return d
    if variant in ("1x1", "mismatched"):
        return {k: "%s/%s__%s.png" % (root, k, variant) for k in ALL_MAP_KEYS}
    raise KeyError(variant)


MAP_VARIANTS = ("full", "full_nometal", "empty", "missing", "extra", "1x1",
                "mismatched")


def _sample(product, n, seed):
    if FULL:
        return list(product)
    allc = list(product)
    return random.Random(seed).sample(allc, min(n, len(allc)))


def test_build_material_matrix():
    combos = _sample(itertools.product(
        CLASSES, ("vray", "corona"), METAL_OPTS, MAP_VARIANTS, (True, False),
        BUILD_UNITS, (False, True)), 4000, SEED + 10)
    # group by runtime config so install() runs once per group
    groups = {}
    for c in combos:
        groups.setdefault((c[4], c[5]), []).append(c)
    n = 0
    with _quiet():
        for (gamma, unit), items in groups.items():
            b, bc, rt = _install(gamma=gamma, system_unit=unit)
            for mclass, kind, metal, mv, _g, _u, cbm in items:
                maps = _fake_maps(mv, mclass)
                if kind == "vray":
                    fn = lambda: b.build_material(maps, "S_" + mclass, mclass,
                                                  metal=metal)
                else:
                    fn = lambda: bc.build_material(
                        maps, "S_" + mclass, mclass, metal=metal,
                        use_corona_bitmap=cbm, uvw_randomizer=cbm)
                if metal == "bogus":
                    with pytest.raises(ValueError):
                        fn()
                    continue
                mat = fn()
                _check_material(kind, mclass, mat, rt, list(b.LOG), maps)
                n += 1
    assert n > 0


def test_gamma_manager_never_changes_written_values():
    """Swatches are linear: gamma on/off must produce identical writes."""
    def dump(gamma, kind, mclass, metal):
        b, bc, rt = _install(gamma=gamma)
        fn = b.build_material if kind == "vray" else bc.build_material
        mat = fn(_fake_maps("full_nometal", mclass), "X", mclass, metal=metal)
        out = []
        for nd in _walk(mat):
            for k, v in sorted(nd.props.items()):
                if isinstance(v, mock_pymxs.MockColor):
                    out.append((nd.cls, k, round(v.r, 9), round(v.g, 9),
                                round(v.b, 9)))
                elif isinstance(v, (int, float, str, bool)):
                    out.append((nd.cls, k, v))
        return out
    with _quiet():
        for mclass in CLASSES:
            for kind in ("vray", "corona"):
                for metal in (None, "gold"):
                    assert dump(True, kind, mclass, metal) == dump(
                        False, kind, mclass, metal)


def test_colour_writes_in_swatch_range():
    """Every Color written is 0-255 except Complex IOR n,k (raw n,k x 255,
    VERIFY_CORONA type/scale row)."""
    exempt = {"complexIorN", "complexIorK"}
    with _quiet():
        b, bc, rt = _install()
        for mclass in CLASSES:
            for metal in [None] + METALS:
                for fn in (b.build_material, bc.build_material):
                    mat = fn(_fake_maps("full_nometal", mclass), "X", mclass,
                             metal=metal)
                    for nd in _walk(mat):
                        for k, v in nd.props.items():
                            if (isinstance(v, mock_pymxs.MockColor)
                                    and k not in exempt):
                                assert all(0.0 <= c <= 255.0 for c in (
                                    v.r, v.g, v.b)), (mclass, k, v)


def test_swatch_clamped_from_bad_table(monkeypatch):
    monkeypatch.setitem(RECIPES["generic"], "reflect_color", (1.5, -0.2, 0.5))
    with _quiet():
        b, bc, rt = _install()
        mat = b.build_material({}, "X", "generic")
    c = mat.props["reflection"]
    assert all(0.0 <= x <= 255.0 for x in (c.r, c.g, c.b)), c
    assert (c.r, c.g, c.b) == (255.0, 0.0, 127.5)
    assert any("clamped" in l for l in b.LOG), b.LOG


@pytest.mark.parametrize("metal", [None, "gold"])
@pytest.mark.parametrize("mclass", CLASSES)
def test_scalar_metalness_parity(mclass, metal):
    """STRESS-A3: with no metalness map, the V-Ray scalar metalness (0 when
    unwritten) is 0/1 and equals Corona's metalnessMode (0 when unwritten)."""
    maps = _fake_maps("full_nometal", mclass)
    with _quiet():
        b, bc, rt = _install()
        pv = b.build_material(maps, "X", mclass, metal=metal)
        pc = bc.build_material(maps, "X", mclass, metal=metal).props
    if str(rt.classOf(pv)) == "VRay2SidedMtl":
        pv = pv.props["frontMtl"]
    v = pv.props.get("reflection_metalness", 0.0)
    assert v in (0.0, 1.0), (mclass, v)
    assert int(v) == pc.get("metalnessMode", 0), (mclass, v, pc.get(
        "metalnessMode"))


# ---------- build_from_manifest matrix ----------

def _write_map_files(root, variant):
    os.makedirs(root, exist_ok=True)
    rng = np.random.default_rng(len(variant))
    paths = {}
    keys = ALL_MAP_KEYS
    if variant == "empty":
        return {}
    if variant == "missing":
        return {k: os.path.join(root, "gone", k + ".png") for k in keys}
    for i, k in enumerate(keys):
        if variant == "full_nometal" and k == "metalness":
            continue
        side = 1 if variant == "1x1" else (
            (4 + 3 * i) if variant == "mismatched" else 8)
        p = os.path.join(root, "%s__%s.png" % (k, variant))
        Image.fromarray((rng.random((side, side + i % 2, 3)) * 255).astype(
            np.uint8)).save(p)
        paths[k] = p
    if variant == "extra":
        kp = os.path.join(root, "fal_keys.json")
        with open(kp, "w") as f:
            json.dump({"fal": SECRET, "omega": SECRET}, f)
        paths["keys"] = kp
        sp = os.path.join(root, "specular__extra.png")
        Image.fromarray(np.zeros((2, 2, 3), np.uint8)).save(sp)
        paths["specular"] = sp
    return paths


@pytest.fixture(scope="module")
def manifest_maps(tmp_path_factory):
    root = str(tmp_path_factory.mktemp("stressA_maps"))
    return {v: _write_map_files(os.path.join(root, v), v)
            for v in MAP_VARIANTS}, root


def _mf_path(root, name, mclass, maps, metal_in_manifest=None):
    mf = {"schema": 1, "name": name, "class": mclass, "maps": maps}
    if metal_in_manifest:
        mf["metal"] = metal_in_manifest
    p = os.path.join(root, "m_%d.json" % (abs(hash((name, mclass,
                                                    json.dumps(mf)))),))
    with open(p, "w", encoding="utf-8") as f:
        json.dump(mf, f)
    return p


def test_build_from_manifest_matrix(manifest_maps):
    mmaps, root = manifest_maps
    combos = _sample(itertools.product(
        CLASSES, ("vray", "corona", "both", "auto"), METAL_OPTS,
        MAP_VARIANTS, (True, False), BUILD_UNITS, (None, 1, 24)),
        1500, SEED + 11)
    rng = random.Random(SEED + 12)
    groups = {}
    for c in combos:
        groups.setdefault((c[4], c[5]), []).append(c)
    paths = {}
    n = 0
    with _quiet():
        for (gamma, unit), items in groups.items():
            for active in (1, 24):
                b, bc, rt = _install(gamma=gamma, system_unit=unit,
                                     active_slot=active,
                                     renderer=rng.choice(["vray", "corona",
                                                          None]))
                for (mclass, rnd, metal, mv, _g, _u, slot) in items[
                        (0 if active == 1 else 1)::2]:
                    via_mf = metal not in (None,) and rng.random() < 0.3
                    key = (mclass, mv, metal if via_mf else None)
                    if key not in paths:
                        paths[key] = _mf_path(root, "MF_" + mclass, mclass,
                                              mmaps[mv], key[2])
                    kw = dict(slot=slot, renderer=rnd,
                              metal=None if via_mf else metal)
                    if mv == "missing":
                        # validator order: metal key before file existence
                        exc = (ValueError if via_mf and metal == "bogus"
                               else FileNotFoundError)
                        with pytest.raises(exc):
                            b.build_from_manifest(paths[key], **kw)
                        continue
                    if metal == "bogus":
                        with pytest.raises(ValueError):
                            b.build_from_manifest(paths[key], **kw)
                        continue
                    out = b.build_from_manifest(paths[key], **kw)
                    n += 1
                    log = out["log"]
                    assert not _misses(log), _misses(log)
                    assert SECRET not in "\n".join(log)
                    mats = out["materials"]
                    if rnd == "both":
                        assert out["renderer"] == "both" and len(mats) == 2
                        s1, s2 = mats[0]["slot"], mats[1]["slot"]
                        assert s1 != s2
                        m1 = rt.meditMaterials[s1 - 1]
                        m2 = rt.meditMaterials[s2 - 1]
                        assert m1 is not m2
                        assert m1.cls in ("VRayMtl", "VRay2SidedMtl")
                        assert m2.cls == "CoronaPhysicalMtl"
                    else:
                        assert len(mats) == 1
                    for m in mats:
                        live = rt.meditMaterials[m["slot"] - 1]
                        _check_gamma(live)
                        assert 1 <= m["slot"] <= 24
    assert n > 0


def test_both_at_last_slot_distinct(manifest_maps):
    mmaps, root = manifest_maps
    p = _mf_path(root, "Last", "concrete", mmaps["full"])
    for kw in ({"slot": 24}, {"slot": None}, {"slot": 99}, {"slot": 0}):
        with _quiet():
            b, bc, rt = _install(active_slot=24)
            out = b.build_from_manifest(p, renderer="both", **kw)
        s = [m["slot"] for m in out["materials"]]
        assert len(set(s)) == 2, (kw, s)
        assert rt.meditMaterials[s[0] - 1] is not rt.meditMaterials[s[1] - 1]


def test_auto_with_neither_class_raises_pinned(manifest_maps):
    mmaps, root = manifest_maps
    p = _mf_path(root, "N", "concrete", mmaps["full"])
    for rnd in (None, "vray", "corona"):
        with _quiet():
            b, bc, rt = _install(renderer=rnd, classes=())
        with pytest.raises(RuntimeError) as ei:
            b.build_from_manifest(p, renderer="auto")
        assert str(ei.value) == ("Neither V-Ray nor Corona material classes "
                                 "are available")


def test_both_log_keeps_vray_placement(manifest_maps):
    mmaps, root = manifest_maps
    p = _mf_path(root, "Both", "concrete", mmaps["full"])
    with _quiet():
        b, bc, rt = _install()
        out = b.build_from_manifest(p, renderer="both", slot=24)
    assert any("placed 'Both' in editor slot 24" in l for l in out["log"])


# =====================================================================
# 3. property drift
# =====================================================================

class StrictNode(mock_pymxs.MockNode):
    """Like real pymxs: writing a property the class lacks raises."""

    def __setattr__(self, key, value):
        if key not in object.__getattribute__(self, "schema"):
            raise AttributeError("Unknown property: \"%s\"" % key)
        self.props[key] = value


class StrictRuntime(mock_pymxs.MockRuntime):
    def _node(self, cls):
        return StrictNode(cls, mock_pymxs._SCHEMAS[cls] - self._drop)


class OldOpenBitMapRuntime(mock_pymxs.MockRuntime):
    """A Max build whose openBitMap has no gamma kwarg."""

    def openBitMap(self, path, gamma=None):
        if gamma is not None:
            raise TypeError("openBitMap: unexpected keyword gamma")
        return mock_pymxs.MockBitmap(path, None)


def _swap_runtime(b, rt):
    """Swap builder.rt in place (no reload) — the Corona builder must follow."""
    b.rt = rt
    sys.modules["pymxs"].runtime = rt


ALL_PROPS = sorted(set().union(*mock_pymxs._SCHEMAS.values()) - {"name"})


def _written(mat):
    return {k for nd in _walk(mat) for k in nd.props}


DRIFT_MAPS = ("full", "full_nometal", "empty")


def test_property_drift_never_raises_and_logs_miss():
    """0-30 % of every schema dropped, strict nodes: build never raises, and a
    dropped property that a full build writes surfaces as a MISS."""
    rng = random.Random(SEED + 20)
    full_written = {}
    with _quiet():
        b, bc, rt = _install()
        for mclass in CLASSES:
            for kind, fn in (("vray", b.build_material),
                             ("corona", bc.build_material)):
                for mv in DRIFT_MAPS:
                    full_written[kind, mclass, mv] = _written(
                        fn(_fake_maps(mv, mclass), "X", mclass))
    droppable = [p for p in ALL_PROPS if p != "texmap_diffuse"]  # STRESS-A5
    # alternates in schema / caught fallbacks that legitimately log no MISS
    no_miss_ok = {"filename", "fileName", "bitmap"}
    trials = 3000 if FULL else 400
    with _quiet():
        b, bc, rt0 = _install()
        for _ in range(trials):
            drop = frozenset(rng.sample(droppable, int(
                len(droppable) * rng.uniform(0.0, 0.30))))
            _swap_runtime(b, StrictRuntime(drop=drop))
            mclass = rng.choice(CLASSES)
            kind = rng.choice(("vray", "corona"))
            fn = b.build_material if kind == "vray" else bc.build_material
            metal = rng.choice([None] + METALS)
            mv = rng.choice(DRIFT_MAPS)
            fn(_fake_maps(mv, mclass), "X", mclass, metal=metal)
            hit = (drop & full_written[kind, mclass, mv]) - no_miss_ok
            if hit and metal is None:
                assert _misses(b.LOG), (kind, mclass, sorted(hit))


def test_texmap_diffuse_write_goes_through_set_first():
    with _quiet():
        b, bc, rt = _install()
        _swap_runtime(b, StrictRuntime(drop={"texmap_diffuse"}))
        b.build_material(_fake_maps("full", "generic"), "X", "generic")
    assert _misses(b.LOG)


def test_old_openbitmap_fallback_does_not_raise():
    with _quiet():
        b, bc, rt = _install()
        _swap_runtime(b, OldOpenBitMapRuntime())
        for mclass in CLASSES:
            b.build_material(_fake_maps("full", mclass), "X", mclass)
            bc.build_material(_fake_maps("full", mclass), "X", mclass)


def test_old_openbitmap_fallback_reports_miss():
    with _quiet():
        b, bc, rt = _install()
        _swap_runtime(b, OldOpenBitMapRuntime())
        b.build_material(_fake_maps("full", "generic"), "X", "generic")
    assert any("MISS" in l and "gamma" in l.lower() for l in b.LOG), b.LOG


# =====================================================================
# 4. manifest fuzz + injection
# =====================================================================

FUZZ_NAMES = [
    "x" * 10000, "Mat\u00e9riau_\u6728\u6750_\U0001F332", 'a"b', "a\\b",
    "a'b", "line1\nline2", "100%_%s_%d", "close)paren", '");delete $*;("',
    '" + (python.Execute "import os") + "', "\\\\server\\share", "",
]


@pytest.mark.parametrize("name", FUZZ_NAMES)
def test_fuzz_names_roundtrip_and_never_executed(tmp_path, name):
    maps = _write_map_files(str(tmp_path / "maps"), "full")
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"name": name, "class": "concrete",
                             "maps": maps}), encoding="utf-8")
    with _quiet():
        b, bc, rt = _install()
        seen = []
        real = rt.execute

        def rec(expr):
            seen.append(str(expr))
            return real(expr)
        rt.execute = rec
        if not name.strip():                  # STRESS-A1: empty name rejected
            with pytest.raises(ValueError):
                b.build_from_manifest(str(p), renderer="both")
            assert not seen
            return
        out = b.build_from_manifest(str(p), renderer="both")
    want = name[:b.MAX_NAME_LEN]              # STRESS-A1: 120-char cap
    assert out["material"] == want
    assert rt.meditMaterials[out["slot"] - 1].props["name"] == want
    assert set(seen) <= {"(VRayMtl != undefined)",
                         "(CoronaPhysicalMtl != undefined)"}, seen


def test_bad_manifests_raise_value_errors(tmp_path):
    maps = _write_map_files(str(tmp_path / "maps"), "full")
    cases = [
        ("{", ValueError), ("", ValueError), ("\x00", ValueError),
        (json.dumps([1, 2]), ValueError),
        (json.dumps({"name": "x", "maps": {}}), ValueError),
        (json.dumps({"name": "x", "class": "nope", "maps": {}}), ValueError),
        (json.dumps({"name": "x", "class": "concrete", "maps": {},
                     "metal": "bogus"}), ValueError),
        (json.dumps({"name": "x", "class": "concrete",
                     "maps": {"albedo": "/nope/a.png"}}), FileNotFoundError),
        (json.dumps({"name": "x", "class": "concrete",
                     "maps": {"albedo": "\\\\srv\\share\\a.png"}}),
         FileNotFoundError),
    ]
    with _quiet():
        b, bc, rt = _install()
        for raw, exc in cases:
            p = tmp_path / "m.json"
            p.write_text(raw, encoding="utf-8")
            with pytest.raises(exc):
                b.build_from_manifest(str(p))


def test_dotdot_and_absolute_paths_build(tmp_path):
    maps = _write_map_files(str(tmp_path / "a" / "maps"), "full")
    (tmp_path / "b").mkdir()
    dotted = {k: os.path.join(str(tmp_path / "b"), "..", "a", "maps",
                              os.path.basename(v)) for k, v in maps.items()}
    p = tmp_path / "m.json"
    p.write_text(json.dumps({"name": "dd", "class": "stone", "maps": dotted}))
    with _quiet():
        b, bc, rt = _install()
        out = b.build_from_manifest(str(p), renderer="both")
    assert len(out["materials"]) == 2


BAD_TYPE_MANIFESTS = {
    "class_list": {"name": "x", "class": ["concrete"], "maps": {}},
    "maps_list": {"name": "x", "class": "concrete", "maps": []},
    "maps_null": {"name": "x", "class": "concrete", "maps": None},
    "map_path_null": {"name": "x", "class": "concrete",
                      "maps": {"albedo": None}},
    "metal_list": {"name": "x", "class": "concrete", "maps": {},
                   "metal": ["gold"]},
    "name_null": {"name": None, "class": "concrete", "maps": {}},
    "name_int": {"name": 123, "class": "concrete", "maps": {}},
    "top_string": "name class maps",
    "top_null": None,
    "name_empty": {"name": "", "class": "concrete", "maps": {}},
    "name_blank": {"name": "   ", "class": "concrete", "maps": {}},
    "map_path_int": {"name": "x", "class": "concrete", "maps": {"albedo": 3}},
}


@pytest.mark.parametrize("case", sorted(BAD_TYPE_MANIFESTS))
def test_wrong_type_manifest_raises_value_error(tmp_path, case):
    p = tmp_path / "m.json"
    p.write_text(json.dumps(BAD_TYPE_MANIFESTS[case]))
    with _quiet():
        b, bc, rt = _install()
        with pytest.raises(ValueError) as ei:
            b.build_from_manifest(str(p))
    assert type(ei.value) is ValueError and "manifest" in str(ei.value)


def test_relative_map_paths_resolve_from_manifest_dir(tmp_path, monkeypatch):
    maps = _write_map_files(str(tmp_path / "mf"), "full")
    rel = {k: os.path.basename(v) for k, v in maps.items()}
    p = tmp_path / "mf" / "m.json"
    p.write_text(json.dumps({"name": "rel", "class": "concrete",
                             "maps": rel}))
    other = tmp_path / "elsewhere"
    other.mkdir()
    monkeypatch.chdir(other)
    with _quiet():
        b, bc, rt = _install()
        out = b.build_from_manifest(str(p), renderer="vray")
    assert out["material"] == "rel"
    mat = rt.meditMaterials[out["slot"] - 1]
    paths = {pg[0] for pg in (_tex_path_gamma(n) for n in _walk(mat)) if pg}
    assert os.path.join(str(tmp_path / "mf"), rel["albedo"]) in paths, paths


def _execute_calls(path):
    tree = ast.parse(open(path, encoding="utf-8").read())
    calls = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in ("execute", "Execute",
                                       "ExecuteFile")):
            calls.append(node)
    return tree, calls


def test_static_no_user_string_reaches_execute():
    """Every rt.execute argument is a literal, the _has_class literal-name
    template, or forge_max.show()'s rollout built from static tables."""
    for rel in ("maxplugin/builder.py", "maxplugin/builder_corona.py",
                "maxplugin/forge_max.py"):
        tree, calls = _execute_calls(os.path.join(REPO, rel))
        for c in calls:
            arg = c.args[0]
            src = ast.unparse(arg) if hasattr(ast, "unparse") else ""
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                continue
            ok = src in ('"(%s != undefined)" % name',
                         "'(%s != undefined)' % name",
                         "ROLLOUT_MXS.replace('%CLASS_ITEMS%', items)"
                         ".replace('%METAL_ITEMS%', metal_items)",
                         # FX-D: one-pass fill, same static tables
                         "_fill_rollout({'CLASS': items, "
                         "'METAL': metal_items})")
            assert ok, "%s:%d execute(%s)" % (rel, c.lineno, src)
    # _has_class is only ever called with string literals
    for rel in ("maxplugin/builder.py", "maxplugin/builder_corona.py",
                "maxplugin/forge_max.py"):
        tree = ast.parse(open(os.path.join(REPO, rel)).read())
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call)
                    and getattr(node.func, "id", getattr(
                        node.func, "attr", None)) == "_has_class"):
                assert isinstance(node.args[0], ast.Constant), (rel,
                                                                node.lineno)


def _mxs_literal_end(s):
    """Index where a MAXScript "..." literal starting at s[0] ends."""
    assert s[0] == '"'
    i = 1
    while i < len(s):
        if s[i] == "\\":
            i += 2
            continue
        if s[i] == '"':
            return i
        i += 1
    return -1


def test_mxs_str_escaping_is_closed():
    with _quiet():
        _install()
        import maxplugin.forge_max as fm
    rng = random.Random(SEED + 30)
    alphabet = '"\\\'\n\r\t%()$*?#;abc\u00e9\u6728'
    for _ in range(5000 if FULL else 1000):
        s = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 20)))
        lit = '"' + fm._mxs_str(s) + '"'
        assert _mxs_literal_end(lit) == len(lit) - 1, repr(s)
    for _, label in fm._CLASSES + [(None, l) for _, l in
                                   matphys.metal_choices()]:
        assert not set(label) & set('"\\\n%')


# =====================================================================
# 5. reentrancy
# =====================================================================

def test_build_from_manifest_twice_log_isolated(manifest_maps):
    mmaps, root = manifest_maps
    pa = _mf_path(root, "AAA", "concrete", mmaps["full"])
    pb = _mf_path(root, "BBB", "stone", mmaps["full"])
    with _quiet():
        b, bc, rt = _install()
        for rnd in ("vray", "corona", "both"):
            a = b.build_from_manifest(pa, renderer=rnd)
            bb = b.build_from_manifest(pb, renderer=rnd)
            assert not any("AAA" in l for l in bb["log"])
            assert any("AAA" in l for l in a["log"])     # copy, not alias
            assert bb["log"][0].startswith("building 'BBB'")


def test_nested_undo_ctx():
    with _quiet():
        b, bc, rt = _install()
        with b._undo_ctx("outer"):
            with b._undo_ctx("inner"):
                b.build_material({}, "N", "generic")
        orig = sys.modules["pymxs"].undo

        def boom(*a, **k):
            raise RuntimeError("no undo")
        sys.modules["pymxs"].undo = boom
        b.pymxs.undo = boom
        try:
            with b._undo_ctx("outer"):
                with b._undo_ctx("inner"):
                    pass
        finally:
            sys.modules["pymxs"].undo = orig


def test_corona_follows_swapped_and_reloaded_runtime():
    with _quiet():
        b, bc, rt1 = _install()
        rt2 = mock_pymxs.MockRuntime(system_unit="cm")
        _swap_runtime(b, rt2)
        mat = bc.build_material(_fake_maps("full", "stone"), "S", "stone")
        assert abs(mat.props["displacementMaximum"] - 0.3) < 1e-9
        assert bc._vb is b and bc._vb.rt is rt2
        b2, bc2, rt3 = _install(system_unit="m")       # importlib.reload
        assert bc2 is bc and bc2._vb is b2 and b2 is b
        mat = bc.build_material(_fake_maps("full", "stone"), "S", "stone")
        assert abs(mat.props["displacementMaximum"] - 0.003) < 1e-12
        assert b.LOG[0].startswith("building 'S'")
