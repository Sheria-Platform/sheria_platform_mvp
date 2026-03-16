# services/api/app/memory/ingestion_repository.py
"""Ingestion job persistence -- create, update, and query pipeline job records."""

from datetime import datetime

from sqlalchemy import select, update

from services.api.app.memory.models import AsyncSessionLocal, IngestionJob


def _job_to_dict(row: IngestionJob) -> dict:
    """Serialise an ``IngestionJob`` ORM row to a plain dict."""
    return {
        "job_id": row.job_id,
        "status": row.status,
        "filename": row.filename,
        "s3_key": row.s3_key,
        "started_at": row.started_at.timestamp() if row.started_at else None,
        "completed_at": row.completed_at.timestamp() if row.completed_at else None,
        "duration_s": row.duration_s,
        "stats": row.stats or {},
        "error": row.error or "",
    }


class IngestionRepository:
    """Async repository for ingestion job persistence."""

    async def create_ingestion_job(
        self,
        job_id: str,
        user_id: str,
        filename: str,
        s3_key: str,
        started_at: datetime,
    ) -> None:
        """Insert a new ingestion job row with ``pending`` status."""
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    IngestionJob(
                        job_id=job_id,
                        user_id=user_id,
                        status="pending",
                        filename=filename,
                        s3_key=s3_key,
                        started_at=started_at,
                    )
                )

    async def update_ingestion_job(
        self,
        job_id: str,
        status: str,
        completed_at: datetime | None = None,
        duration_s: float | None = None,
        stats: dict | None = None,
        error: str | None = None,
    ) -> None:
        """Update mutable fields on an existing ingestion job row."""
        values: dict = {"status": status}
        if completed_at is not None:
            values["completed_at"] = completed_at
        if duration_s is not None:
            values["duration_s"] = duration_s
        if stats is not None:
            values["stats"] = stats
        if error is not None:
            values["error"] = error
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(IngestionJob)
                    .where(IngestionJob.job_id == job_id)
                    .values(**values)
                )

    async def get_all_ingestion_jobs(
        self, user_id: str, limit: int = 100
    ) -> list[dict]:
        """Return all ingestion jobs for a user, newest-first."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(IngestionJob)
                .where(IngestionJob.user_id == user_id)
                .order_by(IngestionJob.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_job_to_dict(r) for r in rows]

    async def get_ingestion_job(self, job_id: str, user_id: str) -> dict | None:
        """Return a single job dict, or ``None`` if not found / wrong user."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(IngestionJob).where(
                    IngestionJob.job_id == job_id,
                    IngestionJob.user_id == user_id,
                )
            )
            row = result.scalar_one_or_none()
            return _job_to_dict(row) if row else None


# Global singleton -- stateless; no lifecycle management required
ingestion_repository = IngestionRepository()
