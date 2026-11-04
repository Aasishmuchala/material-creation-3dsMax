/*  MatForge macro registrar -- shared by install_matforge.ms (run-from-repo)
    and the ApplicationPlugins bundle startup (Contents/scripts/matforge_startup.ms).

    matforgeRegisterMacros root
        root = the folder holding run_matforge.py / matforge_panel.ms /
               matforge_diagnose.ms (no trailing slash). Defines the three
               MatForge macroScripts with that folder BAKED IN as a literal.

    Why the macro source is generated and `execute`d: 3ds Max serializes each
    macroScript to ...\usermacros\MatForge-*.mcr and reloads it on every
    startup, but only the handler body survives -- session globals do not.
    Referencing a global path inside `on execute do` would be `undefined` after
    the next restart and `doesFileExist undefined` THROWS (-- Unable to convert:
    undefined to type: String). A literal @"..." survives the round trip, and
    a literal can only carry a path resolved at install time if the macro
    source itself is built as a string.                                        */

global matforgeRegisterMacros

-- one macroScript's source; `runner` is "python.ExecuteFile" or "fileIn".
-- The handler also re-sets the MatForgeRoot global from the literal so the
-- Python side (run_matforge.py) can find the root when __file__ is not set.
fn mfMacroSrc macroName tip btn root fileName runner = (
    local s = "macroScript " + macroName + "\n"
    s += "    category:\"MatForge\"\n"
    s += "    toolTip:\"" + tip + "\"\n"
    s += "    buttonText:\"" + btn + "\"\n"
    s += "(\n"
    s += "    on execute do (\n"
    s += "        global MatForgeRoot = @\"" + root + "\"\n"
    s += "        local p = @\"" + root + "\\" + fileName + "\"\n"
    s += "        if (doesFileExist p) then " + runner + " p\n"
    s += "        else messageBox (\"Not found:\\n\" + p) title:\"MatForge\"\n"
    s += "    )\n"
    s += ")\n"
    s
)

fn matforgeRegisterMacros root = (
    root = trimRight root "\\/"
    local ok = true
    local defs = #(
        -- reliable native rollout (RECOMMENDED default)
        #("MatForge_Open", "MatForge - reference image to V-Ray material",
          "MatForge", "run_matforge.py", "python.ExecuteFile"),
        -- fancy dark web panel (Create / Settings / Help chat) -- needs the webview
        #("MatForge_Panel", "MatForge - dark web panel (needs the embedded browser)",
          "MatForge panel", "matforge_panel.ms", "fileIn"),
        -- layer-by-layer self-test (run this if anything looks broken)
        #("MatForge_Diagnose", "MatForge - self-test / diagnostic",
          "MatForge diagnose", "matforge_diagnose.ms", "fileIn")
    )
    for d in defs do (
        try ( execute (mfMacroSrc d[1] d[2] d[3] root d[4] d[5]) )
        catch (
            ok = false
            format "[MatForge] could not register %: %\n" d[1] (getCurrentException())
        )
    )
    ok
)
