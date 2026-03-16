# services/api/app/memory/postgres.py
"""PostgreSQL-backed conversation memory.

Persists every chat turn (user and assistant messages) to the
``chat_history`` table so conversation context survives across API
restarts and can be audited.

Example:
    >>> await postgres_memory.add_message(
    ...     session_id="abc-123",
    ...     role="user",
    ...     content="What is adverse possession?",
    ...     user_id="judge-001",
    ... )
    >>> history = await postgres_memory.get_history("abc-123", limit=6)
"""

import uuid
from collections.abc import Sequence
from datetime import datetime, timedelta

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
    select,
    text,
    update,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from services.api.app.config import settings


class Base(DeclarativeBase):
    pass


class ChatHistory(Base):
    """ORM model for the ``chat_history`` table.

    Each row represents one turn in a conversation.

    Attributes:
        id: Auto-incrementing primary key.
        session_id: UUID string grouping messages into a conversation.
        user_id: Identifier of the authenticated user.
        role: Speaker -- ``"user"``, ``"assistant"``, or ``"system"``.
        content: The raw message text.
        metadata_: Flexible JSON blob for token counts, latency, etc.
        created_at: UTC timestamp of insertion.
    """

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True, nullable=False)
    user_id = Column(String, index=True, nullable=False)
    role = Column(String(50), nullable=False)
    content = Column(Text, nullable=False)
    metadata_ = Column(JSON, default={}, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class IngestionJob(Base):
    """ORM model for the ``ingestion_jobs`` table."""

    __tablename__ = "ingestion_jobs"

    job_id = Column(String, primary_key=True)
    user_id = Column(String, index=True, nullable=False)
    status = Column(String(20), nullable=False, default="pending")
    filename = Column(String, nullable=False, default="")
    s3_key = Column(String, nullable=False, default="")
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    duration_s = Column(Float, nullable=True)
    stats = Column(JSON, default={})
    error = Column(Text, nullable=False, default="")
    created_at = Column(DateTime, default=datetime.utcnow)


class User(Base):
    """ORM model for the ``users`` table — judicial staff accounts."""

    __tablename__ = "users"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    username = Column(String(50), unique=True, nullable=False, index=True)
    email = Column(String(120), unique=True, nullable=False, index=True)
    full_name = Column(String(200), nullable=False)
    hashed_password = Column(String, nullable=True)
    role = Column(String(30), nullable=False)
    court_station = Column(String(200), nullable=False)
    staff_number = Column(String(50), nullable=True)
    status = Column(String(20), nullable=False, default="pending")
    activation_token = Column(String, nullable=True, index=True)
    activation_token_expires_at = Column(DateTime, nullable=True)
    approved_by = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    activated_at = Column(DateTime, nullable=True)


class VerificationActivity(Base):
    """ORM model for the ``verification_activity`` table — audit log of document authentications."""

    __tablename__ = "verification_activity"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    filename = Column(String, nullable=False, default="")
    document_type = Column(String(50), nullable=False)
    case_number = Column(String, nullable=False, default="")
    authentic = Column(Boolean, nullable=False)
    confidence = Column(Float, nullable=False)
    report = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


class Feedback(Base):
    """ORM model for the ``feedback`` table — user ratings for assistant responses."""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    message_id = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PredictionHistory(Base):
    """ORM model for the ``prediction_history`` table — audit log of case duration forecasts."""

    __tablename__ = "prediction_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String, index=True, nullable=False)
    case_type = Column(String(100), nullable=False)
    court = Column(String(200), nullable=False, default="")
    complexity = Column(String(20), nullable=False)
    parties_count = Column(Integer, nullable=False, default=2)
    estimated_months_min = Column(Integer, nullable=True)
    estimated_months_max = Column(Integer, nullable=True)
    confidence = Column(Float, nullable=True)
    risk_level = Column(String(20), nullable=True)
    report = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)


# Async engine -- ``echo=False`` suppresses SQL statement logging
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,
    echo=False,
)

AsyncSessionLocal: async_sessionmaker[AsyncSession] = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class PostgresMemory:
    """Async manager for persisting and retrieving conversation turns.

    Uses SQLAlchemy async sessions backed by ``asyncpg``.  Each method
    opens its own session to keep transactions short-lived.
    """

    async def add_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: str,
    ) -> None:
        """Persist a single chat turn to the database.

        Args:
            session_id: UUID string for the conversation thread.
            role: Speaker role -- ``"user"`` or ``"assistant"``.
            content: The message text to store.
            user_id: Authenticated user identifier for multi-tenancy.

        Raises:
            sqlalchemy.exc.SQLAlchemyError: On database write failure.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                msg = ChatHistory(
                    session_id=session_id,
                    role=role,
                    content=content,
                    user_id=user_id,
                )
                session.add(msg)
                # ``session.begin()`` commits automatically on exit

    async def get_history(
        self,
        session_id: str,
        limit: int = 10,
    ) -> Sequence[ChatHistory]:
        """Retrieve the most recent *limit* messages for a session.

        Messages are returned in chronological order (oldest first)
        to match the format expected by LLM ``messages`` lists.

        Args:
            session_id: The conversation thread identifier.
            limit: Maximum number of messages to return.  Fetches the
                *newest* ``limit`` rows, then reverses them.

        Returns:
            A sequence of ``ChatHistory`` ORM objects ordered oldest
            to newest.

        Example:
            >>> history = await postgres_memory.get_history(
            ...     "session-abc", limit=6
            ... )
            >>> messages = [
            ...     {"role": m.role, "content": m.content}
            ...     for m in history
            ... ]
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(ChatHistory.session_id == session_id)
                .order_by(ChatHistory.created_at.desc())
                .limit(limit)
            )
            # Reverse to restore chronological (oldest -> newest) order
            rows = result.scalars().all()
            return list(reversed(rows))

    async def get_user_sessions(self, user_id: str, limit: int = 50) -> list[dict]:
        """Return sessions for a user, newest-first.

        Each dict contains:
            session_id, started_at, last_activity, message_count, preview.

        ``preview`` is the content of the first user message, truncated to
        120 characters.
        """
        sql = text("""
            WITH first_user_msg AS (
                SELECT
                    session_id,
                    content,
                    ROW_NUMBER() OVER (
                        PARTITION BY session_id ORDER BY created_at ASC
                    ) AS rn
                FROM chat_history
                WHERE user_id = :user_id AND role = 'user'
            )
            SELECT
                ch.session_id,
                MIN(ch.created_at)  AS started_at,
                MAX(ch.created_at)  AS last_activity,
                COUNT(*)            AS message_count,
                MAX(fum.content)    AS preview
            FROM chat_history ch
            LEFT JOIN first_user_msg fum
                ON fum.session_id = ch.session_id AND fum.rn = 1
            WHERE ch.user_id = :user_id
            GROUP BY ch.session_id
            ORDER BY MAX(ch.created_at) DESC
            LIMIT :limit
        """)
        async with AsyncSessionLocal() as session:
            result = await session.execute(sql, {"user_id": user_id, "limit": limit})
            rows = result.mappings().all()
            return [
                {
                    "session_id": r["session_id"],
                    "started_at": r["started_at"].isoformat()
                    if r["started_at"]
                    else None,
                    "last_activity": r["last_activity"].isoformat()
                    if r["last_activity"]
                    else None,
                    "message_count": r["message_count"],
                    "preview": (r["preview"] or "")[:120],
                }
                for r in rows
            ]

    async def get_session_messages(self, session_id: str, user_id: str) -> list[dict]:
        """Return all messages for a session in chronological order.

        Validates ownership: returns [] if the session belongs to a different user.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(ChatHistory)
                .where(
                    ChatHistory.session_id == session_id,
                    ChatHistory.user_id == user_id,
                )
                .order_by(ChatHistory.created_at.asc())
            )
            rows = result.scalars().all()
            return [
                {
                    "id": r.id,
                    "role": r.role,
                    "content": r.content,
                    "created_at": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]

    # ------------------------------------------------------------------
    # Ingestion job persistence
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # User account management
    # ------------------------------------------------------------------

    async def create_user(
        self,
        username: str,
        email: str,
        full_name: str,
        court_station: str,
        role: str,
        staff_number: str | None = None,
    ) -> None:
        """Insert a new user row with status ``pending``.

        Called when judicial staff submit a registration request.  The
        account cannot be used until an administrator approves it and the
        user activates it via the emailed link.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    User(
                        username=username,
                        email=email,
                        full_name=full_name,
                        court_station=court_station,
                        role=role,
                        staff_number=staff_number,
                        status="pending",
                    )
                )

    async def get_user_by_username(self, username: str) -> dict | None:
        """Return a user dict by username, or ``None`` if not found.

        Used during login and registration uniqueness checks.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.username == username)
            )
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_user_by_email(self, email: str) -> dict | None:
        """Return a user dict by email address, or ``None`` if not found.

        Used during registration to enforce email uniqueness.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.email == email))
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_user_by_id(self, user_id: str) -> dict | None:
        """Return a user dict by primary-key UUID, or ``None`` if not found."""
        async with AsyncSessionLocal() as session:
            result = await session.execute(select(User).where(User.id == user_id))
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_user_by_activation_token(self, token: str) -> dict | None:
        """Return a user in ``approved`` status matching the one-time token.

        Returns ``None`` if the token is unknown or the account has already
        been activated (status transitions away from ``approved`` on use).
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(
                    User.activation_token == token,
                    User.status == "approved",
                    User.activation_token_expires_at > datetime.utcnow(),
                )
            )
            row = result.scalar_one_or_none()
            return _user_to_dict(row) if row else None

    async def get_pending_users(self) -> list[dict]:
        """Return all users with status ``pending``, newest-first.

        Called by the admin approval endpoint to list unreviewed requests.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User)
                .where(User.status == "pending")
                .order_by(User.created_at.desc())
            )
            rows = result.scalars().all()
            return [_user_to_dict(r) for r in rows]

    async def approve_user(
        self,
        user_id: str,
        role: str,
        activation_token: str,
        approved_by: str,
    ) -> None:
        """Transition a user from ``pending`` to ``approved`` and store the
        one-time ``activation_token``.

        The administrator may override the role requested during registration.
        The token is later consumed by ``activate_user``.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(
                        status="approved",
                        role=role,
                        activation_token=activation_token,
                        activation_token_expires_at=datetime.utcnow()
                        + timedelta(days=settings.ACTIVATION_TOKEN_TTL_DAYS),
                        approved_by=approved_by,
                    )
                )

    async def activate_user(self, user_id: str, hashed_password: str) -> None:
        """Set the user's bcrypt password hash, mark status ``active``, and
        consume the one-time activation token.

        After this call the user can log in via ``POST /api/v1/auth/login``.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                await session.execute(
                    update(User)
                    .where(User.id == user_id)
                    .values(
                        status="active",
                        hashed_password=hashed_password,
                        activation_token=None,
                        activated_at=datetime.utcnow(),
                    )
                )

    # ------------------------------------------------------------------
    # Feedback persistence
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Verification activity persistence
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # Prediction history persistence
    # ------------------------------------------------------------------

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

    # ------------------------------------------------------------------
    # User status management
    # ------------------------------------------------------------------

    async def get_users(self, status: str | None = None) -> list[dict]:
        """Return all users, optionally filtered by status, newest-first.

        Args:
            status: Optional status filter (``"pending"``, ``"active"``,
                ``"suspended"``, ``"approved"``).  ``None`` returns all users.
        """
        async with AsyncSessionLocal() as session:
            query = select(User).order_by(User.created_at.desc())
            if status is not None:
                query = query.where(User.status == status)
            result = await session.execute(query)
            rows = result.scalars().all()
            return [_user_to_dict(r) for r in rows]

    async def update_user_status(self, user_id: str, new_status: str) -> bool:
        """Set the ``status`` field on a user row.

        Args:
            user_id: Primary-key UUID of the user to update.
            new_status: Target status string (e.g. ``"suspended"`` or ``"active"``).

        Returns:
            ``True`` if a row was matched and updated, ``False`` if not found.
        """
        async with AsyncSessionLocal() as session:
            async with session.begin():
                result = await session.execute(
                    update(User).where(User.id == user_id).values(status=new_status)
                )
                return result.rowcount > 0  # type: ignore[attr-defined]

    async def seed_admin(
        self,
        username: str,
        email: str,
        full_name: str,
        hashed_password: str,
    ) -> bool:
        """Create the default admin account if no admin user exists yet.

        Idempotent — safe to call on every startup.  Does nothing if any
        user with ``role="admin"`` already exists in the database.

        Args:
            username: Login username for the admin account.
            email: Email address for the admin account.
            full_name: Display name shown in the UI.
            hashed_password: Bcrypt hash of the initial password.

        Returns:
            ``True`` if the admin was created, ``False`` if one already exists.
        """
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(User).where(User.role == "admin").limit(1)
            )
            if result.scalar_one_or_none() is not None:
                return False

        async with AsyncSessionLocal() as session:
            async with session.begin():
                session.add(
                    User(
                        username=username,
                        email=email,
                        full_name=full_name,
                        hashed_password=hashed_password,
                        role="admin",
                        court_station="Judiciary Headquarters",
                        status="active",
                        activated_at=datetime.utcnow(),
                    )
                )
        return True


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


def _user_to_dict(row: User) -> dict:
    """Serialise a ``User`` ORM row to a plain dict (excludes hashed_password from most uses)."""
    return {
        "id": row.id,
        "username": row.username,
        "email": row.email,
        "full_name": row.full_name,
        "role": row.role,
        "court_station": row.court_station,
        "staff_number": row.staff_number,
        "status": row.status,
        "hashed_password": row.hashed_password,
        "activation_token": row.activation_token,
        "approved_by": row.approved_by,
        "activation_token_expires_at": row.activation_token_expires_at.isoformat()
        if row.activation_token_expires_at
        else None,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "activated_at": row.activated_at.isoformat() if row.activated_at else None,
    }


# Global singleton -- stateless; no lifecycle management required
postgres_memory = PostgresMemory()
