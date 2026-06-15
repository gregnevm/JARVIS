# --- Node.js LTS stage: дає node/npm/npx для stdio MCP-серверів (Platform P5 Gateway).
# Той самий Debian bookworm, що й python:3.11-slim → glibc сумісний, можна копіювати бінарник.
FROM node:22-bookworm-slim AS node

FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

COPY tools/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && playwright install chromium --with-deps

# Node.js LTS — потрібен MCP Gateway (P5), щоб піднімати stdio-сервери через `npx -y ...`.
# Копіюємо з node:22-slim (без apt-кешу й build-tools) → +~110 МБ, образ лишається стрункий.
COPY --from=node /usr/local/bin/node /usr/local/bin/node
COPY --from=node /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -sf ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
    && ln -sf ../lib/node_modules/npm/bin/npx-cli.js /usr/local/bin/npx \
    && node --version && npm --version && npx --version

COPY jarvis_core /app/jarvis_core
COPY tools/app ./app
ENV PYTHONPATH=/app

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
