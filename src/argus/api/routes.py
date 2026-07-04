"""JSON API. Sync `def` endpoints throughout (ADR-0004).
ponytail: one router module; split per-resource when it outgrows a screenful."""

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from argus.core.db import session_scope
from argus.core.models import Job
from argus.investigations import engine
from argus.investigations.models import (
    Evidence,
    Investigation,
    InvestigationLink,
    Report,
)
from argus.knowledge.models import Company, Document
from argus.observability.models import PipelineRun
from argus.research.retrieval import SearchFilters, search

router = APIRouter()


def get_db():
    with session_scope() as session:
        yield session


@router.get("/health")
def health(session: Session = Depends(get_db)) -> dict:
    session.execute(select(1))
    return {"status": "ok"}


# --- search / knowledge ---


@router.get("/api/search")
def api_search(
    q: str,
    company_id: uuid.UUID | None = None,
    doc_type: str | None = None,
    k: int = 10,
    session: Session = Depends(get_db),
) -> list[dict]:
    filters = SearchFilters(company_id=company_id, doc_types=[doc_type] if doc_type else None)
    return [vars(r) for r in search(session, q, filters=filters, k=k)]


@router.get("/api/companies")
def api_companies(q: str, limit: int = 20, session: Session = Depends(get_db)) -> list[dict]:
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
    question: str
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
def list_investigations(session: Session = Depends(get_db)) -> list[dict]:
    rows = session.scalars(
        select(Investigation).order_by(Investigation.created_at.desc())
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
    return _investigation_json(session, _get_or_404(session, investigation_id))


@router.get("/api/investigations/{investigation_id}/evidence")
def get_evidence(
    investigation_id: uuid.UUID, session: Session = Depends(get_db)
) -> list[dict]:
    _get_or_404(session, investigation_id)
    rows = session.scalars(
        select(Evidence).where(Evidence.investigation_id == investigation_id)
    ).all()
    return [
        {
            "chunk_id": e.chunk_id, "document_id": e.document_id, "stance": e.stance,
            "rationale": e.rationale, "query": e.query, "excerpt": e.excerpt,
            "strategy": e.strategy,
        }
        for e in rows
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
    }


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
    result = engine.replay_retrieval(session, investigation_id)
    return {
        "match": result["match"],
        "recorded_count": len(result["recorded"]),
        "replayed_count": len(result["replayed"]),
    }


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


# --- observability ---


@router.get("/api/metrics/pipeline")
def pipeline_metrics(session: Session = Depends(get_db)) -> dict:
    queue = dict(
        session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    since = datetime.now(UTC) - timedelta(hours=24)
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
    return {"queue_depth": queue, "stages_24h": stages}
