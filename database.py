from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from config import settings


# DB connection. SQLite normally allows only 1 thread,
# but FastAPI can handle many. So we disable that threading restriction.
engine = create_async_engine(settings.database_url)

# Factory creating DB sessions. Each req should get its own session.
AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """Yields a new DB session"""
    async with AsyncSessionLocal() as session:
        yield session
