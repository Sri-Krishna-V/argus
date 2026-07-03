# Argus — Enterprise Research Operating System

Argus continuously ingests financial knowledge from public sources, structures it into a
canonical, graph-linked knowledge platform, and assists institutional research through
evidence-based investigations — persistent, reproducible research artifacts with complete
provenance, never chat sessions.

Argus is **not** a chatbot, a PDF-RAG demo, a trading system, or an investment advisor.
It is knowledge infrastructure that AI consumes; generated text is never a source of truth.

## Why this project exists

Enterprise AI is a systems engineering problem, not an LLM problem. Argus demonstrates the
architecture behind institutional research platforms: deterministic ingestion pipelines,
entity resolution against canonical IDs, hybrid retrieval, a provenance-carrying knowledge
graph, reproducible AI-assisted investigations — and the engineering discipline
(idempotency, immutability, observability, replayable events) that production systems need.

## Documentation

Start here — the repository is designed to be understandable before reading any code:

| Document | Purpose |
|---|---|
| [docs/DESIGN_BIBLE.md](docs/DESIGN_BIBLE.md) | Governing principles; every ADR references it |
| [docs/PRD.md](docs/PRD.md) | Product requirements, users, MVP scope |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | The six layers, storage design, AI boundary |
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
```

## Status

Under construction, following the Design Bible's ten-phase roadmap (§22). Currently:
**Phase 1 — Product Definition** complete; Phase 2 — Domain Modeling next.

## What V1 deliberately excludes

Collaboration, permissions, proprietary connectors, real-time streaming, portfolio
optimization, multi-user organizations. Deferred infrastructure (Neo4j, Kafka, dedicated
vector DBs) is a documented decision with named upgrade triggers — see the ADRs.
