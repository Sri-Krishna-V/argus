"""Demo mode (ADR-0014): the canned agent runtime and the demo seeder.

The canned runtime is what makes a public demo possible without an LLM key, so the
properties that matter are the ones the investigation engine relies on: exactly one
stance per excerpt, and citation markers that came out of the prompt rather than out
of thin air (the citation gate rejects anything else)."""

import uuid

import pytest
import sqlalchemy as sa

from argus.agentruntime import canned
from argus.agentruntime.evidence import StanceBatch
from argus.agentruntime.schemas import DraftReport, ResearchPlan, Stance
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.investigations import engine
from argus.investigations.models import Evidence, Investigation, InvestigationLink, Report
from argus.investigations.orchestrator import MARKER_RE
from tests.conftest import drain_queue, ingest_html, requires_db

FILING = """
Apple Inc. annual report risk factors. A significant concentration of our manufacturing
and assembly capacity is located in China, and substantially all of our hardware products
are manufactured by outsourcing partners located primarily in Asia. Regulatory action,
tariffs or export controls affecting that supply chain could materially affect gross
margins and product availability. We are working to diversify manufacturing across
additional regions, though that transition will take several years to complete.
Component shortages have previously delayed product launches and constrained channel
inventory during peak selling seasons. Our reliance on single-source suppliers for
custom silicon, display panels and radio-frequency components concentrates that risk
further, and qualifying an alternate supplier typically takes several quarters.
Foreign exchange movements in the currencies of our manufacturing partners can raise
input costs faster than we are able to reprice finished goods. Labour disputes, power
rationing and public-health restrictions at assembly sites have each interrupted
production in prior years. We maintain safety stock for critical components, but that
buffer is measured in weeks and would not absorb a prolonged regional disruption.
Our contractual commitments to suppliers are largely non-cancellable, so a demand
shortfall can leave us carrying inventory that must be written down.
"""

NEWS = """
Microsoft cloud revenue grew during the quarter as demand for data center capacity
outpaced supply, while management cautioned that capital expenditure would remain
elevated for several quarters. Analysts noted that antitrust scrutiny of large
technology platforms continues in both the United States and Europe. Export controls on
advanced chips remain a live risk for semiconductor suppliers to hyperscale operators.
Operating margin narrowed slightly as depreciation on newly built capacity began to
land in the cost line. Executives said commercial bookings growth was broad based
rather than concentrated in a handful of large contracts. Competitors are expanding
their own regional capacity, which could compress pricing on standard compute in the
next fiscal year. Currency headwinds reduced reported growth by roughly two points.
"""

CHIPS = """
Semiconductor suppliers to artificial intelligence data centers reported another
quarter of accelerating orders, with lead times for advanced packaging stretching past
a year. Export controls limiting sales of the highest-performance accelerators to
certain markets removed a portion of expected revenue, and management declined to
quantify the effect for coming quarters. Foundry partners are raising prices on leading
edge nodes, which pressures gross margin for fabless designers. Several customers have
begun designing in-house accelerators, a competitive risk that would reduce merchant
silicon demand over time. Inventory in the channel remains below normal levels, which
suggests the current order book reflects real end demand rather than stockpiling.
"""


# --- canned runtime (no DB) ---


def test_plan_names_the_watchlist_ticker_it_recognises():
    plan, record = canned.run_structured(
        "plan", "instr", "How exposed is Apple to China supply chain risk?", ResearchPlan
    )
    assert plan.companies == ["AAPL"]  # ticker, not a name — resolve_companies matches exactly
    assert plan.investigation_type == "risk_assessment"
    assert plan.doc_types == ["filing", "news"]
    assert 3 <= len(plan.queries) <= 5
    queries = [q.query for q in plan.queries]
    assert len(queries) == len(set(queries))  # one collect task per query; no duplicates
    assert record.model == canned.MODEL


def test_plan_falls_back_to_proper_nouns_for_unknown_issuers():
    plan, _ = canned.run_structured(
        "plan", "instr", "What supply chain risks does Ford disclose?", ResearchPlan
    )
    assert plan.companies == ["Ford"]


def test_stance_batch_returns_exactly_one_result_per_excerpt():
    # a stray bracketed number inside an excerpt must not be read as a new excerpt:
    # a miscount makes collect_query raise
    message = "Question: q\n\nExcerpts:\n---\n[1] first\n\n[2] second [9] inline\n\n[3] third\n---"
    batch, _ = canned.run_structured("classify_stance", "instr", message, StanceBatch)
    assert len(batch.results) == 3


def test_stance_buckets_cover_every_stance():
    stances = {canned._stance_for(f"excerpt number {i}") for i in range(40)}
    assert stances == {Stance.SUPPORTING, Stance.CONTRADICTING, Stance.UNKNOWN}
    # stable per text, so a replay classifies identically
    assert canned._stance_for("excerpt number 1") == canned._stance_for("excerpt number 1")


def test_draft_cites_only_markers_present_in_the_prompt():
    ids = [uuid.uuid4() for _ in range(3)]
    evidence = "\n\n".join(
        f"[chunk:{cid}] stance={stance}\nSome disclosure text for excerpt {i}."
        for i, (cid, stance) in enumerate(
            zip(ids, ["supporting", "contradicting", "unknown"], strict=True)
        )
    )
    message = f"Question: q\nObjective: o\n\nEvidence:\n---\n{evidence}\n---"
    draft, _ = canned.run_structured("draft_report", "instr", message, DraftReport)
    cited = {uuid.UUID(m) for m in MARKER_RE.findall(draft.narrative)}
    assert cited and cited <= set(ids)
    assert canned.DISCLOSURE in draft.narrative  # never passes canned prose off as analysis
    assert draft.risks and MARKER_RE.search(draft.risks[0])


def test_draft_headlines_prose_over_table_boilerplate():
    """Filing text is half cover-page tables; a report that quotes those as findings
    reads like a bug even though the citation is real."""
    prose, table = uuid.uuid4(), uuid.uuid4()
    evidence = (
        f"[chunk:{table}] stance=supporting\n"
        "— Nasdaq Stock Market LLC 3.450% Senior Notes due 2032 — 4.625% due 2032 —\n\n"
        f"[chunk:{prose}] stance=supporting\n"
        "Demand for cloud and AI services is difficult to forecast, and overestimating "
        "it could leave the company with excess capacity."
    )
    draft, _ = canned.run_structured(
        "draft_report", "instr", f"Question: q\nObjective: o\n\nEvidence:\n---\n{evidence}\n---",
        DraftReport,
    )
    assert str(prose) in draft.key_findings[0]


def test_prose_score_demotes_form_furniture():
    prose = "Demand for cloud and AI services is difficult to forecast this year."
    assert canned._prose_score(prose) > canned._prose_score(
        "REPORT OF MANAGEMENT ON INTERNAL CONTROL OVER FINANCIAL REPORTING"
    )
    assert canned._prose_score(prose) > canned._prose_score(
        "Emerging growth company \u2610 If an emerging growth company, indicate by check mark"
    )
    assert canned._prose_score(prose) > canned._prose_score(
        "— Nasdaq Stock Market LLC 3.450% Senior Notes due 2032 — 4.625% due 2032 —"
    )


def test_unknown_operation_is_rejected():
    with pytest.raises(ValueError, match="no response for operation"):
        canned.run_structured("summarise", "instr", "msg", DraftReport)


# --- end to end over a real corpus ---

pytestmark_db = pytest.mark.usefixtures("fake_embeddings", "seeded_companies")


@pytest.fixture
def demo_corpus(monkeypatch, db_session):
    """Three documents across two sources, so confidence has diversity to score and
    there is enough evidence for the seeder's review/annotation pass."""
    monkeypatch.setattr(get_settings(), "llm_provider", "demo")
    # FakeProvider's bag-of-words embeddings score unrelated filings as near-duplicates;
    # dedup has its own tests (tests/test_agentruntime.py)
    monkeypatch.setattr(get_settings(), "dedup_cosine_threshold", 1.1)
    ingest_html(FILING, source="sec_edgar", doc_type="filing", title="Apple 10-K")
    ingest_html(NEWS, source="rss", doc_type="news", title="Cloud demand roundup")
    ingest_html(CHIPS, source="rss", doc_type="news", title="AI chip demand check")
    drain_queue()


@requires_db
@pytestmark_db
def test_investigation_completes_on_the_canned_runtime(demo_corpus):
    with session_scope() as session:
        inv = engine.create(session, "How exposed is Apple to China supply chain risk?")
        inv_id = inv.id
    engine.execute(inv_id, "run")

    with session_scope() as session:
        inv = session.get(Investigation, inv_id)
        assert inv.status == "complete"
        report = session.scalar(sa.select(Report).where(Report.investigation_id == inv_id))
        assert report.model == canned.MODEL
        allowed = set(
            session.scalars(
                sa.select(Evidence.chunk_id).where(Evidence.investigation_id == inv_id)
            )
        )
        cited = {uuid.UUID(m) for m in MARKER_RE.findall(report.narrative)}
        assert cited and cited <= allowed  # the citation gate would have failed the run
        assert inv.confidence > 0
        assert set(inv.confidence_breakdown["components"]) == {
            "source_diversity", "document_count", "source_quality", "recency",
            "stance_agreement",
        }


@requires_db
@pytestmark_db
def test_seed_covers_every_lifecycle_state(demo_corpus, db_session):
    from argus import demo
    from argus.knowledge.models import Company

    # a resolvable issuer with no documents: the seeder's failed investigation depends
    # on retrieval genuinely finding nothing for it
    db_session.add(Company(name="Ford Motor Co", cik="9990009", tickers=["ZZFD"]))
    db_session.commit()
    demo.reset_investigations()  # earlier tests in this session commit investigations

    summary = demo.seed()

    assert set(summary["statuses"]) >= {
        "complete", "archived", "paused", "cancelled", "running", "created", "failed",
    }
    assert summary["reports"] >= 6
    assert summary["evidence"] > 0
    assert len(summary["dead_jobs"]) == 2
    assert summary["collaboration"] == {"reviewed": 3, "annotated": 2}

    with session_scope() as session:
        links = session.scalars(sa.select(InvestigationLink.link_type)).all()
        assert "branched_from" in links and "relates_to" in links
        reviews = session.scalars(
            sa.select(Evidence.review).where(Evidence.review.is_not(None))
        ).all()
        assert sorted(reviews) == ["approved", "approved", "rejected"]
        # every report the demo shows must be citable — this is what `make eval` scores
        narratives = session.scalars(sa.select(Report.narrative)).all()
        assert all(MARKER_RE.search(n) for n in narratives)

    # seeding twice would double the demo set
    with pytest.raises(RuntimeError, match="pass --reset"):
        demo.seed()
    assert demo.seed(reset=True)["reports"] >= 6


def test_seed_refuses_without_an_agent_runtime(monkeypatch):
    from argus import demo

    monkeypatch.setattr(get_settings(), "llm_provider", "openrouter")
    monkeypatch.setattr(get_settings(), "openrouter_api_key", "")
    with pytest.raises(RuntimeError, match="no agent runtime configured"):
        demo.seed()
