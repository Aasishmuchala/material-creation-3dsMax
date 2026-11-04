-- MatForge startup (ApplicationPlugins bundle): registers the MatForge macroScripts with
-- this bundle's own Contents/scripts folder baked in. Runs on every Max start, so the
-- toolbar actions follow the bundle wherever it is installed. Category "MatForge".
global matforgeRegisterMacros
global MatForgeRoot
(
    local here = try (getThisScriptFilename()) catch (undefined)
    if here == undefined do here = getSourceFileName()
    local root = trimRight (getFilenamePath here) "\\/"
    MatForgeRoot = root
    local reg = root + "\\matforge_macros.ms"
    if (doesFileExist reg) then (
        fileIn reg
        matforgeRegisterMacros root
    ) else format "[MatForge] startup: missing %\n" reg
)
