# ADR-0004: Synchronous code throughout

**Status:** Accepted · **Serves:** Design Bible §7.12 (simplicity over cleverness)

## Context

The stack could be async end-to-end (async SQLAlchemy, async httpx, asyncio worker,
`async def` endpoints). Async pays off when a process must hold thousands of concurrent
I/O waits. Argus V1 ingests documents at a rate of a few per minute and serves a handful
of concurrent users; the failure modes async introduces (forgotten awaits, event-loop
blocking, greenlet/session pitfalls, two flavors of every utility) buy nothing here.

## Decision

Sync everywhere: sync SQLAlchemy sessions, sync `httpx` clients in connectors, a plain
polling loop in the worker, `def` endpoints in FastAPI (which runs them on a threadpool).
One concurrency model, one kind of stack trace.

## Consequences

- Simpler code, trivially debuggable; no colored-function split.
- Worker throughput scales by running more worker processes, not by async concurrency —
  `SKIP LOCKED` job claiming already makes that safe.
- Upgrade path: if a connector ever needs high-fanout I/O, isolate async inside that
  connector; the `Connector` protocol is interface-compatible either way.
