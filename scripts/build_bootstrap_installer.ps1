# Build a one-file NOVERA fresh-VPS bootstrap installer.
# The output never contains bot tokens, RPC/WSS credentials, seed phrases,
# runtime encryption keys, .env files or databases.

[CmdletBinding()]
param(
    [string]$OutDir = ""
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
if (-not $OutDir) {
    $OutDir = Join-Path $Root "_cursor_output\releases"
}

$Stamp = (Get-Date).ToUniversalTime().ToString("yyyyMMdd-HHmmss")
$ReleaseName = "NOVERA_BOOTSTRAP_INSTALLER_$Stamp"
$ReleaseVersion = "v10.6-bootstrap-$Stamp"
$Marker = "__NOVERA_BOOTSTRAP_PAYLOAD__"
$StubPath = Join-Path $Root "deploy\NOVERA_BOOTSTRAP_INSTALLER.stub.sh"
$Work = Join-Path $env:TEMP "novera-bootstrap-$Stamp"
$PayloadDir = Join-Path $Work "payload"
$TarPath = Join-Path $Work "payload.tar.gz"
$InstallerPath = Join-Path $OutDir "$ReleaseName.sh"
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

if (-not (Test-Path -LiteralPath $StubPath -PathType Leaf)) {
    throw "Bootstrap installer stub not found: $StubPath"
}

New-Item -ItemType Directory -Force -Path $OutDir, $PayloadDir | Out-Null

Write-Host "[BOOTSTRAP] Staging payload without runtime state or secrets..."
$Include = @(
    "delta_backend", "frontend", "deploy", "scripts", "tests", "secrets",
    "Dockerfile", ".dockerignore", "compose.vps.yml", "compose.testnet.yml",
    ".env.vps.example", ".env.testnet.example",
    "main.py", "requirements.txt", "requirements-dev.txt",
    "README.md", "pyproject.toml", "AGENTS.md"
)

foreach ($Item in $Include) {
    $Source = Join-Path $Root $Item
    if (-not (Test-Path -LiteralPath $Source)) { continue }
    $Destination = Join-Path $PayloadDir $Item
    if (Test-Path -LiteralPath $Source -PathType Container) {
        New-Item -ItemType Directory -Force -Path $Destination | Out-Null
        & robocopy $Source $Destination /E /NFL /NDL /NJH /NJS /NC /NS /NP `
            /XD __pycache__ .pytest_cache .mypy_cache .ruff_cache node_modules .git `
            /XF *.pyc *.pyo .env *.sqlite3 *.sqlite3-* runtime_config_key.txt | Out-Null
        if ($LASTEXITCODE -ge 8) {
            throw "robocopy failed for $Item (code $LASTEXITCODE)"
        }
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $Destination) | Out-Null
        Copy-Item -LiteralPath $Source -Destination $Destination -Force
    }
}

$PayloadSecrets = Join-Path $PayloadDir "secrets"
if (Test-Path -LiteralPath $PayloadSecrets) {
    Get-ChildItem -LiteralPath $PayloadSecrets -File |
        Where-Object { $_.Name -ne "README.md" } |
        Remove-Item -Force
}

Get-ChildItem -LiteralPath $PayloadDir -Recurse -File -Force |
    Where-Object {
        $_.Name -eq ".env" -or
        $_.Name -match "\.sqlite3(?:-|$)" -or
        $_.Name -eq "runtime_config_key.txt"
    } |
    Remove-Item -Force

$Critical = @(
    "delta_backend/api.py",
    "delta_backend/config.py",
    "delta_backend/repository.py",
    "delta_backend/runtime_secrets.py",
    "delta_backend/services/blockchain.py",
    "delta_backend/services/deposit_monitor.py",
    "delta_backend/services/payouts.py",
    "delta_backend/services/safety.py",
    "frontend/assets/app.js",
    "frontend/index.html",
    "frontend/assets/novera-brand.css",
    "requirements.txt",
    "pyproject.toml",
    "compose.vps.yml",
    "Dockerfile",
    ".dockerignore",
    "deploy/VERSION",
    "deploy/vps-preflight.sh",
    "deploy/backup.sh",
    "deploy/restore-backup.sh"
)
$PayloadManifestLines = foreach ($Relative in $Critical) {
    $Path = Join-Path $PayloadDir ($Relative -replace "/", "\")
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Critical payload file missing: $Relative"
    }
    $Hash = (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
    "$Hash  $Relative"
}
$PayloadManifestPath = Join-Path $PayloadDir "deploy\PAYLOAD_SHA256.txt"
[System.IO.File]::WriteAllText(
    $PayloadManifestPath,
    (($PayloadManifestLines -join "`n") + "`n"),
    $Utf8NoBom
)

# Scan application/deploy payload (fixtures excluded) for token-shaped literals.
$TokenPattern = "\b[0-9]{6,16}:[A-Za-z0-9_-]{30,}\b"
$TokenLeaks = Get-ChildItem -LiteralPath $PayloadDir -Recurse -File |
    Where-Object { $_.FullName -notmatch "\\tests\\" } |
    Select-String -Pattern $TokenPattern
if ($TokenLeaks) {
    throw "Token-shaped literal found outside test fixtures"
}

Write-Host "[BOOTSTRAP] Creating payload archive..."
Push-Location $PayloadDir
try {
    & tar -czf $TarPath -C $PayloadDir .
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
} finally {
    Pop-Location
}
$TarHash = (Get-FileHash -LiteralPath $TarPath -Algorithm SHA256).Hash.ToLowerInvariant()

$Stub = Get-Content -LiteralPath $StubPath -Raw -Encoding UTF8
if (($Stub -split "`r?`n" | Where-Object { $_ -eq $Marker }).Count -ne 1) {
    throw "Bootstrap stub must contain exactly one payload marker"
}
$Stub = $Stub.Replace("__PAYLOAD_TAR_SHA256__", $TarHash)
$Stub = $Stub.Replace("__RELEASE_VERSION__", $ReleaseVersion)
$Stub = $Stub -replace "`r`n", "`n" -replace "`r", "`n"
if (-not $Stub.EndsWith("`n")) { $Stub += "`n" }

$Bytes = [System.IO.File]::ReadAllBytes($TarPath)
$Base64 = [Convert]::ToBase64String($Bytes)
$Wrapped = for ($Index = 0; $Index -lt $Base64.Length; $Index += 76) {
    $Length = [Math]::Min(76, $Base64.Length - $Index)
    $Base64.Substring($Index, $Length)
}
$PayloadText = ($Wrapped -join "`n") + "`n"
[System.IO.File]::WriteAllText($InstallerPath, $Stub + $PayloadText, $Utf8NoBom)

$InstallerHash = (Get-FileHash -LiteralPath $InstallerPath -Algorithm SHA256).Hash.ToLowerInvariant()
[System.IO.File]::WriteAllText(
    "$InstallerPath.sha256",
    "$InstallerHash  $ReleaseName.sh`n",
    [System.Text.Encoding]::ASCII
)

Write-Host "[BOOTSTRAP] Verifying one-file round trip..."
$BuiltLines = [System.IO.File]::ReadAllLines($InstallerPath)
$MarkerIndex = [Array]::IndexOf($BuiltLines, $Marker)
if ($MarkerIndex -lt 0 -or $MarkerIndex -eq $BuiltLines.Length - 1) {
    throw "Built installer payload marker is missing"
}
$Decoded = [Convert]::FromBase64String(
    ($BuiltLines[($MarkerIndex + 1)..($BuiltLines.Length - 1)] -join "")
)
$VerifyTar = Join-Path $Work "verify.tar.gz"
[System.IO.File]::WriteAllBytes($VerifyTar, $Decoded)
if ((Get-FileHash -LiteralPath $VerifyTar -Algorithm SHA256).Hash.ToLowerInvariant() -ne $TarHash) {
    throw "Embedded payload archive hash mismatch"
}
$VerifyDir = Join-Path $Work "verify"
New-Item -ItemType Directory -Force -Path $VerifyDir | Out-Null
& tar -xzf $VerifyTar -C $VerifyDir
if ($LASTEXITCODE -ne 0) { throw "Embedded payload extraction failed" }

foreach ($Relative in $Critical) {
    $Original = Join-Path $PayloadDir ($Relative -replace "/", "\")
    $Extracted = Join-Path $VerifyDir ($Relative -replace "/", "\")
    if (-not (Test-Path -LiteralPath $Extracted -PathType Leaf)) {
        throw "Extracted payload missing: $Relative"
    }
    $Expected = (Get-FileHash -LiteralPath $Original -Algorithm SHA256).Hash
    $Actual = (Get-FileHash -LiteralPath $Extracted -Algorithm SHA256).Hash
    if ($Expected -ne $Actual) {
        throw "Extracted payload hash mismatch: $Relative"
    }
}

$Leaks = Get-ChildItem -LiteralPath $VerifyDir -Recurse -File -Force |
    Where-Object {
        $_.Name -eq ".env" -or
        $_.Name -match "\.sqlite3(?:-|$)" -or
        $_.Name -eq "runtime_config_key.txt" -or
        ($_.DirectoryName -match "\\secrets(?:\\|$)" -and $_.Name -ne "README.md")
    }
if ($Leaks) {
    throw "Secret-like files found in extracted payload"
}

$Manifest = @(
    "release=$ReleaseName",
    "version=$ReleaseVersion",
    "built_utc=$Stamp",
    "installer_sha256=$InstallerHash",
    "payload_tar_sha256=$TarHash",
    "contains_runtime_secrets=false",
    "default_domain=bnbb.tech",
    "default_ipv4=170.168.91.129",
    "default_owner_id=8054710484",
    ""
) + @($PayloadManifestLines)
if (($Manifest | Where-Object { $_ -match "^[a-f0-9]{64}  " }).Count -ne $Critical.Count) {
    throw "External manifest does not contain every critical payload hash"
}
$ManifestPath = Join-Path $OutDir "BOOTSTRAP_MANIFEST_$Stamp.txt"
[System.IO.File]::WriteAllText(
    $ManifestPath,
    (($Manifest -join "`n") + "`n"),
    $Utf8NoBom
)

Write-Host ""
Write-Host "[BOOTSTRAP] OK installer: $InstallerPath"
Write-Host "[BOOTSTRAP] OK SHA-256:  $InstallerHash"
Write-Host "[BOOTSTRAP] OK manifest: $ManifestPath"
Write-Host "[BOOTSTRAP] Bot token will be requested securely at install time."

Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
