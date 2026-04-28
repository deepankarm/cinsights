from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import CodingSession, SessionStatus

router = APIRouter(prefix="/api/users", tags=["users"])


class UserSummary(BaseModel):
    user_id: str
    display_name: str
    session_count: int
    analyzed_count: int
    indexed_count: int
    avg_read_edit_ratio: float | None
    avg_edits_without_read_pct: float | None
    avg_research_mutation_ratio: float | None
    avg_write_vs_edit_pct: float | None
    avg_error_rate: float | None
    avg_repeated_edits: float | None
    avg_subagent_spawn_rate: float | None
    avg_tokens_per_useful_edit: float | None
    avg_context_pressure: float | None
    avg_turn_count: float | None
    avg_tool_calls_per_turn: float | None
    avg_duration_ms: float | None
    total_tokens: int
    projects: list[str]
    agents: list[str]
    sources: list[str]

    # Token efficiency
    avg_efficiency_score: float | None = None
    avg_tasks_per_session: float | None = None
    total_tasks: int = 0


@router.get("/", response_model=list[UserSummary])
async def list_users(
    start: str | None = Query(None, description="Start date (YYYY-MM-DD)"),
    end: str | None = Query(None, description="End date (YYYY-MM-DD)"),
    project: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[UserSummary]:
    query = select(CodingSession).where(
        col(CodingSession.status).in_([SessionStatus.INDEXED, SessionStatus.ANALYZED]),
        CodingSession.user_id.is_not(None),  # type: ignore[union-attr]
    )

    if start:
        query = query.where(CodingSession.start_time >= datetime.fromisoformat(start))
    if end:
        query = query.where(CodingSession.start_time <= datetime.fromisoformat(f"{end}T23:59:59"))
    if project:
        query = query.where(CodingSession.project_name == project)

    result = await db.exec(query)
    sessions = result.all()

    by_user: dict[str, list[CodingSession]] = {}
    for s in sessions:
        by_user.setdefault(s.user_id or "unknown", []).append(s)

    summaries = []
    for user_id, user_sessions in by_user.items():
        name_part = user_id.split("@")[0]
        # Clean up GitHub noreply format: "12345+username" → "username"
        if "+" in name_part and name_part.split("+")[0].isdigit():
            name_part = name_part.split("+", 1)[1]

        projects = sorted({s.project_name for s in user_sessions if s.project_name})
        agents = sorted({s.agent_type for s in user_sessions if s.agent_type})
        sources = sorted({s.source for s in user_sessions if s.source})

        durations = []
        for s in user_sessions:
            if s.start_time and s.end_time:
                ms = (s.end_time - s.start_time).total_seconds() * 1000
                if ms > 0:
                    durations.append(ms)

        summaries.append(
            UserSummary(
                user_id=user_id,
                display_name=name_part,
                session_count=len(user_sessions),
                analyzed_count=sum(1 for s in user_sessions if s.status == SessionStatus.ANALYZED),
                indexed_count=sum(1 for s in user_sessions if s.status == SessionStatus.INDEXED),
                avg_read_edit_ratio=_avg(s.read_edit_ratio for s in user_sessions),
                avg_edits_without_read_pct=_avg(s.edits_without_read_pct for s in user_sessions),
                avg_research_mutation_ratio=_avg(s.research_mutation_ratio for s in user_sessions),
                avg_write_vs_edit_pct=_avg(s.write_vs_edit_pct for s in user_sessions),
                avg_error_rate=_avg(s.error_rate for s in user_sessions),
                avg_repeated_edits=_avg(s.repeated_edits_count for s in user_sessions),
                avg_subagent_spawn_rate=_avg(s.subagent_spawn_rate for s in user_sessions),
                avg_tokens_per_useful_edit=_avg(s.tokens_per_useful_edit for s in user_sessions),
                avg_context_pressure=_avg(s.context_pressure_score for s in user_sessions),
                avg_turn_count=_avg(s.turn_count for s in user_sessions),
                avg_tool_calls_per_turn=_avg(s.tool_calls_per_turn for s in user_sessions),
                avg_duration_ms=round(sum(durations) / len(durations)) if durations else None,
                total_tokens=sum(s.total_tokens for s in user_sessions),
                projects=projects,
                agents=agents,
                sources=sources,
                avg_efficiency_score=_avg(s.efficiency_score for s in user_sessions),
                avg_tasks_per_session=_avg(s.task_count for s in user_sessions),
                total_tasks=sum(s.task_count or 0 for s in user_sessions),
            )
        )

    summaries.sort(key=lambda u: u.session_count, reverse=True)
    return summaries


def _avg(values) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


@router.get("/{user_id}/stats")
async def get_user_stats(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from cinsights.db.models import ScopeStats

    q = (
        select(ScopeStats)
        .where(ScopeStats.scope_type == "user", ScopeStats.scope_value == user_id)
        .order_by(col(ScopeStats.computed_at).desc())
        .limit(1)
    )
    row = (await db.exec(q)).first()
    if not row or not row.stats_json:
        return {}
    return json.loads(row.stats_json)


class MoodQuote(BaseModel):
    quote: str
    mood: str
    project: str | None = None
    session_id: str | None = None


class MoodGroup(BaseModel):
    mood: str
    quotes: list[MoodQuote]


class UserMoodResponse(BaseModel):
    user_id: str
    total_sessions: int
    sessions_with_quotes: int
    mood_groups: list[MoodGroup]


@router.get("/{user_id}/mood-quotes", response_model=UserMoodResponse)
async def get_user_mood_quotes(
    user_id: str,
    db: AsyncSession = Depends(get_db),
) -> UserMoodResponse:
    query = select(
        CodingSession.id,
        CodingSession.project_name,
        CodingSession.metadata_json,
    ).where(
        CodingSession.user_id == user_id,
        col(CodingSession.status).in_([SessionStatus.ANALYZED, "ANALYZED"]),
    )
    result = await db.exec(query)
    rows = result.all()

    by_mood: dict[str, list[MoodQuote]] = defaultdict(list)
    sessions_with = 0

    for session_id, project_name, meta_json in rows:
        if not meta_json:
            continue
        meta = json.loads(meta_json)
        quotes = meta.get("notable_quotes", [])
        if not quotes:
            continue
        sessions_with += 1
        for q in quotes:
            mood = q.get("mood")
            if not mood:
                continue
            by_mood[mood].append(
                MoodQuote(
                    quote=q.get("quote", ""),
                    mood=mood,
                    project=project_name,
                    session_id=session_id,
                )
            )

    # Order moods by count descending
    mood_groups = [
        MoodGroup(mood=mood, quotes=quotes)
        for mood, quotes in sorted(by_mood.items(), key=lambda x: -len(x[1]))
    ]

    return UserMoodResponse(
        user_id=user_id,
        total_sessions=len(rows),
        sessions_with_quotes=sessions_with,
        mood_groups=mood_groups,
    )


class UserTaskInTheme(BaseModel):
    task_id: str
    name: str
    session_id: str
    date: datetime | None
    tokens: int
    turn_count: int


class UserThemeRead(BaseModel):
    theme_id: str
    theme_name: str
    project_name: str
    user_tokens: int  # tokens this user contributed to the theme
    theme_total_tokens: int  # total tokens across all contributors
    share_pct: float  # user_tokens / theme_total_tokens * 100
    user_task_count: int
    theme_dev_count: int  # distinct developers in the theme; UI hides share bar when 1
    last_active: datetime | None
    tasks: list[UserTaskInTheme] = []  # user's tasks within this theme, newest first


@router.get("/{user_id}/themes", response_model=list[UserThemeRead])
async def get_user_themes(
    user_id: str,
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[UserThemeRead]:
    """Themes this user has contributed to, ranked by recency-weighted volume.

    A theme is "the user's" if any of their tasks (joined via
    CodingSession.user_id) appear in the theme's task set.
    """
    from sqlmodel import func

    from cinsights.db.models import Task, Theme, ThemeTask

    # User-scoped aggregates per theme: their tokens, task count, last active
    user_agg_q = (
        select(
            Theme.id,
            Theme.name,
            Theme.project_name,
            Theme.total_tokens,
            func.sum(Task.prompt_tokens_total + Task.completion_tokens_total).label("user_tokens"),
            func.count(Task.id).label("user_task_count"),
            func.max(CodingSession.start_time).label("last_active"),
        )
        .join(ThemeTask, ThemeTask.theme_id == Theme.id)
        .join(Task, Task.id == ThemeTask.task_id)
        .join(CodingSession, CodingSession.id == Task.session_id)
        .where(CodingSession.user_id == user_id)
        .group_by(Theme.id, Theme.name, Theme.project_name, Theme.total_tokens)
    )
    rows = (await db.exec(user_agg_q)).all()
    if not rows:
        return []

    theme_ids = [row[0] for row in rows]

    # Theme-level: distinct developer count (so the UI knows when share % is meaningful)
    dev_count_q = (
        select(Theme.id, func.count(func.distinct(CodingSession.user_id)))
        .join(ThemeTask, ThemeTask.theme_id == Theme.id)
        .join(Task, Task.id == ThemeTask.task_id)
        .join(CodingSession, CodingSession.id == Task.session_id)
        .where(col(Theme.id).in_(theme_ids))
        .group_by(Theme.id)
    )
    dev_counts = dict((await db.exec(dev_count_q)).all())

    # User's tasks within each of those themes (one query, then group)
    tasks_q = (
        select(
            ThemeTask.theme_id,
            Task.id,
            Task.name,
            Task.session_id,
            Task.prompt_tokens_total,
            Task.completion_tokens_total,
            Task.turn_count,
            CodingSession.start_time,
        )
        .join(Task, Task.id == ThemeTask.task_id)
        .join(CodingSession, CodingSession.id == Task.session_id)
        .where(col(ThemeTask.theme_id).in_(theme_ids))
        .where(CodingSession.user_id == user_id)
        .order_by(col(CodingSession.start_time).desc())
    )
    tasks_by_theme: dict[str, list[UserTaskInTheme]] = {tid: [] for tid in theme_ids}
    for row in (await db.exec(tasks_q)).all():
        theme_id, task_id, task_name, session_id, p_tok, c_tok, turn_count, start_time = row
        tasks_by_theme[theme_id].append(
            UserTaskInTheme(
                task_id=task_id,
                name=task_name,
                session_id=session_id,
                date=start_time,
                tokens=int((p_tok or 0) + (c_tok or 0)),
                turn_count=int(turn_count or 0),
            )
        )

    now = datetime.utcnow()
    items: list[UserThemeRead] = []
    for theme_id, name, project_name, theme_total, user_tok, task_count, last_active in rows:
        user_tok = int(user_tok or 0)
        share = (user_tok / theme_total * 100) if theme_total > 0 else 0.0
        items.append(
            UserThemeRead(
                theme_id=theme_id,
                theme_name=name,
                project_name=project_name,
                user_tokens=user_tok,
                theme_total_tokens=theme_total,
                share_pct=round(share, 1),
                user_task_count=int(task_count or 0),
                theme_dev_count=int(dev_counts.get(theme_id, 1)),
                last_active=last_active,
                tasks=tasks_by_theme.get(theme_id, []),
            )
        )

    # Recency-weighted sort: tokens * 1/(1 + days_since/7).
    # Today's work weighted full; 7d old -> half; 30d old -> ~20%.
    def score(t: UserThemeRead) -> float:
        if not t.last_active:
            return 0.0
        days = (now - t.last_active).total_seconds() / 86400
        return t.user_tokens / (1 + days / 7)

    items.sort(key=score, reverse=True)
    return items[:limit]
