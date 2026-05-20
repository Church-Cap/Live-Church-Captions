$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "The local Python environment has not been set up yet."
    Write-Host "Run: .\setup-windows.cmd"
    exit 1
}

if (-not (Test-Path ".env")) {
    Copy-Item ".env.example" ".env"
}

$ViewerPort = if ($env:VIEWER_PORT) { $env:VIEWER_PORT } else { "8080" }
$OperatorPort = if ($env:OPERATOR_PORT) { $env:OPERATOR_PORT } else { "9090" }
$OperatorUrl = "http://localhost:$OperatorPort/operator"
$StartupUrl = "http://localhost:$OperatorPort/setup"

function Get-LanIp {
    $addresses = Get-NetIPAddress -AddressFamily IPv4 -ErrorAction SilentlyContinue |
        Where-Object {
            $_.IPAddress -notlike "127.*" -and
            $_.IPAddress -notlike "169.254.*" -and
            $_.PrefixOrigin -ne "WellKnown"
        } |
        Select-Object -First 1
    if ($addresses) { return $addresses.IPAddress }
    return "127.0.0.1"
}

$LanIp = Get-LanIp
$AudienceUrl = "http://$LanIp`:$ViewerPort/"

Write-Host "Starting Church Cap in secure dual-port mode..."
Write-Host "Operator page: $OperatorUrl"
Write-Host "First-run password setup: $StartupUrl"
Write-Host "Audience/IP URL: $AudienceUrl"
Write-Host ""
Write-Host "Please wait while Church Cap starts. The password setup or operator page will open automatically in a few seconds."
Write-Host "If you are locked out, stop the server with Ctrl+C and run: .\reset-operator-password.cmd"
Write-Host "To inspect GPU support, run: .venv\Scripts\python.exe scripts\check-gpu.py"
Write-Host "Press Ctrl+C in this PowerShell window to stop the server."

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"

$job = Start-Job -ScriptBlock {
    param($StartupUrl)
    for ($i = 0; $i -lt 45; $i++) {
        try {
            Invoke-WebRequest -Uri $StartupUrl -UseBasicParsing -TimeoutSec 1 | Out-Null
            break
        } catch {
            Start-Sleep -Seconds 1
        }
    }
    Start-Process $StartupUrl
} -ArgumentList $StartupUrl

try {
    & $VenvPython scripts\run-dual.py
} finally {
    Remove-Job $job -Force -ErrorAction SilentlyContinue
}
