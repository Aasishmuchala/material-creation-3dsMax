/*  MatForge self-test  --  Scripting > Run Script... > this file.
    Reports, layer by layer, exactly what works: system Python + Pillow/numpy,
    V-Ray, keys, and the panel asset. Output also prints to the MAXScript
    Listener so you can copy it. If any row says FAIL, that layer is the culprit.

    This is a PASSIVE check by design -- it does NOT touch your Material Editor
    slots or run the (slow) map generator, so it is safe to run anytime. To see
    a real material built end-to-end, just use the rollout (run_matforge.py).  */

global mfDiagText = "diagnose did not run"

-- run the layered check; if the backend can't even load, show WHY (readable)
try (
    python.Execute "import sys; repo=r'C:\\Users\\aasis\\matforge'; (repo in sys.path) or sys.path.insert(0,repo)"
    python.Execute "import maxplugin.forge_max as fm; import importlib; importlib.reload(fm)"
    python.Execute "import pymxs; pymxs.runtime.mfDiagText = fm.diagnose(run_create=False)"
) catch (
    mfDiagText = "MatForge diagnostic could not load its Python backend:\n\n"
    mfDiagText += (getCurrentException())
    mfDiagText += "\n\nSend me that text."
)

format "\n%\n" mfDiagText          -- always copyable from the Listener

-- WinForms TextBox needs CRLF; diagnose() joins with LF only -> convert or the
-- whole report collapses onto one line with box glyphs.
global mfDiagTextCRLF = substituteString mfDiagText "\n" "\r\n"

-- show it in a scrollable, copyable dialog; fall back to a messageBox
try (
    try (destroyDialog mfDiagRO) catch()
    rollout mfDiagRO "MatForge diagnostic" width:540 (
        dotNetControl tb "System.Windows.Forms.TextBox" pos:[8,8] width:524 height:310
        button btnCopy "Copy" width:80 height:26 pos:[8,326] across:2 align:#left
        button btnClose "Close" width:80 height:26 align:#right
        on mfDiagRO open do (
            -- guard the dotNet setup; a failure here would otherwise leave a
            -- blank dialog with no fallback
            try (
                tb.Multiline = true
                tb.ReadOnly = true
                tb.WordWrap = false
                tb.ScrollBars = (dotNetClass "System.Windows.Forms.ScrollBars").Both
                tb.Font = dotNetObject "System.Drawing.Font" "Consolas" 9
                tb.Text = mfDiagTextCRLF
            ) catch ( tb.Text = mfDiagTextCRLF )
        )
        on btnCopy pressed do setClipBoardText mfDiagText
        on btnClose pressed do destroyDialog mfDiagRO
    )
    createDialog mfDiagRO 540 366
) catch (
    messageBox mfDiagText title:"MatForge diagnostic"
)
