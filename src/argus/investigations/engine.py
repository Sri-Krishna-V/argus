"""Investigation engine: question → plan → stance-classified evidence → verified
report → deterministic confidence. Every step appends an investigation_event
(prompts, params, model, chunk IDs) so the run can be replayed (Bible §13).

Citation gate: a draft narrative may only cite chunks in the collected evidence set;
an invented marker fails the run — it never becomes a report."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, exists, select, update
from sqlalchemy.orm import Session

from argus.agentruntime import evidence as collector
from argus.agentruntime import planner
from argus.agentruntime.schemas import ExecutionRecord, ResearchPlan
from argus.core.db import session_scope
from argus.investigations import orchestrator
from argus.investigations.models import (
    Evidence,
    Hypothesis,
    Investigation,
    InvestigationEvent,
    InvestigationTask,
)
from argus.knowledge.models import Document, DocumentCompany


def _emit(session: Session, investigation_id: uuid.UUID, event_type: str, payload: dict) -> None:
    session.add(
        InvestigationEvent(
            investigation_id=investigation_id, event_type=event_type, payload=payload
        )
    )


def _record_payload(record: ExecutionRecord) -> dict:
    return record.model_dump(mode="json")


def create(session: Session, question: str, hypothesis: str | None = None) -> Investigation:
    inv = Investigation(question=question)
    session.add(inv)
    session.flush()
    if hypothesis:
        session.add(Hypothesis(investigation_id=inv.id, statement=hypothesis))
    _emit(session, inv.id, "investigation.created",
          {"question": question, "hypothesis": hypothesis})
    return inv


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
    if inv.status == "cancelled":
        return inv  # cancelled while draining; leave terminal state alone
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


def refresh(session: Session, investigation_id: uuid.UUID) -> Investigation:
    """Re-run evidence collection with the stored plan (user-triggered — PRD §11
    knowledge-evolution V1-lite), rebuild the report, recompute confidence."""
    inv = session.get(Investigation, investigation_id)
    if not inv.plan:
        raise ValueError("investigation has no stored plan; run it first")
    inv.status = "running"
    inv.version += 1
    session.flush()
    # previous version's unfinished tasks (e.g. an orphaned pending task left behind
    # by a run that failed elsewhere in the DAG) never get re-driven; retire them
    session.execute(
        update(InvestigationTask)
        .where(
            InvestigationTask.investigation_id == inv.id,
            InvestigationTask.status.in_(["pending", "running"]),
        )
        .values(status="obsolete")
    )
    session.execute(delete(Evidence).where(Evidence.investigation_id == inv.id))
    plan = ResearchPlan.model_validate(inv.plan)
    company_ids = [uuid.UUID(c) for c in inv.company_ids]
    orchestrator.compile_dag(session, inv, plan, company_ids)
    session.commit()  # tasks + jobs must be visible to the drain's own transactions

    orchestrator.drain(inv.id)
    inv = _finalize(session, investigation_id)
    _emit(session, inv.id, "investigation.refreshed",
          {"confidence": inv.confidence, "version": inv.version})
    return inv


def execute(investigation_id: uuid.UUID, action: str = "run") -> None:
    """Transaction-owning wrapper for the API: a failed run rolls back its partial
    writes, then the failure itself is committed in a fresh transaction — the
    investigation is never left 'running' with garbage evidence."""
    step = {"run": run, "refresh": refresh}[action]
    try:
        with session_scope() as session:
            step(session, investigation_id)
    except Exception as exc:
        with session_scope() as session:
            inv = session.get(Investigation, investigation_id)
            if inv.status != "cancelled":
                inv.status = "failed"
                _emit(session, investigation_id, "investigation.failed", {"error": str(exc)})


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


def has_new_evidence(session: Session, inv: Investigation) -> bool:
    """Knowledge-evolution V1-lite (PRD §11): an enriched document mentioning this
    investigation's companies arrived after the last refresh.
    ponytail: computed on read instead of an event consumer — can't drift, needs no
    extra infrastructure; move to a consumer + flag column if read cost ever matters."""
    if inv.last_refreshed_at is None or not inv.company_ids:
        return False
    return session.scalar(
        select(
            exists().where(
                DocumentCompany.company_id.in_([uuid.UUID(c) for c in inv.company_ids]),
                DocumentCompany.document_id == Document.id,
                Document.status == "enriched",
                Document.ingested_at > inv.last_refreshed_at,
            )
        )
    )
