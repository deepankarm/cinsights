from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends
from sqlmodel import Session

from cinsights.db.engine import get_db
from cinsights.stats import DigestStats, compute_all

router = APIRouter(prefix="/api/stats", tags=["stats"])


@router.get("/overview", response_model=DigestStats)
async def get_stats_overview(
    days: int = 7,
    project: str | None = None,
    db: Session = Depends(get_db),
):
    """Compute all stats for the given period. Zero LLM cost."""
    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    return compute_all(db, start, end, project_name=project)
