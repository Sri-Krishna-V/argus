# Argus — Claude Code guide

Enterprise Research Operating System: ingest SEC filings + news → immutable documents →
chunks/embeddings/knowledge graph → cited, confidence-scored investigations. Governing docs:
`docs/DESIGN_BIBLE.md` (principles), `docs/PRD.md` + `docs/PRD-V2.md` (scope),
`docs/ARCHITECTURE.md` (system as built), `docs/adr/` (12 decisions, 0001–0012).
Architecture leads implementation; conflicts with the Design Bible must be documented.

**Status (2026-07):** V1 complete + hardened (ADR-0009). V2 Phase 1 (task DAG + orchestrator)
in flight on `v2-phase1-task-dag`; plan at `docs/superpowers/plans/2026-07-06-v2-phase1-task-dag.md`.

## Commands

```bash
make up        # start Postgres (pgvector) via docker compose, wait for healthy
make migrate   # alembic upgrade head (needed before tests on a fresh DB)
make test      # pytest — 156 tests; requires make up first
make lint      # ruff check + lint-imports (layer contract)
make eval      # score retrieval + investigation quality against evals/golden.json
make api       # uvicorn argus.main:app --reload (API + UI at :8000)
make worker    # job outbox loop + connector scheduler (JSON logs)
make stack / make stack-down   # full containerized stack (postgres + api + worker)
make backup / make restore     # pg_dump + raw-store tarball; restore from backup files
uv run alembic revision -m "..."           # new migration (hand-written, numbered 000N_slug)
uv run pytest tests/test_pipeline.py -v    # one file; -k <expr> for one test
```

CLI: `argus status | search | ingest | reprocess | retry-dead | eval | worker` (src/argus/cli.py).

## Hard rules

- **Layer direction** (enforced by import-linter in pyproject.toml):
  `ui/api → investigations → agentruntime → research → dataplatform → knowledge → observability → core`.
  AI code (ADK/Gemini) exists only in `agentruntime/`; `adapter.py` is the only module that imports ADK.
- **Documents are immutable** (DB trigger). Never write an UPDATE path for `documents`; derived
  artifacts are keyed on `(document_id, stage, pipeline_version)` and re-derivable from the raw store.
- **Events are append-only** (`events` table, DB trigger); `jobs` is a disposable outbox derived from it.
- **Every AI output carries citations**; evidence without a chunk reference is rejected.
- **Confidence is computed, never LLM-generated** (source diversity, recency, stance agreement).
- **Sync code only** (ADR-0004): sync SQLAlchemy, sync httpx, `def` endpoints. No async.
- **DB clock is the only time authority** for queue predicates — `func.now()`, never
  `datetime.now()` (WSL2 wall clock steps backward up to 1.8s; see commit 9b1d07e).
- Jobs: `pending → running → completed | pending(retry, exp backoff) | dead` at max_attempts
  (`argus retry-dead`). Stuck `running` jobs reaped after ARGUS_JOB_LEASE_SECONDS (600) — safe
  because stages are idempotent on (document_id, stage, pipeline_version).

## Conventions

- src layout: code in `src/argus/<layer>/`; tests mirror it in `tests/`
- Migrations hand-written and numbered (`migrations/versions/0001_…`–`0006_…`), no autogenerate
- Settings via `argus.core.config.get_settings()`, env prefix `ARGUS_`, `.env` supported —
  config.py is the full catalog; add tunables there, not as constants
- DB access via `argus.core.db.session_scope()` context manager
- Structured JSON logs: `logger.info(msg, extra={"context": {...}})`
- Deliberate simplifications carry `# ponytail:` comments naming the ceiling + upgrade path

## Testing

- `tests/conftest.py` auto-creates an `argus_test` DB, migrates once per session, wraps each
  test in a rolled-back transaction — no manual cleanup.
- Key fixtures: `db_session`, `fake_embeddings` (ARGUS_EMBEDDING_PROVIDER=fake),
  `seeded_companies` (fake tickers ZZZT/ZZAP — never real ones), `drain_queue()`.
- All AI paths test against a deterministic fake adapter; live LLM runs need
  ARGUS_OPENROUTER_API_KEY in `.env` (not currently set — live paths unverified).
- Cover failure modes and boundaries, not just happy paths.

## Gotchas

- No CI — `make test && make lint` locally is the gate before any commit.
- Empty ARGUS_API_KEY = dev mode (no auth); non-empty enables constant-time bearer check.
- WSL2: if port 5432 conflicts, DB may run on 15432 — check `.env` / docker-compose.
- Task readiness in `investigation_tasks` is **derived on read** from dependency states,
  never stored (migration 0006) — don't add a "ready" column.
- `orchestrator._advance()`'s fan-in readiness check takes `.with_for_update()` on the
  pending sibling row(s) it evaluates — required because two workers can complete
  sibling tasks concurrently (ADR-0010) and, without the lock, each can see the other
  as "not complete yet" under READ COMMITTED, so neither enqueues the dependent (see
  ARCHITECTURE.md §3 "Fan-in concurrency safety", commit 85d5452). Don't remove it to
  "simplify" the query.
- Connectors: SEC fetches allowlisted to `*.sec.gov`; downloads capped at ARGUS_MAX_FETCH_BYTES.
