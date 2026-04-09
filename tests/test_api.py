from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.models import (
    CodingSession,
    Insight,
    InsightCategory,
    InsightSeverity,
    SessionStatus,
    ToolCall,
)


async def _seed_data(db_engine) -> None:
    sessionmaker = async_sessionmaker(
        db_engine, class_=AsyncSession, expire_on_commit=False
    )
    async with sessionmaker() as db:
        session = CodingSession(
            id="trace-100",
            session_id="session-100",
            start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
            model="claude-sonnet-4-20250514",
            total_tokens=8000,
            status=SessionStatus.ANALYZED,
        )
        db.add(session)

        tc = ToolCall(
            session_id="trace-100",
            span_id="span-100",
            tool_name="Read",
            duration_ms=50.0,
            success=True,
            timestamp=datetime(2026, 4, 1, 10, 1, tzinfo=UTC),
        )
        db.add(tc)

        insight = Insight(
            session_id="trace-100",
            category=InsightCategory.SUMMARY,
            title="Session Summary",
            content="The session focused on debugging a Go concurrency issue.",
            severity=InsightSeverity.INFO,
        )
        db.add(insight)
        await db.commit()


async def test_list_sessions_empty(client):
    r = await client.get("/api/sessions/")
    assert r.status_code == 200
    assert r.json() == []


async def test_list_sessions(client, db_engine):
    await _seed_data(db_engine)
    r = await client.get("/api/sessions/")
    assert r.status_code == 200
    data = r.json()
    assert len(data) == 1
    assert data[0]["id"] == "trace-100"
    assert data[0]["tool_call_count"] == 1
    assert data[0]["insight_count"] == 1


async def test_get_session_detail(client, db_engine):
    await _seed_data(db_engine)
    r = await client.get("/api/sessions/trace-100")
    assert r.status_code == 200
    data = r.json()
    assert data["model"] == "claude-sonnet-4-20250514"
    assert len(data["tool_calls"]) == 1
    assert data["tool_calls"][0]["tool_name"] == "Read"
    assert len(data["insights"]) == 1
    assert data["insights"][0]["category"] == "summary"


async def test_get_session_not_found(client):
    r = await client.get("/api/sessions/nonexistent")
    assert r.status_code == 404


async def test_get_stats(client, db_engine):
    await _seed_data(db_engine)
    r = await client.get("/api/sessions/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_sessions"] == 1
    assert data["analyzed_sessions"] == 1
    assert data["total_insights"] == 1
    assert "Read" in data["top_tools"]


async def test_list_sessions_filter_status(client, db_engine):
    await _seed_data(db_engine)
    r = await client.get("/api/sessions/?status=pending")
    assert r.status_code == 200
    assert len(r.json()) == 0

    r = await client.get("/api/sessions/?status=analyzed")
    assert r.status_code == 200
    assert len(r.json()) == 1
