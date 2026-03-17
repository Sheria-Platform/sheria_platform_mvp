# services/api/app/memory/feedback_repository.py
"""Feedback persistence -- record user ratings for assistant responses."""

from services.api.app.memory.models import AsyncSessionLocal, Feedback


class FeedbackRepository:
    """Async repository for user feedback on assistant responses."""

    async def record_feedback(
        self,
        session_id: str,
        user_id: str,
        message_id: int,
        score: int,
        comment: str | None,
    ) -> None:
        """Persist a user rating for an assistant response.

        Args:
            session_id: Conversation thread the rated message belongs to.
            user_id: Authenticated user submitting the rating.
            message_id: Primary-key ID of the ``ChatHistory`` row being rated.
            score: ``1`` for positive, ``-1`` for negative.
            comment: Optional free-text explanation.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    Feedback(
                        session_id=session_id,
                        user_id=user_id,
                        message_id=message_id,
                        score=score,
                        comment=comment,
                    )
                )


# Global singleton -- stateless; no lifecycle management required
feedback_repository = FeedbackRepository()
