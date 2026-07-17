"""Deterministic source ranking (PRD-V2 2.3): authority tier, freshness decay,
independence (publisher diversity among corroborating evidence), and corroboration
count combine into an explainable 0-1 score — modeled on investigations/confidence.py.
QUALITY_TIER lives here (not in investigations/confidence.py) because research sits
below investigations in the layer contract; confidence.py imports it from here."""

from datetime import datetime

from argus.core.config import get_settings
from argus.knowledge.models import Document

# source quality tiers: regulatory filings beat news beats profile boilerplate
QUALITY_TIER = {"filing": 1.0, "transcript": 0.9, "news": 0.6, "profile": 0.4}


def score_source(
    document: Document,
    corroborating_count: int,
    now: datetime,
    corroborating_publishers: int | None = None,
) -> tuple[float, dict]:
    """(score, explanation). `now` must come from the DB clock (core rule) — this
    function itself is pure computation over whatever timestamp is passed in.
    `corroborating_publishers` defaults to `corroborating_count` (assume every
    corroborator is a distinct source unless the caller knows otherwise)."""
    settings = get_settings()
    if corroborating_publishers is None:
        corroborating_publishers = corroborating_count

    authority = QUALITY_TIER.get(document.doc_type, 0.5)
    if document.published_at is None:
        freshness = 0.5  # unknown age: neither reward nor penalize
    else:
        age_days = max((now - document.published_at).days, 0)
        freshness = 0.5 ** (age_days / settings.rank_freshness_halflife_days)
    corroboration = min(corroborating_count / settings.rank_corroboration_saturation, 1.0)
    # distinct publishers out of total corroborators: an echo of one source scores
    # low even with a high raw count; independent confirmation scores high
    independence = (
        min(corroborating_publishers / corroborating_count, 1.0) if corroborating_count > 0 else 0.0
    )

    components = {
        "authority": authority,
        "freshness": freshness,
        "independence": independence,
        "corroboration": corroboration,
    }
    weights = {
        "authority": settings.rank_w_authority,
        "freshness": settings.rank_w_freshness,
        "independence": settings.rank_w_independence,
        "corroboration": settings.rank_w_corroboration,
    }
    score = sum(weights[k] * v for k, v in components.items())
    explanation = {
        "components": {
            k: {"value": round(v, 4), "weight": weights[k]} for k, v in components.items()
        },
        "inputs": {
            "doc_type": document.doc_type,
            "published_at": document.published_at.isoformat() if document.published_at else None,
            "corroborating_count": corroborating_count,
            "corroborating_publishers": corroborating_publishers,
        },
    }
    return round(score, 4), explanation
