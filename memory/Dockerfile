FROM python:3.11-slim

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Build-контекст = repo root (compose: context: .) — щоб додати спільний jarvis_core.
COPY memory/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY memory/alembic.ini .
COPY memory/migrations ./migrations
# Спільний домен (Context Passport P9/P10 тощо) — pure-import, без нових pip-залежностей.
COPY jarvis_core /app/jarvis_core
COPY memory/app ./app

EXPOSE 8100
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8100"]
