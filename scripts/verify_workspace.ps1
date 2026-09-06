# GFORT local workspace verification (Windows PowerShell)
# Safe local checks only. Never touches production, secrets, or live payouts.
# Usage (from repo root or any cwd):
#   powershell -ExecutionPolicy Bypass -File scripts/verify_workspace.ps1

[CmdletBinding()]
param(
    [switch]$SkipTests,
    [switch]$InstallDeps
)

$ErrorActionPreference = "Stop"
$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

function Resolve-Python {
    $candidates = @()
    if ($env:GFORT_PYTHON) { $candidates += $env:GFORT_PYTHON }
    $candidates += @(
        "$env:LOCALAPPDATA\Programs\Python\Python312\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python313\python.exe",
        "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe",
        "$env:ProgramFiles\Python312\python.exe",
        "$env:ProgramFiles\Python311\python.exe",
        "C:\Python312\python.exe"
    )
    foreach ($path in $candidates) {
        if ($path -and (Test-Path $path)) {
            return (Resolve-Path $path).Path
        }
    }
    foreach ($name in @("python3", "python")) {
        $cmd = Get-Command $name -ErrorAction SilentlyContinue
        if (-not $cmd) { continue }
        $source = [string]$cmd.Source
        # Skip Windows Store stubs that open the Microsoft Store.
        if ($source -match "WindowsApps\\python") { continue }
        return $source
    }
    return $null
}

Write-Host "GFORT local workspace verification (PowerShell)"
Write-Host "Root: $projectRoot"

$python = Resolve-Python
if (-not $python) {
    Write-Host @"
ERROR: No usable Python 3.11+ found.

Install one of:
  1) winget install -e --id Python.Python.3.12
  2) Docker Desktop, then: powershell -File scripts/verify_in_docker.ps1
  3) Git Bash / WSL, then: bash scripts/verify_workspace.sh

No production action was performed.
"@
    exit 2
}

$pyVersion = & $python --version 2>&1
Write-Host "Python: $pyVersion ($python)"

if ($InstallDeps) {
    Write-Host "Installing requirements-dev.txt into the active interpreter..."
    & $python -m pip install --upgrade pip
    & $python -m pip install -r requirements-dev.txt
}

Write-Host "compileall..."
& $python -m compileall -q delta_backend tests main.py
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

$bash = Get-Command bash -ErrorAction SilentlyContinue
if ($bash) {
    Write-Host "bash -n deploy/*.sh scripts/*.sh..."
    Get-ChildItem deploy\*.sh, scripts\*.sh | ForEach-Object {
        & bash -n $_.FullName
        if ($LASTEXITCODE -ne 0) { throw "bash -n failed for $($_.Name)" }
    }
} else {
    Write-Host "bash not found; shell syntax check skipped (use Docker/WSL path for full parity)."
}

if ($SkipTests) {
    Write-Host "Tests skipped by -SkipTests."
    Write-Host "Workspace syntax checks passed. No production action was performed."
    exit 0
}

$depsOk = $true
foreach ($mod in @("fastapi", "aiogram", "web3", "pytest")) {
    & $python -c "import $mod" 2>$null
    if ($LASTEXITCODE -ne 0) {
        $depsOk = $false
        Write-Host "Missing dependency module: $mod"
    }
}

if (-not $depsOk) {
    Write-Host "Python dependencies are incomplete; pytest skipped."
    Write-Host "Fix: powershell -ExecutionPolicy Bypass -File scripts/verify_workspace.ps1 -InstallDeps"
    Write-Host "Or:  powershell -File scripts/verify_in_docker.ps1"
    Write-Host "Workspace syntax checks passed. No production action was performed."
    exit 0
}

Write-Host "pytest -q..."
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }

Write-Host "Workspace syntax checks and tests passed. No production action was performed."
