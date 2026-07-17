"""Phase 10: one full user journey driven through the HTTP layer (FastAPI
TestClient) with the fake adapter + fake embeddings — ingest, search, run an
investigation, replay it, refresh on new evidence, check metrics, render the
UI, and run an eval in-process. No live LLM/network calls anywhere."""

import re
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient

from argus.agentruntime import evidence as collector
from argus.agentruntime.schemas import (
    DraftReport,
    ExecutionRecord,
    ResearchPlan,
    Stance,
    StanceResult,
)
from argus.evals import runner as eval_runner
from argus.investigations.orchestrator import MARKER_RE
from argus.main import app
from tests.conftest import drain_queue, ingest_html, requires_db

pytestmark = [requires_db, pytest.mark.usefixtures("fake_embeddings", "seeded_companies")]


@pytest.fixture(autouse=True)
def _no_dedup_collapse(monkeypatch):
    """This module's `corpus` fixture deliberately shares a huge boilerplate block
    (FILLER) across a supporting/contradicting document pair, to exercise stance
    classification — not dedup. FakeProvider's crude bag-of-words embeddings score
    that shared boilerplate similar enough to trip near-dup dedup (PRD-V2 2.4) and
    collapse the pair the journey depends on; real embeddings wouldn't conflate
    "growing" and "decelerating" this way. Dedup itself has dedicated unit tests
    in tests/test_agentruntime.py."""
    from argus.core.config import get_settings

    monkeypatch.setattr(get_settings(), "dedup_cosine_threshold", 1.1)

FILLER = "Quarterly commentary follows. " + "filler " * 40


def _fake_adapter(monkeypatch):
    """Canned planner/stance/draft responses tailored to this module's corpus: the
    supporting doc carries a GROWTHSIGNAL token, the contradicting doc a
    DECLINESIGNAL token, so stance classification is deterministic."""

    def fake_run_structured(operation, instruction, message, schema):
        record = ExecutionRecord(
            operation=operation, model="fake-model", prompt=message[:200], response_text="r",
            started_at=datetime.now(UTC), duration_ms=1,
        )
        if schema is ResearchPlan:
            return ResearchPlan(
                companies=["NVIDIA CORP"], doc_types=["news"],
                queries=["data center revenue GPU demand hyperscalers"], rationale="canned",
            ), record
        if schema is collector.StanceBatch:
            excerpts = re.findall(r"^\[\d+\](.*)$", message, re.M)
            results = []
            for text in excerpts:
                if "GROWTHSIGNAL" in text:
                    results.append(StanceResult(stance=Stance.SUPPORTING, rationale="canned"))
                elif "DECLINESIGNAL" in text:
                    results.append(StanceResult(stance=Stance.CONTRADICTING, rationale="canned"))
                else:
                    results.append(StanceResult(stance=Stance.UNKNOWN, rationale="canned"))
            return collector.StanceBatch(results=results), record
        if schema is DraftReport:
            supporting = re.search(
                r"\[chunk:([0-9a-f-]{36})\] stance=supporting", message
            ).group(1)
            contradicting = re.search(
                r"\[chunk:([0-9a-f-]{36})\] stance=contradicting", message
            ).group(1)
            narrative = (
                f"Data center revenue growth is strong [chunk:{supporting}]. "
                f"Competitive pressure is a real risk [chunk:{contradicting}]."
            )
            return DraftReport(
                executive_summary="Mixed signals on data center growth.",
                key_findings=["Revenue growth accelerating per one source"],
                risks=["Slowdown flagged by a contradicting source"],
                follow_up_questions=["Which trend dominates next quarter?"],
                narrative=narrative,
            ), record
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr("argus.agentruntime.adapter.run_structured", fake_run_structured)


_docs: dict | None = None


@pytest.fixture
def corpus():
    """One module-level corpus: a supporting doc and a contradicting doc for the
    same fake company (ZZZT), plus a topically unrelated doc — ingested once and
    reused by every test in this module (per-test copies would pollute ranking)."""
    global _docs
    if _docs is None:
        _docs = {
            "supporting": ingest_html(
                f"<html><body><p>NVIDIA CORP data center revenue grew sharply this "
                f"quarter, GROWTHSIGNAL as GPU demand from hyperscalers accelerated. "
                f"{FILLER}</p></body></html>",
                published_at=datetime(2026, 6, 1, tzinfo=UTC), doc_type="news",
            ),
            "contradicting": ingest_html(
                f"<html><body><p>NVIDIA CORP data center revenue growth is "
                f"decelerating, DECLINESIGNAL as hyperscalers pause GPU capital "
                f"spending. {FILLER}</p></body></html>",
                published_at=datetime(2026, 6, 2, tzinfo=UTC), doc_type="news",
            ),
            "unrelated": ingest_html(
                f"<html><body><p>Apple Inc. unveiled a new smartwatch band color "
                f"option this week. {FILLER}</p></body></html>",
                published_at=datetime(2026, 6, 1, tzinfo=UTC), doc_type="news",
            ),
        }
        drain_queue()
    return _docs


@pytest.fixture
def client():
    return TestClient(app)


# --- 1: ingest -> searchable ---


def test_search_finds_relevant_doc_with_scores_and_strategy(client, corpus):
    results = client.get(
        "/api/search", params={"q": "GROWTHSIGNAL data center revenue hyperscalers"}
    ).json()
    assert results
    # GROWTHSIGNAL is unique to the supporting doc: it must win both the lexical
    # and semantic signal and rank first, ahead of the contradicting/unrelated docs.
    top = results[0]
    assert top["document_id"] == str(corpus["supporting"])
    assert top["scores"] and top["strategy"] == "hybrid-rrf/v2"


# --- 2: investigation lifecycle via API ---


@pytest.fixture
def investigation(client, monkeypatch, corpus):
    _fake_adapter(monkeypatch)
    created = client.post(
        "/api/investigations",
        json={"question": "How is the data center business trending?", "hypothesis": "growing"},
    )
    assert created.status_code == 201
    return created.json()


def test_investigation_lifecycle_evidence_and_report(client, investigation):
    inv_id = investigation["id"]
    assert investigation["status"] == "complete"
    assert investigation["confidence"] is not None
    assert investigation["confidence_breakdown"]["components"]

    evidence = client.get(f"/api/investigations/{inv_id}/evidence").json()
    stances = {e["stance"] for e in evidence}
    assert {"supporting", "contradicting"} <= stances
    chunk_ids = {e["chunk_id"] for e in evidence}

    report = client.get(f"/api/investigations/{inv_id}/report").json()
    cited = set(MARKER_RE.findall(report["narrative"]))
    assert cited and cited <= chunk_ids  # every citation resolves to a real evidence chunk


# --- 3: replay ---


def test_replay_reproduces_recorded_retrieval(client, investigation):
    inv_id = investigation["id"]
    result = client.post(f"/api/investigations/{inv_id}/replay").json()
    assert result["match"] is True
    assert result["tasks"]
    assert all(t["recorded"] == t["replayed"] for t in result["tasks"])


# --- 4: refresh + staleness (ADR-0007: staleness computed on read, cleared by refresh) ---


def test_refresh_and_staleness(client, monkeypatch, corpus):
    _fake_adapter(monkeypatch)
    created = client.post(
        "/api/investigations",
        json={"question": "Staleness check: how is the data center business?"},
    ).json()
    inv_id = created["id"]
    assert created["new_evidence_available"] is False

    ingest_html(
        f"<html><body><p>NVIDIA CORP announced a new data center accelerator "
        f"roadmap, GROWTHSIGNAL for the coming year. {FILLER}</p></body></html>",
        published_at=datetime(2026, 6, 20, tzinfo=UTC), doc_type="news",
    )
    drain_queue()

    stale_view = client.get(f"/api/investigations/{inv_id}").json()
    assert stale_view["new_evidence_available"] is True

    refreshed = client.post(f"/api/investigations/{inv_id}/refresh").json()
    assert refreshed["status"] == "complete"
    assert refreshed["version"] == 2
    assert refreshed["new_evidence_available"] is False


# --- 5: metrics ---


def test_metrics_pipeline_shows_stage_runs(client, corpus):
    metrics = client.get("/api/metrics/pipeline").json()
    stages = {s["stage"] for s in metrics["stages_24h"]}
    assert "embed" in stages  # every ingested doc in this journey passed through embed
    assert "queue_depth" in metrics


# --- 6: UI smoke ---


def test_ui_pages_render(client, investigation):
    # The UI is a client-rendered SPA: every non-API path serves the same shell,
    # so the only server-side assertion left is that the shell is reachable.
    for path in ("/", f"/investigations/{investigation['id']}", "/pipeline"):
        assert client.get(path).status_code == 200


# --- 7: eval integration ---


def test_eval_retrieval_in_process_hits_and_records(corpus):
    from argus.core.db import session_scope

    golden = {
        "version": 1,
        "questions": [{
            "id": "e2e-growth",
            "question": "GROWTHSIGNAL data center revenue hyperscalers",
            "expected": [{"ticker": "ZZZT"}],
        }],
    }
    with session_scope() as session:
        metrics = eval_runner.eval_retrieval(session, golden, k=5)
        assert metrics["questions"] == 1
        assert metrics["per_question"][0]["hit"] is True

        run = eval_runner.record_run(session, "retrieval", metrics, 1, "hybrid-rrf/v1")
        assert run.id is not None
        assert run.metrics["hit_rate_at_k"] == 1.0
