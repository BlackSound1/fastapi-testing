from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

SQLALCHEMY_DATABASE_URL = "sqlite+aiosqlite:///./blog.db"

# DB connection. SQLite normally allows only 1 thread,
# but FastAPI can handle many. So we disable that threading restriction.
engine = create_async_engine(
    SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False}
)

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
