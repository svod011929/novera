# Build a self-contained GFORT/NOVERA release-candidate installer from the
# current working tree. Never embeds secrets. Never installs to production.
#
# Usage:
#   powershell -ExecutionPolicy Bypass -File scripts/build_release_candidate.ps1
#
# Output:
#   _cursor_output/releases/GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_<stamp>.sh
#   _cursor_output/releases/*.sha256
#   _cursor_output/releases/PAYLOAD_MANIFEST.txt

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
$ReleaseName = "GFORT_FINAL_FULL_INSTALLER_V10_6_RC_NOVERA_$Stamp"
$Marker = "__GFORT_FINAL_V10_6_RC_NOVERA_PAYLOAD__"
$RefInstaller = Join-Path $Root "_reference\INSTALLERS\GFORT_FINAL_FULL_INSTALLER_V10_6_ADMIN_CONTROLS.sh"
$Work = Join-Path $env:TEMP "gfort-rc-$Stamp"
$PayloadDir = Join-Path $Work "payload"
$TarPath = Join-Path $Work "payload.tar.gz"
$StubPath = Join-Path $Work "stub.sh"
$InstallerPath = Join-Path $OutDir "$ReleaseName.sh"
$B64Path = Join-Path $Work "payload.b64"

if (-not (Test-Path $RefInstaller)) {
    throw "Reference installer not found: $RefInstaller"
}

New-Item -ItemType Directory -Force -Path $OutDir | Out-Null
New-Item -ItemType Directory -Force -Path $PayloadDir | Out-Null

Write-Host "[RC] Extracting installer stub from V10.6 reference..."
$refLines = Get-Content -LiteralPath $RefInstaller -Encoding UTF8
$markerIndex = -1
for ($i = 0; $i -lt $refLines.Count; $i++) {
    if ($refLines[$i] -match '^__GFORT_FINAL_.*PAYLOAD__$') {
        $markerIndex = $i
        break
    }
}
if ($markerIndex -lt 0) { throw "Payload marker not found in reference installer" }
$stub = $refLines[0..($markerIndex - 1)]

Write-Host "[RC] Patching stub for NOVERA RC (hashes, brand, marker)..."
$ApiHash = (Get-FileHash -Algorithm SHA256 (Join-Path $Root "delta_backend\api.py")).Hash.ToLower()
$RepoHash = (Get-FileHash -Algorithm SHA256 (Join-Path $Root "delta_backend\repository.py")).Hash.ToLower()

$patched = New-Object System.Collections.Generic.List[string]
foreach ($line in $stub) {
    $out = $line
    $out = $out -replace '__GFORT_FINAL_V10_6_PAYLOAD__', $Marker
    $out = $out -replace 'PAYLOAD_MARKER="__GFORT_FINAL_V10_6_PAYLOAD__"', "PAYLOAD_MARKER=`"$Marker`""
    $out = $out -replace 'RELEASE_ID="v10\.6-\$STAMP"', 'RELEASE_ID="v10.6-rc-novera-$STAMP"'
    $out = $out -replace 'check_hash ace6693e4d4c17f4ed345c3c1f15b50fe29f9d1cb596b2b0104666f60029fab0 delta_backend/api.py', "check_hash $ApiHash delta_backend/api.py"
    $out = $out -replace 'check_hash c03da6f5be8d043507594d2b5425f2415e97e20087337622d168df88ccf51563 delta_backend/repository.py', "check_hash $RepoHash delta_backend/repository.py"
    $out = $out -replace "grep -Fq 'GFORT \| DIGITAL ARBITRAGE ECOSYSTEM' delta_backend/launcher.py", "grep -Fq 'NOVERA | DIGITAL CAPITAL ECOSYSTEM' delta_backend/launcher.py"
    $out = $out -replace 'Formatted /start message is missing\.', 'Formatted NOVERA /start message is missing.'
    $out = $out -replace "if \[\[ `"\`$body`" == \*'GFORT'\* && `"\`$body`" == \*'teamReferralIncome'\* && `"\`$body`" == \*'profitCalculator'\* \]\]", "if [[ `"`$body`" == *'NOVERA'* && `"`$body`" == *'teamReferralIncome'* && `"`$body`" == *'profitCalculator'* ]]"
    $out = $out -replace 'Public GFORT Mini App and API', 'Public NOVERA Mini App and API'
    $out = $out -replace 'Public GFORT Mini App did not become fully ready\.', 'Public NOVERA Mini App did not become fully ready.'
    $out = $out -replace 'V10\.6 admin code matches the tested build; signer, blockchain, payout and safety services remain byte-identical to V10\.5', 'V10.6-RC-NOVERA critical hashes match this candidate; signer/blockchain/payout/safety remain byte-identical to V10.5'
    $patched.Add($out) | Out-Null
}

# Append RC-specific self-tests before "main "$@"".
$extraTests = @(
    '  grep -Fq ''X-NOVERA-Session'' delta_backend/api.py || fail "NOVERA session header support is missing."',
    '  grep -Fq ''sanitize_telegram_html'' delta_backend/api.py || fail "Telegram HTML sanitizer is missing."',
    '  grep -Fq ''broadcast_audience_counts'' delta_backend/repository.py || fail "Broadcast audience counts are missing."',
    '  grep -Fq ''queue_broadcast_self_test'' delta_backend/repository.py || fail "Broadcast self-test path is missing."',
    '  grep -Fq ''retry_broadcast'' delta_backend/repository.py || fail "Broadcast retry is missing."',
    '  grep -Fq ''walletImpactLead'' frontend/assets/app.js || fail "Wallet vs payout clarity UI is missing."',
    '  grep -Fq ''design-tokens.css'' frontend/assets/novera-brand.css || fail "NOVERA design tokens are missing."',
    '  test -f frontend/assets/design-tokens.css || fail "design-tokens.css is missing."',
    '  test -f frontend/assets/brand/novera-logo.jpg || fail "NOVERA logo is missing."',
    '  test -f tests/test_financial_regression.py || fail "Financial regression suite is missing."',
    '  test -f tests/test_security_hardening.py || fail "Security hardening suite is missing."'
)

$insertAt = -1
for ($i = 0; $i -lt $patched.Count; $i++) {
    if ($patched[$i] -match '^\s*ok "All V10\.6 preflight checks passed') {
        $insertAt = $i
        break
    }
}
if ($insertAt -ge 0) {
    $patched.Insert($insertAt, '  # I-12 RC self-tests (NOVERA + I-08..I-11 surfaces)')
    $offset = 1
    foreach ($t in $extraTests) {
        $patched.Insert($insertAt + $offset, $t)
        $offset++
    }
}

$patched.Add($Marker) | Out-Null
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllLines($StubPath, $patched.ToArray(), $utf8NoBom)

Write-Host "[RC] Staging payload (no secrets / no reference / no cursor output)..."
$include = @(
    "delta_backend", "frontend", "deploy", "scripts", "tests", "secrets",
    "Dockerfile", "compose.vps.yml", "compose.testnet.yml",
    ".env.vps.example", ".env.testnet.example",
    "main.py", "requirements.txt", "requirements-dev.txt",
    "README.md", "pyproject.toml"
)
# Optional files if present
foreach ($optional in @("LICENSE", "AGENTS.md")) {
    if (Test-Path (Join-Path $Root $optional)) { $include += $optional }
}

foreach ($item in $include) {
    $src = Join-Path $Root $item
    if (-not (Test-Path $src)) { continue }
    $dest = Join-Path $PayloadDir $item
    if (Test-Path $src -PathType Container) {
        New-Item -ItemType Directory -Force -Path $dest | Out-Null
        # Copy tree excluding junk.
        & robocopy $src $dest /E /NFL /NDL /NJH /NJS /NC /NS /NP `
            /XD __pycache__ .pytest_cache .mypy_cache .ruff_cache node_modules .git `
            /XF *.pyc *.pyo .env *.sqlite3 *.sqlite3-* | Out-Null
        if ($LASTEXITCODE -ge 8) { throw "robocopy failed for $item (code $LASTEXITCODE)" }
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path $dest) | Out-Null
        Copy-Item -LiteralPath $src -Destination $dest -Force
    }
}

# secrets: keep README only
$secretsDir = Join-Path $PayloadDir "secrets"
if (Test-Path $secretsDir) {
    Get-ChildItem -LiteralPath $secretsDir -File | Where-Object { $_.Name -ne "README.md" } | Remove-Item -Force
}

# Ensure no .env leaked
Get-ChildItem -LiteralPath $PayloadDir -Recurse -File -Filter ".env" -ErrorAction SilentlyContinue | Remove-Item -Force
Get-ChildItem -LiteralPath $PayloadDir -Recurse -File -Filter "*.sqlite3*" -ErrorAction SilentlyContinue | Remove-Item -Force

Write-Host "[RC] Creating tar.gz payload..."
Push-Location $PayloadDir
try {
    & tar -czf $TarPath *
    if ($LASTEXITCODE -ne 0) { throw "tar failed" }
} finally {
    Pop-Location
}

Write-Host "[RC] Base64-encoding payload..."
$bytes = [System.IO.File]::ReadAllBytes($TarPath)
$b64 = [Convert]::ToBase64String($bytes)
# Wrap at 76 chars like traditional installers
$wrapped = for ($i = 0; $i -lt $b64.Length; $i += 76) {
    $len = [Math]::Min(76, $b64.Length - $i)
    $b64.Substring($i, $len)
}
Set-Content -LiteralPath $B64Path -Value $wrapped -Encoding ascii

Write-Host "[RC] Assembling installer..."
$stubText = Get-Content -LiteralPath $StubPath -Raw -Encoding UTF8
# Ensure stub ends with a newline before payload
if (-not $stubText.EndsWith("`n")) { $stubText += "`n" }
$payloadText = Get-Content -LiteralPath $B64Path -Raw -Encoding ascii
# Use LF line endings for the shell installer
$stubLf = $stubText -replace "`r`n", "`n" -replace "`r", "`n"
$payloadLf = $payloadText -replace "`r`n", "`n" -replace "`r", "`n"
$utf8NoBom = New-Object System.Text.UTF8Encoding $false
[System.IO.File]::WriteAllText($InstallerPath, $stubLf + $payloadLf, $utf8NoBom)

$installerHash = (Get-FileHash -Algorithm SHA256 $InstallerPath).Hash.ToLower()
$tarHash = (Get-FileHash -Algorithm SHA256 $TarPath).Hash.ToLower()
Set-Content -LiteralPath "$InstallerPath.sha256" -Value "$installerHash  $ReleaseName.sh" -Encoding ascii

# Manifest of payload files + hashes for critical paths
$manifest = New-Object System.Collections.Generic.List[string]
$manifest.Add("release=$ReleaseName") | Out-Null
$manifest.Add("built_utc=$Stamp") | Out-Null
$manifest.Add("marker=$Marker") | Out-Null
$manifest.Add("installer_sha256=$installerHash") | Out-Null
$manifest.Add("payload_tar_sha256=$tarHash") | Out-Null
$manifest.Add("contains_secrets=false") | Out-Null
$manifest.Add("") | Out-Null
$critical = @(
    "delta_backend/api.py", "delta_backend/repository.py", "delta_backend/config.py",
    "delta_backend/services/blockchain.py", "delta_backend/services/deposit_monitor.py",
    "delta_backend/services/payouts.py", "delta_backend/services/safety.py",
    "frontend/assets/app.js", "frontend/index.html", "compose.vps.yml", "Dockerfile"
)
foreach ($rel in $critical) {
    $path = Join-Path $PayloadDir ($rel -replace "/", "\")
    $h = (Get-FileHash -Algorithm SHA256 $path).Hash.ToLower()
    $manifest.Add("$h  $rel") | Out-Null
}
$manifestPath = Join-Path $OutDir "PAYLOAD_MANIFEST_$Stamp.txt"
Set-Content -LiteralPath $manifestPath -Value $manifest -Encoding utf8

# Verify: extract payload from the built installer and confirm compose/Dockerfile
Write-Host "[RC] Verifying embedded payload extract..."
$verifyDir = Join-Path $Work "verify"
New-Item -ItemType Directory -Force -Path $verifyDir | Out-Null
$builtLines = [System.IO.File]::ReadAllLines($InstallerPath)
$builtMarker = -1
for ($i = 0; $i -lt $builtLines.Length; $i++) {
    if ($builtLines[$i] -eq $Marker) { $builtMarker = $i; break }
}
if ($builtMarker -lt 0) { throw "Built installer missing payload marker" }
$b64Out = ($builtLines[($builtMarker + 1)..($builtLines.Length - 1)] -join "")
$decoded = [Convert]::FromBase64String($b64Out)
$verifyTar = Join-Path $Work "verify.tar.gz"
[System.IO.File]::WriteAllBytes($verifyTar, $decoded)
Push-Location $verifyDir
try {
    & tar -xzf $verifyTar
    if ($LASTEXITCODE -ne 0) { throw "verify tar extract failed" }
} finally {
    Pop-Location
}
foreach ($must in @("compose.vps.yml", "Dockerfile", ".env.vps.example", "delta_backend\api.py", "frontend\index.html")) {
    if (-not (Test-Path (Join-Path $verifyDir $must))) {
        throw "Extracted payload missing $must"
    }
}
# Confirm no secrets leaked into payload
$leaks = Get-ChildItem -LiteralPath $verifyDir -Recurse -File | Where-Object {
    $_.Name -eq ".env" -or $_.Name -match '\.sqlite3' -or
    ($_.DirectoryName -match '\\secrets\\' -and $_.Name -ne "README.md")
}
if ($leaks) {
    throw ("Secret-like files found in payload: " + ($leaks.FullName -join ", "))
}

# Round-trip hash of extracted critical files must match staged payload
$verifyApi = (Get-FileHash -Algorithm SHA256 (Join-Path $verifyDir "delta_backend\api.py")).Hash.ToLower()
if ($verifyApi -ne $ApiHash) { throw "Extracted api.py hash mismatch" }

Write-Host ""
Write-Host "[RC] OK  installer: $InstallerPath"
Write-Host "[RC] OK  sha256:    $installerHash"
Write-Host "[RC] OK  manifest:  $manifestPath"
Write-Host "[RC] HARD STOP: do not install on production without explicit owner command."

# Cleanup work dir
Remove-Item -LiteralPath $Work -Recurse -Force -ErrorAction SilentlyContinue
