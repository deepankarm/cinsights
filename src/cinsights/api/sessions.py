from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, col, func, select

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


# --- Response schemas ---


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
    status: SessionStatus
    tool_calls: list[ToolCallRead]
    insights: list[InsightRead]


class StatsResponse(BaseModel):
    total_sessions: int
    analyzed_sessions: int
    total_insights: int
    top_tools: dict[str, int]
    insight_counts: dict[str, int]


# --- Endpoints ---


@router.get("/", response_model=list[SessionRead])
async def list_sessions(
    skip: int = 0,
    limit: int = 20,
    status: SessionStatus | None = None,
    user_id: str | None = None,
    project_name: str | None = None,
    db: Session = Depends(get_db),
):
    """List sessions with pagination and optional filters."""
    query = select(CodingSession).order_by(col(CodingSession.start_time).desc())
    if status:
        query = query.where(CodingSession.status == status)
    if user_id:
        query = query.where(CodingSession.user_id == user_id)
    if project_name:
        query = query.where(CodingSession.project_name == project_name)
    query = query.offset(skip).limit(limit)

    sessions = db.exec(query).all()

    results = []
    for s in sessions:
        tool_count = db.exec(
            select(func.count()).where(ToolCall.session_id == s.id)
        ).one()
        insight_count = db.exec(
            select(func.count()).where(Insight.session_id == s.id)
        ).one()
        results.append(
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
                tool_call_count=tool_count,
                insight_count=insight_count,
            )
        )
    return results


@router.get("/stats", response_model=StatsResponse)
async def get_stats(db: Session = Depends(get_db)):
    """Aggregate stats across all sessions."""
    total = db.exec(select(func.count()).select_from(CodingSession)).one()
    analyzed = db.exec(
        select(func.count())
        .select_from(CodingSession)
        .where(CodingSession.status == SessionStatus.ANALYZED)
    ).one()
    total_insights = db.exec(select(func.count()).select_from(Insight)).one()

    # Top tools
    tool_rows = db.exec(
        select(ToolCall.tool_name, func.count())
        .group_by(ToolCall.tool_name)
        .order_by(func.count().desc())
        .limit(10)
    ).all()
    top_tools = {name: count for name, count in tool_rows}

    # Insight counts by category
    insight_rows = db.exec(
        select(Insight.category, func.count()).group_by(Insight.category)
    ).all()
    insight_counts = {cat: count for cat, count in insight_rows}

    return StatsResponse(
        total_sessions=total,
        analyzed_sessions=analyzed,
        total_insights=total_insights,
        top_tools=top_tools,
        insight_counts=insight_counts,
    )


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session_detail(session_id: str, db: Session = Depends(get_db)):
    """Get session detail with tool calls and insights."""
    session = db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tool_calls = db.exec(
        select(ToolCall)
        .where(ToolCall.session_id == session_id)
        .order_by(ToolCall.timestamp)
    ).all()

    insights = db.exec(
        select(Insight)
        .where(Insight.session_id == session_id)
        .order_by(Insight.created_at)
    ).all()

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
    db: Session = Depends(get_db),
):
    """Update session metadata (e.g., manual project tagging)."""
    session = db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    if body.project_name is not None:
        session.project_name = body.project_name

    db.commit()
    return {"ok": True}


@router.post("/{session_id}/analyze", response_model=SessionDetail)
async def trigger_analysis(session_id: str, db: Session = Depends(get_db)):
    """Manually trigger LLM analysis for a session."""
    from cinsights.analysis.session import SessionAnalyzer
    from cinsights.config import get_settings
    from cinsights.sources.base import TraceData
    from cinsights.sources.phoenix import PhoenixSource

    session = db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    settings = get_settings()
    if not settings.anthropic_api_key:
        raise HTTPException(status_code=500, detail="ANTHROPIC_API_KEY not configured")

    source = PhoenixSource(base_url=settings.phoenix_endpoint)
    spans = source.get_spans(session_id)
    if not spans:
        raise HTTPException(status_code=404, detail="No spans found for session")

    trace = TraceData(
        trace_id=session_id,
        start_time=session.start_time,
        end_time=session.end_time or session.start_time,
        spans=spans,
    )

    # Clear existing insights
    existing_insights = db.exec(
        select(Insight).where(Insight.session_id == session_id)
    ).all()
    for ins in existing_insights:
        db.delete(ins)
    db.flush()

    import json

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
    db.commit()
    db.refresh(session)

    return await get_session_detail(session_id, db)
