"""Argus operations CLI."""

import uuid

import typer

from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.logging import configure_logging

app = typer.Typer(help="Argus — Enterprise Research Operating System", no_args_is_help=True)


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
    typer.echo(run_connector_pass(connector))


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


if __name__ == "__main__":
    app()
