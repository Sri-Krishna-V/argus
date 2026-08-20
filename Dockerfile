FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

RUN useradd --create-home --uid 1000 app

WORKDIR /app

# dependency layer: cached until pyproject.toml/uv.lock change
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

# project layer
COPY src/ src/
COPY migrations/ migrations/
COPY alembic.ini ./
COPY evals/ evals/
RUN uv sync --frozen --no-dev
COPY --from=web-build /web/dist web/dist

# Named-volume mount points are created here so docker initializes each volume with
# app:app ownership — a mount point missing from the image is created root-owned and
# the container user cannot write it. That silently broke ingestion (raw store) and
# forced an 83 MB model re-download per process (fastembed cache).
RUN mkdir -p /app/data /home/app/.cache \
    && chown -R app:app /app /home/app
USER app
ENV PATH="/app/.venv/bin:$PATH"

# forwarded-allow-ips lists the proxy hop (loopback + the docker bridge range), NOT
# "*": uvicorn then scans X-Forwarded-For right-to-left and takes the first untrusted
# address, so a client cannot forge its own rate-limit bucket key by prepending one.
# "*" would trust the leftmost, client-supplied entry instead.
CMD ["uvicorn", "argus.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log", \
     "--forwarded-allow-ips", "127.0.0.1,172.16.0.0/12"]
