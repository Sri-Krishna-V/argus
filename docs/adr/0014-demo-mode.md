# ADR-0014: Public demo mode

## Status

Accepted

## Context

Argus runs in production (VPS API behind Caddy, SPA on Vercel), but nobody outside
the deployment could see it work. `ARGUS_API_KEY` gates all of `/api/*`, so a visitor
landed on the SPA's key prompt; the database was empty because the raw store bind
mount was owned by a host uid the container user didn't have (`PermissionError:
'data/raw'` on every connector pass); and `ARGUS_OPENROUTER_API_KEY` was unset, so
the investigation flow — plan, evidence, report, confidence — could not run at all.

The requirement is that someone interested in the product can review every flow it
has, without an API key, without spending LLM tokens, and without being able to alter
or break the deployment.

Handing out the write key, or opening writes anonymously, fails the last constraint:
`POST /api/investigations` runs an investigation synchronously in-request and would be
both a cost and an availability lever for anyone with curl.

## Decision

Three independent, separately-toggleable pieces.

**1. A canned agent runtime.** `ARGUS_LLM_PROVIDER=demo` makes
`adapter.run_structured` — still the only entry point to the AI boundary
([ADR-0005](0005-agent-runtime-adk.md)) — serve every call from
`agentruntime/canned.py`: keyword-derived plans, hash-bucketed stances, and drafts
whose `[chunk:<uuid>]` markers are parsed back out of the prompt. Everything below
the LLM is the production path: retrieval, near-duplicate dedup, source ranking,
context fusion, the citation gate, and computed confidence. Only the prose is canned.

**2. Demo access mode.** `ARGUS_DEMO_MODE=1` makes the `request_context` middleware
skip the API-key check for `GET`/`HEAD`/`OPTIONS` on `/api/*`. Every other method
still requires the key, unchanged. `GET /api/search` gains a per-IP rate limit
(`ARGUS_RATE_LIMIT_SEARCH_PER_MINUTE`, default 60) because it is the one anonymous
endpoint that costs real CPU — a query embedding plus a pgvector scan. `/health`
reports `demo` so the SPA can render its write affordances disabled rather than
letting a visitor discover read-only mode via a 401.

**3. `argus demo seed`.** Builds the demo investigation set over whatever the
connectors have ingested, driven through the same functions the UI calls — the API
route handlers, `engine`, `lifecycle`, the jobs outbox. It covers all seven lifecycle
states, a branch and a link, analyst reviews and annotations, a second report version
from a refresh, and two dead jobs whose Retry genuinely re-runs an idempotent stage.

The raw store also moved from the `./data` bind mount to a named volume that the
image creates (`mkdir -p /app/data` before `chown app:app`), so the container user
owns it on any host regardless of the host uid. That was the actual cause of the
empty database, and it is a portability fix, not a demo concern.

## Consequences

- **Canned output must never read as model analysis.** Every `ExecutionRecord` and
  `Report` carries `model="canned-demo"`, the narrative and executive summary end in
  an explicit "no language model was called" sentence, and the SPA shows a demo
  banner. A live deployment sets `ARGUS_LLM_PROVIDER=openrouter` and none of this
  applies.
- **Anonymous reads expose what the read endpoints expose**: document metadata,
  chunk excerpts of public filings and news, dead-job `last_error` strings (which name
  internal exception types), and the full `investigation_events` payloads — including
  each `ExecutionRecord`'s `prompt`. On this demo that audit trail is the point, and
  the prompts are canned instructions over public filings. On a deployment running a
  live model it would publish every prompt verbatim, so `ARGUS_DEMO_MODE=1` must not be
  combined with `ARGUS_LLM_PROVIDER=openrouter` without accepting that. Demo mode is
  opt-in per deployment rather than a default for exactly this reason.
- **The per-IP rate limit depends on the proxy hop being trusted.** The API binds to
  loopback behind Caddy, so uvicorn runs with
  `--forwarded-allow-ips 127.0.0.1,172.16.0.0/12` and resolves the client from
  `X-Forwarded-For` by scanning right-to-left for the first untrusted address — a
  client cannot forge its own bucket key by prepending entries. Without that flag every
  anonymous visitor would share one bucket and two concurrent searchers would 429 each
  other; with `*` the leftmost, client-supplied entry would be trusted instead.
- **The demo is genuinely read-only**, so the flows that exist only as API writes
  (annotate, review evidence, pause/resume/cancel) are reviewable as seeded data and
  in the activity timeline, not by clicking. Opening a narrow anonymous write
  allowlist with a nightly reseed is a deliberate follow-up, not part of this ADR.
- **`argus demo seed --reset` uses `TRUNCATE`**, because `investigation_events`
  carries the append-only trigger ([ADR-0003](0003-events-and-outbox.md)) and a
  row-level delete is correctly rejected. TRUNCATE is not reachable from the
  application: it lives in operator tooling, behind a CLI confirmation, and never
  touches documents, chunks or the raw store. On a non-demo deployment there is no
  reason to run it.
- Investigation questions come from `evals/golden.json`, so `make eval` scores the
  same set a visitor is looking at.
