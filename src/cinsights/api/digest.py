from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import col, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import Digest, DigestSection

router = APIRouter(prefix="/api/digests", tags=["digests"])


class DigestSectionRead(BaseModel):
    id: str
    section_type: str
    title: str
    content: str
    order: int
    metadata: dict | list | None = None  # Parsed from metadata_json


class DigestRead(BaseModel):
    id: str
    user_id: str | None
    project_name: str | None
    period_start: datetime
    period_end: datetime
    session_count: int
    status: str
    analysis_prompt_tokens: int
    analysis_completion_tokens: int
    created_at: datetime
    completed_at: datetime | None


class DigestDetail(BaseModel):
    id: str
    user_id: str | None
    project_name: str | None
    period_start: datetime
    period_end: datetime
    session_count: int
    status: str
    stats: dict | None = None  # Parsed from stats_json
    sections: list[DigestSectionRead]
    analysis_prompt_tokens: int
    analysis_completion_tokens: int
    created_at: datetime
    completed_at: datetime | None


@router.get("/", response_model=list[DigestRead])
async def list_digests(
    limit: int = 10,
    project: str | None = None,
    global_only: bool = False,
    db: AsyncSession = Depends(get_db),
) -> list[DigestRead]:
    """List digests, newest first. Filter by project or global scope."""
    q = select(Digest).order_by(col(Digest.created_at).desc())
    if project:
        q = q.where(Digest.project_name == project)
    elif global_only:
        q = q.where(Digest.project_name.is_(None))
    result = await db.exec(q.limit(limit))
    digests = result.all()

    return [
        DigestRead(
            id=d.id,
            user_id=d.user_id,
            project_name=d.project_name,
            period_start=d.period_start,
            period_end=d.period_end,
            session_count=d.session_count,
            status=d.status,
            analysis_prompt_tokens=d.analysis_prompt_tokens,
            analysis_completion_tokens=d.analysis_completion_tokens,
            created_at=d.created_at,
            completed_at=d.completed_at,
        )
        for d in digests
    ]


@router.get("/{digest_id}", response_model=DigestDetail)
async def get_digest(
    digest_id: str, db: AsyncSession = Depends(get_db)
) -> DigestDetail:
    """Get a digest with all sections and stats."""
    digest = await db.get(Digest, digest_id)
    if not digest:
        raise HTTPException(status_code=404, detail="Digest not found")

    sections_result = await db.exec(
        select(DigestSection)
        .where(DigestSection.digest_id == digest_id)
        .order_by(DigestSection.order)
    )
    sections = sections_result.all()

    stats = None
    if digest.stats_json:
        stats = json.loads(digest.stats_json)

    return DigestDetail(
        id=digest.id,
        user_id=digest.user_id,
        project_name=digest.project_name,
        period_start=digest.period_start,
        period_end=digest.period_end,
        session_count=digest.session_count,
        status=digest.status,
        stats=stats,
        sections=[
            DigestSectionRead(
                id=s.id,
                section_type=s.section_type,
                title=s.title,
                content=s.content,
                order=s.order,
                metadata=json.loads(s.metadata_json) if s.metadata_json else None,
            )
            for s in sections
        ],
        analysis_prompt_tokens=digest.analysis_prompt_tokens,
        analysis_completion_tokens=digest.analysis_completion_tokens,
        created_at=digest.created_at,
        completed_at=digest.completed_at,
    )
