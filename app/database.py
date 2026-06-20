from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

if settings.raw_database_url:
    engine = create_async_engine(settings.database_url, echo=settings.debug)
else:
    sqlite_path = os.getenv("SQLITE_PATH", "./canas.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_path}", echo=settings.debug)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
