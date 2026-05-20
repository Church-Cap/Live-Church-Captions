$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "No .venv found. Run .\setup-windows.cmd first."
    exit 1
}

Write-Host ""
Write-Host "Installing NVIDIA CUDA 12 runtime packages inside Church Cap's .venv."
Write-Host "This is optional and can be a large download."
Write-Host "It avoids requiring a full system-wide CUDA Toolkit install for many users."
Write-Host ""

& $VenvPython -m pip install --upgrade pip "setuptools<82" wheel
& $VenvPython -m pip install --upgrade --extra-index-url https://pypi.ngc.nvidia.com nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 "nvidia-cudnn-cu12<9"

Write-Host ""
Write-Host "CUDA runtime packages installed into .venv."
Write-Host "Checking GPU status again..."
& $VenvPython scripts\check-gpu.py
