"""JSON API. Sync `def` endpoints throughout (ADR-0004).
ponytail: one router module; split per-resource when it outgrows a screenful."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from argus.core.db import session_scope
from argus.core.models import Job
from argus.investigations import engine, orchestrator
from argus.investigations.models import (
    Evidence,
    Hypothesis,
    Investigation,
    InvestigationEvent,
    InvestigationLink,
    InvestigationTask,
    Report,
)
from argus.knowledge.models import Company, Document
from argus.observability.models import PipelineRun
from argus.research.citations import resolve
from argus.research.retrieval import SearchFilters, search

router = APIRouter()


def get_db():
    with session_scope() as session:
        yield session


@router.get("/health")
def health(session: Session = Depends(get_db)) -> dict:
    session.execute(select(1))
    return {"status": "ok"}


@router.get("/health/ready")
def health_ready(session: Session = Depends(get_db)):
    try:
        session.execute(select(1))
    except Exception:
        return JSONResponse({"status": "unavailable"}, status_code=503)
    return {"status": "ready"}


# --- search / knowledge ---


@router.get("/api/search")
def api_search(
    q: str = Query(..., max_length=500),
    company_id: uuid.UUID | None = None,
    doc_type: str | None = None,
    k: int = Query(10, ge=1, le=100),
    session: Session = Depends(get_db),
) -> list[dict]:
    filters = SearchFilters(company_id=company_id, doc_types=[doc_type] if doc_type else None)
    return [vars(r) for r in search(session, q, filters=filters, k=k)]


@router.get("/api/companies")
def api_companies(
    q: str = Query(..., max_length=500),
    limit: int = Query(20, ge=1, le=200),
    session: Session = Depends(get_db),
) -> list[dict]:
    rows = session.scalars(
        select(Company).where(Company.name.ilike(f"%{q}%")).limit(limit)
    ).all()
    return [
        {"id": c.id, "name": c.name, "cik": c.cik, "tickers": c.tickers} for c in rows
    ]


@router.get("/api/documents/{document_id}")
def api_document(document_id: uuid.UUID, session: Session = Depends(get_db)) -> dict:
    doc = session.get(Document, document_id)
    if doc is None:
        raise HTTPException(404, "document not found")
    return {
        c: getattr(doc, c)
        for c in ("id", "source", "title", "url", "doc_type", "published_at", "status")
    }


# --- investigations ---


class CreateInvestigation(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    hypothesis: str | None = None


class CreateLink(BaseModel):
    dst_investigation_id: uuid.UUID
    link_type: str = "relates_to"


def _investigation_json(session: Session, inv: Investigation) -> dict:
    return {
        "id": inv.id,
        "question": inv.question,
        "status": inv.status,
        "confidence": inv.confidence,
        "confidence_breakdown": inv.confidence_breakdown,
        "version": inv.version,
        "created_at": inv.created_at,
        "last_refreshed_at": inv.last_refreshed_at,
        "new_evidence_available": engine.has_new_evidence(session, inv),
    }


@router.post("/api/investigations", status_code=201)
def create_investigation(body: CreateInvestigation) -> dict:
    # own transactions: create commits first, so a failed run is still inspectable
    with session_scope() as session:
        inv = engine.create(session, body.question, body.hypothesis)
        inv_id = inv.id
    # ponytail: runs synchronously in-request (seconds with live LLM); move to the
    # jobs outbox + polling if investigations ever need to be concurrent
    engine.execute(inv_id, "run")
    with session_scope() as session:
        return _investigation_json(session, session.get(Investigation, inv_id))


@router.get("/api/investigations")
def list_investigations(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> list[dict]:
    rows = session.scalars(
        select(Investigation)
        .order_by(Investigation.created_at.desc(), Investigation.id.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [_investigation_json(session, inv) for inv in rows]


def _get_or_404(session: Session, investigation_id: uuid.UUID) -> Investigation:
    inv = session.get(Investigation, investigation_id)
    if inv is None:
        raise HTTPException(404, "investigation not found")
    return inv


@router.get("/api/investigations/{investigation_id}")
def get_investigation(
    investigation_id: uuid.UUID, session: Session = Depends(get_db)
) -> dict:
    inv = _get_or_404(session, investigation_id)
    hypotheses = session.scalars(
        select(Hypothesis).where(Hypothesis.investigation_id == investigation_id)
    ).all()
    links = session.execute(
        select(InvestigationLink, Investigation)
        .join(Investigation, Investigation.id == InvestigationLink.dst_investigation_id)
        .where(InvestigationLink.src_investigation_id == investigation_id)
    ).all()
    return _investigation_json(session, inv) | {
        "hypotheses": [
            {"id": h.id, "statement": h.statement, "created_at": h.created_at}
            for h in hypotheses
        ],
        "links": [
            {"link_type": link.link_type, "investigation_id": dst.id, "question": dst.question}
            for link, dst in links
        ],
    }


@router.get("/api/investigations/{investigation_id}/evidence")
def get_evidence(
    investigation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> list[dict]:
    _get_or_404(session, investigation_id)
    rows = session.scalars(
        select(Evidence)
        .where(Evidence.investigation_id == investigation_id)
        .order_by(Evidence.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "chunk_id": e.chunk_id, "document_id": e.document_id, "stance": e.stance,
            "rationale": e.rationale, "query": e.query, "excerpt": e.excerpt,
            "strategy": e.strategy,
        }
        for e in rows
    ]


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


@router.get("/api/investigations/{investigation_id}/events")
def get_events(
    investigation_id: uuid.UUID,
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> list[dict]:
    _get_or_404(session, investigation_id)
    rows = session.scalars(
        select(InvestigationEvent)
        .where(InvestigationEvent.investigation_id == investigation_id)
        .order_by(InvestigationEvent.id)
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": e.id, "event_type": e.event_type, "payload": e.payload,
            "created_at": e.created_at,
        }
        for e in rows
    ]


def _report_citations(session: Session, narrative: str) -> list[dict]:
    """Numbered, first-appearance-order citations for [chunk:<uuid>] markers.
    Only http(s) URLs are kept — a stored javascript: URI must never become a link."""
    order: list[uuid.UUID] = []
    for m in orchestrator.MARKER_RE.finditer(narrative):
        cid = uuid.UUID(m.group(1))
        if cid not in order:
            order.append(cid)
    if not order:
        return []
    by_id = {c.chunk_id: c for c in resolve(session, order)}
    return [
        {
            "index": i,
            "chunk_id": by_id[cid].chunk_id,
            "document_id": by_id[cid].document_id,
            "title": by_id[cid].title,
            "url": by_id[cid].url
            if by_id[cid].url and by_id[cid].url.startswith(("http://", "https://"))
            else None,
            "source": by_id[cid].source,
            "published_at": by_id[cid].published_at,
            "excerpt": by_id[cid].excerpt,
        }
        for i, cid in enumerate(order, 1)
    ]


@router.get("/api/investigations/{investigation_id}/report")
def get_report(investigation_id: uuid.UUID, session: Session = Depends(get_db)) -> dict:
    _get_or_404(session, investigation_id)
    report = session.scalars(
        select(Report)
        .where(Report.investigation_id == investigation_id)
        .order_by(Report.created_at.desc())
        .limit(1)
    ).first()
    if report is None:
        raise HTTPException(404, "no report yet")
    return {
        c: getattr(report, c)
        for c in (
            "id", "version", "executive_summary", "key_findings", "risks",
            "follow_up_questions", "narrative", "model", "created_at",
        )
    } | {"citations": _report_citations(session, report.narrative)}


@router.post("/api/investigations/{investigation_id}/refresh")
def refresh_investigation(investigation_id: uuid.UUID) -> dict:
    with session_scope() as session:
        _get_or_404(session, investigation_id)
    engine.execute(investigation_id, "refresh")
    with session_scope() as session:
        return _investigation_json(session, session.get(Investigation, investigation_id))


@router.post("/api/investigations/{investigation_id}/replay")
def replay_investigation(
    investigation_id: uuid.UUID, session: Session = Depends(get_db)
) -> dict:
    _get_or_404(session, investigation_id)
    return engine.replay_retrieval(session, investigation_id)


@router.post("/api/investigations/{investigation_id}/links", status_code=201)
def link_investigations(
    investigation_id: uuid.UUID, body: CreateLink, session: Session = Depends(get_db)
) -> dict:
    _get_or_404(session, investigation_id)
    _get_or_404(session, body.dst_investigation_id)
    session.add(
        InvestigationLink(
            src_investigation_id=investigation_id,
            dst_investigation_id=body.dst_investigation_id,
            link_type=body.link_type,
        )
    )
    return {"linked": True}


# --- jobs ---


_JOB_STATUSES = ("pending", "running", "completed", "failed", "dead")


@router.get("/api/jobs")
def list_jobs(
    status: str = Query(...),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: Session = Depends(get_db),
) -> list[dict]:
    if status not in _JOB_STATUSES:
        raise HTTPException(422, f"status must be one of {_JOB_STATUSES}")
    rows = session.scalars(
        select(Job)
        .where(Job.status == status)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [
        {
            "id": j.id, "job_type": j.job_type, "document_id": j.document_id,
            "attempts": j.attempts, "max_attempts": j.max_attempts,
            "last_error": j.last_error, "created_at": j.created_at,
        }
        for j in rows
    ]


@router.post("/api/jobs/{job_id}/retry")
def retry_job(job_id: int, session: Session = Depends(get_db)) -> dict:
    job = session.get(Job, job_id)
    if job is None or job.status != "dead":
        raise HTTPException(404, "no dead job with that id")
    job.status = "pending"
    job.attempts = 0
    job.run_after = func.now()
    return {"retried": True}


# --- observability ---


@router.get("/api/metrics/pipeline")
def pipeline_metrics(session: Session = Depends(get_db)) -> dict:
    queue = dict(
        session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    # only jobs already runnable — backoff-scheduled jobs would yield a negative age
    now = datetime.now(UTC)
    oldest_run_after = session.scalar(
        select(func.min(Job.run_after)).where(Job.status == "pending", Job.run_after <= now)
    )
    oldest_pending_seconds = (
        None if oldest_run_after is None else (now - oldest_run_after).total_seconds()
    )
    since = datetime.now(UTC) - timedelta(hours=24)
    retries_24h = session.scalar(
        select(func.count())
        .select_from(PipelineRun)
        .where(PipelineRun.created_at >= since, PipelineRun.attempt > 1)
    )
    stages = [
        {
            "stage": stage, "status": status, "runs": runs,
            "avg_duration_ms": round(float(avg_ms), 1),
        }
        for stage, status, runs, avg_ms in session.execute(
            select(
                PipelineRun.stage, PipelineRun.status,
                func.count(), func.avg(PipelineRun.duration_ms),
            )
            .where(PipelineRun.created_at >= since)
            .group_by(PipelineRun.stage, PipelineRun.status)
            .order_by(PipelineRun.stage)
        ).all()
    ]
    return {
        "queue_depth": queue,
        "stages_24h": stages,
        "oldest_pending_seconds": oldest_pending_seconds,
        "retries_24h": retries_24h,
        "document_count": session.scalar(select(func.count()).select_from(Document)),
    }
