# ADR-0003: Append-only events table + jobs outbox instead of an external broker

**Status:** Accepted · **Serves:** Design Bible §7.4 (event driven), §8 (every event replayable)

## Context

Ingestion is event-driven and every event must be replayable. A message broker (Kafka,
Redis Streams, RabbitMQ) is the conventional answer, but adds an infrastructure component
whose delivery guarantees then have to be reconciled with database state (dual-write
problem). A bare jobs table alone is the opposite failure: a task queue wearing an
event-driven costume, with no durable event log to replay.

## Decision

Two tables with distinct roles:

- **`events`** — append-only domain event log (`document.ingested`, `document.parsed`,
  `document.enriched`, …), written in the same transaction as the state change it records.
  Never updated, never deleted. This is the source of truth and the replay record.
- **`jobs`** — outbox derived from events: work items claimed by the worker via
  `SELECT … FOR UPDATE SKIP LOCKED`, with retry counts and dead-letter status. Disposable;
  can be rebuilt from `events`.

Consumers beyond the pipeline (e.g. the knowledge-evolution staleness detector) read the
event log by cursor, so new subscribers replay history without producer changes.

## Consequences

- Exactly-once event recording for free via transactionality — no dual-write problem.
- Replayability is structural: reprocessing = re-emitting jobs from retained events.
- Polling latency (worker poll interval) instead of push; irrelevant at V1 throughput.
- Upgrade path: at sustained high throughput, tail `events` into Redis Streams/Kafka;
  the event schema is already the contract.
