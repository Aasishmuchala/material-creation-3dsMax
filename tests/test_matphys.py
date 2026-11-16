"""matphys tests - Fresnel vectors, metal F0 bands, glass converters, albedo clamp."""
import ast
import glob
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO)

import matphys  # noqa: E402
from matphys import colour as C  # noqa: E402

TOL = 1e-3
METAL_KEYS = ("gold", "silver", "copper", "aluminium", "chrome", "iron", "titanium",
              "nickel", "zinc", "brass", "bronze", "platinum", "stainless_steel")


def _close(a, b, tol):
    return abs(a - b) <= tol


# ---------- Fresnel vectors ----------

@pytest.mark.parametrize("n,k,f0,g,r82,r90", [
    (0.166, 3.15, 0.9411, 0.9979, 0.9567, 1.0000),
    (1.5, 0.0, 0.0400, 0.0000, 0.4639, None),
    (1.47, 7.79, 0.9120, None, 0.8358, None),
])
def test_fresnel_vectors(n, k, f0, g, r82, r90):
    assert _close(matphys.f0(n, k), f0, TOL)
    assert _close(matphys.reflectance_at(n, k, 82.0), r82, TOL)
    if g is not None:
        assert _close(matphys.edge_tint(n, k), g, TOL)
    if r90 is not None:
        assert _close(matphys.reflectance_at(n, k, 90.0), r90, TOL)


def test_aluminium_dips_below_f0_near_grazing():
    assert matphys.reflectance_at(1.47, 7.79, 82.0) < matphys.f0(1.47, 7.79)


def test_rgb_helpers_match_scalar():
    nk = ((0.166, 3.15), (1.5, 0.0), (1.47, 7.79))
    assert matphys.rgb_f0(nk) == tuple(matphys.f0(n, k) for n, k in nk)
    assert matphys.rgb_edge_tint(nk) == tuple(matphys.edge_tint(n, k) for n, k in nk)
    assert matphys.rgb_reflectance_at(nk, 60) == tuple(matphys.reflectance_at(n, k, 60) for n, k in nk)


@pytest.mark.parametrize("key", METAL_KEYS)
def test_conductor_limits_for_every_metal(key):
    for n, k in matphys.metal_nk(key):
        assert abs(matphys.fresnel_conductor(n, k, 1.0) - matphys.f0(n, k)) <= 1e-6
        assert abs(matphys.reflectance_at(n, k, 90.0) - 1.0) <= 1e-6


# ---------- metal table ----------

def test_metal_keys_and_order():
    assert tuple(matphys.METALS) == METAL_KEYS
    assert [k for k, _ in matphys.metal_choices()] == list(METAL_KEYS)
    assert all(isinstance(label, str) and label for _, label in matphys.metal_choices())


@pytest.mark.parametrize("key", METAL_KEYS)
def test_metal_entry_shape(key):
    m = matphys.METALS[key]
    assert set(m) >= {"label", "nk", "source", "approx"}
    assert len(m["nk"]) == 3 and all(len(p) == 2 for p in m["nk"])
    assert isinstance(m["approx"], bool)
    assert "refractiveindex.info" in m["source"] and "650/550/450" in m["source"]


def _band(got, want, tol=0.08):
    return all(abs(g - w) <= tol for g, w in zip(got, want))


LAGARDE = {
    "silver": (0.972, 0.960, 0.915), "copper": (0.955, 0.638, 0.538),
    "aluminium": (0.913, 0.922, 0.924), "chrome": (0.550, 0.556, 0.554),
    "iron": (0.562, 0.565, 0.578), "titanium": (0.542, 0.497, 0.449),
    "nickel": (0.660, 0.609, 0.526), "platinum": (0.672, 0.637, 0.585),
}


@pytest.mark.parametrize("key", sorted(LAGARDE))
def test_f0_band_lagarde(key):
    f = matphys.metal_f0(key)
    assert _band(f, LAGARDE[key]), (key, f)


def test_f0_band_gold():
    r, g, b = matphys.metal_f0("gold")
    assert r >= 0.92 - 0.08
    assert abs(g - 0.766) <= 0.08 and abs(b - 0.336) <= 0.08


def test_f0_band_zinc():
    f = matphys.metal_f0("zinc")
    assert max(f) - min(f) < 0.08
    assert 0.55 <= matphys.luminance_linear(f) <= 0.85


def test_f0_band_brass():
    r, g, b = matphys.metal_f0("brass")
    assert r > g > b and 0.85 <= r <= 0.98 and 0.30 <= b <= 0.65


def test_f0_band_bronze():
    r, g, b = matphys.metal_f0("bronze")
    assert r > g > b and 0.45 <= g <= 0.75


def test_stainless_is_flagged_iron_approx():
    s = matphys.METALS["stainless_steel"]
    assert s["approx"] is True
    assert s["nk"] == matphys.METALS["iron"]["nk"]
    assert "iron" in s["source"].lower() and "approx" in s["source"].lower()


@pytest.mark.parametrize("key", METAL_KEYS)
def test_edge_tint_in_unit_range(key):
    for g in matphys.metal_edge_tint(key):
        assert 0.0 <= g <= 1.0


def test_unknown_metal_raises():
    with pytest.raises(KeyError):
        matphys.metal_f0("unobtainium")


# ---------- glass ----------

PINNED_GLASS = {
    "soda_lime": (1.52, (0.85, 0.95, 0.95), 10.0, False),
    "low_iron": (1.52, (0.98, 0.985, 0.98), 10.0, True),
    "borosilicate": (1.47, (0.99, 0.99, 0.985), 10.0, True),
    "fused_silica": (1.458, (0.999, 0.999, 0.999), 10.0, False),
    "lead_crystal": (1.56, (0.97, 0.98, 0.97), 10.0, True),
    "tinted_bronze": (1.52, (0.62, 0.50, 0.38), 6.0, True),
    "tinted_grey": (1.52, (0.48, 0.47, 0.45), 6.0, True),
    "tinted_green": (1.52, (0.60, 0.82, 0.70), 6.0, True),
    "water": (1.333, (0.712, 0.945, 0.991), 1000.0, False),
    "ice": (1.31, (0.70, 0.95, 0.995), 1000.0, True),
}


def test_glass_table_is_pinned():
    assert tuple(matphys.GLASS) == tuple(PINNED_GLASS)
    for key, (ior, t, d, approx) in PINNED_GLASS.items():
        g = matphys.GLASS[key]
        assert g["ior"] == ior and matphys.glass_ior(key) == ior
        assert tuple(g["transmittance"]) == t
        assert g["thickness_mm"] == d
        assert g["approx"] is approx
        assert g["label"] and g["source"]
    assert matphys.GLASS["soda_lime"]["source"] == "Rubin 1985 (as in inspector RuleConfig)"
    assert [k for k, _ in matphys.glass_choices()] == list(PINNED_GLASS)


@pytest.mark.parametrize("key", sorted(PINNED_GLASS))
def test_transmittance_round_trips(key):
    g = matphys.GLASS[key]
    back = matphys.transmittance(matphys.glass_sigma_mm(key), g["thickness_mm"])
    for a, b in zip(back, g["transmittance"]):
        assert abs(a - b) <= 1e-9


def test_vray_fog_vectors():
    s = matphys.glass_sigma_mm("soda_lime")
    fog, mult = matphys.to_vray_fog(s, 6.0, 1.0)
    for a, b in zip(fog, (0.907, 0.970, 0.970)):
        assert abs(a - b) <= 0.003
    assert abs(mult - 0.1667) <= 1e-4
    fog_cm, mult_cm = matphys.to_vray_fog(s, 6.0, 10.0)
    assert fog_cm == fog
    assert abs(mult_cm - 1.6667) <= 1e-4


def test_corona_absorption_vector():
    s = matphys.glass_sigma_mm("soda_lime")
    fog, _ = matphys.to_vray_fog(s, 6.0, 1.0)
    col, dist = matphys.to_corona_absorption(s, 6.0, 10.0)
    assert col == fog
    assert abs(dist - 0.6) <= 1e-12


def test_sigma_clamps_zero_transmittance():
    old = matphys.GLASS["soda_lime"]["transmittance"]
    try:
        matphys.GLASS["soda_lime"]["transmittance"] = (0.0, 1.0, 2.0)
        s = matphys.glass_sigma_mm("soda_lime")
        assert s[0] > 0 and s[1] == 0.0 and s[2] == 0.0
    finally:
        matphys.GLASS["soda_lime"]["transmittance"] = old


# ---------- colour ----------

def test_display_encode():
    # Plan pinned ~0.2158; the exact IEC 61966-2-1 encode of 0.04 is 0.2209
    # (1.055 * 0.04 ** (1 / 2.4) - 0.055), which is what the inspector uses too.
    enc = matphys.display_encode((0.04, 0.04, 0.04), True)
    for c in enc:
        assert abs(c - 0.2209) <= 1e-3
        assert c == matphys.linear_to_srgb(0.04)
    x = (0.04, 0.5, 0.9)
    assert matphys.display_encode(x, False) == x
    assert matphys.display_encode(x) == matphys.rgb_to_srgb(x)


def test_colour_round_trip_and_clamps():
    for v in (0.0, 0.002, 0.04045, 0.2, 0.5, 1.0):
        assert abs(C.linear_to_srgb(C.srgb_to_linear(v)) - v) <= 1e-7  # knee: ~3e-8
    assert C.srgb_to_linear(-1.0) == 0.0 and C.srgb_to_linear(2.0) == 1.0
    assert C.linear_to_srgb(-1.0) == 0.0 and abs(C.linear_to_srgb(2.0) - 1.0) <= 1e-12
    assert matphys.luminance_linear((1, 0, 0)) == 0.2126
    assert matphys.luminance_linear((0, 1, 0)) == 0.7152
    assert matphys.luminance_linear((0, 0, 1)) == 0.0722


def test_scale_to_luminance_zero_branch():
    out = matphys.scale_to_luminance((0.0, 0.0, 0.0), 50.0)
    assert len(out) == 3 and out[0] == out[1] == out[2]
    assert abs(out[0] * 255.0 - 50.0) <= 1e-6


def test_colour_matches_inspector_module():
    insp = os.path.join(REPO, "inspector")
    if not os.path.isdir(os.path.join(insp, "material_inspector")):
        pytest.skip("inspector package not present")
    sys.path.insert(0, insp)
    try:
        from material_inspector.core import colour as IC
    finally:
        sys.path.remove(insp)
    for rgb in ((0.1, 0.2, 0.3), (0.0, 0.0, 0.0), (0.9, 0.5, 0.01), (1.0, 1.0, 1.0)):
        assert IC.srgb_luminance_8bit(rgb) == matphys.srgb_luminance_8bit(rgb)
        for target in (30.0, 240.0):
            assert tuple(IC.scale_to_luminance(rgb, target)) == matphys.scale_to_luminance(rgb, target)


# ---------- albedo ----------

def test_albedo_constants():
    assert matphys.ALBEDO_FLOOR_ERROR == 30.0
    assert matphys.ALBEDO_FLOOR_STRICT == 50.0
    assert matphys.ALBEDO_CEILING == 240.0
    assert matphys.BRIGHT_WHITELIST == ("snow", "spectralon", "ptfe", "whitereference")


def test_clamp_albedo_floor():
    rgb, changed = matphys.clamp_albedo_srgb((0.05, 0.05, 0.05))
    assert changed is True
    assert abs(matphys.srgb_luminance_8bit(rgb) - 30.0) <= 0.5


def test_clamp_albedo_ceiling_and_whitelist():
    bright = (0.99, 0.99, 0.99)
    rgb, changed = matphys.clamp_albedo_srgb(bright, name="Painted_Wall")
    assert changed is True and abs(matphys.srgb_luminance_8bit(rgb) - 240.0) <= 0.5
    rgb, changed = matphys.clamp_albedo_srgb(bright, name="Fresh_SNOW")
    assert changed is False and rgb == bright
    assert matphys.is_whitelisted("PTFE_target") and not matphys.is_whitelisted("plaster")


def test_clamp_albedo_in_range_unchanged():
    rgb, changed = matphys.clamp_albedo_srgb((0.5, 0.4, 0.3))
    assert changed is False and rgb == (0.5, 0.4, 0.3)


# ---------- API surface + Python 3.7 syntax guard ----------

def test_public_api_reexported():
    for name in ("WAVELENGTHS_NM", "srgb_to_linear", "linear_to_srgb", "luminance_linear",
                 "srgb_luminance_8bit", "scale_to_luminance", "rgb_to_linear", "rgb_to_srgb",
                 "display_encode", "f0", "fresnel_conductor", "reflectance_at", "edge_tint",
                 "rgb_f0", "rgb_edge_tint", "rgb_reflectance_at", "METALS", "metal_f0",
                 "metal_edge_tint", "metal_nk", "metal_choices", "GLASS", "glass_ior",
                 "glass_sigma_mm", "transmittance", "to_vray_fog", "to_corona_absorption",
                 "glass_choices", "ALBEDO_FLOOR_ERROR", "ALBEDO_FLOOR_STRICT", "ALBEDO_CEILING",
                 "BRIGHT_WHITELIST", "is_whitelisted", "clamp_albedo_srgb"):
        assert hasattr(matphys, name), name
        assert name in matphys.__all__
    assert matphys.WAVELENGTHS_NM == (650.0, 550.0, 450.0)
    doc = matphys.__doc__
    assert "650 / 550 / 450 nm" in doc and "D65" in doc


def test_matphys_sources_are_py37_clean():
    paths = sorted(glob.glob(os.path.join(REPO, "matphys", "*.py")))
    assert len(paths) == 6
    for path in paths:
        src = open(path).read()
        compile(src, path, "exec", flags=0)
        assert ":=" not in src, path
        assert "from __future__" not in src, path
        for node in ast.walk(ast.parse(src)):
            assert not isinstance(node, ast.AnnAssign), (path, node.lineno)
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                assert node.returns is None, (path, node.name)
                args = node.args.args + node.args.kwonlyargs
                assert all(a.annotation is None for a in args), (path, node.name)
