"""Argus operations CLI."""

import uuid
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
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


def _score_style(value: float, good: float, ok: float) -> str:
    if value >= good:
        return "ok"
    if value >= ok:
        return "warn"
    return "err"

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
    from argus.investigations.orchestrator import register

    register()
    main_loop()


@app.command()
def status() -> None:
    """One-screen ops snapshot: job queue, dead jobs, documents, recent pipeline runs."""
    from sqlalchemy import func, select

    from argus.core.models import Job
    from argus.knowledge.models import Document
    from argus.observability.models import PipelineRun

    with session_scope() as session:
        queue = dict(
            session.execute(select(Job.status, func.count()).group_by(Job.status)).all()
        )
        dead_count = queue.get("dead", 0)
        doc_count = session.scalar(select(func.count()).select_from(Document))
        recent = session.scalars(
            select(PipelineRun).order_by(PipelineRun.created_at.desc()).limit(10)
        ).all()

    queue_style = "err" if dead_count else "ok"
    console.print(
        "[accent]queue[/accent]  " + " ".join(f"{k}={v}" for k, v in sorted(queue.items()))
        + f"  [{queue_style}]dead={dead_count}[/{queue_style}]"
    )
    console.print(f"[accent]documents[/accent]  {doc_count}")

    table = Table(title="Recent pipeline runs")
    table.add_column("stage")
    table.add_column("status")
    table.add_column("duration (ms)", justify="right")
    table.add_column("attempt", justify="right")
    for run in recent:
        style = "ok" if run.status == "success" else "err"
        table.add_row(
            run.stage, f"[{style}]{run.status}[/{style}]", str(run.duration_ms), str(run.attempt)
        )
    console.print(table)


@app.command()
def search(
    query: str,
    k: int = typer.Option(10, "-k", help="number of results"),
) -> None:
    """Hybrid search from the terminal."""
    from argus.research.retrieval import search as run_search

    with session_scope() as session:
        results = run_search(session, query, k=k)

    if not results:
        console.print("[warn]no results[/warn]")
        raise typer.Exit(0)

    table = Table(title=f"Search: {query!r}")
    table.add_column("title")
    table.add_column("type")
    table.add_column("source")
    table.add_column("snippet")
    for r in results:
        table.add_row(
            r.title or "[muted]untitled[/muted]", r.doc_type, r.source, r.text[:80] + "…"
        )
    console.print(table)


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
    console.print(
        f"enqueued [accent]{stage}[/accent] for [ok]{len(doc_ids)}[/ok] documents "
        f"at v{pipeline_version}"
    )


@app.command("retry-dead")
def retry_dead(
    job_id: int | None = typer.Option(None, "--job-id", help="retry only this job"),
    yes: bool = typer.Option(False, "--yes", help="skip confirmation when retrying all"),
) -> None:
    """Reset dead (poison) jobs back to pending for another attempt."""
    from sqlalchemy import func, update

    from argus.core.models import Job

    with session_scope() as session:
        if job_id is not None:
            job = session.get(Job, job_id)
            if job is None or job.status != "dead":
                console.print(f"[warn]no dead job with id {job_id}[/warn]")
                raise typer.Exit(1)
            stmt = update(Job).where(Job.id == job_id)
        else:
            if not yes:
                typer.confirm("retry all dead jobs?", abort=True)
            stmt = update(Job).where(Job.status == "dead")
        result = session.execute(
            stmt.values(status="pending", attempts=0, run_after=func.now())
        )
        style = "ok" if result.rowcount else "muted"
        console.print(f"retried [{style}]{result.rowcount}[/{style}] job(s)")


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
        table = Table(title="Retrieval eval")
        table.add_column("question")
        table.add_column("rank", justify="right")
        for pq in metrics["per_question"]:
            rank = pq["rank"]
            style = "muted" if rank is None else ("ok" if rank <= 3 else "warn")
            table.add_row(pq["id"], f"[{style}]{rank if rank else 'miss'}[/{style}]")
        console.print(table)
        console.print(
            f"hit@3=[{_score_style(metrics['hit_rate_at_3'], 0.8, 0.5)}]"
            f"{metrics['hit_rate_at_3']:.2f}[/] "
            f"hit@{k}=[{_score_style(metrics['hit_rate_at_k'], 0.8, 0.5)}]"
            f"{metrics['hit_rate_at_k']:.2f}[/] "
            f"mrr=[{_score_style(metrics['mrr'], 0.7, 0.4)}]{metrics['mrr']:.2f}[/] "
            f"skipped={metrics['skipped']}"
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
        table = Table(title="Investigation eval")
        table.add_column("investigation")
        table.add_column("citations", justify="right")
        table.add_column("coverage", justify="right")
        table.add_column("both stances", justify="right")
        for pi in metrics["per_investigation"]:
            style = _score_style(pi["citation_coverage"], 0.8, 0.5)
            table.add_row(
                str(pi["id"]), str(pi["citation_count"]),
                f"[{style}]{pi['citation_coverage']:.2f}[/{style}]",
                "yes" if pi["has_both_stances"] else "[muted]no[/muted]",
            )
        console.print(table)
        console.print(
            f"mean_coverage=[{_score_style(metrics['mean_citation_coverage'], 0.8, 0.5)}]"
            f"{metrics['mean_citation_coverage']:.2f}[/] "
            f"both_stances_fraction={metrics['both_stances_fraction']:.2f} "
            f"mean_unknown_fraction={metrics['mean_unknown_fraction']:.2f}"
        )
        runner.record_run(
            session, "investigation", metrics, None, runner.INVESTIGATION_EVAL_VERSION
        )


if __name__ == "__main__":
    app()
