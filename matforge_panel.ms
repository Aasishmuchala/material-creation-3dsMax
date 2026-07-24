/*  MatForge panel - hosts the dark web UI (ui/panel.html) in a dockable Max
    dialog and bridges it to the Python backend.

    Bridge protocol (race-free):
      * JS sets document.title = "MATFORGE::<cmd>::<n>" and stashes the payload
        in a JS variable (NOT the title, so keys/messages/colons stay out of it).
      * This timer notices the title change, pulls the payload via
        InvokeScript("mfGetPayload"), runs the matching Python, and pushes the
        result back into the page via InvokeScript.
    The title is never reset by JS, so a command can't be missed between polls. */

global mfPanelHtml = @"C:\Users\aasis\matforge\ui\panel.html"
global mfWB
global mfTimer
global mfLastTitle = ""
global mfBackendOk = false

-- load the Python backend; if this fails, show the REAL error instead of
-- aborting the whole script silently (that reads as "nothing opened").
try (
    python.Execute "import sys; repo=r'C:\\Users\\aasis\\matforge'; (repo in sys.path) or sys.path.insert(0,repo)"
    python.Execute "import maxplugin.forge_max as fm; import importlib; importlib.reload(fm)"
    python.Execute "fm.set_ie_emulation()"   -- IE11 edge + unlock local JS
    mfBackendOk = true
) catch (
    local em = "MatForge could not load its Python backend:\n\n"
    em += (getCurrentException())
    em += "\n\nTry the native rollout instead (no browser needed):\n"
    em += "  Scripting > Run Script > run_matforge.py"
    messageBox em title:"MatForge"
)

fn mfCall method = ( try ( return mfWB.Document.InvokeScript method ) catch ( return "" ) )
fn mfBack method a b = ( try ( mfWB.Document.InvokeScript method #(a, b) ) catch () )
fn mfBack1 method a = ( try ( mfWB.Document.InvokeScript method #(a) ) catch () )

fn mfPoll s e = (
    try (
        local t = mfWB.DocumentTitle
        if (t != undefined and t != mfLastTitle and (matchPattern t pattern:"MATFORGE::*")) then (
            mfLastTitle = t
            local parts = filterString t "::"          -- payload is NOT in the title
            local cmd = if parts.count >= 2 then parts[2] else ""
            global mfBridgePayload = mfCall "mfGetPayload"
            if (mfBridgePayload == undefined) do mfBridgePayload = ""
            case cmd of (
                "browse":  ( python.Execute "fm._bridge_browse()"
                             local p = (try (mfBridgeImage) catch "")
                             if (p != undefined and p != "") do mfBack1 "mfImage" p )
                "create":  ( python.Execute "fm._bridge_create()"
                             mfBack "mfStatus" (try (mfBridgeState) catch "err") (try (mfBridgeText) catch "") )
                "savekeys":( python.Execute "fm._bridge_savekeys()"
                             mfBack "mfSaveStatus" (try (mfBridgeState) catch "err") (try (mfBridgeText) catch "") )
                "getkeys": ( python.Execute "fm._bridge_getkeys()"
                             mfBack1 "mfKeys" (try (mfBridgeText) catch "{}") )
                "chat":    ( mfBack1 "mfChatBusy" true
                             python.Execute "fm._bridge_chat()"
                             mfBack "mfChat" "assistant" (try (mfBridgeText) catch "")
                             mfBack1 "mfChatBusy" false )
                default: ()
            )
        )
    ) catch ( try (format "[MatForge] poll error: %\n" (getCurrentException())) catch () )
)

fn mfFallbackRollout = (
    -- webview unavailable -> open the native rollout so the user still has a UI
    try ( python.ExecuteFile @"C:\Users\aasis\matforge\run_matforge.py" ) catch()
)

fn mfOpenPanel = (
    try (destroyDialog mfPanelRollout) catch()
    rollout mfPanelRollout "MatForge" width:460 height:640 (
        dotNetControl wb "System.Windows.Forms.WebBrowser" pos:[0,0] width:460 height:640
        on mfPanelRollout open do (
            mfLastTitle = ""          -- reset sentinel: JS command counter also
                                      -- resets on (re)load, else 1st click is lost
            local wbOk = true
            try (
                mfWB = wb
                try (wb.ScrollBarsEnabled = true) catch()
                try (wb.WebBrowserShortcutsEnabled = false) catch()
                wb.Navigate mfPanelHtml
                mfTimer = dotNetObject "System.Windows.Forms.Timer"
                mfTimer.Interval = 250
                dotNet.addEventHandler mfTimer "Tick" mfPoll
                mfTimer.Start()
            ) catch ( wbOk = false )
            if (not wbOk) do (
                try (destroyDialog mfPanelRollout) catch()
                messageBox "The embedded browser could not start. Opening the native rollout instead." title:"MatForge"
                mfFallbackRollout()
            )
        )
        on mfPanelRollout close do ( try (mfTimer.Stop()) catch() )
    )
    createDialog mfPanelRollout 460 640 style:#(#style_titlebar,#style_border,#style_sysmenu,#style_resizing)
    try ( cui.RegisterDialogBar mfPanelRollout minSize:[360,520] maxSize:[760,1000] ) catch()
    try ( cui.DockDialogBar mfPanelRollout #cui_dock_right ) catch()
)

-- only open the webview panel if the backend actually loaded; otherwise the
-- native rollout is the working fallback (the catch above already explained why)
if mfBackendOk then mfOpenPanel() else mfFallbackRollout()
