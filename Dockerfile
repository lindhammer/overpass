FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright \
    PYTHONPATH=/app

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY overpass ./overpass

RUN pip install -e . \
    && python -m playwright install --with-deps chromium

RUN useradd --create-home --shell /usr/sbin/nologin overpass \
    && mkdir -p /app/output /app/.cache /ms-playwright \
    && chown -R overpass:overpass /app /ms-playwright

USER overpass

CMD ["overpass-worker"]
