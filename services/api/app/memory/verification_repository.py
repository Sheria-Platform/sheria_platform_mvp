# services/api/app/memory/verification_repository.py
"""Verification activity persistence -- save and retrieve document authentication results."""

from sqlalchemy import select

from services.api.app.memory.models import AsyncSessionLocal, VerificationActivity


def _verification_to_dict(row: VerificationActivity) -> dict:
    """Serialise a ``VerificationActivity`` ORM row to a plain dict."""
    return {
        "id": row.id,
        "filename": row.filename,
        "document_type": row.document_type,
        "case_number": row.case_number,
        "authentic": row.authentic,
        "confidence": row.confidence,
        "report": row.report,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


class VerificationRepository:
    """Async repository for document verification activity persistence."""

    async def save_verification(
        self,
        user_id: str,
        filename: str,
        document_type: str,
        case_number: str,
        report_dict: dict,
    ) -> int:
        """Persist a completed verification report and return the new row id.

        Args:
            user_id: Authenticated user who ran the verification.
            filename: Original uploaded filename.
            document_type: Declared document type (e.g. ``"court_order"``).
            case_number: Case reference supplied by the user (may be empty).
            report_dict: Full ``VerificationReport`` serialised as a dict.

        Returns:
            The auto-incremented primary key of the newly inserted row.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                row = VerificationActivity(
                    user_id=user_id,
                    filename=filename,
                    document_type=document_type,
                    case_number=case_number,
                    authentic=report_dict.get("authentic", False),
                    confidence=report_dict.get("confidence", 0.0),
                    report=report_dict,
                )
                session.add(row)
                await session.flush()
                return row.id

    async def get_user_verifications(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        """Return verification activities for a user, newest-first.

        Args:
            user_id: Authenticated user identifier.
            limit: Maximum number of rows to return.

        Returns:
            List of dicts with keys: id, filename, document_type, case_number,
            authentic, confidence, report, created_at.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(VerificationActivity)
                .where(VerificationActivity.user_id == user_id)
                .order_by(VerificationActivity.created_at.desc())
                .limit(limit)
            )
            rows = result.scalars().all()
            return [_verification_to_dict(r) for r in rows]


# Global singleton -- stateless; no lifecycle management required
verification_repository = VerificationRepository()
