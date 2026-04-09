from datetime import UTC, datetime

from cinsights.db.models import (
    CodingSession,
    Insight,
    InsightCategory,
    InsightSeverity,
    SessionStatus,
    ToolCall,
)


async def test_create_session(db):
    session = CodingSession(
        id="trace-001",
        session_id="session-001",
        start_time=datetime(2026, 4, 1, tzinfo=UTC),
        end_time=datetime(2026, 4, 1, 0, 30, tzinfo=UTC),
        model="claude-sonnet-4-20250514",
        total_tokens=5000,
    )
    db.add(session)
    await db.commit()

    fetched = await db.get(CodingSession, "trace-001")
    assert fetched is not None
    assert fetched.session_id == "session-001"
    assert fetched.status == SessionStatus.PENDING
    assert fetched.total_tokens == 5000


async def test_create_tool_call(db):
    session = CodingSession(
        id="trace-002",
        start_time=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db.add(session)
    await db.commit()

    tc = ToolCall(
        session_id="trace-002",
        span_id="span-001",
        tool_name="Bash",
        input_value="ls -la",
        output_value="total 0",
        duration_ms=150.5,
        success=True,
        timestamp=datetime(2026, 4, 1, 0, 1, tzinfo=UTC),
    )
    db.add(tc)
    await db.commit()
    await db.refresh(tc)

    assert tc.id is not None
    assert tc.tool_name == "Bash"
    assert tc.duration_ms == 150.5


async def test_create_insight(db):
    session = CodingSession(
        id="trace-003",
        start_time=datetime(2026, 4, 1, tzinfo=UTC),
    )
    db.add(session)
    await db.commit()

    insight = Insight(
        session_id="trace-003",
        category=InsightCategory.FRICTION,
        title="Repeated file read failures",
        content="Agent tried to read non-existent files 3 times.",
        severity=InsightSeverity.WARNING,
    )
    db.add(insight)
    await db.commit()
    await db.refresh(insight)

    assert insight.category == InsightCategory.FRICTION
    assert insight.severity == InsightSeverity.WARNING
