# libs/schemas/chat.py
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class Message(BaseModel):
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ChatRequest(BaseModel):
    message: str
    session_id: str | None = None
    stream: bool = True

    # Optional filters for advanced users (e.g., "only search HR docs")
    filters: dict[str, Any] | None = None


class ChatResponse(BaseModel):
    """
    Standard response structure for non-streaming calls
    """

    answer: str
    session_id: str
    # Citations are critical for "Industrial" RAG to build trust
    citations: list[dict[str, str]] = []  # [{"source": "doc.pdf", "text": "..."}]
    latency_ms: float


class RetrievalResult(BaseModel):
    """
    Used by Retriever Node
    """

    content: str
    source: str
    score: float
    metadata: dict[str, Any]
