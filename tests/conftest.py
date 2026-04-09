import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

# Force test settings before any app imports
os.environ["CINSIGHTS_DATABASE_URL"] = "sqlite+aiosqlite://"
os.environ["CINSIGHTS_PHOENIX_ENDPOINT"] = "http://localhost:6006"
os.environ.setdefault("ANTHROPIC_API_KEY", "test-key")


@pytest_asyncio.fixture
async def db_engine():
    """Async in-memory SQLite engine for tests.

    StaticPool keeps the single connection alive so all sessions in a test see
    the same in-memory DB. We create the schema directly via run_sync since
    tests don't run alembic migrations.
    """
    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def db(db_engine) -> AsyncIterator[AsyncSession]:
    sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with sessionmaker() as session:
        yield session


@pytest_asyncio.fixture
async def client(db_engine) -> AsyncIterator[AsyncClient]:
    """Async HTTP client for FastAPI tests, wired to the per-test in-memory DB.

    Uses httpx.AsyncClient + ASGITransport so the app, the test, and the DB
    layer all live in the same event loop. The get_db dependency is overridden
    to yield an AsyncSession bound to the test engine.
    """
    from cinsights.api.sessions import router as sessions_router
    from cinsights.db.engine import get_db

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    test_app = FastAPI(lifespan=noop_lifespan)
    test_app.include_router(sessions_router)

    sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    test_app.dependency_overrides[get_db] = override_get_db

    transport = ASGITransport(app=test_app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
