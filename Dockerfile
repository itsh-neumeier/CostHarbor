FROM python:3.12-slim AS base

# WeasyPrint system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpango-1.0-0 libpangocairo-1.0-0 libgdk-pixbuf2.0-0 \
    libffi-dev libcairo2 libglib2.0-0 \
    fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r costharbor && useradd -r -g costharbor -m costharbor

WORKDIR /app

COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[dev]" 2>/dev/null || pip install --no-cache-dir .

COPY alembic.ini ./
COPY alembic/ ./alembic/
COPY app/ ./app/

RUN mkdir -p /data/uploads /data/documents && \
    chown -R costharbor:costharbor /app /data

USER costharbor

EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host ${APP_HOST:-0.0.0.0} --port ${APP_PORT:-8000}"]
