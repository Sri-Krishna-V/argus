# V2 Phase 1: Investigation Task DAG + Orchestrator — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Every investigation compiles into a validated task DAG (fan-out evidence collection per query → fan-in synthesis) executed deterministically through the existing jobs outbox, replacing the monolithic linear pipeline while keeping the external API behavior identical.

**Architecture:** The LLM planner produces a typed research plan; deterministic code in `investigations/orchestrator.py` compiles it into `investigation_tasks` rows validated with stdlib `graphlib`, and enqueues outbox jobs (`job_type="investigation.task"`). The dataplatform worker gains a handler registry so the CLI composition root can wire investigation handlers in without an upward layer import. `engine.execute()` keeps synchronous semantics by draining the investigation's own jobs in-process; real parallelism arrives by running more workers (ADR-0010).

**Tech Stack:** SQLAlchemy 2 (sync), Alembic hand-written migrations, pydantic v2, stdlib `graphlib`, pytest.

## Global Constraints (from CLAUDE.md + master spec)

- Layer direction enforced by import-linter: `ui/api → investigations → agentruntime → research → dataplatform → knowledge → observability → core`. dataplatform must NEVER import investigations.
- Documents immutable; events append-only; `jobs` is a disposable outbox.
- Every AI output cites chunks; evidence without a chunk reference is rejected; the citation gate is unchanged.
- Confidence is computed, never LLM-generated.
- Sync code only (ADR-0004): sync SQLAlchemy, sync httpx, `def` endpoints.
- All queue time predicates use the DB clock (`func.now()`), never `datetime.now(UTC)` — the WSL2 wall clock steps backward (commit 9b1d07e).
- Migrations hand-written, numbered `000N_slug.py`, no autogenerate.
- Settings via `argus.core.config.get_settings()`, env prefix `ARGUS_`.
- Tests must cover failure modes and boundaries, not just happy paths (user rule).
- Verify with `make lint && make test` before every commit (DB on `127.0.0.1:15432` per docker-compose.override.yml; tests auto-use `argus_test`).
- AI paths are tested with the fake adapter pattern from `tests/test_investigations.py::_fake_adapter` — no live LLM calls in tests.

---

### Task 1: Typed plan schema (PlannedQuery) with back-compat

**Files:**
- Modify: `src/argus/agentruntime/schemas.py` (ResearchPlan)
- Modify: `src/argus/agentruntime/planner.py` (INSTRUCTION)
- Modify: `src/argus/agentruntime/evidence.py` (collect loop uses `q.query`)
- Modify: `src/argus/investigations/engine.py` (`_collect` event payload + `replay_retrieval` read strings)
- Test: `tests/test_agentruntime.py` (add), existing suite stays green

**Interfaces:**
- Produces: `PlannedQuery(query: str, objective: str = "")`;
  `ResearchPlan(investigation_type: str = "general", objective: str = "", companies: list[str], doc_types: list[str], queries: list[PlannedQuery], rationale: str)`.
  A `field_validator("queries", mode="before")` upgrades `list[str]` (V1 stored plans and the V1 fake adapter) to `PlannedQuery` objects.
- Later tasks rely on: `plan.queries[i].query`, `plan.queries[i].objective`, `plan.investigation_type`.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_agentruntime.py`)

```python
def test_research_plan_upgrades_v1_string_queries():
    from argus.agentruntime.schemas import PlannedQuery, ResearchPlan

    plan = ResearchPlan.model_validate(
        {"companies": ["NVIDIA CORP"], "doc_types": ["news"],
         "queries": ["data center revenue", "automotive growth"], "rationale": "r"}
    )
    assert plan.investigation_type == "general"
    assert plan.queries == [
        PlannedQuery(query="data center revenue", objective=""),
        PlannedQuery(query="automotive growth", objective=""),
    ]


def test_research_plan_round_trips_typed_queries():
    from argus.agentruntime.schemas import ResearchPlan

    plan = ResearchPlan.model_validate(
        {"investigation_type": "earnings_analysis", "objective": "assess Q3",
         "companies": [], "doc_types": [],
         "queries": [{"query": "q3 margins", "objective": "margin trend"}],
         "rationale": "r"}
    )
    dumped = plan.model_dump(mode="json")
    assert ResearchPlan.model_validate(dumped) == plan
    assert dumped["queries"][0]["objective"] == "margin trend"


def test_research_plan_rejects_empty_query_text():
    import pytest
    from argus.agentruntime.schemas import ResearchPlan

    with pytest.raises(ValueError):
        ResearchPlan.model_validate(
            {"companies": [], "doc_types": [], "queries": [""], "rationale": "r"}
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_agentruntime.py -q`
Expected: FAIL — `ImportError: cannot import name 'PlannedQuery'`

- [ ] **Step 3: Implement the schema** — in `src/argus/agentruntime/schemas.py`, replace the `ResearchPlan` class:

```python
class PlannedQuery(BaseModel):
    """One retrieval query with the reason it exists (PRD-V2 2.1: queries are
    explainable). Priority/timeframe arrive with Retrieval Intelligence (Phase 3)."""

    query: str = Field(min_length=1, description="short keyword retrieval query")
    objective: str = Field(default="", description="what evidence this query targets")


class ResearchPlan(BaseModel):
    """Planner output: plan precedes retrieval, never search-first."""

    investigation_type: str = Field(
        default="general",
        description="one of: company_research, industry_analysis, executive_profiling, "
        "risk_assessment, event_investigation, earnings_analysis, competitive_analysis, "
        "general",
    )
    objective: str = Field(default="", description="one sentence: the investigation goal")
    companies: list[str] = Field(description="company names central to the question")
    doc_types: list[str] = Field(description="document types to search: news, filing")
    queries: list[PlannedQuery] = Field(description="3-6 retrieval queries covering the question")
    rationale: str = Field(description="one paragraph: why these targets and queries")

    @field_validator("queries", mode="before")
    @classmethod
    def _upgrade_v1_queries(cls, v):
        # V1 stored plans (and the V1 fake adapter) carry plain strings
        if isinstance(v, list):
            return [{"query": q} if isinstance(q, str) else q for q in v]
        return v
```

Add `field_validator` to the pydantic import line.

- [ ] **Step 4: Update the three consumers.**

`src/argus/agentruntime/planner.py` — replace INSTRUCTION:

```python
INSTRUCTION = """You are a research planner for a company-research platform.
Given a research question, produce a retrieval plan:
- investigation_type: one of company_research, industry_analysis, executive_profiling,
  risk_assessment, event_investigation, earnings_analysis, competitive_analysis, general
- objective: one sentence stating what the investigation must determine
- companies: company names central to the question, as canonically written
  (e.g. "NVIDIA CORP", "Apple Inc.")
- doc_types: the subset of ["news", "filing"] worth searching
- queries: 3-6 short keyword retrieval queries; each carries an objective explaining
  what evidence it targets
- rationale: one paragraph on why these targets and queries
Plan only. Do not answer the question."""
```

`src/argus/agentruntime/evidence.py` — in `collect()`, change the loop head:

```python
    for planned in plan.queries:
        query = planned.query
        hits = retrieve(session, query, company_ids or [None], doc_types, k, seen)
```

`src/argus/investigations/engine.py` — in `_collect()`, the event payload becomes:

```python
        "queries": [q.query for q in plan.queries],
```

(`replay_retrieval` reads `p["queries"]` as strings from the event payload — unchanged.)

- [ ] **Step 5: Run the full suite**

Run: `make lint && make test`
Expected: all pass (the fake adapter's `queries=[str]` is upgraded by the validator).

- [ ] **Step 6: Commit**

```bash
git add src/argus/agentruntime/ src/argus/investigations/engine.py tests/test_agentruntime.py
git commit -m "feat: typed research plan (PlannedQuery, investigation_type) with V1 back-compat"
```

---

### Task 2: `investigation_tasks` table, model, migration 0006

**Files:**
- Modify: `src/argus/investigations/models.py`
- Create: `migrations/versions/0006_investigation_tasks.py`
- Test: `tests/test_orchestrator.py` (new file)

**Interfaces:**
- Produces: model `InvestigationTask` with columns
  `id: uuid pk`, `investigation_id: uuid FK`, `task_type: str`, `objective: str`,
  `specialist: str | None`, `depends_on: JSONB list[str]` (task UUIDs as strings),
  `status: str` (`pending|running|complete|failed|obsolete`, server_default `pending`),
  `inputs: JSONB dict`, `outputs: JSONB dict`, `error: str | None`, `created_at`.
  Readiness is derived (all deps complete) — deliberately NOT a stored status.

- [ ] **Step 1: Write the failing test** (create `tests/test_orchestrator.py`)

```python
"""Orchestrator: DAG compilation, task execution, failure semantics (PRD-V2 1.2/4.1)."""

import uuid

import sqlalchemy as sa

from argus.core.db import session_scope
from tests.conftest import requires_db


@requires_db
def test_investigation_task_defaults_and_fk(db_session):
    from argus.investigations import engine
    from argus.investigations.models import InvestigationTask

    inv = engine.create(db_session, "test question")
    db_session.flush()
    task = InvestigationTask(
        investigation_id=inv.id, task_type="collect_evidence", objective="find evidence"
    )
    db_session.add(task)
    db_session.flush()
    assert task.status == "pending"
    assert task.depends_on == []
    assert task.inputs == {} and task.outputs == {}

    orphan = InvestigationTask(
        investigation_id=uuid.uuid4(), task_type="collect_evidence", objective="x"
    )
    db_session.add(orphan)
    import pytest
    with pytest.raises(sa.exc.IntegrityError):
        db_session.flush()
    db_session.rollback()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: FAIL — `ImportError: cannot import name 'InvestigationTask'`

- [ ] **Step 3: Add the model** to `src/argus/investigations/models.py`:

```python
class InvestigationTask(Base):
    """One DAG node (PRD-V2 1.2). depends_on holds task UUIDs as strings; readiness
    is derived (all deps complete), never stored — it cannot drift. Execution rides
    the jobs outbox: job.document_id carries the investigation id, payload the task id."""

    __tablename__ = "investigation_tasks"

    id: Mapped[uuid.UUID] = mapped_column(**_uuid_pk)
    investigation_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("investigations.id"), index=True
    )
    task_type: Mapped[str]  # collect_evidence | synthesize (Phase 1)
    objective: Mapped[str]  # why this task exists (PRD-V2: interpretable planning)
    specialist: Mapped[str | None]  # assigned in Phase 5 (specialist registry)
    depends_on: Mapped[list] = mapped_column(JSONB, server_default=text("'[]'::jsonb"))
    status: Mapped[str] = mapped_column(server_default="pending")
    inputs: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    outputs: Mapped[dict] = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None]
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=_now)
```

- [ ] **Step 4: Write migration** `migrations/versions/0006_investigation_tasks.py` (mirror the style of `0004_investigations.py` — check its `revision`/`down_revision` chain; `down_revision` here is `"0005"`):

```python
"""investigation tasks (V2 Phase 1: task DAG)

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "investigation_tasks",
        sa.Column("id", UUID(as_uuid=True), primary_key=True,
                  server_default=sa.text("gen_random_uuid()")),
        sa.Column("investigation_id", UUID(as_uuid=True),
                  sa.ForeignKey("investigations.id"), nullable=False),
        sa.Column("task_type", sa.String(), nullable=False),
        sa.Column("objective", sa.String(), nullable=False),
        sa.Column("specialist", sa.String(), nullable=True),
        sa.Column("depends_on", JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("inputs", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("outputs", JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("error", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False,
                  server_default=sa.text("now()")),
    )
    op.create_index("ix_investigation_tasks_investigation_id", "investigation_tasks",
                    ["investigation_id"])
    op.create_index("ix_investigation_tasks_inv_status", "investigation_tasks",
                    ["investigation_id", "status"])


def downgrade() -> None:
    op.drop_table("investigation_tasks")
```

Adjust `revision`/`down_revision` literals to match the real identifiers used in `0005_eval_runs.py` (read that file first — the project may use full slugs).

- [ ] **Step 5: Run the test**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: PASS (conftest migrates to head, picking up 0006).

- [ ] **Step 6: Verify migration round-trips** — the existing migration round-trip test covers upgrade/downgrade; run it:

Run: `uv run pytest tests/test_migrations.py -q` (if this file doesn't exist, run `make test`)
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add src/argus/investigations/models.py migrations/versions/0006_investigation_tasks.py tests/test_orchestrator.py
git commit -m "feat: investigation_tasks table — DAG nodes with derived readiness"
```

---

### Task 3: Worker handler registry (layer-clean extension point)

**Files:**
- Modify: `src/argus/dataplatform/worker.py` (`_execute`, new `EXTRA_HANDLERS`)
- Modify: `src/argus/dataplatform/worker.py:claim_next` (optional `document_id` filter)
- Test: `tests/test_worker_registry.py` (new)

**Interfaces:**
- Produces: `worker.EXTRA_HANDLERS: dict[str, Callable[[Session, Job], None]]` —
  the composition root (cli) registers handlers for non-pipeline job types.
  `worker.claim_next(session, document_id: uuid.UUID | None = None)` — when given,
  claims only jobs whose `document_id` matches (used by `engine.execute` to drain
  one investigation synchronously).

- [ ] **Step 1: Write the failing tests** (create `tests/test_worker_registry.py`)

```python
"""Worker extension point: non-pipeline job types run via EXTRA_HANDLERS."""

import uuid

import pytest
import sqlalchemy as sa

from argus.core import events
from argus.core.db import session_scope
from argus.core.models import Job
from argus.dataplatform import worker
from tests.conftest import requires_db


@requires_db
def test_extra_handler_executes_and_completes(migrated_db, monkeypatch):
    seen = []
    monkeypatch.setitem(worker.EXTRA_HANDLERS, "test.noop",
                        lambda session, job: seen.append(job.payload["x"]))
    with session_scope() as session:
        events.enqueue(session, "test.noop", payload={"x": 42})
    assert worker.run_once() is True
    assert seen == [42]
    with session_scope() as session:
        job = session.scalar(sa.select(Job).where(Job.job_type == "test.noop"))
        assert job.status == "completed"


@requires_db
def test_unknown_job_type_still_dead_letters(migrated_db):
    with session_scope() as session:
        job = events.enqueue(session, "no.such.type")
        job.max_attempts = 1
    assert worker.run_once() is True
    with session_scope() as session:
        job = session.scalar(sa.select(Job).where(Job.job_type == "no.such.type"))
        assert job.status == "dead"
        assert "unknown job type" in job.last_error


@requires_db
def test_claim_next_document_id_filter(migrated_db):
    target = uuid.uuid4()
    with session_scope() as session:
        events.enqueue(session, "test.noop", document_id=uuid.uuid4())
        events.enqueue(session, "test.noop", document_id=target)
    with session_scope() as session:
        job = worker.claim_next(session, document_id=target)
        assert job is not None and job.document_id == target
        assert worker.claim_next(session, document_id=target) is None  # only one
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_worker_registry.py -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'EXTRA_HANDLERS'`

- [ ] **Step 3: Implement.** In `src/argus/dataplatform/worker.py`:

Add near the top (after `log = ...`):

```python
# Extension point: the composition root (argus.cli) registers handlers for job types
# owned by layers ABOVE dataplatform (e.g. "investigation.task" → investigations).
# dataplatform never imports upward (layer contract); it only calls what was injected.
EXTRA_HANDLERS: dict[str, Callable[[Session, Job], None]] = {}
```

Add `from collections.abc import Callable` to imports.

Replace `_execute`:

```python
def _execute(session: Session, job: Job) -> None:
    if job.job_type in pipeline.STAGES:
        version = job.payload.get("pipeline_version", get_settings().pipeline_version)
        pipeline.run_stage(session, job.job_type, job.document_id, version)
    elif job.job_type in EXTRA_HANDLERS:
        EXTRA_HANDLERS[job.job_type](session, job)
    else:
        raise ValueError(f"unknown job type {job.job_type}")
```

Extend `claim_next`:

```python
def claim_next(session: Session, document_id: uuid.UUID | None = None) -> Job | None:
    # all queue time predicates use the DB clock (see events.enqueue) — never the client's
    q = (
        select(Job)
        .where(Job.status == "pending", Job.run_after <= func.now())
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if document_id is not None:
        q = q.where(Job.document_id == document_id)
    job = session.scalars(q).first()
    if job:
        job.status = "running"
        job.claimed_at = func.now()
        job.attempts += 1
    return job
```

Add `import uuid` to worker imports.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_worker_registry.py tests/test_stress.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/argus/dataplatform/worker.py tests/test_worker_registry.py
git commit -m "feat: worker handler registry + per-aggregate claim filter"
```

---

### Task 4: Orchestrator — DAG compilation with graphlib validation

**Files:**
- Create: `src/argus/investigations/orchestrator.py`
- Test: `tests/test_orchestrator.py` (extend)

**Interfaces:**
- Consumes: `ResearchPlan` (Task 1), `InvestigationTask` (Task 2), `events.enqueue` (core).
- Produces:
  `JOB_TYPE = "investigation.task"`;
  `compile_dag(session, inv, plan: ResearchPlan, company_ids: list[uuid.UUID]) -> list[InvestigationTask]`
  — persists one `collect_evidence` task per planned query (inputs: `{"query", "objective", "company_ids": [str], "doc_types", "k"}`) plus one `synthesize` task depending on all collect tasks; validates acyclicity with `graphlib.TopologicalSorter`; enqueues one outbox job per dependency-free task (`document_id=inv.id`, `payload={"task_id": str(task.id)}`); emits an `investigation.compiled` InvestigationEvent listing task ids/types; raises `ValueError` on an empty query plan or a cyclic graph.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_orchestrator.py`)

```python
def _plan(queries=("q1", "q2")):
    from argus.agentruntime.schemas import ResearchPlan

    return ResearchPlan(
        companies=["NVIDIA CORP"], doc_types=["news"],
        queries=list(queries), rationale="canned",
    )


@requires_db
def test_compile_dag_builds_fanout_fanin(db_session):
    from argus.core.models import Job
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import InvestigationTask

    inv = engine.create(db_session, "How is the DC business?")
    db_session.flush()
    tasks = orchestrator.compile_dag(db_session, inv, _plan(), company_ids=[])
    db_session.flush()

    collects = [t for t in tasks if t.task_type == "collect_evidence"]
    synths = [t for t in tasks if t.task_type == "synthesize"]
    assert len(collects) == 2 and len(synths) == 1
    assert all(t.depends_on == [] for t in collects)
    assert sorted(synths[0].depends_on) == sorted(str(t.id) for t in collects)
    assert collects[0].inputs["query"] == "q1"

    jobs = db_session.scalars(
        sa.select(Job).where(Job.job_type == orchestrator.JOB_TYPE)
    ).all()
    # only dependency-free tasks are enqueued; synthesize waits
    assert {j.payload["task_id"] for j in jobs} == {str(t.id) for t in collects}
    assert all(j.document_id == inv.id for j in jobs)


@requires_db
def test_compile_dag_rejects_empty_plan(db_session):
    import pytest

    from argus.investigations import engine, orchestrator

    inv = engine.create(db_session, "q")
    db_session.flush()
    with pytest.raises(ValueError, match="no queries"):
        orchestrator.compile_dag(db_session, inv, _plan(queries=()), company_ids=[])


def test_validate_dag_rejects_cycles():
    import pytest

    from argus.investigations.orchestrator import _validate_dag

    a, b = str(uuid.uuid4()), str(uuid.uuid4())
    with pytest.raises(ValueError, match="cycle"):
        _validate_dag({a: [b], b: [a]})
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: FAIL — `ModuleNotFoundError: argus.investigations.orchestrator`

- [ ] **Step 3: Create** `src/argus/investigations/orchestrator.py`:

```python
"""Deterministic research orchestrator (PRD-V2 4.1, ADR-0010): compiles a plan into
an investigation task DAG and executes it through the jobs outbox. It assigns and
routes work; it never performs domain reasoning — every LLM call lives in the task
handlers' agentruntime calls, behind the citation gate."""

import graphlib
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from argus.agentruntime.schemas import ResearchPlan
from argus.core import events
from argus.core.config import get_settings
from argus.investigations.models import Investigation, InvestigationEvent, InvestigationTask

JOB_TYPE = "investigation.task"


def _emit(session: Session, investigation_id: uuid.UUID, event_type: str, payload: dict) -> None:
    session.add(
        InvestigationEvent(
            investigation_id=investigation_id, event_type=event_type, payload=payload
        )
    )


def _validate_dag(deps: dict[str, list[str]]) -> None:
    """deps: task_id -> prerequisite task_ids. Raises ValueError on a cycle."""
    try:
        graphlib.TopologicalSorter(deps).prepare()
    except graphlib.CycleError as exc:
        raise ValueError(f"investigation DAG contains a cycle: {exc.args[1]}") from exc


def _enqueue_task(session: Session, task: InvestigationTask) -> None:
    events.enqueue(
        session, JOB_TYPE,
        document_id=task.investigation_id,  # aggregate id: lets execute() drain one investigation
        payload={"task_id": str(task.id)},
    )


def compile_dag(
    session: Session, inv: Investigation, plan: ResearchPlan, company_ids: list[uuid.UUID]
) -> list[InvestigationTask]:
    """Plan → persisted task DAG (PRD-V2 1.2). The LLM plans; this code decides the
    graph shape deterministically: one collect task per query, one synthesis fan-in."""
    if not plan.queries:
        raise ValueError("plan has no queries; nothing to investigate")
    k = get_settings().agent_retrieval_k

    collects = [
        InvestigationTask(
            id=uuid.uuid4(),
            investigation_id=inv.id,
            task_type="collect_evidence",
            objective=q.objective or f"collect evidence for: {q.query}",
            inputs={
                "query": q.query,
                "objective": q.objective,
                "company_ids": [str(c) for c in company_ids],
                "doc_types": plan.doc_types,
                "k": k,
            },
        )
        for q in plan.queries
    ]
    synthesize = InvestigationTask(
        id=uuid.uuid4(),
        investigation_id=inv.id,
        task_type="synthesize",
        objective="synthesize a cited report from all collected evidence",
        depends_on=[str(t.id) for t in collects],
    )
    tasks = [*collects, synthesize]

    _validate_dag({str(t.id): list(t.depends_on) for t in tasks})
    session.add_all(tasks)
    session.flush()
    for task in tasks:
        if not task.depends_on:
            _enqueue_task(session, task)
    _emit(session, inv.id, "investigation.compiled", {
        "tasks": [
            {"id": str(t.id), "type": t.task_type, "objective": t.objective,
             "depends_on": t.depends_on}
            for t in tasks
        ],
        "investigation_type": plan.investigation_type,
    })
    return tasks
```

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/argus/investigations/orchestrator.py tests/test_orchestrator.py
git commit -m "feat: orchestrator compiles plans into validated task DAGs"
```

---

### Task 5: Orchestrator — task execution, dependency advance, failure semantics

**Files:**
- Modify: `src/argus/investigations/orchestrator.py` (handlers, `run_task`, `_advance`)
- Modify: `src/argus/agentruntime/evidence.py` (extract `collect_query` from the `collect` loop body)
- Modify: `src/argus/investigations/engine.py` (move `_draft_and_score` → orchestrator's synthesize handler; engine keeps a thin re-export until Task 6 rewires callers)
- Test: `tests/test_orchestrator.py` (extend)

**Interfaces:**
- Consumes: `worker.EXTRA_HANDLERS` contract `(session, job) -> None` (Task 3).
- Produces:
  `evidence.collect_query(session, question, query, company_ids, doc_types, k, seen) -> tuple[list[CollectedEvidence], list[ExecutionRecord]]` — one query's retrieval + stance classification (the body of V1's `collect` loop; `collect` now calls it);
  `orchestrator.run_task(session, job) -> None` — the `investigation.task` handler: no-ops on complete/obsolete tasks (idempotent redelivery), raises `RuntimeError` if dependencies aren't complete (job backoff retries), dispatches by `task_type`, records `outputs`, marks `complete`, then enqueues newly-ready dependents; on exception with `job.attempts >= job.max_attempts` marks task and investigation `failed` (committed via a fresh session) before re-raising;
  `orchestrator.synthesize(session, inv) -> None` — V1 `_draft_and_score` behavior verbatim (citation gate, deterministic confidence, versioned report).

- [ ] **Step 1: Write the failing tests** (append to `tests/test_orchestrator.py`; reuse the fake adapter and seeded corpus patterns from `tests/test_investigations.py` — import `_fake_adapter` from there like `tests/test_stress.py` does, and `ingest_html`/`drain_queue` from conftest)

```python
def _register(monkeypatch):
    from argus.dataplatform import worker
    from argus.investigations import orchestrator

    monkeypatch.setitem(worker.EXTRA_HANDLERS, orchestrator.JOB_TYPE, orchestrator.run_task)


@requires_db
def test_dag_executes_to_completed_report(monkeypatch, fake_embeddings, seeded_companies):
    from argus.dataplatform import worker
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import Evidence, InvestigationTask, Report
    from tests.conftest import drain_queue, ingest_html
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    _register(monkeypatch)
    ingest_html(
        "<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        "grew strongly this quarter.</p></body></html>", doc_type="news",
    )
    drain_queue()

    with session_scope() as session:
        inv = engine.create(session, "How is the automotive business?")
        inv_id = inv.id
        plan = _plan(queries=("automotive self-driving platform revenue",))
        orchestrator.compile_dag(session, inv, plan,
                                 company_ids=[seeded_companies["NVIDIA CORP"]])

    drain_queue()  # collect fan-out then synthesize fan-in, via the outbox

    with session_scope() as session:
        tasks = session.scalars(
            sa.select(InvestigationTask).where(InvestigationTask.investigation_id == inv_id)
        ).all()
        assert {t.status for t in tasks} == {"complete"}
        collect = next(t for t in tasks if t.task_type == "collect_evidence")
        assert collect.outputs["chunk_ids"]
        assert session.scalar(
            sa.select(sa.func.count()).select_from(Evidence)
            .where(Evidence.investigation_id == inv_id)
        ) > 0
        report = session.scalar(sa.select(Report).where(Report.investigation_id == inv_id))
        assert report is not None
        inv = session.get(type(inv), inv_id) if False else None  # placeholder removed below
```

Replace the last line with a confidence assertion:

```python
        from argus.investigations.models import Investigation
        inv = session.get(Investigation, inv_id)
        assert inv.confidence is not None and 0 < inv.confidence <= 1
```

```python
@requires_db
def test_synthesize_waits_for_dependencies(monkeypatch, fake_embeddings, db_session):
    """A synthesize job delivered before its deps are complete must raise (job retries)."""
    import pytest

    from argus.core.models import Job
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import InvestigationTask

    inv = engine.create(db_session, "q")
    db_session.flush()
    collect = InvestigationTask(investigation_id=inv.id, task_type="collect_evidence",
                                objective="x", inputs={"query": "q", "company_ids": [],
                                                       "doc_types": [], "k": 2})
    db_session.add(collect)
    db_session.flush()
    synth = InvestigationTask(investigation_id=inv.id, task_type="synthesize",
                              objective="x", depends_on=[str(collect.id)])
    db_session.add(synth)
    db_session.flush()
    job = Job(job_type=orchestrator.JOB_TYPE, document_id=inv.id,
              payload={"task_id": str(synth.id)})
    db_session.add(job)
    db_session.flush()
    with pytest.raises(RuntimeError, match="dependencies not complete"):
        orchestrator.run_task(db_session, job)


@requires_db
def test_completed_task_redelivery_is_noop(monkeypatch, db_session):
    from argus.core.models import Job
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import InvestigationTask

    inv = engine.create(db_session, "q")
    db_session.flush()
    task = InvestigationTask(investigation_id=inv.id, task_type="collect_evidence",
                             objective="x", status="complete")
    db_session.add(task)
    db_session.flush()
    job = Job(job_type=orchestrator.JOB_TYPE, document_id=inv.id,
              payload={"task_id": str(task.id)})
    db_session.add(job)
    db_session.flush()
    orchestrator.run_task(db_session, job)  # must not raise or re-run


@requires_db
def test_exhausted_task_fails_investigation(monkeypatch, fake_embeddings, migrated_db):
    from argus.core import events as core_events
    from argus.dataplatform import worker
    from argus.investigations import engine, orchestrator
    from argus.investigations.models import Investigation, InvestigationTask
    from tests.conftest import drain_queue

    def boom(session, inv, task):
        raise RuntimeError("handler exploded")

    monkeypatch.setitem(orchestrator.HANDLERS, "collect_evidence", boom)
    _register(monkeypatch)
    monkeypatch.setattr(core_events, "retry_at",
                        lambda attempts: core_events.func.now())

    with session_scope() as session:
        inv = engine.create(session, "q")
        inv_id = inv.id
        session.flush()
        task = InvestigationTask(investigation_id=inv_id, task_type="collect_evidence",
                                 objective="x", inputs={"query": "q", "company_ids": [],
                                                        "doc_types": [], "k": 2})
        session.add(task)
        session.flush()
        orchestrator._enqueue_task(session, task)

    drain_queue()

    with session_scope() as session:
        task = session.scalars(sa.select(InvestigationTask)
                               .where(InvestigationTask.investigation_id == inv_id)).one()
        assert task.status == "failed"
        assert "handler exploded" in task.error
        assert session.get(Investigation, inv_id).status == "failed"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: FAIL — `AttributeError: ... has no attribute 'run_task'` / `'HANDLERS'`

- [ ] **Step 3: Extract `collect_query`** in `src/argus/agentruntime/evidence.py` — pull the body of `collect()`'s per-query loop into:

```python
def collect_query(
    session: Session, question: str, query: str, company_ids: list[uuid.UUID | None],
    doc_types: list[str] | None, k: int, seen: set[uuid.UUID] | None = None,
) -> tuple[list[CollectedEvidence], list[ExecutionRecord]]:
    """One query's evidence: deterministic retrieval, then one stance batch call.
    The DAG's collect_evidence task unit (PRD-V2 4.2-lite)."""
    seen = set() if seen is None else seen
    hits = retrieve(session, query, company_ids or [None], doc_types, k, seen)
    if not hits:
        return [], []
    numbered = "\n\n".join(
        f"[{i}] {h.text[:EXCERPT_CHARS]}" for i, h in enumerate(hits, 1)
    )
    batch, record = adapter.run_structured(
        "classify_stance",
        INSTRUCTION,
        f"Question: {question}\n\nExcerpts:\n---\n{numbered}\n---",
        StanceBatch,
    )
    if len(batch.results) != len(hits):
        raise ValueError(
            f"stance batch returned {len(batch.results)} results for {len(hits)} excerpts"
        )
    evidence = [
        CollectedEvidence(
            chunk_id=hit.chunk_id, document_id=hit.document_id,
            excerpt=hit.text[:EXCERPT_CHARS], stance=result.stance,
            rationale=result.rationale, query=query, scores=hit.scores,
            strategy=hit.strategy,
        )
        for hit, result in zip(hits, batch.results, strict=True)
    ]
    return evidence, [record]
```

Rewrite `collect()` to loop over `plan.queries` calling `collect_query` with the shared `seen` set and extending results — behavior identical to V1.

- [ ] **Step 4: Implement handlers in `orchestrator.py`.** Add:

```python
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as pg_insert

from argus.agentruntime import drafter
from argus.agentruntime import evidence as collector
from argus.agentruntime.schemas import CollectedEvidence, Stance
from argus.core.db import session_scope
from argus.core.models import Job
from argus.investigations import confidence
from argus.investigations.models import Evidence, Report
from argus.knowledge.models import Document
```

```python
def collect_evidence(session: Session, inv: Investigation, task: InvestigationTask) -> None:
    p = task.inputs
    company_ids = [uuid.UUID(c) for c in p["company_ids"]] or [None]
    collected, records = collector.collect_query(
        session, inv.question, p["query"], company_ids, p["doc_types"] or None, p["k"]
    )
    # this task owns exactly its query's evidence rows: rebuild them idempotently
    session.execute(
        delete(Evidence).where(
            Evidence.investigation_id == inv.id, Evidence.query == p["query"]
        )
    )
    if collected:
        # parallel collect tasks may retrieve the same chunk; first writer wins
        # (unique (investigation_id, chunk_id)); the loser's stance for that chunk
        # is recorded in its ExecutionRecord either way
        session.execute(
            pg_insert(Evidence)
            .values([
                {
                    "investigation_id": inv.id, "chunk_id": e.chunk_id,
                    "document_id": e.document_id, "stance": e.stance.value,
                    "rationale": e.rationale, "query": e.query, "excerpt": e.excerpt,
                    "scores": e.scores, "strategy": e.strategy,
                }
                for e in collected
            ])
            .on_conflict_do_nothing(index_elements=["investigation_id", "chunk_id"])
        )
    task.outputs = {
        "chunk_ids": [str(e.chunk_id) for e in collected],
        "evidence_count": len(collected),
    }
    _emit(session, inv.id, "evidence.collected", {
        "task_id": str(task.id), "query": p["query"], "company_ids": p["company_ids"],
        "doc_types": p["doc_types"], "k": p["k"],
        "chunk_ids": task.outputs["chunk_ids"],
        "records": [r.model_dump(mode="json") for r in records],
    })


def synthesize(session: Session, inv: Investigation, task: InvestigationTask) -> None:
    """V1 _draft_and_score, unchanged semantics: citation gate + deterministic
    confidence + versioned report (ADR-0005)."""
    ...  # move the body of engine._draft_and_score here verbatim, replacing
    ...  # references to `inv` accordingly; record outputs afterwards:
    task.outputs = {"report_version": inv.version, "confidence": inv.confidence}


HANDLERS = {"collect_evidence": collect_evidence, "synthesize": synthesize}
```

(Move `MARKER_RE` and the `_draft_and_score` body from `engine.py` into `synthesize`; in `engine.py` keep `from argus.investigations.orchestrator import synthesize as _draft_and_score` temporarily so `refresh()` still works until Task 6 — NO: that creates a circular import since orchestrator imports nothing from engine. Instead: move the function, and in `engine.py` delete `_draft_and_score` and change its two call sites in this same task to call the orchestrator — but `run`/`refresh` are rewired in Task 6. To keep every commit green, in THIS task update `engine._plan_and_collect`/`run`/`refresh` minimally: replace `_draft_and_score(session, inv)` calls with `orchestrator.synthesize(session, inv, _pseudo_task(inv))` where `_pseudo_task` is a throwaway unsaved `InvestigationTask(investigation_id=inv.id, task_type="synthesize", objective="v1-compat")`. `engine` importing `orchestrator` is the final direction (engine is the facade), so this is safe and temporary scaffolding falls away in Task 6.)

```python
def run_task(session: Session, job: Job) -> None:
    task = session.get(InvestigationTask, uuid.UUID(job.payload["task_id"]))
    if task is None:
        raise ValueError(f"no investigation task {job.payload['task_id']}")
    if task.status in ("complete", "obsolete"):
        return  # idempotent redelivery
    deps = session.scalars(
        select(InvestigationTask).where(
            InvestigationTask.id.in_([uuid.UUID(d) for d in task.depends_on])
        )
    ).all() if task.depends_on else []
    if any(d.status != "complete" for d in deps):
        raise RuntimeError(f"task {task.id} dependencies not complete")

    inv = session.get(Investigation, task.investigation_id)
    task.status = "running"
    try:
        HANDLERS[task.task_type](session, inv, task)
    except Exception as exc:
        _fail_if_exhausted(job, task.id, inv.id, exc)
        raise
    task.status = "complete"
    task.error = None
    _advance(session, task)


def _fail_if_exhausted(job: Job, task_id: uuid.UUID, inv_id: uuid.UUID, exc: Exception) -> None:
    """On the final attempt, persist task+investigation failure in a fresh transaction
    (the caller's session is about to roll back with the re-raised exception)."""
    if job.attempts < job.max_attempts:
        return
    with session_scope() as s:
        task = s.get(InvestigationTask, task_id)
        task.status = "failed"
        task.error = f"{type(exc).__name__}: {exc}"
        s.get(Investigation, inv_id).status = "failed"
        _emit(s, inv_id, "task.failed", {"task_id": str(task_id), "error": task.error})


def _advance(session: Session, completed: InvestigationTask) -> None:
    """Enqueue every dependent whose prerequisites are now all complete. Runs inside
    the completing task's transaction: the status flip and the follow-on job commit
    atomically (outbox pattern, ADR-0003)."""
    session.flush()
    siblings = session.scalars(
        select(InvestigationTask).where(
            InvestigationTask.investigation_id == completed.investigation_id,
            InvestigationTask.status == "pending",
        )
    ).all()
    statuses = {
        str(t.id): t.status
        for t in session.scalars(
            select(InvestigationTask).where(
                InvestigationTask.investigation_id == completed.investigation_id
            )
        )
    }
    for t in siblings:
        if str(completed.id) in t.depends_on and all(
            statuses.get(d) == "complete" for d in t.depends_on
        ):
            _enqueue_task(session, t)
```

Note for the implementer: `_fail_if_exhausted` opens a second session while the caller's is mid-transaction — the UPDATE it issues touches the same task row the failing session has loaded but NOT modified in the failure path (status was set to "running" pre-exception and rolls back), so there is no lock conflict; the job row lock is held by the worker's claim transaction which has already committed by execution time. Test this exact scenario (`test_exhausted_task_fails_investigation` covers it).

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/test_orchestrator.py tests/test_investigations.py -q`
Expected: PASS

- [ ] **Step 6: Full suite + commit**

```bash
make lint && make test
git add src/argus/investigations/ src/argus/agentruntime/evidence.py tests/test_orchestrator.py
git commit -m "feat: orchestrator executes task DAGs — handlers, dependency advance, failure semantics"
```

---

### Task 6: Engine runs investigations through the DAG; replay per task

**Files:**
- Modify: `src/argus/investigations/engine.py` (`run`, `refresh`, `replay_retrieval`; delete `_plan_and_collect`, `_collect`, `_draft_and_score` and the Task 5 compat shim)
- Modify: `src/argus/investigations/orchestrator.py` (add `drain(investigation_id)`)
- Test: `tests/test_investigations.py` (replay test update), `tests/test_orchestrator.py` (refresh + drain edge cases)

**Interfaces:**
- Consumes: `worker.claim_next(session, document_id=...)` (Task 3), `worker.run_once` semantics.
- Produces:
  `orchestrator.drain(investigation_id) -> None` — claims and runs this investigation's `investigation.task` jobs until none remain claimable AND no task is `pending`/`running`, waiting briefly between claim misses while tasks are in flight (another worker may hold them); each job runs in its own transaction exactly like `worker.run_once` (claim → execute → complete/fail with backoff + dead-letter);
  `engine.run(session, ...)` — plans, resolves companies, compiles the DAG, commits, then drains; sets `complete` + emits `investigation.completed` when all tasks completed (unchanged external contract);
  `engine.refresh(...)` — marks the previous version's non-terminal tasks `obsolete`, compiles a fresh DAG from the stored plan, drains;
  `engine.replay_retrieval(...)` — replays retrieval per collect task from `task.inputs`, comparing against `task.outputs["chunk_ids"]`.

- [ ] **Step 1: Write/adjust the failing tests.**

In `tests/test_orchestrator.py` append:

```python
@requires_db
def test_engine_run_via_dag_and_refresh_marks_obsolete(monkeypatch, fake_embeddings,
                                                       seeded_companies):
    from argus.investigations import engine
    from argus.investigations.models import Investigation, InvestigationTask, Report
    from tests.conftest import drain_queue, ingest_html
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    _register(monkeypatch)
    ingest_html(
        "<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        "grew strongly.</p></body></html>", doc_type="news",
    )
    drain_queue()

    with session_scope() as session:
        inv = engine.create(session, "How is the automotive business?")
        inv_id = inv.id
    with session_scope() as session:
        engine.run(session, inv_id)
    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "complete" and inv.confidence is not None
        v1_tasks = session.scalars(sa.select(InvestigationTask)
                                   .where(InvestigationTask.investigation_id == inv_id)).all()
        assert v1_tasks and all(t.status == "complete" for t in v1_tasks)

    with session_scope() as session:
        engine.refresh(session, inv_id)
    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "complete" and inv.version == 2
        reports = session.scalars(sa.select(Report)
                                  .where(Report.investigation_id == inv_id)).all()
        assert {r.version for r in reports} == {1, 2}
        tasks = session.scalars(sa.select(InvestigationTask)
                                .where(InvestigationTask.investigation_id == inv_id)).all()
        # v1 tasks stay complete (history preserved); v2 tasks complete too
        assert len(tasks) == 2 * len(v1_tasks)


@requires_db
def test_replay_matches_per_task(monkeypatch, fake_embeddings, seeded_companies):
    from argus.investigations import engine
    from tests.conftest import drain_queue, ingest_html
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    _register(monkeypatch)
    ingest_html(
        "<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        "grew strongly.</p></body></html>", doc_type="news",
    )
    drain_queue()
    with session_scope() as session:
        inv_id = engine.create(session, "How is the automotive business?").id
    with session_scope() as session:
        engine.run(session, inv_id)
    with session_scope() as session:
        result = engine.replay_retrieval(session, inv_id)
        assert result["match"] is True
        assert result["tasks"]  # per-task breakdown
```

In `tests/test_investigations.py`, update the existing replay test to assert the new shape (`result["match"]`, `result["tasks"]` list with `task_id`/`recorded`/`replayed` keys) — find it with `grep -n replay tests/test_investigations.py` and keep its corpus setup unchanged.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_orchestrator.py -q`
Expected: FAIL — engine.run still executes the V1 linear path (no tasks created).

- [ ] **Step 3: Implement `orchestrator.drain`:**

```python
import time


def drain(investigation_id: uuid.UUID) -> None:
    """Run this investigation's jobs to completion in-process. Mirrors
    worker.run_once's transaction/backoff/dead-letter semantics, filtered to one
    aggregate; safe alongside real workers (SKIP LOCKED splits the work) —
    when another worker holds a task, poll until every task is terminal."""
    from argus.dataplatform import worker  # investigations → dataplatform is layer-legal

    while True:
        ran = worker.run_once(document_id=investigation_id)
        if ran:
            continue
        with session_scope() as session:
            live = session.scalar(
                select(InvestigationTask.id).where(
                    InvestigationTask.investigation_id == investigation_id,
                    InvestigationTask.status.in_(["pending", "running"]),
                ).limit(1)
            )
        if live is None:
            return
        time.sleep(0.1)  # a job exists but isn't claimable yet (backoff or other worker)
```

Extend `worker.run_once(document_id: uuid.UUID | None = None)` to pass the filter to `claim_next` (2-line change; the registry handler dispatch from Task 3 handles the rest). While in there, confirm `run_once`'s `PipelineRun` recording tolerates non-pipeline job types (it already writes `stage=job_type` generically).

- [ ] **Step 4: Rewire `engine.run`/`refresh`/`replay_retrieval`:**

```python
def run(session: Session, investigation_id: uuid.UUID) -> Investigation:
    """Plan → compile DAG → execute via the outbox → complete. Raises on failure so
    the caller's transaction rolls back partial writes (execute() persists failures)."""
    inv = session.get(Investigation, investigation_id)
    inv.status = "running"
    session.flush()
    plan, record = planner.plan(inv.question)
    company_ids = collector.resolve_companies(session, plan.companies)
    inv.plan = plan.model_dump(mode="json")
    inv.company_ids = [str(c) for c in company_ids]
    _emit(session, inv.id, "agent.plan",
          {"plan": inv.plan, "company_ids": inv.company_ids,
           "record": _record_payload(record)})
    # evidence is derived: rebuild wholesale on every (re)run
    session.execute(delete(Evidence).where(Evidence.investigation_id == inv.id))
    orchestrator.compile_dag(session, inv, plan, company_ids)
    session.commit()  # tasks + jobs must be visible to the drain's own transactions

    orchestrator.drain(inv.id)
    return _finalize(session, investigation_id)


def _finalize(session: Session, investigation_id: uuid.UUID) -> Investigation:
    session.expire_all()  # drain committed in other sessions
    inv = session.get(Investigation, investigation_id)
    if inv.status == "failed":
        raise RuntimeError("investigation failed during task execution")
    incomplete = session.scalar(
        select(InvestigationTask.id).where(
            InvestigationTask.investigation_id == investigation_id,
            InvestigationTask.status.in_(["pending", "running", "failed"]),
        ).limit(1)
    )
    if incomplete is not None:
        raise RuntimeError("investigation ended with unfinished tasks")
    inv.status = "complete"
    inv.last_refreshed_at = datetime.now(UTC)
    _emit(session, inv.id, "investigation.completed",
          {"confidence": inv.confidence, "version": inv.version})
    return inv
```

`refresh()` mirrors it: guard `inv.plan`, bump version, mark old non-terminal tasks obsolete
(`update(InvestigationTask).where(investigation_id==..., status.in_(["pending","running"])).values(status="obsolete")`),
delete Evidence wholesale, `compile_dag` from `ResearchPlan.model_validate(inv.plan)` with stored `company_ids`, commit, drain, `_finalize`, emit `investigation.refreshed`.

**Transaction-shape caution for the implementer:** `run()` now calls `session.commit()` mid-function. `engine.execute()` wraps `run` in `session_scope()` which commits again at exit — harmless. But the failure path in `execute()` still works because `run` raises AFTER its own commit only when tasks failed, and the failure was already persisted by `_fail_if_exhausted`; `execute()`'s except-branch then sets `status="failed"` idempotently. The `db_session`-fixture tests call `engine.run(session, ...)` directly with their own open session — `run` committing that session is acceptable in tests that use `session_scope()` blocks (as the new tests do). Do NOT use the `db_session` fixture for run/refresh tests; use `session_scope()` like `tests/test_investigations.py` does at lines 150-154.

`replay_retrieval` becomes:

```python
def replay_retrieval(session: Session, investigation_id: uuid.UUID) -> dict:
    """Re-execute each collect task's retrieval from its recorded inputs; recorded
    and replayed chunk sets must match per task (corpus unchanged, Bible §13)."""
    tasks = session.scalars(
        select(InvestigationTask).where(
            InvestigationTask.investigation_id == investigation_id,
            InvestigationTask.task_type == "collect_evidence",
            InvestigationTask.status == "complete",
        ).order_by(InvestigationTask.created_at)
    ).all()
    if not tasks:
        raise LookupError("no completed collect tasks to replay")
    per_task = []
    for t in tasks:
        p = t.inputs
        company_ids = [uuid.UUID(c) for c in p["company_ids"]] or [None]
        hits = collector.retrieve(session, p["query"], company_ids,
                                  p["doc_types"] or None, p["k"], set())
        replayed = [str(h.chunk_id) for h in hits]
        per_task.append({
            "task_id": str(t.id), "query": p["query"],
            "recorded": t.outputs.get("chunk_ids", []), "replayed": replayed,
            "match": set(t.outputs.get("chunk_ids", [])) == set(replayed),
        })
    return {"tasks": per_task, "match": all(t["match"] for t in per_task)}
```

Delete `_plan_and_collect`, `_collect`, `_draft_and_score`, `MARKER_RE` from `engine.py` (now owned by orchestrator) and the Task 5 pseudo-task shim. Keep `create`, `execute`, `has_new_evidence` untouched.

- [ ] **Step 5: Run the affected suites, then everything**

Run: `uv run pytest tests/test_orchestrator.py tests/test_investigations.py tests/test_e2e.py -q`
Expected: PASS. Then `make lint && make test` — all green.

- [ ] **Step 6: Commit**

```bash
git add src/argus/investigations/ src/argus/dataplatform/worker.py tests/
git commit -m "feat: investigations execute through the task DAG; per-task replay"
```

---

### Task 7: Tasks API endpoint + replay response shape

**Files:**
- Modify: `src/argus/api/routes.py`
- Test: `tests/test_api_features.py`

**Interfaces:**
- Produces: `GET /api/investigations/{id}/tasks` →
  `{"tasks": [{"id", "task_type", "objective", "specialist", "depends_on", "status", "outputs", "error", "created_at"}]}` ordered by `created_at` (404 on unknown investigation).
  `POST /api/investigations/{id}/replay` already exists — it returns whatever
  `engine.replay_retrieval` returns, so it now serves the per-task shape; update its
  test assertions only.

- [ ] **Step 1: Write the failing tests** (append to `tests/test_api_features.py`, using its existing `client` fixture/pattern — check how other tests build the TestClient there and mirror it)

```python
@requires_db
def test_tasks_endpoint_lists_dag(monkeypatch, fake_embeddings, seeded_companies):
    from fastapi.testclient import TestClient

    from argus.dataplatform import worker
    from argus.investigations import engine, orchestrator
    from argus.main import app as fastapi_app
    from tests.test_investigations import _fake_adapter

    _fake_adapter(monkeypatch)
    monkeypatch.setitem(worker.EXTRA_HANDLERS, orchestrator.JOB_TYPE, orchestrator.run_task)
    ingest_html(
        "<html><body><p>ZZZT NVIDIA CORP automotive self-driving platform revenue "
        "grew.</p></body></html>", doc_type="news",
    )
    drain_queue()
    with session_scope() as session:
        inv_id = engine.create(session, "How is the automotive business?").id
    engine.execute(inv_id, "run")

    client = TestClient(fastapi_app)
    r = client.get(f"/api/investigations/{inv_id}/tasks")
    assert r.status_code == 200
    tasks = r.json()["tasks"]
    assert {t["task_type"] for t in tasks} == {"collect_evidence", "synthesize"}
    assert all(t["status"] == "complete" for t in tasks)
    synth = next(t for t in tasks if t["task_type"] == "synthesize")
    assert synth["depends_on"]


@requires_db
def test_tasks_endpoint_404s_on_unknown_investigation(fake_embeddings):
    import uuid as _uuid

    from fastapi.testclient import TestClient

    from argus.main import app as fastapi_app

    client = TestClient(fastapi_app)
    assert client.get(f"/api/investigations/{_uuid.uuid4()}/tasks").status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_api_features.py -q -k tasks_endpoint`
Expected: FAIL — 404 route not found → first test asserts on `r.status_code == 200`.

- [ ] **Step 3: Implement the endpoint** in `src/argus/api/routes.py` (next to the evidence endpoint; import `InvestigationTask` from `argus.investigations.models`):

```python
@router.get("/api/investigations/{investigation_id}/tasks")
def get_tasks(investigation_id: uuid.UUID, session: Session = Depends(get_db)) -> dict:
    _get_or_404(session, investigation_id)
    rows = session.scalars(
        select(InvestigationTask)
        .where(InvestigationTask.investigation_id == investigation_id)
        .order_by(InvestigationTask.created_at, InvestigationTask.id)
    ).all()
    return {
        "tasks": [
            {
                "id": t.id, "task_type": t.task_type, "objective": t.objective,
                "specialist": t.specialist, "depends_on": t.depends_on,
                "status": t.status, "outputs": t.outputs, "error": t.error,
                "created_at": t.created_at,
            }
            for t in rows
        ]
    }
```

Also update the existing replay-endpoint test (grep `replay` in `tests/test_api_features.py` / `tests/test_e2e.py`) to the new response shape if it asserts on `recorded`/`replayed` keys.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/test_api_features.py tests/test_e2e.py -q`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/argus/api/routes.py tests/test_api_features.py tests/test_e2e.py
git commit -m "api: investigation tasks endpoint — DAG visibility"
```

---

### Task 8: Composition-root wiring + docs

**Files:**
- Modify: `src/argus/cli.py` (worker command registers the handler)
- Modify: `src/argus/main.py` (register at app startup too — the API's `engine.execute` drain path runs in-process and needs the handler)
- Modify: `docs/ARCHITECTURE.md` (§3 lifecycle diagram note + §9 module map), `docs/DOMAIN_MODEL.md` (investigation_tasks)
- Test: `tests/test_orchestrator.py` (registration function)

**Interfaces:**
- Produces: `orchestrator.register() -> None` — idempotently installs
  `EXTRA_HANDLERS["investigation.task"] = run_task`. Called by `argus.cli.worker`
  and `argus.main` at import/startup. (investigations importing dataplatform is
  layer-legal; dataplatform still knows nothing about investigations.)

- [ ] **Step 1: Write the failing test** (append to `tests/test_orchestrator.py`)

```python
def test_register_installs_handler(monkeypatch):
    from argus.dataplatform import worker
    from argus.investigations import orchestrator

    monkeypatch.setattr(worker, "EXTRA_HANDLERS", {})
    orchestrator.register()
    orchestrator.register()  # idempotent
    assert worker.EXTRA_HANDLERS[orchestrator.JOB_TYPE] is orchestrator.run_task
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_orchestrator.py::test_register_installs_handler -q`
Expected: FAIL — no attribute `register`.

- [ ] **Step 3: Implement.** In `orchestrator.py`:

```python
def register() -> None:
    """Install the investigation.task handler into the worker registry. Called from
    composition roots (argus.main, argus.cli worker) — never from dataplatform."""
    from argus.dataplatform import worker

    worker.EXTRA_HANDLERS[JOB_TYPE] = run_task
```

In `src/argus/cli.py` `worker()` command, before `main_loop()`:

```python
    from argus.investigations.orchestrator import register

    register()
```

In `src/argus/main.py`, alongside app construction (find where routers are mounted):

```python
from argus.investigations.orchestrator import register as _register_investigation_handler

_register_investigation_handler()
```

- [ ] **Step 4: Docs.**
  - `docs/ARCHITECTURE.md` §3 "Investigation lifecycle": add one paragraph after the diagram — investigations now compile to a task DAG (`investigation_tasks`) executed through the jobs outbox per ADR-0010; the diagram's steps are the DAG's node types; parallelism = more workers.
  - `docs/ARCHITECTURE.md` §9 module map: add `orchestrator.py` under `investigations/`.
  - `docs/DOMAIN_MODEL.md`: add `investigation_tasks` with column summary and the derived-readiness invariant.

- [ ] **Step 5: Full verification**

Run: `make lint && make test`
Expected: all green. Also run the stress tests twice (they exercise the queue this phase leans on): `uv run pytest tests/test_stress.py -q`.

- [ ] **Step 6: Commit**

```bash
git add src/argus/cli.py src/argus/main.py src/argus/investigations/orchestrator.py docs/ tests/test_orchestrator.py
git commit -m "feat: wire investigation task handler at composition roots; Phase 1 docs"
```

---

## Self-review notes (already applied)

- Spec coverage: 1.1 planner (Task 1), 1.2 DAG (Tasks 2, 4), 4.1 orchestrator (Tasks 4–6), 4.4 coordination/advance (Task 5), 4.5 recovery via job retry/dead-letter + task failure semantics (Task 5); observability minimum via tasks endpoint (Task 7). State machine states beyond V1's vocabulary are deliberately Phase 2.
- The V1 `evidence.collected` event shape changes (per-task) — `replay_retrieval` no longer reads events, it reads tasks; the events remain for audit history.
- Type consistency: `run_task(session, job)` matches the `EXTRA_HANDLERS` contract `(Session, Job) -> None`; `collect_query` returns `(list[CollectedEvidence], list[ExecutionRecord])` everywhere it's referenced.
