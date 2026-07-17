"""Context fusion (PRD-V2 2.5): the one structured artifact every specialist
consumes instead of raw evidence rows. Pure pydantic over plain values — research/
sits below investigations/ in the layer contract, so investigations passes
evidence/plan/timeline data IN as dicts; this module never imports ORM models."""

from datetime import datetime

from pydantic import BaseModel, Field

EXCERPT_TRIM_CHARS = 500


class EvidenceEntry(BaseModel):
    chunk_id: str
    excerpt: str
    stance: str
    query: str
    source_rank: float | None = None
    document_id: str
    document_title: str | None = None
    document_source: str
    document_published_at: datetime | None = None


class TimelineEntry(BaseModel):
    document_id: str
    published_at: datetime
    title: str | None = None
    doc_type: str
    source: str


class Contradiction(BaseModel):
    query: str
    supporting_chunk_id: str
    contradicting_chunk_id: str


class Gap(BaseModel):
    query: str
    evidence_count: int
    minimum_required: int


class InvestigationContext(BaseModel):
    """Deterministic: identical inputs always dump to identical JSON — the
    replay/reproducibility guarantee (Bible §13) extends to the fused context."""

    objective: str
    plan_summary: str
    evidence: list[EvidenceEntry] = Field(default_factory=list)
    timeline: list[TimelineEntry] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    gaps: list[Gap] = Field(default_factory=list)
    claims: list = Field(default_factory=list)  # Phase 4 placeholder


def build(
    objective: str,
    plan_summary: str,
    evidence: list[dict],
    timeline_entries: list[dict],
    query_counts: dict[str, int],
    min_evidence_per_query: int,
) -> InvestigationContext:
    """evidence: plain dicts matching EvidenceEntry fields (excerpts trimmed here,
    not by the caller). query_counts: query text -> evidence rows it produced,
    used to detect gaps. Contradictions are stance-opposite evidence pairs sharing
    a query — deterministic given a deterministically-ordered `evidence` list."""
    evidence_entries = [
        EvidenceEntry(**{**e, "excerpt": e["excerpt"][:EXCERPT_TRIM_CHARS]}) for e in evidence
    ]

    by_query: dict[str, list[dict]] = {}
    for e in evidence:
        by_query.setdefault(e["query"], []).append(e)
    contradictions = [
        Contradiction(
            query=query, supporting_chunk_id=s["chunk_id"], contradicting_chunk_id=c["chunk_id"]
        )
        for query, rows in by_query.items()
        for s in rows
        if s["stance"] == "supporting"
        for c in rows
        if c["stance"] == "contradicting"
    ]

    gaps = [
        Gap(query=q, evidence_count=count, minimum_required=min_evidence_per_query)
        for q, count in query_counts.items()
        if count < min_evidence_per_query
    ]

    return InvestigationContext(
        objective=objective,
        plan_summary=plan_summary,
        evidence=evidence_entries,
        timeline=[TimelineEntry(**t) for t in timeline_entries],
        contradictions=contradictions,
        gaps=gaps,
        claims=[],
    )
