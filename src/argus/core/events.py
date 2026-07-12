"""Domain event append + job outbox (ADR-0003). Both writes happen in the caller's
transaction: state change, event, and follow-on job commit atomically or not at all."""

import uuid
from datetime import datetime, timedelta

from sqlalchemy import ColumnElement, func
from sqlalchemy.orm import Session

from argus.core.models import Event, Job


def emit(
    session: Session,
    event_type: str,
    aggregate_id: uuid.UUID | None = None,
    payload: dict | None = None,
    next_job: str | None = None,
    job_payload: dict | None = None,
) -> Event:
    """Append a domain event; optionally derive the follow-on outbox job from it."""
    event = Event(event_type=event_type, aggregate_id=aggregate_id, payload=payload or {})
    session.add(event)
    session.flush()
    if next_job:
        session.add(
            Job(
                event_id=event.id,
                job_type=next_job,
                document_id=aggregate_id,
                payload=job_payload or {},
            )
        )
    return event


def enqueue(
    session: Session,
    job_type: str,
    document_id: uuid.UUID | None = None,
    payload: dict | None = None,
    run_after: datetime | None = None,
) -> Job:
    """Enqueue a job not derived from a new event (scheduler ticks, reprocessing)."""
    # DB clock, not client clock: the database is the queue's single time authority,
    # so client clock skew (multi-host workers, WSL2 backward steps) can't make a
    # freshly enqueued job look "not yet due" to claim_next
    job = Job(
        job_type=job_type,
        document_id=document_id,
        payload=payload or {},
        run_after=run_after or func.now(),
    )
    session.add(job)
    session.flush()
    return job


def retry_at(attempts: int) -> ColumnElement[datetime]:
    # ponytail: fixed exponential backoff (30s * 2^n), jitter when workers multiply
    return func.now() + timedelta(seconds=30 * 2**attempts)
