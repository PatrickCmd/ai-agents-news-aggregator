from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from news_schemas.scraper_run import (
    PipelineName,
    RunStats,
    ScraperRunIn,
    ScraperRunOut,
    ScraperRunStatus,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from news_db.models.scraper_run import ScraperRun


class ScraperRunRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def start(self, run_in: ScraperRunIn) -> ScraperRunOut:
        row = ScraperRun(
            trigger=run_in.trigger,
            status=ScraperRunStatus.RUNNING.value,
            lookback_hours=run_in.lookback_hours,
            pipelines_requested=[p.value for p in run_in.pipelines_requested],
            stats={},
        )
        self._session.add(row)
        await self._session.commit()
        await self._session.refresh(row)
        return self._to_out(row)

    async def complete(
        self,
        run_id: UUID,
        status: ScraperRunStatus,
        stats: RunStats,
        error_message: str | None = None,
    ) -> ScraperRunOut:
        stmt = (
            update(ScraperRun)
            .where(ScraperRun.id == run_id)
            .values(
                status=status.value,
                completed_at=datetime.now(UTC),
                stats=stats.model_dump(mode="json"),
                error_message=error_message,
            )
            .returning(ScraperRun)
        )
        result = await self._session.execute(stmt)
        row = result.scalar_one()
        await self._session.commit()
        return self._to_out(row)

    async def get_by_id(self, run_id: UUID) -> ScraperRunOut | None:
        row = await self._session.get(ScraperRun, run_id)
        return self._to_out(row) if row else None

    async def get_recent(self, limit: int = 20) -> list[ScraperRunOut]:
        stmt = select(ScraperRun).order_by(ScraperRun.started_at.desc()).limit(limit)
        rows = (await self._session.execute(stmt)).scalars().all()
        return [self._to_out(r) for r in rows]

    async def mark_orphaned(self, older_than: datetime) -> int:
        stmt = (
            update(ScraperRun)
            .where(ScraperRun.status == ScraperRunStatus.RUNNING.value)
            .where(ScraperRun.started_at < older_than)
            .values(
                status=ScraperRunStatus.FAILED.value,
                completed_at=datetime.now(UTC),
                error_message="orphaned",
            )
        )
        result = await self._session.execute(stmt)
        await self._session.commit()
        rowcount = getattr(result, "rowcount", 0) or 0
        return int(rowcount)

    @staticmethod
    def _to_out(row: ScraperRun) -> ScraperRunOut:
        return ScraperRunOut(
            id=row.id,
            trigger=row.trigger,
            status=ScraperRunStatus(row.status),
            started_at=row.started_at,
            completed_at=row.completed_at,
            lookback_hours=row.lookback_hours,
            pipelines_requested=[PipelineName(p) for p in row.pipelines_requested],
            stats=RunStats.model_validate(row.stats),
            error_message=row.error_message,
        )
