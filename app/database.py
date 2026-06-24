import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

engine_kwargs = {"echo": settings.debug}
if settings.raw_database_url:
    engine_kwargs["pool_recycle"] = 300
    engine_kwargs["pool_pre_ping"] = True
    engine = create_async_engine(settings.database_url, **engine_kwargs)
else:
    sqlite_path = os.getenv("SQLITE_PATH", "./canas.db")
    engine = create_async_engine(f"sqlite+aiosqlite:///{sqlite_path}", **engine_kwargs)

async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with async_session() as session:
        try:
            yield session
        finally:
            await session.close()


NEW_COLUMNS = {
    "body_measurements": [
        "grasa_corporal FLOAT",
        "musculo FLOAT",
        "agua FLOAT",
        "hueso FLOAT",
        "imc FLOAT",
        "grasa_visceral FLOAT",
        "metabolismo_basal FLOAT",
        "grasa_subcutanea FLOAT",
        "proteina FLOAT",
        "masa_muscular_kg FLOAT",
        "edad_corporal FLOAT",
    ],
    "exercises": [
        "target_muscles TEXT",
        "equipment VARCHAR(200)",
    ],
    "food_catalog": [
        "grupo VARCHAR(50)",
        "instrucciones TEXT",
    ]
}


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    dialect = engine.dialect.name
    if dialect in ("postgresql", "sqlite"):
        async with engine.begin() as conn:
            for table, cols in NEW_COLUMNS.items():
                for col_def in cols:
                    try:
                        if dialect == "postgresql":
                            await conn.execute(
                                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col_def}")
                            )
                        elif dialect == "sqlite":
                            col_name = col_def.split()[0]
                            await conn.execute(
                                text(f"ALTER TABLE {table} ADD COLUMN {col_def}")
                            )
                    except Exception:
                        pass
