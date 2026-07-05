# Frontend Revamp — CLI + Dashboard

**Date:** 2026-07-05
**Status:** Approved design, pending implementation plan

## Goal

Two frontend surfaces, two personalities:

- **CLI** — fun and colorful. Rich-powered output for humans operating the pipeline.
- **Dashboard** — enterprise standard. React SPA replacing the htmx UI.

## Decisions made

| Decision | Choice |
|---|---|
| Dashboard stack | React SPA (replaces Jinja2 + htmx) |
| React flavor | Vite + React, static build — no Node in production |
| CLI scope | Restyle existing commands + `status` and `search` |
| htmx UI fate | Deleted entirely |
| Governance | ADR-0010 documents the deviation from the Phase-7 no-build decision |

## Part 1 — CLI (`src/argus/cli.py`)

`rich` is already a transitive dependency (via typer 0.26 → rich 15). **No new Python dependencies.**

### Global

- Module-level `rich.console.Console` with a small Argus theme (accent, success, error, warn styles).
- Typer app configured with `rich_markup_mode="rich"` so `--help` renders styled panels; pretty tracebacks stay on typer defaults.

### Restyled commands

| Command | Treatment |
|---|---|
| `ingest` | `console.status()` spinner while the connector pass runs; result summary line with connector name highlighted |
| `reprocess` | colored confirmation: stage, doc count, pipeline version highlighted |
| `retry-dead` | colored result count; errors in red via stderr console |
| `eval retrieval` | per-question rich table (id, rank; miss in red, rank ≤ 3 in green); summary metrics line with green/amber/red thresholds |
| `eval investigation` | per-investigation rich table (citations, coverage, stances); colored summary metrics |
| `worker` | **untouched** — structured JSON logs are for machines |

### New commands

- **`argus status`** — one-screen ops panel: job queue counts by status (color per status), dead-job count, total documents, last ~10 pipeline runs (stage, status, duration). Terminal twin of the Pipeline page. Reads via `session_scope()`, same queries as the pipeline API.
- **`argus search QUERY`** — hybrid retrieval from the terminal: rich table of results (score, doc type, title/snippet, document id). Options: `-k` (default 10). Reuses `argus.research.retrieval.search`.

Both commands are read-only.

## Part 2 — Dashboard SPA (`web/`)

### Stack

- React 19 + TypeScript
- Vite 7 (build + dev server)
- Tailwind CSS v4
- shadcn/ui components
- TanStack Router (type-safe file-based routes)
- TanStack Query v5 (fetching, caching, invalidation)
- Recharts via shadcn chart components (pipeline visuals)

Pinned via `package-lock`/`pnpm-lock` committed in `web/`.

### Application chrome

- Sidebar navigation (Investigations, Search, Pipeline) + header with theme toggle.
- Dark mode default, light mode available (class-based Tailwind theming).
- Loading skeletons for all data views; toasts for mutations; error boundaries per route.

### Pages

**Investigations (`/`)**
- Data table: question, status badge, stale badge (new evidence available), confidence bar, created date. Sortable.
- "New investigation" dialog (question required ≤2000 chars, optional hypothesis) → POST `/api/investigations` → navigate to detail.

**Investigation detail (`/investigations/$id`)**
- Report narrative with `[chunk:<uuid>]` markers rendered as numbered superscript citations; citation list with popover previews; only `http(s)` URLs rendered as links (same XSS rule as the htmx view — markers resolved client-side from the citations payload, narrative rendered as text, never as HTML).
- Hypotheses with computed-confidence meters.
- Evidence in three stance columns: supporting / contradicting / unknown.
- Linked investigations list + link-creation action.
- Refresh and Replay actions with pending states.

**Search (`/search`)**
- Query input, company filter (autocomplete via `/api/companies`), doc-type filter.
- Result cards: score, doc type, snippet, link to document metadata.

**Pipeline (`/pipeline`)**
- Queue status cards (pending/running/failed/dead/done counts).
- Recent pipeline runs table + a small runs-over-time / duration chart.
- Dead-letter table with per-job retry action.
- Document count stat.

### Data & API changes (additive only)

The SPA consumes the existing JSON API. Gaps to close with small additive changes:

1. Investigation detail payload: include hypotheses and links (extend `/api/investigations/{id}` or add sub-resources — implementer's choice, additive either way).
2. Report payload: include resolved citations (chunk id → document title/url/snippet) so the client can number markers without a second round trip.
3. Dead jobs: `GET /api/jobs?status=dead` (paginated, reuses existing pagination bounds).
4. Retry dead job: `POST /api/jobs/{id}/retry` (same logic as `argus retry-dead --job-id`).
5. Stale flag (`has_new_evidence`) included in investigation list/detail payloads.

All endpoints stay sync `def` (ADR-0004) and respect the existing opt-in API-key auth.

### Auth

When `ARGUS_API_KEY` auth is enabled: any 401 routes the SPA to a key-entry screen; key stored in `localStorage`; a fetch wrapper injects `X-API-Key` on every request. When auth is disabled the screen never appears.

### Serving & build

- `vite build` → `web/dist`.
- FastAPI mounts `web/dist` at `/` (StaticFiles) with SPA fallback to `index.html` for client-side routes. API routes keep precedence.
- Dev: `vite dev` on its own port, proxying `/api` + `/health` to `:8000`.
- Docker: multi-stage — a `node` stage runs `vite build`, the final Python image copies `web/dist` only. **No Node in the production image.**
- CSP/security headers: adjust the existing security-header middleware only as far as the SPA needs (script-src 'self' still holds — Vite emits hashed static files, no inline scripts).
- `src/argus/ui/templates/`, `ui/views.py`, `ui/static/htmx.min.js` deleted; `ui/` keeps only the static-mount wiring for `web/dist`.

## Part 3 — Governance, tooling, tests

- **ADR-0010**: "React SPA dashboard" — supersedes the Phase-7 no-build decision; rationale: enterprise UI ceiling, typed API consumption; consequences: Node required at build time only.
- **Makefile**: `make web` (install + build), `make web-dev` (vite dev server). `make stack` builds the SPA via the multi-stage Dockerfile.
- **Tests**:
  - Existing htmx view tests deleted with the views.
  - pytest: SPA shell served at `/`; new/extended API endpoints covered (including auth-enabled 401 behavior and retry-job edge cases: unknown id, non-dead job).
  - CLI: `status` and `search` smoke tests via `typer.testing.CliRunner`.
  - Frontend gate: `tsc --noEmit` + `vite build` must pass (wired into `make web`). No JS unit-test framework in v1 — the API contract is covered by pytest.

## Out of scope (v1)

- No TUI dashboard (textual), no investigation creation from CLI.
- No SSR, no Next.js, no marketing pages.
- No user accounts/roles — auth remains the existing single API key.
- No live websockets; freshness via TanStack Query polling where useful (e.g. pipeline page refetch interval).

## Success criteria

- `argus status` / `argus search` work against a live DB and look good in a normal terminal.
- Dashboard serves from the single Python container, all four pages functional against real data.
- `make test`, `make lint`, frontend `tsc` + build all green.
- ADR-0010 committed; layer contract (import-linter) untouched.
