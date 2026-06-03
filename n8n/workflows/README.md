# n8n workflow: agent_loop

Оркестратор. Gateway шле `POST /webhook/agent`, n8n делегує всю «мозкову» логіку
в Tools-сервіс (`/agent`) і повертає текст назад.

> **Архітектурне рішення (Фаза 6).** Памʼять + маршрутизація CHAT/AGENT + тул-луп
> живуть у Python (`tools/app/agent.py`), а не розмазані по нодах n8n. Причина: без
> Docker складне багатонодове розгалуження неможливо протестувати, тоді як Python
> покривається юніт-тестами. n8n лишається єдиною точкою оркестрації (тут зручно
> згодом додати логування, нотифікації, rate-limit) — але важка логіка типізована й тестована.
> Memory-сервіс і далі використовується — його тепер кличе `tools/agent`, а не n8n.

## Імпорт
1. Відкрий n8n: http://localhost:5678 (логін з `.env`: `N8N_BASIC_AUTH_USER` / `N8N_BASIC_AUTH_PASSWORD`).
2. Меню (⋮) → **Import from File** → обери `agent_loop.json`.
3. Увімкни тумблер **Active**. Без цього працює лише тестовий шлях `/webhook-test/agent`,
   а Gateway звертається на продакшн `/webhook/agent`.

## Кроки (Фаза 6 — делегування в Tools/agent)
Лінійний потік: **Webhook → Agent → Respond**.

1. **Webhook** (POST `agent`, Respond = "Using Respond to Webhook node"):
   приймає `{user_id, chat_id, text, type, mode}` (дані тіла — у `$json.body`).
2. **Agent** (HTTP → `{{$env.TOOLS_URL}}/agent`): шле `{user_id, text}`. Tools-сервіс
   усередині робить: пошук контексту в Memory → вибір моделі за `AGENT_MODE`
   (chat/agent/hybrid) → CHAT-відповідь **або** тул-луп на AGENT-моделі (макс 5 ітерацій,
   інструменти calc/web_search/web_fetch/code_exec) → запис історії в Memory. Повертає
   `{text, mode, iters}`. Таймаут 280с (CPU-інференс повільний).
3. **Respond**: повертає `{ "text": $('Agent').item.json.text }` у Gateway (з фолбеком).

## Доступ до env у виразах
Workflow читає лише `$env.TOOLS_URL`. У compose виставлено
`N8N_BLOCK_ENV_ACCESS_IN_NODE=false`, а змінні приходять через `env_file: .env`.
(Ollama/Memory/моделі тепер конфігурує Tools-сервіс, не workflow.)

## Що далі
- **Фаза 7:** rate-limit (Redis), error handling, circuit breaker, healthchecks, фінальний README.

> Якщо імпорт лається на `typeVersion` ноди — створи ноди вручну за кроками вище
> (назви полів ті самі). n8n час від часу змінює версії нод між релізами.
