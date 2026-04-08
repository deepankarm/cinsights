"""Computed statistics from the database — zero LLM cost.

All functions take a SQLModel Session and date range, and return
structured data from pure SQL queries against coding_session,
tool_call, and insight tables.
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

# Tools that operate on files
_FILE_TOOLS = {"Read", "Edit", "Write", "Glob", "Grep", "NotebookEdit"}

# Regex to extract file paths from tool input
_FILE_PATH_RE = re.compile(r'["\']?(/[^\s"\',:}{]+\.\w+)')

# Error type patterns in failed tool output
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
    grade: str  # A, B, C, D, F
    model: str | None


class DigestStats(BaseModel):
    """All computed statistics for a digest period."""

    # Period
    period_start: datetime
    period_end: datetime
    session_count: int
    analyzed_count: int

    # Aggregates
    total_tool_calls: int
    total_tokens: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_duration_minutes: float
    active_days: int

    # Distributions
    tool_distribution: dict[str, int]
    error_breakdown: dict[str, int]  # tool_name -> failed count
    error_types: dict[str, int]  # "Command Failed" -> count
    language_distribution: dict[str, int]
    time_of_day: dict[int, int]  # hour -> session count

    # Session-level
    session_durations: list[dict]  # [{session_id, duration_min, start_time}]
    session_health: list[SessionHealthScore]
    tokens_per_session: list[dict]  # [{session_id, tokens, start_time}]

    # Overlap detection
    overlapping_sessions: list[dict]  # [{session_ids, overlap_minutes}]

    # Per-session insight summaries (for LLM digest context)
    session_summaries: list[dict]

    # Permission/notification stats
    permission_prompt_count: int

    # cinsights own usage
    analysis_tokens_used: int


def _base_query(start: datetime, end: datetime):
    """Filter for sessions in the date range that are analyzed."""
    return (
        select(CodingSession)
        .where(CodingSession.start_time >= start)
        .where(CodingSession.start_time <= end)
        .where(CodingSession.status == SessionStatus.ANALYZED)
    )


def compute_tool_distribution(
    db: Session, start: datetime, end: datetime
) -> dict[str, int]:
    rows = db.exec(
        select(ToolCall.tool_name, func.count())
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
        .where(CodingSession.start_time >= start)
        .where(CodingSession.start_time <= end)
        .group_by(ToolCall.tool_name)
        .order_by(func.count().desc())
    ).all()
    return {name: count for name, count in rows}


def compute_error_breakdown(
    db: Session, start: datetime, end: datetime
) -> tuple[dict[str, int], dict[str, int]]:
    """Returns (tool_error_counts, error_type_counts)."""
    # Errors by tool name
    tool_errors = db.exec(
        select(ToolCall.tool_name, func.count())
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
        .where(CodingSession.start_time >= start)
        .where(CodingSession.start_time <= end)
        .where(ToolCall.success == False)  # noqa: E712
        .group_by(ToolCall.tool_name)
        .order_by(func.count().desc())
    ).all()

    # Error types by parsing output
    error_types: dict[str, int] = {}
    failed_calls = db.exec(
        select(ToolCall.output_value)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
        .where(CodingSession.start_time >= start)
        .where(CodingSession.start_time <= end)
        .where(ToolCall.success == False)  # noqa: E712
    ).all()

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


def compute_language_distribution(
    db: Session, start: datetime, end: datetime
) -> dict[str, int]:
    """Extract languages from file paths in tool call inputs."""
    inputs = db.exec(
        select(ToolCall.input_value)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
        .where(CodingSession.start_time >= start)
        .where(CodingSession.start_time <= end)
        .where(col(ToolCall.tool_name).in_(list(_FILE_TOOLS)))
        .where(ToolCall.input_value.isnot(None))
    ).all()

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


def compute_time_of_day(
    db: Session, start: datetime, end: datetime
) -> dict[int, int]:
    """Session start hour distribution (0-23)."""
    sessions = db.exec(_base_query(start, end)).all()
    hours: dict[int, int] = {}
    for s in sessions:
        h = s.start_time.hour
        hours[h] = hours.get(h, 0) + 1
    return dict(sorted(hours.items()))


def compute_session_health(
    db: Session, start: datetime, end: datetime
) -> list[SessionHealthScore]:
    """Compute health scores for each session."""
    sessions = db.exec(
        _base_query(start, end).order_by(col(CodingSession.start_time).desc())
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

        # Grade based on error rate
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


def compute_permission_count(
    db: Session, start: datetime, end: datetime
) -> int:
    """Count permission/notification tool calls (spans named 'Permission Request')."""
    return db.exec(
        select(func.count())
        .select_from(ToolCall)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
        .where(CodingSession.start_time >= start)
        .where(CodingSession.start_time <= end)
        .where(
            col(ToolCall.tool_name).in_(
                ["Permission Request", "Notification: permission_prompt"]
            )
        )
    ).one()


def detect_overlapping_sessions(
    db: Session, start: datetime, end: datetime
) -> list[dict]:
    """Detect sessions that overlap in time (multi-clauding)."""
    sessions = db.exec(
        _base_query(start, end)
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
                if overlap_sec > 60:  # At least 1 minute overlap
                    overlaps.append(
                        {
                            "session_ids": [s1.id, s2.id],
                            "overlap_minutes": round(overlap_sec / 60, 1),
                        }
                    )
    return overlaps


def collect_session_summaries(
    db: Session, start: datetime, end: datetime
) -> list[dict]:
    """Collect per-session insight summaries for the digest LLM prompt."""
    sessions = db.exec(
        _base_query(start, end).order_by(CodingSession.start_time)
    ).all()

    summaries = []
    for s in sessions:
        insights = db.exec(
            select(Insight).where(Insight.session_id == s.id)
        ).all()

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

        summaries.append(
            {
                "session_id": s.id,
                "start_time": s.start_time.isoformat(),
                "duration_min": round(duration, 1),
                "model": s.model,
                "tool_count": tool_count,
                "error_count": error_count,
                "total_tokens": s.total_tokens,
                "summary": summary_text,
                "frictions": friction_texts,
                "wins": win_texts,
            }
        )

    return summaries


def compute_all(
    db: Session,
    start: datetime,
    end: datetime,
) -> DigestStats:
    """Compute all statistics for a digest period."""
    sessions = db.exec(_base_query(start, end)).all()

    # Basic aggregates
    total_tokens = sum(s.total_tokens for s in sessions)
    total_prompt = sum(s.prompt_tokens for s in sessions)
    total_completion = sum(s.completion_tokens for s in sessions)
    total_duration = sum(
        (s.end_time - s.start_time).total_seconds() / 60
        for s in sessions
        if s.end_time
    )
    active_days = len({s.start_time.date() for s in sessions})
    total_tool_calls = db.exec(
        select(func.count())
        .select_from(ToolCall)
        .join(CodingSession, ToolCall.session_id == CodingSession.id)
        .where(CodingSession.start_time >= start)
        .where(CodingSession.start_time <= end)
    ).one()
    analysis_tokens = sum(
        s.analysis_prompt_tokens + s.analysis_completion_tokens for s in sessions
    )

    # Distributions
    tool_dist = compute_tool_distribution(db, start, end)
    error_breakdown, error_types = compute_error_breakdown(db, start, end)
    lang_dist = compute_language_distribution(db, start, end)
    time_of_day = compute_time_of_day(db, start, end)

    # Per-session data
    session_durations = [
        {
            "session_id": s.id,
            "duration_min": round(
                (s.end_time - s.start_time).total_seconds() / 60, 1
            )
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

    return DigestStats(
        period_start=start,
        period_end=end,
        session_count=len(sessions),
        analyzed_count=len(sessions),
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
        session_health=compute_session_health(db, start, end),
        tokens_per_session=tokens_per_session,
        overlapping_sessions=detect_overlapping_sessions(db, start, end),
        session_summaries=collect_session_summaries(db, start, end),
        permission_prompt_count=compute_permission_count(db, start, end),
        analysis_tokens_used=analysis_tokens,
    )
