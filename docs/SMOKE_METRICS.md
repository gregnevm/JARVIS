# Smoke — метрики Mini App (5.3)

1. `docker compose up -d tools gateway redis`
2. Надішли боту 2–3 повідомлення (chat + agent з tool, напр. «порахуй 2+2»).
3. Відкрий Mini App `/app` → секція **Метрики**:
   - Turn p50/p95 > 0
   - RAG hit rate оновився після запитів з памʼяттю
   - Tools показує `calc` або інший викликаний інструмент

API: `GET http://localhost:8200/dashboard` → поле `metrics`.
