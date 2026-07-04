"""Evidence collector: deterministic hybrid retrieval, then LLM stance classification.
Chunk references come from RetrievalResult by construction, so evidence is citable
before the LLM ever sees it (ADR-0005)."""

import uuid

from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from argus.agentruntime import adapter
from argus.agentruntime.schemas import (
    CollectedEvidence,
    ExecutionRecord,
    ResearchPlan,
    StanceResult,
)
from argus.core.config import get_settings
from argus.knowledge.models import Company
from argus.research.retrieval import RetrievalResult, SearchFilters, search

EXCERPT_CHARS = 700

INSTRUCTION = """You classify evidence stance for a research question.
For EACH numbered excerpt, decide whether it SUPPORTS, CONTRADICTS, or is UNKNOWN
(neutral/irrelevant) with respect to the question, with a one-sentence rationale.
Return exactly one result per excerpt, in the same order as the excerpts."""


class StanceBatch(BaseModel):
    """One structured call classifies a whole query's result set."""

    results: list[StanceResult]


def _resolve_companies(session: Session, names: list[str]) -> list[uuid.UUID]:
    """Planner names → canonical company ids; unresolvable names are dropped."""
    ids = []
    for name in names:
        company_id = session.scalar(
            select(Company.id).where(
                or_(
                    Company.name.ilike(f"%{name}%"),
                    Company.aliases.any(name),
                    Company.tickers.any(name.upper()),
                )
            )
        )
        if company_id is not None:
            ids.append(company_id)
    return ids


def collect(
    session: Session, question: str, plan: ResearchPlan, k: int | None = None
) -> tuple[list[CollectedEvidence], list[ExecutionRecord]]:
    k = k or get_settings().agent_retrieval_k
    company_ids = _resolve_companies(session, plan.companies) or [None]
    doc_types = plan.doc_types or None
    seen: set[uuid.UUID] = set()
    evidence: list[CollectedEvidence] = []
    records: list[ExecutionRecord] = []

    for query in plan.queries:
        hits: list[RetrievalResult] = []
        for company_id in company_ids:
            filters = SearchFilters(company_id=company_id, doc_types=doc_types)
            for hit in search(session, query, filters=filters, k=k):
                if hit.chunk_id not in seen:
                    seen.add(hit.chunk_id)
                    hits.append(hit)
        if not hits:
            continue

        numbered = "\n\n".join(
            f"[{i}] {h.text[:EXCERPT_CHARS]}" for i, h in enumerate(hits, 1)
        )
        batch, record = adapter.run_structured(
            "classify_stance",
            INSTRUCTION,
            f"Question: {question}\n\nExcerpts:\n{numbered}",
            StanceBatch,
        )
        records.append(record)
        if len(batch.results) != len(hits):
            raise ValueError(
                f"stance batch returned {len(batch.results)} results for {len(hits)} excerpts"
            )
        evidence.extend(
            CollectedEvidence(
                chunk_id=hit.chunk_id,
                document_id=hit.document_id,
                excerpt=hit.text[:EXCERPT_CHARS],
                stance=result.stance,
                rationale=result.rationale,
                query=query,
                scores=hit.scores,
                strategy=hit.strategy,
            )
            for hit, result in zip(hits, batch.results, strict=True)
        )
    return evidence, records
