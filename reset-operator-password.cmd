@echo off
setlocal
cd /d "%~dp0"

powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0reset-operator-password.ps1"
set "EXIT_CODE=%ERRORLEVEL%"

if not "%EXIT_CODE%"=="0" (
  echo.
  echo Password reset did not complete.
  echo If Windows blocked the script, right-click the Church Cap folder or zip file,
  echo choose Properties, tick Unblock if shown, then try this file again.
  echo.
  pause
)

exit /b %EXIT_CODE%
