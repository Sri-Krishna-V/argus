"""Deterministic research orchestrator (PRD-V2 4.1, ADR-0010): compiles a plan into
an investigation task DAG and executes it through the jobs outbox. It assigns and
routes work; it never performs domain reasoning — every LLM call lives in the task
handlers' agentruntime calls, behind the citation gate."""

import graphlib
import uuid

from sqlalchemy.orm import Session

from argus.agentruntime.schemas import ResearchPlan
from argus.core import events
from argus.core.config import get_settings
from argus.investigations.models import Investigation, InvestigationEvent, InvestigationTask

JOB_TYPE = "investigation.task"


def _emit(session: Session, investigation_id: uuid.UUID, event_type: str, payload: dict) -> None:
    session.add(
        InvestigationEvent(
            investigation_id=investigation_id, event_type=event_type, payload=payload
        )
    )


def _validate_dag(deps: dict[str, list[str]]) -> None:
    """deps: task_id -> prerequisite task_ids. Raises ValueError on a cycle."""
    try:
        graphlib.TopologicalSorter(deps).prepare()
    except graphlib.CycleError as exc:
        raise ValueError(f"investigation DAG contains a cycle: {exc.args[1]}") from exc


def _enqueue_task(session: Session, task: InvestigationTask) -> None:
    events.enqueue(
        session, JOB_TYPE,
        document_id=task.investigation_id,  # aggregate id: lets execute() drain one investigation
        payload={"task_id": str(task.id)},
    )


def compile_dag(
    session: Session, inv: Investigation, plan: ResearchPlan, company_ids: list[uuid.UUID]
) -> list[InvestigationTask]:
    """Plan → persisted task DAG (PRD-V2 1.2). The LLM plans; this code decides the
    graph shape deterministically: one collect task per query, one synthesis fan-in."""
    if not plan.queries:
        raise ValueError("plan has no queries; nothing to investigate")
    k = get_settings().agent_retrieval_k

    collects = [
        InvestigationTask(
            id=uuid.uuid4(),
            investigation_id=inv.id,
            task_type="collect_evidence",
            objective=q.objective or f"collect evidence for: {q.query}",
            depends_on=[],  # server_default only applies post-flush; DAG validation runs pre-flush
            inputs={
                "query": q.query,
                "objective": q.objective,
                "company_ids": [str(c) for c in company_ids],
                "doc_types": plan.doc_types,
                "k": k,
            },
        )
        for q in plan.queries
    ]
    synthesize = InvestigationTask(
        id=uuid.uuid4(),
        investigation_id=inv.id,
        task_type="synthesize",
        objective="synthesize a cited report from all collected evidence",
        depends_on=[str(t.id) for t in collects],
    )
    tasks = [*collects, synthesize]

    _validate_dag({str(t.id): list(t.depends_on) for t in tasks})
    session.add_all(tasks)
    session.flush()
    for task in tasks:
        if not task.depends_on:
            _enqueue_task(session, task)
    _emit(session, inv.id, "investigation.compiled", {
        "tasks": [
            {"id": str(t.id), "type": t.task_type, "objective": t.objective,
             "depends_on": t.depends_on}
            for t in tasks
        ],
        "investigation_type": plan.investigation_type,
    })
    return tasks
