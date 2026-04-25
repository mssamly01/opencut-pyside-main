# Build a Windows opencut-pyside.exe with PyInstaller.
#
# Run from a clean checkout on a Windows host (CI does this via
# .github/workflows/build.yml). The resulting .exe lands in
# packaging\dist\opencut-pyside.exe.

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RepoRoot = Split-Path -Parent $ScriptDir
Set-Location $RepoRoot

python -m pip install --upgrade pip
pip install -r requirements-dev.txt
pip install pyinstaller

Set-Location $ScriptDir
pyinstaller --clean --noconfirm opencut-pyside.spec

Write-Host "Built: $RepoRoot\packaging\dist\opencut-pyside.exe"
