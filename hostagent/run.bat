@echo off
REM JARVIS host-agent — запуск на Windows-хості (поза Docker).
REM Скопіюй .env з кореня JARVIS або задай HOSTAGENT_TOKEN вручну.
cd /d %~dp0
if exist ..\.env (
  for /f "usebackq tokens=1,* delims==" %%a in (`findstr /i "^HOSTAGENT_TOKEN= ^HOSTAGENT_ALLOW_ADMIN= ^HOSTAGENT_BIND_HOST= ^HOSTAGENT_PORT= " ..\.env`) do set %%a=%%b
)
python -m uvicorn app.main:app --host %HOSTAGENT_BIND_HOST: =127.0.0.1% --port %HOSTAGENT_PORT: =8400%
