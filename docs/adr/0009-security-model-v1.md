# ADR-0009: Security model V1 — hardened single-key, internal-network bar

**Status:** Accepted · **Serves:** Design Bible §15 (AI boundary), PRD §15 (risks), ADR-0008 (deferrals)

## Context

V1 ships with real ingested data, a live LLM spend path, and a server-rendered UI. It is a
single-analyst tool intended to run on an internal network behind a reverse proxy — not an
internet-facing multi-tenant service. The security bar must match that deployment: close
every outright bug, add the controls that are cheap and load-bearing at this scale, and
name what is deliberately deferred (and its trigger) rather than half-building it.

## Decision

**Authentication is one shared secret.** When `ARGUS_API_KEY` is set, every `/api/*`
request must present it (`X-API-Key` or `Bearer`), compared in constant time
(`secrets.compare_digest`). Empty key disables auth — the dev default. Health probes and
the UI stay open; the UI is read/create on the same trust level as the network. Multi-user
auth remains deferred per ADR-0008 (trigger: a second user or external access).

**Per-layer controls** (each lives in exactly one place):

| Layer | Control | Where |
|---|---|---|
| API | Constant-time key check, security headers (CSP self-only, nosniff, DENY framing), request-ID | `request_context` middleware, `main.py` |
| API | Body size cap (413, `ARGUS_MAX_BODY_BYTES`), per-IP token bucket on investigation creates (429, `ARGUS_RATE_LIMIT_INVESTIGATIONS_PER_MINUTE`) — the endpoint that burns LLM tokens | same middleware |
| API | Bounded query params and length-capped inputs (Pydantic/`Query`) | `api/routes.py` |
| UI | LLM narrative HTML-escaped before citation markup; citation `href` only rendered for `http(s)` schemes (feed-supplied URLs are publisher-controlled) | `ui/views.py` |
| Agent runtime | Per-call timeout + bounded retries on the LLM call (`ARGUS_LLM_TIMEOUT_SECONDS`); excerpts delimited and declared data-not-instructions; structured-output validation; citations verified against the retrieved chunk set; confidence computed, never LLM-generated | `agentruntime/`, `investigations/engine.py` |
| Connectors | Download size cap (`ARGUS_MAX_FETCH_BYTES`), 30s timeouts, SEC fetches allowlisted to `*.sec.gov` | `connectors/` |
| Data | Parameterized SQL only; raw store is content-addressed (no path from external input); documents immutable; server-side `statement_timeout` (`ARGUS_DB_STATEMENT_TIMEOUT_MS`) | `core/db.py`, `dataplatform/storage.py` |
| Infra | Non-root container, Postgres bound to loopback, password via `ARGUS_POSTGRES_PASSWORD`, api healthcheck on `/health/ready`, `uv sync --frozen` builds | `Dockerfile`, `docker-compose.yml` |

**Prompt injection stance:** ingested documents (SEC filings, RSS articles) are untrusted
input to LLM prompts. The primary defense is structural, not textual: an injected
instruction cannot fabricate a citation (markers must resolve to actually-retrieved
chunks) and cannot inflate confidence (computed deterministically). Delimiting excerpts
raises the bar; the residual risk — stance misclassification steering a report's tone —
is recorded in RISKS.md and bounded by the mandatory contradicting-evidence section.

## Deferred (named, with triggers)

- **TLS** — terminate at a reverse proxy in front of the app; in-app TLS when the proxy
  assumption breaks.
- **Multi-user auth / RBAC / per-user keys** — ADR-0008; trigger: second user.
- **Separate DB roles** (migrate vs runtime vs read-only) — trigger: more than one service
  or person holding credentials.
- **Secrets manager** — `.env` + env vars are fine for one box; trigger: more than one
  deployment environment.
- **Log redaction filter** — nothing secret is logged today and logging is
  structured/reviewed; trigger: third-party log shipping.
- **Distributed rate limiting** — in-process bucket assumes one API replica; trigger:
  horizontal API scaling (move to the proxy or Redis).
- **Container sandboxing** (read-only fs, seccomp, dropped caps) — trigger: running
  untrusted plugins/connectors.

## Consequences

- The whole authn surface is ~15 lines in one middleware — auditable at a glance.
- Every knob is an `ARGUS_` setting with a safe default; production hardening is
  configuration, not code.
- Anyone deploying past the internal-network assumption must revisit the deferred list
  first; the triggers say when.
