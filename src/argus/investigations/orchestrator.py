"""Deterministic research orchestrator (PRD-V2 4.1, ADR-0010): compiles a plan into
an investigation task DAG and executes it through the jobs outbox. It assigns and
routes work; it never performs domain reasoning — every LLM call lives in the task
handlers' agentruntime calls, behind the citation gate."""

import graphlib
import re
import time
import uuid

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from argus.agentruntime import drafter
from argus.agentruntime import evidence as collector
from argus.agentruntime.schemas import ResearchPlan
from argus.core import events
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.models import Job
from argus.investigations import confidence
from argus.investigations.models import (
    Evidence,
    Investigation,
    InvestigationEvent,
    InvestigationTask,
    Report,
)
from argus.knowledge.models import Document
from argus.research import fusion, ranking
from argus.research.timeline import timeline as timeline_query

JOB_TYPE = "investigation.task"

# Sole citation-marker pattern (Task 6 retired the engine.py copy + v1-compat
# shim); ui/views.py, api/routes.py and evals/runner.py import this one.
MARKER_RE = re.compile(r"\[chunk:([0-9a-f-]{36})\]")


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
    # Paused: never enqueue new work. A task already running keeps running (its job
    # exists already, untouched); resume() re-derives readiness and enqueues then —
    # nothing needs tracking for "would have been enqueued" in the meantime.
    inv_status = session.scalar(
        select(Investigation.status).where(Investigation.id == task.investigation_id)
    )
    if inv_status == "paused":
        return
    job = events.enqueue(
        session, JOB_TYPE,
        document_id=task.investigation_id,  # aggregate id: lets execute() drain one investigation
        payload={"task_id": str(task.id)},
    )
    # ponytail: task handlers fail on deterministic application errors (citation
    # gate, empty evidence, stance-batch mismatches) — retrying with the same
    # recorded inputs can't succeed, and drain() polls in-process, so the default
    # 30s*2^n backoff would stall a synchronous run()/refresh() for minutes on any
    # failure. Fail fast; upgrade to distinguishing transient vs. permanent
    # exceptions if genuinely-transient task failures show up in practice.
    job.max_attempts = 1


def compile_dag(
    session: Session, inv: Investigation, plan: ResearchPlan, company_ids: list[uuid.UUID]
) -> list[InvestigationTask]:
    """Plan → persisted task DAG (PRD-V2 1.2). The LLM plans; this code decides the
    graph shape deterministically: one collect task per query, one synthesis fan-in."""
    if not plan.queries:
        raise ValueError("plan has no queries; nothing to investigate")
    k = get_settings().agent_retrieval_k

    # collect_evidence's DELETE-then-reinsert rebuild owns its query text (see
    # collect_evidence below); nothing upstream enforces distinct query strings, so
    # dedupe here, at the one place that turns queries into tasks, order-preserving.
    # Higher-priority queries (PRD-V2 2.1) get their tasks first.
    seen: set[str] = set()
    queries = []
    for q in sorted(plan.queries, key=lambda q: q.priority, reverse=True):
        if q.query not in seen:
            seen.add(q.query)
            queries.append(q)

    collects = [
        InvestigationTask(
            id=uuid.uuid4(),
            investigation_id=inv.id,
            task_type="collect_evidence",
            objective=q.objective or f"collect evidence for: {q.query}",
            depends_on=[],  # server_default only applies post-flush; DAG validation runs pre-flush
            inputs={
                "query": q.query,
                "objective": q.objective,
                "company_ids": [str(c) for c in company_ids],
                "doc_types": plan.doc_types,
                "k": k,
            },
        )
        for q in queries
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


def collect_evidence(session: Session, inv: Investigation, task: InvestigationTask) -> None:
    p = task.inputs
    company_ids = [uuid.UUID(c) for c in p["company_ids"]] or [None]
    collected, records, dropped = collector.collect_query(
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
        "duplicates_dropped": dropped,
    }
    _emit(session, inv.id, "evidence.collected", {
        "task_id": str(task.id), "query": p["query"], "company_ids": p["company_ids"],
        "doc_types": p["doc_types"], "k": p["k"],
        "chunk_ids": task.outputs["chunk_ids"], "duplicates_dropped": dropped,
        "records": [r.model_dump(mode="json") for r in records],
    })


def _investigation_timeline(session: Session, inv: Investigation) -> list[dict]:
    """Date-ordered doc entries across every company this investigation covers
    (PRD-V2 2.5 fusion input); documents shared by multiple companies dedupe."""
    seen: dict[uuid.UUID, dict] = {}
    for c in inv.company_ids:
        for e in timeline_query(session, uuid.UUID(c)):
            seen.setdefault(e.document_id, {
                "document_id": str(e.document_id), "published_at": e.published_at,
                "title": e.title, "doc_type": e.doc_type, "source": e.source,
            })
    return sorted(seen.values(), key=lambda d: d["published_at"], reverse=True)


def _score_source_rank(session: Session, rows: list[Evidence], docs: dict) -> None:
    """Deterministic source ranking (PRD-V2 2.3), computed once over the whole
    evidence set (not per collect task) so corroboration counts don't depend on
    job-scheduling order. corroboration = other documents sharing this row's
    stance, plus documents dedup merged into it (`scores["corroborated_by"]`,
    PRD-V2 2.4) — corroboration from a dropped duplicate is never silently lost."""
    now = session.scalar(select(func.now()))  # DB clock is the time authority
    stance_docs: dict[str, set[uuid.UUID]] = {}
    for r in rows:
        stance_docs.setdefault(r.stance, set()).add(r.document_id)
    publisher_by_doc = {d.id: (d.publisher or d.source) for d in docs.values()}
    for r in rows:
        corroborating_ids = (stance_docs.get(r.stance, set()) - {r.document_id}) | (
            {uuid.UUID(d) for d in r.scores.get("corroborated_by", [])} - {r.document_id}
        )
        score, explanation = ranking.score_source(
            docs[r.document_id], len(corroborating_ids), now,
            len({publisher_by_doc[d] for d in corroborating_ids if d in publisher_by_doc}),
        )
        r.scores = {**r.scores, "source_rank": score, "source_rank_explanation": explanation}


def synthesize(session: Session, inv: Investigation, task: InvestigationTask) -> None:
    """Source ranking (2.3) + context fusion (2.5) over all collected evidence, then
    the V1 citation gate + deterministic confidence + versioned report (ADR-0005),
    unchanged."""
    rows = session.scalars(
        select(Evidence).where(
            Evidence.investigation_id == inv.id,
            or_(Evidence.review.is_(None), Evidence.review != "rejected"),
        ).order_by(Evidence.query, Evidence.id)  # deterministic fusion ordering
    ).all()
    if not rows:
        raise ValueError("no evidence collected; cannot draft a report (ADR-0005)")

    corroborated_doc_ids = {
        uuid.UUID(d) for r in rows for d in r.scores.get("corroborated_by", [])
    }
    docs = {
        d.id: d
        for d in session.scalars(
            select(Document).where(
                Document.id.in_({r.document_id for r in rows} | corroborated_doc_ids)
            )
        )
    }
    _score_source_rank(session, rows, docs)

    collect_tasks = session.scalars(
        select(InvestigationTask).where(
            InvestigationTask.investigation_id == inv.id,
            InvestigationTask.task_type == "collect_evidence",
        )
    ).all()
    query_counts = {
        t.inputs.get("query", ""): t.outputs.get("evidence_count", 0) for t in collect_tasks
    }
    context = fusion.build(
        objective=inv.plan.get("objective") or inv.question,
        plan_summary=inv.plan.get("rationale", ""),
        evidence=[
            {
                "chunk_id": str(r.chunk_id), "excerpt": r.excerpt, "stance": r.stance,
                "query": r.query, "source_rank": r.scores.get("source_rank"),
                "document_id": str(r.document_id),
                "document_title": docs[r.document_id].title,
                "document_source": docs[r.document_id].source,
                "document_published_at": docs[r.document_id].published_at,
            }
            for r in rows
        ],
        timeline_entries=_investigation_timeline(session, inv),
        query_counts=query_counts,
        min_evidence_per_query=get_settings().min_evidence_per_query,
    )
    _emit(session, inv.id, "investigation.context_fused", context.model_dump(mode="json"))

    draft, record = drafter.draft(inv.question, context)
    # citation gate: every marker must reference collected evidence
    cited = {uuid.UUID(m) for m in MARKER_RE.findall(draft.narrative)}
    allowed = {r.chunk_id for r in rows}
    if invented := cited - allowed:
        raise ValueError(f"draft cites chunks outside the evidence set: {sorted(invented)}")
    if not cited:
        raise ValueError("draft narrative carries no citation markers")

    breakdown = confidence.compute(list(rows), docs)
    inv.confidence = breakdown["score"]
    inv.confidence_breakdown = breakdown

    # reports are versioned history: refresh appends v(n+1), never rewrites v(n)
    session.add(
        Report(
            investigation_id=inv.id, version=inv.version,
            executive_summary=draft.executive_summary, key_findings=draft.key_findings,
            risks=draft.risks, follow_up_questions=draft.follow_up_questions,
            narrative=draft.narrative, model=record.model,
        )
    )
    _emit(session, inv.id, "agent.draft", {"record": record.model_dump(mode="json")})
    task.outputs = {"report_version": inv.version, "confidence": inv.confidence}


HANDLERS = {"collect_evidence": collect_evidence, "synthesize": synthesize}


def register() -> None:
    """Install the investigation.task handler into the worker registry. Called from
    composition roots (argus.main, argus.cli worker) — never from dataplatform."""
    from argus.dataplatform import worker

    worker.EXTRA_HANDLERS[JOB_TYPE] = run_task


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
        # Capture ids BEFORE rollback: rollback expires all ORM instances, and
        # touching `task`/`inv` afterwards would silently re-open a transaction
        # on this session.
        exhausted = job.attempts >= job.max_attempts
        task_id, inv_id = task.id, inv.id
        _fail_if_exhausted(session, exhausted, task_id, inv_id, exc)
        raise
    task.status = "complete"
    task.error = None
    _advance(session, task)


def _fail_if_exhausted(
    session: Session, exhausted: bool, task_id: uuid.UUID, inv_id: uuid.UUID, exc: Exception
) -> None:
    """On the final attempt, persist task+investigation failure in a fresh transaction.

    `task.status = "running"` was autoflushed to Postgres earlier in this call
    (any query the handler ran against `session` triggers autoflush), so `session`'s
    transaction holds a row lock on this task until it ends. Opening a second
    session and updating the same row WITHOUT rolling back `session` first would
    self-deadlock: the second session's UPDATE blocks on a lock this call stack
    holds and won't release until this function returns. Rolling back first also
    clears any aborted-transaction state (25P02) if `exc` was itself a DB error,
    which no same-transaction/SAVEPOINT scheme can do. See Fable advisory,
    2026-07-08.
    """
    session.rollback()
    if not exhausted:
        return
    with session_scope() as s:
        task = s.get(InvestigationTask, task_id)
        task.status = "failed"
        task.error = f"{type(exc).__name__}: {exc}"
        inv = s.get(Investigation, inv_id)
        if inv.status != "cancelled":
            inv.status = "failed"
        _emit(s, inv_id, "task.failed", {"task_id": str(task_id), "error": task.error})


def _ready_pending_tasks(
    session: Session, investigation_id: uuid.UUID
) -> list[InvestigationTask]:
    """Pending tasks whose prerequisites are all complete (readiness is derived,
    never stored — migration 0006). Locks the pending fan-in row(s) so concurrent
    callers (sibling task completions via _advance, a resume()) serialize on this
    row instead of racing on independent READ COMMITTED snapshots — without this,
    two siblings completing concurrently can each see the other as "not complete
    yet" and both skip enqueueing the dependent (ADR-0010). order_by is required
    for a deterministic lock-acquisition order across transactions locking >1 row."""
    pending = session.scalars(
        select(InvestigationTask).where(
            InvestigationTask.investigation_id == investigation_id,
            InvestigationTask.status == "pending",
        )
        .order_by(InvestigationTask.id)
        .with_for_update()
    ).all()
    statuses = {
        str(t.id): t.status
        for t in session.scalars(
            select(InvestigationTask).where(
                InvestigationTask.investigation_id == investigation_id
            )
        )
    }
    return [
        t for t in pending if all(statuses.get(d) == "complete" for d in t.depends_on)
    ]


def _advance(session: Session, completed: InvestigationTask) -> None:
    """Enqueue every dependent whose prerequisites are now all complete. Runs inside
    the completing task's transaction: the status flip and the follow-on job commit
    atomically (outbox pattern, ADR-0003)."""
    session.flush()
    for t in _ready_pending_tasks(session, completed.investigation_id):
        if str(completed.id) in t.depends_on:
            _enqueue_task(session, t)


def enqueue_ready_tasks(session: Session, investigation_id: uuid.UUID) -> int:
    """Resume support (api routes): a paused investigation's newly-ready dependents
    were never enqueued (see _enqueue_task's paused guard), so re-derive readiness
    from scratch and enqueue every ready pending task. Reuses the same locked
    readiness predicate as _advance — no second definition of "ready" to drift."""
    ready = _ready_pending_tasks(session, investigation_id)
    for t in ready:
        _enqueue_task(session, t)
    return len(ready)


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
            # A failed investigation can leave a dependent task permanently
            # "pending" (one of its deps is "failed", never "complete" — it can
            # never become ready). Without this check the loop above never sees
            # live == None and spins forever. _finalize does the actual raising.
            failed = session.scalar(
                select(Investigation.id).where(
                    Investigation.id == investigation_id, Investigation.status == "failed"
                )
            )
            # Same reasoning as `failed`: a paused investigation can leave a pending
            # dependent that will never get a job (its enqueue is suppressed while
            # paused, see _enqueue_task) — without this check the loop would spin
            # forever waiting for a job that's never coming.
            paused = session.scalar(
                select(Investigation.id).where(
                    Investigation.id == investigation_id, Investigation.status == "paused"
                )
            )
        if live is None or failed is not None or paused is not None:
            return
        time.sleep(0.1)  # a job exists but isn't claimable yet (backoff or other worker)
