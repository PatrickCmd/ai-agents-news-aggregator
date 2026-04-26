from __future__ import annotations

from typer.testing import CliRunner


def test_cli_help_includes_rank() -> None:
    from news_editor.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "rank" in result.stdout
