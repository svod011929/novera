# Apply a non-secret brand profile onto a staged bootstrap payload (and stub text).
# Dot-source from build_bootstrap_installer.ps1. Never writes bot tokens, RPC/WSS,
# seed phrases, or encryption keys into the payload.

Set-StrictMode -Version Latest

function Resolve-BrandProfile {
    param(
        [Parameter(Mandatory = $true)][string]$Root,
        [Parameter(Mandatory = $true)][string]$BrandProfile
    )

    $ProfilesRoot = Join-Path $Root "_owner_inputs\BRAND_PROFILES"
    $ProfileJson = $null
    $ProfileDir = $null

    if (Test-Path -LiteralPath $BrandProfile -PathType Leaf) {
        $ProfileJson = (Resolve-Path -LiteralPath $BrandProfile).Path
        $ProfileDir = Split-Path -Parent $ProfileJson
    } elseif (Test-Path -LiteralPath (Join-Path $BrandProfile "profile.json") -PathType Leaf) {
        $ProfileDir = (Resolve-Path -LiteralPath $BrandProfile).Path
        $ProfileJson = Join-Path $ProfileDir "profile.json"
    } else {
        $Candidate = Join-Path $ProfilesRoot $BrandProfile
        $ProfileJson = Join-Path $Candidate "profile.json"
        if (-not (Test-Path -LiteralPath $ProfileJson -PathType Leaf)) {
            throw "Brand profile not found: $BrandProfile (expected $ProfileJson)"
        }
        $ProfileDir = $Candidate
    }

    $Raw = Get-Content -LiteralPath $ProfileJson -Raw -Encoding UTF8
    $Profile = $Raw | ConvertFrom-Json
    Assert-BrandProfileSafe -Profile $Profile -ProfileJson $ProfileJson
    return [pscustomobject]@{
        Data = $Profile
        Dir  = $ProfileDir
        Json = $ProfileJson
    }
}

function Assert-BrandProfileSafe {
    param(
        [Parameter(Mandatory = $true)]$Profile,
        [Parameter(Mandatory = $true)][string]$ProfileJson
    )

    foreach ($Required in @("id", "product_name", "tagline", "default_domain", "default_ipv4", "default_owner_id")) {
        $HasField = $Profile.PSObject.Properties.Name -contains $Required
        if (-not $HasField -or [string]::IsNullOrWhiteSpace([string]$Profile.$Required)) {
            throw "Brand profile missing required field '$Required': $ProfileJson"
        }
    }

    $Id = [string]$Profile.id
    if ($Id -notmatch '^[a-z0-9][a-z0-9_-]{1,32}$') {
        throw "Brand profile id must be lowercase slug [a-z0-9_-]{2,33}: $Id"
    }

    $Product = [string]$Profile.product_name
    if ($Product -notmatch '^[A-Za-z0-9][A-Za-z0-9 _.+-]{1,40}$') {
        throw "product_name has invalid characters: $Product"
    }

    if ([string]$Profile.default_domain -notmatch '^[A-Za-z0-9.-]+$') {
        throw "default_domain is invalid"
    }
    if ([string]$Profile.default_ipv4 -notmatch '^[0-9]{1,3}(\.[0-9]{1,3}){3}$') {
        throw "default_ipv4 is invalid"
    }
    if ([string]$Profile.default_owner_id -notmatch '^[0-9]{5,20}$') {
        throw "default_owner_id must be a numeric Telegram id"
    }

    $Forbidden = @(
        "bot_token", "BOT_TOKEN", "seed_phrase", "SEED_PHRASE", "seed",
        "bsc_rpc_url", "BSC_RPC_URL", "bsc_wss_url", "BSC_WSS_URL",
        "runtime_config_key", "private_key", "mnemonic", "api_key"
    )
    foreach ($Name in $Profile.PSObject.Properties.Name) {
        if ($Forbidden -contains $Name) {
            throw "Brand profile must not contain secret field '$Name'"
        }
    }

    $Retired = "G" + "FORT"
    $Blob = ($Profile | ConvertTo-Json -Depth 8)
    if ($Blob -match [regex]::Escape($Retired)) {
        throw "Brand profile must not contain the retired public brand"
    }
}

function Get-BrandAssetPath {
    param(
        [Parameter(Mandatory = $true)][string]$ProfileDir,
        [AllowEmptyString()]
        [Parameter(Mandatory = $false)][string]$RelativeOrEmpty = ""
    )
    if ([string]::IsNullOrWhiteSpace($RelativeOrEmpty)) { return $null }
    $Path = Join-Path $ProfileDir ($RelativeOrEmpty -replace "/", "\")
    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        throw "Brand asset missing: $Path"
    }
    return $Path
}

function Set-CssCustomProperty {
    param(
        [Parameter(Mandatory = $true)][string]$Css,
        [Parameter(Mandatory = $true)][string]$Name,
        [Parameter(Mandatory = $true)][string]$Value
    )
    $EscapedName = [regex]::Escape($Name)
    $Pattern = "(?m)(--$EscapedName\s*:\s*)([^;]+)(;)"
    if ($Css -notmatch $Pattern) {
        throw "design-tokens.css is missing custom property --$Name"
    }
    return [regex]::Replace($Css, $Pattern, { param($Match) $Match.Groups[1].Value + $Value + $Match.Groups[3].Value }, 1)
}

function Apply-BrandColorsToTokens {
    param(
        [Parameter(Mandatory = $true)][string]$TokensPath,
        [Parameter(Mandatory = $true)]$Colors,
        [Parameter(Mandatory = $true)]$Utf8NoBom
    )
    if ($null -eq $Colors) { return }
    $Css = [System.IO.File]::ReadAllText($TokensPath)
    foreach ($Prop in $Colors.PSObject.Properties) {
        $Name = [string]$Prop.Name
        $Value = [string]$Prop.Value
        if ([string]::IsNullOrWhiteSpace($Value)) { continue }
        $Css = Set-CssCustomProperty -Css $Css -Name $Name -Value $Value
    }
    [System.IO.File]::WriteAllText($TokensPath, $Css, $Utf8NoBom)
}

function Apply-BrandFontsToTokens {
    param(
        [Parameter(Mandatory = $true)][string]$TokensPath,
        [Parameter(Mandatory = $true)]$Fonts,
        [Parameter(Mandatory = $true)]$Utf8NoBom
    )
    if ($null -eq $Fonts) { return }
    $Css = [System.IO.File]::ReadAllText($TokensPath)
    if ($Fonts.PSObject.Properties.Name -contains "display" -and -not [string]::IsNullOrWhiteSpace([string]$Fonts.display)) {
        $Css = Set-CssCustomProperty -Css $Css -Name "font-display" -Value ([string]$Fonts.display)
    }
    if ($Fonts.PSObject.Properties.Name -contains "body" -and -not [string]::IsNullOrWhiteSpace([string]$Fonts.body)) {
        $Css = Set-CssCustomProperty -Css $Css -Name "font-body" -Value ([string]$Fonts.body)
    }
    [System.IO.File]::WriteAllText($TokensPath, $Css, $Utf8NoBom)
}

function Apply-PublicProductRename {
    param(
        [Parameter(Mandatory = $true)][string]$PayloadDir,
        [Parameter(Mandatory = $true)][string]$FromName,
        [Parameter(Mandatory = $true)][string]$ToName,
        [Parameter(Mandatory = $true)][string]$ToTitle,
        [Parameter(Mandatory = $true)]$Utf8NoBom
    )

    if ($FromName -eq $ToName) { return }

    $TextExtensions = @(
        ".py", ".js", ".css", ".html", ".svg", ".json", ".md", ".txt",
        ".sh", ".ps1", ".yml", ".yaml", ".toml", ".ini", ".cfg", ".example"
    )
    # Keep technical identifiers: NOVERA_BOT_TOKEN_FILE, __NOVERA_BOOTSTRAP_PAYLOAD__,
    # novera-brand.css paths. Only rewrite standalone public product tokens.
    $FromTitle = $FromName.Substring(0, 1) + $FromName.Substring(1).ToLowerInvariant()
    $TokenPattern = '(?<![A-Za-z0-9_])' + [regex]::Escape($FromName) + '(?![A-Za-z0-9_])'
    $TitlePattern = '(?<![A-Za-z0-9_])' + [regex]::Escape($FromTitle) + '(?![A-Za-z0-9_])'

    Get-ChildItem -LiteralPath $PayloadDir -Recurse -File -Force |
        Where-Object {
            ($TextExtensions -contains $_.Extension.ToLowerInvariant() -or
             $_.Name -in @("Dockerfile", "Caddyfile.vps")) -and
            $_.Name -notlike "*BOOTSTRAP_INSTALLER*"
        } |
        ForEach-Object {
            $Text = [System.IO.File]::ReadAllText($_.FullName)
            $Clean = [regex]::Replace($Text, $TokenPattern, $ToName)
            if ($ToTitle -and $ToTitle -ne $ToName) {
                $Clean = [regex]::Replace($Clean, $TitlePattern, $ToTitle)
            }
            if ($Clean -ne $Text) {
                [System.IO.File]::WriteAllText($_.FullName, $Clean, $Utf8NoBom)
            }
        }
}

function Apply-BrandProfileToPayload {
    param(
        [Parameter(Mandatory = $true)]$ResolvedProfile,
        [Parameter(Mandatory = $true)][string]$PayloadDir,
        [Parameter(Mandatory = $true)]$Utf8NoBom
    )

    $Profile = $ResolvedProfile.Data
    $ProfileDir = $ResolvedProfile.Dir
    $Product = [string]$Profile.product_name
    $Tagline = [string]$Profile.tagline
    $Title = if ($Profile.PSObject.Properties.Name -contains "product_name_title" -and
                -not [string]::IsNullOrWhiteSpace([string]$Profile.product_name_title)) {
        [string]$Profile.product_name_title
    } else {
        $Product.Substring(0, 1).ToUpperInvariant() + $Product.Substring(1).ToLowerInvariant()
    }

    $Assets = $Profile.assets
    if ($null -ne $Assets) {
        $LogoRel = if ($Assets.PSObject.Properties.Name -contains "logo") { [string]$Assets.logo } else { "" }
        $MarkRel = if ($Assets.PSObject.Properties.Name -contains "mark") { [string]$Assets.mark } else { $LogoRel }
        $BoardRel = if ($Assets.PSObject.Properties.Name -contains "board") { [string]$Assets.board } else { "" }

        $LogoSrc = Get-BrandAssetPath -ProfileDir $ProfileDir -RelativeOrEmpty $LogoRel
        if ($LogoSrc) {
            $BrandDir = Join-Path $PayloadDir "frontend\assets\brand"
            New-Item -ItemType Directory -Force -Path $BrandDir | Out-Null
            Copy-Item -LiteralPath $LogoSrc -Destination (Join-Path $BrandDir "novera-logo.jpg") -Force
            $MarkSrc = Get-BrandAssetPath -ProfileDir $ProfileDir -RelativeOrEmpty $MarkRel
            if (-not $MarkSrc) { $MarkSrc = $LogoSrc }
            Copy-Item -LiteralPath $MarkSrc -Destination (Join-Path $BrandDir "novera-mark.jpg") -Force
        }

        $BoardSrc = Get-BrandAssetPath -ProfileDir $ProfileDir -RelativeOrEmpty $BoardRel
        if ($BoardSrc) {
            $BrandDir = Join-Path $PayloadDir "frontend\assets\brand"
            New-Item -ItemType Directory -Force -Path $BrandDir | Out-Null
            Copy-Item -LiteralPath $BoardSrc -Destination (Join-Path $BrandDir "novera-board.jpg") -Force
        }
    }

    $TokensPath = Join-Path $PayloadDir "frontend\assets\design-tokens.css"
    if (-not (Test-Path -LiteralPath $TokensPath -PathType Leaf)) {
        throw "design-tokens.css missing in payload"
    }
    if ($Profile.PSObject.Properties.Name -contains "colors") {
        Apply-BrandColorsToTokens -TokensPath $TokensPath -Colors $Profile.colors -Utf8NoBom $Utf8NoBom
    }
    if ($Profile.PSObject.Properties.Name -contains "fonts") {
        Apply-BrandFontsToTokens -TokensPath $TokensPath -Fonts $Profile.fonts -Utf8NoBom $Utf8NoBom
    }

    $IndexPath = Join-Path $PayloadDir "frontend\index.html"
    if (Test-Path -LiteralPath $IndexPath -PathType Leaf) {
        $Html = [System.IO.File]::ReadAllText($IndexPath)
        $Html = [regex]::Replace(
            $Html,
            '(?s)(<span><strong>)NOVERA(</strong><small>)Digital Capital(</small></span>)',
            { param($Match) $Match.Groups[1].Value + $Product + $Match.Groups[2].Value + $Tagline + $Match.Groups[3].Value }
        )
        if ($Profile.PSObject.Properties.Name -contains "theme_color" -and
            -not [string]::IsNullOrWhiteSpace([string]$Profile.theme_color)) {
            $Theme = [string]$Profile.theme_color
            $Html = [regex]::Replace(
                $Html,
                'name="theme-color" content="[^"]*"',
                ('name="theme-color" content="{0}"' -f $Theme)
            )
        }
        [System.IO.File]::WriteAllText($IndexPath, $Html, $Utf8NoBom)
    }

    Apply-PublicProductRename `
        -PayloadDir $PayloadDir `
        -FromName "NOVERA" `
        -ToName $Product `
        -ToTitle $Title `
        -Utf8NoBom $Utf8NoBom

    $Audit = [ordered]@{
        id                 = [string]$Profile.id
        product_name       = $Product
        product_name_title = $Title
        tagline            = $Tagline
        default_domain     = [string]$Profile.default_domain
        default_ipv4       = [string]$Profile.default_ipv4
        default_owner_id   = [string]$Profile.default_owner_id
        contains_secrets   = $false
        note               = "Public branding only. Bot token, RPC/WSS, seed and runtime key are collected on the VPS."
    }
    $AuditPath = Join-Path $PayloadDir "deploy\BRAND_PROFILE.json"
    $AuditJson = ($Audit | ConvertTo-Json -Depth 4) + "`n"
    [System.IO.File]::WriteAllText($AuditPath, $AuditJson, $Utf8NoBom)
}

function Apply-BrandProfileToStubText {
    param(
        [Parameter(Mandatory = $true)]$ResolvedProfile,
        [Parameter(Mandatory = $true)][string]$StubText
    )

    $Profile = $ResolvedProfile.Data
    $Product = [string]$Profile.product_name
    $Domain = [string]$Profile.default_domain
    $Ip = [string]$Profile.default_ipv4
    $Owner = [string]$Profile.default_owner_id

    # Keep technical markers/env names (__NOVERA_BOOTSTRAP_PAYLOAD__, NOVERA_BOT_TOKEN_FILE).
    # Public product label is APP_NAME; defaults come from the brand profile.
    $StubText = $StubText -replace '(?m)^APP_NAME="[^"]*"', ('APP_NAME="{0}"' -f $Product)
    $StubText = $StubText -replace '(?m)^DEFAULT_DOMAIN="[^"]*"', ('DEFAULT_DOMAIN="{0}"' -f $Domain)
    $StubText = $StubText -replace '(?m)^DEFAULT_IPV4="[^"]*"', ('DEFAULT_IPV4="{0}"' -f $Ip)
    $StubText = $StubText -replace '(?m)^DEFAULT_OWNER_ID="[^"]*"', ('DEFAULT_OWNER_ID="{0}"' -f $Owner)

    return $StubText
}
