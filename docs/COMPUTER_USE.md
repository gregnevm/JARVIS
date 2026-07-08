# JARVIS — Computer Use (Agent Mode)

> **Статус:** C0+C1+C2 реалізовано (2026-06-04). Підтвердження мутуючих дій у Telegram
> + аудит `data/logs/computer.jsonl`. Admin PowerShell за замовч. вимкнено —
> `COMPUTER_ALLOW_ADMIN=false` і `HOSTAGENT_ALLOW_ADMIN=0`.
> **Мета:** дати агентові JARVIS здатність **реально керувати комп'ютером** —
> AIO, повністю self-hosted, з вшитим принципом «завжди найшвидшим/найпрямішим шляхом».
> **Прив'язка до коду:** надбудова над наявним тул-лупом (`tools/app/agent.py`
> `AgentRunner._agent`) і toolkit-ом (`tools/app/toolkit/` — пакет).

---

## 0. Головний принцип: «драбина швидкодії» (capability ladder)

Агент **ніколи не клікає мишею, якщо задачу можна зробити пряміше**. Кожна дія
обирається з пріоритетного списку механізмів — від найпрямішого до найдорожчого.
Це формалізуємо як *tier* кожного інструмента і вшиваємо у system-prompt + логіку
диспетчера.

| Tier | Механізм | Приклад | Коли |
|------|----------|---------|------|
| **T0** | Прямий API/OS-виклик | PowerShell (admin), файлова система, реєстр, WinAPI | завжди перший вибір |
| **T1** | CLI-утиліти | `winget`, `git`, `curl`, `ffmpeg`, `gh` | коли є готова утиліта |
| **T2** | Браузер через DOM/CDP | читати HTML, заповнити форму, клік по селектору, JS-eval | веб-задачі |
| **T3** | UI Automation (семантично) | pywinauto/UIA: «натисни кнопку *Save*» за **назвою**, не за пікселем | десктоп-застосунки з API доступності |
| **T4** | Візуальний GUI | скріншот → vision-модель → клік по (x,y) | **останній резерв**, коли все вище неможливо |

У system-prompt принцип формулюється так: *«Спершу спробуй PowerShell або CLI.
Браузер — через читання DOM і селектори, не візуально. Візуальний клік по
координатах — лише якщо немає жодного програмного способу.»* Агент у відповіді
звітує, **яким tier** він діяв (прозорість + аудит).

---

## 1. Загальна архітектура (AIO, self-hosted)

Ключове обмеження стеку: `tools/` живе **в Docker-контейнері (Linux)**, а керувати
треба **реальним Windows-хостом**. Тому потрібен новий компонент — **host-agent**,
що крутиться на самому Windows (поза Compose), а контейнер ходить до нього по HTTP
через `host.docker.internal`.

```
Telegram ─► gateway ─► tools /agent (агент-луп, AGENT_MODE=computer)
                           │  обирає tier і кличе інструмент
                           ▼
          ┌──────────────── computer toolkit (у контейнері) ────────────────┐
          │  T2 браузер: Playwright/CDP (може жити в контейнері)             │
          │  T0/T1/T3/T4: проксі-виклик на host-agent ──────────────────────┼──► host-agent (Windows, на хості)
          └─────────────────────────────────────────────────────────────────┘     ├─ /powershell  (T0, admin-gated)
                                                                                    ├─ /fs/*         (T0 файли)
                                                                                    ├─ /cli          (T1)
                                                                                    ├─ /uia/*        (T3 pywinauto)
                                                                                    ├─ /window/*     (T3 фокус/розкладка)
                                                                                    └─ /screen/*     (T4 screenshot/click/type)
```

Чому host-agent окремо, а не «розширити контейнер»: контейнер фізично не має
десктопа Windows, миші, вікон, реєстру, `winget`. Тільки процес **на хості** це
бачить. Браузер (T2) — виняток: його можна тримати в контейнері через Playwright,
бо він самодостатній.

---

## 2. Новий сервіс: `hostagent/` (на Windows-хості)

Маленький FastAPI, запускається як scheduled task / NSSM-сервіс (за тим самим
патерном, що persistent Ollama, `ROADMAP.md` M1). Стек: `pyautogui` (T4),
`pywinauto`/`uiautomation` (T3), `pygetwindow` (вікна), `mss` (швидкі скріншоти),
`subprocess`→PowerShell (T0/T1).

Ендпойнти (чернетка контракту):

- `POST /powershell` `{script, as_admin, timeout}` → `{stdout, stderr, code}` — **T0, головний робочий кінь**.
- `POST /cli` `{exe, args[], cwd}` — T1, без shell-інтерполяції (безпечніше за raw shell).
- `GET /fs/list?path=`, `GET /fs/read?path=`, `POST /fs/write` — T0 файли (з лімітами розміру, як `fetch_max_chars`).
- `POST /uia/invoke` `{window, control_name, action}` — T3, клік по **імені** контролу.
- `GET /window/list`, `POST /window/focus` `{title}` — T3 керування вікнами.
- `GET /screen/shot` → PNG/base64, `POST /screen/click` `{x,y}`, `POST /screen/type` `{text}` — T4.
- `GET /health` — для healthcheck, як у решти сервісів.

Захист host-agent: слухає лише `127.0.0.1`/локальну Docker-мережу, токен
`HOSTAGENT_TOKEN` у заголовку, нічого назовні.

---

## 3. Інтеграція з наявним кодом (точки дотику)

Усе лягає поверх наявного тул-лупа — `AgentRunner._agent` міняти майже не треба,
він уже крутить інструменти (`tools/app/agent.py`):

1. **`tools/app/toolkit/`** (пакет: `dispatch.py`/`image.py`/`notes.py`/`schemas.py`/`web.py`) — нові функції-інструменти (`run_powershell`,
   `run_cli`, `fs_list/read/write`, `browser_*`, `uia_invoke`, `window_focus`,
   `screen_*`), кожна тегована своїм tier у `description`. Зареєструвати у
   `TOOL_SCHEMAS` (gated прапором) + гілки в `dispatch()`. Це рівно той патерн,
   що вже є для `web_fetch`/`take_note`.
2. **`tools/app/config.py` / `.env.example`** — нові прапори за аналогією з
   `enable_code_exec`:
   - `ENABLE_COMPUTER_USE=false` (майстер-вимикач);
   - `COMPUTER_ALLOW_ADMIN=false` (окремо для admin-PowerShell — найнебезпечніше);
   - `HOSTAGENT_URL=http://host.docker.internal:8400`, `HOSTAGENT_TOKEN=…`;
   - `COMPUTER_REQUIRE_CONFIRM=true` (підтвердження в Telegram перед мутуючими діями);
   - `COMPUTER_APPROVAL_POLICY=` — іменована драбина `strict|smart|auto|off` поверх
     confirm/auto-trust/bypass (`computer_policy.py`, SSOT; невідоме → strict fail-closed);
   - `PS_WHITELIST` / `CLI_WHITELIST` — перелік дозволених команд/exe.
3. **Новий режим у `decide_mode`/`AGENT_MODE`** — `computer` (завжди тул-луп з повним
   computer-toolkit). Додати `SYSTEM_COMPUTER` промпт, що навчає «драбини швидкодії» з §0.
4. **`gateway/`** — підтвердження дій: коли інструмент мутуючий і
   `COMPUTER_REQUIRE_CONFIRM=true`, агент повертає «pending action», gateway шле
   inline-кнопки ✅/❌ (уже є `bot/keyboards.py`, `bot/admin.py`).
5. **`docker-compose.yml`** — host-agent у Compose **не** додаємо (він на хості).
   Лише пробрасуємо `HOSTAGENT_URL` через `extra_hosts: host.docker.internal`.

---

## 4. Браузер (T2) — «лазити по коду, не візуально»

Замість пікселів — **DOM-рівень через Playwright (Chrome DevTools Protocol)**:

- `browser_open(url)`, `browser_read()` → повертає **очищений DOM/текст + список
  інтерактивних елементів** (посилання, інпути, кнопки з їх селекторами) — модель
  «читає сторінку як код».
- `browser_click(selector)`, `browser_fill(selector, value)`, `browser_eval(js)` —
  дії по селектору/JS, миттєво, без скріншотів.
- Playwright може жити **в контейнері** `tools` (або окремому `browser/`), не
  торкаючись хоста. Це і найшвидше, і найнадійніше для веб.

Vision у браузері (T4) вмикається лише якщо сторінка — canvas/непарсибельна.

---

## 5. Безпека (найважливіше — admin PowerShell для LLM)

Дати локальній LLM admin-shell — це фактично root на машині. Мінімальний контур:

- **Дефолт усе вимкнено**: `ENABLE_COMPUTER_USE=false`, `COMPUTER_ALLOW_ADMIN=false`
  (як `ENABLE_CODE_EXEC=false` за замовчуванням).
- **Підтвердження в Telegram** перед будь-якою мутуючою/admin-дією
  (`COMPUTER_REQUIRE_CONFIRM`). Read-only (list/read/screenshot) — без підтвердження.
- **Whitelist** команд/exe; admin — окремий, ще вужчий whitelist.
- **Аудит**: кожна дія в `data/logs/computer.jsonl` (патерн `data/logs/llm.jsonl`) —
  хто, що, який tier, результат.
- **Таймаути** на кожен виклик (як `code_exec_timeout`).
- Лише whitelisted `ALLOWED_USER_IDS`/`ADMIN_USER_IDS` можуть тригерити
  computer-mode (розділення адмінів уже є).

---

## 6. Фази впровадження (мілстоуни)

- **C0 — каркас host-agent** ✅: `hostagent/` FastAPI на хості, `/health`, `/powershell` (non-admin),
  `/fs/*`, `/cli`, токен. Див. `hostagent/README.md`, `hostagent/run.bat`.
- **C1 — toolkit T0/T1** ✅: `run_powershell`, `run_cli`, `fs_*` у `toolkit.py` +
  `AGENT_MODE=computer` + промпт «драбини». Усе під прапорами (`ENABLE_COMPUTER_USE`).
- **C2 — підтвердження + аудит** ✅: inline-кнопки `cmp:Y/N` у gateway, `computer.jsonl`,
  `COMPUTER_REQUIRE_CONFIRM` (read-only без підтвердження).
- **C3 — браузер T2** ✅: Playwright (`browser_*`), confirm на click/fill, `ENABLE_BROWSER=true`. Профіль: [`docs/adr/C3-browser-profile.md`](adr/C3-browser-profile.md).
- **C4 — UIA T3** ✅: `window_list`, `window_focus`, `uia_invoke` (host-agent + toolkit).
- **Rate limit**: `COMPUTER_RATE_LIMIT_PER_HOUR` (мутуючі дії, Redis).
- **C4 — T3 UIA**: pywinauto-керування вікнами/контролами за назвою.
- **C5 — admin-режим** ✅: `COMPUTER_ALLOW_ADMIN` + лише `ADMIN_USER_IDS`; подвійне підтвердження (`cmpA:Y`); audit tier `admin`; runbook [`COMPUTER_ROLLBACK.md`](COMPUTER_ROLLBACK.md).
- **C6 — T4 vision (опційно)**: лише якщо поставлено vision-модель; screenshot→координати
  як останній резерв.

---

## 7. Відкриті рішення (вирішити перед кодом)

- **VRAM під vision (T4)**: на GPU з ~8 ГБ поряд із 7b — тісно. Варіант:
  vision-модель вантажити *on-demand* (вивантажуючи agent-модель), бо T4 — рідкісний резерв.
- **PowerShell admin**: окремий UAC-prompt на хості vs наперед піднятий admin-сервіс
  (зручніше, але небезпечніше).
- **Браузер**: окремий профіль Chrome із логінами (зручно, але агент отримає доступ
  до сесій) vs чистий профіль.

---

## TL;DR

**host-agent на Windows + розширення `tools/` toolkit + новий `AGENT_MODE=computer`
із вшитою «драбиною швидкодії» (PowerShell/CLI → DOM → UIA → і лише потім піксельний
клік)** — усе за прапорами й з підтвердженням у Telegram. Старт — з фази **C0/C1**.
