param(
    [switch]$SkipTranslation
)

$ErrorActionPreference = "Stop"
$AppDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $AppDir

function Step($Message) {
    Write-Host ""
    Write-Host "==> $Message"
}

function Ensure-EnvFile {
    if (Test-Path ".env") {
        Write-Host ".env already exists; keeping your current settings."
        return
    }
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" ".env"
        Write-Host "Created .env from .env.example"
        return
    }
    if (Test-Path "env.example") {
        Copy-Item "env.example" ".env"
        Write-Host "Created .env from env.example"
        return
    }
    Write-Host "Could not find .env.example or env.example. Re-download Church Cap and try again."
    exit 1
}

Write-Host ""
Write-Host "====================================================="
Write-Host " Church Cap first-time setup for Windows"
Write-Host "====================================================="
Write-Host ""
Write-Host "This prepares Church Cap as a local server app."
Write-Host "Python packages are installed only into this folder's .venv."
Write-Host ""
Write-Host "Requirements:"
Write-Host "  - Windows 10 or newer"
Write-Host "  - Python 3.12, or Python 3.10+ if 3.12 is not available"
Write-Host "  - If Python is missing, this script can offer to install Python 3.12 with winget"
Write-Host "  - Internet access for first setup"
Write-Host "  - Optional NVIDIA GPU with current drivers for CUDA acceleration"
Write-Host ""

$answer = Read-Host "Continue with setup? [y/N]"
if ($answer -notmatch "^(y|yes)$") {
    Write-Host "Setup cancelled."
    exit 0
}

function Find-Python {
    $localPython312 = Join-Path $env:LocalAppData "Programs\Python\Python312\python.exe"
    $programPython312 = Join-Path $env:ProgramFiles "Python312\python.exe"
    $candidates = @(
        @{ Command = "py"; Args = @("-3.12") },
        @{ Command = "py"; Args = @("-3") },
        @{ Command = "python"; Args = @() },
        @{ Command = "python3"; Args = @() },
        @{ Command = $localPython312; Args = @() },
        @{ Command = $programPython312; Args = @() }
    )

    foreach ($candidate in $candidates) {
        if ($candidate.Command -match "[\\/]") {
            if (-not (Test-Path $candidate.Command)) { continue }
        } else {
            $cmd = Get-Command $candidate.Command -ErrorAction SilentlyContinue
            if (-not $cmd) { continue }
        }
        try {
            $version = & $candidate.Command @($candidate.Args) -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            if ([version]$version -ge [version]"3.10") {
                return @{ Command = $candidate.Command; Args = $candidate.Args }
            }
        } catch {
            continue
        }
    }
    return $null
}

Step "1/6 Finding Python"
$Python = Find-Python

if (-not $Python) {
    Write-Host "Python 3.10 or newer was not found."
    $winget = Get-Command winget -ErrorAction SilentlyContinue
    if ($winget) {
        Write-Host "Windows Package Manager (winget) is available."
        $installPython = Read-Host "Install Python 3.12 now with winget? [y/N]"
        if ($installPython -match "^(y|yes)$") {
            winget install --id Python.Python.3.12 --source winget --accept-package-agreements --accept-source-agreements
            $Python = Find-Python
            if (-not $Python) {
                Write-Host ""
                Write-Host "Python was installed, but this PowerShell window cannot see it yet."
                Write-Host "Close PowerShell, open it again in this folder, then rerun:"
                Write-Host "  .\setup-windows.cmd"
                exit 1
            }
        }
    }
}

if (-not $Python) {
    Write-Host "Install Python 3.12 from https://www.python.org/downloads/windows/ and tick 'Add python.exe to PATH'."
    Write-Host "Then rerun this setup script."
    exit 1
}

$pythonVersion = & $Python.Command @($Python.Args) --version
Write-Host "Using $pythonVersion"

Step "2/6 Creating local project virtual environment"
if (-not (Test-Path ".venv")) {
    & $Python.Command @($Python.Args) -m venv .venv
} else {
    Write-Host ".venv already exists; reusing it. To rebuild, delete .venv and rerun setup."
}

$VenvPython = Join-Path $AppDir ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "Virtual environment Python was not created correctly."
    exit 1
}

Step "3/6 Installing Python packages inside .venv only"
& $VenvPython -m ensurepip --upgrade | Out-Null
& $VenvPython -m pip install --upgrade pip "setuptools<82" wheel
& $VenvPython -m pip install -r requirements.txt

Step "4/6 Creating local folders and .env"
New-Item -ItemType Directory -Force -Path data, logs, certs | Out-Null
Ensure-EnvFile

Step "5/6 Checking CUDA/GPU support"
& $VenvPython scripts\check-gpu.py
$GpuStatus = $null
try {
    $GpuStatus = (& $VenvPython scripts\check-gpu.py --json | ConvertFrom-Json)
} catch {
    $GpuStatus = $null
}
Write-Host ""
Write-Host "If CUDA and the required NVIDIA runtime DLLs are available, Church Cap will use device=cuda and compute_type=float16 when WHISPER_DEVICE=auto."
Write-Host "If CUDA is not available, it will use CPU with int8 compute."
if ($GpuStatus -and $GpuStatus.nvidia_smi_available -and -not $GpuStatus.cuda_available) {
    Write-Host ""
    Write-Host "An NVIDIA GPU is visible, but CUDA is not ready for faster-whisper."
    if ($GpuStatus.missing_cuda_libraries -and $GpuStatus.missing_cuda_libraries.Count -gt 0) {
        Write-Host "Missing CUDA runtime files: $($GpuStatus.missing_cuda_libraries -join ', ')"
    }
    Write-Host "Church Cap can install or force reinstall local NVIDIA CUDA 12 runtime packages into .venv."
    Write-Host "This is optional, large, and only affects this Church Cap folder."
    $installCudaRuntime = Read-Host "Install or force reinstall local CUDA 12 runtime packages now? [y/N]"
    if ($installCudaRuntime -match "^(y|yes)$") {
        & (Join-Path $AppDir "scripts\install-cuda-runtime-windows.ps1")
    } else {
        Write-Host "Skipping CUDA runtime install. Church Cap will use CPU."
        Write-Host "You can run .\install-cuda-runtime-windows.cmd later."
    }
}

Step "6/6 Installing Base translation dependencies/models"
if ($SkipTranslation) {
    Write-Host "Skipping Argos Translate setup because -SkipTranslation was used."
} else {
    Write-Host "Base translation uses Argos Translate for local, offline text translation after language packs are downloaded."
    Write-Host "Translation is experimental and may be inaccurate. It may still run on CPU even when Whisper uses CUDA."
    Write-Host "You can install all Base packs or the heavier Core SMaLL-100 model later from the operator Languages page."
    Write-Host ""
    Write-Host "Translation resource options:"
    Write-Host "  1) Install common Base packs (recommended)"
    Write-Host "  2) Install all available Base packs"
    Write-Host "  3) Install common Base packs and optional Core model"
    Write-Host "  4) Skip translation resources for now"
    $translationAnswer = Read-Host "Choose translation setup [1]"
    switch ($translationAnswer) {
        "2" { & (Join-Path $AppDir "scripts\install-translation-models-argos.ps1") -All }
        "3" {
            & (Join-Path $AppDir "scripts\install-translation-models-argos.ps1")
            & (Join-Path $AppDir "scripts\install-small100-core.ps1")
        }
        "4" { Write-Host "Skipping translation resources. You can install them later from the operator Languages page." }
        default { & (Join-Path $AppDir "scripts\install-translation-models-argos.ps1") }
    }
}

Write-Host ""
Write-Host "Setup complete."
Write-Host ""
Write-Host "Start the server:"
Write-Host "  .\start-windows.cmd"
Write-Host ""
Write-Host "First-run password setup:"
Write-Host "  http://localhost:9090/setup"
Write-Host ""
Write-Host "Operator page after setup:"
Write-Host "  http://localhost:9090/operator"
Write-Host ""
Write-Host "On first run, create the operator password in the web page."
