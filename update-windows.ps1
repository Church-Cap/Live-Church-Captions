param(
    [switch]$Check,
    [switch]$Yes,
    [switch]$Restart,
    [int]$ServerPid = 0
)

$ErrorActionPreference = "Stop"

$LatestReleaseUrl = "https://api.github.com/repos/Church-Cap/Live-Church-Captions/releases/latest"
$RepoTagZipBaseUrl = "https://github.com/Church-Cap/Live-Church-Captions/archive/refs/tags"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "church-cap-update-$Stamp"
$ZipPath = Join-Path $TempDir "church-cap-release.zip"
$PreserveDir = Join-Path $TempDir "preserve"
$StageDir = Join-Path $TempDir "staged-release"
$ManifestPath = Join-Path $TempDir "staged-release.sha256.json"
$BackupRoot = Join-Path $AppDir "data\update-backups"
$BackupDir = Join-Path $BackupRoot "pre-update-$Stamp"
$ReplacementStarted = $false
$UpdateComplete = $false

function Normalize-Version {
    param([string]$Version)
    return (($Version -replace '^v\.', '') -replace '^v', '').Trim()
}

function Get-AppVersionFromText {
    param([string]$Text)
    $match = [regex]::Match($Text, 'app_version\s*:\s*str\s*=\s*"([^"]+)"')
    if ($match.Success) {
        return Normalize-Version $match.Groups[1].Value
    }
    return $null
}

function Get-LocalVersion {
    $settingsPath = Join-Path $AppDir "app\settings.py"
    if (-not (Test-Path $settingsPath)) { return "" }
    return Get-AppVersionFromText -Text (Get-Content $settingsPath -Raw)
}

function Get-RemoteReleaseTag {
    $response = Invoke-WebRequest -Uri $LatestReleaseUrl -UseBasicParsing -TimeoutSec 15 -Headers @{
        "Accept" = "application/vnd.github+json"
        "User-Agent" = "Church-Cap-Updater"
    }
    $release = $response.Content | ConvertFrom-Json
    return [string]$release.tag_name
}

function Convert-VersionTuple {
    param([string]$Version)
    $numbers = [regex]::Matches(($Version -replace '^v\.', '' -replace '^v', ''), '\d+') | ForEach-Object { [int]$_.Value }
    if (-not $numbers) { return @(0) }
    return @($numbers)
}

function Test-RemoteNewer {
    param([string]$Remote, [string]$Current)
    $r = Convert-VersionTuple $Remote
    $c = Convert-VersionTuple $Current
    $max = [Math]::Max($r.Count, $c.Count)
    for ($i = 0; $i -lt $max; $i++) {
        $rv = if ($i -lt $r.Count) { $r[$i] } else { 0 }
        $cv = if ($i -lt $c.Count) { $c[$i] } else { 0 }
        if ($rv -gt $cv) { return $true }
        if ($rv -lt $cv) { return $false }
    }
    return $false
}

function Copy-PreservedFile {
    param([string]$RelativePath)
    $source = Join-Path $AppDir $RelativePath
    $destination = Join-Path $PreserveDir $RelativePath
    if (Test-Path $source) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item $source $destination -Force
    }
}

function Set-EnvKey {
    param([string]$EnvPath, [string]$Key, [string]$Value)
    if (-not (Test-Path $EnvPath) -or [string]::IsNullOrWhiteSpace($Value)) { return }
    $lines = Get-Content $EnvPath
    $updated = $false
    $newLines = @()
    foreach ($line in $lines) {
        if ($line -like "$Key=*") {
            $newLines += "$Key=$Value"
            $updated = $true
        } else {
            $newLines += $line
        }
    }
    if (-not $updated) {
        $newLines += "$Key=$Value"
    }
    Set-Content -Path $EnvPath -Value $newLines
}

function Assert-ReleaseTree {
    param([string]$ReleaseDir)
    $requiredFiles = @(
        "app\main.py",
        "app\settings.py",
        "app\updater.py",
        "app\platforms.py",
        "app\service_leader_auth.py",
        "app\templates\service_leader.html",
        "app\templates\service_leader_pair.html",
        "app\templates\service_leader_pairing.html",
        "app\templates\operator.html",
        "app\static\styles.css",
        "requirements.txt",
        "setup-macos.sh",
        "start-macos.sh",
        "update-macos.sh",
        "setup-windows.cmd",
        "update-windows.ps1",
        "setup-linux.sh",
        "start-linux.sh",
        "update-linux.sh",
        "scripts\linux-system-packages.sh",
        "env.example"
    )
    foreach ($file in $requiredFiles) {
        if (-not (Test-Path (Join-Path $ReleaseDir $file))) {
            throw "Downloaded release is missing required file: $file"
        }
    }
}

function New-ReleaseManifest {
    param([string]$ReleaseDir, [string]$ManifestFile)
    $root = (Resolve-Path $ReleaseDir).Path
    $items = Get-ChildItem -LiteralPath $root -Recurse -File -Force | Sort-Object FullName | ForEach-Object {
        [pscustomobject]@{
            Path = $_.FullName.Substring($root.Length + 1)
            Hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $_.FullName).Hash
        }
    }
    $items | ConvertTo-Json -Depth 3 | Set-Content -Path $ManifestFile
}

function Test-ReleaseManifest {
    param([string]$InstalledDir, [string]$ManifestFile)
    $root = (Resolve-Path $InstalledDir).Path
    $items = Get-Content $ManifestFile -Raw | ConvertFrom-Json
    foreach ($item in $items) {
        $path = Join-Path $root $item.Path
        if (-not (Test-Path $path)) {
            throw "Installed release is missing file after copy: $($item.Path)"
        }
        $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $path).Hash
        if ($hash -ne $item.Hash) {
            throw "Installed file checksum mismatch: $($item.Path)"
        }
    }
}

function Copy-CurrentBackup {
    New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
    $envPath = Join-Path $AppDir ".env"
    if (Test-Path $envPath) {
        Copy-Item $envPath (Join-Path $BackupDir ".env") -Force
    }
    $preserveNames = @(".env", ".venv", ".git", "data", "logs", "certs")
    Get-ChildItem -Force -LiteralPath $AppDir |
        Where-Object { $preserveNames -notcontains $_.Name } |
        Copy-Item -Destination $BackupDir -Recurse -Force
}

function Remove-ReplaceableFiles {
    $preserveNames = @(".env", ".venv", ".git", "data", "logs", "certs")
    Get-ChildItem -Force -LiteralPath $AppDir |
        Where-Object { $preserveNames -notcontains $_.Name } |
        Remove-Item -Recurse -Force
}

function Restore-Backup {
    if (-not (Test-Path $BackupDir)) { return }
    Remove-ReplaceableFiles
    Get-ChildItem -Force -LiteralPath $BackupDir | Copy-Item -Destination $AppDir -Recurse -Force
    Write-Host "Previous Church Cap files restored from:"
    Write-Host "  $BackupDir"
}

try {
    $CurrentVersion = Get-LocalVersion
    $RemoteTag = Get-RemoteReleaseTag
    $RemoteVersion = Normalize-Version $RemoteTag
    if ([string]::IsNullOrWhiteSpace($RemoteTag) -or [string]::IsNullOrWhiteSpace($RemoteVersion)) {
        throw "Could not read the latest Church Cap release tag from GitHub."
    }
    $RepoZipUrl = "$RepoTagZipBaseUrl/$RemoteTag.zip"

    Write-Host "Church Cap updater"
    Write-Host "Current version: v.$CurrentVersion"
    Write-Host "Latest GitHub release: $RemoteTag"
    Write-Host "  $AppDir"
    Write-Host ""

    if (-not (Test-RemoteNewer -Remote $RemoteVersion -Current $CurrentVersion)) {
        Write-Host "Church Cap is up to date."
        exit 0
    }

    if ($Check) {
        Write-Host "Update available: v.$RemoteVersion"
        exit 0
    }

    if (-not $Yes) {
        $answer = Read-Host "Replace this Church Cap folder with v.$RemoteVersion now? [y/N]"
        if ($answer -notmatch "^(y|yes)$") {
            Write-Host "Update cancelled."
            exit 0
        }
    }

    New-Item -ItemType Directory -Force -Path $TempDir, $PreserveDir, $StageDir | Out-Null

    Write-Host "Downloading:"
    Write-Host "  $RepoZipUrl"
    curl.exe -L --fail --retry 3 --retry-delay 2 --connect-timeout 15 --max-time 240 -o $ZipPath $RepoZipUrl

    Write-Host "Checking downloaded ZIP integrity..."
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $zip = [System.IO.Compression.ZipFile]::OpenRead($ZipPath)
    $buffer = New-Object byte[] 8192
    foreach ($entry in $zip.Entries) {
        if ([string]::IsNullOrEmpty($entry.Name)) { continue }
        $stream = $entry.Open()
        try {
            while ($stream.Read($buffer, 0, $buffer.Length) -gt 0) {}
        } finally {
            $stream.Dispose()
        }
    }
    $zip.Dispose()

    Expand-Archive -Path $ZipPath -DestinationPath $TempDir -Force
    $ExtractedDir = Get-ChildItem -Path $TempDir -Directory -Filter "Live-Church-Captions-*" | Select-Object -First 1
    if (-not $ExtractedDir) {
        throw "Could not find extracted GitHub folder."
    }

    Assert-ReleaseTree -ReleaseDir $ExtractedDir.FullName
    $ExtractedVersion = Get-AppVersionFromText -Text (Get-Content (Join-Path $ExtractedDir.FullName "app\settings.py") -Raw)
    if ($ExtractedVersion -ne $RemoteVersion) {
        throw "Downloaded release version v.$ExtractedVersion did not match GitHub release $RemoteTag."
    }

    Copy-PreservedFile ".env"
    Copy-PreservedFile "config\glossary.csv"
    Copy-PreservedFile "config\profanity_filter.txt"

    Get-ChildItem -Force -LiteralPath $ExtractedDir.FullName | Copy-Item -Destination $StageDir -Recurse -Force
    if (Test-Path $PreserveDir) {
        Get-ChildItem -Force -LiteralPath $PreserveDir | Copy-Item -Destination $StageDir -Recurse -Force
    }

    $envExample = Join-Path $StageDir "env.example"
    $feedbackEmail = ""
    if (Test-Path $envExample) {
        $line = Select-String -Path $envExample -Pattern "^FEEDBACK_EMAIL=" | Select-Object -First 1
        if ($line) { $feedbackEmail = ($line.Line -replace "^FEEDBACK_EMAIL=", "") }
    }
    Set-EnvKey -EnvPath (Join-Path $StageDir ".env") -Key "APP_VERSION" -Value $RemoteVersion
    Set-EnvKey -EnvPath (Join-Path $StageDir ".env") -Key "FEEDBACK_EMAIL" -Value $feedbackEmail

    Write-Host "Checking staged release files..."
    New-ReleaseManifest -ReleaseDir $StageDir -ManifestFile $ManifestPath
    $VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
    $CompilePython = if (Test-Path $VenvPython) { $VenvPython } else { "python" }
    & $CompilePython -m py_compile (Join-Path $StageDir "app\settings.py") (Join-Path $StageDir "app\main.py") (Join-Path $StageDir "app\updater.py") (Join-Path $StageDir "app\platforms.py") (Join-Path $StageDir "app\service_leader_auth.py")

    if (Test-Path $VenvPython) {
        Write-Host "Updating Python packages before replacing app files..."
        & $VenvPython -m pip install -r (Join-Path $StageDir "requirements.txt")
        $translationReq = Join-Path $StageDir "requirements-translation.txt"
        if (Test-Path $translationReq) {
            & $VenvPython -m pip install -r $translationReq
        }
    } else {
        Write-Host "No existing .venv found. Run setup-windows.cmd before starting Church Cap."
    }

    Copy-CurrentBackup

    if ($ServerPid -gt 0) {
        Write-Host "Stopping running Church Cap process: $ServerPid"
        Stop-Process -Id $ServerPid -Force -ErrorAction SilentlyContinue
        Start-Sleep -Seconds 2
    }

    Write-Host "Replacing Church Cap files in:"
    Write-Host "  $AppDir"
    $ReplacementStarted = $true
    Remove-ReplaceableFiles
    Get-ChildItem -Force -LiteralPath $StageDir | Copy-Item -Destination $AppDir -Recurse -Force

    Write-Host "Verifying installed file checksums..."
    Test-ReleaseManifest -InstalledDir $AppDir -ManifestFile $ManifestPath
    $UpdateComplete = $true

    Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue

    Write-Host ""
    Write-Host "Church Cap updated in place to v.$RemoteVersion."
    Write-Host "Rollback backup kept at:"
    Write-Host "  $BackupDir"
    Write-Host ""
    if ($Restart) {
        Write-Host "Restarting Church Cap..."
        Start-Process -FilePath "powershell.exe" -ArgumentList @("-NoProfile", "-ExecutionPolicy", "Bypass", "-File", (Join-Path $AppDir "start-windows.ps1")) -WorkingDirectory $AppDir
    } else {
        Write-Host "Start Church Cap:"
        Write-Host "  .\start-windows.cmd"
    }
} catch {
    Write-Host ""
    Write-Host "Update failed: $($_.Exception.Message)"
    if ($ReplacementStarted -and -not $UpdateComplete) {
        Write-Host "Restoring the previous Church Cap files..."
        Restore-Backup
    }
    Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue
    exit 1
}
