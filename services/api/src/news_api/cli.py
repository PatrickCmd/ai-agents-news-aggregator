"""Typer CLI — exposes `serve` for local uvicorn."""

from __future__ import annotations

import typer
import uvicorn

app = typer.Typer(no_args_is_help=True, add_completion=False)


@app.callback()
def _main() -> None:
    """news-api CLI."""


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8000, reload: bool = False) -> None:
    """Run the FastAPI app under uvicorn for local dev.

    `reload` defaults to False because uvicorn's reloader requires an importable
    app target string (it can't reload a Python object directly). For active
    development, set `--reload` and uvicorn will use the import-string form via
    the factory pattern (`uvicorn.run("news_api.app:create_app", factory=True, ...)`).
    """
    if reload:
        uvicorn.run("news_api.app:create_app", factory=True, host=host, port=port, reload=True)
    else:
        from news_api.app import create_app

        uvicorn.run(create_app(), host=host, port=port)


if __name__ == "__main__":
    app()
