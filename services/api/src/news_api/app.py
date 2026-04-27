"""FastAPI app factory — mounted under /v1."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from news_api.routes import healthz, me
from news_api.settings import get_api_settings


def create_app() -> FastAPI:
    settings = get_api_settings()
    app = FastAPI(title="news-api", version="0.5.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "PUT", "POST", "OPTIONS"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=3600,
    )
    app.include_router(healthz.router, prefix="/v1")
    app.include_router(me.router, prefix="/v1")
    return app
