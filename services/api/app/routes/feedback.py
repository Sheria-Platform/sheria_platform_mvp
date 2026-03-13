# services/api/app/routes/feedback.py
"""User feedback submission endpoint.

Allows authenticated users to rate individual assistant responses with
a thumbs-up/thumbs-down score and an optional free-text comment.
Feedback is persisted to the ``feedback`` table in PostgreSQL via the
``PostgresMemory.record_feedback`` ORM method.
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from services.api.app.auth.jwt import get_current_user
from services.api.app.memory.postgres import postgres_memory

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
        await postgres_memory.record_feedback(
            session_id=req.session_id,
            user_id=user["id"],
            message_id=req.message_id,
            score=req.score,
            comment=req.comment,
        )
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
