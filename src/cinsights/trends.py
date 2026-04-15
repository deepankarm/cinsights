"""Daily trend aggregation and baseline computation.

All operations are incremental — called after each session is indexed.
Zero LLM cost.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from datetime import datetime

from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.models import (
    CodingSession,
    SessionBaseline,
    SessionDailyTrend,
    SessionStatus,
    ToolCall,
)

logger = logging.getLogger(__name__)

_METRIC_FIELDS = [
    "read_edit_ratio",
    "edits_without_read_pct",
    "research_mutation_ratio",
    "write_vs_edit_pct",
    "error_rate",
]


async def update_daily_trend(db: AsyncSession, session: CodingSession) -> None:
    """Upsert a daily trend row for this session's (date, user, project)."""
    if not session.start_time:
        return

    date_str = session.start_time.strftime("%Y-%m-%d")
    user_id = session.user_id or "unknown"
    project = session.project_name
    trend_id = f"{date_str}:{user_id}:{project or '_'}"

    existing = await db.get(SessionDailyTrend, trend_id)
    if existing:
        trend = existing
    else:
        trend = SessionDailyTrend(
            id=trend_id,
            date=date_str,
            user_id=user_id,
            project_name=project,
            tenant_id=session.tenant_id,
        )
        db.add(trend)

    # Re-aggregate from all sessions for this (date, user, project)
    query = select(CodingSession).where(
        CodingSession.user_id == user_id,
        CodingSession.start_time >= datetime.fromisoformat(f"{date_str}T00:00:00"),
        CodingSession.start_time < datetime.fromisoformat(f"{date_str}T23:59:59"),
        col(CodingSession.status).in_([SessionStatus.INDEXED, SessionStatus.ANALYZED]),
    )
    if project:
        query = query.where(CodingSession.project_name == project)
    else:
        query = query.where(CodingSession.project_name.is_(None))  # type: ignore[union-attr]

    result = await db.exec(query)
    sessions = result.all()

    if not sessions:
        return

    trend.session_count = len(sessions)
    trend.indexed_count = sum(1 for s in sessions if s.status == SessionStatus.INDEXED)
    trend.analyzed_count = sum(1 for s in sessions if s.status == SessionStatus.ANALYZED)
    trend.total_tokens = sum(s.total_tokens for s in sessions)

    # Parse context growth for turn counts
    total_turns = 0
    for s in sessions:
        if s.context_growth_json:
            try:
                cg = json.loads(s.context_growth_json)
                total_turns += len(cg)
            except (json.JSONDecodeError, TypeError):
                pass
    trend.total_turns = total_turns

    # Tool call count
    tc_result = await db.exec(
        select(ToolCall.session_id).where(col(ToolCall.session_id).in_([s.id for s in sessions]))
    )
    trend.total_tool_calls = len(tc_result.all())

    # Average quality metrics
    for field in _METRIC_FIELDS:
        values = [getattr(s, field) for s in sessions if getattr(s, field) is not None]
        avg_field = f"avg_{field}"
        if values:
            setattr(trend, avg_field, round(sum(values) / len(values), 2))
        else:
            setattr(trend, avg_field, None)

    # Duration
    durations = []
    for s in sessions:
        if s.start_time and s.end_time:
            ms = (s.end_time - s.start_time).total_seconds() * 1000
            if ms > 0:
                durations.append(ms)
    trend.avg_session_duration_ms = round(sum(durations) / len(durations), 0) if durations else None

    # Tools per turn
    if total_turns > 0 and trend.total_tool_calls > 0:
        trend.avg_tool_calls_per_turn = round(trend.total_tool_calls / total_turns, 1)

    # Agent distribution
    agent_counts: Counter[str] = Counter()
    for s in sessions:
        agent_counts[s.agent_type] += 1
    trend.agent_distribution_json = json.dumps(dict(agent_counts))

    trend.last_updated = datetime.utcnow()


async def update_baseline(db: AsyncSession, session: CodingSession, window: int = 30) -> None:
    """Update the rolling baseline for this session's (user, project) pair."""
    user_id = session.user_id or "unknown"
    project = session.project_name
    baseline_id = f"{user_id}:{project or '_'}"

    # Fetch last N sessions for this (user, project)
    query = (
        select(CodingSession)
        .where(
            CodingSession.user_id == user_id,
            col(CodingSession.status).in_([SessionStatus.INDEXED, SessionStatus.ANALYZED]),
        )
        .order_by(col(CodingSession.start_time).desc())
        .limit(window)
    )
    if project:
        query = query.where(CodingSession.project_name == project)
    else:
        query = query.where(CodingSession.project_name.is_(None))  # type: ignore[union-attr]

    result = await db.exec(query)
    sessions = result.all()

    if not sessions:
        return

    existing = await db.get(SessionBaseline, baseline_id)
    if existing:
        baseline = existing
    else:
        baseline = SessionBaseline(
            id=baseline_id,
            user_id=user_id,
            project_name=project,
            tenant_id=session.tenant_id,
        )
        db.add(baseline)

    baseline.session_count = len(sessions)

    # Turn counts
    turn_counts = []
    for s in sessions:
        if s.context_growth_json:
            try:
                cg = json.loads(s.context_growth_json)
                turn_counts.append(len(cg))
            except (json.JSONDecodeError, TypeError):
                pass
    baseline.avg_turns = round(sum(turn_counts) / len(turn_counts), 1) if turn_counts else 0

    # Tool counts (from span_count as proxy — actual tool count would need a join)
    baseline.avg_tool_count = round(sum(s.span_count for s in sessions) / len(sessions), 1)

    # Quality metrics
    for field in _METRIC_FIELDS:
        values = [getattr(s, field) for s in sessions if getattr(s, field) is not None]
        baseline_field = f"avg_{field}"
        if values:
            setattr(baseline, baseline_field, round(sum(values) / len(values), 2))

    # Duration
    durations = []
    for s in sessions:
        if s.start_time and s.end_time:
            ms = (s.end_time - s.start_time).total_seconds() * 1000
            if ms > 0:
                durations.append(ms)
    baseline.avg_duration_ms = round(sum(durations) / len(durations), 0) if durations else 0

    # Tool distribution
    tool_counts: Counter[str] = Counter()
    for s in sessions:
        tc_result = await db.exec(select(ToolCall.tool_name).where(ToolCall.session_id == s.id))
        for name in tc_result.all():
            tool_counts[name] += 1
    total_tools = sum(tool_counts.values())
    if total_tools > 0:
        dist = {k: round(v / total_tools, 3) for k, v in tool_counts.most_common(20)}
        baseline.tool_distribution_json = json.dumps(dist)

    baseline.last_updated = datetime.utcnow()
