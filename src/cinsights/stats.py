"""Computed statistics from the database — zero LLM cost.

All functions take a SQLModel Session, date range, and optional project_name filter.
"""

from __future__ import annotations

import re
from datetime import datetime

from pydantic import BaseModel
from sqlmodel import Session, col, func, select

from cinsights.db.models import (
    CodingSession,
    Insight,
    InsightCategory,
    SessionStatus,
    ToolCall,
)

# --- File extension to language mapping ---

_EXT_TO_LANG: dict[str, str] = {
    ".py": "Python", ".go": "Go", ".js": "JavaScript", ".ts": "TypeScript",
    ".tsx": "TypeScript", ".jsx": "JavaScript", ".rs": "Rust", ".java": "Java",
    ".rb": "Ruby", ".php": "PHP", ".c": "C", ".cpp": "C++", ".h": "C/C++",
    ".cs": "C#", ".swift": "Swift", ".kt": "Kotlin", ".scala": "Scala",
    ".json": "JSON", ".yaml": "YAML", ".yml": "YAML", ".toml": "TOML",
    ".xml": "XML", ".html": "HTML", ".css": "CSS", ".scss": "CSS",
    ".md": "Markdown", ".sql": "SQL", ".sh": "Shell", ".bash": "Shell",
    ".zsh": "Shell", ".dockerfile": "Docker", ".tf": "Terraform",
    ".svelte": "Svelte", ".vue": "Vue",
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


# --- Output models ---


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

    analysis_tokens_used: int


# --- Project detection ---


def detect_project_from_tool_calls(tool_calls: list) -> str | None:
    """Extract project name from file paths in tool call inputs."""
    file_path_re = re.compile(r'"?(/(?:Users|home)/\w+/[\w/.-]+\.\w+)')
    repo_markers = ("repos", "projects", "code", "work", "src")

    repo_counts: dict[str, int] = {}
    for tc in tool_calls:
        input_val = tc.input_value if hasattr(tc, "input_value") else tc.get("input_value")
        if not input_val:
            continue
        for match in file_path_re.finditer(input_val):
            parts = match.group(1).split("/")
            for i, p in enumerate(parts):
                if p in repo_markers:
                    remaining = [x for x in parts[i + 1 :] if x and not x.startswith(".")]
                    if len(remaining) >= 2:
                        repo_counts[remaining[1]] = repo_counts.get(remaining[1], 0) + 1
                    elif remaining:
                        repo_counts[remaining[0]] = repo_counts.get(remaining[0], 0) + 1
                    break

    if not repo_counts:
        return None

    winner, count = max(repo_counts.items(), key=lambda x: x[1])
    total = sum(repo_counts.values())
    return winner if count / total > 0.7 else None


# --- Query helpers ---


def _session_filter(start: datetime, end: datetime, project_name: str | None = None):
    clauses = [
        CodingSession.start_time >= start,
        CodingSession.start_time <= end,
        CodingSession.status == SessionStatus.ANALYZED,
    ]
    if project_name:
        clauses.append(CodingSession.project_name == project_name)
    return clauses


def _base_query(start: datetime, end: datetime, project_name: str | None = None):
    q = select(CodingSession)
    for clause in _session_filter(start, end, project_name):
        q = q.where(clause)
    return q


def _tc_agg_query(columns, start, end, project_name=None):
    q = (
        select(*columns)
        .select_from(ToolCall)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
    )
    for clause in _session_filter(start, end, project_name):
        q = q.where(clause)
    return q


# --- Compute functions ---


def compute_tool_distribution(db, start, end, project_name=None) -> dict[str, int]:
    rows = db.exec(
        _tc_agg_query(
            (ToolCall.tool_name, func.count()), start, end, project_name
        ).group_by(ToolCall.tool_name).order_by(func.count().desc())
    ).all()
    return {name: count for name, count in rows}


def compute_error_breakdown(db, start, end, project_name=None):
    tool_errors = db.exec(
        _tc_agg_query(
            (ToolCall.tool_name, func.count()), start, end, project_name
        ).where(ToolCall.success == False)  # noqa: E712
        .group_by(ToolCall.tool_name).order_by(func.count().desc())
    ).all()

    failed_calls = db.exec(
        _tc_agg_query(
            (ToolCall.output_value,), start, end, project_name
        ).where(ToolCall.success == False)  # noqa: E712
    ).all()

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


def compute_language_distribution(db, start, end, project_name=None) -> dict[str, int]:
    q = _tc_agg_query(
        (ToolCall.input_value,), start, end, project_name
    ).where(
        col(ToolCall.tool_name).in_(list(_FILE_TOOLS))
    ).where(ToolCall.input_value.isnot(None))

    inputs = db.exec(q).all()
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


def compute_time_of_day(db, start, end, project_name=None) -> dict[int, int]:
    sessions = db.exec(_base_query(start, end, project_name)).all()
    hours: dict[int, int] = {}
    for s in sessions:
        hours[s.start_time.hour] = hours.get(s.start_time.hour, 0) + 1
    return dict(sorted(hours.items()))


def compute_session_health(db, start, end, project_name=None) -> list[SessionHealthScore]:
    sessions = db.exec(
        _base_query(start, end, project_name)
        .order_by(col(CodingSession.start_time).desc())
    ).all()

    scores = []
    for s in sessions:
        duration = 0.0
        if s.end_time and s.start_time:
            duration = (s.end_time - s.start_time).total_seconds() / 60

        tool_count = db.exec(
            select(func.count()).where(ToolCall.session_id == s.id)
        ).one()
        error_count = db.exec(
            select(func.count())
            .where(ToolCall.session_id == s.id)
            .where(ToolCall.success == False)  # noqa: E712
        ).one()

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

        scores.append(SessionHealthScore(
            session_id=s.id, start_time=s.start_time,
            duration_minutes=round(duration, 1),
            tool_count=tool_count, error_count=error_count,
            error_rate=round(error_rate, 3), total_tokens=s.total_tokens,
            grade=grade, model=s.model,
        ))
    return scores


def compute_permission_stats(db, start, end, project_name=None) -> PermissionStats:
    """Count permission prompts and compute wait times."""
    # Get all tool calls sorted by time for sessions in range
    sessions = db.exec(_base_query(start, end, project_name)).all()
    session_ids = {s.id for s in sessions}

    if not session_ids:
        return PermissionStats(
            count=0, total_wait_seconds=0, avg_wait_seconds=0, max_wait_seconds=0
        )

    all_tcs = db.exec(
        select(ToolCall)
        .where(col(ToolCall.session_id).in_(list(session_ids)))
        .order_by(ToolCall.timestamp)
    ).all()

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


def compute_plan_mode_stats(db, start, end, project_name=None) -> PlanModeStats:
    """Count plan mode entries and agent stats."""
    sessions = db.exec(_base_query(start, end, project_name)).all()
    session_ids = {s.id for s in sessions}

    if not session_ids:
        return PlanModeStats(
            entries=0, total_duration_seconds=0,
            plan_agent_count=0, plan_agent_tokens=0,
        )

    plan_tcs = db.exec(
        select(ToolCall)
        .where(col(ToolCall.session_id).in_(list(session_ids)))
        .where(col(ToolCall.tool_name).in_(["EnterPlanMode", "ExitPlanMode", "Subagent: Plan"]))
    ).all()

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


def detect_claude_md(db, start, end, project_name=None) -> bool:
    """Check if any session in the period reads or edits a CLAUDE.md file."""
    q = _tc_agg_query(
        (func.count(),), start, end, project_name
    ).where(ToolCall.input_value.like("%CLAUDE.md%"))
    count = db.exec(q).one()
    return count > 0


def detect_overlapping_sessions(db, start, end, project_name=None) -> list[dict]:
    sessions = db.exec(
        _base_query(start, end, project_name)
        .where(CodingSession.end_time.isnot(None))
        .order_by(CodingSession.start_time)
    ).all()

    overlaps = []
    for i, s1 in enumerate(sessions):
        for s2 in sessions[i + 1 :]:
            if s2.start_time < s1.end_time:
                overlap_sec = (
                    min(s1.end_time, s2.end_time) - s2.start_time
                ).total_seconds()
                if overlap_sec > 60:
                    overlaps.append({
                        "session_ids": [s1.id, s2.id],
                        "overlap_minutes": round(overlap_sec / 60, 1),
                    })
    return overlaps


def collect_session_summaries(db, start, end, project_name=None) -> list[dict]:
    sessions = db.exec(
        _base_query(start, end, project_name).order_by(CodingSession.start_time)
    ).all()

    summaries = []
    for s in sessions:
        insights = db.exec(select(Insight).where(Insight.session_id == s.id)).all()

        summary_text = ""
        friction_texts = []
        win_texts = []
        for ins in insights:
            if ins.category == InsightCategory.SUMMARY:
                summary_text = ins.content
            elif ins.category == InsightCategory.FRICTION:
                friction_texts.append(f"{ins.title}: {ins.content[:200]}")
            elif ins.category == InsightCategory.WIN:
                win_texts.append(f"{ins.title}: {ins.content[:200]}")

        duration = 0.0
        if s.end_time:
            duration = (s.end_time - s.start_time).total_seconds() / 60

        tool_count = db.exec(
            select(func.count()).where(ToolCall.session_id == s.id)
        ).one()
        error_count = db.exec(
            select(func.count())
            .where(ToolCall.session_id == s.id)
            .where(ToolCall.success == False)  # noqa: E712
        ).one()

        summaries.append({
            "session_id": s.id, "start_time": s.start_time.isoformat(),
            "duration_min": round(duration, 1), "model": s.model,
            "tool_count": tool_count, "error_count": error_count,
            "total_tokens": s.total_tokens, "summary": summary_text,
            "frictions": friction_texts, "wins": win_texts,
        })
    return summaries


def compute_all(
    db: Session, start: datetime, end: datetime, project_name: str | None = None,
) -> DigestStats:
    """Compute all statistics for a digest period, optionally filtered by project."""
    sessions = db.exec(_base_query(start, end, project_name)).all()

    total_tokens = sum(s.total_tokens for s in sessions)
    total_prompt = sum(s.prompt_tokens for s in sessions)
    total_completion = sum(s.completion_tokens for s in sessions)
    total_duration = sum(
        (s.end_time - s.start_time).total_seconds() / 60
        for s in sessions if s.end_time
    )
    active_days = len({s.start_time.date() for s in sessions})

    tc_count_q = (
        select(func.count())
        .select_from(ToolCall)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
    )
    for clause in _session_filter(start, end, project_name):
        tc_count_q = tc_count_q.where(clause)
    total_tool_calls = db.exec(tc_count_q).one()

    analysis_tokens = sum(
        s.analysis_prompt_tokens + s.analysis_completion_tokens for s in sessions
    )

    p = project_name
    tool_dist = compute_tool_distribution(db, start, end, p)
    error_breakdown, error_types = compute_error_breakdown(db, start, end, p)
    lang_dist = compute_language_distribution(db, start, end, p)
    time_of_day = compute_time_of_day(db, start, end, p)

    session_durations = [{
        "session_id": s.id,
        "duration_min": round((s.end_time - s.start_time).total_seconds() / 60, 1)
        if s.end_time else 0,
        "start_time": s.start_time.isoformat(),
    } for s in sessions]

    tokens_per_session = [{
        "session_id": s.id, "tokens": s.total_tokens,
        "start_time": s.start_time.isoformat(),
    } for s in sessions]

    return DigestStats(
        period_start=start, period_end=end,
        session_count=len(sessions), analyzed_count=len(sessions),
        total_tool_calls=total_tool_calls, total_tokens=total_tokens,
        total_prompt_tokens=total_prompt, total_completion_tokens=total_completion,
        total_duration_minutes=round(total_duration, 1), active_days=active_days,
        tool_distribution=tool_dist, error_breakdown=error_breakdown,
        error_types=error_types, language_distribution=lang_dist,
        time_of_day=time_of_day, session_durations=session_durations,
        session_health=compute_session_health(db, start, end, p),
        tokens_per_session=tokens_per_session,
        overlapping_sessions=detect_overlapping_sessions(db, start, end, p),
        session_summaries=collect_session_summaries(db, start, end, p),
        permission_stats=compute_permission_stats(db, start, end, p),
        plan_mode_stats=compute_plan_mode_stats(db, start, end, p),
        has_claude_md=detect_claude_md(db, start, end, p),
        analysis_tokens_used=analysis_tokens,
    )
