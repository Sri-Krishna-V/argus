"""Investigation engine: question → plan → stance-classified evidence → verified
report → deterministic confidence. Every step appends an investigation_event
(prompts, params, model, chunk IDs) so the run can be replayed (Bible §13).

Citation gate: a draft narrative may only cite chunks in the collected evidence set;
an invented marker fails the run — it never becomes a report."""

import re
import uuid
from datetime import UTC, datetime

from sqlalchemy import delete, exists, select
from sqlalchemy.orm import Session

from argus.agentruntime import drafter, planner
from argus.agentruntime import evidence as collector
from argus.agentruntime.schemas import (
    CollectedEvidence,
    ExecutionRecord,
    ResearchPlan,
    Stance,
)
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.investigations import confidence
from argus.investigations.models import (
    Evidence,
    Hypothesis,
    Investigation,
    InvestigationEvent,
    Report,
)
from argus.knowledge.models import Document, DocumentCompany

MARKER_RE = re.compile(r"\[chunk:([0-9a-f-]{36})\]")


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
    """Full pipeline for one investigation; raises on failure so the caller's
    transaction rolls back partial writes. Use execute() for persisted failures."""
    inv = session.get(Investigation, investigation_id)
    inv.status = "running"
    session.flush()
    _plan_and_collect(session, inv)
    _draft_and_score(session, inv)
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
    plan = ResearchPlan.model_validate(inv.plan)
    _collect(session, inv, plan, [uuid.UUID(c) for c in inv.company_ids])
    _draft_and_score(session, inv)
    inv.status = "complete"
    inv.last_refreshed_at = datetime.now(UTC)
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
            inv.status = "failed"
            _emit(session, investigation_id, "investigation.failed", {"error": str(exc)})


def _plan_and_collect(session: Session, inv: Investigation) -> None:
    plan, record = planner.plan(inv.question)
    company_ids = collector.resolve_companies(session, plan.companies)
    inv.plan = plan.model_dump(mode="json")
    inv.company_ids = [str(c) for c in company_ids]
    _emit(session, inv.id, "agent.plan",
          {"plan": inv.plan, "company_ids": inv.company_ids, "record": _record_payload(record)})
    _collect(session, inv, plan, company_ids)


def _collect(
    session: Session, inv: Investigation, plan: ResearchPlan, company_ids: list[uuid.UUID]
) -> None:
    k = get_settings().agent_retrieval_k
    collected, records = collector.collect(
        session, inv.question, plan, k=k, company_ids=company_ids
    )
    # evidence is derived: rebuild wholesale on every (re)run
    session.execute(delete(Evidence).where(Evidence.investigation_id == inv.id))
    for e in collected:
        session.add(
            Evidence(
                investigation_id=inv.id, chunk_id=e.chunk_id, document_id=e.document_id,
                stance=e.stance.value, rationale=e.rationale, query=e.query,
                excerpt=e.excerpt, scores=e.scores, strategy=e.strategy,
            )
        )
    _emit(session, inv.id, "evidence.collected", {
        "queries": [q.query for q in plan.queries],
        "company_ids": inv.company_ids,
        "doc_types": plan.doc_types,
        "k": k,
        "chunk_ids": [str(e.chunk_id) for e in collected],
        "records": [_record_payload(r) for r in records],
    })
    session.flush()


def _draft_and_score(session: Session, inv: Investigation) -> None:
    rows = session.scalars(
        select(Evidence).where(Evidence.investigation_id == inv.id)
    ).all()
    if not rows:
        raise ValueError("no evidence collected; cannot draft a report (ADR-0005)")

    draft, record = drafter.draft(
        inv.question,
        [
            CollectedEvidence(
                chunk_id=r.chunk_id, document_id=r.document_id, excerpt=r.excerpt,
                stance=Stance(r.stance), rationale=r.rationale, query=r.query,
                scores=r.scores, strategy=r.strategy,
            )
            for r in rows
        ],
    )
    # citation gate: every marker must reference collected evidence
    cited = {uuid.UUID(m) for m in MARKER_RE.findall(draft.narrative)}
    allowed = {r.chunk_id for r in rows}
    if invented := cited - allowed:
        raise ValueError(f"draft cites chunks outside the evidence set: {sorted(invented)}")
    if not cited:
        raise ValueError("draft narrative carries no citation markers")

    docs = {
        d.id: d
        for d in session.scalars(
            select(Document).where(Document.id.in_({r.document_id for r in rows}))
        )
    }
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
    _emit(session, inv.id, "agent.draft", {"record": _record_payload(record)})


def replay_retrieval(session: Session, investigation_id: uuid.UUID) -> dict:
    """Re-execute retrieval from the recorded params; the recorded and replayed chunk
    sets must match for the investigation to be reproducible (corpus unchanged)."""
    event = session.scalars(
        select(InvestigationEvent)
        .where(
            InvestigationEvent.investigation_id == investigation_id,
            InvestigationEvent.event_type == "evidence.collected",
        )
        .order_by(InvestigationEvent.id.desc())
        .limit(1)
    ).first()
    if event is None:
        raise LookupError("no evidence.collected event to replay")

    p = event.payload
    company_ids = [uuid.UUID(c) for c in p["company_ids"]] or [None]
    seen: set[uuid.UUID] = set()
    replayed: list[uuid.UUID] = []
    for query in p["queries"]:
        hits = collector.retrieve(
            session, query, company_ids, p["doc_types"] or None, p["k"], seen
        )
        replayed.extend(h.chunk_id for h in hits)
    recorded = [uuid.UUID(c) for c in p["chunk_ids"]]
    return {
        "recorded": recorded,
        "replayed": replayed,
        "match": set(recorded) == set(replayed),
    }


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
