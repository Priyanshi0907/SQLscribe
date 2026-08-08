FROM python:3.12-slim

WORKDIR /app

# System deps for psycopg2 (PostgreSQL) — psycopg2-binary avoids needing
# libpq-dev, but gcc is still occasionally needed for source builds on
# certain platforms/wheel mismatches, so keep it lightweight but present.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite-backed local state (auth.db, history.db, schema_meta.db, the
# seeded demo db, uploaded files) all live under /app/data — mount this
# as a volume in production so it survives container restarts/redeploys.
RUN mkdir -p /app/data /app/data/uploads /app/data/local_sources

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
