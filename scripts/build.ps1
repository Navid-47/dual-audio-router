# Build Dual Audio Router for Windows (PyInstaller + optional Inno Setup)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)

Set-Location $Root

Write-Host "==> Installing build dependencies..." -ForegroundColor Cyan
pip install -r requirements-dev.txt | Out-Null

Write-Host "==> Cleaning previous build..." -ForegroundColor Cyan
if (Test-Path "dist") { Remove-Item -Recurse -Force "dist" }
if (Test-Path "build") { Remove-Item -Recurse -Force "build" }

Write-Host "==> Running PyInstaller..." -ForegroundColor Cyan
pyinstaller --noconfirm "installer\dual_audio_router.spec"

$AppDir = Join-Path $Root "dist\Dual Audio Router"
if (-not (Test-Path (Join-Path $AppDir "Dual Audio Router.exe"))) {
    Write-Error "PyInstaller build failed — exe not found."
}

Write-Host "==> Portable build ready: $AppDir" -ForegroundColor Green

$Iscc = @(
    "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
    "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
) | Where-Object { Test-Path $_ } | Select-Object -First 1

if ($Iscc) {
    Write-Host "==> Building installer with Inno Setup..." -ForegroundColor Cyan
    $OutputDir = Join-Path $Root "installer\output"
    if (-not (Test-Path $OutputDir)) { New-Item -ItemType Directory -Path $OutputDir | Out-Null }
    & $Iscc (Join-Path $Root "installer\setup.iss")
    Write-Host "==> Installer ready: installer\output\DualAudioRouter-Setup.exe" -ForegroundColor Green
} else {
    Write-Host "Inno Setup not found — skipping installer .exe." -ForegroundColor Yellow
    Write-Host "Install from https://jrsoftware.org/isinfo.php then re-run this script."
    Write-Host "You can still distribute the folder: dist\Dual Audio Router\"
}
