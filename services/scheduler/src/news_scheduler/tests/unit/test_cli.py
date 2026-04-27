from __future__ import annotations

from typer.testing import CliRunner


def test_cli_help_includes_all_three_commands() -> None:
    from news_scheduler.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "list-unsummarised" in result.stdout
    assert "list-active-users" in result.stdout
    assert "list-new-digests" in result.stdout
