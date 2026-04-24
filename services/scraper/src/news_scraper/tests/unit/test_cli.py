from __future__ import annotations

from typer.testing import CliRunner

from news_scraper.cli import app as cli_app


def test_cli_help_lists_expected_commands() -> None:
    runner = CliRunner()
    result = runner.invoke(cli_app, ["--help"])
    assert result.exit_code == 0
    for cmd in (
        "ingest",
        "ingest-youtube",
        "ingest-rss",
        "ingest-web",
        "runs",
        "run-show",
        "serve",
    ):
        assert cmd in result.stdout
