from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import CodingSession, Digest, Task, Theme, ThemeTask, ToolCall

router = APIRouter(prefix="/api/projects", tags=["projects"])


class ProjectRead(BaseModel):
    name: str
    session_count: int
    analyzed_count: int
    developer_count: int
    active_days: int
    total_tokens: int
    total_tool_calls: int
    top_tools: list[str]
    languages: list[str]
    latest_session: datetime
    has_digest: bool
    agents: dict[str, int] = {}


@router.get("/", response_model=list[ProjectRead])
async def list_projects(db: AsyncSession = Depends(get_db)) -> list[ProjectRead]:
    """List all detected projects with summary stats."""
    rows_result = await db.exec(
        select(
            CodingSession.project_name,
            func.count(),
            func.sum(CodingSession.total_tokens),
            func.max(CodingSession.start_time),
            func.count(CodingSession.id).filter(CodingSession.status == "analyzed"),
            func.count(func.distinct(CodingSession.user_id)),
            func.count(func.distinct(func.date(CodingSession.start_time))),
        )
        .where(CodingSession.project_name.isnot(None))
        .group_by(CodingSession.project_name)
        .order_by(func.count().desc())
    )
    rows = rows_result.all()

    results: list[ProjectRead] = []
    for (
        project_name,
        session_count,
        total_tokens,
        latest,
        analyzed_count,
        dev_count,
        active_days,
    ) in rows:
        # Top tools for this project
        tool_result = await db.exec(
            select(ToolCall.tool_name, func.count())
            .join(CodingSession, ToolCall.session_id == CodingSession.id)
            .where(CodingSession.project_name == project_name)
            .group_by(ToolCall.tool_name)
            .order_by(func.count().desc())
            .limit(3)
        )
        tool_rows = tool_result.all()

        # Agent distribution for this project
        agent_result = await db.exec(
            select(CodingSession.agent_type, func.count())
            .where(CodingSession.project_name == project_name)
            .where(CodingSession.agent_type.isnot(None))
            .group_by(CodingSession.agent_type)
        )
        agents = {name: count for name, count in agent_result.all()}

        # Check if a digest exists for this project
        digest_count_result = await db.exec(
            select(func.count())
            .select_from(Digest)
            .where(Digest.project_name == project_name)
            .where(Digest.status == "complete")
        )
        has_digest = digest_count_result.one() > 0

        results.append(
            ProjectRead(
                name=project_name,
                session_count=session_count,
                analyzed_count=analyzed_count,
                developer_count=dev_count,
                active_days=active_days,
                total_tokens=total_tokens or 0,
                total_tool_calls=sum(c for _, c in tool_rows),
                top_tools=[name for name, _ in tool_rows],
                languages=[],
                latest_session=latest,
                has_digest=has_digest,
                agents=agents,
            )
        )

    return results


@router.get("/{project_name}/stats")
async def get_project_stats(
    project_name: str,
    db: AsyncSession = Depends(get_db),
) -> dict:
    from cinsights.db.models import ScopeStats

    q = (
        select(ScopeStats)
        .where(ScopeStats.scope_type == "project", ScopeStats.scope_value == project_name)
        .order_by(col(ScopeStats.computed_at).desc())
        .limit(1)
    )
    row = (await db.exec(q)).first()
    if not row or not row.stats_json:
        return {}
    return json.loads(row.stats_json)


class ThemeMember(BaseModel):
    task_id: str
    task_name: str
    user_id: str | None
    session_id: str
    date: datetime | None
    tokens: int


class ThemeRead(BaseModel):
    id: str
    name: str
    summary: str
    total_tokens: int
    task_count: int
    first_date: datetime | None
    last_date: datetime | None
    members: list[ThemeMember]


@router.get("/{project_name}/themes", response_model=list[ThemeRead])
async def list_project_themes(
    project_name: str,
    db: AsyncSession = Depends(get_db),
) -> list[ThemeRead]:
    """All themes for a project, ordered by total_tokens desc, members hydrated.

    Returns ``[]`` when the project has no themes (not yet digested or
    skipped due to too few tasks).
    """
    themes_result = await db.exec(
        select(Theme)
        .where(Theme.project_name == project_name)
        .order_by(col(Theme.total_tokens).desc())
    )
    themes = themes_result.all()
    if not themes:
        return []

    theme_ids = [t.id for t in themes]

    # Hydrate members in one go: ThemeTask → Task → CodingSession
    members_result = await db.exec(
        select(
            ThemeTask.theme_id,
            Task.id,
            Task.name,
            Task.prompt_tokens_total,
            Task.completion_tokens_total,
            Task.session_id,
            CodingSession.user_id,
            CodingSession.start_time,
        )
        .join(Task, Task.id == ThemeTask.task_id)
        .join(CodingSession, CodingSession.id == Task.session_id)
        .where(col(ThemeTask.theme_id).in_(theme_ids))
        .order_by(CodingSession.start_time)
    )
    members_by_theme: dict[str, list[ThemeMember]] = {tid: [] for tid in theme_ids}
    for row in members_result.all():
        (theme_id, task_id, task_name, p_tok, c_tok, session_id, user_id, start_time) = row
        members_by_theme[theme_id].append(
            ThemeMember(
                task_id=task_id,
                task_name=task_name,
                user_id=user_id,
                session_id=session_id,
                date=start_time,
                tokens=(p_tok or 0) + (c_tok or 0),
            )
        )

    return [
        ThemeRead(
            id=t.id,
            name=t.name,
            summary=t.summary,
            total_tokens=t.total_tokens,
            task_count=t.task_count,
            first_date=t.first_date,
            last_date=t.last_date,
            members=members_by_theme.get(t.id, []),
        )
        for t in themes
    ]
