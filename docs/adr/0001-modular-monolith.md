# ADR-0001: Modular monolith, not microservices

**Status:** Accepted · **Serves:** Design Bible §9 (layered architecture), §7.12 (simplicity over cleverness)

## Context

Argus has seven logical layers (presentation → research platform → agent runtime → research
engine → knowledge platform → data platform → infrastructure) and is built by one engineer.
Microservices would give each layer independent deployment at the cost of network boundaries,
serialization, distributed tracing, and deployment orchestration — none of which this system
needs to demonstrate its architecture.

## Decision

One deployable Python application. Layers are top-level packages under `src/argus/` with a
strict import direction (`ui/api → investigations → agentruntime → research → knowledge →
dataplatform → core`), enforced mechanically by `import-linter` so the boundaries are real
rather than aspirational. Two runtime processes share the codebase: the API server and the
pipeline worker.

## Consequences

- Single deployment, single debugger, transactional consistency across modules.
- Module boundaries are the future service boundaries: any layer can be extracted behind
  its existing interface if scale demands it (the upgrade path).
- Discipline is required to keep layers decoupled; the import linter is the guardrail.
