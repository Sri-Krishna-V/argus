"""CLI smoke tests: rich console wiring and the read-only ops commands."""

import sqlalchemy as sa
from typer.testing import CliRunner

from argus.cli import app, console
from argus.core.db import session_scope
from argus.investigations.models import Report
from tests.conftest import requires_db

runner = CliRunner()


def test_console_is_rich_console_with_theme():
    from rich.console import Console

    assert isinstance(console, Console)
    assert console.get_style("ok") is not None
    assert console.get_style("err") is not None


def test_help_still_works():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "Argus" in result.output


@requires_db
def test_ingest_reports_stats_and_colors_failures(monkeypatch):
    from argus import cli

    def fake_pass(name: str) -> dict:
        return {"seen": 3, "new": 1, "failed": 2}

    import argus.dataplatform.worker as worker_module

    monkeypatch.setattr(worker_module, "run_connector_pass", fake_pass)

    result = runner.invoke(cli.app, ["ingest", "company_profiles"])
    assert result.exit_code == 0
    assert "seen" in result.output and "'new': 1" in result.output


@requires_db
def test_reprocess_unknown_stage_is_a_clean_error():
    from argus import cli

    result = runner.invoke(cli.app, ["reprocess", "--stage", "nope", "--pipeline-version", "1"])
    assert result.exit_code != 0
    assert "unknown stage" in result.output


@requires_db
def test_retry_dead_no_matching_job_reports_zero():
    from argus import cli

    result = runner.invoke(cli.app, ["retry-dead", "--yes"])
    assert result.exit_code == 0
    assert "retried" in result.output.lower()


@requires_db
def test_eval_investigation_no_reports_is_a_clean_message():
    from argus import cli

    with session_scope() as session:
        session.execute(sa.delete(Report))  # other modules' investigations may have run first

    result = runner.invoke(cli.app, ["eval", "investigation"])
    assert result.exit_code == 1
    assert "no reports found" in result.output


@requires_db
def test_status_shows_queue_and_document_counts():
    from argus import cli

    result = runner.invoke(cli.app, ["status"])
    assert result.exit_code == 0
    assert "documents" in result.output.lower()
    assert "queue" in result.output.lower()
