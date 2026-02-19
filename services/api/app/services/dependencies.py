from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from services.api.app.core.database import get_db
from services.api.app.memory.postgres import PostgresMemory


async def get_memory(db: AsyncSession = Depends(get_db)) -> PostgresMemory:
    return PostgresMemory(db_session=db)
