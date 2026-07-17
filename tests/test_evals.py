"""Phase 8: eval harness — golden-set retrieval scoring, investigation report-quality
scoring, and the CLI surface. Requires Postgres.

eval_investigation() scores across every Report row in the shared test DB, so the
"no reports yet" and "exactly one report" cases each clear the table themselves
first rather than relying on collection order relative to other modules."""

import json
import re
import uuid
from datetime import UTC, datetime

import pytest
import sqlalchemy as sa
from typer.testing import CliRunner

from argus.agentruntime import evidence as collector
from argus.agentruntime.schemas import (
    DraftReport,
    ExecutionRecord,
    ResearchPlan,
    Stance,
    StanceResult,
)
from argus.cli import app
from argus.core.db import session_scope
from argus.evals import runner
from argus.investigations import engine
from argus.investigations.models import Report
from argus.observability.models import EvalRun
from argus.research.retrieval import STRATEGY_VERSION, RetrievalResult
from tests.conftest import drain_queue, ingest_html, requires_db

pytestmark = [requires_db, pytest.mark.usefixtures("fake_embeddings", "seeded_companies")]

FILLER = "Quarterly commentary follows. " + "filler " * 40


# --- load_golden: pure, no DB ---


def test_load_golden_missing_expected_names_the_question(tmp_path):
    path = tmp_path / "golden.json"
    path.write_text(json.dumps({"version": 1, "questions": [{"id": "q1", "question": "x"}]}))
    with pytest.raises(ValueError, match="q1"):
        runner.load_golden(path)


def test_load_golden_invalid_json_raises_value_error(tmp_path):
    path = tmp_path / "golden.json"
    path.write_text("{not valid json")
    with pytest.raises(ValueError):
        runner.load_golden(path)


# --- eval_retrieval: seeded corpus, requires DB ---

_docs: dict | None = None


def _corpus():
    """Two topic-distinct, single-company documents ingested once per module."""
    global _docs
    if _docs is not None:
        return _docs
    docs = {
        "nvda_gpu": ingest_html(
            f"<html><body><p>NVIDIA CORP graphics processing unit shipments surged on "
            f"accelerating hyperscale datacenter buildouts. {FILLER}</p></body></html>",
            published_at=datetime(2026, 6, 1, tzinfo=UTC),
            doc_type="news",
        ),
        "aapl_wearables": ingest_html(
            f"<html><body><p>Apple Inc. wearables segment grew modestly amid soft "
            f"smartwatch demand this quarter. {FILLER}</p></body></html>",
            published_at=datetime(2026, 5, 1, tzinfo=UTC),
            doc_type="news",
        ),
    }
    drain_queue()
    _docs = docs
    return docs


def test_eval_retrieval_happy_path_ranks_relevant_doc_and_records_run(db_session):
    docs = _corpus()
    golden = {
        "version": 1,
        "questions": [{
            "id": "nvda-gpu",
            "question": "graphics processing unit shipments hyperscale datacenter buildouts",
            "expected": [{"ticker": "ZZZT"}],
        }],
    }
    metrics = runner.eval_retrieval(db_session, golden, k=5)
    assert metrics["questions"] == 1
    assert metrics["skipped"] == 0
    pq = metrics["per_question"][0]
    assert pq == {"id": "nvda-gpu", "rank": pq["rank"], "hit": True}
    assert pq["rank"] is not None and pq["rank"] <= 3
    assert metrics["hit_rate_at_3"] == 1.0
    assert metrics["hit_rate_at_k"] == 1.0
    assert metrics["mrr"] == pytest.approx(1 / pq["rank"])

    run = runner.record_run(db_session, "retrieval", metrics, golden["version"], STRATEGY_VERSION)
    assert run.id is not None
    assert run.strategy == STRATEGY_VERSION
    assert run.golden_version == 1
    fetched = db_session.get(EvalRun, run.id)
    assert fetched.metrics["hit_rate_at_3"] == 1.0
    assert docs["nvda_gpu"]  # sanity: fixture populated


def test_eval_retrieval_miss_is_none_rank_and_zero_mrr_contribution(db_session):
    _corpus()
    golden = {
        "version": 1,
        "questions": [{
            "id": "aapl-miss",
            "question": "graphics processing unit shipments hyperscale datacenter buildouts",
            "expected": [{"ticker": "ZZAP"}],  # Apple — irrelevant to this query
        }],
    }
    metrics = runner.eval_retrieval(db_session, golden, k=1)
    assert metrics["questions"] == 1
    assert metrics["skipped"] == 0
    pq = metrics["per_question"][0]
    assert pq["hit"] is False
    assert pq["rank"] is None
    assert metrics["mrr"] == 0.0
    assert metrics["hit_rate_at_3"] == 0.0


def test_eval_retrieval_skips_selector_with_no_documents(db_session):
    _corpus()
    golden = {
        "version": 1,
        "questions": [{
            "id": "ghost",
            "question": "irrelevant",
            "expected": [{"ticker": "NOSUCHTICKER"}],
        }],
    }
    metrics = runner.eval_retrieval(db_session, golden, k=5)
    assert metrics["questions"] == 0
    assert metrics["skipped"] == 1
    assert metrics["per_question"] == []
    assert metrics["hit_rate_at_3"] == 0.0
    assert metrics["mrr"] == 0.0


def test_eval_retrieval_ranks_unique_documents_not_chunks(monkeypatch, db_session):
    """Two chunks of one document ahead of the expected doc's single chunk must count
    as ONE document for ranking purposes: expected doc is the 2nd unique document, not
    the 3rd raw result."""
    docs = _corpus()
    expected_doc = docs["nvda_gpu"]
    other_doc = uuid.uuid4()

    def fake_search(session, query, k=10):
        return [
            RetrievalResult(
                chunk_id=uuid.uuid4(), document_id=other_doc, text="t", title=None,
                url=None, source="s", doc_type="news", published_at=None,
            ),
            RetrievalResult(
                chunk_id=uuid.uuid4(), document_id=other_doc, text="t", title=None,
                url=None, source="s", doc_type="news", published_at=None,
            ),
            RetrievalResult(
                chunk_id=uuid.uuid4(), document_id=expected_doc, text="t", title=None,
                url=None, source="s", doc_type="news", published_at=None,
            ),
        ]

    monkeypatch.setattr(runner, "search", fake_search)
    golden = {
        "version": 1,
        "questions": [{"id": "dedupe", "question": "irrelevant", "expected": [{"ticker": "ZZZT"}]}],
    }
    metrics = runner.eval_retrieval(db_session, golden, k=5)
    assert metrics["per_question"][0]["rank"] == 2


# --- CLI ---


def test_cli_retrieval_all_skipped_exits_1_and_records_nothing(tmp_path):
    _corpus()
    golden_path = tmp_path / "golden.json"
    golden_path.write_text(json.dumps({
        "version": 1,
        "questions": [{"id": "ghost", "question": "irrelevant", "expected": [{"ticker": "NOPE"}]}],
    }))
    with session_scope() as session:
        before = session.scalar(sa.select(sa.func.count()).select_from(EvalRun))

    result = CliRunner().invoke(app, ["eval", "retrieval", "--golden", str(golden_path)])
    assert result.exit_code == 1

    with session_scope() as session:
        after = session.scalar(sa.select(sa.func.count()).select_from(EvalRun))
    assert after == before


def test_cli_investigation_with_no_reports_exits_1_and_records_nothing():
    with session_scope() as session:
        session.execute(sa.delete(Report))  # other modules' investigations may have run first
        before_runs = session.scalar(sa.select(sa.func.count()).select_from(EvalRun))

    result = CliRunner().invoke(app, ["eval", "investigation"])
    assert result.exit_code == 1

    with session_scope() as session:
        after_runs = session.scalar(sa.select(sa.func.count()).select_from(EvalRun))
    assert after_runs == before_runs


# --- eval_investigation: fake-adapter investigation end to end ---


def _make_record(operation="op"):
    return ExecutionRecord(
        operation=operation, model="fake-model", prompt="p", response_text="r",
        started_at=datetime.now(UTC), duration_ms=1,
    )


def test_eval_investigation_matches_hand_computed_metrics(monkeypatch):
    # Three single-chunk documents so collect() gathers exactly three evidence rows.
    # doc_type="filing" keeps these isolated from _corpus()'s NVIDIA "news" document
    # (same company_id) so the retrieved evidence set is exactly these three.
    # They also share a huge FILLER boilerplate block on purpose (short, distinct
    # "angle" sentences otherwise); FakeProvider's bag-of-words embeddings would
    # otherwise score that shared boilerplate as a near-duplicate (PRD-V2 2.4) and
    # collapse the three-way stance split this test depends on. Disable dedup here;
    # it has its own unit tests in tests/test_agentruntime.py.
    from argus.core.config import get_settings

    monkeypatch.setattr(get_settings(), "dedup_cosine_threshold", 1.1)
    for angle in [
        "data center revenue accelerated sharply",
        "faces mounting competitive pricing pressure",
        "announced routine executive appointments",
    ]:
        ingest_html(
            f"<html><body><p>NVIDIA CORP {angle}. {FILLER}</p></body></html>",
            published_at=datetime(2026, 6, 1, tzinfo=UTC),
            doc_type="filing",
        )
    drain_queue()

    def fake_run_structured(operation, instruction, message, schema):
        record = _make_record(operation)
        if schema is ResearchPlan:
            return ResearchPlan(
                companies=["NVIDIA CORP"], doc_types=["filing"],
                queries=["NVIDIA CORP outlook"], rationale="canned",
            ), record
        if schema is collector.StanceBatch:
            n = len(re.findall(r"^\[\d+\]", message, re.M))
            stances = [Stance.SUPPORTING, Stance.CONTRADICTING, Stance.UNKNOWN]
            return collector.StanceBatch(
                results=[
                    StanceResult(stance=stances[i % 3], rationale="canned") for i in range(n)
                ]
            ), record
        if schema is DraftReport:
            supporting = re.search(r"\[chunk:([0-9a-f-]{36})\] stance=supporting", message).group(1)
            contradicting = re.search(
                r"\[chunk:([0-9a-f-]{36})\] stance=contradicting", message
            ).group(1)
            narrative = (
                f"Momentum looks strong [chunk:{supporting}]. Repeated for emphasis "
                f"[chunk:{supporting}]. Competitive pressure is a real risk "
                f"[chunk:{contradicting}]."
            )
            return DraftReport(
                executive_summary="s", key_findings=["f"], risks=["r"],
                follow_up_questions=["q"], narrative=narrative,
            ), record
        raise AssertionError(f"unexpected schema {schema}")

    monkeypatch.setattr("argus.agentruntime.adapter.run_structured", fake_run_structured)

    with session_scope() as session:
        session.execute(sa.delete(Report))  # isolate: score exactly this test's report
        inv_id = engine.create(session, "How is NVIDIA doing?").id
    with session_scope() as session:
        engine.run(session, inv_id)

    metrics = None
    with session_scope() as session:
        metrics = runner.eval_investigation(session)

    assert metrics["reports"] == 1
    pi = metrics["per_investigation"][0]
    assert pi["id"] == str(inv_id)
    assert pi["citation_count"] == 3  # 2 supporting markers + 1 contradicting marker
    assert pi["citation_coverage"] == pytest.approx(2 / 3)  # 2 distinct chunks / 3 evidence
    assert pi["has_both_stances"] is True
    assert metrics["mean_citation_coverage"] == pytest.approx(2 / 3)
    assert metrics["both_stances_fraction"] == 1.0
    assert metrics["mean_unknown_fraction"] == pytest.approx(1 / 3)

    with session_scope() as session:
        run = runner.record_run(
            session, "investigation", metrics, None, runner.INVESTIGATION_EVAL_VERSION
        )
        assert run.golden_version is None
        assert run.strategy == "report-eval/v1"
