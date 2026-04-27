"""Allows `python -m news_api …` to invoke the Typer CLI."""

from __future__ import annotations

from news_api.cli import app

if __name__ == "__main__":
    app()
