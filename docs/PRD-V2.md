# ARGUS V2 — Product Requirements Document

**Version:** 2.0
**Status:** Draft
**Owner:** Sri Krishna V

---

## Research Execution Engine

### Executive Summary

Argus is an Investigation Operating System built for financial research.

Unlike traditional AI assistants that generate answers from retrieved documents, Argus treats every user request as an investigation requiring structured planning, evidence collection, validation, reasoning and synthesis.

The current version establishes the architectural foundations of the platform through ingestion pipelines, hybrid retrieval, a knowledge platform, investigation management and report generation.

The next evolution transforms Argus into a Research Execution Engine capable of autonomously planning investigations, coordinating specialist AI agents, constructing structured evidence models and generating explainable, citation-backed research reports.

The objective is not to build another chat application.

The objective is to build a system that reasons like an institutional research analyst.

---

### Vision

Argus enables analysts to investigate complex financial questions through structured evidence rather than conversational prompting.

Instead of asking an LLM for an answer, users initiate investigations.

Every investigation becomes a reproducible execution pipeline that:

- Plans research
- Identifies unknowns
- Collects evidence
- Validates sources
- Discovers relationships
- Resolves contradictions
- Measures confidence
- Synthesizes findings
- Produces transparent reports

---

### Product Philosophy

Argus is built around one core belief:

> AI should execute investigations — not conversations.

This philosophy influences every capability within the platform.

**Principle 1 — Planning precedes execution.**
The system must determine how to investigate before beginning evidence collection.

**Principle 2 — Evidence precedes reasoning.**
Reasoning cannot occur until evidence has been gathered and validated.

**Principle 3 — Knowledge is structured.**
Documents are temporary. Knowledge persists.

**Principle 4 — Every conclusion must be traceable.**
Every statement produced by the system should reference supporting evidence.

**Principle 5 — Confidence is measurable.**
The system should never communicate certainty without evaluating supporting evidence.

**Principle 6 — Investigations are reproducible.**
Running the same investigation tomorrow should produce an explainable evolution rather than unpredictable behaviour.

**Principle 7 — AI systems collaborate.**
Different reasoning tasks require different specialists.

**Principle 8 — Humans remain decision makers.**
Argus recommends. Analysts decide.

---

### Product Goals

Argus V2 will transform investigations into structured execution pipelines.

The platform shall:

- Plan investigations before execution
- Coordinate specialist research agents
- Build structured evidence models
- Maintain investigation state
- Continuously refine investigation plans
- Detect knowledge gaps
- Produce transparent research reports
- Measure investigation confidence
- Improve through evaluation

---

### Non-Goals

Argus is not intended to become:

- Portfolio management software
- Trading software
- Market prediction software
- Auto-investment software
- Portfolio optimization software
- ChatGPT for finance
- Enterprise identity platform
- CRM
- Business intelligence dashboard

---

### Current State Assessment

The existing platform provides strong architectural foundations.

**Current Strengths**

- Modular architecture
- Hybrid retrieval foundation
- Knowledge platform
- Investigation abstraction
- Report generation
- Citation support
- Data ingestion framework
- Evaluation infrastructure

These capabilities establish the execution environment. However, investigations remain execution-first rather than planning-first. The system currently lacks structured research planning.

**Current investigation flow**

```
Question
↓
Retrieve Documents
↓
LLM
↓
Report
```

**Target investigation flow**

```
Question
↓
Investigation Planning
↓
Research Graph
↓
Retrieval Planning
↓
Evidence Collection
↓
Knowledge Construction
↓
Evidence Validation
↓
Multi-Agent Reasoning
↓
Confidence Analysis
↓
Report Generation
```

---

### Product Success Metrics

Argus V2 will be evaluated using investigation quality rather than model quality.

Primary metrics include:

- Investigation completion rate
- Evidence coverage
- Citation completeness
- Source diversity
- Contradiction detection rate
- Planning accuracy
- Agent utilization
- Confidence calibration
- Investigation reproducibility
- Research latency

---

## Research Execution Engine — Overview

The Research Execution Engine is the core capability introduced in Argus V2.

Every investigation executed by the platform passes through this engine. The engine transforms user intent into an executable research workflow. It consists of four intelligence layers.

```
Research Execution Engine
├── Investigation Intelligence
├── Retrieval Intelligence
├── Knowledge Intelligence
└── Agent Intelligence
```

Each layer owns a specific responsibility. No capability overlaps. No component performs multiple responsibilities.

---

## Capability 1 — Investigation Intelligence

### Purpose

Investigation Intelligence determines **what should be investigated**.

It converts ambiguous research questions into structured execution plans. Rather than immediately retrieving documents, the system first understands the investigation itself.

### Objectives

The Investigation Intelligence layer shall:

- Understand investigation intent
- Identify research objectives
- Generate execution plans
- Track investigation progress
- Manage investigation lifecycle
- Adapt investigations as new evidence appears

It consists of four core systems:

```
Investigation Intelligence
├── Investigation Planner
├── Investigation DAG
├── Dynamic Replanning
└── Investigation State Machine
```

---

### Capability 1.1 — Investigation Planner

**Problem**

Current investigations execute immediately after receiving a user question. This creates several limitations:

- Important evidence may never be collected
- Retrieval becomes query-driven rather than objective-driven
- Parallel execution becomes impossible
- Research depth depends on prompt quality
- Investigation progress cannot be measured

Large financial investigations require planning before execution.

**Motivation**

Human analysts rarely begin researching immediately. Instead they determine:

- What needs to be answered?
- Which evidence is required?
- Which sources should be consulted?
- Which unknowns exist?
- Which tasks depend on others?

Argus should replicate this workflow.

**User Stories**

- As a research analyst, I want Argus to determine how an investigation should be executed, so that research becomes systematic rather than conversational.
- As an investment analyst, I want complex investigations automatically decomposed, so that multiple evidence streams can be explored simultaneously.

**Functional Requirements**

The Investigation Planner shall:

- Interpret research objectives
- Identify investigation type
- Detect required evidence categories
- Generate executable research plans
- Estimate investigation complexity
- Estimate execution cost
- Prioritize investigation tasks
- Produce dependency relationships
- Allocate work to specialist agents
- Maintain planning metadata

The planner shall support investigations including:

- Company research
- Industry analysis
- Executive profiling
- Risk assessment
- Event investigation
- Earnings analysis
- Competitive analysis
- Supply chain analysis
- Regulatory investigations
- M&A investigations

**Non-Functional Requirements**

- Planning should be deterministic. Equivalent investigations should produce equivalent execution plans.
- Planning should remain interpretable. Every generated task must explain why it exists.

**Out of Scope**

The planner will not:

- Generate reports
- Retrieve documents
- Evaluate evidence
- Make investment decisions

**Dependencies**

- Investigation classification
- Agent registry
- Retrieval capabilities
- Knowledge platform

**Success Metrics**

- Planning accuracy
- Task completeness
- Dependency correctness
- Planning latency
- Investigation success rate

**Acceptance Criteria**

Given a financial research question, the planner produces:

- Investigation objective
- Investigation type
- Required evidence categories
- Execution tasks
- Task dependencies
- Estimated complexity
- Assigned specialist agents

...without requiring manual planning.

---

### Capability 1.2 — Investigation DAG

**Problem**

Current investigations execute sequentially. Research tasks frequently have dependencies — some tasks may execute independently, others require previous evidence. Sequential execution wastes time and reduces reasoning quality.

**Motivation**

Every investigation should become an execution graph rather than a prompt chain. This graph becomes the source of truth for the investigation.

**User Story**

As an analyst, I want investigations represented as dependency graphs, so that execution order is determined automatically.

**Functional Requirements**

The system shall represent every investigation as a Directed Acyclic Graph (DAG). Each node shall represent a single research objective.

Nodes may include:

- Retrieve SEC filings
- Analyze earnings
- Extract executive changes
- Compare competitors
- Identify litigation
- Build event timeline
- Validate claims
- Calculate confidence
- Generate synthesis

Each node shall maintain:

- Objective
- Inputs
- Outputs
- Dependencies
- Status
- Assigned agent
- Confidence
- Evidence references
- Execution history

The DAG shall support:

- Parallel execution
- Dependency resolution
- Partial completion
- Incremental updates
- Failure recovery
- Resume from checkpoint

**Non-Functional Requirements**

- The graph should remain immutable after execution begins. Changes require explicit replanning.
- Execution history must remain fully traceable.

**Success Metrics**

- Parallel task utilization
- Dependency correctness
- Average execution depth
- Recovery success rate

**Acceptance Criteria**

- Every investigation is converted into a valid execution graph before evidence collection begins.
- Every executed task can be traced back to an investigation objective.

---

### Capability 1.3 — Dynamic Replanning

**Problem**

Financial investigations are inherently non-linear. New evidence frequently changes the direction of an investigation, invalidates existing assumptions, or introduces entirely new lines of inquiry. A static execution plan cannot adapt to these evolving conditions, causing the system either to ignore critical findings or require manual intervention.

**Motivation**

An experienced analyst continuously revises their research strategy as new information becomes available. Argus should behave similarly. The investigation plan must evolve based on evidence rather than remain fixed after initial planning.

**User Stories**

- As an analyst, I want the investigation plan to adapt automatically when important evidence is discovered, so that research remains relevant without restarting the investigation.
- As a portfolio researcher, I want newly discovered risks to trigger additional investigation tasks, so that the system explores emerging evidence autonomously.

**Functional Requirements**

The system shall continuously evaluate investigation progress.

The replanning engine shall detect:

- Newly discovered entities
- Emerging relationships
- Contradictory evidence
- Incomplete objectives
- Failed execution paths
- Insufficient evidence coverage
- Newly introduced risks

When required, the engine shall:

- Create additional investigation tasks
- Remove obsolete tasks
- Modify execution priority
- Reassign specialist agents
- Update dependency relationships
- Merge duplicate investigation branches

Every replan shall preserve complete execution history. No completed investigation task shall be discarded.

**Non-Functional Requirements**

- Replanning shall not invalidate completed evidence.
- The system shall maintain deterministic investigation history.
- Every replanning event shall be explainable.

**Out of Scope**

The replanning engine shall not:

- Rewrite completed reports
- Delete collected evidence
- Modify analyst annotations
- Override analyst decisions

**Dependencies**

- Investigation Planner
- Investigation DAG
- Knowledge Intelligence
- Retrieval Intelligence
- Agent Intelligence

**Success Metrics**

- Successful replanning rate
- Investigation completion improvement
- Evidence coverage improvement
- Duplicate investigation reduction
- Analyst intervention reduction

**Acceptance Criteria**

When newly discovered evidence changes the investigation scope, the system automatically updates the execution graph while preserving completed work.

---

### Capability 1.4 — Investigation State Machine

**Problem**

Investigations currently behave like single execution sessions. Institutional research requires investigations that can pause, resume, branch, review and evolve over weeks or months. The platform requires explicit lifecycle management.

**Motivation**

An investigation is an evolving asset rather than a single request. The platform should understand the lifecycle of every investigation.

**User Stories**

- As an analyst, I want investigations to persist across sessions, so that research can continue over time.
- As a research lead, I want to understand the current status of every investigation, so that I can prioritize ongoing work.

**Functional Requirements**

Every investigation shall exist within one of the following states:

```
Draft
↓
Planning
↓
Executing
↓
Evidence Review
↓
Reasoning
↓
Confidence Evaluation
↓
Analyst Review
↓
Completed
↓
Archived
```

The system shall support:

- Pause
- Resume
- Cancel
- Branch
- Merge
- Restart
- Archive

Each transition shall generate immutable investigation events.

Every investigation shall expose:

- Current status
- Previous status
- Investigation age
- Active tasks
- Completed tasks
- Pending evidence
- Assigned agents
- Overall confidence

**Non-Functional Requirements**

- State transitions shall be deterministic.
- No investigation shall exist in multiple execution states simultaneously.

**Success Metrics**

- Successful resume rate
- Investigation completion rate
- Average investigation duration
- Investigation abandonment rate

**Acceptance Criteria**

- Every investigation maintains a valid lifecycle throughout execution.
- Users can pause and resume investigations without loss of context.

---

## Capability 2 — Retrieval Intelligence

### Purpose

Retrieval Intelligence determines **where evidence should come from**.

Traditional RAG systems retrieve documents. Argus plans evidence acquisition. Retrieval is treated as an investigation strategy rather than a database query.

### Objectives

The Retrieval Intelligence layer shall:

- Plan retrieval
- Select evidence sources
- Optimize evidence diversity
- Rank evidence quality
- Remove duplication
- Merge context

It consists of:

```
Retrieval Intelligence
├── Query Planner
├── Hybrid Retrieval
├── Source Ranking
├── Evidence Deduplication
└── Context Fusion
```

---

### Capability 2.1 — Query Planner

**Problem**

Current retrieval begins immediately using the user's original question. Financial investigations often require multiple specialized searches rather than a single query.

**Motivation**

An experienced analyst rarely searches exactly what was asked. Instead they create multiple investigative questions. Argus should perform the same decomposition.

**User Story**

As an analyst, I want my investigation automatically converted into multiple research queries, so that evidence coverage improves.

**Functional Requirements**

The Query Planner shall generate:

- Entity queries
- Event queries
- Financial queries
- Executive queries
- Legal queries
- Competitor queries
- Regulatory queries
- Macroeconomic queries

The planner shall identify:

- Primary entities
- Secondary entities
- Investigation timeframe
- Geography
- Industry
- Evidence requirements

Each query shall include:

- Objective
- Evidence target
- Expected source types
- Retrieval priority

**Non-Functional Requirements**

- Equivalent investigations should generate equivalent query plans.
- Generated queries shall remain explainable.

**Success Metrics**

- Query diversity
- Entity coverage
- Evidence completeness
- Investigation recall

**Acceptance Criteria**

Every investigation produces multiple specialized retrieval plans before evidence collection begins.

---

### Capability 2.2 — Hybrid Retrieval

**Problem**

Single retrieval strategies fail on complex investigations. Vector search alone cannot capture chronology. Keyword search alone misses semantic similarity. Graph traversal alone lacks textual evidence.

**Motivation**

Institutional research requires multiple retrieval strategies working together.

**User Story**

As an analyst, I want Argus to search across multiple evidence representations, so that investigations are comprehensive.

**Functional Requirements**

The platform shall support:

- Semantic Retrieval
- Keyword Retrieval
- Metadata Retrieval
- Graph Traversal
- Timeline Retrieval
- Citation Expansion
- Relationship Traversal
- Entity-Centric Retrieval
- Claim-Based Retrieval

Hybrid retrieval shall determine which retrieval methods are appropriate for each investigation. Results shall be merged into a unified evidence collection.

**Non-Functional Requirements**

- Retrieval quality shall prioritize evidence relevance over document count.
- The retrieval process shall remain reproducible.

**Dependencies**

- Query Planner
- Knowledge Platform
- Evidence Graph

**Success Metrics**

- Retrieval precision
- Retrieval recall
- Evidence diversity
- Investigation coverage

**Acceptance Criteria**

Every investigation combines multiple retrieval strategies rather than relying on a single retrieval mechanism.

---

### Capability 2.3 — Source Ranking

**Problem**

Not all evidence sources carry equal reliability. Current retrieval treats documents as equivalent. Financial investigations require source credibility assessment.

**Motivation**

Professional analysts naturally prioritize regulatory filings over anonymous social media posts. Argus should encode similar behaviour.

**Functional Requirements**

Every evidence source shall receive a quality assessment.

Ranking shall consider:

- Authority
- Freshness
- Independence
- Historical reliability
- Citation frequency
- Source provenance
- Data completeness
- Investigation relevance

The ranking engine shall expose reasoning for every assigned score.

**Success Metrics**

- High-quality source utilization
- Source diversity
- Analyst agreement
- Investigation confidence improvement

**Acceptance Criteria**

Every retrieved document contains an associated quality score and explanation.

---

### Capability 2.4 — Evidence Deduplication

**Problem**

Large investigations retrieve overlapping information from multiple sources. Duplicate evidence inflates confidence and wastes reasoning resources.

**Motivation**

Evidence should be represented once regardless of how many sources repeat it. The system should distinguish between corroboration and duplication.

**Functional Requirements**

The platform shall detect:

- Duplicate documents
- Duplicate claims
- Duplicate events
- Duplicate entities

The system shall preserve:

- Independent corroboration
- Source attribution
- Publication history

Duplicate evidence shall be merged into canonical representations.

**Non-Functional Requirements**

- Deduplication shall never remove original provenance.
- Every merge shall remain reversible.

**Success Metrics**

- Duplicate reduction
- Storage efficiency
- Confidence calibration improvement
- Evidence uniqueness

**Acceptance Criteria**

Repeated evidence is represented once while preserving every originating source.

---

### Capability 2.5 — Context Fusion

**Problem**

Retrieved evidence exists as disconnected observations. Reasoning requires coherent investigative context.

**Motivation**

Before specialist agents begin reasoning, evidence should be transformed into a structured investigation context. This context becomes the shared understanding of the investigation.

**Functional Requirements**

Context Fusion shall combine:

- Retrieved documents
- Entities
- Events
- Claims
- Timelines
- Financial metrics
- Relationships
- Citations

The resulting investigation context shall:

- Remove redundancy
- Preserve provenance
- Expose uncertainty
- Highlight contradictions
- Identify missing evidence
- Identify investigation gaps

The fused context becomes the primary input for downstream Knowledge Intelligence and Agent Intelligence.

**Non-Functional Requirements**

- Context construction shall remain deterministic and reproducible.
- The system shall preserve traceability from every synthesized context element back to its originating evidence.

**Success Metrics**

- Context completeness
- Evidence traceability
- Redundancy reduction
- Downstream reasoning quality

**Acceptance Criteria**

Before any reasoning agent executes, the system produces a unified investigation context representing all collected evidence, relationships, and uncertainties in a structured form.

---

## Capability 3 — Knowledge Intelligence

### Purpose

Knowledge Intelligence transforms raw evidence into structured understanding.

Traditional RAG systems treat documents as the primary unit of reasoning. Argus treats knowledge as the primary unit of reasoning. Documents are only evidence.

The platform reasons over:

- Entities
- Events
- Claims
- Relationships
- Timelines
- Evidence

...rather than PDFs or text chunks.

This capability becomes the cognitive memory of the Research Execution Engine.

### Objectives

Knowledge Intelligence shall:

- Extract knowledge from evidence
- Maintain canonical entities
- Build investigation graphs
- Resolve conflicting information
- Preserve provenance
- Track knowledge evolution
- Provide structured context to reasoning agents

The subsystem consists of:

```
Knowledge Intelligence
├── Evidence Graph
├── Timeline Engine
├── Entity Resolution
├── Claim Intelligence
├── Contradiction Detection
├── Knowledge Evolution
└── Cross Investigation Memory
```

---

### Capability 3.1 — Evidence Graph

**Problem**

Financial investigations produce disconnected observations. A filing references a CEO. A news article references a lawsuit. A transcript references declining margins. These observations remain isolated. Reasoning across isolated documents is inefficient.

**Motivation**

Professional analysts naturally build mental models connecting evidence. Argus should externalize this process. Evidence should become an interconnected graph rather than a collection of retrieved documents.

**User Story**

As an analyst, I want every piece of evidence connected to the entities, claims and events it supports, so that I can understand relationships instead of searching through documents.

**Functional Requirements**

The platform shall construct an Evidence Graph for every investigation.

Nodes may represent:

- Companies
- Executives
- Investors
- Products
- Business Units
- Markets
- Financial Metrics
- Events
- Claims
- Risks
- Documents

Relationships may include:

- owns
- acquired
- appointed
- resigned
- invested
- manufactures
- competes_with
- reported
- denied
- supports
- contradicts
- occurred_before
- occurred_after

Every node shall maintain:

- Canonical identifier
- Source references
- Confidence
- Last updated
- Investigation references

Every edge shall maintain:

- Relationship type
- Supporting evidence
- Confidence
- Provenance
- Temporal validity

**Non-Functional Requirements**

- The graph shall remain explainable. Every relationship must be traceable back to evidence.
- No inferred relationship may exist without supporting justification.

**Out of Scope**

The Evidence Graph will not:

- Predict relationships
- Invent entities
- Perform investment recommendations

**Dependencies**

- Retrieval Intelligence
- Entity Resolution
- Timeline Engine

**Success Metrics**

- Graph completeness
- Relationship precision
- Evidence traceability
- Entity coverage

**Acceptance Criteria**

Every investigation produces a structured Evidence Graph representing all discovered entities, events, claims and relationships with complete provenance.

---

### Capability 3.2 — Timeline Engine

**Problem**

Financial events are inherently temporal. Current retrieval presents evidence without chronology. Analysts must manually reconstruct timelines.

**Motivation**

Understanding sequence often matters more than understanding content. Example:

```
CEO resignation
↓
Supplier bankruptcy
↓
Revenue guidance reduction
↓
Credit downgrade
↓
Share price decline
```

This sequence explains causality. The Timeline Engine exists to reconstruct this automatically.

**User Story**

As an analyst, I want investigations automatically organized chronologically, so that I understand how events evolved.

**Functional Requirements**

The Timeline Engine shall extract:

- Event dates
- Relative dates
- Effective periods
- Reporting periods
- Deadlines
- Historical references

The engine shall:

- Order events
- Merge duplicate events
- Estimate uncertain dates
- Associate evidence
- Link events to entities
- Detect event chains
- Detect missing chronology

Each event shall contain:

- Timestamp
- Event description
- Entities involved
- Supporting evidence
- Confidence
- Source references

**Non-Functional Requirements**

- Chronology must remain deterministic.
- Conflicting timelines must remain visible.
- No inferred dates may replace observed dates.

**Success Metrics**

- Timeline completeness
- Event ordering accuracy
- Event coverage
- Missing chronology detection

**Acceptance Criteria**

Every investigation produces a navigable timeline representing all significant discovered events.

---

### Capability 3.3 — Entity Resolution

**Problem**

Entities appear under different names across sources. Examples:

- Meta
- Meta Platforms
- Facebook
- META

These all refer to the same organization. Without canonical resolution, investigations fragment.

**Motivation**

Institutional research requires a unified representation of real-world entities. Argus must reason about companies — not document strings.

**Functional Requirements**

The system shall resolve:

- Companies
- People
- Products
- Locations
- Funds
- Organizations
- Tickers
- Subsidiaries

Resolution shall consider:

- Aliases
- Ticker symbols
- Identifiers
- Historical names
- Parent organizations
- Subsidiaries

The platform shall maintain one canonical identity. Every alias shall remain searchable.

**Success Metrics**

- Resolution precision
- Duplicate reduction
- Investigation consistency

**Acceptance Criteria**

Equivalent real-world entities are represented by one canonical identity.

---

### Capability 3.4 — Claim Intelligence

**Problem**

Documents contain facts, opinions, predictions and marketing language. Current retrieval treats them equally.

**Motivation**

The platform should reason over claims rather than paragraphs. A claim becomes the smallest unit of reasoning.

Example:

- "Revenue increased 18%"
- "Company plans expansion"
- "CEO resigned"

Each is a structured claim.

**Functional Requirements**

The platform shall identify claims. Each claim shall include:

- Claim text
- Subject
- Predicate
- Object
- Supporting evidence
- Contradicting evidence
- Confidence
- Timestamp
- Source

Claims shall become reusable investigation objects.

**Non-Functional Requirements**

- Claims shall remain independent from source documents.
- Multiple documents may support one claim.

**Success Metrics**

- Claim extraction quality
- Claim coverage
- Evidence mapping accuracy

**Acceptance Criteria**

Every investigation represents extracted facts as structured claims.

---

### Capability 3.5 — Contradiction Detection

**Problem**

Financial sources frequently disagree. Current systems simply retrieve both documents. They do not recognize disagreement.

**Motivation**

Contradictions are valuable evidence. Disagreement should become a first-class investigation artifact.

**User Story**

As an analyst, I want conflicting evidence highlighted automatically, so that I investigate uncertainty rather than overlook it.

**Functional Requirements**

The platform shall detect contradictions between:

- Claims
- Financial metrics
- Dates
- Executive statements
- Regulatory filings
- News reports

Contradictions shall include:

- Supporting evidence
- Opposing evidence
- Confidence difference
- Source quality
- Affected entities

Contradictions shall generate investigation tasks.

**Non-Functional Requirements**

- The platform shall distinguish contradiction from uncertainty.
- No contradiction shall be hidden.

**Success Metrics**

- Contradiction recall
- False contradiction rate
- Investigation usefulness

**Acceptance Criteria**

Contradictory claims are automatically identified and surfaced during investigations.

---

### Capability 3.6 — Knowledge Evolution

**Problem**

Knowledge changes. Companies evolve. Executives change. Financials update. Current investigations capture snapshots. Institutional research requires history.

**Motivation**

Knowledge should evolve instead of being overwritten. The platform must understand change over time.

**Functional Requirements**

Every knowledge object shall support version history. Changes shall record:

- Previous value
- New value
- Timestamp
- Evidence
- Investigation
- Confidence

The platform shall expose:

- Historical snapshots
- Change history
- Knowledge freshness
- Stale knowledge detection

**Non-Functional Requirements**

- Knowledge history shall be immutable.
- Previous states shall always remain recoverable.

**Success Metrics**

- Version completeness
- Freshness accuracy
- Historical retrieval quality

**Acceptance Criteria**

Every knowledge object maintains a complete historical evolution.

---

### Capability 3.7 — Cross Investigation Memory

**Problem**

Investigations currently exist independently. Knowledge gained in one investigation is not reused elsewhere. This results in duplicated work and fragmented understanding.

**Motivation**

Analysts continuously build upon prior research. Argus should accumulate institutional memory. Every completed investigation should enrich future investigations.

**User Story**

As an analyst, I want previous investigations to inform future research, so that existing knowledge is reused instead of rediscovered.

**Functional Requirements**

The platform shall maintain persistent investigation memory. Memory shall include:

- Validated entities
- Resolved claims
- Historical timelines
- Evidence relationships
- Investigation outcomes
- Confidence assessments

When a new investigation begins, the platform shall:

- Identify relevant prior investigations
- Surface reusable evidence
- Reuse validated knowledge
- Recommend related investigations
- Identify unresolved questions from previous work

Memory shall preserve provenance and investigation context. Previously validated knowledge shall never bypass evidence verification when new contradictory information is discovered.

**Non-Functional Requirements**

- Investigation memory shall improve research efficiency without introducing hidden assumptions.
- Every reused artifact shall remain traceable to its originating investigation.

**Success Metrics**

- Knowledge reuse rate
- Investigation acceleration
- Duplicate investigation reduction
- Analyst acceptance of reused evidence

**Acceptance Criteria**

New investigations automatically leverage relevant knowledge from prior investigations while preserving complete traceability and allowing evidence to be revalidated.

---

### Capability 3.8 — Memory Infrastructure (Build vs. Buy: Supermemory)

**Problem**

Cross Investigation Memory (3.7) requires a persistent, evolving knowledge substrate capable of tracking facts as they change, merging corroborating evidence, and surfacing contradictions across investigations conducted over months. Building this from scratch — contradiction resolution, temporal decay, entity-aware retrieval, graph traversal at scale — duplicates infrastructure that dedicated memory-layer providers already solve.

**Motivation**

Supermemory is a memory and context layer for AI agents built around a fact-based knowledge graph rather than a traditional chunk-based vector store. Each stored fact links to related facts through three relationship types:

- **Updates** — a new fact supersedes an old one (e.g. a claim about an executive's role changes)
- **Extends** — a new fact enriches an existing one without invalidating it
- **Derives** — the system infers a new insight from a pattern across facts

Facts are also typed (Facts, Preferences, Episodes) with different persistence rules, and temporary or expired information is forgotten automatically unless overridden.

This maps closely onto Knowledge Intelligence requirements already defined in this PRD:

- **Contradiction Detection (3.5)** — Supermemory's "Updates" relationship auto-detects when a new claim supersedes an old one.
- **Knowledge Evolution (3.6)** — every fact retains full version history (previous value, new value, timestamp) with nothing overwritten.
- **Cross Investigation Memory (3.7)** — investigations become persistent, queryable state rather than isolated sessions.

Rather than building this substrate internally, Argus could adopt Supermemory as the underlying memory engine for these three capabilities, focusing internal engineering effort on financial-domain-specific reasoning (claim intelligence, source ranking, evidence validation) that a general-purpose memory layer does not provide out of the box.

**Functional Requirements**

The platform shall:

- Store every resolved entity, claim, and evidence relationship as a memory object via the Supermemory API (`add` / `search`).
- Use Supermemory's automatic Updates/Extends/Derives graph to track how claims about an entity evolve across investigations, rather than re-implementing contradiction and versioning logic independently.
- Query Supermemory at investigation start to surface prior relevant investigations, resolved claims, and unresolved questions, supporting 3.7's requirement to identify relevant prior investigations.
- Tag every memory with its originating investigation ID, preserving provenance so a fact recalled from memory can be traced back to Argus's own Evidence Graph rather than treated as an opaque external fact.
- Route every fact recalled from Supermemory back through Argus's own Evidence Validation and Confidence Analysis stages before it can influence a conclusion — recalled memory re-enters an investigation as candidate evidence, never as an accepted finding.

**Non-Functional Requirements**

- Given the sensitivity of financial research data, memory storage shall use Supermemory's self-hosted or BYOC (bring-your-own-cloud) deployment rather than the shared multi-tenant hosted platform, keeping evidence inside Argus's own security perimeter.
- Memory retrieval latency shall not materially add to Context Fusion (2.5) latency budgets. Supermemory's reported sub-300ms recall is compatible with this constraint but shall be independently benchmarked under Argus's own investigation load before adoption.
- Automatic forgetting (temporary facts expiring after a stated date) shall be disabled or overridden for anything classified as investigation evidence. Financial evidence must follow Argus's own retention and archival rules (per 1.4 Investigation State Machine), not a generic consumer-memory decay policy.

**Out of Scope**

This integration will not:

- Replace the Evidence Graph (3.1) or Claim Intelligence (3.4). Supermemory supplies persistence and cross-session recall underneath them, not financial-domain extraction logic.
- Serve as the source of truth for investment-relevant conclusions. It remains a recall layer feeding candidate evidence back into validation.

**Dependencies**

- Cross Investigation Memory (3.7)
- Knowledge Evolution (3.6)
- Evidence Graph (3.1)
- Supermemory API or self-hosted deployment

**Success Metrics**

- Reduction in duplicate research across investigations touching the same entity (supports 3.7's duplicate investigation reduction metric)
- Memory recall latency under production load
- Rate of analyst-accepted vs. analyst-rejected prior claims surfaced from memory after revalidation

**Acceptance Criteria**

When a new investigation references an entity previously investigated, the system surfaces relevant prior facts and their evolution history from Supermemory, tags each with its originating investigation, and routes them through evidence validation before they influence the new investigation's conclusions.

Part 4 — Research Execution Engine
Capability 4
Agent Intelligence
Purpose

Agent Intelligence is responsible for executing investigations.

Investigation Intelligence determines what should be investigated.

Retrieval Intelligence determines where evidence comes from.

Knowledge Intelligence determines what the evidence means.

Agent Intelligence determines who performs each piece of work, when they perform it, and how their outputs are coordinated into a coherent investigation.

Agents are not autonomous chatbots.

Agents are deterministic execution units with clearly defined responsibilities operating within a shared investigation context.

Vision

Argus should resemble a high-performing institutional research team rather than a single intelligent assistant.

Every investigation is executed by specialists.

Each specialist owns one domain.

Each specialist contributes structured outputs.

No agent owns the entire investigation.

Reasoning is collaborative.

Execution is orchestrated.

Knowledge is shared.

Objectives

The Agent Intelligence layer shall:

Execute investigation plans
Coordinate specialist agents
Manage shared investigation context
Recover from execution failures
Validate intermediate outputs
Prevent duplicated work
Produce explainable execution traces

The subsystem consists of:

Agent Intelligence

├── Research Orchestrator
├── Specialist Agents
├── Shared Investigation Memory
├── Agent Coordination
├── Execution Recovery
├── Agent Observability
└── Human Collaboration
Capability 4.1
Research Orchestrator
Problem

Executing every investigation through a single LLM produces monolithic reasoning, poor specialization and limited observability.

The platform requires a dedicated orchestration capability responsible for coordinating execution.

Motivation

The orchestrator behaves like a research manager.

It does not perform research.

It assigns work.

Coordinates execution.

Monitors progress.

Collects outputs.

Ensures objectives are completed.

User Stories

As an analyst,

I want investigations executed through coordinated specialists,

so that each domain receives expert attention.

As a researcher,

I want execution progress continuously tracked,

so that long-running investigations remain transparent.

Functional Requirements

The orchestrator shall:

Receive an Investigation DAG.

Schedule executable tasks.

Assign tasks to appropriate specialist agents.

Maintain execution dependencies.

Track task completion.

Aggregate intermediate outputs.

Handle execution failures.

Trigger replanning when required.

Manage investigation checkpoints.

Prevent duplicate execution.

Terminate completed investigations.

The orchestrator shall never perform domain reasoning itself.

Non Functional Requirements

Execution scheduling shall remain deterministic.

Task assignment shall be reproducible.

Execution history shall be fully traceable.

Dependencies
Investigation Planner
Investigation DAG
Shared Investigation Memory
Specialist Agents
Success Metrics
Investigation completion rate
Scheduling efficiency
Parallel execution utilization
Failed task recovery
Execution latency
Acceptance Criteria

Given an Investigation DAG,

the orchestrator executes every task through specialist agents while maintaining execution dependencies and complete traceability.

Capability 4.2
Specialist Agent Framework
Problem

Financial investigations span multiple domains.

No single reasoning model performs equally well across all domains.

Specialization improves reasoning quality and system modularity.

Motivation

Argus should function like a research organization.

Each specialist owns one capability.

Agents collaborate through shared knowledge rather than conversational context.

Functional Requirements

Every specialist agent shall:

Own exactly one domain.

Receive structured objectives.

Consume structured investigation context.

Produce structured outputs.

Reference supporting evidence.

Return confidence.

Expose execution metadata.

Agents shall never communicate directly through free-form prompts.

Communication shall occur through structured investigation artifacts.

Initial Specialist Agents
Financial Analyst

Responsible for:

Financial statements
Revenue analysis
Margin analysis
Cash flow
Balance sheet
Valuation metrics
Capital allocation
Filings Analyst

Responsible for:

SEC filings
Annual reports
Quarterly reports
Regulatory disclosures
Governance documents
News Analyst

Responsible for:

News events
Market announcements
Executive interviews
Press releases
Breaking developments
Competitive Intelligence Analyst

Responsible for:

Competitor analysis
Industry positioning
Strategic comparisons
Market landscape
Executive Intelligence Analyst

Responsible for:

Leadership
Board changes
Insider activity
Organizational structure
Executive history
Risk Analyst

Responsible for:

Operational risks
Regulatory risks
Litigation
Supply chain
ESG
Reputation
Macro Analyst

Responsible for:

Economic indicators
Interest rates
Inflation
Sector trends
Government policy
Evidence Validation Agent

Responsible for:

Source verification
Citation validation
Claim verification
Evidence completeness
Report Synthesis Agent

Responsible for:

Combining validated outputs
Maintaining consistency
Generating structured reports
Non Functional Requirements

Specialists must remain independent.

Capabilities must not overlap.

Each agent shall remain replaceable.

Success Metrics
Specialist accuracy
Domain coverage
Investigation quality
Task completion rate
Acceptance Criteria

Every investigation task is executed by an explicitly defined specialist agent.

Capability 4.3
Shared Investigation Memory
Problem

LLMs naturally rely on conversational context.

Large investigations exceed context windows.

Conversation history is insufficient for institutional research.

Motivation

Investigation knowledge should exist independently from any model.

Agents should consume shared investigation state rather than previous prompts.

Functional Requirements

Shared memory shall maintain:

Current investigation objective

Execution graph

Collected evidence

Resolved entities

Claims

Relationships

Timeline

Confidence

Outstanding questions

Completed tasks

Pending tasks

Contradictions

Investigation metadata

Every agent shall read from shared memory.

Every agent shall contribute back into shared memory.

Memory becomes the single source of truth.

Non Functional Requirements

Memory shall remain model-independent.

Memory shall remain persistent.

Memory shall remain explainable.

Success Metrics
Context reuse
Investigation consistency
Duplicate reasoning reduction
Agent agreement
Acceptance Criteria

No agent depends upon conversational history to perform investigation tasks.

Capability 4.4
Agent Coordination
Problem

Specialists cannot operate independently.

Outputs from one specialist frequently become inputs for another.

Coordination is required.

Motivation

Research resembles a dependency graph.

Not parallel chat sessions.

Functional Requirements

The coordination system shall:

Manage dependencies.

Route outputs.

Trigger downstream tasks.

Detect blocked execution.

Synchronize investigation state.

Prevent conflicting updates.

Support:

Sequential execution

Parallel execution

Conditional execution

Iterative refinement

Collaborative reasoning

Non Functional Requirements

Execution order shall remain deterministic.

Coordination shall remain observable.

Success Metrics
Dependency satisfaction
Parallel utilization
Coordination latency
Acceptance Criteria

Specialist agents collaborate through structured execution rather than prompt passing.

Capability 4.5
Execution Recovery
Problem

Long-running investigations inevitably experience failures.

Failures should not terminate investigations.

Motivation

Research organizations recover from interruptions.

Argus should do the same.

Functional Requirements

The platform shall detect:

Agent failure

Timeout

Insufficient evidence

Conflicting outputs

Incomplete execution

Missing dependencies

Recovery actions include:

Retry

Alternative specialist assignment

Task rescheduling

Investigation replanning

Human escalation

Partial completion

Checkpoint restore

Non Functional Requirements

Recovery shall preserve completed work.

Execution history shall remain immutable.

Success Metrics
Recovery success
Retry effectiveness
Investigation completion
Failure isolation
Acceptance Criteria

Agent failures do not terminate investigations unless recovery strategies are exhausted.

Capability 4.6
Agent Observability
Problem

Current AI systems provide limited visibility into execution.

Users observe only final outputs.

Institutional research requires transparent execution.

Motivation

Every investigation should be inspectable.

Analysts should understand:

Who performed work.

What evidence was used.

Why decisions were made.

Functional Requirements

The platform shall expose:

Active agents

Completed tasks

Execution duration

Input evidence

Output artifacts

Dependencies

Failures

Confidence

Reasoning summaries

Resource utilization

Investigation progress

Every investigation shall produce a complete execution trace.

Non Functional Requirements

Observability shall never expose private reasoning.

Execution traces shall remain reproducible.

Success Metrics
Trace completeness
Investigation transparency
Debugging efficiency
Acceptance Criteria

Every completed investigation includes a complete execution history for every participating agent.

Capability 4.7
Human Collaboration
Problem

Financial research remains a human decision-making activity.

The system should accelerate analysts rather than replace them.

Motivation

Argus is a collaborative intelligence platform.

Analysts remain accountable for conclusions.

Functional Requirements

Analysts shall be able to:

Pause investigations

Resume investigations

Review intermediate findings

Approve evidence

Reject evidence

Modify investigation objectives

Add annotations

Request additional research

Override conclusions

Restart execution

Branch investigations

Every analyst action becomes part of the investigation history.

Non Functional Requirements

Human decisions shall always take precedence over autonomous execution.

The platform shall preserve all analyst interventions.

Success Metrics
Analyst adoption
Investigation completion
Human intervention usefulness
Review efficiency
Acceptance Criteria

Analysts remain active participants throughout the investigation lifecycle while preserving complete transparency of both human and autonomous contributions.

Research Execution Engine Complete

With this capability, the core execution model of Argus is complete:

Question
        │
        ▼
Investigation Intelligence
(What should be investigated?)
        │
        ▼
Retrieval Intelligence
(Where should evidence come from?)
        │
        ▼
Knowledge Intelligence
(What does the evidence mean?)
        │
        ▼
Agent Intelligence
(Who executes each task?)
        │
        ▼
Evidence Synthesis
        │
        ▼
Confidence Evaluation
        │
        ▼
Final Research Report