"""Server-rendered UI: Jinja2 + HTMX, no build pipeline (plan §Phase 7).
Reads through the same engine/research modules as the JSON API."""

import re
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from markupsafe import escape
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from argus.api.routes import get_db
from argus.core.db import session_scope
from argus.core.models import Job
from argus.investigations import engine
from argus.investigations.models import (
    Evidence,
    Hypothesis,
    Investigation,
    InvestigationLink,
    Report,
)
from argus.knowledge.models import Document
from argus.observability.models import PipelineRun
from argus.research.citations import resolve
from argus.research.retrieval import search

router = APIRouter(default_response_class=HTMLResponse, include_in_schema=False)
templates = Jinja2Templates(directory=str(Path(__file__).parent / "templates"))


@router.get("/")
def workspace(request: Request, session: Session = Depends(get_db)):
    rows = session.scalars(
        select(Investigation).order_by(Investigation.created_at.desc())
    ).all()
    investigations = [
        {"inv": inv, "stale": engine.has_new_evidence(session, inv)} for inv in rows
    ]
    return templates.TemplateResponse(
        request, "workspace.html", {"investigations": investigations}
    )


@router.post("/investigations")
def create_investigation(question: str = Form(...), hypothesis: str = Form("")):
    with session_scope() as session:
        inv_id = engine.create(session, question, hypothesis or None).id
    engine.execute(inv_id, "run")
    return RedirectResponse(f"/investigations/{inv_id}", status_code=303)


@router.post("/investigations/{investigation_id}/refresh")
def refresh_investigation(investigation_id: uuid.UUID):
    engine.execute(investigation_id, "refresh")
    return RedirectResponse(f"/investigations/{investigation_id}", status_code=303)


def _render_narrative(session: Session, narrative: str) -> tuple[str, list]:
    """Replace [chunk:<uuid>] markers with numbered citation references and return
    the resolved citation list, in first-appearance order. The narrative is LLM
    output — HTML-escape it before injecting our own markup (the template renders
    the result with `| safe`)."""
    order: list[uuid.UUID] = []
    for m in engine.MARKER_RE.finditer(narrative):
        cid = uuid.UUID(m.group(1))
        if cid not in order:
            order.append(cid)
    citations = resolve(session, order) if order else []
    index = {cid: i for i, cid in enumerate(order, 1)}

    def number(m: re.Match) -> str:
        n = index[uuid.UUID(m.group(1))]
        return f'<sup><a href="#cite-{n}">[{n}]</a></sup>'

    return engine.MARKER_RE.sub(number, str(escape(narrative))), citations


@router.get("/investigations/{investigation_id}")
def investigation_detail(
    request: Request, investigation_id: uuid.UUID, session: Session = Depends(get_db)
):
    inv = session.get(Investigation, investigation_id)
    evidence = session.scalars(
        select(Evidence).where(Evidence.investigation_id == investigation_id)
    ).all()
    report = session.scalars(
        select(Report)
        .where(Report.investigation_id == investigation_id)
        .order_by(Report.created_at.desc())
        .limit(1)
    ).first()
    hypotheses = session.scalars(
        select(Hypothesis).where(Hypothesis.investigation_id == investigation_id)
    ).all()
    links = session.execute(
        select(InvestigationLink, Investigation)
        .join(Investigation, Investigation.id == InvestigationLink.dst_investigation_id)
        .where(InvestigationLink.src_investigation_id == investigation_id)
    ).all()
    narrative_html, citations = (
        _render_narrative(session, report.narrative) if report else ("", [])
    )
    by_stance = {
        stance: [e for e in evidence if e.stance == stance]
        for stance in ("supporting", "contradicting", "unknown")
    }
    return templates.TemplateResponse(request, "investigation.html", {
        "inv": inv,
        "stale": engine.has_new_evidence(session, inv),
        "hypotheses": hypotheses,
        "by_stance": by_stance,
        "report": report,
        "narrative_html": narrative_html,
        "citations": citations,
        "links": links,
    })


@router.get("/search")
def search_page(request: Request, q: str = "", session: Session = Depends(get_db)):
    results = search(session, q, k=20) if q else []
    return templates.TemplateResponse(request, "search.html", {"q": q, "results": results})


@router.get("/pipeline")
def pipeline_dashboard(request: Request, session: Session = Depends(get_db)):
    queue = dict(
        session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
    )
    dead = session.scalars(
        select(Job).where(Job.status == "dead").order_by(Job.created_at.desc()).limit(20)
    ).all()
    recent = session.scalars(
        select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(30)
    ).all()
    counts = {
        "documents": session.scalar(select(func.count()).select_from(Document)),
    }
    return templates.TemplateResponse(request, "pipeline.html", {
        "queue": queue, "dead": dead, "recent": recent, "counts": counts,
    })
