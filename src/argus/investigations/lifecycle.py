"""Investigation lifecycle state machine (PRD-V2 1.4): the single source of truth
for which status transitions are legal.

# ponytail: PRD-V2's fine-grained states (draft/planning/executing/evidence_review/
# reasoning/confidence_evaluation/analyst_review) are collapsed into created|running
# here — the task DAG (investigation_tasks) plus the investigation_events timeline
# already make that progress observable without a second state machine to keep in
# sync. Split them out only if a consumer needs to query "is this investigation
# currently in evidence_review" without walking the DAG.
"""

from sqlalchemy.orm import Session

from argus.investigations import engine
from argus.investigations.models import Investigation

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "created": {"running", "paused", "cancelled"},
    "running": {"paused", "complete", "failed", "cancelled"},
    "paused": {"running", "cancelled"},
    "complete": {"archived"},
    "failed": {"archived"},
    "cancelled": {"archived"},
    "archived": set(),
}


def transition(
    session: Session, inv: Investigation, new_status: str, payload: dict | None = None
) -> Investigation:
    """Validate + apply a status change, emitting `investigation.<new_status>`.
    Raises ValueError on an illegal transition — callers translate that to 409."""
    if new_status not in ALLOWED_TRANSITIONS.get(inv.status, set()):
        raise ValueError(f"cannot transition investigation from {inv.status!r} to {new_status!r}")
    inv.status = new_status
    engine._emit(session, inv.id, f"investigation.{new_status}", payload or {})
    return inv
