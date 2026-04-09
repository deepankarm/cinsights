from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import (
    CodingSession,
    Insight,
    InsightCategory,
    InsightSeverity,
    SessionStatus,
    ToolCall,
)

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

class ToolCallRead(BaseModel):
    id: str
    tool_name: str
    input_value: str | None
    output_value: str | None
    duration_ms: float | None
    success: bool
    timestamp: datetime


class InsightRead(BaseModel):
    id: str
    category: InsightCategory
    title: str
    content: str
    severity: InsightSeverity
    created_at: datetime


class SessionRead(BaseModel):
    id: str
    session_id: str | None
    user_id: str | None
    project_name: str | None
    start_time: datetime
    end_time: datetime | None
    model: str | None
    total_tokens: int
    status: SessionStatus
    tool_call_count: int
    insight_count: int


class SessionDetail(BaseModel):
    id: str
    session_id: str | None
    user_id: str | None
    project_name: str | None
    start_time: datetime
    end_time: datetime | None
    model: str | None
    total_tokens: int
    prompt_tokens: int
    completion_tokens: int
    context_growth: list[dict] | None = None
    status: SessionStatus
    tool_calls: list[ToolCallRead]
    insights: list[InsightRead]


class StatsResponse(BaseModel):
    total_sessions: int
    analyzed_sessions: int
    total_insights: int
    top_tools: dict[str, int]
    insight_counts: dict[str, int]

@router.get("/", response_model=list[SessionRead])
async def list_sessions(
    skip: int = 0,
    limit: int = 20,
    status: SessionStatus | None = None,
    user_id: str | None = None,
    project_name: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[SessionRead]:
    """List sessions with pagination and optional filters."""
    query = select(CodingSession).order_by(col(CodingSession.start_time).desc())
    if status:
        query = query.where(CodingSession.status == status)
    if user_id:
        query = query.where(CodingSession.user_id == user_id)
    if project_name:
        query = query.where(CodingSession.project_name == project_name)
    query = query.offset(skip).limit(limit)

    result = await db.exec(query)
    sessions = result.all()
    if not sessions:
        return []

    session_ids = [s.id for s in sessions]

    # Batch counts: one query each for tool_calls and insights, grouped by session.
    tc_result = await db.exec(
        select(ToolCall.session_id, func.count())
        .where(col(ToolCall.session_id).in_(session_ids))
        .group_by(ToolCall.session_id)
    )
    tool_counts: dict[str, int] = {sid: cnt for sid, cnt in tc_result.all()}

    ins_result = await db.exec(
        select(Insight.session_id, func.count())
        .where(col(Insight.session_id).in_(session_ids))
        .group_by(Insight.session_id)
    )
    insight_counts: dict[str, int] = {sid: cnt for sid, cnt in ins_result.all()}

    return [
        SessionRead(
            id=s.id,
            session_id=s.session_id,
            user_id=s.user_id,
            project_name=s.project_name,
            start_time=s.start_time,
            end_time=s.end_time,
            model=s.model,
            total_tokens=s.total_tokens,
            status=s.status,
            tool_call_count=tool_counts.get(s.id, 0),
            insight_count=insight_counts.get(s.id, 0),
        )
        for s in sessions
    ]


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: AsyncSession = Depends(get_db)) -> StatsResponse:
    """Aggregate stats across all sessions."""
    total_result = await db.exec(select(func.count()).select_from(CodingSession))
    total = total_result.one()
    analyzed_result = await db.exec(
        select(func.count())
        .select_from(CodingSession)
        .where(CodingSession.status == SessionStatus.ANALYZED)
    )
    analyzed = analyzed_result.one()
    insights_result = await db.exec(select(func.count()).select_from(Insight))
    total_insights = insights_result.one()

    # Top tools
    tool_result = await db.exec(
        select(ToolCall.tool_name, func.count())
        .group_by(ToolCall.tool_name)
        .order_by(func.count().desc())
        .limit(10)
    )
    top_tools = {name: count for name, count in tool_result.all()}

    # Insight counts by category
    insight_result = await db.exec(
        select(Insight.category, func.count()).group_by(Insight.category)
    )
    insight_counts = {cat: count for cat, count in insight_result.all()}

    return StatsResponse(
        total_sessions=total,
        analyzed_sessions=analyzed,
        total_insights=total_insights,
        top_tools=top_tools,
        insight_counts=insight_counts,
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session_detail(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> SessionDetail:
    """Get session detail with tool calls and insights."""
    session = await db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tc_result = await db.exec(
        select(ToolCall)
        .where(ToolCall.session_id == session_id)
        .order_by(ToolCall.timestamp)
    )
    tool_calls = tc_result.all()

    ins_result = await db.exec(
        select(Insight)
        .where(Insight.session_id == session_id)
        .order_by(Insight.created_at)
    )
    insights = ins_result.all()

    return SessionDetail(
        id=session.id,
        session_id=session.session_id,
        user_id=session.user_id,
        project_name=session.project_name,
        start_time=session.start_time,
        end_time=session.end_time,
        model=session.model,
        total_tokens=session.total_tokens,
        prompt_tokens=session.prompt_tokens,
        completion_tokens=session.completion_tokens,
        context_growth=(
            json.loads(session.context_growth_json) if session.context_growth_json else None
        ),
        status=session.status,
        tool_calls=[
            ToolCallRead(
                id=tc.id,
                tool_name=tc.tool_name,
                input_value=tc.input_value,
                output_value=tc.output_value,
                duration_ms=tc.duration_ms,
                success=tc.success,
                timestamp=tc.timestamp,
            )
            for tc in tool_calls
        ],
        insights=[
            InsightRead(
                id=ins.id,
                category=ins.category,
                title=ins.title,
                content=ins.content,
                severity=ins.severity,
                created_at=ins.created_at,
            )
            for ins in insights
        ],
    )


class SessionUpdate(BaseModel):
    project_name: str | None = None


@router.patch("/{session_id}")
async def update_session(
    session_id: str,
    body: SessionUpdate,
    db: AsyncSession = Depends(get_db),
) -> dict[str, bool]:
    """Update session metadata (e.g., manual project tagging)."""
    session = await db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.project_name is not None:
        session.project_name = body.project_name

    await db.commit()
    return {"ok": True}


@router.post("/{session_id}/analyze", response_model=SessionDetail)
async def trigger_analysis(
    session_id: str, db: AsyncSession = Depends(get_db)
) -> SessionDetail:
    """Manually trigger LLM analysis for a session."""
    import asyncio

    from cinsights.analysis.session import SessionAnalyzer
    from cinsights.config import get_settings
    from cinsights.sources.base import TraceData
    from cinsights.sources.phoenix import PhoenixSource

    session = await db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    # PhoenixSource is sync (HTTP via the phoenix client), so we run its blocking
    # call in a thread to keep the event loop free.
    source = PhoenixSource(base_url=settings.phoenix_endpoint)
    spans = await asyncio.to_thread(source.get_spans, session_id)
    if not spans:
        raise HTTPException(status_code=404, detail="No spans found for session")

    trace = TraceData(
        trace_id=session_id,
        start_time=session.start_time,
        end_time=session.end_time or session.start_time,
        spans=spans,
    )

    # Clear existing insights
    existing_result = await db.exec(
        select(Insight).where(Insight.session_id == session_id)
    )
    for ins in existing_result.all():
        await db.delete(ins)
    await db.flush()

    extra_headers = None
    if settings.anthropic_extra_headers:
        extra_headers = json.loads(settings.anthropic_extra_headers)

    analyzer = SessionAnalyzer(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        base_url=settings.anthropic_base_url,
        extra_headers=extra_headers,
    )
    result = await analyzer.analyze(trace, spans)

    for item in result.insights:
        try:
            cat = InsightCategory(item.category)
        except ValueError:
            cat = InsightCategory.PATTERN
        try:
            sev = InsightSeverity(item.severity)
        except ValueError:
            sev = InsightSeverity.INFO

        insight = Insight(
            session_id=session_id,
            category=cat,
            title=item.title,
            content=item.content,
            severity=sev,
        )
        db.add(insight)

    session.status = SessionStatus.ANALYZED
    await db.commit()
    await db.refresh(session)

    return await get_session_detail(session_id, db)
