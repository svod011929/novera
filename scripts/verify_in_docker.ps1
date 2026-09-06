# GFORT isolated verify via Docker (no host Python required).
# Does not start the app, does not load production secrets, does not deploy.
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/verify_in_docker.ps1

[CmdletBinding()]
param(
    [string]$Image = "python:3.12-slim"
)

$ErrorActionPreference = "Stop"
$projectRoot = (Resolve-Path (Split-Path -Parent $PSScriptRoot)).Path

$docker = Get-Command docker -ErrorAction SilentlyContinue
if (-not $docker) {
    Write-Host @"
ERROR: Docker is not installed or not on PATH.

Install Docker Desktop, then re-run this script.
Fallback without Docker:
  winget install -e --id Python.Python.3.12
  powershell -ExecutionPolicy Bypass -File scripts/verify_workspace.ps1 -InstallDeps

No production action was performed.
"@
    exit 2
}

Write-Host "GFORT Docker workspace verification"
Write-Host "Root: $projectRoot"
Write-Host "Image: $Image"

# Mount the project read-write only for pip cache inside container /tmp and pytest temp.
# Application code is not modified by this command.
$mount = "${projectRoot}:/app"

$cmd = @'
set -euo pipefail
cd /app
echo "Python: $(python --version)"
python -m pip install --upgrade pip
python -m pip install -r requirements-dev.txt
python -m compileall -q delta_backend tests main.py
if command -v bash >/dev/null 2>&1; then
  for script in deploy/*.sh scripts/*.sh; do
    bash -n "$script"
  done
fi
pytest -q
echo "Workspace syntax checks and tests passed. No production action was performed."
'@

docker run --rm `
  -v $mount `
  -w /app `
  -e PYTHONDONTWRITEBYTECODE=1 `
  -e PYTHONUNBUFFERED=1 `
  $Image `
  bash -lc $cmd

exit $LASTEXITCODE
