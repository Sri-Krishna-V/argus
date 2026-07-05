"""Argus operations CLI."""

import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.theme import Theme

from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.logging import configure_logging

THEME = Theme({
    "ok": "bold green",
    "warn": "bold yellow",
    "err": "bold red",
    "accent": "bold cyan",
    "muted": "dim",
})
console = Console(theme=THEME)

app = typer.Typer(
    help="[accent]Argus[/accent] — Enterprise Research Operating System",
    no_args_is_help=True,
    rich_markup_mode="rich",
)
eval_app = typer.Typer(no_args_is_help=True, help="Run evaluation harnesses (Phase 8).")
app.add_typer(eval_app, name="eval")


@app.callback()
def _setup() -> None:
    configure_logging(get_settings().log_level)


@app.command()
def worker() -> None:
    """Run the pipeline worker + connector scheduler (Ctrl-C to stop)."""
    from argus.dataplatform.worker import main_loop

    main_loop()


@app.command()
def ingest(connector: str) -> None:
    """Run one connector pass now (company_profiles | sec_edgar | rss)."""
    from argus.dataplatform.worker import CONNECTORS, run_connector_pass

    if connector not in CONNECTORS:
        raise typer.BadParameter(f"unknown connector; choose from {sorted(CONNECTORS)}")
    with console.status(f"[accent]running {connector}...[/accent]"):
        stats = run_connector_pass(connector)
    style = "err" if stats.get("failed") else "ok"
    console.print(f"[{style}]{connector}[/{style}] {stats}")


@app.command()
def reprocess(
    stage: str = typer.Option(..., help="pipeline stage to re-run"),
    pipeline_version: int = typer.Option(..., help="version to (re)derive artifacts under"),
    document_id: str | None = typer.Option(None, help="limit to one document"),
) -> None:
    """Re-derive artifacts from stored raw documents — no re-downloading (Bible §14)."""
    from sqlalchemy import select

    from argus.core import events
    from argus.dataplatform.pipeline import STAGES
    from argus.knowledge.models import Document

    if stage not in STAGES:
        raise typer.BadParameter(f"unknown stage; choose from {STAGES}")
    with session_scope() as session:
        query = select(Document.id)
        if document_id:
            query = query.where(Document.id == uuid.UUID(document_id))
        else:
            query = query.where(Document.doc_type != "profile_registry")
        doc_ids = session.scalars(query).all()
        for doc_id in doc_ids:
            events.enqueue(
                session, stage, document_id=doc_id,
                payload={"pipeline_version": pipeline_version},
            )
    typer.echo(f"enqueued {stage} for {len(doc_ids)} documents at v{pipeline_version}")


@app.command("retry-dead")
def retry_dead(
    job_id: int | None = typer.Option(None, "--job-id", help="retry only this job"),
    yes: bool = typer.Option(False, "--yes", help="skip confirmation when retrying all"),
) -> None:
    """Reset dead (poison) jobs back to pending for another attempt."""
    from datetime import UTC, datetime

    from sqlalchemy import update

    from argus.core.models import Job

    with session_scope() as session:
        if job_id is not None:
            job = session.get(Job, job_id)
            if job is None or job.status != "dead":
                typer.echo(f"no dead job with id {job_id}")
                raise typer.Exit(1)
            stmt = update(Job).where(Job.id == job_id)
        else:
            if not yes:
                typer.confirm("retry all dead jobs?", abort=True)
            stmt = update(Job).where(Job.status == "dead")
        result = session.execute(
            stmt.values(status="pending", attempts=0, run_after=datetime.now(UTC))
        )
        typer.echo(f"retried {result.rowcount} job(s)")


@eval_app.command("retrieval")
def eval_retrieval_cmd(
    golden: Path = typer.Option(
        Path("evals/golden.json"), help="path to the golden question set"
    ),
    k: int = typer.Option(10, help="chunks/documents to retrieve per question"),
) -> None:
    """Score hybrid retrieval against the golden set."""
    from argus.evals import runner
    from argus.research.retrieval import STRATEGY_VERSION

    try:
        golden_set = runner.load_golden(golden)
    except ValueError as exc:
        typer.echo(str(exc))
        raise typer.Exit(1) from exc

    with session_scope() as session:
        metrics = runner.eval_retrieval(session, golden_set, k=k)
        if metrics["questions"] == 0:
            typer.echo(
                f"all {metrics['skipped']} questions skipped (no matching documents); "
                "not recording a run"
            )
            raise typer.Exit(1)
        for pq in metrics["per_question"]:
            typer.echo(f"{pq['id']}  rank={pq['rank'] if pq['rank'] else 'miss'}")
        typer.echo(
            f"hit@3={metrics['hit_rate_at_3']:.2f} hit@{k}={metrics['hit_rate_at_k']:.2f} "
            f"mrr={metrics['mrr']:.2f} skipped={metrics['skipped']}"
        )
        runner.record_run(
            session, "retrieval", metrics, golden_set["version"], STRATEGY_VERSION
        )


@eval_app.command("investigation")
def eval_investigation_cmd() -> None:
    """Score citation coverage and stance balance across the latest report of every
    investigation that has one."""
    from argus.evals import runner

    with session_scope() as session:
        metrics = runner.eval_investigation(session)
        if metrics["reports"] == 0:
            typer.echo("no reports found; nothing to evaluate")
            raise typer.Exit(1)
        for pi in metrics["per_investigation"]:
            typer.echo(
                f"{pi['id']}  citations={pi['citation_count']} "
                f"coverage={pi['citation_coverage']:.2f} both_stances={pi['has_both_stances']}"
            )
        typer.echo(
            f"mean_coverage={metrics['mean_citation_coverage']:.2f} "
            f"both_stances_fraction={metrics['both_stances_fraction']:.2f} "
            f"mean_unknown_fraction={metrics['mean_unknown_fraction']:.2f}"
        )
        runner.record_run(
            session, "investigation", metrics, None, runner.INVESTIGATION_EVAL_VERSION
        )


if __name__ == "__main__":
    app()
