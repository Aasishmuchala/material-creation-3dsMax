<#
.SYNOPSIS
  One-command on-box verification for MatForge + Material Inspector (Windows, 3ds Max installed).
.DESCRIPTION
  Runs root + inspector pytest, the headless V-Ray/Corona smoke and the Inspector self-test
  through 3dsmaxbatch.exe, collects the results into OutDir and zips it. Reads no key files.
.PARAMETER MaxRoot
  3ds Max install folder. Default: newest "C:\Program Files\Autodesk\3ds Max 20xx".
.PARAMETER OutDir
  Where results are collected (default .\onbox_out).
#>
param(
    [string]$MaxRoot = "",
    [string]$OutDir = ".\onbox_out"
)
$ErrorActionPreference = "Continue"
$Repo = Split-Path -Parent $PSScriptRoot
$results = [ordered]@{}

function Step($name, $ok) {
    $results[$name] = $ok
    $tag = if ($ok) { "PASS" } else { "FAIL" }
    Write-Host ("[{0}] {1}" -f $tag, $name)
}

# --- locate Max -------------------------------------------------------------
if (-not $MaxRoot) {
    $cand = Get-ChildItem "C:\Program Files\Autodesk" -Directory -Filter "3ds Max 20*" -ErrorAction SilentlyContinue |
        Sort-Object Name -Descending | Select-Object -First 1
    if ($cand) { $MaxRoot = $cand.FullName }
}
$batch = if ($MaxRoot) { Join-Path $MaxRoot "3dsmaxbatch.exe" } else { "" }
$haveBatch = ($batch -ne "") -and (Test-Path $batch)

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
$OutDir = (Resolve-Path $OutDir).Path

# --- versions ---------------------------------------------------------------
Write-Host "== Versions =="
Write-Host ("Repo:      {0}" -f $Repo)
Write-Host ("Max root:  {0}" -f $(if ($MaxRoot) { $MaxRoot } else { "(not found)" }))
Write-Host ("Batch exe: {0}" -f $(if ($haveBatch) { $batch } else { "(not found)" }))
if ($MaxRoot -and (Test-Path (Join-Path $MaxRoot "3dsmax.exe"))) {
    Write-Host ("3dsmax.exe: {0}" -f (Get-Item (Join-Path $MaxRoot "3dsmax.exe")).VersionInfo.ProductVersion)
}
Get-ChildItem "C:\Program Files\Chaos\V-Ray", "C:\Program Files\Chaos\Corona" -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Write-Host ("Renderer dir: {0}" -f $_.FullName) }
try { Push-Location $Repo; Write-Host ("Git: {0}" -f (git rev-parse --short HEAD 2>$null)); Pop-Location } catch {}

if (Get-Process -Name 3dsmax -ErrorAction SilentlyContinue) {
    Write-Warning "An interactive 3dsmax.exe is running. 3dsmaxbatch needs a licence seat; close Max if the batch steps fail."
}

# --- system Python (py -3.12 -> py -3 -> python) ----------------------------
$pyCmd = $null
foreach ($c in @(@("py", "-3.12"), @("py", "-3"), @("python"))) {
    if (-not (Get-Command $c[0] -ErrorAction SilentlyContinue)) { continue }
    $extra = @(); if ($c.Count -gt 1) { $extra = $c[1..($c.Count - 1)] }
    & $c[0] @extra -c "import sys" 2>$null
    if ($LASTEXITCODE -eq 0) { $pyCmd = $c; break }
}
if (-not $pyCmd) {
    Write-Host "No system Python 3 found (py -3.12 / py -3 / python)."
    Step "system python" $false
    exit 1
}
$pyExe = $pyCmd[0]; $pyArgs = @(); if ($pyCmd.Count -gt 1) { $pyArgs = $pyCmd[1..($pyCmd.Count - 1)] }
function Py { & $pyExe @pyArgs @args }
Write-Host ("Python:    {0}" -f ((Py --version) 2>&1))

Py -c "import PIL, numpy" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Installing Pillow + numpy + pytest ..."
    Py -m pip install --quiet Pillow numpy pytest
}
Py -c "import PIL, numpy" 2>$null
Step "system python has Pillow+numpy" ($LASTEXITCODE -eq 0)
Py -c "import pytest" 2>$null
if ($LASTEXITCODE -ne 0) { Py -m pip install --quiet pytest }

# --- pytest -----------------------------------------------------------------
Write-Host "== Root pytest =="
Push-Location $Repo
Py -m pytest tests -q 2>&1 | Tee-Object -FilePath (Join-Path $OutDir "pytest_root.log")
Step "root pytest" ($LASTEXITCODE -eq 0)
Pop-Location

Write-Host "== Inspector pytest =="
Push-Location (Join-Path $Repo "inspector")
$env:QT_QPA_PLATFORM = "offscreen"
Py -m pytest -q 2>&1 | Tee-Object -FilePath (Join-Path $OutDir "pytest_inspector.log")
Step "inspector pytest" ($LASTEXITCODE -eq 0)
Pop-Location

# --- Max batch steps --------------------------------------------------------
$selfJson = Join-Path $env:TEMP "material_inspector_selftest.json"
if ($haveBatch) {
    Write-Host "== MatForge smoke (V-Ray + Corona) via 3dsmaxbatch =="
    $smokeRes = Join-Path $Repo "smoke_result.txt"
    Remove-Item $smokeRes -ErrorAction SilentlyContinue
    & $batch (Join-Path $Repo "smoke_wrapper.ms") 2>&1 | Tee-Object -FilePath (Join-Path $OutDir "smoke_batch.log")
    $smokeTxt = if (Test-Path $smokeRes) { Get-Content $smokeRes -Raw } else { "" }
    # contract: SMOKE_OK / SMOKE_OK_WITH_MISSES / SMOKE_FAIL
    Write-Host ("smoke_result: {0}" -f $(if ($smokeTxt -match "SMOKE_(OK_WITH_MISSES|OK|FAIL)") { $Matches[0] } else { "(no verdict)" }))
    Step "MatForge smoke" ($smokeTxt -match "SMOKE_OK(?!_WITH)" -or $smokeTxt -match "SMOKE_OK_WITH_MISSES")
    if ($smokeTxt -match "SMOKE_OK_WITH_MISSES") { Write-Warning "Smoke finished with property MISSes - send smoke_result.txt back." }

    Write-Host "== Inspector self-test via 3dsmaxbatch =="
    # max_selftest.py ends with rt.messageBox; under 3dsmaxbatch that is non-blocking/ignored.
    # If it hangs or writes no JSON, run it in the GUI instead (see the manual step below).
    Remove-Item $selfJson -ErrorAction SilentlyContinue
    & $batch (Join-Path $Repo "inspector\tools\max_selftest.py") 2>&1 | Tee-Object -FilePath (Join-Path $OutDir "selftest_batch.log")
    $selfOk = Test-Path $selfJson
    Step "Inspector self-test (batch)" $selfOk
    if (-not $selfOk) {
        Write-Host "MANUAL STEP: open 3ds Max, File > New (empty scene), Scripting > Run Script... >"
        Write-Host ("  {0}" -f (Join-Path $Repo "inspector\tools\max_selftest.py"))
        Write-Host "  then re-run this script (or just copy %TEMP%\material_inspector_selftest.json to the zip)."
    }
} else {
    Write-Warning "3dsmaxbatch.exe not found - pass -MaxRoot 'C:\Program Files\Autodesk\3ds Max 2026'. Skipping Max steps."
    Step "MatForge smoke" $false
    Step "Inspector self-test (batch)" $false
}

# --- collect + zip ----------------------------------------------------------
Write-Host "== Collecting =="
foreach ($f in @(
        (Join-Path $Repo "smoke_result.txt"),
        $selfJson,
        (Join-Path $env:TEMP "material_inspector_selftest_tex"))) {
    if (Test-Path $f) { Copy-Item $f $OutDir -Recurse -Force -ErrorAction SilentlyContinue }
}
$logDir = Join-Path $env:LOCALAPPDATA "MeasuredLight\logs"
if (Test-Path $logDir) { Copy-Item $logDir (Join-Path $OutDir "inspector_logs") -Recurse -Force -ErrorAction SilentlyContinue }
$maxLog = Join-Path $env:LOCALAPPDATA "Autodesk\3dsMax"
if (Test-Path $maxLog) {
    Get-ChildItem $maxLog -Recurse -Filter "*.log" -ErrorAction SilentlyContinue |
        Sort-Object LastWriteTime -Descending | Select-Object -First 3 |
        ForEach-Object { Copy-Item $_.FullName (Join-Path $OutDir ("max_" + $_.Name)) -Force }
}
$summary = $results.GetEnumerator() | ForEach-Object { "{0}: {1}" -f $(if ($_.Value) { "PASS" } else { "FAIL" }), $_.Key }
$summary | Set-Content (Join-Path $OutDir "summary.txt")

$zip = "$OutDir.zip"
Remove-Item $zip -ErrorAction SilentlyContinue
Compress-Archive -Path (Join-Path $OutDir "*") -DestinationPath $zip -Force
Write-Host ""
Write-Host "== SUMMARY =="
$summary | ForEach-Object { Write-Host $_ }
$failed = @($results.Values | Where-Object { -not $_ }).Count
Write-Host ""
Write-Host $(if ($failed -eq 0) { "OVERALL: PASS" } else { "OVERALL: FAIL ($failed step(s))" })
Write-Host ("Send back: {0}" -f $zip)
Write-Host "Then do the manual checks in docs\WINDOWS_READY.md."
exit $(if ($failed -eq 0) { 0 } else { 1 })
