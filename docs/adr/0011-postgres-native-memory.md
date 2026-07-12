# ADR-0011: Postgres-native knowledge memory — Supermemory deferred

**Status:** Accepted · **Serves:** PRD-V2 §3.4–3.8 · **Extends:** ADR-0002

## Context

PRD-V2 §3.8 proposes adopting Supermemory (self-hosted) as the memory substrate for
contradiction detection (§3.5), knowledge evolution (§3.6), and cross-investigation memory
(§3.7). That adds an external service inside the trust perimeter, a new deployment unit,
and a second source of truth beside Postgres — against ADR-0002 (one Postgres serves every
layer, each mechanism with a named upgrade path). PRD-V2 itself requires every recalled
fact to re-enter validation as candidate evidence, so the external layer would add recall,
not authority.

## Decision

Build the memory substrate on Postgres (user decision, 2026-07-06):

- `claims` are append-only rows (UPDATE/DELETE trigger-guarded, like `documents`);
  `supersedes_claim_id` chains are the version history (§3.6 "Updates"),
  `claim_evidence` many-to-many is corroboration with provenance (§3.6 "Extends").
- Contradictions are computed from claims + stance data (deterministic), not stored state.
- Cross-investigation memory is a query: claims/entities/graph are already global tables;
  planning surfaces prior investigations by shared companies and unresolved questions.

## Consequences

- No new service, no BYOC deployment, no consumer-grade forgetting policy to disable;
  evidence retention follows Argus's own rules automatically.
- We re-implement none of Supermemory's ML-driven "Derives" inference — deliberately:
  inferred relationships without evidence are forbidden (Bible §18, PRD-V2 §3.1).
- Revisit trigger: cross-investigation recall latency materially degrading Context Fusion,
  or corpus scale where claim-graph queries stop fitting Postgres. The repository
  interfaces keep the swap local.
