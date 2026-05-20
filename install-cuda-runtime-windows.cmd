@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\install-cuda-runtime-windows.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo CUDA runtime installation did not complete.
  echo Church Cap can still run on CPU.
  echo.
  pause
)

exit /b %EXIT_CODE%
