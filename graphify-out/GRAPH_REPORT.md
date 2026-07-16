# Graph Report - .  (2026-07-16)

## Corpus Check
- 151 files · ~76,513 words
- Verdict: corpus is large enough that graph structure adds value.

## Summary
- 1190 nodes · 1874 edges · 177 communities (86 shown, 91 thin omitted)
- Extraction: 79% EXTRACTED · 21% INFERRED · 0% AMBIGUOUS · INFERRED: 392 edges (avg confidence: 0.75)
- Token cost: 513,360 input · 0 output

## Community Hubs (Navigation)
- Agent Runtime & Evidence
- API Security Tests
- PRD-V2 Capability Tree
- Architecture Principles & Rules
- React Router Pages
- Architecture Decision Records
- Pipeline Integration Tests
- API Routes
- Task DAG Orchestrator
- Evaluation Harness
- TypeScript App Config
- Events & Jobs Outbox
- Investigation Engine Tests
- Operations CLI
- Orchestrator Tests
- shadcn Components Config
- Investigation Engine
- Vite Node Config
- FastAPI Composition Root
- Company Profiles Connector
- Frontend Runtime Dependencies
- Frontend Dev Dependencies
- Investigation Platform Models
- Hybrid Retrieval Tests
- Entity Extraction
- Config & JSON Logging
- SEC EDGAR Connector
- Deterministic Pipeline Stages
- Pipeline Worker
- Domain Repositories & Invariants
- Knowledge Layer Models
- Connector Protocol Stubs
- SPA Forms & Dialogs
- RSS Connector Tests
- Domain Events & Enqueue
- Frontend API Types
- Test DB Fixtures
- Content-Addressed Raw Store
- Web Package Manifest
- Oxlint Config
- Embedding Providers
- Connector Framework
- Knowledge Graph Builder
- Entity Timeline
- Icon Sprite Sheet
- Frontend API Client
- Computed Confidence
- Migration 0002 Domain Tables
- Migration 0004 Investigations
- Migration 0005 Eval Runs
- Citation Assembly
- Graph Neighborhood Traversal
- Signal Ridge Visual
- Status Dot Component
- CLI Ops Commands
- Task DAG View
- Stack Exclusions & SPA Root
- Layer Direction Rule
- Product Philosophy Principles
- Docker Compose Services
- CI Jobs
- App Shell Nav
- Confidence Meter
- Badge Component
- Button Component
- TS Project References
- Event-Driven Ingestion Tour
- Module Map
- Storage Layer Philosophy
- @fontsource-variable/geist-mono
- lucide-react
- react
- shadcn
- sonner
- tailwind-merge
- tailwindcss
- @tanstack/react-query
- @tanstack/react-router
- tw-animate-css
- Brand Identity Assets
- Evaluation framework golden.json eval_runs
- Observability pipeline_runs /api/metrics/pipeline
- Reproducibility via investigation_events replay trail
- Core domain model 12 objects
- Documentation philosophy repo understandable before
- Engineering principles idempotent pipelines immutable
- Evidence philosophy support/contradict/missing/reliability/reproducibility
- Knowledge graph philosophy relationships are
- Living document principle architecture leads
- Long-term roadmap 10 phases
- Mission statement
- Non-goals no trading no advice
- Platform layers Data/Knowledge/Research/Agent Runtime/Presentation
- Product identity Argus is a
- Project philosophy enterprise AI is
- Repository philosophy communicate engineering maturity
- Retrieval philosophy combine techniques evidence
- Scalability philosophy 100-million-document test
- Success criteria
- Vision statement
- Confidence is computed never LLM-generated
- Events are append-only jobs is
- Job lifecycle pending - running
- ponytail comments naming ceiling upgrade
- Sync code only ADR-0004
- Glossary Event Job Chunk Citation
- Setup narrated
- Core product concept persistent Investigations
- Future roadmap
- PRD mission
- MVP scope V1 included/excluded
- PRD non-goals
- Problem statement heterogeneous sources
- PRD product goals
- PRD success metrics
- Product success statement
- Target users Portfolio Managers Research
- UX principles enterprise software not
- PRD vision
- Citation resolved traversal evidence- chunk-
- Company object
- Connector object
- Derived Artifact object
- Entity object mention resolution
- Domain event record events table
- Evidence object
- Hypothesis object
- Investigation object
- Investigation Task object V2 Phase
- Job record jobs outbox
- Pipeline run record
- Relationship object graph_nodes/graph_edges
- Research Report object
- Research Session investigation_events
- Timeline Event computed not stored
- argus
- Current state assessment execution-first vs
- PRD-V2 executive summary Research Execution
- PRD-V2 non-goals
- PRD-V2 product goals
- PRD-V2 product success metrics
- PRD-V2 vision
- Engineering highlights list
- Argus project overview Enterprise Research
- Status V1 feature-complete
- Tech stack table with ADR-backed
- Hero Brand Image Isometric Card
- React Logo Iconify SVG Icon
- Vite Logo SVG
- Oxlint type-aware config guidance
- React Compiler not enabled dev/build

## God Nodes (most connected - your core abstractions)
1. `session_scope()` - 77 edges
2. `drain_queue()` - 46 edges
3. `ingest_html()` - 44 edges
4. `Job` - 33 edges
5. `get_settings()` - 31 edges
6. `Document` - 28 edges
7. `Investigation` - 24 edges
8. `Base` - 21 edges
9. `_fake_adapter()` - 21 edges
10. `ResearchPlan` - 19 edges

## Surprising Connections (you probably didn't know these)
- `test_auth_off_by_default_api_works_without_a_key()` --calls--> `get_settings()`  [INFERRED]
  tests/test_api_features.py → src/argus/core/config.py
- `test_body_just_under_cap_is_not_413()` --calls--> `get_settings()`  [INFERRED]
  tests/test_api_features.py → src/argus/core/config.py
- `test_body_over_cap_is_413()` --calls--> `get_settings()`  [INFERRED]
  tests/test_api_features.py → src/argus/core/config.py
- `db_session()` --calls--> `session_scope()`  [INFERRED]
  tests/conftest.py → src/argus/core/db.py
- `test_eval_retrieval_in_process_hits_and_records()` --calls--> `session_scope()`  [INFERRED]
  tests/test_e2e.py → src/argus/core/db.py

## Import Cycles
- None detected.

## Hyperedges (group relationships)
- **Layered architecture enforced across governing docs** — bible_architectural_philosophy, arch_layer_stack, claude_layer_direction_rule [INFERRED 0.85]
- **Evidence-first AI boundary (citations mandatory, confidence computed)** — claude_citations_required_rule, claude_confidence_computed_rule, bible_evidence_philosophy, arch_ai_boundary, docs_risks_hallucinated_summaries [INFERRED 0.85]
- **Fan-in concurrency safety mechanism for the task DAG** — claude_fan_in_concurrency_gotcha, arch_fan_in_concurrency_safety, domain_investigation_task_object, prdv2_investigation_dag [INFERRED 0.85]
- **V2 Phase 0 Runway ADRs (execution model, memory, deferrals)** — docs_adr_0010_v2_execution_model, docs_adr_0011_postgres_native_memory, docs_adr_0012_v2_deferrals, docs_superpowers_specs_2026_07_06_v2_research_execution_engine_design [EXTRACTED 1.00]
- **Deferred-Capability-as-Named-Decision Pattern Family** — docs_adr_0007_knowledge_evolution_v1_lite, docs_adr_0008_deferred_capabilities, docs_adr_0012_v2_deferrals [INFERRED 0.80]
- **Frontend Revamp Initiative (CLI + Dashboard)** — docs_superpowers_specs_2026_07_05_frontend_revamp_design, docs_superpowers_plans_2026_07_05_cli_revamp, docs_superpowers_plans_2026_07_05_dashboard_spa, docs_adr_0013_react_spa_dashboard [EXTRACTED 1.00]

## Communities (177 total, 91 thin omitted)

### Community 0 - "Agent Runtime & Evidence"
Cohesion: 0.05
Nodes (56): The only module that imports ADK (ADR-0005). One entry point: run a single struc, One LLM call with structured JSON output. Validation errors propagate — an     u, run_structured(), draft(), Report drafter: stance-classified evidence → DraftReport. Receives evidence IDs, collect(), collect_query(), BaseModel (+48 more)

### Community 1 - "API Security Tests"
Cohesion: 0.05
Nodes (24): _assert_security_headers(), companies_and_investigations(), _investigation_citing(), UUID, rate_limit_of(), Phase 10 enterprise-default features: opt-in API-key auth, request-ID correlatio, A handful of investigations to paginate over, created once per module. Uses, Turn auth on for one test; restores the (empty, disabled) default after. (+16 more)

### Community 2 - "PRD-V2 Capability Tree"
Cohesion: 0.07
Nodes (42): Investigation lifecycle (question -> plan -> retrieve -> stance -> draft -> gate -> confidence -> report), Functional requirements (investigation mgmt, retrieval, planning, evidence, reports, evolution), Primary user journey (investigation lifecycle), Capability 4.4: Agent Coordination, Capability 4: Agent Intelligence, Capability 4.6: Agent Observability, Capability 3.4: Claim Intelligence, Competitive Intelligence Analyst specialist agent (+34 more)

### Community 3 - "Architecture Principles & Rules"
Cohesion: 0.05
Nodes (38): The AI boundary (agentruntime is the only AI layer), Fan-in concurrency safety (_advance() row locking), Modular monolith architecture style, Security model (request_context middleware chain), AI philosophy (AI never owns ingestion or becomes source of truth), Investigations as primary product abstraction, Argus purpose (demonstrate production-grade AI systems engineering), Every AI output carries citations (+30 more)

### Community 4 - "React Router Pages"
Cohesion: 0.08
Nodes (27): queryClient, Register, router, @tanstack/react-router, Route, Route, STANCE_LABELS, PipelinePage() (+19 more)

### Community 5 - "Architecture Decision Records"
Cohesion: 0.09
Nodes (32): ADR-0001: Modular Monolith, Not Microservices, Modular Monolith Pattern (import-linter-enforced layers), ADR-0002: One Postgres Instance Serves Every Storage Concern, Postgres-as-Single-Store Architecture (pgvector + FTS + graph CTEs + outbox), ADR-0003: Append-Only Events Table + Jobs Outbox, Event Log + Disposable Jobs Outbox Pattern, ADR-0004: Synchronous Code Throughout, Sync-Only Concurrency Model (+24 more)

### Community 6 - "Pipeline Integration Tests"
Cohesion: 0.12
Nodes (27): drain_queue(), ingest_html(), Ingest one stub document; returns its document id., Run jobs until the queue is empty. A claim can transiently miss while pending, test_collect_builds_cited_evidence(), test_collect_raises_on_stance_count_mismatch(), test_search_finds_ingested_document(), corpus() (+19 more)

### Community 7 - "API Routes"
Cohesion: 0.15
Nodes (30): api_companies(), api_document(), api_search(), CreateLink, get_db(), get_evidence(), get_investigation(), _get_or_404() (+22 more)

### Community 8 - "Task DAG Orchestrator"
Cohesion: 0.16
Nodes (26): InvestigationTask, _advance(), collect_evidence(), compile_dag(), drain(), _emit(), _enqueue_task(), _fail_if_exhausted() (+18 more)

### Community 9 - "Evaluation Harness"
Cohesion: 0.11
Nodes (22): eval_investigation(), eval_retrieval(), load_golden(), Path, Session, UUID, Evaluation harness (Phase 8): golden-set retrieval quality and investigation rep, record_run() (+14 more)

### Community 10 - "TypeScript App Config"
Cohesion: 0.08
Nodes (24): DOM, src, vite/client, compilerOptions, allowArbitraryExtensions, allowImportingTsExtensions, erasableSyntaxOnly, jsx (+16 more)

### Community 11 - "Events & Jobs Outbox"
Cohesion: 0.12
Nodes (20): Reset dead (poison) jobs back to pending for another attempt., retry_dead(), Event, Job, Eventing tables (ADR-0003): events is the append-only source of truth, jobs is t, Append-only (UPDATE/DELETE rejected by trigger, migration 0002).     The bigint, Outbox work item, claimed with FOR UPDATE SKIP LOCKED.     status: pending → run, _dead_job() (+12 more)

### Community 12 - "Investigation Engine Tests"
Cohesion: 0.12
Nodes (20): test_evidence_limit_and_offset(), test_tasks_endpoint_lists_dag(), _doc(), _ev(), _fake_adapter(), _make_record(), Phase 7: investigation engine end-to-end with a faked adapter, deterministic con, An empty plan must fail the run, never produce an evidence-free report. (+12 more)

### Community 13 - "Operations CLI"
Cohesion: 0.09
Nodes (15): eval_investigation_cmd(), eval_retrieval_cmd(), Path, Argus operations CLI., Hybrid search from the terminal., Re-derive artifacts from stored raw documents — no re-downloading (Bible §14)., Score hybrid retrieval against the golden set., Score citation coverage and stance balance across the latest report of every (+7 more)

### Community 14 - "Orchestrator Tests"
Cohesion: 0.15
Nodes (21): InvestigationTask, One DAG node (PRD-V2 1.2). depends_on holds task UUIDs as strings; readiness, test_narrative_without_markers_is_rejected(), _plan(), Orchestrator: DAG compilation, task execution, failure semantics (PRD-V2 1.2/4.1, A synthesize job delivered before its deps are complete must raise (job retries), Two PlannedQuery entries with identical query text must collapse to one     coll, Finding 1 regression: two collect siblings feeding one synthesize task,     comp (+13 more)

### Community 15 - "shadcn Components Config"
Cohesion: 0.09
Nodes (21): aliases, components, hooks, lib, ui, utils, iconLibrary, menuAccent (+13 more)

### Community 16 - "Investigation Engine"
Cohesion: 0.23
Nodes (20): create(), _emit(), execute(), _finalize(), has_new_evidence(), Investigation, Session, UUID (+12 more)

### Community 17 - "Vite Node Config"
Cohesion: 0.10
Nodes (19): node, vite.config.ts, compilerOptions, allowImportingTsExtensions, erasableSyntaxOnly, lib, module, moduleDetection (+11 more)

### Community 18 - "FastAPI Composition Root"
Cohesion: 0.12
Nodes (11): Request, _rate_limited(), FastAPI composition root: JSON API + static React SPA (web/dist) in one app. Run, Token bucket, refilled continuously at rate_per_minute/60s; burst == rate_per_mi, request_context(), _with_security_headers(), _fake_adapter(), investigation() (+3 more)

### Community 19 - "Company Profiles Connector"
Cohesion: 0.13
Nodes (13): Session, Company profiles connector: SEC's official ticker registry seeds the canonical c, Upsert canonical companies from the registry snapshot. Idempotent., seed_companies(), Company, Canonical entity. One row per CIK; the entity-resolution target., CompanyRepository, Session (+5 more)

### Community 20 - "Frontend Runtime Dependencies"
Cohesion: 0.12
Nodes (17): @base-ui/react, class-variance-authority, clsx, @fontsource-variable/geist, next-themes, react-dom, recharts, @tailwindcss/vite (+9 more)

### Community 21 - "Frontend Dev Dependencies"
Cohesion: 0.12
Nodes (17): oxlint, @tanstack/router-plugin, @types/node, @types/react, @types/react-dom, typescript, vite, @vitejs/plugin-react (+9 more)

### Community 22 - "Investigation Platform Models"
Cohesion: 0.16
Nodes (16): create_investigation(), CreateInvestigation, Investigation, InvestigationEvent, Investigation platform tables. An investigation's evidence and report are derive, Append-only execution history: every prompt, retrieval param, model version,, Report, test_investigation_detail_includes_hypotheses_and_links() (+8 more)

### Community 23 - "Hybrid Retrieval Tests"
Cohesion: 0.20
Nodes (15): Session, Transactional unit of work: commits on success, rolls back on error., session_scope(), _corpus(), Phase 5: hybrid retrieval ranks known-relevant docs top-3; filters, graph hops,, Three topic-distinct documents, ingested once per module — per-test copies     w, test_citations_resolve_and_missing_chunks_raise(), test_filters_constrain_results() (+7 more)

### Community 24 - "Entity Extraction"
Cohesion: 0.16
Nodes (13): CompanyMatcher, Mention, Deterministic entity extraction with precision guards (docs/RISKS.md #1).  Ticke, Built once from the canonical companies table, reused across documents.      pon, companies: (id, name, tickers, aliases), _get_matcher(), matcher(), Precision guards from docs/RISKS.md #1: bare tickers never match; names need wor (+5 more)

### Community 25 - "Config & JSON Logging"
Cohesion: 0.16
Nodes (11): BaseSettings, LogRecord, _setup(), Settings, configure_logging(), JsonFormatter, Structured JSON logging (Design Bible §8: every failure observable)., SEC EDGAR connector: recent filings for the configured watchlist via the officia (+3 more)

### Community 26 - "SEC EDGAR Connector"
Cohesion: 0.18
Nodes (11): get_settings(), fetch_bytes(), Client, Streaming GET capped at settings.max_fetch_bytes — a single oversized or     mal, Client, Session, SecEdgarConnector, _ensure_test_db() (+3 more)

### Community 27 - "Deterministic Pipeline Stages"
Cohesion: 0.27
Nodes (15): _build_graph(), _chunk(), _embed(), _extract_entities(), _extract_metadata(), _pack_paragraphs(), _parse(), Session (+7 more)

### Community 28 - "Pipeline Worker"
Cohesion: 0.23
Nodes (15): claim_next(), _execute(), main_loop(), make_connector(), Job, Session, UUID, Pipeline worker: claims outbox jobs with SKIP LOCKED, runs stages, records every (+7 more)

### Community 29 - "Domain Repositories & Invariants"
Cohesion: 0.19
Nodes (9): DocumentRepository, UUID, Repositories for the knowledge aggregates. All DB access above core goes through, The only sanctioned mutation; content columns are trigger-guarded., _doc(), Phase 2 invariants: immutability, append-only events, canonical uniqueness, migr, test_document_content_is_immutable(), test_document_source_native_id_dedupes() (+1 more)

### Community 30 - "Knowledge Layer Models"
Cohesion: 0.19
Nodes (13): DeclarativeBase, Base, Declarative base for all Argus models., Chunk, DocumentCompany, EntityMention, GraphEdge, GraphNode (+5 more)

### Community 31 - "Connector Protocol Stubs"
Cohesion: 0.21
Nodes (6): DocumentRef, CompanyProfilesConnector, Ingest today's registry snapshot (provenance) and upsert canonical companies., StubConnector, _FakeWireConnector, Minimal Connector: discover() returns refs with no inline content, so     ingest

### Community 33 - "RSS Connector Tests"
Cohesion: 0.15
Nodes (4): RSS/Atom news connector. Entry content is the document (article pages are paywal, RssConnector, Connectors are independently testable against recorded fixtures (Bible §8) — no, test_rss_discover_parses_fixture()

### Community 34 - "Domain Events & Enqueue"
Cohesion: 0.26
Nodes (11): ColumnElement, emit(), enqueue(), datetime, Job, Session, UUID, Domain event append + job outbox (ADR-0003). Both writes happen in the caller's (+3 more)

### Community 35 - "Frontend API Types"
Cohesion: 0.18
Nodes (11): Citation, Evidence, Hypothesis, Investigation, InvestigationDetail, InvestigationLinkRef, InvestigationTask, Job (+3 more)

### Community 37 - "Test DB Fixtures"
Cohesion: 0.20
Nodes (7): Engine, get_engine(), db_session(), _investigation_task_handler(), migrated_db(), Fresh schema per session: argus_test persists across pytest runs, and     accumu, engine.run/refresh (Task 6) drain investigation.task jobs through the outbox

### Community 38 - "Content-Addressed Raw Store"
Cohesion: 0.31
Nodes (9): Path, Content-addressed raw store (Bible §14: raw data is permanent, never modified)., Store bytes by sha256. Returns (checksum, relative path). Idempotent., Parsed layer is derived and disposable; path is deterministic., read_parsed(), read_raw(), _root(), write_parsed() (+1 more)

### Community 39 - "Web Package Manifest"
Cohesion: 0.20
Nodes (9): name, private, scripts, build, dev, lint, preview, type (+1 more)

### Community 41 - "Oxlint Config"
Cohesion: 0.22
Nodes (8): oxc, typescript, warn, plugins, rules, react/only-export-components, react/rules-of-hooks, $schema

### Community 42 - "Embedding Providers"
Cohesion: 0.31
Nodes (5): FakeProvider, FastEmbedProvider, get_provider(), Embedding provider. Default is fastembed (ONNX all-MiniLM-L6-v2): local, determi, Deterministic bag-of-words feature hashing for tests: no model download, and

### Community 45 - "Connector Framework"
Cohesion: 0.38
Nodes (6): ingest(), Session, Connector framework. Connectors only discover and fetch; the framework owns dedu, Entry point used by scheduler and CLI; honors a connector-specific run()., Run one connector pass: discover refs, fetch new ones, persist, enqueue parse., run_connector()

### Community 46 - "Knowledge Graph Builder"
Cohesion: 0.43
Nodes (6): build_for_document(), ensure_company_node(), Session, UUID, Knowledge graph construction (Bible §18: relationships are intelligence).  V1 ed, Idempotent: rebuilds this document's edges for the given pipeline version.

### Community 47 - "Entity Timeline"
Cohesion: 0.43
Nodes (6): datetime, Session, UUID, Temporal knowledge: entity-scoped documents ordered by publication time. Compute, timeline(), TimelineEntry

### Community 48 - "Icon Sprite Sheet"
Cohesion: 0.62
Nodes (7): icons.svg (Icon Sprite Sheet), bluesky-icon symbol, discord-icon symbol, documentation-icon symbol, github-icon symbol, social-icon symbol, x-icon symbol

### Community 50 - "Frontend API Client"
Cohesion: 0.33
Nodes (4): api, ApiError, getApiKey(), request()

### Community 51 - "Computed Confidence"
Cohesion: 0.40
Nodes (5): Evidence, compute(), datetime, Deterministic confidence: a weighted, explainable function over evidence. Never, evidence + {document_id: Document} → {"score": float, "components": {...}}.

### Community 52 - "Migration 0002 Domain Tables"
Cohesion: 0.60
Nodes (4): _created_at(), Column, upgrade(), _uuid_pk()

### Community 53 - "Migration 0004 Investigations"
Cohesion: 0.60
Nodes (4): _created_at(), Column, upgrade(), _uuid_pk()

### Community 54 - "Migration 0005 Eval Runs"
Cohesion: 0.60
Nodes (4): _created_at(), Column, upgrade(), _uuid_pk()

### Community 55 - "Citation Assembly"
Cohesion: 0.47
Nodes (5): Citation, Session, UUID, Citation assembly: a citation is the guaranteed-resolvable traversal chunk → doc, resolve()

### Community 56 - "Graph Neighborhood Traversal"
Cohesion: 0.47
Nodes (5): GraphHop, neighborhood(), Session, UUID, Graph traversal: depth-limited neighborhood expansion over typed edges via a rec

### Community 57 - "Signal Ridge Visual"
Cohesion: 0.40
Nodes (4): draw(), EMBER, noise(), STEEL

### Community 58 - "Status Dot Component"
Cohesion: 0.60
Nodes (5): CLAY_STATUSES, dotClasses(), EMBER_STATUSES, StatusDot(), STEEL_STATUSES

### Community 59 - "CLI Ops Commands"
Cohesion: 0.50
Nodes (4): ingest(), Run one connector pass now (company_profiles | sec_edgar | rss)., One-screen ops snapshot: job queue, dead jobs, documents, recent pipeline runs., status()

### Community 60 - "Task DAG View"
Cohesion: 0.83
Nodes (3): ACTIVE_STATUSES, computeDepths(), TaskDag()

### Community 61 - "Stack Exclusions & SPA Root"
Cohesion: 0.67
Nodes (3): Deliberate exclusions (Neo4j, Kafka, dedicated vector DB, ...), SPA root mount (#root + main.tsx bootstrap, dark class), React + TypeScript + Vite template

### Community 62 - "Layer Direction Rule"
Cohesion: 0.67
Nodes (3): Layer stack (ui/api...core) with import direction, Architectural philosophy: layered architecture, Layer direction hard rule (import-linter enforced)

### Community 63 - "Product Philosophy Principles"
Cohesion: 1.00
Nodes (3): 12 core principles (Knowledge First ... Simplicity over Cleverness), PRD product philosophy (Knowledge/Evidence/Human/Evolution First), PRD-V2 product philosophy (8 principles: planning precedes execution, ...)

### Community 64 - "Docker Compose Services"
Cohesion: 0.67
Nodes (3): api service (uvicorn FastAPI), postgres service (pgvector/pgvector:pg16), worker service (argus worker)

### Community 65 - "CI Jobs"
Cohesion: 0.67
Nodes (3): CI backend job (pytest vs pgvector, ruff, lint-imports), CI image job (Docker build + GHCR push on main), CI web job (npm lint + build)

## Knowledge Gaps
- **216 isolated node(s):** `argus`, `$schema`, `typescript`, `oxc`, `react/rules-of-hooks` (+211 more)
  These have ≤1 connection - possible missing edges or undocumented components.
- **91 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `session_scope()` connect `Hybrid Retrieval Tests` to `API Security Tests`, `Test DB Fixtures`, `Pipeline Integration Tests`, `API Routes`, `Task DAG Orchestrator`, `Evaluation Harness`, `Events & Jobs Outbox`, `Investigation Engine Tests`, `Operations CLI`, `Orchestrator Tests`, `Investigation Engine`, `FastAPI Composition Root`, `Investigation Platform Models`, `CLI Ops Commands`, `Pipeline Worker`?**
  _High betweenness centrality (0.064) - this node is a cross-community bridge._
- **Why does `get_settings()` connect `SEC EDGAR Connector` to `Agent Runtime & Evidence`, `RSS Connector Tests`, `API Security Tests`, `Test DB Fixtures`, `Content-Addressed Raw Store`, `Pipeline Integration Tests`, `Task DAG Orchestrator`, `Evaluation Harness`, `Embedding Providers`, `Events & Jobs Outbox`, `Connector Framework`, `FastAPI Composition Root`, `Config & JSON Logging`, `Deterministic Pipeline Stages`, `Pipeline Worker`, `Connector Protocol Stubs`?**
  _High betweenness centrality (0.060) - this node is a cross-community bridge._
- **Why does `drain_queue()` connect `Pipeline Integration Tests` to `Agent Runtime & Evidence`, `API Security Tests`, `Test DB Fixtures`, `Evaluation Harness`, `Events & Jobs Outbox`, `Investigation Engine Tests`, `Operations CLI`, `Orchestrator Tests`, `FastAPI Composition Root`, `Investigation Platform Models`, `Hybrid Retrieval Tests`, `Pipeline Worker`?**
  _High betweenness centrality (0.045) - this node is a cross-community bridge._
- **Are the 73 inferred relationships involving `session_scope()` (e.g. with `create_investigation()` and `get_db()`) actually correct?**
  _`session_scope()` has 73 INFERRED edges - model-reasoned connections that need verification._
- **Are the 3 inferred relationships involving `drain_queue()` (e.g. with `session_scope()` and `Job`) actually correct?**
  _`drain_queue()` has 3 INFERRED edges - model-reasoned connections that need verification._
- **Are the 31 inferred relationships involving `Job` (e.g. with `CreateInvestigation` and `CreateLink`) actually correct?**
  _`Job` has 31 INFERRED edges - model-reasoned connections that need verification._
- **Are the 29 inferred relationships involving `get_settings()` (e.g. with `run_structured()` and `collect()`) actually correct?**
  _`get_settings()` has 29 INFERRED edges - model-reasoned connections that need verification._