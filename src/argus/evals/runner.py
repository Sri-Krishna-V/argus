"""Evaluation harness (Phase 8): golden-set retrieval quality and investigation
report quality, both measured against the corpus/reports actually in the DB —
no mocked scoring. Results are stamped with strategy/pipeline versions and
persisted so regressions are attributable (Bible §8)."""

import json
import logging
import uuid
from collections import Counter
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from argus.core.config import get_settings
from argus.investigations.models import Evidence, Report
from argus.investigations.orchestrator import MARKER_RE
from argus.knowledge.models import Company, Document, DocumentCompany
from argus.observability.models import EvalRun
from argus.research.retrieval import search

log = logging.getLogger(__name__)

INVESTIGATION_EVAL_VERSION = "report-eval/v1"


def load_golden(path: Path) -> dict:
    try:
        data = json.loads(Path(path).read_text())
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"golden set {path}: {exc}") from exc

    if not data.get("version"):
        raise ValueError(f"golden set {path}: missing 'version'")
    questions = data.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError(f"golden set {path}: 'questions' must be a non-empty list")
    for q in questions:
        qid = q.get("id")
        if not qid:
            raise ValueError(f"golden set {path}: a question is missing 'id'")
        if not q.get("question"):
            raise ValueError(f"golden set {path}: question {qid!r} missing 'question'")
        expected = q.get("expected")
        if not isinstance(expected, list) or not expected:
            raise ValueError(f"golden set {path}: question {qid!r} missing non-empty 'expected'")
        for selector in expected:
            if not selector.get("ticker"):
                raise ValueError(
                    f"golden set {path}: question {qid!r} has a selector without 'ticker'"
                )
    return data


def _resolve_selector(session: Session, ticker: str, doc_type: str | None) -> set[uuid.UUID]:
    query = (
        select(Document.id)
        .join(DocumentCompany, DocumentCompany.document_id == Document.id)
        .join(Company, Company.id == DocumentCompany.company_id)
        .where(Company.tickers.any(ticker))
    )
    if doc_type:
        query = query.where(Document.doc_type == doc_type)
    return set(session.scalars(query).all())


def eval_retrieval(session: Session, golden: dict, k: int = 10) -> dict:
    per_question = []
    skipped = 0
    for q in golden["questions"]:
        expected_ids: set[uuid.UUID] = set()
        for selector in q["expected"]:
            expected_ids |= _resolve_selector(session, selector["ticker"], selector.get("doc_type"))
        if not expected_ids:
            skipped += 1
            continue

        results = search(session, q["question"], k=k)
        doc_order: list[uuid.UUID] = []
        for r in results:
            if r.document_id not in doc_order:
                doc_order.append(r.document_id)

        rank = next(
            (i for i, doc_id in enumerate(doc_order, start=1) if doc_id in expected_ids), None
        )
        per_question.append({"id": q["id"], "rank": rank, "hit": rank is not None})

    n = len(per_question)
    hits_at_3 = sum(1 for pq in per_question if pq["rank"] and pq["rank"] <= 3)
    hit_rate_at_3 = hits_at_3 / n if n else 0.0
    hit_rate_at_k = sum(1 for pq in per_question if pq["hit"]) / n if n else 0.0
    mrr = sum(1 / pq["rank"] if pq["rank"] else 0.0 for pq in per_question) / n if n else 0.0
    return {
        "questions": n,
        "skipped": skipped,
        "hit_rate_at_3": hit_rate_at_3,
        "hit_rate_at_k": hit_rate_at_k,
        "mrr": mrr,
        "k": k,
        "per_question": per_question,
    }


def eval_investigation(session: Session) -> dict:
    latest = (
        select(Report.investigation_id, func.max(Report.version).label("version"))
        .group_by(Report.investigation_id)
        .subquery()
    )
    reports = session.scalars(
        select(Report).join(
            latest,
            (Report.investigation_id == latest.c.investigation_id)
            & (Report.version == latest.c.version),
        )
    ).all()

    per_investigation = []
    coverage_total = both_stances_total = unknown_fraction_total = 0.0
    for report in reports:
        evidence_rows = session.scalars(
            select(Evidence).where(Evidence.investigation_id == report.investigation_id)
        ).all()
        markers = MARKER_RE.findall(report.narrative)
        cited_chunks = {uuid.UUID(m) for m in markers}
        evidence_count = len(evidence_rows)
        coverage = len(cited_chunks) / evidence_count if evidence_count else 0.0
        stance_counts = Counter(r.stance for r in evidence_rows)
        has_both_stances = stance_counts["supporting"] > 0 and stance_counts["contradicting"] > 0
        unknown_fraction = stance_counts["unknown"] / evidence_count if evidence_count else 0.0

        coverage_total += coverage
        both_stances_total += int(has_both_stances)
        unknown_fraction_total += unknown_fraction
        per_investigation.append({
            "id": str(report.investigation_id),
            "citation_count": len(markers),
            "citation_coverage": coverage,
            "has_both_stances": has_both_stances,
        })

    n = len(per_investigation)
    return {
        "reports": n,
        "mean_citation_coverage": coverage_total / n if n else 0.0,
        "both_stances_fraction": both_stances_total / n if n else 0.0,
        "mean_unknown_fraction": unknown_fraction_total / n if n else 0.0,
        "per_investigation": per_investigation,
    }


def record_run(
    session: Session, kind: str, metrics: dict, golden_version: int | None, strategy: str
) -> EvalRun:
    run = EvalRun(
        kind=kind,
        metrics=metrics,
        golden_version=golden_version,
        pipeline_version=get_settings().pipeline_version,
        strategy=strategy,
    )
    session.add(run)
    session.flush()
    log.info("eval run recorded", extra={"context": {"kind": kind, "strategy": strategy}})
    return run
