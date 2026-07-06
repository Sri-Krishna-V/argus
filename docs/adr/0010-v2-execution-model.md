# ADR-0010: V2 execution model — DB-orchestrated task DAG, ADK stays at the adapter boundary

**Status:** Accepted · **Serves:** PRD-V2 §1.2, §4.1–4.5, Design Bible §10, §13

## Context

PRD-V2 turns each investigation into a DAG of tasks executed by specialist agents, with
deterministic scheduling, parallel execution, pause/resume across sessions, crash recovery,
and a persistent shared memory that no agent's conversational history can substitute for
(§4.3: "No agent depends upon conversational history").

Google ADK v2 (our documented agent framework, ADR-0006) ships its own orchestration —
`SequentialAgent`, `ParallelAgent`, `sub_agents` with session-state passing. It is
in-process, session-scoped, and (for LlmAgent delegation) model-driven: no durable
checkpoints, no lease-based recovery, non-deterministic ordering. Meanwhile Argus already
owns a durable execution substrate: the append-only `events` table with the `jobs` outbox,
claimed via `FOR UPDATE SKIP LOCKED`, with leases, exponential backoff, and dead-lettering
(ADR-0003), proven by the ingestion pipeline.

## Decision

- Investigations compile to rows in `investigation_tasks`; dependencies are validated with
  stdlib `graphlib.TopologicalSorter`; execution flows through the existing jobs outbox
  (`job_type="investigation.task"`). Parallelism = multiple worker processes; ADR-0004
  (sync-only) is preserved.
- The orchestrator is deterministic Python in `investigations/` — it marks tasks ready,
  enqueues jobs, routes outputs, and never performs domain reasoning.
- ADK's orchestration primitives are **not** used. Every specialist execution remains one
  structured call through `agentruntime/adapter.py` (`LlmAgent` + `output_schema`), exactly
  the V1 pattern. `adapter.py` stays the only module importing ADK.

## Consequences

- Scheduling, recovery, and traceability inherit battle-tested job semantics for free;
  execution history stays in `investigation_events`, replayable per Bible §13.
- We forgo ADK session-state conveniences (`output_key` templating); task inputs/outputs
  live in Postgres instead, which is what PRD-V2 §4.3 demands anyway.
- Revisit trigger: if specialists ever need multi-turn tool use *within* a single task
  (agentic loops, not one structured call), adopt ADK's tool/loop machinery inside the
  adapter for that task type — the DAG layer is unaffected.
