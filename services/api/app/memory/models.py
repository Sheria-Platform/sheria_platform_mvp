# services/api/app/memory/models.py
"""ORM models, engine, and async session factory for the PostgreSQL data layer.

All SQLAlchemy model classes and the shared database connection objects live
here so that individual repository modules can import only what they need
without circular dependencies.
"""

import uuid
from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Float,
    Integer,
    String,
    Text,
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
    """ORM model for the ``users`` table -- judicial staff accounts."""

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
    """ORM model for the ``verification_activity`` table -- audit log of document authentications."""

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
    """ORM model for the ``feedback`` table -- user ratings for assistant responses."""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, nullable=False)
    user_id = Column(String, nullable=False)
    message_id = Column(Integer, nullable=False)
    score = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class PredictionHistory(Base):
    """ORM model for the ``prediction_history`` table -- audit log of case duration forecasts."""

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
