# Argus — Enterprise Research Operating System

![Python](https://img.shields.io/badge/python-3.12%2B-3776AB?logo=python&logoColor=white)
![PostgreSQL](https://img.shields.io/badge/postgres-16%20%2B%20pgvector-336791?logo=postgresql&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-modular%20monolith-009688?logo=fastapi&logoColor=white)
![Docker](https://img.shields.io/badge/docker-compose-2496ED?logo=docker&logoColor=white)

Argus continuously ingests financial knowledge from public sources, structures it into a
canonical, graph-linked knowledge platform, and assists institutional research through
evidence-based investigations — persistent, reproducible research artifacts with complete
provenance, never chat sessions.

Argus is **not** a chatbot, a PDF-RAG demo, a trading system, or an investment advisor. It is
knowledge infrastructure that AI consumes; generated text is never a source of truth. Every
claim in every report resolves back to a chunk of a real, ingested document — evidence without
a citation is rejected before it ever reaches a report, and confidence in that report is a
computed number, not something the model says about itself.

## Why this project exists

Enterprise AI is a systems engineering problem, not an LLM problem. Anyone can wire a chatbot
to a vector store; the hard part — the part that actually determines whether a research
platform survives contact with a real institution — is everything underneath it: deterministic
ingestion pipelines that don't lose data, entity resolution against canonical IDs, hybrid
retrieval that doesn't hallucinate relevance, a knowledge graph where every edge carries
provenance, and an AI boundary narrow enough that a compliance team could actually audit it.

Argus is a from-scratch implementation of that architecture: the ingestion pipeline, the
knowledge platform, the retrieval engine, the citation-gated agent runtime, and the operational
discipline (idempotency, immutability, observability, replayable events, security hardening)
that separates production infrastructure from a weekend demo.

## By the numbers

| | |
|---|---|
| Enforced architectural layers (`import-linter`) | 10 |
| Deterministic ingestion pipeline stages | 7 |
| Test functions | 118, across 14 files |
| Architecture Decision Records | 9 |
| Hand-written schema migrations | 5 |
| Source under `src/argus/` | ~3,300 lines |
| Storage engines unified into one Postgres instance | 6 — relational, vector (pgvector/HNSW), full-text, graph (recursive CTEs), event log, job queue |

## Architecture

One modular monolith, one Postgres instance, one narrow AI boundary. Import direction is a
straight line — enforced by `import-linter` (`make lint`), not by convention — and every box
below maps to a real package under `src/argus/`.

```mermaid
flowchart TB
    subgraph EXT["External world"]
        sec[["SEC EDGAR"]]
        rss[["News / RSS sources"]]
        llm[["OpenRouter\n(model access)"]]
    end

    subgraph L1["Presentation — ui/"]
        ui["HTMX + Jinja2 workspace,\ndashboards, report viewer"]
    end

    subgraph L2["API — api/"]
        api["FastAPI JSON routes\n+ security middleware"]
    end

    subgraph LE["Evaluation — evals/"]
        evalset["golden.json scoring:\nretrieval + investigation quality"]
    end

    subgraph L3["Research Platform — investigations/"]
        iengine["Investigation engine\n(create / run / refresh)"]
        confidence["Deterministic confidence\nscoring"]
        reportstore["Versioned reports\n+ replay log"]
    end

    subgraph L4["Agent Runtime — agentruntime/ (the ONLY layer with AI)"]
        planner["Planner"]
        evidencecollect["Evidence collector\n+ stance classifier"]
        drafter["Drafter\n(citation-required)"]
    end

    subgraph L5["Research Engine — research/ (deterministic)"]
        retrieval["Hybrid retrieval\n(FTS + pgvector, RRF)"]
        citations["Citation resolver"]
        timeline["Timelines / graph traversal"]
    end

    subgraph L6["Data Platform — dataplatform/ (deterministic)"]
        connectors["Connectors\nsec / rss / profiles"]
        pipeline["7-stage pipeline\nparse → … → validate"]
        embeddings["Embeddings\n(fastembed)"]
    end

    subgraph L7["Knowledge Platform — knowledge/ (deterministic)"]
        entities["Canonical entities\n+ resolution"]
        kgraph["Knowledge graph\n(provenance-enforced)"]
    end

    subgraph L8["Observability — observability/"]
        pipelineruns["Pipeline run tracking\n+ dead-letter visibility"]
    end

    subgraph L9["Infrastructure — core/"]
        events[("Append-only\nevents")]
        jobs[("Outbox\njobs")]
        db[("Postgres 16\n+ pgvector")]
    end

    sec --> connectors
    rss --> connectors
    ui --> api --> iengine
    iengine --> planner --> llm
    evidencecollect --> llm
    drafter --> llm
    iengine --> evidencecollect --> retrieval
    evidencecollect --> drafter --> confidence --> reportstore
    retrieval --> citations
    retrieval --> entities
    connectors --> pipeline --> embeddings
    pipeline --> entities
    pipeline --> kgraph
    pipeline --> events
    iengine --> events
    events --> jobs --> pipeline
    pipelineruns -.->|watches| pipeline
    evalset -.->|scores| retrieval
    evalset -.->|scores| reportstore
    entities --> db
    kgraph --> db
    events --> db
    jobs --> db

    classDef apiui fill:#e0e7ff,stroke:#4338ca,color:#312e81;
    classDef investigations fill:#ccfbf1,stroke:#0f766e,color:#134e4a;
    classDef agentruntime fill:#ffedd5,stroke:#c2410c,color:#7c2d12;
    classDef research fill:#ede9fe,stroke:#6d28d9,color:#4c1d95;
    classDef dataplatform fill:#dbeafe,stroke:#1d4ed8,color:#1e3a8a;
    classDef knowledge fill:#dcfce7,stroke:#15803d,color:#14532d;
    classDef observability fill:#cffafe,stroke:#0e7490,color:#164e63;
    classDef core fill:#e2e8f0,stroke:#475569,color:#1e293b;
    classDef ext fill:#f1f5f9,stroke:#64748b,color:#0f172a;

    class ui,api apiui
    class evalset apiui
    class iengine,confidence,reportstore investigations
    class planner,evidencecollect,drafter agentruntime
    class retrieval,citations,timeline research
    class connectors,pipeline,embeddings dataplatform
    class entities,kgraph knowledge
    class pipelineruns observability
    class events,jobs,db core
    class sec,rss,llm ext
```

## How it works

**Ingesting a document** — every source, every document, one deterministic path:

```mermaid
flowchart LR
    conn["Connector\nsec / rss / profiles"]:::dataplatform
    ingest["Dedupe, write raw bytes\ncontent-addressed, insert\nimmutable documents row"]:::dataplatform
    evt[("event appended")]:::core
    job[("job enqueued\noutbox pattern")]:::core

    subgraph stages ["7 idempotent stages, keyed on (document_id, stage, pipeline_version)"]
        direction LR
        s1["parse"]:::dataplatform --> s2["extract\nmetadata"]:::dataplatform --> s3["extract\nentities"]:::dataplatform --> s4["chunk"]:::dataplatform --> s5["embed"]:::dataplatform --> s6["build\ngraph"]:::dataplatform --> s7["validate"]:::dataplatform
    end

    conn --> ingest --> evt --> job --> stages
    stages -.->|"each stage emits an event\n+ enqueues the next job"| evt

    classDef dataplatform fill:#dbeafe,stroke:#1d4ed8,color:#1e3a8a;
    classDef core fill:#e2e8f0,stroke:#475569,color:#1e293b;
```

Crashed or stuck jobs are re-queued by a lease-based reaper; jobs that exhaust their retry
budget dead-letter visibly instead of vanishing. Full detail in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#5-event-driven-ingestion).

**Answering a research question** — every claim traces back to evidence, or the run fails:

```mermaid
flowchart LR
    q(["Question"]):::investigations
    plan["Plan the research\n(LLM)"]:::agentruntime
    retrieve["Retrieve evidence\n(hybrid search)"]:::research
    draft["Draft report\nwith citations (LLM)"]:::agentruntime
    gate{"Citation gate"}:::investigations
    reject["Rejected —\nno invented citations"]:::investigations
    score["Score confidence\n(deterministic)"]:::knowledge
    report[("Report")]:::investigations

    q --> plan --> retrieve --> draft --> gate
    gate -->|no| reject
    gate -->|yes| score --> report

    classDef investigations fill:#ccfbf1,stroke:#0f766e,color:#134e4a;
    classDef agentruntime fill:#ffedd5,stroke:#c2410c,color:#7c2d12;
    classDef research fill:#ede9fe,stroke:#6d28d9,color:#4c1d95;
    classDef knowledge fill:#dcfce7,stroke:#15803d,color:#14532d;
```

Full detail, including the resolvable citation chain and the confidence formula, in
[docs/ARCHITECTURE.md](docs/ARCHITECTURE.md#3-the-ai-boundary).

## Engineering highlights

- **Documents are immutable.** Content columns are guarded by a database trigger; corrections
  arrive as new documents, never edits. Nothing downstream can silently rewrite history.
- **Events are append-only; jobs are a disposable outbox.** The `events` table is the one
  source of truth; `jobs` is derived from it and can be rebuilt from scratch at any time.
- **Every pipeline stage is idempotent and replayable.** Keyed on
  `(document_id, stage, pipeline_version)` — safe to re-run after a crash, and reprocessing
  never mutates a previous version.
- **AI never touches raw storage.** Confined to a single package (`agentruntime/`), enforced
  by `import-linter`, not by convention or code review discipline.
- **Uncited evidence is structurally rejected.** A drafted report that cites a chunk outside
  its own retrieved evidence set fails the run — no invented citations reach an analyst.
- **Confidence is computed, never generated.** A deterministic function of source diversity,
  document count, source quality, recency, and stance agreement — auditable, reproducible,
  and never something the model asserts about itself.
- **Hybrid retrieval, not vector-only.** Full-text and pgvector search fused with reciprocal
  rank fusion, under a versioned strategy so old and new scores are never silently conflated.
- **Full reproducibility.** Every investigation persists its retrieval parameters, model
  versions, and retrieved chunk IDs — replay an old investigation and get the same evidence.
- **Hardened by default.** Constant-time API-key comparison, per-IP rate limiting on the
  endpoint that spends LLM tokens, SSRF allowlisting on external fetches, capped request
  bodies, and a full set of security headers — see ADR-0009.
- **Observable failure, not silent failure.** Every stage attempt is recorded; poison jobs
  dead-letter visibly on a live dashboard instead of retrying forever or disappearing.

## Tech stack

| Technology | Role | Why this, not the obvious alternative |
|---|---|---|
| PostgreSQL 16 + pgvector | Relational, vector, full-text, graph (CTEs), event log, job queue — one database | [ADR-0002](docs/adr/0002-postgres-for-everything.md): one operationally simple store beats a five-system stack at this scale |
| FastAPI + sync SQLAlchemy 2.0 | HTTP API + ORM | [ADR-0004](docs/adr/0004-sync-first.md): sync-first — async adds complexity this I/O volume doesn't justify |
| Google ADK + LiteLLM via OpenRouter | Agent orchestration + model access | [ADR-0006](docs/adr/0006-openrouter-model-access.md): the model is an `ARGUS_LLM_MODEL` config value, never a code dependency |
| Events + outbox (no broker) | Ingestion backbone | [ADR-0003](docs/adr/0003-events-and-outbox.md): append-only log + `SKIP LOCKED` outbox instead of Kafka/Redis Streams |
| HTMX + Jinja2 | Server-rendered workspace UI | Enterprise software, not a chat widget; no SPA build step |
| Typer + rich | CLI (`argus status`, `search`, `worker`, `ingest`, `reprocess`, `retry-dead`, `eval`) | The operational surface for running and repairing the pipeline, with colorized human-facing output |
| Docker + docker-compose | Containerized stack (`make stack`) | Postgres + API + worker, one profile, reproducible environment |
| `import-linter` | Layer-boundary enforcement | [ADR-0001](docs/adr/0001-modular-monolith.md): a modular monolith with import direction enforced in tooling, not code review |

Every deferred piece of infrastructure (Neo4j, Kafka, a dedicated vector DB, multi-user auth,
…) is a documented decision with a concrete trigger to revisit it —
[ADR-0008](docs/adr/0008-deferred-capabilities.md).

## Documentation

**New to the codebase? Start with [docs/ONBOARDING.md](docs/ONBOARDING.md)** — a guided
walkthrough written for a developer joining the project for the first time. Everything below
is where to go deeper once you're past the basics.

| Document | Purpose |
|---|---|
| [docs/ONBOARDING.md](docs/ONBOARDING.md) | Start here: setup, guided tour, glossary, "where do I change X?" |
| [docs/DESIGN_BIBLE.md](docs/DESIGN_BIBLE.md) | Governing principles; every ADR references it |
| [docs/PRD.md](docs/PRD.md) | Product requirements, users, MVP scope |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The layers, storage design, AI boundary — with diagrams |
| [docs/DOMAIN_MODEL.md](docs/DOMAIN_MODEL.md) | Object catalog + entity-relationship diagram |
| [docs/RISKS.md](docs/RISKS.md) | PRD risks mapped to design mitigations |
| [docs/adr/](docs/adr/) | Architecture Decision Records with tradeoffs and upgrade paths |

## Quickstart

Requires: Python 3.12+, [uv](https://docs.astral.sh/uv/), Docker.

```bash
cp .env.example .env
make up        # Postgres 16 + pgvector via docker compose
make migrate   # apply database migrations
make test      # run the test suite
make lint      # ruff + layered-architecture contract
make worker    # run the pipeline worker + connector scheduler
make api       # run the API + UI (uvicorn --reload)
make stack     # build and run the full app (postgres + api + worker) in containers
make eval      # score retrieval and investigation quality against the golden set
make backup    # pg_dump + raw-store tarball into backups/
make restore   # restore from a backup: make restore DB_DUMP=... RAW_TGZ=...
```

## CLI usage

`argus --help` lists every command with rich-rendered help. The operational surface:

```bash
argus status              # one-screen ops snapshot: job queue, dead jobs, documents, recent pipeline runs
argus search "query" -k 5 # hybrid search from the terminal, results as a table
argus ingest company_profiles   # run one connector pass now
argus reprocess --stage parse --pipeline-version 2   # re-derive artifacts, no re-downloading
argus retry-dead           # requeue dead-lettered jobs
argus eval retrieval       # score retrieval against evals/golden.json
argus eval investigation   # score investigation quality
argus worker               # run the pipeline worker + connector scheduler (plain JSON logs, for machines)
```

Every command above renders colorized, human-facing output (`rich` tables and themed
text); `worker` is the one exception — it keeps plain structured JSON logging, since it's
meant to be read by log aggregators, not a terminal.

## Status

V1 is feature-complete: all ten roadmap phases (Design Bible §22) are implemented and tested —
ingestion pipeline, knowledge graph, hybrid retrieval, agent runtime, citation-gated
investigations, UI, containerized stack, and the eval framework. One item remains explicitly
pending: live end-to-end verification against a real LLM, which awaits
`ARGUS_OPENROUTER_API_KEY`. Everything else is verified against a deterministic fake adapter.

## Deliberately out of scope for V1

Collaboration, permissions, proprietary connectors, real-time streaming, portfolio
optimization, multi-user organizations. Each deferred piece of infrastructure (Neo4j, Kafka,
dedicated vector DBs) is a documented decision with a named upgrade trigger, not an oversight —
see the ADRs.
