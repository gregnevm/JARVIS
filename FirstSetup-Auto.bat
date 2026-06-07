@echo off
REM JARVIS — повністю автономний setup (без питань).
REM Перед першим запуском: copy setup.local.env.example setup.local.env
REM і впиши TELEGRAM_BOT_TOKEN + ALLOWED_USER_IDS.
cd /d %~dp0
if not exist setup.local.env (
  echo [WARN] setup.local.env not found.
  echo        copy setup.local.env.example setup.local.env
  echo        and fill TELEGRAM_BOT_TOKEN + ALLOWED_USER_IDS for Telegram bot.
  echo        Stack will still install; add token later and re-run gateway.
  echo.
)
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0scripts\FirstSetup.ps1" -Auto
set EXITCODE=%ERRORLEVEL%
if %EXITCODE%==2 (
  echo.
  echo Docker pending - reboot or wait for Docker Desktop, then setup resumes at logon.
  pause
  exit /b 2
)
if %EXITCODE% NEQ 0 (
  echo.
  echo FirstSetup-Auto finished with warnings/errors. See data\firstsetup.log
  pause
  exit /b %EXITCODE%
)
echo.
echo FirstSetup-Auto complete. See data\firstsetup.status.json
pause
exit /b 0
