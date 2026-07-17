"""Deterministic confidence: a weighted, explainable function over evidence.
Never LLM-generated (Bible §15). Every component and weight appears in the
breakdown so a score of 0.62 is auditable, not vibes."""

from datetime import UTC, datetime

from argus.investigations.models import Evidence
from argus.knowledge.models import Document
from argus.research.ranking import QUALITY_TIER

RECENCY_DAYS = 365

WEIGHTS = {
    "source_diversity": 0.25,  # distinct connectors, saturates at 3
    "document_count": 0.15,  # distinct documents, saturates at 5
    "source_quality": 0.20,  # mean doc_type tier
    "recency": 0.15,  # share of evidence published within RECENCY_DAYS
    "stance_agreement": 0.25,  # supporting / (supporting + contradicting)
}


def compute(evidence: list[Evidence], documents: dict, now: datetime | None = None) -> dict:
    """evidence + {document_id: Document} → {"score": float, "components": {...}}.
    Empty evidence scores 0 — no evidence, no confidence."""
    if not evidence:
        return {"score": 0.0, "components": {}, "evidence_count": 0}
    now = now or datetime.now(UTC)

    docs: list[Document] = [documents[e.document_id] for e in evidence]
    sources = {d.source for d in docs}
    doc_ids = {d.id for d in docs}
    published = [d.published_at for d in docs if d.published_at is not None]
    recent = [p for p in published if (now - p).days <= RECENCY_DAYS]
    supporting = sum(e.stance == "supporting" for e in evidence)
    contradicting = sum(e.stance == "contradicting" for e in evidence)
    stanced = supporting + contradicting

    components = {
        "source_diversity": min(len(sources) / 3, 1.0),
        "document_count": min(len(doc_ids) / 5, 1.0),
        "source_quality": sum(QUALITY_TIER.get(d.doc_type, 0.5) for d in docs) / len(docs),
        "recency": len(recent) / len(published) if published else 0.0,
        # all-unknown evidence is maximally uncertain, not agreeing
        "stance_agreement": supporting / stanced if stanced else 0.5,
    }
    score = sum(WEIGHTS[k] * v for k, v in components.items())
    return {
        "score": round(score, 4),
        "components": {
            k: {"value": round(v, 4), "weight": WEIGHTS[k]} for k, v in components.items()
        },
        "evidence_count": len(evidence),
        "inputs": {
            "distinct_sources": len(sources),
            "distinct_documents": len(doc_ids),
            "supporting": supporting,
            "contradicting": contradicting,
            "unknown": len(evidence) - stanced,
        },
    }
