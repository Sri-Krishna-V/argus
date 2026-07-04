# Argus — Claude Code guide

Enterprise Research Operating System. Governing docs: `docs/DESIGN_BIBLE.md` (principles),
`docs/PRD.md` (scope), `docs/ARCHITECTURE.md` (system as built), `docs/adr/` (decisions).
Architecture leads implementation; conflicts with the Design Bible must be documented.

## Commands

```bash
make up        # start Postgres (pgvector) via docker compose, wait for healthy
make migrate   # alembic upgrade head
make test      # pytest
make lint      # ruff check + lint-imports (layer contract)
uv run alembic revision -m "..."   # new migration (hand-written, numbered 000N_slug)
```

## Hard rules

- **Layer direction** (enforced by import-linter in pyproject.toml):
  `ui/api → investigations → agentruntime → research → dataplatform → knowledge → observability → core`.
  AI code (ADK/Gemini) exists only in `agentruntime/`; `adapter.py` is the only module that imports ADK.
- **Documents are immutable.** Never write an UPDATE path for `documents`; derived artifacts
  are keyed on `(document_id, stage, pipeline_version)` and re-derivable from the raw store.
- **Events are append-only** (`events` table); `jobs` is a disposable outbox derived from it.
- **Every AI output carries citations**; evidence without a chunk reference is rejected.
- **Confidence is computed, never LLM-generated.**
- Sync code only (ADR-0004): sync SQLAlchemy, sync httpx, `def` endpoints.

## Conventions

- src layout: code in `src/argus/<layer>/`; tests mirror it in `tests/`
- Migrations are hand-written and numbered (`0001_enable_pgvector.py`), no autogenerate
- Settings via `argus.core.config.get_settings()`, env prefix `ARGUS_`, `.env` supported
- DB access via `argus.core.db.session_scope()` context manager
- Structured JSON logs: pass structured fields as `logger.info(msg, extra={"context": {...}})`
