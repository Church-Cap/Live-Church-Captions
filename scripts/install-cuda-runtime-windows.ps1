$ErrorActionPreference = "Stop"
$ProjectRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
    Write-Host "No .venv found. Run .\setup-windows.cmd first."
    exit 1
}

Write-Host ""
Write-Host "Force reinstalling NVIDIA CUDA 12 runtime packages inside Church Cap's .venv."
Write-Host "This is optional and can be a large download."
Write-Host "It avoids requiring a full system-wide CUDA Toolkit install for many users."
Write-Host "The reinstall bypasses pip's cache so damaged or stale CUDA wheels are replaced."
Write-Host ""

& $VenvPython -m pip install --upgrade pip "setuptools<82" wheel

Write-Host ""
Write-Host "Removing existing local NVIDIA runtime wheels if present..."
& $VenvPython -m pip uninstall -y nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 nvidia-cudnn-cu12

Write-Host ""
Write-Host "Clearing pip's local package cache where possible..."
& $VenvPython -m pip cache purge

Write-Host ""
Write-Host "Downloading and force reinstalling fresh CUDA runtime wheels..."
& $VenvPython -m pip install --force-reinstall --no-cache-dir --upgrade --extra-index-url https://pypi.ngc.nvidia.com nvidia-cuda-runtime-cu12 nvidia-cublas-cu12 "nvidia-cudnn-cu12<9"

Write-Host ""
Write-Host "CUDA runtime packages force reinstalled into .venv."
Write-Host "Checking GPU status again..."
& $VenvPython scripts\check-gpu.py
