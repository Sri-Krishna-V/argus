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
