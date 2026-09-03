# syntax=docker/dockerfile:1.7
FROM node:22-bookworm-slim AS frontend
WORKDIR /build/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# L'image officielle Playwright fournit Chromium et ses bibliothèques système. Sa version doit
# rester alignée avec la dépendance Python verrouillée lors de la construction.
FROM mcr.microsoft.com/playwright/python:v1.62.0-noble AS runtime
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONPATH=/app/src \
    TESTPILOT_DATA_DIR=/var/lib/testpilot
WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends postgresql-client \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml requirements.lock alembic.ini ./
COPY alembic/ alembic/
COPY src/ src/
COPY scripts/ scripts/
RUN python -m pip install --no-cache-dir -r requirements.lock \
    && python -m pip install --no-cache-dir --no-deps .
COPY --from=frontend /build/frontend/dist frontend/dist/

RUN install -d -o pwuser -g pwuser /var/lib/testpilot
USER pwuser
EXPOSE 8000
CMD ["python", "-m", "uvicorn", "testpilot.api.app:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--proxy-headers", "--forwarded-allow-ips", "127.0.0.1"]
