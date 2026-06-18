from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from services.db import SessionLocal


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
