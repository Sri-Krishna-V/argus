"""Phase 7: investigation engine end-to-end with a faked adapter, deterministic
confidence edge cases, citation gate, replay, staleness, and the HTTP surface."""

import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa

from argus.agentruntime import evidence as collector
from argus.agentruntime.schemas import DraftReport, ResearchPlan, Stance, StanceResult
from argus.core.db import session_scope
from argus.investigations import confidence, engine
from argus.investigations.models import (
    Evidence,
    Investigation,
    InvestigationEvent,
    Report,
)
from argus.knowledge.models import Document
from tests.conftest import drain_queue, ingest_html, requires_db

FILLER = "Quarterly commentary follows. " + "filler " * 40

pytestmark = [requires_db, pytest.mark.usefixtures("fake_embeddings", "seeded_companies")]


# --- confidence: pure, no DB ---


def _doc(doc_type="news", source="rss", published_at=None, doc_id=None):
    return Document(
        id=doc_id or uuid.uuid4(), source=source, source_native_id="x", checksum="c",
        raw_path="p", doc_type=doc_type, published_at=published_at,
    )


def _ev(stance="supporting", document_id=None):
    return Evidence(
        investigation_id=uuid.uuid4(), chunk_id=uuid.uuid4(),
        document_id=document_id or uuid.uuid4(), stance=stance, rationale="r",
        query="q", excerpt="e", scores={}, strategy="s",
    )


def test_confidence_empty_evidence_is_zero():
    assert confidence.compute([], {}) == {"score": 0.0, "components": {}, "evidence_count": 0}


def test_confidence_breakdown_is_explainable_and_bounded():
    now = datetime.now(UTC)
    docs = {}
    evidence = []
    for i, (doc_type, source, stance) in enumerate([
        ("filing", "sec_edgar", "supporting"),
        ("news", "rss", "supporting"),
        ("news", "rss", "contradicting"),
    ]):
        d = _doc(doc_type, source, published_at=now - timedelta(days=30 * i))
        docs[d.id] = d
        evidence.append(_ev(stance, document_id=d.id))

    out = confidence.compute(evidence, docs, now=now)
    assert 0.0 < out["score"] <= 1.0
    assert set(out["components"]) == set(confidence.WEIGHTS)
    assert out["inputs"]["supporting"] == 2 and out["inputs"]["contradicting"] == 1
    assert out["components"]["stance_agreement"]["value"] == pytest.approx(2 / 3, abs=1e-4)
    # recompute from the breakdown itself: the score is auditable
    recomputed = sum(c["weight"] * c["value"] for c in out["components"].values())
    assert out["score"] == pytest.approx(recomputed, abs=1e-4)


def test_confidence_all_unknown_stances_is_neutral_not_agreeing():
    d = _doc()
    out = confidence.compute([_ev("unknown", document_id=d.id)], {d.id: d})
    assert out["components"]["stance_agreement"]["value"] == 0.5


def test_confidence_handles_missing_publish_dates_and_unknown_doc_types():
    d = _doc(doc_type="mystery", published_at=None)
    out = confidence.compute([_ev(document_id=d.id)], {d.id: d})
    assert out["components"]["recency"]["value"] == 0.0
    assert out["components"]["source_quality"]["value"] == 0.5


# --- engine with faked adapter ---


def _fake_adapter(monkeypatch, narrative_marker="valid"):
    """Planner/stance/draft canned responses. Draft cites a chunk actually present in
    the prompt ("valid"), an invented one ("invented"), or none ("none")."""

    def fake_run_structured(operation, instruction, message, schema):
        from argus.agentruntime.schemas import ExecutionRecord

        record = ExecutionRecord(
            operation=operation, model="fake-model", prompt=message[:200],
            response_text="r", started_at=datetime.now(UTC), duration_ms=1,
        )
        if schema is ResearchPlan:
            return ResearchPlan(
                companies=["NVIDIA CORP"], doc_types=["news"],
                queries=["automotive self-driving platform revenue"], rationale="canned",
            ), record
        if schema is collector.StanceBatch:
            n = len(re.findall(r"^\[\d+\]", message, re.M))
            return collector.StanceBatch(
                results=[StanceResult(stance=Stance.SUPPORTING, rationale="canned")] * n
            ), record
        if schema is DraftReport:
            if narrative_marker == "valid":
                chunk = re.search(r"\[chunk:([0-9a-f-]{36})\]", message).group(1)
                # hostile fragment: LLM output must render escaped in the UI
                narrative = f"<script>alert(1)</script> Growth is strong [chunk:{chunk}]."
            elif narrative_marker == "invented":
                narrative = f"Growth is strong [chunk:{uuid.uuid4()}]."
            else:
                narrative = "Growth is strong, trust me."
            return DraftReport(
                executive_summary="s", key_findings=["f"], risks=["r"],
                follow_up_questions=["q"], narrative=narrative,
            ), record
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr("argus.agentruntime.adapter.run_structured", fake_run_structured)


_corpus_doc = None


@pytest.fixture
def corpus():
    """One module-level document, topically distinct from other modules' fixtures —
    per-test copies would pollute their ranking assertions (shared test DB)."""
    global _corpus_doc
    if _corpus_doc is None:
        _corpus_doc = ingest_html(
            f"<html><body><p>NVIDIA CORP automotive segment revenue doubled on "
            f"self-driving platform adoption by carmakers. {FILLER}</p></body></html>",
            published_at=datetime(2026, 6, 1, tzinfo=UTC),
            doc_type="news",
        )
        drain_queue()
    return _corpus_doc


def test_run_produces_evidence_report_confidence_and_history(monkeypatch, corpus):
    _fake_adapter(monkeypatch)
    with session_scope() as session:
        inv = engine.create(session, "How is the DC business?", hypothesis="It is growing")
        inv_id = inv.id
    with session_scope() as session:
        engine.run(session, inv_id)

    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "complete"
        assert inv.confidence is not None and 0 < inv.confidence <= 1
        assert inv.confidence_breakdown["components"]
        assert inv.plan["queries"] and inv.company_ids

        rows = session.scalars(
            sa.select(Evidence).where(Evidence.investigation_id == inv_id)
        ).all()
        assert rows and all(r.stance == "supporting" for r in rows)

        report = session.scalar(sa.select(Report).where(Report.investigation_id == inv_id))
        assert report.model == "fake-model" and "[chunk:" in report.narrative

        event_types = [
            e.event_type for e in session.scalars(
                sa.select(InvestigationEvent)
                .where(InvestigationEvent.investigation_id == inv_id)
                .order_by(InvestigationEvent.id)
            )
        ]
        assert event_types == [
            "investigation.created", "agent.plan", "evidence.collected",
            "agent.draft", "investigation.completed",
        ]
        # replay record carries the prompts and retrieval params (Bible §13)
        collected = session.scalar(
            sa.select(InvestigationEvent).where(
                InvestigationEvent.investigation_id == inv_id,
                InvestigationEvent.event_type == "evidence.collected",
            )
        )
        assert collected.payload["chunk_ids"] and collected.payload["k"] > 0
        assert collected.payload["records"][0]["model"] == "fake-model"


def test_invented_citation_marker_fails_run_and_rolls_back(monkeypatch, corpus):
    _fake_adapter(monkeypatch, narrative_marker="invented")
    with session_scope() as session:
        inv_id = engine.create(session, "q?").id

    engine.execute(inv_id, "run")  # swallows the failure, persists it

    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "failed"
        failed = session.scalar(
            sa.select(InvestigationEvent).where(
                InvestigationEvent.investigation_id == inv_id,
                InvestigationEvent.event_type == "investigation.failed",
            )
        )
        assert "outside the evidence set" in failed.payload["error"]
        # partial writes rolled back: no evidence, no report survives a failed run
        assert not session.scalars(
            sa.select(Evidence).where(Evidence.investigation_id == inv_id)
        ).all()
        assert not session.scalars(
            sa.select(Report).where(Report.investigation_id == inv_id)
        ).all()


def test_narrative_without_markers_is_rejected(monkeypatch, corpus):
    _fake_adapter(monkeypatch, narrative_marker="none")
    with session_scope() as session:
        inv_id = engine.create(session, "q?").id
    with session_scope() as session, pytest.raises(ValueError, match="no citation markers"):
        engine.run(session, inv_id)


def test_plan_with_no_hits_fails_not_fabricates(monkeypatch, corpus):
    """No retrievable evidence must fail the run, never produce an evidence-free report."""
    _fake_adapter(monkeypatch)
    monkeypatch.setattr(
        "argus.agentruntime.planner.plan",
        lambda q: (
            ResearchPlan(companies=[], doc_types=[], queries=[], rationale="empty"),
            _make_record(),
        ),
    )
    with session_scope() as session:
        inv_id = engine.create(session, "q?").id
    with session_scope() as session, pytest.raises(ValueError, match="no evidence"):
        engine.run(session, inv_id)


def _make_record():
    from argus.agentruntime.schemas import ExecutionRecord

    return ExecutionRecord(
        operation="plan", model="fake-model", prompt="p", response_text="r",
        started_at=datetime.now(UTC), duration_ms=1,
    )


def test_refresh_requires_a_stored_plan(corpus):
    with session_scope() as session:
        inv_id = engine.create(session, "q?").id
    with session_scope() as session, pytest.raises(ValueError, match="no stored plan"):
        engine.refresh(session, inv_id)


def test_replay_reproduces_recorded_retrieval_set(monkeypatch, corpus):
    _fake_adapter(monkeypatch)
    with session_scope() as session:
        inv_id = engine.create(session, "How is the DC business?").id
    with session_scope() as session:
        engine.run(session, inv_id)
    with session_scope() as session:
        result = engine.replay_retrieval(session, inv_id)
        assert result["match"] is True
        assert result["recorded"]


def test_replay_without_history_raises(corpus):
    with session_scope() as session:
        inv_id = engine.create(session, "q?").id
        with pytest.raises(LookupError, match="no evidence.collected"):
            engine.replay_retrieval(session, inv_id)


def test_staleness_flips_on_new_document_and_clears_on_refresh(monkeypatch, corpus):
    _fake_adapter(monkeypatch)
    with session_scope() as session:
        inv_id = engine.create(session, "How is the DC business?").id
    with session_scope() as session:
        engine.run(session, inv_id)
    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert engine.has_new_evidence(session, inv) is False

    ingest_html(
        f"<html><body><p>NVIDIA CORP announced a new accelerator roadmap. "
        f"{FILLER}</p></body></html>",
        published_at=datetime(2026, 6, 20, tzinfo=UTC),
        doc_type="news",
    )
    drain_queue()

    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert engine.has_new_evidence(session, inv) is True

    engine.execute(inv_id, "refresh")
    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "complete" and inv.version == 2
        assert engine.has_new_evidence(session, inv) is False
        # refresh appended a v2 report; v1 history is preserved
        versions = session.scalars(
            sa.select(Report.version).where(Report.investigation_id == inv_id)
        ).all()
        assert sorted(versions) == [1, 2]


def test_never_run_investigation_is_not_stale(corpus):
    with session_scope() as session:
        inv = engine.create(session, "q?")
        assert engine.has_new_evidence(session, inv) is False


# --- HTTP surface ---


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from argus.main import app

    return TestClient(app)


def test_health_and_404s(client):
    assert client.get("/health").json() == {"status": "ok"}
    missing = uuid.uuid4()
    assert client.get(f"/api/investigations/{missing}").status_code == 404
    assert client.get(f"/api/documents/{missing}").status_code == 404
    assert client.get("/api/investigations/not-a-uuid").status_code == 422


def test_investigation_api_lifecycle(client, monkeypatch, corpus):
    _fake_adapter(monkeypatch)
    created = client.post(
        "/api/investigations",
        json={"question": "How is the DC business?", "hypothesis": "growing"},
    )
    assert created.status_code == 201
    body = created.json()
    assert body["status"] == "complete" and body["confidence"] is not None
    inv_id = body["id"]

    evidence = client.get(f"/api/investigations/{inv_id}/evidence").json()
    assert evidence and all(e["chunk_id"] for e in evidence)

    report = client.get(f"/api/investigations/{inv_id}/report").json()
    assert "[chunk:" in report["narrative"]

    replay = client.post(f"/api/investigations/{inv_id}/replay").json()
    assert replay["match"] is True

    metrics = client.get("/api/metrics/pipeline").json()
    assert "queue_depth" in metrics and "stages_24h" in metrics

    results = client.get("/api/search", params={"q": "data center GPU"}).json()
    assert results and results[0]["strategy"] == "hybrid-rrf/v1"


def test_pipeline_metrics_edge_cases(client):
    from argus.core import events
    from argus.core.models import Job
    from argus.observability.models import PipelineRun

    drain_queue()  # no claimable jobs should remain from earlier tests
    baseline = client.get("/api/metrics/pipeline").json()
    assert baseline["oldest_pending_seconds"] is None

    with session_scope() as session:
        events.enqueue(
            session, "reembed", run_after=datetime.now(UTC) - timedelta(seconds=30)
        )
        session.add(PipelineRun(stage="embed", status="failure", duration_ms=1, attempt=2))

    metrics = client.get("/api/metrics/pipeline").json()
    assert metrics["oldest_pending_seconds"] is not None
    assert metrics["oldest_pending_seconds"] > 0
    assert metrics["retries_24h"] == baseline["retries_24h"] + 1

    with session_scope() as session:
        session.execute(sa.delete(Job).where(Job.job_type == "reembed"))


def test_report_404_before_run(client, corpus):
    with session_scope() as session:
        inv_id = engine.create(session, "q?").id
    assert client.get(f"/api/investigations/{inv_id}/report").status_code == 404


def test_ui_pages_render(client, monkeypatch, corpus):
    _fake_adapter(monkeypatch)
    with session_scope() as session:
        inv_id = engine.create(session, "UI render check?").id
    with session_scope() as session:
        engine.run(session, inv_id)

    assert "Investigation workspace" in client.get("/").text
    detail = client.get(f"/investigations/{inv_id}").text
    assert "Executive summary" in detail and "Confidence" in detail
    assert "cite-1" in detail  # markers rendered as resolvable citation links
    # LLM narrative is untrusted: raw HTML must arrive escaped, never executable
    assert "<script>alert(1)</script>" not in detail
    assert "&lt;script&gt;" in detail
    assert client.get("/search", params={"q": "GPU demand"}).status_code == 200
    assert client.get("/pipeline").status_code == 200
