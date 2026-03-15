# services/api/app/routes/history.py
"""Chat history endpoints.

Exposes persisted conversation data from the ``chat_history`` PostgreSQL table
to authenticated users.  Two endpoints:

- ``GET /sessions``        — list all sessions for the current user
- ``GET /sessions/{id}``   — all messages within a specific session
"""

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from services.api.app.auth.jwt import get_current_user
from services.api.app.dependencies import get_memory
from services.api.app.memory.postgres import PostgresMemory

router = APIRouter()


# ── Pydantic response models ──────────────────────────────────────────────────


class SessionSummary(BaseModel):
    session_id: str
    started_at: str
    last_activity: str
    message_count: int
    preview: str


class MessageRecord(BaseModel):
    id: int
    role: str
    content: str
    created_at: str


# ── Routes ────────────────────────────────────────────────────────────────────


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    user: dict = Depends(get_current_user),
    memory: PostgresMemory = Depends(get_memory),
) -> list[SessionSummary]:
    """Return all sessions for the authenticated user, newest-first."""
    rows = await memory.get_user_sessions(user["id"])
    return [SessionSummary(**r) for r in rows]


@router.get("/sessions/{session_id}", response_model=list[MessageRecord])
async def get_session(
    session_id: str,
    user: dict = Depends(get_current_user),
    memory: PostgresMemory = Depends(get_memory),
) -> list[MessageRecord]:
    """Return all messages in a session.

    Returns 404 if the session does not exist or belongs to another user.
    """
    rows = await memory.get_session_messages(session_id, user["id"])
    if not rows:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Session not found or access denied.",
        )
    return [MessageRecord(**r) for r in rows]
