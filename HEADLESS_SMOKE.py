"""Headless MatForge smoke — run via 3dsmaxbatch (no GUI needed).

Builds every material class through the real V-Ray builder, exercises the
displacement-modifier path on a temp Plane, collects any property MISSes
(the ONE thing the off-Max mock can't verify — real V-Ray 7 property names),
and writes a plain-text result file the caller can read directly.

Deliberately avoids the Material Editor (meditMaterials/MatEditor.Open) since
that UI may be unavailable in a headless batch session — the validation that
matters is whether the wiring's property names resolve on this V-Ray build.
"""
import os
import sys
import traceback

_REPO = r"C:\Users\aasis\matforge"
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

RESULT = os.path.join(_REPO, "smoke_result.txt")
_lines = []


def out(s):
    _lines.append(str(s))
    try:
        print(s)
    except Exception:
        pass


def _flush():
    try:
        with open(RESULT, "w", encoding="utf-8") as f:
            f.write("\n".join(_lines) + "\n")
    except Exception:
        pass


try:
    import importlib

    from maxplugin import builder
    importlib.reload(builder)
    from core.recipes import RECIPES
    from pymxs import runtime as rt

    SAMPLE = os.path.join(_REPO, "sample_maps", "Sample_Wood_maps")
    MAPS = {k: os.path.join(SAMPLE, k + ".png")
            for k in ("albedo", "roughness", "normal", "height", "ao")}
    FOLIAGE = dict(MAPS, opacity=os.path.join(SAMPLE, "albedo.png"))

    have_vray = hasattr(rt, "VRayMtl")
    out("MatForge HEADLESS SMOKE")
    out("3ds Max: %s" % str(getattr(rt, "maxVersion", lambda: "?")()))
    out("V-Ray (VRayMtl class present): %s" % have_vray)
    out("sample maps exist: %s" % all(os.path.isfile(p)
                                      for p in MAPS.values()))
    out("-" * 60)

    all_misses = []
    if not have_vray:
        out("SMOKE_FAIL: VRayMtl not found — V-Ray did not load in this "
            "batch session.")
    else:
        for mclass in RECIPES:
            maps = FOLIAGE if RECIPES[mclass].get("opacity") else MAPS
            try:
                mat = builder.build_material(maps, "HS_" + mclass, mclass)
                cls = str(rt.classOf(mat))
                misses = [l for l in builder.LOG if "MISS" in l]
                all_misses += ["%s | %s" % (mclass, m.strip())
                               for m in misses]
                out("  %-15s -> %-16s misses=%d" % (mclass, cls, len(misses)))
            except Exception as e:
                out("  %-15s -> BUILD ERROR: %s" % (mclass, e))
                all_misses.append("%s | EXCEPTION %s" % (mclass, e))

        # displacement-modifier path (real VRayDisplacementMod property names)
        try:
            plane = rt.Plane(width=100, length=100)
            rt.select(plane)
            stone = builder.build_material(MAPS, "HS_StoneDisp", "stone")
            n = builder.assign_to_selection(stone, "stone",
                                            height_map=MAPS["height"])
            dmiss = [l for l in builder.LOG if "MISS" in l]
            all_misses += ["displacement | %s" % m.strip() for m in dmiss]
            mods = [str(rt.classOf(m)) for m in plane.modifiers]
            out("  displacement    -> nodes=%s mods=%s" % (n, mods))
            try:
                rt.delete(plane)
            except Exception:
                pass
        except Exception as e:
            out("  displacement    -> PATH ERROR: %s" % e)

        uniq = sorted(set(all_misses))
        out("-" * 60)
        out("PROPERTY MISSES (%d unique):" % len(uniq))
        for m in uniq:
            out("  " + m)
        out("-" * 60)
        out("SMOKE_OK" if not uniq
            else "SMOKE_OK_WITH_MISSES (%d unique property names to patch)"
                 % len(uniq))
except Exception:
    out("SMOKE_FAIL — unhandled exception:")
    out(traceback.format_exc())
finally:
    _flush()
