<#
  Material Inspector installer for 3ds Max (Windows).

  Run from the repository root in PowerShell:
      powershell -ExecutionPolicy Bypass -File tools\install.ps1            # current user
      powershell -ExecutionPolicy Bypass -File tools\install.ps1 -AllUsers  # needs admin

  For every installed 3ds Max 2025+ it:
    1. installs numpy + Pillow into that 3ds Max's bundled Python (per-user),
    2. builds dist\MaterialInspector.bundle with that Python,
    3. copies the bundle into the Autodesk ApplicationPlugins folder.
  Restart 3ds Max afterwards. Paths are the usual defaults; UNVERIFIED on your machine.
#>
param([switch]$AllUsers)
$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$maxDirs = Get-ChildItem "C:\Program Files\Autodesk" -Directory -Filter "3ds Max 20*" -ErrorAction SilentlyContinue |
           Where-Object { [int]($_.Name -replace '\D','') -ge 2025 }
if (-not $maxDirs) { Write-Error "No 3ds Max 2025+ found under C:\Program Files\Autodesk" }

$built = $false
foreach ($d in $maxDirs) {
    $py = Get-ChildItem $d.FullName -Recurse -Filter python.exe -Depth 2 -ErrorAction SilentlyContinue |
          Select-Object -First 1
    if (-not $py) { Write-Warning "$($d.Name): bundled python.exe not found, skipping"; continue }
    Write-Host "$($d.Name): $($py.FullName)"
    & $py.FullName -m ensurepip --user 2>$null | Out-Null
    & $py.FullName -m pip install --user --upgrade numpy pillow
    if (-not $built) {
        Push-Location $repo; & $py.FullName tools\build_bundle.py; Pop-Location; $built = $true
    }
}
if (-not $built) { Write-Error "Could not build the bundle (no usable 3ds Max Python)." }

$target = if ($AllUsers) { Join-Path $env:ProgramData "Autodesk\ApplicationPlugins" }
          else { Join-Path $env:APPDATA "Autodesk\ApplicationPlugins" }
New-Item -ItemType Directory -Force -Path $target | Out-Null
$dest = Join-Path $target "MaterialInspector.bundle"
if (Test-Path $dest) { Remove-Item $dest -Recurse -Force }
Copy-Item (Join-Path $repo "dist\MaterialInspector.bundle") $dest -Recurse
Write-Host "Installed to $dest - restart 3ds Max, then Customize > Customize User Interface > category 'Measured Light'."
