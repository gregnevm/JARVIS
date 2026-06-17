# JARVIS Coding Agent — VS Code extension (CA-6.3)

IDE-міст до рідного coding-агента JARVIS (Стовп B). Тонкий клієнт поверх tools REST —
жодної бізнес-логіки на клієнті (S3), лише представлення diff у нативному VS Code diff-view.

## Можливості

- **JARVIS: Propose Edit (inline diff)** — у відкритому файлі вводиш інструкцію
  («додай docstring до `foo`»), агент повертає оновлений вміст; розширення показує
  diff поточний↔запропонований і за згодою застосовує правку. На бекенді — `POST
  /agent/code/edit` (dry-run, нічого не пишеться на диск без твоєї згоди).
- **JARVIS: Review Working Diff** — рев'ю unified-diff з активного редактора через
  `POST /agent/code/review`; зауваження — в Output-канал «JARVIS Review».

## Налаштування (`Settings → JARVIS`)

| Ключ | Дефолт | Опис |
|------|--------|------|
| `jarvis.toolsUrl` | `http://127.0.0.1:8001` | базовий URL tools-сервісу |
| `jarvis.apiKey` | `` | Bearer-ключ (Стовп A, CA-6.2); порожньо — self-hosted без auth |
| `jarvis.userId` | `0` | user_id для скоупу/аудиту |

## Запуск (dev)

Це zero-build розширення (plain JS, без транспіляції):

1. Відкрий теку `clients/vscode-jarvis/` у VS Code.
2. `F5` → запуститься Extension Development Host.
3. Відкрий будь-який файл → Command Palette → **JARVIS: Propose Edit**.

Переконайся, що tools-сервіс JARVIS піднятий і доступний за `jarvis.toolsUrl`.

## Межі

- Правки застосовуються **лише** після явного `Apply` (інлайн-diff — dry-run).
- Git-safety, confirm-tier і policy-gate (CA-1.3 / CA-6.4) діють на бекенді; розширення
  їх не обходить.
