"""Pipeline Protocol shared by the three source pipelines."""

from __future__ import annotations

from typing import Protocol

from news_schemas.scraper_run import PipelineName, PipelineStats


class Pipeline(Protocol):
    name: PipelineName

    async def run(self, *, lookback_hours: int) -> PipelineStats: ...
