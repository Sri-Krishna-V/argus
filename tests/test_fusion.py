"""PRD-V2 2.5: context fusion is a pure pydantic builder over plain values — no DB,
no ORM, no LLM. Determinism, contradiction/gap detection, and empty-input safety
are exactly what's worth testing here."""

import uuid

from argus.research.fusion import build


def _ev(chunk_id, document_id, query, stance, excerpt="excerpt text"):
    return {
        "chunk_id": str(chunk_id), "excerpt": excerpt, "stance": stance, "query": query,
        "source_rank": 0.5, "document_id": str(document_id), "document_title": "t",
        "document_source": "s", "document_published_at": None,
    }


def test_fusion_is_deterministic_given_identical_inputs():
    c1, c2, d1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    evidence = [_ev(c1, d1, "q1", "supporting"), _ev(c2, d1, "q1", "contradicting")]
    kwargs = dict(
        objective="obj", plan_summary="summary", evidence=evidence, timeline_entries=[],
        query_counts={"q1": 2}, min_evidence_per_query=2,
    )
    assert build(**kwargs).model_dump(mode="json") == build(**kwargs).model_dump(mode="json")


def test_fusion_detects_contradictions_from_opposing_stances():
    c1, c2, d1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    evidence = [_ev(c1, d1, "q1", "supporting"), _ev(c2, d1, "q1", "contradicting")]
    context = build("obj", "s", evidence, [], {"q1": 2}, min_evidence_per_query=2)
    assert len(context.contradictions) == 1
    assert context.contradictions[0].supporting_chunk_id == str(c1)
    assert context.contradictions[0].contradicting_chunk_id == str(c2)


def test_fusion_no_contradiction_when_stances_agree():
    c1, c2, d1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    evidence = [_ev(c1, d1, "q1", "supporting"), _ev(c2, d1, "q1", "supporting")]
    context = build("obj", "s", evidence, [], {"q1": 2}, min_evidence_per_query=2)
    assert context.contradictions == []


def test_fusion_detects_gaps_when_a_query_underdelivers():
    context = build("obj", "s", [], [], {"q1": 1, "q2": 3}, min_evidence_per_query=2)
    assert [g.query for g in context.gaps] == ["q1"]
    assert context.gaps[0].evidence_count == 1
    assert context.gaps[0].minimum_required == 2


def test_fusion_handles_empty_evidence_without_crashing():
    context = build("obj", "s", [], [], {}, min_evidence_per_query=2)
    assert context.evidence == []
    assert context.timeline == []
    assert context.contradictions == []
    assert context.gaps == []
    assert context.claims == []  # Phase 4 placeholder


def test_fusion_trims_long_excerpts():
    c1, d1 = uuid.uuid4(), uuid.uuid4()
    long_excerpt = "x" * 900
    context = build(
        "obj", "s", [_ev(c1, d1, "q1", "supporting", excerpt=long_excerpt)], [],
        {"q1": 1}, min_evidence_per_query=1,
    )
    assert len(context.evidence[0].excerpt) == 500
