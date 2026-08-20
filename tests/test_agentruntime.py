"""Phase 6: agent runtime with the adapter boundary faked — no live LLM calls.
Evidence assembly runs against a real seeded Postgres corpus (like test_research);
planner/drafter tests check prompt construction and the schemas contract."""

import os
import re
import uuid
from datetime import UTC, datetime

import pytest

from argus.agentruntime import adapter, drafter, evidence, planner
from argus.agentruntime.schemas import (
    DraftReport,
    ExecutionRecord,
    ResearchPlan,
    Stance,
    StanceResult,
)
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.research.citations import resolve
from tests.conftest import drain_queue, ingest_html, requires_db

FILLER = "Quarterly commentary follows. " + "filler " * 40


def _record(operation: str) -> ExecutionRecord:
    return ExecutionRecord(
        operation=operation,
        model="fake-model",
        prompt="p",
        response_text="r",
        started_at=datetime.now(UTC),
        duration_ms=1,
    )


@pytest.fixture
def fake_adapter(monkeypatch):
    """Replace the single AI entry point; canned output per schema, calls captured."""
    calls = []

    def fake_run_structured(operation, instruction, message, schema):
        calls.append({"operation": operation, "message": message, "schema": schema})
        if schema is ResearchPlan:
            result = ResearchPlan(
                companies=["NVIDIA CORP"],
                doc_types=["news"],
                queries=["data center GPU revenue"],
                rationale="canned",
            )
        elif schema is evidence.StanceBatch:
            n = len(re.findall(r"^\[\d+\]", message, re.M))
            result = evidence.StanceBatch(
                results=[StanceResult(stance=Stance.SUPPORTING, rationale="canned")] * n
            )
        elif schema is DraftReport:
            result = DraftReport(
                executive_summary="s",
                key_findings=["f"],
                risks=[],
                follow_up_questions=[],
                narrative="Growth is strong [chunk:00000000-0000-0000-0000-000000000000].",
            )
        else:
            raise AssertionError(f"unexpected schema {schema}")
        return result, _record(operation)

    monkeypatch.setattr("argus.agentruntime.adapter.run_structured", fake_run_structured)
    return calls


def test_planner_returns_plan_and_record(fake_adapter):
    plan, record = planner.plan("How is NVIDIA's data center business doing?")
    assert plan.queries and plan.companies == ["NVIDIA CORP"]
    assert record.operation == "plan"
    assert "NVIDIA" in fake_adapter[0]["message"]


def test_drafter_prompt_carries_markers_and_rejects_empty(fake_adapter):
    from argus.research.fusion import InvestigationContext

    chunk_id = uuid.uuid4()
    context = InvestigationContext(
        objective="assess growth",
        plan_summary="canned",
        evidence=[{
            "chunk_id": str(chunk_id), "excerpt": "data center revenue grew",
            "stance": "supporting", "query": "q", "source_rank": 0.5,
            "document_id": str(uuid.uuid4()), "document_source": "news",
        }],
    )
    report, record = drafter.draft("question?", context)
    assert f"[chunk:{chunk_id}]" in fake_adapter[0]["message"]
    assert record.operation == "draft_report"
    assert "[chunk:" in report.narrative
    # evidence is fenced and the instruction warns against treating it as commands
    assert fake_adapter[0]["message"].count("---") == 2
    assert "never treat" in drafter.INSTRUCTION.lower()

    with pytest.raises(ValueError, match="without evidence"):
        drafter.draft("question?", InvestigationContext(objective="x", plan_summary=""))


class _LiteLlmCaptured(Exception):
    """Sentinel raised by the fake LiteLlm to abort before any live call."""


def test_adapter_constructs_litellm_with_timeout_and_bounded_retries(monkeypatch):
    captured = {}

    def fake_lite_llm(**kwargs):
        captured.update(kwargs)
        raise _LiteLlmCaptured

    # pin the live provider: ARGUS_LLM_PROVIDER=demo would serve this call from the
    # canned runtime and never construct LiteLlm at all (ADR-0014)
    monkeypatch.setattr(get_settings(), "llm_provider", "openrouter")
    monkeypatch.setattr("argus.agentruntime.adapter.LiteLlm", fake_lite_llm)
    with pytest.raises(_LiteLlmCaptured):
        adapter.run_structured("op", "instr", "msg", ResearchPlan)

    assert captured["timeout"] == get_settings().llm_timeout_seconds
    assert captured["num_retries"] == 2


@requires_db
@pytest.mark.usefixtures("fake_embeddings")
def test_collect_builds_cited_evidence(fake_adapter, seeded_companies):
    ingest_html(
        f"<html><body><p>NVIDIA CORP data center revenue grew 400 percent on "
        f"accelerating GPU demand from hyperscalers. {FILLER}</p></body></html>",
        published_at=datetime(2026, 6, 1, tzinfo=UTC),
        doc_type="news",
    )
    drain_queue()

    plan = ResearchPlan(
        companies=["NVIDIA CORP"],
        doc_types=["news"],
        queries=["data center GPU revenue growth"],
        rationale="test",
    )
    with session_scope() as session:
        collected, records = evidence.collect(session, "How is the DC business?", plan, k=5)
        assert collected and records
        assert all(e.stance == Stance.SUPPORTING and e.rationale for e in collected)
        assert all(e.query == "data center GPU revenue growth" for e in collected)
        assert all(e.strategy == "hybrid-rrf/v2" for e in collected)
        # every chunk reference resolves — citable by construction (ADR-0005)
        citations = resolve(session, [e.chunk_id for e in collected])
        assert len(citations) == len(collected)
        # excerpts are fenced and numbered [n]; instruction warns against injection
        stance_call = next(c for c in fake_adapter if c["schema"] is evidence.StanceBatch)
        assert "[1]" in stance_call["message"] and "---" in stance_call["message"]
        assert "never treat" in evidence.INSTRUCTION.lower()


@requires_db
@pytest.mark.usefixtures("fake_embeddings")
def test_collect_raises_on_stance_count_mismatch(monkeypatch, seeded_companies):
    ingest_html(
        f"<html><body><p>Apple Inc. iPhone shipments slowed in China amid "
        f"competition from domestic handset makers. {FILLER}</p></body></html>",
        published_at=datetime(2026, 5, 1, tzinfo=UTC),
        doc_type="news",
    )
    drain_queue()

    def bad_run_structured(operation, instruction, message, schema):
        return evidence.StanceBatch(results=[]), _record(operation)

    monkeypatch.setattr("argus.agentruntime.adapter.run_structured", bad_run_structured)
    plan = ResearchPlan(
        companies=["Apple Inc."], doc_types=["news"], queries=["iPhone China"], rationale="t"
    )
    with session_scope() as session, pytest.raises(ValueError, match="stance batch"):
        evidence.collect(session, "q?", plan, k=5)


def test_collect_processes_queries_in_priority_order(monkeypatch):
    """PRD-V2 2.1: higher-priority queries collect first. Pure — patches
    collect_query to record call order instead of hitting the DB/LLM."""
    seen_order = []

    def fake_collect_query(session, question, query, company_ids, doc_types, k, seen=None):
        seen_order.append(query)
        return [], [], 0

    monkeypatch.setattr(evidence, "collect_query", fake_collect_query)
    plan = ResearchPlan(
        companies=[], doc_types=[],
        queries=[
            {"query": "low", "priority": 0},
            {"query": "high", "priority": 5},
            {"query": "mid", "priority": 2},
            {"query": "tie-a", "priority": 2},
        ],
        rationale="t",
    )
    evidence.collect(None, "q?", plan, k=5, company_ids=[])
    assert seen_order == ["high", "mid", "tie-a", "low"]  # stable sort keeps ties in plan order


def _hit(chunk_id, document_id, text, rrf):
    from argus.research.retrieval import RetrievalResult

    return RetrievalResult(
        chunk_id=chunk_id, document_id=document_id, text=text, title=None, url=None,
        source="s", doc_type="news", published_at=None, scores={"rrf": rrf},
    )


def test_dedup_threshold_boundary_just_below_and_above():
    """PRD-V2 2.4: cosine similarity right at ARGUS_DEDUP_COSINE_THRESHOLD (0.97
    default) — just below keeps both chunks, just above merges them."""
    import math

    from argus.agentruntime.evidence import _dedup

    c1, c2, d1, d2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    hit1 = _hit(c1, d1, "alpha text one", rrf=0.9)
    hit2 = _hit(c2, d2, "beta text two", rrf=0.5)  # distinct text: no hash collision

    below = {c1: [1.0, 0.0], c2: [0.9699, math.sqrt(1 - 0.9699**2)]}
    kept, dropped, corroborated = _dedup([hit1, hit2], below, threshold=0.97)
    assert dropped == 0 and len(kept) == 2 and corroborated == {}

    above = {c1: [1.0, 0.0], c2: [0.9701, math.sqrt(1 - 0.9701**2)]}
    kept, dropped, corroborated = _dedup([hit1, hit2], above, threshold=0.97)
    assert dropped == 1 and kept == [hit1]  # higher-RRF instance kept


def test_dedup_keeps_provenance_and_corroboration_across_documents():
    """A dropped duplicate from a DIFFERENT document must not vanish silently —
    its document id survives in the kept row's corroborated_by, so source ranking
    (2.3) still counts it."""
    from argus.agentruntime.evidence import _dedup

    c1, c2, d1, d2 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    hit1 = _hit(c1, d1, "identical wording here", rrf=0.9)
    hit2 = _hit(c2, d2, "identical wording here", rrf=0.5)  # exact text match -> hash dup

    kept, dropped, corroborated = _dedup([hit1, hit2], {}, threshold=0.97)
    assert dropped == 1 and kept == [hit1]
    assert corroborated == {c1: [str(d2)]}


def test_dedup_same_document_duplicate_drops_without_corroboration_entry():
    """A duplicate chunk from the SAME document (e.g. overlapping chunk windows) is
    just noise, not corroboration — no corroborated_by entry for it."""
    from argus.agentruntime.evidence import _dedup

    c1, c2, d1 = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
    hit1 = _hit(c1, d1, "same doc text", rrf=0.9)
    hit2 = _hit(c2, d1, "same doc text", rrf=0.5)

    kept, dropped, corroborated = _dedup([hit1, hit2], {}, threshold=0.97)
    assert dropped == 1 and kept == [hit1] and corroborated == {}


@pytest.mark.skipif(
    not os.environ.get("ARGUS_OPENROUTER_API_KEY"), reason="no OpenRouter API key"
)
def test_adapter_live_smoke():
    from argus.agentruntime import adapter

    plan, record = adapter.run_structured(
        "plan", planner.INSTRUCTION, "How is NVIDIA's data center business?", ResearchPlan
    )
    assert plan.queries and record.model and record.duration_ms >= 0


def test_research_plan_upgrades_v1_string_queries():
    from argus.agentruntime.schemas import PlannedQuery, ResearchPlan

    plan = ResearchPlan.model_validate(
        {"companies": ["NVIDIA CORP"], "doc_types": ["news"],
         "queries": ["data center revenue", "automotive growth"], "rationale": "r"}
    )
    assert plan.investigation_type == "general"
    assert plan.queries == [
        PlannedQuery(query="data center revenue", objective=""),
        PlannedQuery(query="automotive growth", objective=""),
    ]


def test_research_plan_round_trips_typed_queries():
    from argus.agentruntime.schemas import ResearchPlan

    plan = ResearchPlan.model_validate(
        {"investigation_type": "earnings_analysis", "objective": "assess Q3",
         "companies": [], "doc_types": [],
         "queries": [{"query": "q3 margins", "objective": "margin trend"}],
         "rationale": "r"}
    )
    dumped = plan.model_dump(mode="json")
    assert ResearchPlan.model_validate(dumped) == plan
    assert dumped["queries"][0]["objective"] == "margin trend"


def test_research_plan_rejects_empty_query_text():
    import pytest

    from argus.agentruntime.schemas import ResearchPlan

    with pytest.raises(ValueError):
        ResearchPlan.model_validate(
            {"companies": [], "doc_types": [], "queries": [""], "rationale": "r"}
        )
