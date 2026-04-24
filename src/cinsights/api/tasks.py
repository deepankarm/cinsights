"""Cross-session task API endpoints."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import CodingSession, Task

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


class TaskListItem(BaseModel):
    id: str
    session_id: str
    task_number: int
    name: str
    description: str
    start_turn: int
    end_turn: int
    turn_count: int
    prompt_tokens_total: int
    completion_tokens_total: int
    estimated_waste_tokens: int | None = None
    session_start_time: datetime | None = None
    user_id: str | None = None
    project_name: str | None = None


class TaskStatsResponse(BaseModel):
    total_tasks: int
    avg_turns_per_task: float
    avg_tokens_per_task: float
    top_task_names: list[dict]


@router.get("/", response_model=list[TaskListItem])
async def list_tasks(
    skip: int = 0,
    limit: int = 50,
    user_id: str | None = None,
    project_name: str | None = None,
    search: str | None = None,
    sort: str = "date",
    db: AsyncSession = Depends(get_db),
) -> list[TaskListItem]:
    """List tasks across all sessions with filters."""
    query = select(
        Task, CodingSession.start_time, CodingSession.user_id, CodingSession.project_name
    ).join(CodingSession, Task.session_id == CodingSession.id)

    if user_id:
        query = query.where(CodingSession.user_id == user_id)
    if project_name:
        query = query.where(CodingSession.project_name == project_name)
    if search:
        query = query.where(
            col(Task.name).contains(search) | col(Task.description).contains(search)
        )

    if sort == "cost":
        query = query.order_by(col(Task.prompt_tokens_total).desc())
    elif sort == "turns":
        query = query.order_by(col(Task.turn_count).desc())
    else:
        query = query.order_by(col(CodingSession.start_time).desc(), col(Task.task_number))

    query = query.offset(skip).limit(limit)
    result = await db.exec(query)

    return [
        TaskListItem(
            id=task.id,
            session_id=task.session_id,
            task_number=task.task_number,
            name=task.name,
            description=task.description,
            start_turn=task.start_turn,
            end_turn=task.end_turn,
            turn_count=task.turn_count,
            prompt_tokens_total=task.prompt_tokens_total,
            completion_tokens_total=task.completion_tokens_total,
            estimated_waste_tokens=task.estimated_waste_tokens,
            session_start_time=session_start,
            user_id=uid,
            project_name=proj,
        )
        for task, session_start, uid, proj in result.all()
    ]


@router.get("/stats", response_model=TaskStatsResponse)
async def get_task_stats(
    user_id: str | None = None,
    project_name: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> TaskStatsResponse:
    """Aggregate task statistics."""
    query = select(
        func.count(),
        func.avg(Task.turn_count),
        func.avg(Task.prompt_tokens_total),
    ).select_from(Task)

    if user_id or project_name:
        query = query.join(CodingSession, Task.session_id == CodingSession.id)
        if user_id:
            query = query.where(CodingSession.user_id == user_id)
        if project_name:
            query = query.where(CodingSession.project_name == project_name)

    result = await db.exec(query)
    row = result.one()
    total = row[0] or 0
    avg_turns = round(row[1] or 0, 1)
    avg_tokens = round(row[2] or 0, 0)

    # Top task names
    name_query = (
        select(Task.name, func.count().label("cnt"))
        .group_by(Task.name)
        .order_by(func.count().desc())
        .limit(10)
    )
    name_result = await db.exec(name_query)
    top_names = [{"name": name, "count": cnt} for name, cnt in name_result.all()]

    return TaskStatsResponse(
        total_tasks=total,
        avg_turns_per_task=avg_turns,
        avg_tokens_per_task=avg_tokens,
        top_task_names=top_names,
    )
