# JARVIS Host Agent

FastAPI-сервіс на **Windows-хості** (поза Docker). Дає контейнеру `tools` доступ до PowerShell, CLI та файлової системи хоста через `host.docker.internal:8400`.

## Запуск

```bat
cd hostagent
pip install -r requirements.txt
set HOSTAGENT_TOKEN=<згенеруй: python -c "import secrets;print(secrets.token_hex(24))">
python -m uvicorn app.main:app --host 127.0.0.1 --port 8400
```

Або `run.bat` (читає `HOSTAGENT_*` з кореневого `.env`).

## Автозапуск

Зареєструй як scheduled task або NSSM-сервіс (аналог persistent Ollama, див. ROADMAP M1). Слухає лише `127.0.0.1`.

## Безпека

- `HOSTAGENT_TOKEN` — обовʼязковий; контейнер передає його в заголовку `X-Hostagent-Token`.
- `HOSTAGENT_ALLOW_ADMIN=1` — дозволяє elevated PowerShell (за замовч. вимкнено).
- У `.env` tools: `ENABLE_COMPUTER_USE=true` + той самий токен у `HOSTAGENT_TOKEN`.
