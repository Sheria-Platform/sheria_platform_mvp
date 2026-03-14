# services/api/app/memory/models.py
"""Re-exports for backward compatibility.

The authoritative ORM definitions live in ``postgres.py`` alongside the
engine and session factory.  This module re-exports them so any code that
imports from ``memory.models`` continues to work without modification.
"""

from services.api.app.memory.postgres import Base, ChatHistory

__all__ = ["Base", "ChatHistory"]
