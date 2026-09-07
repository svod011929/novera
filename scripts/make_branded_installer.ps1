# Idiot-proof branded installer wizard for non-technical operators (Russian UI).
# Creates a brand profile automatically, then calls build_bootstrap_installer.ps1.
# Secrets (bot token, RPC, seed) are NEVER written into the profile or installer.
#
# Double-click:  СОБРАТЬ_БОТА.bat  (project root)
# Advanced:      scripts\build_bootstrap_installer.ps1 -BrandProfile <id>
# Smoke test:    -NonInteractive with all required params (see -?)

[CmdletBinding()]
param(
    [string]$ProductName = "",
    [string]$Tagline = "",
    [string]$Domain = "",
    [string]$Ipv4 = "",
    [string]$OwnerId = "",
    [string]$LogoPath = "",
    [string]$BoardPath = "",
    [string]$Theme = "",
    [string]$ProfileId = "",
    [switch]$NonInteractive,
    [switch]$Yes
)

$ErrorActionPreference = "Stop"
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$OutputEncoding = [System.Text.Encoding]::UTF8
try { chcp 65001 | Out-Null } catch { }

$Root = Split-Path -Parent $PSScriptRoot
$ProfilesRoot = Join-Path $Root "_owner_inputs\BRAND_PROFILES"
$DropLogoDir = Join-Path $Root "_owner_inputs\ПОЛОЖИТЕ_ЛОГОТИП_СЮДА"
$BuildScript = Join-Path $PSScriptRoot "build_bootstrap_installer.ps1"
$Utf8NoBom = New-Object System.Text.UTF8Encoding $false

function Write-Banner {
    Write-Host ""
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host "   СБОРКА УСТАНОВЩИКА БОТА  (для новичков)" -ForegroundColor Cyan
    Write-Host "============================================================" -ForegroundColor Cyan
    Write-Host ""
    Write-Host " Сейчас спрошу несколько простых вопросов."
    Write-Host " Потом сам создам профиль и соберу файл .sh для сервера."
    Write-Host " Токен бота в файл НЕ попадёт — его введёте уже на сервере."
    Write-Host ""
}

function Read-Answer {
    param(
        [Parameter(Mandatory = $true)][string]$Prompt,
        [string]$Default = "",
        [switch]$Required
    )
    while ($true) {
        if ($Default) {
            $Line = Read-Host "$Prompt  [Enter = $Default]"
        } else {
            $Line = Read-Host $Prompt
        }
        if ([string]::IsNullOrWhiteSpace($Line)) {
            if ($Default) { return $Default }
            if (-not $Required) { return "" }
            Write-Host "  Нужно что-то ввести. Попробуйте ещё раз." -ForegroundColor Yellow
            continue
        }
        return $Line.Trim()
    }
}

function ConvertTo-BrandSlug {
    param([Parameter(Mandatory = $true)][string]$Name)
    $Slug = $Name.ToLowerInvariant()
    $Slug = [regex]::Replace($Slug, '[^a-z0-9]+', '-')
    $Slug = $Slug.Trim('-')
    if ([string]::IsNullOrWhiteSpace($Slug)) { $Slug = "my-bot" }
    if ($Slug.Length -gt 32) { $Slug = $Slug.Substring(0, 32).Trim('-') }
    if ($Slug -notmatch '^[a-z0-9]') { $Slug = "b-$Slug" }
    if ($Slug.Length -lt 2) { $Slug = "$Slug-bot" }
    return $Slug
}

function ConvertTo-ProductCode {
    param([Parameter(Mandatory = $true)][string]$Name)
    # profile.json product_name allows Latin letters/digits and limited punctuation.
    $Clean = $Name.Trim()
    if ($Clean -match '^[A-Za-z0-9][A-Za-z0-9 _.+-]{1,40}$') {
        return $Clean.ToUpperInvariant() -replace '\s+', ''
    }
    $Latin = [regex]::Replace($Clean, '[^A-Za-z0-9 _.+-]', '')
    $Latin = $Latin.Trim()
    if ($Latin -match '^[A-Za-z0-9]') {
        $Code = ($Latin.ToUpperInvariant() -replace '\s+', '')
        if ($Code.Length -gt 40) { $Code = $Code.Substring(0, 40) }
        return $Code
    }
    throw "Имя бота должно быть латиницей, например: AURORA или MyBot (не кириллица)."
}

function ConvertTo-ProductTitle {
    param([Parameter(Mandatory = $true)][string]$ProductCode)
    if ($ProductCode.Length -le 1) { return $ProductCode }
    return $ProductCode.Substring(0, 1).ToUpperInvariant() + $ProductCode.Substring(1).ToLowerInvariant()
}

function Resolve-ThemeKey {
    param([string]$Raw)
    $Key = if ([string]::IsNullOrWhiteSpace($Raw)) { "blue" } else { $Raw.Trim().ToLowerInvariant() }
    # Numbers + English keys only (UI asks for 1-5). Avoid Cyrillic in regex for PS 5.1 encoding safety.
    switch -Regex ($Key) {
        '^(1|blue)$' { return "blue" }
        '^(2|green)$' { return "green" }
        '^(3|purple)$' { return "purple" }
        '^(4|gold)$' { return "gold" }
        '^(5|red)$' { return "red" }
        default {
            throw "Unknown color theme: $Raw (use 1-5 or blue/green/purple/gold/red)"
        }
    }
}

function Get-ThemeColors {
    param([Parameter(Mandatory = $true)][string]$ThemeKey)
    $Bg = "#00050A"
    $Bg2 = "#001428"
    $Text = "#F4FBFF"
    $Muted = "#8FB4D2"
    switch ($ThemeKey) {
        "blue" {
            $Accent = "#5CE1FF"; $Accent2 = "#8B5CFF"; $Hot = "#3AA8FF"
            $Brand = "linear-gradient(115deg,#9AF6FF 0%,#5CE1FF 38%,#4A8CFF 68%,#8B5CFF 100%)"
            $Cta = "linear-gradient(115deg,#5CE1FF 0%,#3AA8FF 48%,#8B5CFF 100%)"
            $Progress = "linear-gradient(90deg,#8B5CFF 0%,#3AA8FF 42%,#5CE1FF 100%)"
        }
        "green" {
            $Accent = "#54F0AA"; $Accent2 = "#2BD4A8"; $Hot = "#3DFFB0"
            $Brand = "linear-gradient(115deg,#B8FFE0 0%,#54F0AA 40%,#2BD4A8 70%,#1FA88A 100%)"
            $Cta = "linear-gradient(115deg,#54F0AA 0%,#3DFFB0 48%,#2BD4A8 100%)"
            $Progress = "linear-gradient(90deg,#1FA88A 0%,#2BD4A8 42%,#54F0AA 100%)"
            $Bg2 = "#001A14"
        }
        "purple" {
            $Accent = "#B794FF"; $Accent2 = "#8B5CFF"; $Hot = "#C45CFF"
            $Brand = "linear-gradient(115deg,#E0D0FF 0%,#B794FF 38%,#8B5CFF 68%,#C45CFF 100%)"
            $Cta = "linear-gradient(115deg,#B794FF 0%,#8B5CFF 48%,#C45CFF 100%)"
            $Progress = "linear-gradient(90deg,#C45CFF 0%,#8B5CFF 42%,#B794FF 100%)"
            $Bg2 = "#12001F"
        }
        "gold" {
            $Accent = "#FFD36A"; $Accent2 = "#FFB020"; $Hot = "#FFE08A"
            $Brand = "linear-gradient(115deg,#FFE9A8 0%,#FFD36A 40%,#FFB020 70%,#E09000 100%)"
            $Cta = "linear-gradient(115deg,#FFD36A 0%,#FFB020 48%,#E09000 100%)"
            $Progress = "linear-gradient(90deg,#E09000 0%,#FFB020 42%,#FFD36A 100%)"
            $Bg2 = "#1A1200"
        }
        "red" {
            $Accent = "#FF6D8A"; $Accent2 = "#FF4D6A"; $Hot = "#FF8FA3"
            $Brand = "linear-gradient(115deg,#FFB3C1 0%,#FF6D8A 40%,#FF4D6A 70%,#E03050 100%)"
            $Cta = "linear-gradient(115deg,#FF6D8A 0%,#FF4D6A 48%,#E03050 100%)"
            $Progress = "linear-gradient(90deg,#E03050 0%,#FF4D6A 42%,#FF6D8A 100%)"
            $Bg2 = "#1A0008"
        }
        default {
            $Msg = "Unhandled theme: $ThemeKey"
            throw $Msg
        }
    }
    return [ordered]@{
        "color-bg"           = $Bg
        "color-bg-2"         = $Bg2
        "color-accent"       = $Accent
        "color-accent-2"     = $Accent2
        "color-accent-hot"   = $Hot
        "color-text"         = $Text
        "color-muted"        = $Muted
        "brand-gradient"     = $Brand
        "cta-gradient"       = $Cta
        "progress-gradient"  = $Progress
    }
}

function Get-ThemeLabelRu {
    param([string]$ThemeKey)
    switch ($ThemeKey) {
        "blue" { return "синий" }
        "green" { return "зелёный" }
        "purple" { return "фиолетовый" }
        "gold" { return "золотой" }
        "red" { return "красный" }
        default { return $ThemeKey }
    }
}

function Test-Ipv4Simple {
    param([string]$Value)
    return [bool]($Value -match '^[0-9]{1,3}(\.[0-9]{1,3}){3}$')
}

function Test-DomainSimple {
    param([string]$Value)
    return [bool]($Value -match '^[A-Za-z0-9.-]+$' -and $Value -match '[A-Za-z]')
}

function Test-OwnerIdSimple {
    param([string]$Value)
    return [bool]($Value -match '^[0-9]{5,20}$')
}

function Find-LogoInFolder {
    param([Parameter(Mandatory = $true)][string]$Folder)
    $Names = @("logo.jpg", "logo.jpeg", "logo.png", "logo.webp")
    foreach ($Name in $Names) {
        $Candidate = Join-Path $Folder $Name
        if (Test-Path -LiteralPath $Candidate -PathType Leaf) { return $Candidate }
    }
    $Any = Get-ChildItem -LiteralPath $Folder -File -ErrorAction SilentlyContinue |
        Where-Object { $_.Extension -match '^\.(jpg|jpeg|png|webp)$' -and $_.Name -notmatch '^PUT_' } |
        Select-Object -First 1
    if ($Any) { return $Any.FullName }
    return $null
}

function Wait-ForLogoDrop {
    param(
        [Parameter(Mandatory = $true)][string]$Folder,
        [int]$TimeoutSec = 600
    )
    New-Item -ItemType Directory -Force -Path $Folder | Out-Null
    $Hint = Join-Path $Folder "ЧИТАЙТЕ_МЕНЯ.txt"
    $HintText = @"
ПОЛОЖИТЕ СЮДА КАРТИНКУ ЛОГОТИПА

Как назвать файл (любой вариант подойдёт):
  logo.jpg
  logo.png

Потом вернитесь в чёрное окно и нажмите Enter.
"@
    [System.IO.File]::WriteAllText($Hint, $HintText, $Utf8NoBom)

    Write-Host ""
    Write-Host " Открываю папку для логотипа:" -ForegroundColor Yellow
    Write-Host "   $Folder"
    Write-Host " Положите туда файл logo.jpg (или logo.png) и вернитесь сюда."
    try {
        Start-Process explorer.exe -ArgumentList $Folder | Out-Null
    } catch {
        Write-Host " (Не удалось открыть проводник — откройте папку вручную.)" -ForegroundColor Yellow
    }

    $Deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ($true) {
        $Found = Find-LogoInFolder -Folder $Folder
        if ($Found) {
            Write-Host " Нашёл логотип: $Found" -ForegroundColor Green
            return $Found
        }
        if ((Get-Date) -gt $Deadline) {
            throw "Логотип так и не появился в папке. Положите logo.jpg и запустите снова."
        }
        Write-Host ""
        $Cont = Read-Host " Уже положили логотип? Нажмите Enter (или напишите путь к файлу)"
        if (-not [string]::IsNullOrWhiteSpace($Cont) -and (Test-Path -LiteralPath $Cont.Trim() -PathType Leaf)) {
            return (Resolve-Path -LiteralPath $Cont.Trim()).Path
        }
        $Found = Find-LogoInFolder -Folder $Folder
        if ($Found) {
            Write-Host " Нашёл логотип: $Found" -ForegroundColor Green
            return $Found
        }
        Write-Host "  Пока не вижу logo.jpg / logo.png в этой папке. Попробуйте ещё раз." -ForegroundColor Yellow
    }
}

function New-BrandProfileFromAnswers {
    param(
        [Parameter(Mandatory = $true)][string]$Id,
        [Parameter(Mandatory = $true)][string]$Product,
        [Parameter(Mandatory = $true)][string]$Title,
        [Parameter(Mandatory = $true)][string]$TaglineValue,
        [Parameter(Mandatory = $true)][string]$DomainValue,
        [Parameter(Mandatory = $true)][string]$IpValue,
        [Parameter(Mandatory = $true)][string]$OwnerValue,
        [Parameter(Mandatory = $true)][string]$ThemeKey,
        [Parameter(Mandatory = $true)][string]$LogoSource,
        [string]$BoardSource = ""
    )

    if ($Id -eq "_template" -or $Id -eq "readme") {
        throw "Нельзя использовать id '$Id'"
    }

    $ProfileDir = Join-Path $ProfilesRoot $Id
    $AssetsDir = Join-Path $ProfileDir "assets"
    New-Item -ItemType Directory -Force -Path $AssetsDir | Out-Null

    $LogoExt = [System.IO.Path]::GetExtension($LogoSource).ToLowerInvariant()
    if ($LogoExt -notmatch '^\.(jpg|jpeg|png|webp)$') {
        throw "Логотип должен быть картинкой (.jpg / .png)."
    }
    $LogoDestName = if ($LogoExt -in @(".jpg", ".jpeg")) { "logo.jpg" } else { "logo$LogoExt" }
    $LogoDest = Join-Path $AssetsDir $LogoDestName
    Copy-Item -LiteralPath $LogoSource -Destination $LogoDest -Force

    $BoardRel = ""
    if (-not [string]::IsNullOrWhiteSpace($BoardSource) -and (Test-Path -LiteralPath $BoardSource -PathType Leaf)) {
        $BoardExt = [System.IO.Path]::GetExtension($BoardSource).ToLowerInvariant()
        $BoardDestName = if ($BoardExt -in @(".jpg", ".jpeg")) { "board.jpg" } else { "board$BoardExt" }
        $BoardDest = Join-Path $AssetsDir $BoardDestName
        Copy-Item -LiteralPath $BoardSource -Destination $BoardDest -Force
        $BoardRel = "assets/$BoardDestName"
    }

    $Colors = Get-ThemeColors -ThemeKey $ThemeKey
    $ThemeColor = [string]$Colors["color-bg"]

    $AssetsObj = [ordered]@{
        logo = "assets/$LogoDestName"
        mark = "assets/$LogoDestName"
    }
    if ($BoardRel) { $AssetsObj["board"] = $BoardRel }

    $Profile = [ordered]@{
        id                 = $Id
        product_name       = $Product
        product_name_title = $Title
        tagline            = $TaglineValue
        theme_color        = $ThemeColor
        default_domain     = $DomainValue
        default_ipv4       = $IpValue
        default_owner_id   = $OwnerValue
        assets             = $AssetsObj
        colors             = $Colors
        fonts              = [ordered]@{
            display = '"Orbitron",ui-sans-serif,system-ui,sans-serif'
            body    = '"Manrope",ui-sans-serif,system-ui,sans-serif'
        }
    }

    $JsonPath = Join-Path $ProfileDir "profile.json"
    $Json = ($Profile | ConvertTo-Json -Depth 8) + "`n"
    [System.IO.File]::WriteAllText($JsonPath, $Json, $Utf8NoBom)
    return $ProfileDir
}

function Write-HugeNextSteps {
    param(
        [Parameter(Mandatory = $true)][string]$InstallerPath,
        [Parameter(Mandatory = $true)][string]$Product,
        [Parameter(Mandatory = $true)][string]$DomainValue,
        [Parameter(Mandatory = $true)][string]$IpValue,
        [Parameter(Mandatory = $true)][string]$OwnerValue
    )

    $FileName = Split-Path -Leaf $InstallerPath
    $Folder = Split-Path -Parent $InstallerPath

    Write-Host ""
    Write-Host "################################################################" -ForegroundColor Green
    Write-Host "#                                                              #" -ForegroundColor Green
    Write-Host "#   ГОТОВО!  УСТАНОВЩИК СОБРАН                                 #" -ForegroundColor Green
    Write-Host "#                                                              #" -ForegroundColor Green
    Write-Host "################################################################" -ForegroundColor Green
    Write-Host ""
    Write-Host " ФАЙЛ УСТАНОВЩИКА:" -ForegroundColor Cyan
    Write-Host "   $InstallerPath"
    Write-Host ""
    Write-Host " Папка:" -ForegroundColor Cyan
    Write-Host "   $Folder"
    Write-Host ""
    Write-Host "------------------------------------------------------------"
    Write-Host " ЧТО ДЕЛАТЬ ДАЛЬШЕ (3 шага)" -ForegroundColor Yellow
    Write-Host "------------------------------------------------------------"
    Write-Host ""
    Write-Host " 1) ЗАЛИТЬ ФАЙЛ НА СЕРВЕР"
    Write-Host "    Откройте WinSCP (или FileZilla)."
    Write-Host "    Слева на своём компьютере найдите файл:"
    Write-Host "      $FileName"
    Write-Host "    Справа на сервере зайдите в папку /root"
    Write-Host "    Перетащите файл мышкой слева → направо."
    Write-Host ""
    Write-Host " 2) ЗАПУСТИТЬ ОДНУ КОМАНДУ НА СЕРВЕРЕ"
    Write-Host "    Откройте Putty / терминал сервера и введите:"
    Write-Host ""
    Write-Host "      sudo bash /root/$FileName" -ForegroundColor White
    Write-Host ""
    Write-Host "    (Если спросит пароль сервера — введите пароль от VPS.)"
    Write-Host ""
    Write-Host "    В файле уже прописаны:"
    Write-Host "      сайт   = $DomainValue"
    Write-Host "      IP     = $IpValue"
    Write-Host "      owner  = $OwnerValue"
    Write-Host "      имя    = $Product"
    Write-Host ""
    Write-Host " 3) КОГДА СПРОСИТ ТОКЕН БОТА"
    Write-Host "    Это НОВЫЙ токен от Telegram BotFather:"
    Write-Host "      a) Откройте Telegram → найдите @BotFather"
    Write-Host "      b) Нажмите /newbot  (или /token для существующего)"
    Write-Host "      c) Скопируйте длинную строку вида 123456:AA..."
    Write-Host "      d) Вставьте в окно сервера и нажмите Enter"
    Write-Host "         (символы могут не отображаться — это нормально)"
    Write-Host ""
    Write-Host "    Токен НЕ нужно было вписывать на этом компьютере —"
    Write-Host "    так безопаснее."
    Write-Host ""
    Write-Host "------------------------------------------------------------"
    Write-Host " Готово. Больше ничего собирать на Windows не нужно."
    Write-Host "------------------------------------------------------------"
    Write-Host ""

    try {
        Start-Process explorer.exe -ArgumentList "/select,$InstallerPath" | Out-Null
    } catch { }
}

# -------------------- gather answers --------------------

if (-not $NonInteractive) {
    Write-Banner
}

if ($NonInteractive) {
    if (-not $ProductName -or -not $Domain -or -not $Ipv4 -or -not $OwnerId -or -not $LogoPath) {
        throw "NonInteractive requires -ProductName -Domain -Ipv4 -OwnerId -LogoPath"
    }
    if (-not $Tagline) { $Tagline = "Digital Capital" }
    if (-not $Theme) { $Theme = "blue" }
} else {
    Write-Host "--- Имя бота ---" -ForegroundColor Cyan
    Write-Host " Латиницей, как на кнопках: AURORA, ACME, MyBot"
    if (-not $ProductName) {
        $ProductName = Read-Answer -Prompt " Имя бота" -Required
    }

    Write-Host ""
    Write-Host "--- Подпись под названием (необязательно) ---" -ForegroundColor Cyan
    if (-not $Tagline) {
        $Tagline = Read-Answer -Prompt " Слоган" -Default "Digital Capital"
    }

    Write-Host ""
    Write-Host "--- Домен сайта ---" -ForegroundColor Cyan
    Write-Host " Например: mybot.com   (без https://)"
    if (-not $Domain) {
        $Domain = Read-Answer -Prompt " Домен" -Required
    }

    Write-Host ""
    Write-Host "--- IP сервера ---" -ForegroundColor Cyan
    Write-Host " Цифры из панели VPS, например: 203.0.113.10"
    if (-not $Ipv4) {
        $Ipv4 = Read-Answer -Prompt " IP" -Required
    }

    Write-Host ""
    Write-Host "--- Ваш Telegram ID (число) ---" -ForegroundColor Cyan
    Write-Host " Напишите боту @userinfobot в Telegram — он покажет Id."
    if (-not $OwnerId) {
        $OwnerId = Read-Answer -Prompt " Telegram ID" -Required
    }

    Write-Host ""
    Write-Host "--- Логотип ---" -ForegroundColor Cyan
    Write-Host " 1 = открыть папку и положить logo.jpg туда"
    Write-Host " 2 = ввести полный путь к картинке"
    if (-not $LogoPath) {
        $LogoChoice = Read-Answer -Prompt " Как дать логотип" -Default "1"
        if ($LogoChoice -eq "2") {
            $LogoPath = Read-Answer -Prompt " Полный путь к файлу" -Required
        } else {
            New-Item -ItemType Directory -Force -Path $DropLogoDir | Out-Null
            # Clear previous drop logos so we do not reuse an old file silently
            Get-ChildItem -LiteralPath $DropLogoDir -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Extension -match '^\.(jpg|jpeg|png|webp)$' } |
                Remove-Item -Force -ErrorAction SilentlyContinue
            $LogoPath = Wait-ForLogoDrop -Folder $DropLogoDir
        }
    }

    Write-Host ""
    Write-Host "--- Цвета ---" -ForegroundColor Cyan
    Write-Host " 1 синий (как NOVERA)     2 зелёный"
    Write-Host " 3 фиолетовый             4 золотой"
    Write-Host " 5 красный"
    if (-not $Theme) {
        $Theme = Read-Answer -Prompt " Номер темы" -Default "1"
    }
}

# Validate / normalize
$ProductCode = ConvertTo-ProductCode -Name $ProductName
$ProductTitle = ConvertTo-ProductTitle -ProductCode $ProductCode
if (-not $ProfileId) { $ProfileId = ConvertTo-BrandSlug -Name $ProductCode }
$ThemeKey = Resolve-ThemeKey -Raw $Theme

if (-not (Test-DomainSimple -Value $Domain)) {
    throw "Домен выглядит странно: $Domain  (пример: mybot.com)"
}
if (-not (Test-Ipv4Simple -Value $Ipv4)) {
    throw "IP должен быть вида 203.0.113.10 — вы ввели: $Ipv4"
}
if (-not (Test-OwnerIdSimple -Value $OwnerId)) {
    throw "Telegram ID — только цифры (5–20 штук). Вы ввели: $OwnerId"
}
if (-not (Test-Path -LiteralPath $LogoPath -PathType Leaf)) {
    throw "Файл логотипа не найден: $LogoPath"
}
if ($ProfileId -eq "novera" -and -not $Yes -and -not $NonInteractive) {
    $Overwrite = Read-Answer -Prompt " Профиль 'novera' уже есть (основной). Перезаписать? да/нет" -Default "нет"
    if ($Overwrite -notmatch '^(да|yes|y|д)$') {
        throw "Отменено. Выберите другое имя бота."
    }
}

Write-Host ""
Write-Host "------------------------------------------------------------"
Write-Host " Проверьте:" -ForegroundColor Cyan
Write-Host "   Имя:     $ProductCode"
Write-Host "   Слоган:  $Tagline"
Write-Host "   Домен:   $Domain"
Write-Host "   IP:      $Ipv4"
Write-Host "   Owner:   $OwnerId"
Write-Host "   Цвета:   $(Get-ThemeLabelRu $ThemeKey)"
Write-Host "   Логотип: $LogoPath"
Write-Host "   Папка:   $ProfileId"
Write-Host "------------------------------------------------------------"

if (-not $Yes -and -not $NonInteractive) {
    $Ok = Read-Answer -Prompt " Всё верно? Собираем" -Default "да"
    if ($Ok -notmatch '^(да|yes|y|д)$') {
        Write-Host " Отменено. Запустите снова, когда будете готовы." -ForegroundColor Yellow
        exit 1
    }
}

Write-Host ""
Write-Host " Создаю профиль бренда..." -ForegroundColor Cyan
$CreatedDir = New-BrandProfileFromAnswers `
    -Id $ProfileId `
    -Product $ProductCode `
    -Title $ProductTitle `
    -TaglineValue $Tagline `
    -DomainValue $Domain `
    -IpValue $Ipv4 `
    -OwnerValue $OwnerId `
    -ThemeKey $ThemeKey `
    -LogoSource $LogoPath `
    -BoardSource $BoardPath

Write-Host " Профиль: $CreatedDir" -ForegroundColor Green
Write-Host ""
Write-Host " Собираю установщик (может занять минуту)..." -ForegroundColor Cyan

& $BuildScript -BrandProfile $ProfileId
if ($LASTEXITCODE -and $LASTEXITCODE -ne 0) {
    throw "Сборка установщика завершилась с ошибкой (код $LASTEXITCODE)"
}

$ReleasesDir = Join-Path $Root "_cursor_output\releases"
$Installer = Get-ChildItem -LiteralPath $ReleasesDir -Filter "*_BOOTSTRAP_INSTALLER_*.sh" -File |
    Sort-Object LastWriteTime -Descending |
    Select-Object -First 1

if (-not $Installer) {
    throw "Не нашёл готовый .sh в $ReleasesDir"
}

Write-HugeNextSteps `
    -InstallerPath $Installer.FullName `
    -Product $ProductCode `
    -DomainValue $Domain `
    -IpValue $Ipv4 `
    -OwnerValue $OwnerId

# Machine-readable path for automation / parent agent
Write-Host "INSTALLER_PATH=$($Installer.FullName)"
