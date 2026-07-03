# ADR-0002: One Postgres instance serves every storage concern

**Status:** Accepted · **Serves:** Design Bible §14 (data philosophy), §19 (scalability philosophy)

## Context

Argus needs relational metadata, vector search, keyword search, a knowledge graph, and an
event queue. The "enterprise-looking" instinct is one specialized system per concern
(Qdrant + OpenSearch + Neo4j + Kafka). That stack imposes distributed consistency problems
on day one: a document indexed in the vector store but missing from the graph, a queue
message for a row that never committed.

## Decision

Postgres 16 is the single store:

| Concern | Mechanism |
|---|---|
| Documents/metadata | Relational tables |
| Embeddings | pgvector, HNSW |
| Keyword search | Native FTS (tsvector + GIN) |
| Knowledge graph | `graph_nodes`/`graph_edges` + recursive CTEs |
| Eventing | Append-only `events` + `jobs` outbox (`FOR UPDATE SKIP LOCKED`) |

The decisive property is **transactional consistency**: a pipeline stage commits its derived
artifacts, its domain event, and its follow-on job atomically, or not at all.

Raw document bytes live outside Postgres in a content-addressed filesystem store
(`data/raw/<sha256>`), shaped like an object store so S3 can replace it.

## The 100-million-document test (§19)

The *architecture* passes; individual *mechanisms* have documented ceilings and upgrade
paths, reachable without touching callers because repositories hide storage:

- **pgvector** degrades past tens of millions of vectors (HNSW build time, memory) →
  dedicated vector DB behind the same repository interface.
- **Jobs outbox** is fine for documents-per-minute throughput; at sustained thousands/sec →
  Redis Streams or Kafka fed from the same `events` table.
- **Recursive CTEs** slow on very deep/huge graphs → Neo4j behind the graph repository.
- **Single instance** → read replicas, then partitioning by document age.

## Consequences

- One database to run, back up, and reason about; integration tests need only compose.
- No storage swap can be done casually — but each swap point is a named interface.
