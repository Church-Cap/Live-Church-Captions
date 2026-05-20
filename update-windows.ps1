$ErrorActionPreference = "Stop"

$RepoZipUrl = "https://github.com/Church-Cap/Live-Church-Captions/archive/refs/heads/main.zip"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ParentDir = Split-Path -Parent $AppDir
$Stamp = Get-Date -Format "yyyyMMdd-HHmmss"
$TargetDir = Join-Path $ParentDir "church_cap_update_$Stamp"
$TempDir = Join-Path ([System.IO.Path]::GetTempPath()) "church-cap-update-$Stamp"
$ZipPath = Join-Path $TempDir "church-cap-main.zip"

Write-Host "Church Cap updater"
Write-Host "This downloads the latest GitHub source into a new folder."
Write-Host "Current folder will not be overwritten:"
Write-Host "  $AppDir"
Write-Host ""

$answer = Read-Host "Download latest Church Cap from GitHub now? [y/N]"
if ($answer -notmatch "^(y|yes)$") {
    Write-Host "Update cancelled."
    exit 0
}

New-Item -ItemType Directory -Force -Path $TempDir, $TargetDir | Out-Null

Write-Host "Downloading:"
Write-Host "  $RepoZipUrl"
curl.exe -L --fail -o $ZipPath $RepoZipUrl

Expand-Archive -Path $ZipPath -DestinationPath $TempDir -Force
$ExtractedDir = Get-ChildItem -Path $TempDir -Directory -Filter "Live-Church-Captions-*" | Select-Object -First 1
if (-not $ExtractedDir) {
    Write-Host "Could not find extracted GitHub folder."
    exit 1
}

Copy-Item -Path (Join-Path $ExtractedDir.FullName "*") -Destination $TargetDir -Recurse -Force

if ((Test-Path (Join-Path $AppDir ".env")) -and -not (Test-Path (Join-Path $TargetDir ".env"))) {
    Copy-Item (Join-Path $AppDir ".env") (Join-Path $TargetDir ".env")
}

foreach ($file in @("config\glossary.csv", "config\profanity_filter.txt")) {
    $source = Join-Path $AppDir $file
    $destination = Join-Path $TargetDir $file
    if (Test-Path $source) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destination) | Out-Null
        Copy-Item $source $destination -Force
    }
}

Remove-Item $TempDir -Recurse -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Update downloaded to:"
Write-Host "  $TargetDir"
Write-Host ""
Write-Host "Next steps:"
Write-Host "  cd `"$TargetDir`""
Write-Host "  .\setup-windows.cmd"
Write-Host "  .\start-windows.cmd"
