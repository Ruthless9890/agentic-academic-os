import os
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase

DATABASE_URL = os.environ["DATABASE_URL"]

# Railway gives postgresql:// but asyncpg needs postgresql+asyncpg://
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=False)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.create_all)
        # idempotent column add for DBs created before pending_update_assignment_id existed
        await conn.execute(text(
            "ALTER TABLE conversation_sessions "
            "ADD COLUMN IF NOT EXISTS pending_update_assignment_id INTEGER REFERENCES assignments(id)"
        ))
        # idempotent column adds for DBs created before document_chunks gained doc_type/filename/created_at
        await conn.execute(text(
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS doc_type VARCHAR(32) NOT NULL DEFAULT 'syllabus'"
        ))
        await conn.execute(text(
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS filename VARCHAR(255)"
        ))
        await conn.execute(text(
            "ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS created_at TIMESTAMP NOT NULL DEFAULT now()"
        ))
