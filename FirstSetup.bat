@echo off
REM JARVIS — перше розгортання на цьому ПК (Windows).
cd /d %~dp0
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\FirstSetup.ps1" %*
if errorlevel 1 (
  echo.
  echo FirstSetup failed. See messages above.
  pause
  exit /b 1
)
pause
