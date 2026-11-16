-- Phase 0 helper: prints the real MAXScript property names of every material / texmap
-- class the Inspector reads, so material_inspector/max_adapter/props.py can be verified.
-- Usage: in a scene with V-Ray and Corona installed, run this script; copy the Listener
-- output into tests/fixtures/props_dump.txt.
(
    local classesToDump = #("VRayMtl", "CoronaPhysicalMtl", "CoronaLegacyMtl", "VRayBitmap",
                            "CoronaBitmap", "Bitmaptexture", "VRayNormalMap", "CoronaNormal",
                            "Normal_Bump", "VRayUVWRandomizer", "CoronaUvwRandomizer")
    for cname in classesToDump do
    (
        local c = execute cname
        if c == undefined then ( format "== % : NOT INSTALLED\n" cname; continue )
        local obj = undefined
        try (obj = c()) catch (format "== % : cannot construct\n" cname; continue)
        format "== % (%)\n" cname (maxVersion())
        for p in (getPropNames obj) do
        (
            local v = try (getProperty obj p) catch ("<err>")
            format "  % : % = %\n" p (classOf v) v
        )
    )
)
