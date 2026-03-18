# services/api/app/memory/prediction_repository.py
"""Prediction history persistence -- save and retrieve case duration forecast records."""

from datetime import datetime

from sqlalchemy import select

from services.api.app.memory.models import AsyncSessionLocal, PredictionHistory


def _prediction_to_dict(row: PredictionHistory) -> dict:
    """Serialise a ``PredictionHistory`` ORM row to a plain dict."""
    return {
        "id": row.id,
        "case_type": row.case_type,
        "court": row.court,
        "complexity": row.complexity,
        "parties_count": row.parties_count,
        "estimated_months_min": row.estimated_months_min,
        "estimated_months_max": row.estimated_months_max,
        "confidence": row.confidence,
        "risk_level": row.risk_level,
        "report": row.report,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class PredictionRepository:
    """Async repository for case duration prediction history."""

    async def save_prediction(
        self,
        user_id: str,
        case_type: str,
        court: str,
        complexity: str,
        parties_count: int,
        report_dict: dict,
    ) -> int:
        """Persist a completed prediction report and return the new row id.

        Args:
            user_id:       Authenticated user who ran the prediction.
            case_type:     Type of case submitted (e.g. ``"land_dispute"``).
            court:         Court name and station.
            complexity:    Declared complexity (``"low"`` | ``"medium"`` | ``"high"``).
            parties_count: Number of parties in the case.
            report_dict:   Full ``PredictionReport`` serialised as a dict.

        Returns:
            The auto-incremented primary key of the newly inserted row.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                row = PredictionHistory(
                    user_id=user_id,
                    case_type=case_type,
                    court=court,
                    complexity=complexity,
                    parties_count=parties_count,
                    estimated_months_min=report_dict.get("estimated_months_min"),
                    estimated_months_max=report_dict.get("estimated_months_max"),
                    confidence=report_dict.get("confidence"),
                    risk_level=report_dict.get("risk_level"),
                    report=report_dict,
                )
                session.add(row)
                await session.flush()
                return row.id

    async def get_user_predictions(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """Return prediction records for a user, newest-first.

        Args:
            user_id: Authenticated user identifier.
            limit:   Maximum number of rows to return.

        Returns:
            List of dicts with keys: id, case_type, court, complexity,
            parties_count, estimated_months_min, estimated_months_max,
            confidence, risk_level, report, created_at.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PredictionHistory)
                .where(PredictionHistory.user_id == user_id)
                .order_by(PredictionHistory.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_prediction_to_dict(r) for r in rows]


    async def get_court_predictions(
        self, court: str, since: datetime, limit: int = 200
    ) -> list[dict]:
        """Return prediction records for a court since a given datetime.

        Args:
            court: Court name to filter by (exact match on the ``court`` column).
            since: Only return rows with ``created_at >= since``.
            limit: Maximum number of rows to return.

        Returns:
            List of dicts with keys: id, case_type, court, complexity,
            parties_count, estimated_months_min, estimated_months_max,
            confidence, risk_level, report, created_at.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(PredictionHistory)
                .where(PredictionHistory.court == court)
                .where(PredictionHistory.created_at >= since)
                .order_by(PredictionHistory.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_prediction_to_dict(r) for r in rows]


# Global singleton -- stateless; no lifecycle management required
prediction_repository = PredictionRepository()
