# scripts/build_windows.ps1
# PowerShell build script - Windows only.
#
# Requirements:
#   1. Python 3.12 in PATH
#   2. ffmpeg.exe downloaded to packaging/bin/ffmpeg.exe
#
# Run:
#   pwsh scripts/build_windows.ps1

$ErrorActionPreference = "Stop"
$RepoRoot = (Get-Item -Path "$PSScriptRoot/..").FullName
Set-Location $RepoRoot

Write-Host "[1/5] Verifying ffmpeg.exe..." -ForegroundColor Cyan
$FFmpegPath = Join-Path $RepoRoot "packaging/bin/ffmpeg.exe"
if (-not (Test-Path $FFmpegPath)) {
    Write-Error "Missing $FFmpegPath. Download from https://www.gyan.dev/ffmpeg/builds/"
}

Write-Host "[2/5] Setting up venv..." -ForegroundColor Cyan
if (-not (Test-Path "$RepoRoot/.venv-build")) {
    python -m venv "$RepoRoot/.venv-build"
}
& "$RepoRoot/.venv-build/Scripts/Activate.ps1"

Write-Host "[3/5] Installing dependencies..." -ForegroundColor Cyan
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt

Write-Host "[4/5] Cleaning previous build..." -ForegroundColor Cyan
Remove-Item -Recurse -Force "$RepoRoot/build", "$RepoRoot/dist" -ErrorAction SilentlyContinue

Write-Host "[5/5] Running PyInstaller..." -ForegroundColor Cyan
python -m PyInstaller --noconfirm "$RepoRoot/packaging/opencut.spec"

$ExePath = Join-Path $RepoRoot "dist/OpenCut/OpenCut.exe"
if (Test-Path $ExePath) {
    Write-Host "Build success: $ExePath" -ForegroundColor Green
} else {
    Write-Error "Build did not produce $ExePath"
}
