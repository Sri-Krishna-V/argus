# CLI Revamp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `argus`'s CLI colorful and fun to use, and add two read-only ops commands (`status`, `search`), without adding any new dependency.

**Architecture:** `rich` is already installed transitively (typer 0.26.8 pulls it, and typer auto-detects it for pretty `--help`/tracebacks). All changes live in the single existing `src/argus/cli.py` — a module-level `rich.console.Console` with a small theme, colored output on every human-facing command, two new commands built on existing engine functions (`run_connector_pass`, `session_scope`, `search`). The long-running `worker` command keeps plain structured JSON logging untouched — it's for machines, not a terminal session.

**Tech Stack:** Python 3.12, typer 0.26.8, rich (already resolved in `uv.lock`), pytest + `typer.testing.CliRunner`.

## Global Constraints

- No new dependencies — `rich` is already available (`uv run python -c "import rich"` succeeds today).
- Sync code only (ADR-0004) — no changes needed here, CLI is already sync.
- `worker`'s structured JSON logs (`configure_logging`) are untouched — only human-facing command output gets color.
- Every new/changed command must keep working under `typer.testing.CliRunner` (which runs without a real tty — rich auto-disables color there, so tests assert on text content, not ANSI codes).
- Tests requiring the DB use the existing `requires_db` marker and `tests/conftest.py` fixtures (`fake_embeddings`, `seeded_companies`, `ingest_html`, `drain_queue`) — never touch dev data, always `argus_test`.

---

### Task 1: Rich console, theme, and typer wiring

**Files:**
- Modify: `src/argus/cli.py` (top of file, lines 1–20)
- Test: `tests/test_cli.py` (new file)

**Interfaces:**
- Produces: `argus.cli.console` (a `rich.console.Console` instance, importable by later tasks and tests), `argus.cli.app` (unchanged `typer.Typer` instance, now with `rich_markup_mode="rich"`).

- [ ] **Step 1: Write the failing test**

Create `tests/test_cli.py`:

```python
"""CLI smoke tests: rich console wiring and the read-only ops commands."""

from typer.testing import CliRunner

from argus.cli import app, console

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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py -v`
Expected: FAIL — `ImportError: cannot import name 'console' from 'argus.cli'`

- [ ] **Step 3: Add the console and theme, wire into the typer app**

In `src/argus/cli.py`, replace the current top of the file:

```python
"""Argus operations CLI."""

import uuid
from pathlib import Path

import typer

from argus.core.config import get_settings
from argus.core.db import session_scope
from argus.core.logging import configure_logging

app = typer.Typer(help="Argus — Enterprise Research Operating System", no_args_is_help=True)
eval_app = typer.Typer(no_args_is_help=True, help="Run evaluation harnesses (Phase 8).")
app.add_typer(eval_app, name="eval")
```

with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Commit**

```bash
git add src/argus/cli.py tests/test_cli.py
git commit -m "cli: add rich console + theme, enable rich help rendering"
```

---

### Task 2: Colorize `ingest`

**Files:**
- Modify: `src/argus/cli.py` (`ingest` command)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `console` from Task 1; `argus.dataplatform.worker.run_connector_pass(name: str) -> dict` (existing, returns `{"seen": int, "new": int, "failed": int}`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py` (needs a DB + a connector that actually runs; `company_profiles` connector is safe to run against the test DB with no network — reuse the existing fixture pattern):

```python
import pytest

from tests.conftest import requires_db


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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_ingest_reports_stats_and_colors_failures -v`
Expected: FAIL — output doesn't match yet (current command still uses `typer.echo`), or passes trivially since old code already prints the dict. Confirm it currently passes as-is (it should — this locks in current behavior before the restyle); if so this step's "fail" is: proceed straight to Step 3, the real regression check is Step 4 after the code changes still keeping the same substrings.

- [ ] **Step 3: Restyle the `ingest` command**

Replace:

```python
@app.command()
def ingest(connector: str) -> None:
    """Run one connector pass now (company_profiles | sec_edgar | rss)."""
    from argus.dataplatform.worker import CONNECTORS, run_connector_pass

    if connector not in CONNECTORS:
        raise typer.BadParameter(f"unknown connector; choose from {sorted(CONNECTORS)}")
    typer.echo(run_connector_pass(connector))
```

with:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all tests in the file)

- [ ] **Step 5: Commit**

```bash
git add src/argus/cli.py tests/test_cli.py
git commit -m "cli: colorize ingest output, spinner while a connector pass runs"
```

---

### Task 3: Colorize `reprocess` and `retry-dead`

**Files:**
- Modify: `src/argus/cli.py` (`reprocess`, `retry_dead` commands)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `console` from Task 1.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_reprocess_unknown_stage_is_a_clean_error tests/test_cli.py::test_retry_dead_no_matching_job_reports_zero -v`
Expected: These likely already PASS against current plain-text output (the assertions only check for substrings, not color) — that's fine, they lock in behavior. Confirm by running before Step 3's edit.

- [ ] **Step 3: Restyle `reprocess` and `retry_dead`**

Replace the end of `reprocess`:

```python
        for doc_id in doc_ids:
            events.enqueue(
                session, stage, document_id=doc_id,
                payload={"pipeline_version": pipeline_version},
            )
    typer.echo(f"enqueued {stage} for {len(doc_ids)} documents at v{pipeline_version}")
```

with:

```python
        for doc_id in doc_ids:
            events.enqueue(
                session, stage, document_id=doc_id,
                payload={"pipeline_version": pipeline_version},
            )
    console.print(
        f"enqueued [accent]{stage}[/accent] for [ok]{len(doc_ids)}[/ok] documents "
        f"at v{pipeline_version}"
    )
```

Replace the body of `retry_dead`:

```python
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
```

with:

```python
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
            stmt.values(status="pending", attempts=0, run_after=datetime.now(UTC))
        )
        style = "ok" if result.rowcount else "muted"
        console.print(f"retried [{style}]{result.rowcount}[/{style}] job(s)")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/argus/cli.py tests/test_cli.py
git commit -m "cli: colorize reprocess and retry-dead output"
```

---

### Task 4: Rich tables for `eval retrieval` and `eval investigation`

**Files:**
- Modify: `src/argus/cli.py` (`eval_retrieval_cmd`, `eval_investigation_cmd`)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `console`, `rich.table.Table`; `argus.evals.runner.eval_retrieval`/`eval_investigation` (existing, unchanged return shape — see current `cli.py` for the exact keys: `per_question` with `id`/`rank`, `hit_rate_at_3`/`hit_rate_at_k`/`mrr`/`skipped`; `per_investigation` with `id`/`citation_count`/`citation_coverage`/`has_both_stances`, `mean_citation_coverage`/`both_stances_fraction`/`mean_unknown_fraction`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
@requires_db
def test_eval_investigation_no_reports_is_a_clean_message():
    from argus import cli

    result = runner.invoke(cli.app, ["eval", "investigation"])
    assert result.exit_code == 1
    assert "no reports found" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_eval_investigation_no_reports_is_a_clean_message -v`
Expected: Already PASSES against current code (locks in the no-reports message, which stays unchanged) — confirm before editing.

- [ ] **Step 3: Add a rich-table helper and use it in both eval commands**

Add near the top of `src/argus/cli.py`, after the `THEME`/`console` definitions:

```python
from rich.table import Table


def _score_style(value: float, good: float, ok: float) -> str:
    if value >= good:
        return "ok"
    if value >= ok:
        return "warn"
    return "err"
```

Replace the body of `eval_retrieval_cmd` from the `for pq in metrics["per_question"]` line onward:

```python
        for pq in metrics["per_question"]:
            typer.echo(f"{pq['id']}  rank={pq['rank'] if pq['rank'] else 'miss'}")
        typer.echo(
            f"hit@3={metrics['hit_rate_at_3']:.2f} hit@{k}={metrics['hit_rate_at_k']:.2f} "
            f"mrr={metrics['mrr']:.2f} skipped={metrics['skipped']}"
        )
        runner.record_run(
            session, "retrieval", metrics, golden_set["version"], STRATEGY_VERSION
        )
```

with:

```python
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
```

Replace the body of `eval_investigation_cmd` from the `for pi in metrics["per_investigation"]` line onward:

```python
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
```

with:

```python
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
```

Note: the `no reports`/`all ... skipped` early-exit branches keep their existing `typer.echo` calls — no change needed there.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/argus/cli.py tests/test_cli.py
git commit -m "cli: render eval results as rich tables with score coloring"
```

---

### Task 5: `argus status` command

**Files:**
- Modify: `src/argus/cli.py` (new `status` command)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `session_scope` (existing), `argus.core.models.Job`, `argus.observability.models.PipelineRun`, `argus.knowledge.models.Document` (all existing models, same queries as `argus.ui.views.pipeline_dashboard` before it's deleted in the dashboard plan).
- Produces: `argus status` typer command — no return value consumed elsewhere.

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
@requires_db
def test_status_shows_queue_and_document_counts():
    from argus import cli

    result = runner.invoke(cli.app, ["status"])
    assert result.exit_code == 0
    assert "documents" in result.output.lower()
    assert "queue" in result.output.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_status_shows_queue_and_document_counts -v`
Expected: FAIL — `No such command 'status'`

- [ ] **Step 3: Implement `argus status`**

Add after the `worker` command in `src/argus/cli.py`:

```python
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
        f"[accent]queue[/accent]  " + " ".join(f"{k}={v}" for k, v in sorted(queue.items()))
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
        table.add_row(run.stage, f"[{style}]{run.status}[/{style}]", str(run.duration_ms), str(run.attempt))
    console.print(table)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/argus/cli.py tests/test_cli.py
git commit -m "cli: add argus status — terminal ops snapshot"
```

---

### Task 6: `argus search` command

**Files:**
- Modify: `src/argus/cli.py` (new `search` command)
- Test: `tests/test_cli.py`

**Interfaces:**
- Consumes: `argus.research.retrieval.search(session, query: str, filters=None, k=10) -> list[RetrievalResult]` (existing; `RetrievalResult` has `chunk_id, document_id, text, title, url, source, doc_type, published_at, scores, strategy`).

- [ ] **Step 1: Write the failing test**

Add to `tests/test_cli.py`:

```python
@pytest.mark.usefixtures("fake_embeddings", "seeded_companies")
@requires_db
def test_search_finds_ingested_document():
    from argus import cli
    from tests.conftest import drain_queue, ingest_html

    ingest_html(
        "<p>" + "Datacenter GPU demand accelerates. " * 20 + "</p>",
        source="test_stub", doc_type="news", title="GPU demand story",
    )
    drain_queue()

    result = runner.invoke(cli.app, ["search", "datacenter GPU demand"])
    assert result.exit_code == 0
    assert "GPU demand story" in result.output
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_cli.py::test_search_finds_ingested_document -v`
Expected: FAIL — `No such command 'search'`

- [ ] **Step 3: Implement `argus search`**

Add after the `status` command in `src/argus/cli.py`:

```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_cli.py -v`
Expected: PASS (all tests)

- [ ] **Step 5: Commit**

```bash
git add src/argus/cli.py tests/test_cli.py
git commit -m "cli: add argus search — hybrid retrieval from the terminal"
```

---

### Task 7: Full-suite check

**Files:** none (verification only)

- [ ] **Step 1: Run the full test suite**

Run: `uv run pytest`
Expected: all tests pass (existing suite + new `tests/test_cli.py`)

- [ ] **Step 2: Run lint**

Run: `uv run ruff check src tests && uv run lint-imports`
Expected: no violations (CLI has no cross-layer imports; `argus.cli` isn't part of the layer contract)

- [ ] **Step 3: Manual smoke test**

Run: `uv run argus --help`, `uv run argus status`, `uv run argus search "test"` against a running dev DB (`make up && make migrate`) and eyeball the colored output in a real terminal.

- [ ] **Step 4: Commit if any lint fixes were needed**

```bash
git add -A
git commit -m "cli: lint fixes"
```
(skip if nothing changed)
