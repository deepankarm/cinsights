"""Tests for API endpoints (users, projects, digests, stats, trends).

Uses the in-memory DB fixture from conftest.py. Tests endpoint routing,
response shapes, and basic query behavior — not business logic.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlmodel import SQLModel
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import (
    CodingSession,
    SessionStatus,
)


@pytest_asyncio.fixture
async def full_client():
    """Client with all API routers wired up."""
    from cinsights.api.digest import router as digest_router
    from cinsights.api.projects import router as projects_router
    from cinsights.api.sessions import router as sessions_router
    from cinsights.api.users import router as users_router

    engine = create_async_engine(
        "sqlite+aiosqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)

    sessionmaker = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    @asynccontextmanager
    async def noop_lifespan(app: FastAPI) -> AsyncIterator[None]:
        yield

    app = FastAPI(lifespan=noop_lifespan)
    app.include_router(sessions_router)
    app.include_router(users_router)
    app.include_router(projects_router)
    app.include_router(digest_router)

    async def override_get_db() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db

    # Seed test data
    async with sessionmaker() as db:
        session = CodingSession(
            id=str(uuid4()),
            session_id="sess-1",
            trace_id="trace-1",
            tenant_id="default",
            source="local",
            user_id="alice",
            project_name="myapp",
            agent_type="claude-code",
            status=SessionStatus.ANALYZED,
            start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
            total_tokens=5000,
            prompt_tokens=4000,
            completion_tokens=1000,
            turn_count=10,
            read_edit_ratio=5.0,
            error_rate=3.0,
        )
        db.add(session)

        session2 = CodingSession(
            id=str(uuid4()),
            session_id="sess-2",
            trace_id="trace-2",
            tenant_id="default",
            source="local",
            user_id="bob",
            project_name="myapp",
            agent_type="claude-code",
            status=SessionStatus.INDEXED,
            start_time=datetime(2026, 4, 1, 11, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 1, 11, 15, tzinfo=UTC),
            total_tokens=2000,
            prompt_tokens=1500,
            completion_tokens=500,
            turn_count=5,
        )
        db.add(session2)
        await db.commit()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c

    await engine.dispose()


# --- Users ---


@pytest.mark.asyncio
async def test_list_users(full_client):
    resp = await full_client.get("/api/users/")
    assert resp.status_code == 200
    users = resp.json()
    assert len(users) == 2
    ids = {u["user_id"] for u in users}
    assert ids == {"alice", "bob"}


@pytest.mark.asyncio
async def test_list_users_has_metrics(full_client):
    resp = await full_client.get("/api/users/")
    alice = next(u for u in resp.json() if u["user_id"] == "alice")
    assert alice["session_count"] == 1
    assert alice["analyzed_count"] == 1


# --- Projects ---


@pytest.mark.asyncio
async def test_list_projects(full_client):
    resp = await full_client.get("/api/projects/")
    assert resp.status_code == 200
    projects = resp.json()
    assert len(projects) == 1
    assert projects[0]["name"] == "myapp"
    assert projects[0]["session_count"] == 2
    assert projects[0]["developer_count"] == 2


# --- Sessions ---


@pytest.mark.asyncio
async def test_list_sessions(full_client):
    resp = await full_client.get("/api/sessions/")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2


@pytest.mark.asyncio
async def test_list_sessions_filter_by_user(full_client):
    resp = await full_client.get("/api/sessions/?user_id=alice")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == "alice"


@pytest.mark.asyncio
async def test_list_sessions_filter_by_project(full_client):
    resp = await full_client.get("/api/sessions/?project_name=myapp")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


@pytest.mark.asyncio
async def test_list_sessions_filter_by_status(full_client):
    resp = await full_client.get("/api/sessions/?status=analyzed")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["user_id"] == "alice"


# --- Digests ---


@pytest.mark.asyncio
async def test_list_digests_empty(full_client):
    resp = await full_client.get("/api/digests/")
    assert resp.status_code == 200
    assert resp.json() == []
