# services/api/app/routes/feedback.py
"""User feedback submission endpoint.

Allows authenticated users to rate individual assistant responses with
a thumbs-up/thumbs-down score and an optional free-text comment.
Feedback is persisted to the ``feedback`` table in PostgreSQL.

Note:
    The ``feedback`` table must be created via a migration before this
    endpoint is usable.  See ``scripts/migrate_db.py``.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import text

from services.api.app.core.database import get_db
from services.api.app.tools.auth import get_current_user

router = APIRouter()
logger = logging.getLogger(__name__)


class FeedbackRequest(BaseModel):
    """Request body for submitting response feedback.

    Attributes:
        session_id: The conversation session the message belongs to.
        message_id: Primary-key ID of the assistant ``ChatHistory``
            row being rated.
        score: Sentiment integer -- ``1`` for positive (like),
            ``-1`` for negative (dislike).
        comment: Optional free-text explanation from the user.
    """

    session_id: str
    message_id: int
    score: int          # 1 = like, -1 = dislike
    comment: str | None = None


@router.post("/", summary="Submit response feedback")
async def submit_feedback(
    req: FeedbackRequest,
    user: dict = Depends(get_current_user),
) -> dict[str, str]:
    """Record a user's rating for an assistant response.

    Args:
        req: Feedback payload including session, message, score,
            and optional comment.
        user: Authenticated user dict from ``get_current_user``.

    Returns:
        ``{"status": "recorded"}`` on success.

    Raises:
        HTTPException(500): On any database write failure.

    Example:
        Request::

            POST /api/v1/feedback/
            Authorization: Bearer <token>
            {
                "session_id": "abc-123",
                "message_id": 42,
                "score": 1,
                "comment": "Very accurate citation."
            }
    """
    try:
        db_session = get_db()
        await db_session.execute(
            text(
                """
                INSERT INTO feedback
                    (session_id, user_id, message_id, score, comment)
                VALUES
                    (:sid, :uid, :mid, :score, :comment)
                """
            ),
            {
                "sid": req.session_id,
                "uid": user["id"],
                "mid": req.message_id,
                "score": req.score,
                "comment": req.comment,
            },
        )
        await db_session.commit()
        logger.info(
            "Feedback recorded. session=%s message=%d score=%d",
            req.session_id,
            req.message_id,
            req.score,
        )
        return {"status": "recorded"}

    except Exception as exc:
        logger.error("Failed to record feedback: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
