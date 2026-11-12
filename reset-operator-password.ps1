$ErrorActionPreference = "Stop"

$AppData = if ($env:APPDATA) { $env:APPDATA } else { Join-Path $HOME "AppData\Roaming" }
$DataDir = Join-Path $AppData "Church Cap\data"
$Files = @(
    (Join-Path $DataDir "operator_auth.json"),
    (Join-Path $DataDir "operator_auth.backup.json")
)
$Deleted = 0

Write-Host "Church Cap operator password reset"
Write-Host "This removes the stored operator password hash and session secret."
Write-Host "The next start will show the first-run password setup page."
Write-Host ""

$answer = Read-Host "Continue? [y/N]"
if ($answer -notmatch "^(y|yes)$") {
    Write-Host "Cancelled."
    exit 0
}

foreach ($file in $Files) {
    if (Test-Path $file) {
        Remove-Item $file -Force
        $Deleted += 1
        Write-Host "Removed $file"
    } else {
        Write-Host "No auth file found at $file"
    }
}

if ($Deleted -gt 0) {
    $Marker = Join-Path $DataDir "operator_password_recovery.flag"
    Set-Content -Path $Marker -Value "password-reset" -Encoding UTF8
    Write-Host "Existing caption, language, and performance settings will be preserved."
}

Write-Host ""
Write-Host "Password reset complete. Start Church Cap and create a new operator password."
