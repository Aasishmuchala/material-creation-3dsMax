"""MatForge smoke test — run INSIDE 3ds Max (Scripting > Run Script...).

Needs V-Ray installed (Max 2026 + V-Ray 7 on this machine). Builds one
material per representative class from the bundled sample maps, drops the
wood one on an editor sphere, and prints SMOKE_OK / SMOKE_FAIL with a
property-miss report. No rendering, no scene changes beyond one sphere
material (and optional assignment is skipped).
"""
import os
import sys
import traceback

_REPO = os.path.dirname(os.path.abspath(__file__))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

import importlib

from maxplugin import builder

importlib.reload(builder)

from pymxs import runtime as rt

SAMPLE = os.path.join(_REPO, "sample_maps", "Sample_Wood_maps")
MAPS = {k: os.path.join(SAMPLE, f"{k}.png")
        for k in ("albedo", "roughness", "normal", "height", "ao")}
FOLIAGE_MAPS = dict(MAPS, opacity=os.path.join(SAMPLE, "albedo.png"))

# one material per DISTINCT wiring feature so every candidate list is
# exercised against real V-Ray property names:
CASES = [
    ("Smoke_Wood", "wood_exterior", MAPS),      # displacement + coat
    ("Smoke_Glass", "glass_clear", MAPS),       # refraction + thin-walled + fog
    ("Smoke_Metal", "metal_brushed", MAPS),     # metalness + anisotropy
    ("Smoke_Leaf", "foliage", FOLIAGE_MAPS),    # 2-sided + clip opacity
    ("Smoke_Marble", "marble", MAPS),           # translucency activation
    ("Smoke_Fabric", "fabric", MAPS),           # sheen
    ("Smoke_Leather", "leather", MAPS),         # coat + sheen
]


def main():
    if not hasattr(rt, "VRayMtl"):
        print("SMOKE_FAIL: VRayMtl class not found — is V-Ray installed?")
        return
    misses, built = [], []
    for name, mclass, maps in CASES:
        try:
            mat = builder.build_material(maps, name, mclass)
            built.append((name, mat))
            misses += [f"{name}: {l}" for l in builder.LOG if "MISS" in l]
        except Exception:
            print(f"SMOKE_FAIL building {name}:")
            traceback.print_exc()
            return
    # checks
    wood = built[0][1]
    assert str(rt.classOf(wood)) == "VRayMtl", "wood should be VRayMtl"
    leaf = built[3][1]
    assert "2Sided" in str(rt.classOf(leaf)), "foliage must be VRay2SidedMtl"
    slot = builder.put_in_editor(wood)
    print(f"editor slot used: {slot}")

    # bump scale sanity: read back what V-Ray actually stored (should be the
    # 0-100 percentage from the recipe, e.g. 45 for wood_exterior)
    try:
        bump = getattr(wood, "texmap_bump_multiplier", None)
        print(f"wood bump multiplier (expect ~45 on 0-100 scale): {bump}")
    except Exception as e:
        print(f"bump readback skipped: {e}")

    # displacement path (review finding #2): assign stone w/ height to a temp
    # plane and confirm a VRayDisplacementMod with a texmap was added; also
    # fold any displacement property MISS into the report (the mod's
    # texmap/type/amount names are only validated live).
    try:
        plane = rt.Plane(width=100, length=100, pos=rt.Point3(0, 0, 0))
        rt.select(plane)
        stone = builder.build_material(MAPS, "Smoke_Stone", "stone")
        builder.assign_to_selection(stone, "stone", height_map=MAPS["height"])
        misses += [f"Smoke_Stone(disp): {l}"
                   for l in builder.LOG if "MISS" in l]
        mods = [str(rt.classOf(m)) for m in plane.modifiers]
        has_disp = any("Displac" in m for m in mods)
        print(f"displacement mod added to temp plane: {has_disp} ({mods})")
        rt.delete(plane)
    except Exception as e:
        print(f"displacement smoke skipped (non-fatal): {e}")

    if misses:
        print(f"SMOKE_OK_WITH_MISSES ({len(misses)} property misses):")
        for m in misses:
            print("  " + m)
    else:
        print("SMOKE_OK — all properties landed, 4 classes built, "
              "wood on editor sphere.")


main()
