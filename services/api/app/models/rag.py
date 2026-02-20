import uuid

from sqlalchemy import (Column, DateTime, ForeignKey, String, Text, func, UUID)
from sqlalchemy.orm import relationship

from services.api.app.core.database import Base
from services.api.app.models.mixins import TimestampMixin


class Conversations(Base, TimestampMixin):
    __tablename__ = "conversations"

    id = Column(UUID(as_uuid=True), primary_key=True,
                default=uuid.uuid4, unique=True, nullable=False, index=True)
    title = Column(String(255), nullable=False)
    user_id = Column(UUID(as_uuid=True), nullable=False)

    messages = relationship("Messages",
                            back_populates="conversation",
                            cascade="all, delete-orphan",
                            order_by="Messages.created_at",
                            lazy="noload")


class Messages(Base):
    __tablename__ = "messages"

    id = Column(UUID(as_uuid=True), primary_key=True,
                default=uuid.uuid4, unique=True, nullable=False, index=True)
    content = Column(Text, nullable=False)
    role = Column(String(255), nullable=False)
    conversation_id = Column(UUID(as_uuid=True), ForeignKey(
        "conversations.id"), nullable=False)

    conversation = relationship("Conversations", back_populates="messages")
    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(), nullable=False)
