@echo off
REM JARVIS host-agent — запуск на Windows-хості (поза Docker).
REM Скопіюй .env з кореня JARVIS або задай HOSTAGENT_TOKEN вручну.
cd /d %~dp0
if exist ..\.env (
  REM Import ALL HOSTAGENT_* keys (token, allow_admin, allow_power, fs_roots, bind_host, port, drop_dir).
  for /f "usebackq tokens=1,* delims==" %%a in (`findstr /i "^HOSTAGENT_" ..\.env`) do set "%%a=%%b"
)
python -m uvicorn app.main:app --host %HOSTAGENT_BIND_HOST: =127.0.0.1% --port %HOSTAGENT_PORT: =8400%
