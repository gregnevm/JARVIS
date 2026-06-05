# Локальна генерація зображень (SD Forge)

**Roadmap 1.4.1** — image gen на Windows-хості, API для tools `generate_image`.

## Швидкий старт

```powershell
cd O:\JARVIS
.\scripts\setup_sd_forge.ps1    # один раз (clone Forge)
.\scripts\start_sd_forge.ps1    # API http://127.0.0.1:7860
```

`.env`:

```
IMAGE_GEN_URL=http://host.docker.internal:7860
IMAGE_GEN_TIMEOUT=300
```

```powershell
docker compose up -d --build tools
.\scripts\verify_stack.ps1   # [OK] IMAGE_GEN: Forge local :7860
```

## AMD / 8GB VRAM

- `webui-user.bat` використовує `--directml --medvram` (див. `setup_sd_forge.ps1`).
- Checkpoint **SD 1.5** recommended; SDXL — лише якщо VRAM дозволяє.

## Альтернативи (хмара, opt-in)

| `IMAGE_GEN_URL` | Опис |
|-----------------|------|
| `pollinations` | без ключа |
| `horde` | `HORDE_API_KEY` |
| `ollama` | macOS image model |
| порожньо | `generate_image` вимкнено |

## Lock

Одночасна генерація — Redis lock (`image_gen_lock`), щоб не з’їдати VRAM з agent model.

## Troubleshooting

| Симптом | Дія |
|---------|-----|
| verify `Forge not running` | `.\scripts\start_sd_forge.ps1` |
| tools timeout | ↑ `IMAGE_GEN_TIMEOUT` |
| OOM | `--medvram`, менший checkpoint |
