FROM node:22-slim AS web-build
WORKDIR /web
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
RUN npm run build

FROM python:3.12-slim
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# app user matches the typical host uid (1000) so the ./data bind mount stays writable
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

RUN chown -R app:app /app
USER app
ENV PATH="/app/.venv/bin:$PATH"

CMD ["uvicorn", "argus.main:app", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
