from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import CodingSession, SessionBaseline, SessionDailyTrend, SessionStatus

router = APIRouter(prefix="/api/trends", tags=["trends"])


class TrendPoint(BaseModel):
    date: str
    session_count: int
    analyzed_count: int
    total_tokens: int
    total_tool_calls: int
    avg_read_edit_ratio: float | None
    avg_edits_without_read_pct: float | None
    avg_error_rate: float | None
    avg_research_mutation_ratio: float | None
    avg_session_duration_ms: float | None
    agent_distribution_json: str | None


class BaselineRead(BaseModel):
    id: str
    user_id: str
    project_name: str | None
    session_count: int
    avg_turns: float
    avg_tool_count: float
    avg_read_edit_ratio: float
    avg_error_rate: float
    avg_duration_ms: float


@router.get("/daily", response_model=list[TrendPoint])
async def get_daily_trends(
    project: str | None = Query(None),
    user_id: str | None = Query(None),
    days: int = Query(30),
    db: AsyncSession = Depends(get_db),
) -> list[TrendPoint]:
    query = select(SessionDailyTrend).order_by(col(SessionDailyTrend.date).desc()).limit(days * 10)

    if project:
        query = query.where(SessionDailyTrend.project_name == project)
    if user_id:
        query = query.where(SessionDailyTrend.user_id == user_id)

    result = await db.exec(query)
    rows = result.all()

    # Aggregate by date (across users/projects if not filtered)
    by_date: dict[str, list[SessionDailyTrend]] = {}
    for row in rows:
        by_date.setdefault(row.date, []).append(row)

    points = []
    for date in sorted(by_date.keys())[-days:]:
        day_rows = by_date[date]
        points.append(
            TrendPoint(
                date=date,
                session_count=sum(r.session_count for r in day_rows),
                analyzed_count=sum(r.analyzed_count for r in day_rows),
                total_tokens=sum(r.total_tokens for r in day_rows),
                total_tool_calls=sum(r.total_tool_calls for r in day_rows),
                avg_read_edit_ratio=_avg([r.avg_read_edit_ratio for r in day_rows]),
                avg_edits_without_read_pct=_avg([r.avg_edits_without_read_pct for r in day_rows]),
                avg_error_rate=_avg([r.avg_error_rate for r in day_rows]),
                avg_research_mutation_ratio=_avg([r.avg_research_mutation_ratio for r in day_rows]),
                avg_session_duration_ms=_avg([r.avg_session_duration_ms for r in day_rows]),
                agent_distribution_json=_merge_agent_dist(day_rows),
            )
        )

    return points


@router.get("/baselines", response_model=list[BaselineRead])
async def get_baselines(
    project: str | None = Query(None),
    user_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> list[BaselineRead]:
    query = select(SessionBaseline)
    if project:
        query = query.where(SessionBaseline.project_name == project)
    if user_id:
        query = query.where(SessionBaseline.user_id == user_id)

    result = await db.exec(query)
    return [
        BaselineRead(
            id=b.id,
            user_id=b.user_id,
            project_name=b.project_name,
            session_count=b.session_count,
            avg_turns=b.avg_turns,
            avg_tool_count=b.avg_tool_count,
            avg_read_edit_ratio=b.avg_read_edit_ratio,
            avg_error_rate=b.avg_error_rate,
            avg_duration_ms=b.avg_duration_ms,
        )
        for b in result.all()
    ]


class TokenDistribution(BaseModel):
    q1: int
    median: int
    q3: int
    whisker_low: int
    whisker_high: int
    max_val: int
    count: int


@router.get("/token-distribution", response_model=TokenDistribution | None)
async def get_token_distribution(
    project: str | None = Query(None),
    user_id: str | None = Query(None),
    db: AsyncSession = Depends(get_db),
) -> TokenDistribution | None:
    query = select(CodingSession.total_tokens).where(
        col(CodingSession.status).in_([SessionStatus.INDEXED, SessionStatus.ANALYZED]),
        CodingSession.total_tokens > 0,
    )
    if project:
        query = query.where(CodingSession.project_name == project)
    if user_id:
        query = query.where(CodingSession.user_id == user_id)

    result = await db.exec(query)
    vals = sorted(result.all())
    if len(vals) < 3:
        return None

    q1 = vals[len(vals) // 4]
    median = vals[len(vals) // 2]
    q3 = vals[len(vals) * 3 // 4]
    iqr = q3 - q1
    whisker_low = max(vals[0], q1 - int(1.5 * iqr))
    whisker_high = min(vals[-1], q3 + int(1.5 * iqr))

    return TokenDistribution(
        q1=q1, median=median, q3=q3,
        whisker_low=whisker_low, whisker_high=whisker_high,
        max_val=vals[-1], count=len(vals),
    )


def _avg(values: list[float | None]) -> float | None:
    nums = [v for v in values if v is not None]
    if not nums:
        return None
    return round(sum(nums) / len(nums), 2)


def _merge_agent_dist(rows: list[SessionDailyTrend]) -> str | None:
    import json

    merged: dict[str, int] = {}
    for r in rows:
        if r.agent_distribution_json:
            try:
                dist = json.loads(r.agent_distribution_json)
                for agent, count in dist.items():
                    merged[agent] = merged.get(agent, 0) + count
            except (json.JSONDecodeError, TypeError):
                pass
    return json.dumps(merged) if merged else None
