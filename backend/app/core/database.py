"""
Async SQLAlchemy engine + session factory.

Why async all the way:
    FastAPI is async. A sync DB call inside an async route blocks the event
    loop and collapses throughput. Using asyncpg + AsyncSession keeps every
    I/O operation cooperative.

Why one engine per process (not per-request):
    Creating an engine allocates a connection pool. Pools are expensive and
    meant to be long-lived — one engine, many short-lived sessions.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

settings = get_settings()

# pool_pre_ping=True issues a cheap SELECT 1 before handing out a pooled
# connection. This prevents the classic "MySQL has gone away" / "connection
# closed" errors after a DB restart or idle timeout, at the cost of one
# extra round trip per checkout.
engine = create_async_engine(
    settings.DATABASE_URL,
    pool_pre_ping=True,
    # echo=True would log every SQL statement; useful for development but
    # noisy and PII-leaky in production. Keep False and use DB-side logging
    # if query visibility is needed.
    echo=False,
)

# expire_on_commit=False: after session.commit() SQLAlchemy would mark all
# loaded objects as expired, causing a silent SELECT when any attribute is
# accessed. That breaks in async contexts (no implicit I/O allowed) and
# hurts perf even in sync. We explicitly refresh when needed instead.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency: yields a session, guarantees cleanup.

    The `async with` block ensures the session is closed even if the route
    raises, returning the connection to the pool. We intentionally do NOT
    commit here — routes commit explicitly so partial writes don't sneak
    through on a handler that forgot to error out cleanly.
    """
    async with AsyncSessionLocal() as session:
        yield session
