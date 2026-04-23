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
    label: str | None = None
    title: str
    content: str
    severity: InsightSeverity
    created_at: datetime


class SessionRead(BaseModel):
    id: str
    session_id: str | None
    user_id: str | None
    project_name: str | None
    agent_type: str | None = None
    source: str | None = None
    start_time: datetime
    end_time: datetime | None
    model: str | None
    total_tokens: int
    status: SessionStatus
    tool_call_count: int
    error_count: int
    insight_count: int
    active_duration_ms: float | None = None
    interrupt_count: int | None = None
    agent_version: str | None = None
    effort_level: str | None = None


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
    total_tool_calls: int = 0
    insights: list[InsightRead]
    notable_quotes: list[dict] | None = None
    interrupt_count: int | None = None
    agent_version: str | None = None
    effort_level: str | None = None
    adaptive_thinking_disabled: bool | None = None

    # Quality metrics
    read_edit_ratio: float | None = None
    edits_without_read_pct: float | None = None
    research_mutation_ratio: float | None = None
    error_rate: float | None = None
    write_vs_edit_pct: float | None = None
    repeated_edits_count: int | None = None
    tokens_per_useful_edit: float | None = None
    context_pressure_score: float | None = None

    # Token efficiency signals
    error_retry_sequences: int | None = None
    context_resets: int | None = None
    duplicate_read_count: int | None = None

    # Baseline averages for comparison
    baseline: dict | None = None


class StatsResponse(BaseModel):
    total_sessions: int
    analyzed_sessions: int
    total_insights: int
    total_tool_calls: int
    distinct_tool_count: int
    top_tools: dict[str, int]
    insight_counts: dict[str, int]


@router.get("/", response_model=list[SessionRead])
async def list_sessions(
    skip: int = 0,
    limit: int = 20,
    status: SessionStatus | None = None,
    user_id: str | None = None,
    project_name: str | None = None,
    label: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[SessionRead]:
    """List sessions with pagination and optional filters."""
    from sqlalchemy import case

    status_order = case(
        (CodingSession.status == "analyzed", 0),
        (CodingSession.status == "indexed", 1),
        else_=2,
    )
    query = select(CodingSession).order_by(
        status_order,
        col(CodingSession.start_time).desc(),
    )
    if status:
        query = query.where(CodingSession.status == status)
    if user_id:
        query = query.where(CodingSession.user_id == user_id)
    if project_name:
        query = query.where(CodingSession.project_name == project_name)
    if label:
        label_sessions = (
            select(Insight.session_id).where(Insight.cluster_label == label).distinct().subquery()
        )
        query = query.where(col(CodingSession.id).in_(select(label_sessions.c.session_id)))
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

    err_result = await db.exec(
        select(ToolCall.session_id, func.count())
        .where(col(ToolCall.session_id).in_(session_ids), ToolCall.success == False)  # noqa: E712
        .group_by(ToolCall.session_id)
    )
    error_counts: dict[str, int] = {sid: cnt for sid, cnt in err_result.all()}

    ins_result = await db.exec(
        select(Insight.session_id, func.count())
        .where(col(Insight.session_id).in_(session_ids))
        .group_by(Insight.session_id)
    )
    insight_counts: dict[str, int] = {sid: cnt for sid, cnt in ins_result.all()}

    import json as json_mod

    def _active_ms(s: CodingSession) -> float | None:
        if not s.context_growth_json:
            return None
        try:
            turns = json_mod.loads(s.context_growth_json)
            total = sum(t.get("duration_ms", 0) for t in turns)
            return total if total > 0 else None
        except Exception:
            return None

    return [
        SessionRead(
            id=s.id,
            session_id=s.session_id,
            user_id=s.user_id,
            project_name=s.project_name,
            agent_type=s.agent_type,
            source=s.source,
            start_time=s.start_time,
            end_time=s.end_time,
            model=s.model,
            total_tokens=s.total_tokens,
            status=s.status,
            tool_call_count=tool_counts.get(s.id, 0),
            error_count=error_counts.get(s.id, 0),
            insight_count=insight_counts.get(s.id, 0),
            active_duration_ms=_active_ms(s),
            interrupt_count=s.interrupt_count,
            agent_version=s.agent_version,
            effort_level=s.effort_level,
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

    # Total and distinct tool counts
    total_tc_result = await db.exec(select(func.count()).select_from(ToolCall))
    total_tool_calls = total_tc_result.one()
    distinct_tc_result = await db.exec(select(func.count(ToolCall.tool_name.distinct())))
    distinct_tool_count = distinct_tc_result.one()

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
        total_tool_calls=total_tool_calls,
        distinct_tool_count=distinct_tool_count,
        top_tools=top_tools,
        insight_counts=insight_counts,
    )


def _parse_metadata(ins, key: str):
    if not ins.metadata_json:
        return None
    try:
        return json.loads(ins.metadata_json).get(key)
    except Exception:
        return None


@router.get("/{session_id}", response_model=SessionDetail)
async def get_session_detail(
    session_id: str,
    tool_limit: int = 500,
    db: AsyncSession = Depends(get_db),
) -> SessionDetail:
    """Get session detail with tool calls and insights."""
    session = await db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    tc_query = (
        select(ToolCall).where(ToolCall.session_id == session_id).order_by(ToolCall.timestamp)
    )
    if tool_limit > 0:
        tc_query = tc_query.limit(tool_limit)
    tc_result = await db.exec(tc_query)
    tool_calls = tc_result.all()

    total_tc = (await db.exec(select(func.count()).where(ToolCall.session_id == session_id))).one()

    ins_result = await db.exec(
        select(Insight).where(Insight.session_id == session_id).order_by(Insight.created_at)
    )
    insights = ins_result.all()

    # Compute baseline averages on the fly from this user's sessions
    baseline_data = None
    if session.user_id:
        avg_result = await db.exec(
            select(
                func.count(),
                func.avg(CodingSession.read_edit_ratio),
                func.avg(CodingSession.edits_without_read_pct),
                func.avg(CodingSession.research_mutation_ratio),
                func.avg(CodingSession.error_rate),
                func.avg(CodingSession.write_vs_edit_pct),
                func.avg(CodingSession.repeated_edits_count),
                func.avg(CodingSession.context_pressure_score),
                func.avg(CodingSession.tokens_per_useful_edit),
                func.avg(CodingSession.error_retry_sequences),
                func.avg(CodingSession.context_resets),
                func.avg(CodingSession.duplicate_read_count),
            ).where(
                CodingSession.user_id == session.user_id,
                CodingSession.id != session.id,
            )
        )
        row = avg_result.one()
        if row[0] >= 3:
            baseline_data = {
                "avg_read_edit_ratio": round(row[1], 2) if row[1] else None,
                "avg_edits_without_read_pct": round(row[2], 1) if row[2] else None,
                "avg_research_mutation_ratio": round(row[3], 2) if row[3] else None,
                "avg_error_rate": round(row[4], 1) if row[4] else None,
                "avg_write_vs_edit_pct": round(row[5], 1) if row[5] else None,
                "avg_repeated_edits_count": round(row[6], 1) if row[6] else None,
                "avg_context_pressure_score": round(row[7], 2) if row[7] else None,
                "avg_tokens_per_useful_edit": round(row[8], 0) if row[8] else None,
                "avg_error_retry_sequences": round(row[9], 1) if row[9] else None,
                "avg_context_resets": round(row[10], 1) if row[10] else None,
                "avg_duplicate_read_count": round(row[11], 1) if row[11] else None,
            }

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
        total_tool_calls=total_tc,
        insights=[
            InsightRead(
                id=ins.id,
                category=ins.category,
                label=_parse_metadata(ins, "label"),
                title=ins.title,
                content=ins.content,
                severity=ins.severity,
                created_at=ins.created_at,
            )
            for ins in insights
        ],
        notable_quotes=_parse_notable_quotes(session),
        interrupt_count=session.interrupt_count,
        agent_version=session.agent_version,
        effort_level=session.effort_level,
        adaptive_thinking_disabled=session.adaptive_thinking_disabled,
        read_edit_ratio=session.read_edit_ratio,
        edits_without_read_pct=session.edits_without_read_pct,
        research_mutation_ratio=session.research_mutation_ratio,
        error_rate=session.error_rate,
        write_vs_edit_pct=session.write_vs_edit_pct,
        repeated_edits_count=session.repeated_edits_count,
        tokens_per_useful_edit=session.tokens_per_useful_edit,
        context_pressure_score=session.context_pressure_score,
        error_retry_sequences=session.error_retry_sequences,
        context_resets=session.context_resets,
        duplicate_read_count=session.duplicate_read_count,
        baseline=baseline_data,
    )


def _parse_notable_quotes(session) -> list[dict] | None:
    if not session.metadata_json:
        return None
    try:
        meta = json.loads(session.metadata_json)
        return meta.get("notable_quotes")
    except Exception:
        return None


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
async def trigger_analysis(session_id: str, db: AsyncSession = Depends(get_db)) -> SessionDetail:
    """Manually trigger LLM analysis for a session."""
    import asyncio

    from cinsights.analysis.session import SessionAnalyzer
    from cinsights.settings import get_settings
    from cinsights.sources.base import TraceData
    from cinsights.sources.factory import create_source

    session = await db.get(CodingSession, session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    settings = get_settings()

    source = create_source(settings)
    spans = await asyncio.to_thread(source.get_spans_by_session, session_id)
    if not spans:
        raise HTTPException(status_code=404, detail="No spans found for session")

    trace = TraceData(
        trace_id=session_id,
        start_time=session.start_time,
        end_time=session.end_time or session.start_time,
        spans=spans,
    )

    # Clear existing insights
    existing_result = await db.exec(select(Insight).where(Insight.session_id == session_id))
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
