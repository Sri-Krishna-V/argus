"""Pipeline worker: claims outbox jobs with SKIP LOCKED, runs stages, records every
execution in pipeline_runs (Bible §8: no silent failures). Also ticks the connector
scheduler. Scale-out = run more worker processes; claiming is already safe."""

import logging
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from argus.core import events
from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.models import Job
from argus.dataplatform import pipeline
from argus.dataplatform.connectors.base import run_connector
from argus.dataplatform.connectors.profiles import CompanyProfilesConnector
from argus.dataplatform.connectors.rss import RssConnector
from argus.dataplatform.connectors.sec import SecEdgarConnector
from argus.observability.models import PipelineRun

log = logging.getLogger(__name__)


def claim_next(session: Session) -> Job | None:
    job = session.scalars(
        select(Job)
        .where(Job.status == "pending", Job.run_after <= datetime.now(UTC))
        .order_by(Job.id)
        .limit(1)
        .with_for_update(skip_locked=True)
    ).first()
    if job:
        job.status = "running"
        job.claimed_at = datetime.now(UTC)
        job.attempts += 1
    return job


def reap_stale(session: Session) -> int:
    """Re-queue jobs whose worker died mid-run (running past the lease).

    Safe because stages are idempotent on (document_id, stage, pipeline_version);
    attempts were already bumped at claim, so a crash-looping job still dies
    after max_attempts.
    """
    lease = timedelta(seconds=get_settings().job_lease_seconds)
    result = session.execute(
        update(Job)
        .where(Job.status == "running", Job.claimed_at < datetime.now(UTC) - lease)
        .values(status="pending", run_after=datetime.now(UTC))
        .returning(Job.id)
    )
    ids = result.scalars().all()
    if ids:
        log.info("reaped stale jobs", extra={"context": {"job_ids": ids}})
    return len(ids)


def _execute(session: Session, job: Job) -> None:
    if job.job_type in pipeline.STAGES:
        version = job.payload.get("pipeline_version", get_settings().pipeline_version)
        pipeline.run_stage(session, job.job_type, job.document_id, version)
    else:
        raise ValueError(f"unknown job type {job.job_type}")


def run_once() -> bool:
    """Claim and run one job. Returns False when the queue is empty."""
    with session_scope() as session:
        job = claim_next(session)
        if job is None:
            return False
        job_id, job_type, doc_id, attempt = job.id, job.job_type, job.document_id, job.attempts
        version = job.payload.get("pipeline_version", get_settings().pipeline_version)

    started = time.monotonic()
    error: str | None = None
    try:
        with session_scope() as session:
            job = session.get(Job, job_id)
            _execute(session, job)
            job.status = "completed"
            job.completed_at = datetime.now(UTC)
    except Exception as exc:  # noqa: BLE001 - the worker must survive any job failure
        error = f"{type(exc).__name__}: {exc}"
        log.exception("job failed", extra={"context": {"job_id": job_id, "type": job_type}})
        with session_scope() as session:
            job = session.get(Job, job_id)
            job.last_error = error
            if job.attempts >= job.max_attempts:
                job.status = "dead"
                events.emit(
                    session, "job.dead", aggregate_id=doc_id,
                    payload={"job_id": job_id, "type": job_type, "error": error},
                )
            else:
                job.status = "pending"
                job.run_after = events.retry_at(job.attempts)

    with session_scope() as session:
        session.add(
            PipelineRun(
                document_id=doc_id,
                stage=job_type,
                pipeline_version=version,
                status="failure" if error else "success",
                duration_ms=int((time.monotonic() - started) * 1000),
                attempt=attempt,
                error=error,
            )
        )
    return True


CONNECTORS = {
    "company_profiles": (CompanyProfilesConnector, "schedule_profiles"),
    "sec_edgar": (SecEdgarConnector, "schedule_sec"),
    "rss": (RssConnector, "schedule_rss"),
}


def make_connector(name: str, session: Session):
    cls = CONNECTORS[name][0]
    return cls(session) if name == "sec_edgar" else cls()


def run_connector_pass(name: str) -> dict:
    started = time.monotonic()
    error: str | None = None
    stats: dict = {}
    try:
        with session_scope() as session:
            stats = run_connector(session, make_connector(name, session))
    except Exception as exc:  # noqa: BLE001
        error = f"{type(exc).__name__}: {exc}"
        log.exception("connector failed", extra={"context": {"connector": name}})
    with session_scope() as session:
        session.add(
            PipelineRun(
                stage=f"connector.{name}",
                status="failure" if error else "success",
                duration_ms=int((time.monotonic() - started) * 1000),
                error=error,
            )
        )
    if not error:
        log.info("connector pass", extra={"context": {"connector": name, **stats}})
    return stats


def main_loop() -> None:  # pragma: no cover - long-running entry point
    """Poll jobs and tick connector schedules. Ctrl-C to stop."""
    settings = get_settings()
    # ponytail: in-memory schedule; a restart re-runs connectors early, which dedupe
    # makes harmless. profiles runs first so entity resolution has canonical targets.
    last_run = dict.fromkeys(CONNECTORS, 0.0)
    log.info("worker started")
    while True:
        for name, (_, interval_key) in CONNECTORS.items():
            if time.monotonic() - last_run[name] >= getattr(settings, interval_key):
                last_run[name] = time.monotonic()
                run_connector_pass(name)
        with session_scope() as session:
            reap_stale(session)
        if not run_once():
            time.sleep(settings.worker_poll_seconds)
