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
        xvfb \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY overpass ./overpass
COPY deploy/docker-entrypoint.sh /usr/local/bin/overpass-docker-entrypoint

RUN pip install -e . \
    && python -m playwright install --with-deps chromium

RUN useradd --create-home --shell /usr/sbin/nologin overpass \
    && mkdir -p /app/output /app/.cache /ms-playwright /tmp/.X11-unix \
    && chmod 1777 /tmp/.X11-unix \
    && chmod +x /usr/local/bin/overpass-docker-entrypoint \
    && chown -R overpass:overpass /app /ms-playwright

USER overpass

ENTRYPOINT ["overpass-docker-entrypoint"]
CMD ["overpass-worker"]
