FROM python:3.11-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DASH_HOST=0.0.0.0 \
    DASH_PORT=8050 \
    DASH_DEBUG=false \
    DATA_MODE=auto \
    DUCKDB_PATH=/app/data/vn30f1m.duckdb

ARG APP_VERSION=0.1.0
ARG GIT_SHA=unknown
ENV APP_VERSION=${APP_VERSION} GIT_SHA=${GIT_SHA}

WORKDIR /app

# Update Debian security packages, including zlib1g
RUN apt-get update \
    && apt-get install -y --no-install-recommends zlib1g \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt

# Upgrade vulnerable Python tooling and install application dependencies
RUN pip install --no-cache-dir --upgrade \
        pip setuptools wheel jaraco.context \
    && pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY assets ./assets
COPY run.py ./run.py

RUN mkdir -p /app/data \
    && useradd --create-home --uid 10001 appuser \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8050

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8050/health', timeout=3)"

CMD ["python", "-m", "app.main"]
