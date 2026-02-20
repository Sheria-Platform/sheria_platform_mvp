from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel


class ChatRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None


class ConversationRead(BaseModel):
    id: UUID
    title: str
    created_at: datetime
    updated_at: datetime | None

    class Config:
        from_attributes = True


class MessageContent(BaseModel):
    role: str
    text: str


class MessageRead(BaseModel):
    id: UUID
    content: MessageContent
    created_at: datetime

    class Config:
        from_attributes = True
