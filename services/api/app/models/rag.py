from sqlalchemy import (Column, DateTime, Float, ForeignKey, Integer, String, Text, JSON,
                        func)

from services.api.app.core.database import Base


class ChatHistory(Base):
    """
    Stores every conversation turn.
    """

    __tablename__ = "chat_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, index=True)  # User's conversation ID
    user_id = Column(String, index=True)
    role = Column(String)  # "user" or "assistant"
    content = Column(Text)  # The text message
    metadata_ = Column(JSON, default={})  # Extra info (latency, tokens used)
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
