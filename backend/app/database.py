"""
Database engine, session factory, and base model.

Every SQLAlchemy model in the app inherits from Base defined here.
The async session factory creates database sessions that FastAPI
dependencies inject into route handlers.

Key design decisions:
- Async engine (asyncpg) — matches FastAPI's async nature
- Base model includes id, created_at, updated_at on every table
- tenant_id is NOT on the base model — it's on a TenantScopedBase
  so that tables like 'users' (which exist outside tenant scope)
  don't carry a meaningless tenant_id column
"""

import uuid
from datetime import datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from app.config import settings

# --- Engine ---
# The engine manages the actual database connection pool.
# echo=True in debug mode prints every SQL query — invaluable for learning,
# but turned off in production to avoid log noise.
engine = create_async_engine(
    settings.database_url,
    echo=settings.debug,
    # Pool settings: how many connections to keep open
    pool_size=20,
    max_overflow=10,
)

# --- Session Factory ---
# Creates async database sessions. Each request gets its own session
# via the get_db dependency. expire_on_commit=False means objects
# stay usable after a commit without re-querying — important for
# returning data in API responses after a save.
async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# --- Base Model ---
# Every table inherits from this. It gives every row:
# - a UUID primary key (not auto-increment integers — UUIDs are safe
#   to expose in URLs and don't leak how many records exist)
# - created_at: set automatically when the row is inserted
# - updated_at: set automatically on every update
class Base(DeclarativeBase):
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
    )
