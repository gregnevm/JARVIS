# JARVIS API — Quickstart (Стовп A)

OpenAI-сумісний `/v1` + керовані ключі. Drop-in для OpenAI SDK: міняєш лише
`base_url` і `api_key`.

> Увімкнення: `ENABLE_OPENAI_API=true` + `OPENAI_API_KEY=<root-key>` у `.env`.
> Self-hosted = один synthetic org; ключі опційні (root-ключа достатньо).

## 1. Згенерувати ключ (`sk-jarvis-…`)

Керування ключами — лише **root**-ключем (`OPENAI_API_KEY`). Ключ показується **один раз**.

```bash
curl -s https://YOUR_HOST/saas/api/keys \
  -H "Authorization: Bearer $ROOT_KEY" \
  -H "Content-Type: application/json" \
  -d '{"name":"my-app","scopes":["chat","embeddings","jobs"]}'
# → {"id":"…","key":"sk-jarvis-…","scopes":[…], …}   ← скопіюй "key" зараз
```

Список / відкликання:

```bash
curl -s https://YOUR_HOST/saas/api/keys -H "Authorization: Bearer $ROOT_KEY"
curl -s -X DELETE https://YOUR_HOST/saas/api/keys/<id> -H "Authorization: Bearer $ROOT_KEY"
```

## 2. OpenAI Python SDK (drop-in)

```python
from openai import OpenAI

client = OpenAI(base_url="https://YOUR_HOST/v1", api_key="sk-jarvis-…")

# chat
print(client.chat.completions.create(
    model="jarvis",
    messages=[{"role": "user", "content": "привіт"}],
).choices[0].message.content)

# embeddings
vec = client.embeddings.create(model="nomic-embed-text", input="hello").data[0].embedding

# моделі
print([m.id for m in client.models.list().data])
```

## 2b. Node / TypeScript (openai-node)

Той самий drop-in — лише `baseURL` + `apiKey`:

```js
import OpenAI from "openai";

const client = new OpenAI({ baseURL: "https://YOUR_HOST/v1", apiKey: "sk-jarvis-…" });

const r = await client.chat.completions.create({
  model: "jarvis",
  messages: [{ role: "user", content: "привіт" }],
});
console.log(r.choices[0].message.content);

// embeddings
const e = await client.embeddings.create({ model: "nomic-embed-text", input: "hello" });
```

## 3. Endpoints (`/v1`)

| Метод | Шлях | Scope | Опис |
|-------|------|-------|------|
| POST | `/v1/chat/completions` | `chat` | Чат (+ SSE `stream:true`) |
| POST | `/v1/responses` | `chat` | Агентний (tool-use), `input` рядок або item-список |
| POST | `/v1/embeddings` | `embeddings` | `nomic-embed-text`, `input` рядок або список |
| POST | `/v1/jobs` | `jobs` | Async-задача → `id` |
| GET | `/v1/jobs/{id}` | `jobs` | Статус async-задачі |
| GET | `/v1/usage?days=N` | будь-який | Лічильники запитів по ключу |
| GET | `/v1/models` | будь-який | Каталог моделей |

Помилки — у форматі OpenAI: `{"error":{"message","type","code"}}`
(`authentication_error` 401/403, `rate_limit_error` 429, `invalid_request_error`,
`api_error` 5xx). Повна схема — `GET /openapi.json`.

## 4. curl

```bash
curl -s https://YOUR_HOST/v1/chat/completions \
  -H "Authorization: Bearer sk-jarvis-…" -H "Content-Type: application/json" \
  -d '{"model":"jarvis","messages":[{"role":"user","content":"hi"}]}'
```

## 5. Postman / Insomnia

Готова колекція: [`sdk/jarvis-api.postman_collection.json`](../sdk/jarvis-api.postman_collection.json).
Імпортуй, постав змінні `base_url`, `api_key` (`sk-jarvis-…`) і `root_key` — усі `/v1`
ендпоінти + керування ключами вже налаштовані.

Деталі фаз і статус — [`API_PLATFORM_ROADMAP.md`](API_PLATFORM_ROADMAP.md).
