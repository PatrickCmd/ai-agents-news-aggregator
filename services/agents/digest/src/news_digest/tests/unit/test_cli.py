from __future__ import annotations

from typer.testing import CliRunner


def test_cli_help_includes_summarize_and_sweep() -> None:
    from news_digest.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "summarize" in result.stdout
    assert "sweep" in result.stdout
