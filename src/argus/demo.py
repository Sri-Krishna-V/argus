"""Demo seeding (ADR-0014): a public, reviewable investigation set built on top of
whatever corpus the connectors have ingested, driven through the same code the UI
calls — the API route functions, the engine, the lifecycle machine, the jobs outbox.

Nothing here writes a report, a stance or a confidence score by hand: every artifact
a visitor sees is real output of the real machinery over a real corpus, with only the
LLM replaced by the deterministic canned runtime (ARGUS_LLM_PROVIDER=demo).

    argus ingest company_profiles && argus ingest sec_edgar && argus ingest rss
    argus demo seed
"""

import logging
import uuid
from pathlib import Path

from sqlalchemy import delete, func, select, text
from sqlalchemy.orm import Session

from argus.api import routes
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.models import Job
from argus.evals.runner import load_golden
from argus.investigations import engine, lifecycle, orchestrator
from argus.investigations.models import Evidence, Investigation, Report
from argus.knowledge.models import Chunk, Document

log = logging.getLogger(__name__)

GOLDEN_PATH = Path("evals/golden.json")

# a real-but-uncovered issuer: the plan resolves it, retrieval finds nothing, and
# synthesis refuses to draft — the "no evidence, no report" rule (ADR-0005) visible
# as a genuinely failed investigation rather than a hand-set status
UNCOVERED_QUESTION = "What supply chain risks does Ford disclose in its latest filings?"

BRANCH_QUESTION = "Has Apple's China concentration changed since the most recent filing?"

# poison jobs for the ops dashboard. Both stages are idempotent on
# (document_id, stage, pipeline_version), so the Retry button genuinely re-runs the
# stage and the job clears — the failure is demo data, the recovery path is real.
DEAD_JOBS = [
    ("embed", "TimeoutError: embedding provider timed out after 30s"),
    ("build_graph", "OperationalError: deadlock detected on graph_edges upsert"),
]

ANNOTATIONS = [
    "Fulfilment-network language is unchanged from the prior filing — worth diffing.",
    "Ask whether the cost commentary here is seasonal before treating it as a trend.",
]


# investigation_events carries the append-only trigger (BEFORE UPDATE OR DELETE), so
# a row-by-row wipe is rejected by design — correctly: nothing in the application may
# rewrite history. TRUNCATE is the operator-level escape hatch instead: unreachable
# from the API, gated behind a CLI confirmation, and only ever aimed at a demo
# instance. Tables are listed rather than CASCADE'd so a future table referencing
# investigations fails loudly here instead of being silently emptied.
_DEMO_TABLES = (
    "annotations", "investigation_events", "investigation_tasks", "reports",
    "evidence", "hypotheses", "investigation_links", "investigations",
)


def reset_investigations() -> int:
    """Drop every investigation and its derived rows, plus the outbox entries that
    belong to them. Documents, chunks and the raw store are never touched — the
    corpus is expensive to rebuild and immutable by design."""
    with session_scope() as session:
        removed = session.scalar(select(func.count()).select_from(Investigation))
        session.execute(text(f"TRUNCATE {', '.join(_DEMO_TABLES)}"))
        # only this seeder's outbox rows: a genuine dead-lettered pipeline job is
        # recoverable work (`argus retry-dead`) and its failure record, not demo litter
        session.execute(
            delete(Job).where(
                (Job.job_type == orchestrator.JOB_TYPE)
                | (Job.payload["demo"].as_boolean().is_(True))
            )
        )
    return removed or 0


def _run(question: str) -> uuid.UUID:
    """Create + run, exactly as POST /api/investigations does (synchronously)."""
    created = routes.create_investigation(routes.CreateInvestigation(question=question))
    return uuid.UUID(str(created["id"]))


def _dag_only(question: str) -> uuid.UUID:
    """Plan and compile the DAG, then leave the investigation `running` with its
    tasks pending — the mid-flight shape. The outbox rows compile_dag enqueued are
    dropped so the live worker doesn't finish these off a second later; jobs are a
    disposable projection of events (ADR-0003), so deleting them is safe."""
    from argus.agentruntime import evidence as collector
    from argus.agentruntime import planner

    with session_scope() as session:
        inv = engine.create(session, question)
        plan, record = planner.plan(question)
        company_ids = collector.resolve_companies(session, plan.companies)
        inv.plan = plan.model_dump(mode="json")
        inv.company_ids = [str(c) for c in company_ids]
        engine._emit(session, inv.id, "agent.plan", {
            "plan": inv.plan, "company_ids": inv.company_ids,
            "record": record.model_dump(mode="json"),
        })
        orchestrator.compile_dag(session, inv, plan, company_ids)
        session.flush()
        session.execute(
            delete(Job).where(
                Job.job_type == orchestrator.JOB_TYPE, Job.document_id == inv.id
            )
        )
        lifecycle.transition(session, inv, "running")
        return inv.id


def _review_and_annotate(investigation_id: uuid.UUID) -> dict:
    """Analyst collaboration through the same endpoints the API exposes: two
    approvals, one rejection, two annotations. Rejected evidence is excluded from
    the next synthesis (orchestrator.synthesize), so these are load-bearing."""
    with session_scope() as session:
        evidence_ids = session.scalars(
            select(Evidence.id)
            .where(Evidence.investigation_id == investigation_id)
            .order_by(Evidence.id)
            .limit(3)
        ).all()
    reviews = ["approved", "approved", "rejected"]
    for evidence_id, review in zip(evidence_ids, reviews, strict=False):
        routes.review_evidence(
            investigation_id, evidence_id, routes.ReviewEvidence(review=review)
        )
    for body in ANNOTATIONS:
        routes.create_annotation(
            investigation_id,
            routes.CreateAnnotation(target={"kind": "investigation"}, body=body),
        )
    return {"reviewed": len(evidence_ids), "annotated": len(ANNOTATIONS)}


def _seed_dead_jobs(session: Session) -> list[int]:
    documents = session.scalars(
        select(Document)
        .where(Document.status == "enriched")
        .order_by(Document.ingested_at)
        .limit(len(DEAD_JOBS))
    ).all()
    version = get_settings().pipeline_version
    jobs = [
        Job(
            job_type=stage, document_id=document.id,
            payload={"pipeline_version": version, "demo": True},
            status="dead", attempts=3, max_attempts=3, last_error=error,
        )
        for document, (stage, error) in zip(documents, DEAD_JOBS, strict=False)
    ]
    session.add_all(jobs)
    session.flush()
    return [job.id for job in jobs]


def seed(*, reset: bool = False, golden_path: Path = GOLDEN_PATH) -> dict:
    """Build the demo set. Returns a summary for the CLI to print."""
    # this process drains its own investigation jobs in-process (engine.execute ->
    # orchestrator.drain), so it is a composition root and must install the task
    # handler exactly like argus.cli's worker and argus.main do
    orchestrator.register()
    settings = get_settings()
    if settings.llm_provider != "demo" and not settings.openrouter_api_key:
        raise RuntimeError(
            "no agent runtime configured: set ARGUS_LLM_PROVIDER=demo (canned, free) "
            "or ARGUS_OPENROUTER_API_KEY (live)"
        )

    with session_scope() as session:
        chunks = session.scalar(select(func.count()).select_from(Chunk))
        existing = session.scalar(select(func.count()).select_from(Investigation))
    if not chunks:
        raise RuntimeError(
            "corpus is empty (0 chunks). Run `argus ingest company_profiles`, then "
            "`argus ingest sec_edgar`, then `argus ingest rss`, and let the worker "
            "drain the queue before seeding"
        )
    if existing and not reset:
        raise RuntimeError(
            f"{existing} investigations already exist — pass --reset to rebuild the demo set"
        )
    if reset:
        log.info("demo reset", extra={"context": {"removed": reset_investigations()}})

    questions = {q["id"]: q["question"] for q in load_golden(golden_path)["questions"]}
    completed = [
        _run(questions[qid])
        for qid in (
            "aapl-china-exposure", "msft-cloud-risk", "nvda-export-controls",
            "googl-antitrust-risk", "chipmakers-ai-demand",
        )
    ]

    # human collaboration on a completed investigation
    collaboration_id = _run(questions["amzn-logistics-risk"])
    collaboration = _review_and_annotate(collaboration_id)

    # a second version: refresh re-collects on the stored plan and appends report v2
    refreshed_id = _run(questions["meta-quarterly-results"])
    routes.refresh_investigation(refreshed_id)

    # remaining lifecycle states, each through the real transition
    archived_id = _run(questions["aapl-quarterly-results"])
    routes.archive_investigation(archived_id)

    paused_id = _dag_only(questions["tsm-quarterly-results"])
    routes.pause_investigation(paused_id)

    cancelled_id = _dag_only(questions["avgo-8k-event"])
    routes.cancel_investigation(cancelled_id)

    running_id = _dag_only(questions["nvda-8k-event"])

    with session_scope() as session:
        created_id = engine.create(session, questions["big-tech-antitrust"]).id

    failed_id = _run(UNCOVERED_QUESTION)

    # branch + link the graph together
    branch = routes.branch_investigation(
        completed[0], routes.BranchInvestigation(question=BRANCH_QUESTION)
    )
    with session_scope() as session:
        routes.link_investigations(
            completed[2],
            routes.CreateLink(dst_investigation_id=completed[4], link_type="relates_to"),
            session,
        )
        dead_job_ids = _seed_dead_jobs(session)
        statuses = dict(
            session.execute(
                select(Investigation.status, func.count()).group_by(Investigation.status)
            ).all()
        )
        reports = session.scalar(select(func.count()).select_from(Report))
        evidence = session.scalar(select(func.count()).select_from(Evidence))

    return {
        "statuses": statuses,
        "reports": reports,
        "evidence": evidence,
        "dead_jobs": dead_job_ids,
        "collaboration": collaboration,
        "ids": {
            "completed": [str(i) for i in completed],
            "collaboration": str(collaboration_id),
            "refreshed": str(refreshed_id),
            "archived": str(archived_id),
            "paused": str(paused_id),
            "cancelled": str(cancelled_id),
            "running": str(running_id),
            "created": str(created_id),
            "failed": str(failed_id),
            "branch": str(branch["id"]),
        },
    }
