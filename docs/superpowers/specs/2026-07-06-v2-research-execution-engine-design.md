# Argus V2 — Research Execution Engine: Master Plan

## Context

V1 is complete (10 phases + security hardening, 125 tests): a modular monolith where an
investigation runs one linear pipeline — plan → hybrid-retrieve → stance-classify → draft →
deterministic confidence — with immutable documents, append-only events, citation gating,
and full replay. `v2-PRD.md` evolves this into a **Research Execution Engine**: investigations
become planned, DAG-executed, knowledge-structured (claims/entities/events), executed by
specialist agents, adaptive (replanning), and lifecycle-managed. This plan maps all ~24 PRD
capabilities onto the existing system and sequences the build.

**User decisions locked in (AskUserQuestion, 2026-07-06):**
1. **Postgres-native memory** — Capability 3.8 (Supermemory) deferred via ADR; claims/versioning/
   contradictions built as append-only Postgres tables. Revisit trigger: cross-investigation
   recall latency or scale.
2. **Master plan now, per-phase specs later** — each phase gets its own brainstorm-lite spec +
   subagent-executable plan (superpowers writing-plans) when it starts, same workflow as V1.
3. **Merge CLI branch first** — `worktree-frontend-revamp` (review-approved) merges to main
   before V2 begins. Dashboard SPA plan is re-scoped after V2's API surface exists.
4. **Defer the long tail** — every capability appears below; items whose cost far exceeds
   near-term value ship as recorded deferrals (V1 "deliberate exclusions" style).

**ADK v2 finding (context7, google/adk-python v2.0.0a1):** ADK offers SequentialAgent/
ParallelAgent/sub_agents with session-state passing, but it is in-process, session-scoped, and
model-driven — no pause/resume across sessions, no crash recovery, non-deterministic delegation.
PRD 4.x demands deterministic scheduling, persistent model-independent shared memory, checkpoint
restore. **Decision: specialists remain single structured ADK calls through `agentruntime/adapter.py`
(LlmAgent + output_schema, exactly the V1 pattern); Argus's Postgres jobs outbox is the
orchestrator.** ADK stays the documented framework at the same boundary (ADR to record this).

## Core architecture: PRD → existing system mapping

| PRD capability | Implementation | Reuses |
|---|---|---|
| 1.1 Investigation Planner | Planner v2: richer structured output (investigation type, objectives, typed tasks w/ deps, per-task rationale, assigned specialist) | `agentruntime/planner.py`, `adapter.run_structured` |
| 1.2 Investigation DAG | New `investigation_tasks` table; validation via stdlib `graphlib.TopologicalSorter`; execution = jobs outbox (`job_type="investigation.task"`), parallel via N workers + `SKIP LOCKED` — ADR-0004 sync-only preserved | `core/models.Job`, `dataplatform/worker.py` |
| 1.3 Dynamic Replanning | Deterministic triggers (contradiction found, gap detected, task failed) enqueue a replan task; planner proposes additive changes; completed tasks never deleted (`status="obsolete"`) | events/outbox, planner v2 |
| 1.4 State Machine | Extend `Investigation.status` + `ALLOWED_TRANSITIONS` dict; every transition emits an `InvestigationEvent`; pause/resume/cancel/branch/archive endpoints; branch = new investigation + `InvestigationLink` (exists) | `investigations/models.py`, `investigation_events` |
| 2.1 Query Planner | Typed queries in plan schema: objective, evidence target, source types, priority, timeframe | `ResearchPlan` schema |
| 2.2 Hybrid Retrieval+ | Add strategies behind the same `search()` surface: graph traversal (`knowledge/graph.neighborhood`), timeline retrieval (`research/timeline`), entity-centric (existing filters); fuse via existing RRF | `research/retrieval.py` |
| 2.3 Source Ranking | Deterministic scorer modeled on `confidence.py` (authority tier, freshness, independence/publisher diversity, corroboration); score + explanation stored per evidence row | `QUALITY_TIER`, `Evidence.scores` |
| 2.4 Evidence Dedup | Chunk level: checksum + embedding-cosine threshold (ARGUS_ setting); claim level: `claim_evidence` many-to-many is the corroboration-vs-duplication record; provenance always kept | `Chunk.embedding`, claims tables |
| 2.5 Context Fusion | Deterministic `InvestigationContext` pydantic builder: evidence + claims + timeline + contradictions + gaps; persisted as an investigation event; the input artifact for every specialist | all of research/, knowledge/ |
| 3.1 Evidence Graph | Extend `graph_nodes`/`graph_edges`: new node_types (person, event, claim, risk), new edge_types (appointed, resigned, supports, contradicts, occurred_before, …), confidence + temporal validity columns; per-investigation subgraph view. Provenance already NOT NULL | `knowledge/models.py`, `graph.py` |
| 3.2 Timeline Engine | Events are graph nodes (node_type="event", timestamp in extra) extracted via one structured LLM call per document/context; deterministic ordering + duplicate-event merge; no inferred dates replace observed ones | graph tables, `research/timeline.py` |
| 3.3 Entity Resolution | Companies exist; add person resolution (executives) as V2-lite: canonical `people` table + alias matching, same pattern as `Company`. Products/locations/funds deferred | `resolve_companies` pattern |
| 3.4 Claim Intelligence | New `claims` (subject/predicate/object, claim_text, event_date, confidence, origin investigation, `supersedes_claim_id`) + `claim_evidence` (chunk FK = citation guarantee, relation supporting\|contradicting). Extraction = structured LLM call; claims are append-only (trigger-guarded, like documents) | migration pattern 0002/0004 |
| 3.5 Contradiction Detection | Deterministic: claims sharing (subject, predicate) with conflicting objects, plus stance-contradicting evidence (exists). Computed on read first (`has_new_evidence` pattern); contradictions feed replanning | claims, `Evidence.stance` |
| 3.6 Knowledge Evolution | `supersedes_claim_id` chain = version history; previous values immutable and recoverable; freshness = timestamps already on everything | append-only rules |
| 3.7 Cross-Investigation Memory | Claims/entities/graph are already global tables; at planning time surface prior investigations (shared company_ids), reusable claims, unresolved follow-up questions; recalled claims re-enter as **candidate evidence requiring revalidation** (PRD hard rule); `InvestigationLink` records reuse | `InvestigationLink`, claims |
| 3.8 Supermemory | **Deferred** (user decision) — ADR with revisit trigger | — |
| 4.1 Research Orchestrator | Deterministic module in `investigations/`: marks tasks ready when deps complete, enqueues outbox jobs, aggregates outputs, terminates/checkpoints. Never does domain reasoning (it's plain Python, not an LLM) | worker, jobs, events |
| 4.2 Specialist Agents | Registry: name → (instruction, output_schema, evidence filters, optional model override). Each execution = one `run_structured` call consuming `InvestigationContext`. Initial set: Financial, Filings, News, Competitive, Executive, Risk, Validation, Synthesis (Macro deferred — no macro data source) | `adapter.py`, `schemas.py` |
| 4.3 Shared Investigation Memory | The investigation's Postgres state (tasks, evidence, claims, context, contradictions) — already model-independent, persistent, explainable. No new infra | everything above |
| 4.4 Agent Coordination | Task outputs land in `investigation_tasks.outputs`; downstream tasks read them from DB; orchestrator routes. Sequential/parallel/conditional all fall out of the DAG | DAG + outbox |
| 4.5 Execution Recovery | Jobs retry/backoff/lease-reaping/dead-letter reused wholesale; task-level statuses mirror job outcomes; human escalation = analyst_review state | `worker.py`, `events.retry_at` |
| 4.6 Agent Observability | `ExecutionRecord` per call already persisted in `investigation_events`; add task-trace API endpoint + agent-utilization metrics (extend `/api/metrics/*`) | `investigation_events`, `observability/` |
| 4.7 Human Collaboration | Analyst endpoints: pause/resume, approve/reject evidence, edit objectives, annotations (`annotations` table), request-more-research (creates tasks), override conclusions; every action is an `InvestigationEvent`; analyst actions always win | state machine, events |

## Schema additions (hand-written migrations 0006+)

- `investigation_tasks`: id, investigation_id FK, objective, task_type, specialist, depends_on
  (JSONB list of task ids), status (pending|ready|running|complete|failed|obsolete), inputs JSONB,
  outputs JSONB, confidence, rationale, created_at. Status/history changes emit InvestigationEvents.
- `claims` + `claim_evidence`: as above; claims append-only (UPDATE/DELETE trigger like migration 0002).
- `people` (+ `document_people`): canonical executives, `Company` pattern.
- `annotations`: investigation_id, target (evidence/report/task ref), body, created_at.
- `graph_nodes`/`graph_edges`: add confidence, valid_from/valid_to (nullable) columns; new types are just strings.
- `investigations`: extend status enum values (draft, planning, executing, evidence_review,
  reasoning, confidence_evaluation, analyst_review, complete, failed, archived, paused).

## Phases

Each phase: brainstorm-lite spec → `superpowers:writing-plans` → subagent-driven dev
(**sonnet subagents, every Agent call**), edge-case tests per module, `make lint && pytest`
green before commit. AI paths tested with the fake adapter; live verification needs
`ARGUS_OPENROUTER_API_KEY` (still missing — Phase 0 asks for it).

- **Phase 0 — Runway.** Merge `worktree-frontend-revamp` into main. Write ADR-0010 (V2 execution
  model: DB-orchestrated DAG, ADK stays at adapter boundary), ADR-0011 (Postgres-native memory,
  Supermemory deferred), ADR-0012 (V2 deferrals list). Update `docs/PRD.md` reference to v2-PRD.
  Ask user for the OpenRouter key.
- **Phase 1 — Task DAG + Orchestrator (1.1, 1.2, 4.1, 4.4, 4.5).** `investigation_tasks`,
  planner v2, orchestrator, worker handles `investigation.task` jobs, DAG validation
  (`graphlib`), V1's linear flow re-expressed as the first DAG (retrieve→stance→draft as task
  types) so the engine is proven before any new AI. Recovery via existing job semantics.
- **Phase 2 — Lifecycle + Human Collaboration (1.4, 4.7).** State machine, transitions,
  pause/resume/cancel/branch/archive, annotations, evidence approve/reject, analyst events.
- **Phase 3 — Retrieval Intelligence (2.1–2.5).** Typed query plans, graph/timeline retrieval
  strategies into RRF, source ranking scorer, chunk dedup, `InvestigationContext` fusion builder.
- **Phase 4 — Knowledge Intelligence (3.1–3.6, 3.3-lite).** Claims + claim_evidence, claim
  extraction task type, evidence-graph node/edge extension, timeline events, contradiction
  detection, supersedes-chain evolution, people resolution (lite).
- **Phase 5 — Specialists + Observability (4.2, 4.3, 4.6).** Specialist registry (8 specialists),
  specialist task types consuming fused context, validation agent gate before synthesis,
  task-trace + agent-utilization APIs.
- **Phase 6 — Replanning + Cross-Investigation Memory (1.3, 3.7).** Replan triggers and additive
  task updates; prior-investigation surfacing at planning; recalled-claim revalidation path.
- **Phase 7 — Evals + Docs.** Extend `evals/` + golden set for PRD success metrics (planning
  accuracy, citation completeness, contradiction detection rate, confidence calibration,
  reproducibility); ARCHITECTURE/DOMAIN_MODEL/ONBOARDING updates; README.
- **After Phase 7:** re-scope the dashboard SPA plan against the V2 API surface.

Dependency chain: 1 → 2 → 3 → 4 → 5 → 6 (7 partially parallel; eval additions land with each phase where cheap).

## Deferred (recorded in ADR-0012, each with a revisit trigger)

Supermemory integration (3.8); investigation **merge** (branch ships, merge waits for demand);
entity resolution beyond companies+people (products/locations/funds); Macro Analyst specialist
(needs macro data connectors); uncertain-date estimation in timelines (PRD itself forbids inferred
dates replacing observed); citation-expansion & claim-based retrieval strategies (need a claims
corpus first — natural V2.1 once Phase 4 data accumulates); execution-cost estimation in planning
(needs usage data).

## Constraints carried forward (unchanged hard rules)

Layer direction (import-linter); documents immutable; events append-only; every AI output cites
chunks (citation gate extends to claims via `claim_evidence.chunk_id` FK); confidence computed,
never LLM-generated; sync-only (ADR-0004) — parallelism = multiple worker processes; all tunables
as `ARGUS_` settings (max parallel tasks, task lease, dedup threshold, ranking weights, replan
triggers, per-specialist model overrides); migrations hand-written and numbered.

## Verification

- Per phase: `make lint` (layer contract) + `make test`; new modules ship failure-mode/boundary
  tests (user's edge-case rule); fake adapter covers AI paths deterministically.
- Phase 1 acceptance: an investigation converts to a valid DAG before any evidence collection;
  two workers execute independent tasks concurrently; killing a worker mid-task recovers via
  lease reaping; replay still matches.
- Phase 4 acceptance: every claim row traces to chunks; contradiction surfaced from two
  conflicting fixture claims; superseded claim history recoverable.
- End-to-end (needs OpenRouter key): one real investigation through DAG → specialists →
  validated synthesis → citation-gated report → deterministic confidence; `make eval` scores it.

## Key files

Modify: `agentruntime/{planner,schemas,evidence}.py`, `investigations/{engine,models,confidence}.py`,
`research/retrieval.py`, `knowledge/{models,graph,repositories}.py`, `dataplatform/worker.py`,
`api/routes.py`, `core/config.py`, `evals/runner.py`, migrations `0006+`.
New: `investigations/{orchestrator,lifecycle}.py`, `agentruntime/specialists.py`,
`research/{ranking,fusion}.py`, `knowledge/{claims,contradictions,people}.py`, ADRs 0010–0012,
`docs/superpowers/specs/` per-phase specs.
`agentruntime/adapter.py` stays the only ADK import.
