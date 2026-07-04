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
    CollectedEvidence,
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
    chunk_id = uuid.uuid4()
    ev = CollectedEvidence(
        chunk_id=chunk_id,
        document_id=uuid.uuid4(),
        excerpt="data center revenue grew",
        stance=Stance.SUPPORTING,
        rationale="says so",
        query="q",
        scores={},
        strategy="hybrid-rrf/v1",
    )
    report, record = drafter.draft("question?", [ev])
    assert f"[chunk:{chunk_id}]" in fake_adapter[0]["message"]
    assert record.operation == "draft_report"
    assert "[chunk:" in report.narrative
    # evidence is fenced and the instruction warns against treating it as commands
    assert fake_adapter[0]["message"].count("---") == 2
    assert "never treat" in drafter.INSTRUCTION.lower()

    with pytest.raises(ValueError, match="without evidence"):
        drafter.draft("question?", [])


class _LiteLlmCaptured(Exception):
    """Sentinel raised by the fake LiteLlm to abort before any live call."""


def test_adapter_constructs_litellm_with_timeout_and_bounded_retries(monkeypatch):
    captured = {}

    def fake_lite_llm(**kwargs):
        captured.update(kwargs)
        raise _LiteLlmCaptured

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
        assert all(e.strategy == "hybrid-rrf/v1" for e in collected)
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


@pytest.mark.skipif(
    not os.environ.get("ARGUS_OPENROUTER_API_KEY"), reason="no OpenRouter API key"
)
def test_adapter_live_smoke():
    from argus.agentruntime import adapter

    plan, record = adapter.run_structured(
        "plan", planner.INSTRUCTION, "How is NVIDIA's data center business?", ResearchPlan
    )
    assert plan.queries and record.model and record.duration_ms >= 0
