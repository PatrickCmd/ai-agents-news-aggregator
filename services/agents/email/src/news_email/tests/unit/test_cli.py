from __future__ import annotations

from typer.testing import CliRunner


def test_cli_help_includes_send_and_preview() -> None:
    from news_email.cli import app

    runner = CliRunner()
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "send" in result.stdout
    assert "preview" in result.stdout
