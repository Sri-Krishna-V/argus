# Argus Architecture

Governing document: [DESIGN_BIBLE.md](DESIGN_BIBLE.md). Product scope: [PRD.md](PRD.md).
Decisions and their tradeoffs live in [adr/](adr/). This document describes the system as built.

---

## 1. Architecture style

Argus is a **modular monolith** ([ADR-0001](adr/0001-modular-monolith.md)): one deployable
Python application whose internal modules mirror the Design Bible's layers (§9) and communicate
through in-process interfaces. Enterprise modularity without distributed-systems overhead.

## 2. Layers

```
Presentation (ui/)            Jinja2 + HTMX investigation workspace, dashboards
        ↓
Research Platform             Investigations: hypotheses, evidence, reports,
(investigations/, api/)       confidence, versioning, replay records
        ↓
Agent Runtime (agentruntime/) Planning, stance classification, report drafting.
                              Google ADK behind an adapter. The ONLY layer with AI.
        ↓
Research Engine (research/)   Hybrid retrieval, ranking, timelines, contradiction
                              grouping, citation assembly. Deterministic.
        ↓
Knowledge Platform            Canonical entities, entity resolution, knowledge
(knowledge/)                  graph, search indexes, versioning. Deterministic.
        ↓
Data Platform (dataplatform/) Connectors, scheduling, parsing, metadata, entity
                              extraction, chunking, embeddings, validation.
        ↓
Infrastructure (core/)        Config, database, logging, events, job queue.
```

**Layer rule** (Bible §9): higher layers never bypass lower layers, and nothing at or below
the Research Engine imports AI code. Enforced with `import-linter`, not by convention.
One nuance: in *import* terms the Knowledge Platform sits below the Data Platform —
pipeline stages depend on the knowledge models and repositories they populate, never the
reverse. The Bible's diagram describes data flow (upward); the import contract describes
code dependency (downward onto the organization's memory). Similarly, `ui/` sits one
import layer above `api/` (views reuse the API's session dependency); `argus.main` is the
composition root that mounts both routers into one FastAPI app, and `argus.cli` the
entry point for worker/ingest commands — both live outside the layer stack.

## 3. The AI boundary

AI never owns the data pipeline (Bible §15). Documents flow through deterministic stages —
parse → metadata → entity extraction → chunk → embed → validate — before any agent can see
them. Agents consume the knowledge platform through the Research Engine's typed interfaces
and must attach chunk-level citations to every piece of evidence; uncited evidence is
rejected at the boundary ([ADR-0005](adr/0005-evidence-first-ai-boundary.md)).

## 4. Storage

One Postgres 16 instance serves every layer ([ADR-0002](adr/0002-postgres-for-everything.md)):

| Concern          | Mechanism                                                |
|------------------|----------------------------------------------------------|
| Documents & metadata | Relational tables; documents are immutable            |
| Raw bytes        | Content-addressed filesystem store (`data/raw/<sha256>`) |
| Embeddings       | `pgvector` (HNSW index)                                   |
| Keyword search   | Native FTS (`tsvector` + GIN)                             |
| Knowledge graph  | `graph_nodes` / `graph_edges` + recursive CTEs            |
| Eventing         | Append-only `events` table + `jobs` outbox (`SKIP LOCKED`)|

Each choice has a named upgrade path recorded in its ADR; the repository interfaces hide
storage so a swap (pgvector → dedicated vector DB, outbox → Kafka, CTEs → Neo4j) does not
ripple upward. This is how the design answers the Bible's 100-million-document test (§19).

### Storage layers (Bible §14)

Raw → Parsed → Enriched → Search → Knowledge. Raw documents are permanent and never
modified; every derived artifact (chunks, embeddings, entities, edges) references its
source document, pipeline version, and timestamp, and can be re-derived at any time via
`argus reprocess` without re-downloading.

## 5. Event-driven ingestion

The append-only `events` table is the source of truth ([ADR-0003](adr/0003-events-and-outbox.md)).
Domain events (`document.ingested`, `document.parsed`, `document.enriched`, …) are appended
in the same transaction as the state change; `jobs` rows are derived from events (outbox
pattern) and claimed by the worker with `FOR UPDATE SKIP LOCKED`. Events are retained
forever, so every pipeline run is replayable. Stages are idempotent, keyed on
`(document_id, stage, pipeline_version)`.

```
Connector → raw store + documents row + event
                                        └→ job → parse → metadata → extract_entities
                                                  → chunk → embed → validate
                                                  (each stage: event + pipeline_runs row)
```

## 6. Reproducibility

Every investigation persists its full execution history in `investigation_events`: prompts,
retrieval strategy + version, retrieved document IDs, embedding model version, LLM model
version. A future engineer can replay an investigation and obtain the same retrieval set.

## 7. Observability

Every pipeline stage writes a `pipeline_runs` row (duration, status, error, retry count).
Queue depth comes from `jobs`. Exposed at `/metrics/pipeline` and on the pipeline dashboard.
Silent failures are unacceptable (Bible §8); poison messages dead-letter visibly.

## 8. Module map

```
src/argus/
├── core/            # settings, db session, JSON logging, event append + outbox queue
├── dataplatform/    # connectors/{profiles,sec,rss}, scheduler, stages/, embeddings provider
├── knowledge/       # repositories, entity resolution, canonical IDs, graph, indexes
├── research/        # hybrid retrieval (RRF), timelines, contradiction grouping, citations
├── agentruntime/    # adapter.py (only ADK import), planner, evidence collector, drafter
├── investigations/  # investigation engine, confidence math, reports, staleness detection
├── observability/   # pipeline_runs recording + status queries
├── api/             # FastAPI JSON routers
└── ui/              # Jinja2 + HTMX views (workspace, reports, explorer, dashboard)
```

## 9. Deliberate exclusions

Deferred capabilities are decisions, not omissions; each is recorded in an ADR with the
trigger that would revisit it: Neo4j, Kafka/Redis Streams, dedicated vector DB, PDF/OCR,
ML-based NER, authentication/multi-user, React UI, streaming connectors, fully-automatic
investigation re-evaluation (V1 ships event-driven staleness detection + manual refresh).
