[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
$Python = if ($env:CHURCH_CAP_PACKAGING_PYTHON) { $env:CHURCH_CAP_PACKAGING_PYTHON } else { Join-Path $ProjectRoot '.venv-packaging\Scripts\python.exe' }
if (-not [Environment]::Is64BitOperatingSystem -or -not [Environment]::Is64BitProcess) { throw 'The Church Cap Windows engine must be built by a native 64-bit Windows process.' }
if (-not (Test-Path -LiteralPath $Python -PathType Leaf)) { throw "Python 3.12 packaging environment not found: $Python" }
$Version = & $Python -c 'import platform,sys; print(sys.version_info.major, sys.version_info.minor, platform.machine())'
if ($LASTEXITCODE -ne 0 -or $Version -notmatch '^3 12 (AMD64|x86_64)$') { throw "Expected Python 3.12 x64, found $Version" }
& $Python -c 'import PyInstaller'
if ($LASTEXITCODE -ne 0) { throw 'PyInstaller is missing from the packaging environment.' }
$Torch = & $Python -c 'import torch; print(torch.__version__, torch.version.cuda)'
if ($LASTEXITCODE -ne 0 -or $Torch -notmatch '^2\.13\.0(?:\+cpu)? None$') { throw "The small Windows installer requires CPU-only PyTorch 2.13.0 from packaging/engine/requirements-windows-cpu.txt; found $Torch." }
$env:PYINSTALLER_CONFIG_DIR = Join-Path $ProjectRoot 'build\pyinstaller-config-windows'
Push-Location $ProjectRoot
try {
    & $Python -m PyInstaller --clean --noconfirm --distpath (Join-Path $ProjectRoot 'dist\engine-windows-x64') --workpath (Join-Path $ProjectRoot 'build\engine-windows-x64') (Join-Path $ProjectRoot 'packaging\engine\church_cap_engine.spec')
    if ($LASTEXITCODE -ne 0) { throw "PyInstaller failed with exit code $LASTEXITCODE." }
} finally { Pop-Location }
& (Join-Path $PSScriptRoot 'check-windows-engine-bundle.ps1')
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host 'Frozen Windows x64 engine created at dist\engine-windows-x64\church-cap-engine\church-cap-engine.exe'
