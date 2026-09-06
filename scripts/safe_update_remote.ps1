# Pack current tree (no secrets/state) and promote on the live VPS via deploy/safe-update.sh.
[CmdletBinding()]
param(
    [ValidateSet("frontend", "full")]
    [string]$Mode = "frontend",
    [string]$HostName = "170.168.91.129",
    [string]$UserName = "root",
    [string]$IdentityFile = "",
    [string]$Domain = "bnbb.tech"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $IdentityFile) {
    $IdentityFile = Join-Path $env:USERPROFILE ".ssh\novera_vps_rsa"
}
if (-not (Test-Path -LiteralPath $IdentityFile)) {
    throw "SSH identity not found: $IdentityFile"
}

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$Work = Join-Path $env:TEMP "novera-safe-update-$Stamp"
$PayloadDir = Join-Path $Work "payload"
$TarPath = Join-Path $Work "payload.tar.gz"
New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null

$Include = @(
    "delta_backend",
    "frontend",
    "deploy",
    "scripts",
    "tests",
    "secrets\README.md",
    "Dockerfile",
    ".dockerignore",
    "compose.vps.yml",
    "compose.testnet.yml",
    "main.py",
    "requirements.txt",
    "requirements-dev.txt",
    "pyproject.toml",
    "README.md",
    "AGENTS.md",
    ".env.vps.example"
)

foreach ($item in $Include) {
    $src = Join-Path $Root $item
    if (-not (Test-Path -LiteralPath $src)) { continue }
    $dest = Join-Path $PayloadDir $item
    $destParent = Split-Path -Parent $dest
    if (-not (Test-Path -LiteralPath $destParent)) {
        New-Item -ItemType Directory -Force -Path $destParent | Out-Null
    }
    if ((Get-Item -LiteralPath $src).PSIsContainer) {
        Copy-Item -LiteralPath $src -Destination $dest -Recurse -Force
    } else {
        Copy-Item -LiteralPath $src -Destination $dest -Force
    }
}

# Strip accidental secrets/state if present under copied trees.
@(
    (Join-Path $PayloadDir "data"),
    (Join-Path $PayloadDir "backups"),
    (Join-Path $PayloadDir ".env"),
    (Join-Path $PayloadDir "secrets\bot_token.txt"),
    (Join-Path $PayloadDir "secrets\runtime_config_key.txt")
) | ForEach-Object {
    if (Test-Path -LiteralPath $_) { Remove-Item -LiteralPath $_ -Recurse -Force }
}

& tar -czf $TarPath -C $PayloadDir .
if ($LASTEXITCODE -ne 0) { throw "Failed to create payload archive" }

$RemoteTar = "/tmp/novera-safe-update-$Stamp.tar.gz"
$RemoteDir = "/tmp/novera-safe-update-$Stamp"
$SshArgs = @(
    "-i", $IdentityFile,
    "-o", "BatchMode=yes",
    "-o", "StrictHostKeyChecking=accept-new",
    "-o", "ConnectTimeout=20"
)

Write-Host "[SAFE-UPDATE] Uploading payload ($Mode)..."
& scp @SshArgs $TarPath "${UserName}@${HostName}:$RemoteTar"
if ($LASTEXITCODE -ne 0) { throw "scp failed" }

$RemoteScript = @"
set -euo pipefail
rm -rf '$RemoteDir'
mkdir -p '$RemoteDir'
tar -xzf '$RemoteTar' -C '$RemoteDir'
chmod 0755 '$RemoteDir'/deploy/*.sh
bash '$RemoteDir'/deploy/safe-update.sh --source '$RemoteDir' --mode '$Mode'
bash /opt/gfort/current/deploy/post-update-check.sh '$Domain'
rm -rf '$RemoteDir' '$RemoteTar'
"@

Write-Host "[SAFE-UPDATE] Running remote promote..."
$RemoteScript | & ssh @SshArgs "${UserName}@${HostName}" "bash -s"
if ($LASTEXITCODE -ne 0) { throw "Remote safe-update failed" }

Remove-Item -Recurse -Force $Work -ErrorAction SilentlyContinue
Write-Host "[SAFE-UPDATE] OK mode=$Mode host=$HostName"
