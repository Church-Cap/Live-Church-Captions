@echo off
setlocal
cd /d "%~dp0"

echo Starting Church Cap Windows setup...
echo.
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0setup-windows.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Setup did not complete.
  echo If Windows blocked the script, right-click the Church Cap folder or zip file,
  echo choose Properties, tick Unblock if shown, then try this file again.
  echo.
  pause
)

exit /b %EXIT_CODE%
