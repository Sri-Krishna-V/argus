# ADR-0008: Deferred capabilities — named decisions, not omissions

**Status:** Accepted · **Serves:** Design Bible §19 (100-million-document test), §22 (roadmap)

## Context

A V1 at this scale can look "incomplete" next to systems that carry Neo4j, Kafka, a
dedicated vector DB, OCR, ML NER, and multi-user auth on day one. Each of those is real
infrastructure with real operational cost, and none of them pay for themselves yet. This
ADR names what V1 defers, why deferring is the correct call now, and the concrete signal
that would flip the decision — so the absence reads as engineering judgment, not gaps.

## Decision

For each capability, V1 ships the deterministic, lowest-operational-cost substitute and
keeps the storage/interface boundary where a swap would land later.

| Deferred | V1 does instead | Why correct at this scale | Trigger to revisit |
|---|---|---|---|
| Dedicated vector DB | `pgvector` + HNSW index in the same Postgres instance | One database to operate, back up, and reason about; HNSW recall is fine below tens of millions of vectors | Corpus size or query throughput outgrows HNSW recall/latency in Postgres |
| External broker (Kafka/Redis Streams) | Append-only `events` table + `jobs` outbox, `SKIP LOCKED` claiming (ADR-0003) | One consumer (the worker); a broker adds an operational service to buy nothing | A second service needs to consume events independently, or throughput exceeds single-DB polling |
| Neo4j / graph DB | `graph_nodes`/`graph_edges` tables + recursive CTEs | Traversal depth needed today (entity → filings → mentions) is shallow; CTEs keep it in one datastore | Traversals need graph algorithms (community detection, shortest-path at scale) or CTE depth/latency becomes a bottleneck |
| PDF/OCR parsing | HTML/plaintext connectors only (SEC EDGAR HTML, RSS) | Every current source ships HTML; OCR is a different reliability problem (layout, quality, cost) not needed by any connector yet | A required source only publishes as PDF/scanned image |
| ML-based NER | Deterministic ticker/canonical-name matching with precision guards | Precision matters more than recall for a citation-gated system; a wrong entity link is worse than a missed one | Recall requirements demand catching entities without exact ticker/name matches (aliases, misspellings, non-English) |
| AuthN/AuthZ + multi-user | Single-analyst V1, no login | No collaboration requirement yet; auth adds a security surface with no user to protect from | A second user or external access needs isolation |
| React / streaming UI | Jinja2 + HTMX | Server-rendered pages cover every current interaction (forms, partial refresh); no client-state complexity to justify a SPA | UI needs client-side state that outgrows HTMX (rich editing, offline, websocket-driven live views) |
| Fully-automatic investigation re-evaluation | Staleness-on-read + manual refresh (ADR-0007) | Conclusions should only change when a user asks; auto re-run multiplies LLM cost by ingestion velocity | Users need investigations to update themselves without a manual refresh |
| Horizontal worker scaling | Single worker process | `SKIP LOCKED` job claiming is already N-worker-safe; a second worker is a deploy config change, not a code change | Throughput needs more than one worker — at that point add jitter to the exponential backoff (jitterless backoff is fine with one worker but causes thundering-herd retries across many) |

## Consequences

- Every "missing" piece above has a named trigger; adding it later is a scoped change
  behind an existing interface (repository, adapter, outbox), not a rewrite.
- Reviewers evaluating this codebase against a larger system should read this table before
  reading absence as gap.

## Known ceilings

Bottlenecks that exist today at V1 scale, with their upgrade path — named so they're found
by reading, not by a production incident:

- **Embed stage dominates pipeline throughput** — batch/parallelize embedding calls, or move
  to a hosted embedding API, when the embed stage is the visible queue bottleneck.
- **Per-request query-embedding latency** (fastembed, CPU) — move to a GPU-backed or hosted
  embedding endpoint if query latency becomes user-visible.
- **HNSW insert cost grows with corpus size** — tune `m`/`ef_construction`, or graduate to a
  dedicated vector DB (see table above) once index maintenance shows up in ingest latency.
- **Recursive-CTE depth limits** on the knowledge graph — cap traversal depth defensively
  today; move to a graph DB if deep multi-hop traversal becomes a real query pattern.
- **Connector rate limits** — SEC EDGAR's 10 req/s User-Agent policy and RSS poll intervals
  cap ingestion speed by design; raise schedule frequency or add connectors only within
  those published limits.
- **Single-DB contention** if api + worker + eval all hammer Postgres concurrently — add
  read replicas or move eval runs off-peak before adding an operational database split.
