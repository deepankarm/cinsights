"""Computed statistics from the database — zero LLM cost.

All functions take a SQLModel Session, date range, and optional project_name filter.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel
from sqlalchemy import case
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession
from sqlmodel.sql.expression import SelectOfScalar

from cinsights.db.models import (
    CodingSession,
    Insight,
    InsightCategory,
    SessionStatus,
    ToolCall,
)

_EXT_TO_LANG: dict[str, str] = {
    ".py": "Python",
    ".go": "Go",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".jsx": "JavaScript",
    ".rs": "Rust",
    ".java": "Java",
    ".rb": "Ruby",
    ".php": "PHP",
    ".c": "C",
    ".cpp": "C++",
    ".h": "C/C++",
    ".cs": "C#",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".json": "JSON",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".toml": "TOML",
    ".xml": "XML",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "CSS",
    ".md": "Markdown",
    ".sql": "SQL",
    ".sh": "Shell",
    ".bash": "Shell",
    ".zsh": "Shell",
    ".dockerfile": "Docker",
    ".tf": "Terraform",
    ".svelte": "Svelte",
    ".vue": "Vue",
}

_FILE_TOOLS = {"Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit"}
_FILE_PATH_RE = re.compile(r'["\']?(/[^\s"\',:}{]+\.\w+)')

_ERROR_PATTERNS = [
    ("Command Failed", re.compile(r"exit code [1-9]|command.+failed|error code", re.I)),
    ("User Rejected", re.compile(r"user.+reject|denied|doesn't want", re.I)),
    ("File Not Found", re.compile(r"file.+not found|no such file|does not exist", re.I)),
    ("Permission Denied", re.compile(r"permission denied|not allowed|EACCES", re.I)),
    ("Edit Failed", re.compile(r"edit.+fail|old_string.+not found|not unique", re.I)),
    ("File Too Large", re.compile(r"too large|file size|exceeds", re.I)),
    ("Timeout", re.compile(r"timeout|timed out|deadline exceeded", re.I)),
]


class WeeklyTrend(BaseModel):
    """One week of aggregated quality metrics."""
    week: str  # ISO date of Monday
    session_count: int
    avg_read_edit_ratio: float | None = None
    avg_edits_without_read_pct: float | None = None
    avg_error_rate: float | None = None
    avg_research_mutation_ratio: float | None = None
    avg_write_vs_edit_pct: float | None = None
    avg_context_pressure: float | None = None
    total_tokens: int = 0


class SessionHealthScore(BaseModel):
    session_id: str
    start_time: datetime
    duration_minutes: float
    tool_count: int
    error_count: int
    error_rate: float
    total_tokens: int
    grade: str
    model: str | None


class PermissionStats(BaseModel):
    count: int
    total_wait_seconds: float
    avg_wait_seconds: float
    max_wait_seconds: float


class PlanModeStats(BaseModel):
    entries: int
    total_duration_seconds: float
    plan_agent_count: int
    plan_agent_tokens: int


class ProjectBreakdown(BaseModel):
    name: str
    session_count: int
    total_tokens: int
    total_tool_calls: int
    top_tools: list[str]
    has_claude_md: bool


class DigestStats(BaseModel):
    """All computed statistics for a digest period."""

    period_start: datetime
    period_end: datetime
    session_count: int
    analyzed_count: int

    total_tool_calls: int
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_duration_minutes: float
    active_days: int

    tool_distribution: dict[str, int]
    error_breakdown: dict[str, int]
    error_types: dict[str, int]
    language_distribution: dict[str, int]
    time_of_day: dict[int, int]

    session_durations: list[dict]
    session_health: list[SessionHealthScore]
    tokens_per_session: list[dict]
    overlapping_sessions: list[dict]
    session_summaries: list[dict]

    permission_stats: PermissionStats
    plan_mode_stats: PlanModeStats
    has_claude_md: bool
    project_breakdown: list[ProjectBreakdown]

    weekly_trends: list[WeeklyTrend]
    previous_digest_summary: str | None = None
    analysis_tokens_used: int


def _session_filter(
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
    *,
    analyzed_only: bool = False,
) -> list[Any]:
    """Build WHERE clauses for selecting sessions in a window.

    By default selects INDEXED + ANALYZED sessions (all sessions with
    extracted metadata). Pass ``analyzed_only=True`` to restrict to sessions
    that have LLM-generated insights.
    """
    clauses: list[Any] = [
        CodingSession.start_time >= start,
        CodingSession.start_time <= end,
    ]
    if analyzed_only:
        clauses.append(CodingSession.status == SessionStatus.ANALYZED)
    else:
        clauses.append(
            col(CodingSession.status).in_([SessionStatus.INDEXED, SessionStatus.ANALYZED])
        )
    if project_name:
        clauses.append(CodingSession.project_name == project_name)
    if user_id:
        clauses.append(CodingSession.user_id == user_id)
    return clauses


def _base_query(
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
    *,
    analyzed_only: bool = False,
) -> SelectOfScalar[CodingSession]:
    """Build a SELECT for CodingSessions in the given window.

    Pure: builds the Select expression, doesn't execute it.
    """
    q = select(CodingSession)
    for clause in _session_filter(start, end, project_name, user_id, analyzed_only=analyzed_only):
        q = q.where(clause)
    return q


def _tc_agg_query(
    columns: tuple[Any, ...],
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
    *,
    analyzed_only: bool = False,
) -> Any:
    """Build a SELECT over ToolCall joined to its session, scoped to the window.

    The caller picks which columns to project (e.g. ``(ToolCall.tool_name,
    func.count())``). Pure: builds the Select, doesn't execute it.
    """
    q = (
        select(*columns)
        .select_from(ToolCall)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
    )
    for clause in _session_filter(start, end, project_name, user_id, analyzed_only=analyzed_only):
        q = q.where(clause)
    return q


async def compute_tool_distribution(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> dict[str, int]:
    result = await db.exec(
        _tc_agg_query((ToolCall.tool_name, func.count()), start, end, project_name, user_id)
        .group_by(ToolCall.tool_name)
        .order_by(func.count().desc())
    )
    return {name: count for name, count in result.all()}


async def compute_error_breakdown(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> tuple[dict[str, int], dict[str, int]]:
    tool_errors_result = await db.exec(
        _tc_agg_query((ToolCall.tool_name, func.count()), start, end, project_name, user_id)
        .where(ToolCall.success == False)  # noqa: E712
        .group_by(ToolCall.tool_name)
        .order_by(func.count().desc())
    )
    tool_errors = tool_errors_result.all()

    failed_result = await db.exec(
        _tc_agg_query((ToolCall.output_value,), start, end, project_name, user_id).where(
            ToolCall.success == False  # noqa: E712 — SQLAlchemy filter
        )
    )
    failed_calls = failed_result.all()

    error_types: dict[str, int] = {}
    for output in failed_calls:
        if not output:
            error_types["Other"] = error_types.get("Other", 0) + 1
            continue
        matched = False
        for label, pattern in _ERROR_PATTERNS:
            if pattern.search(output):
                error_types[label] = error_types.get(label, 0) + 1
                matched = True
                break
        if not matched:
            error_types["Other"] = error_types.get("Other", 0) + 1

    return (
        {name: count for name, count in tool_errors},
        dict(sorted(error_types.items(), key=lambda x: -x[1])),
    )


async def compute_language_distribution(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> dict[str, int]:
    q = (
        _tc_agg_query((ToolCall.input_value,), start, end, project_name, user_id)
        .where(col(ToolCall.tool_name).in_(list(_FILE_TOOLS)))
        .where(ToolCall.input_value.isnot(None))
    )

    result = await db.exec(q)
    inputs = result.all()
    lang_counts: dict[str, int] = {}
    for input_val in inputs:
        if not input_val:
            continue
        for match in _FILE_PATH_RE.finditer(input_val):
            path = match.group(1)
            ext = "." + path.rsplit(".", 1)[-1].lower() if "." in path else ""
            lang = _EXT_TO_LANG.get(ext)
            if lang:
                lang_counts[lang] = lang_counts.get(lang, 0) + 1
    return dict(sorted(lang_counts.items(), key=lambda x: -x[1]))


async def compute_time_of_day(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> dict[int, int]:
    result = await db.exec(_base_query(start, end, project_name, user_id))
    sessions = result.all()
    hours: dict[int, int] = {}
    for s in sessions:
        hours[s.start_time.hour] = hours.get(s.start_time.hour, 0) + 1
    return dict(sorted(hours.items()))


async def compute_session_health(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> list[SessionHealthScore]:
    result = await db.exec(
        _base_query(start, end, project_name, user_id).order_by(col(CodingSession.start_time).desc())
    )
    sessions = result.all()
    if not sessions:
        return []

    session_ids = [s.id for s in sessions]

    # One round-trip: tool count + error count per session.
    counts_q = (
        select(
            ToolCall.session_id,
            func.count().label("tool_count"),
            func.sum(
                case((ToolCall.success == False, 1), else_=0)  # noqa: E712
            ).label("error_count"),
        )
        .where(col(ToolCall.session_id).in_(session_ids))
        .group_by(ToolCall.session_id)
    )
    counts_result = await db.exec(counts_q)
    counts = {
        row.session_id: (int(row.tool_count or 0), int(row.error_count or 0))
        for row in counts_result.all()
    }

    scores = []
    for s in sessions:
        duration = 0.0
        if s.end_time and s.start_time:
            duration = (s.end_time - s.start_time).total_seconds() / 60

        tool_count, error_count = counts.get(s.id, (0, 0))

        error_rate = error_count / max(tool_count, 1)
        if error_rate <= 0.05:
            grade = "A"
        elif error_rate <= 0.10:
            grade = "B"
        elif error_rate <= 0.20:
            grade = "C"
        elif error_rate <= 0.35:
            grade = "D"
        else:
            grade = "F"

        scores.append(
            SessionHealthScore(
                session_id=s.id,
                start_time=s.start_time,
                duration_minutes=round(duration, 1),
                tool_count=tool_count,
                error_count=error_count,
                error_rate=round(error_rate, 3),
                total_tokens=s.total_tokens,
                grade=grade,
                model=s.model,
            )
        )
    return scores


async def compute_permission_stats(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> PermissionStats:
    """Count permission prompts and compute wait times."""
    sessions_result = await db.exec(_base_query(start, end, project_name, user_id))
    session_ids = {s.id for s in sessions_result.all()}

    if not session_ids:
        return PermissionStats(
            count=0, total_wait_seconds=0, avg_wait_seconds=0, max_wait_seconds=0
        )

    tcs_result = await db.exec(
        select(ToolCall)
        .where(col(ToolCall.session_id).in_(list(session_ids)))
        .order_by(ToolCall.timestamp)
    )
    all_tcs = tcs_result.all()

    perm_count = 0
    waits: list[float] = []

    for i, tc in enumerate(all_tcs):
        is_perm = (
            "permission_prompt" in tc.tool_name.lower()
            or tc.tool_name == "Notification: permission_prompt"
        )
        if is_perm:
            perm_count += 1
            # Find next non-permission tool call to measure wait
            for j in range(i + 1, min(i + 10, len(all_tcs))):
                nxt = all_tcs[j]
                if "ermission" not in nxt.tool_name and "otification" not in nxt.tool_name:
                    wait = (nxt.timestamp - tc.timestamp).total_seconds()
                    if 0 < wait < 600:  # cap at 10min
                        waits.append(wait)
                    break

    return PermissionStats(
        count=perm_count,
        total_wait_seconds=round(sum(waits), 1),
        avg_wait_seconds=round(sum(waits) / len(waits), 1) if waits else 0,
        max_wait_seconds=round(max(waits), 1) if waits else 0,
    )


async def compute_plan_mode_stats(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> PlanModeStats:
    """Count plan mode entries and agent stats."""
    sessions_result = await db.exec(_base_query(start, end, project_name, user_id))
    session_ids = {s.id for s in sessions_result.all()}

    if not session_ids:
        return PlanModeStats(
            entries=0,
            total_duration_seconds=0,
            plan_agent_count=0,
            plan_agent_tokens=0,
        )

    plan_result = await db.exec(
        select(ToolCall)
        .where(col(ToolCall.session_id).in_(list(session_ids)))
        .where(col(ToolCall.tool_name).in_(["EnterPlanMode", "ExitPlanMode", "Subagent: Plan"]))
    )
    plan_tcs = plan_result.all()

    entries = sum(1 for tc in plan_tcs if tc.tool_name == "EnterPlanMode")
    plan_agents = [tc for tc in plan_tcs if "Subagent: Plan" in tc.tool_name]
    total_dur = sum(tc.duration_ms or 0 for tc in plan_tcs if tc.tool_name == "ExitPlanMode") / 1000

    # Extract tokens from plan agent input/output (stored in tool call)
    plan_tokens = 0
    for tc in plan_agents:
        if tc.input_value:
            import json

            try:
                data = json.loads(tc.input_value)
                plan_tokens += data.get("llm.token_count.total", 0) if isinstance(data, dict) else 0
            except (json.JSONDecodeError, TypeError):
                pass

    return PlanModeStats(
        entries=entries,
        total_duration_seconds=round(total_dur, 1),
        plan_agent_count=len(plan_agents),
        plan_agent_tokens=plan_tokens,
    )


async def detect_claude_md(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> bool:
    """Check if any session reads or edits a CLAUDE.md file."""
    q = (
        _tc_agg_query((ToolCall.input_value,), start, end, project_name, user_id)
        .where(col(ToolCall.tool_name).in_(["Read", "Edit", "Write"]))
        .where(ToolCall.input_value.isnot(None))
    )

    result = await db.exec(q)
    for input_val in result.all():
        if not input_val:
            continue
        # Parse the file_path from JSON input and check if it ends with CLAUDE.md
        import json as json_mod

        try:
            data = json_mod.loads(input_val)
            fp = data.get("file_path", "") if isinstance(data, dict) else ""
            if fp.endswith("CLAUDE.md") or fp.endswith("CLAUDE.local.md"):
                return True
        except (json_mod.JSONDecodeError, TypeError):
            continue
    return False


async def detect_overlapping_sessions(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    result = await db.exec(
        _base_query(start, end, project_name, user_id)
        .where(CodingSession.end_time.isnot(None))
        .order_by(CodingSession.start_time)
    )
    sessions = result.all()

    overlaps = []
    for i, s1 in enumerate(sessions):
        for s2 in sessions[i + 1 :]:
            if s2.start_time < s1.end_time:
                overlap_sec = (min(s1.end_time, s2.end_time) - s2.start_time).total_seconds()
                if overlap_sec > 60:
                    overlaps.append(
                        {
                            "session_ids": [s1.id, s2.id],
                            "overlap_minutes": round(overlap_sec / 60, 1),
                        }
                    )
    return overlaps


async def collect_session_summaries(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> list[dict]:
    # Session summaries depend on Insight rows → ANALYZED only
    sessions_result = await db.exec(
        _base_query(start, end, project_name, user_id, analyzed_only=True)
        .order_by(CodingSession.start_time)
    )
    sessions = sessions_result.all()
    if not sessions:
        return []

    session_ids = [s.id for s in sessions]

    # Batch tool/error counts for every session in one round-trip.
    counts_q = (
        select(
            ToolCall.session_id,
            func.count().label("tool_count"),
            func.sum(
                case((ToolCall.success == False, 1), else_=0)  # noqa: E712
            ).label("error_count"),
        )
        .where(col(ToolCall.session_id).in_(session_ids))
        .group_by(ToolCall.session_id)
    )
    counts_result = await db.exec(counts_q)
    counts: dict[str, tuple[int, int]] = {
        row.session_id: (int(row.tool_count or 0), int(row.error_count or 0))
        for row in counts_result.all()
    }

    # Batch all insights for these sessions in one round-trip, then bucket
    # by session_id in Python.
    insights_q = select(Insight).where(col(Insight.session_id).in_(session_ids))
    insights_result = await db.exec(insights_q)
    insights_by_session: dict[str, list[Insight]] = {}
    for ins in insights_result.all():
        insights_by_session.setdefault(ins.session_id, []).append(ins)

    from cinsights.settings import get_settings

    min_tools = get_settings().min_session_tool_count

    summaries = []
    for s in sessions:
        tool_count, error_count = counts.get(s.id, (0, 0))

        # Skip tiny sessions from the per-session evidence list.
        # They still contribute to aggregate stats computed elsewhere.
        if tool_count < min_tools:
            continue

        summary_text = ""
        friction_texts: list[str] = []
        win_texts: list[str] = []
        for ins in insights_by_session.get(s.id, ()):
            if ins.category == InsightCategory.SUMMARY:
                summary_text = ins.content
            elif ins.category == InsightCategory.FRICTION:
                friction_texts.append(f"{ins.title}: {ins.content[:200]}")
            elif ins.category == InsightCategory.WIN:
                win_texts.append(f"{ins.title}: {ins.content[:200]}")

        duration = 0.0
        if s.end_time:
            duration = (s.end_time - s.start_time).total_seconds() / 60

        # Size bucket so the LLM can weight evidence appropriately.
        if tool_count >= 200:
            size = "MAJOR"
        elif tool_count >= 50:
            size = "MEDIUM"
        else:
            size = "MINOR"

        summaries.append(
            {
                "session_id": s.id,
                "start_time": s.start_time.isoformat(),
                "duration_min": round(duration, 1),
                "model": s.model,
                "project": s.project_name or "unknown",
                "tool_count": tool_count,
                "error_count": error_count,
                "total_tokens": s.total_tokens,
                "summary": summary_text,
                "frictions": friction_texts,
                "wins": win_texts,
                "size": size,
            }
        )

    # Sort by tool_count desc so the LLM sees the most substantial sessions first.
    # Cap to keep digest prompts within context limits.
    from cinsights.settings import get_config
    max_summaries = get_config().limits.max_digest_session_summaries
    summaries.sort(key=lambda x: x["tool_count"], reverse=True)
    return summaries[:max_summaries]


def _compute_weekly_trends(sessions: list[CodingSession]) -> list[WeeklyTrend]:
    """Aggregate sessions into weekly buckets by quality metrics."""
    from datetime import timedelta

    if not sessions:
        return []

    # Group by ISO week (Monday start)
    by_week: dict[str, list[CodingSession]] = {}
    for s in sessions:
        monday = s.start_time.date() - timedelta(days=s.start_time.weekday())
        week_key = monday.isoformat()
        by_week.setdefault(week_key, []).append(s)

    def _avg_field(sess: list[CodingSession], field: str) -> float | None:
        vals = [getattr(s, field) for s in sess if getattr(s, field, None) is not None]
        return round(sum(vals) / len(vals), 2) if vals else None

    trends = []
    for week in sorted(by_week.keys()):
        week_sessions = by_week[week]
        trends.append(
            WeeklyTrend(
                week=week,
                session_count=len(week_sessions),
                avg_read_edit_ratio=_avg_field(week_sessions, "read_edit_ratio"),
                avg_edits_without_read_pct=_avg_field(week_sessions, "edits_without_read_pct"),
                avg_error_rate=_avg_field(week_sessions, "error_rate"),
                avg_research_mutation_ratio=_avg_field(week_sessions, "research_mutation_ratio"),
                avg_write_vs_edit_pct=_avg_field(week_sessions, "write_vs_edit_pct"),
                avg_context_pressure=_avg_field(week_sessions, "context_pressure_score"),
                total_tokens=sum(s.total_tokens for s in week_sessions),
            )
        )
    return trends


async def compute_all(
    db: AsyncSession,
    start: datetime,
    end: datetime,
    project_name: str | None = None,
    user_id: str | None = None,
) -> DigestStats:
    """Compute all statistics for a digest period, optionally filtered by project.

    Note on concurrency: every step here awaits sequentially against the same
    AsyncSession. We do NOT ``asyncio.gather`` sub-queries because SQLAlchemy's
    AsyncSession is not safe for concurrent use within a single session — you
    must serialize queries on one session and rely on the request boundary
    (separate sessions per request / per scope) for parallelism.
    """
    # All indexed+analyzed sessions for quantitative stats
    sessions_result = await db.exec(_base_query(start, end, project_name, user_id))
    sessions = sessions_result.all()
    analyzed_count = sum(1 for s in sessions if s.status == SessionStatus.ANALYZED)

    total_tokens = sum(s.total_tokens for s in sessions)
    total_prompt = sum(s.prompt_tokens for s in sessions)
    total_completion = sum(s.completion_tokens for s in sessions)
    total_duration = sum(
        (s.end_time - s.start_time).total_seconds() / 60 for s in sessions if s.end_time
    )
    active_days = len({s.start_time.date() for s in sessions})

    tc_count_q = (
        select(func.count())
        .select_from(ToolCall)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
    )
    for clause in _session_filter(start, end, project_name, user_id):
        tc_count_q = tc_count_q.where(clause)
    tc_count_result = await db.exec(tc_count_q)
    total_tool_calls = tc_count_result.one()

    analysis_tokens = sum(
        s.analysis_prompt_tokens + s.analysis_completion_tokens
        for s in sessions
        if s.status == SessionStatus.ANALYZED
    )

    p, u = project_name, user_id
    tool_dist = await compute_tool_distribution(db, start, end, p, u)
    error_breakdown, error_types = await compute_error_breakdown(db, start, end, p, u)
    lang_dist = await compute_language_distribution(db, start, end, p, u)
    time_of_day = await compute_time_of_day(db, start, end, p, u)

    session_durations = [
        {
            "session_id": s.id,
            "duration_min": round((s.end_time - s.start_time).total_seconds() / 60, 1)
            if s.end_time
            else 0,
            "start_time": s.start_time.isoformat(),
        }
        for s in sessions
    ]

    tokens_per_session = [
        {
            "session_id": s.id,
            "tokens": s.total_tokens,
            "start_time": s.start_time.isoformat(),
        }
        for s in sessions
    ]

    # Per-project breakdown (only for global digests)
    proj_breakdown: list[ProjectBreakdown] = []
    if not project_name:
        proj_groups: dict[str, list] = {}
        for s in sessions:
            pn = s.project_name or "unknown"
            proj_groups.setdefault(pn, []).append(s)

        for pn, proj_sessions in sorted(proj_groups.items(), key=lambda x: -len(x[1])):
            proj_ids = [s.id for s in proj_sessions]
            proj_tc_result = await db.exec(
                select(ToolCall.tool_name, func.count())
                .where(col(ToolCall.session_id).in_(proj_ids))
                .group_by(ToolCall.tool_name)
                .order_by(func.count().desc())
                .limit(3)
            )
            proj_tc = proj_tc_result.all()
            proj_breakdown.append(
                ProjectBreakdown(
                    name=pn,
                    session_count=len(proj_sessions),
                    total_tokens=sum(s.total_tokens for s in proj_sessions),
                    total_tool_calls=sum(c for _, c in proj_tc),
                    top_tools=[name for name, _ in proj_tc],
                    has_claude_md=await detect_claude_md(db, start, end, pn),
                )
            )

    return DigestStats(
        period_start=start,
        period_end=end,
        session_count=len(sessions),
        analyzed_count=analyzed_count,
        total_tool_calls=total_tool_calls,
        total_tokens=total_tokens,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        total_duration_minutes=round(total_duration, 1),
        active_days=active_days,
        tool_distribution=tool_dist,
        error_breakdown=error_breakdown,
        error_types=error_types,
        language_distribution=lang_dist,
        time_of_day=time_of_day,
        session_durations=session_durations,
        session_health=await compute_session_health(db, start, end, p, u),
        tokens_per_session=tokens_per_session,
        overlapping_sessions=await detect_overlapping_sessions(db, start, end, p, u),
        session_summaries=await collect_session_summaries(db, start, end, p, u),
        permission_stats=await compute_permission_stats(db, start, end, p, u),
        plan_mode_stats=await compute_plan_mode_stats(db, start, end, p, u),
        has_claude_md=await detect_claude_md(db, start, end, p, u),
        project_breakdown=proj_breakdown,
        weekly_trends=_compute_weekly_trends(sessions),
        analysis_tokens_used=analysis_tokens,
    )
