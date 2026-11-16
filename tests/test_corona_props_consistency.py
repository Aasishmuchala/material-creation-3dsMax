"""Cross-package guard: the Inspector reads Corona materials with the same
property names MatForge's Corona builder writes.

The Inspector's first candidate for each CoronaPhysicalMtl param / slot / the
CoronaNormal input must appear in the builder's candidate list, so a material
MatForge builds is always readable by the Inspector (and a rename on one side
fails here instead of silently on-box).
"""
import os
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INSPECTOR = os.path.join(REPO, "inspector")
for p in (REPO, INSPECTOR):
    if p not in sys.path:
        sys.path.insert(0, p)

import material_inspector.max_adapter.props as P  # noqa: E402
from material_inspector.core.model import SlotRole  # noqa: E402
from maxplugin.corona_props import (CORONA_BITMAP, CORONA_MTL,  # noqa: E402
                                    CORONA_NORMAL, ENUM_ASSUMPTIONS, VERIFIED)

PARAM_MAP = {
    "base_color": "base_color", "roughness": "roughness",
    "metalness_mode": "metalness_mode", "ior": "ior",
    "refraction_amount": "refraction_amount",
    "absorption_color": "absorption_color",
    "absorption_distance": "absorption_distance",
    "thin_walled": "thin_mode",
    "complex_ior": "complex_ior_on",
}
SLOT_MAP = {
    SlotRole.BASE_COLOR: "base_texmap", SlotRole.ROUGHNESS: "roughness_texmap",
    SlotRole.METALNESS: "metalness_texmap", SlotRole.BUMP: "bump_texmap",
    SlotRole.DISPLACEMENT: "displacement_texmap",
    SlotRole.OPACITY: "opacity_texmap",
}


@pytest.mark.parametrize("insp_key,mf_key", sorted(PARAM_MAP.items()))
def test_param_first_candidate_in_builder(insp_key, mf_key):
    first = P.PARAMS["CoronaPhysicalMtl"][insp_key][0]
    assert first in CORONA_MTL[mf_key], (insp_key, first, CORONA_MTL[mf_key])


@pytest.mark.parametrize("role,mf_key", sorted(SLOT_MAP.items(),
                                               key=lambda kv: kv[1]))
def test_slot_first_candidate_in_builder(role, mf_key):
    first = P.SLOTS["CoronaPhysicalMtl"][role][0]
    assert first in CORONA_MTL[mf_key], (role, first, CORONA_MTL[mf_key])


def test_complex_ior_candidates_identical():
    # the Inspector gates R011/R018 on this toggle: every name MatForge may
    # write must be readable, in the same priority order
    assert P.PARAMS["CoronaPhysicalMtl"]["complex_ior"] == \
        CORONA_MTL["complex_ior_on"]


def test_corona_normal_input_consistent():
    assert P.NORMAL_CLASSES["CoronaNormal"]["input"][0] in CORONA_NORMAL["input"]


def test_corona_bitmap_filename_consistent():
    assert P.BITMAP_CLASSES["CoronaBitmap"]["path"][0] in CORONA_BITMAP["filename"]


def test_nothing_claimed_verified_and_enums_pinned():
    assert VERIFIED == frozenset()
    assert ENUM_ASSUMPTIONS == {"roughness_mode": 0, "metalness_mode": 1,
                                "sss_mode": 1}


def test_every_key_documented_in_verify_corona():
    path = os.path.join(REPO, "docs", "VERIFY_CORONA.md")
    with open(path, "r", encoding="utf-8") as f:
        doc = f.read()
    for table in (CORONA_MTL, CORONA_NORMAL, CORONA_BITMAP):
        for key, cands in table.items():
            assert "`%s`" % key in doc, key
            for c in cands:
                assert c in doc, (key, c)
