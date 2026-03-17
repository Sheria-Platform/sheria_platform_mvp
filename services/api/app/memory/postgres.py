# services/api/app/memory/postgres.py
"""Backward-compatibility facade for the PostgreSQL data layer.

All ORM models, engine, and session factory are now in ``memory/models.py``.
Domain logic is split into focused repository classes:
- ChatRepository       -> memory/chat_repository.py
- UserRepository       -> memory/user_repository.py
- IngestionRepository  -> memory/ingestion_repository.py
- VerificationRepository -> memory/verification_repository.py
- PredictionRepository -> memory/prediction_repository.py
- FeedbackRepository   -> memory/feedback_repository.py

This module re-exports everything so existing imports continue to work.
"""

from collections.abc import Sequence
from datetime import datetime

# Re-export ORM models, engine, and session factory from models.py
from services.api.app.memory.models import (  # noqa: F401
    AsyncSessionLocal,
    Base,
    ChatHistory,
    Feedback,
    IngestionJob,
    PredictionHistory,
    User,
    VerificationActivity,
    engine,
)

# Re-export repository singletons
from services.api.app.memory.chat_repository import (  # noqa: F401
    ChatRepository,
    chat_repository,
)
from services.api.app.memory.feedback_repository import (  # noqa: F401
    FeedbackRepository,
    feedback_repository,
)
from services.api.app.memory.ingestion_repository import (  # noqa: F401
    IngestionRepository,
    ingestion_repository,
)
from services.api.app.memory.prediction_repository import (  # noqa: F401
    PredictionRepository,
    prediction_repository,
)
from services.api.app.memory.user_repository import (  # noqa: F401
    UserRepository,
    user_repository,
)
from services.api.app.memory.verification_repository import (  # noqa: F401
    VerificationRepository,
    verification_repository,
)


class PostgresMemory:
    """Composite facade that delegates every method to the correct repository.

    Maintains full backward compatibility so callers using
    ``postgres_memory.add_message(...)`` etc. continue to work unchanged.
    """

    def __init__(self) -> None:
        self._chat = chat_repository
        self._user = user_repository
        self._ingestion = ingestion_repository
        self._verification = verification_repository
        self._prediction = prediction_repository
        self._feedback = feedback_repository

    # -- Chat ------------------------------------------------------------------

    async def add_message(
        self, session_id: str, role: str, content: str, user_id: str
    ) -> None:
        return await self._chat.add_message(session_id, role, content, user_id)

    async def get_history(
        self, session_id: str, limit: int = 10
    ) -> Sequence[ChatHistory]:
        return await self._chat.get_history(session_id, limit)

    async def get_user_sessions(self, user_id: str, limit: int = 50) -> list[dict]:
        return await self._chat.get_user_sessions(user_id, limit)

    async def get_session_messages(
        self, session_id: str, user_id: str
    ) -> list[dict]:
        return await self._chat.get_session_messages(session_id, user_id)

    # -- Ingestion -------------------------------------------------------------

    async def create_ingestion_job(
        self,
        job_id: str,
        user_id: str,
        filename: str,
        s3_key: str,
        started_at: datetime,
    ) -> None:
        return await self._ingestion.create_ingestion_job(
            job_id, user_id, filename, s3_key, started_at
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
        return await self._ingestion.update_ingestion_job(
            job_id, status, completed_at, duration_s, stats, error
        )

    async def get_all_ingestion_jobs(
        self, user_id: str, limit: int = 100
    ) -> list[dict]:
        return await self._ingestion.get_all_ingestion_jobs(user_id, limit)

    async def get_ingestion_job(self, job_id: str, user_id: str) -> dict | None:
        return await self._ingestion.get_ingestion_job(job_id, user_id)

    # -- User ------------------------------------------------------------------

    async def create_user(
        self,
        username: str,
        email: str,
        full_name: str,
        court_station: str,
        role: str,
        staff_number: str | None = None,
    ) -> None:
        return await self._user.create_user(
            username, email, full_name, court_station, role, staff_number
        )

    async def get_user_by_username(self, username: str) -> dict | None:
        return await self._user.get_user_by_username(username)

    async def get_user_by_email(self, email: str) -> dict | None:
        return await self._user.get_user_by_email(email)

    async def get_user_by_id(self, user_id: str) -> dict | None:
        return await self._user.get_user_by_id(user_id)

    async def get_user_by_activation_token(self, token: str) -> dict | None:
        return await self._user.get_user_by_activation_token(token)

    async def get_pending_users(self) -> list[dict]:
        return await self._user.get_pending_users()

    async def approve_user(
        self,
        user_id: str,
        role: str,
        activation_token: str,
        approved_by: str,
    ) -> None:
        return await self._user.approve_user(
            user_id, role, activation_token, approved_by
        )

    async def activate_user(self, user_id: str, hashed_password: str) -> None:
        return await self._user.activate_user(user_id, hashed_password)

    async def get_users(self, status: str | None = None) -> list[dict]:
        return await self._user.get_users(status)

    async def update_user_status(self, user_id: str, new_status: str) -> bool:
        return await self._user.update_user_status(user_id, new_status)

    async def seed_admin(
        self,
        username: str,
        email: str,
        full_name: str,
        hashed_password: str,
    ) -> bool:
        return await self._user.seed_admin(
            username, email, full_name, hashed_password
        )

    # -- Feedback --------------------------------------------------------------

    async def record_feedback(
        self,
        session_id: str,
        user_id: str,
        message_id: int,
        score: int,
        comment: str | None,
    ) -> None:
        return await self._feedback.record_feedback(
            session_id, user_id, message_id, score, comment
        )

    # -- Verification ----------------------------------------------------------

    async def save_verification(
        self,
        user_id: str,
        filename: str,
        document_type: str,
        case_number: str,
        report_dict: dict,
    ) -> int:
        return await self._verification.save_verification(
            user_id, filename, document_type, case_number, report_dict
        )

    async def get_user_verifications(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        return await self._verification.get_user_verifications(user_id, limit)

    # -- Prediction ------------------------------------------------------------

    async def save_prediction(
        self,
        user_id: str,
        case_type: str,
        court: str,
        complexity: str,
        parties_count: int,
        report_dict: dict,
    ) -> int:
        return await self._prediction.save_prediction(
            user_id, case_type, court, complexity, parties_count, report_dict
        )

    async def get_user_predictions(
        self, user_id: str, limit: int = 50
    ) -> list[dict]:
        return await self._prediction.get_user_predictions(user_id, limit)


# Global singleton -- stateless; no lifecycle management required
postgres_memory = PostgresMemory()
