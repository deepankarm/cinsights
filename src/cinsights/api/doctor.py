"""Doctor API — self-observability endpoints for cinsights operations."""

from __future__ import annotations

import json
from datetime import datetime

import sqlalchemy as sa
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlmodel import col, func, select
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.db.engine import get_db
from cinsights.db.models import (
    CodingSession,
    Digest,
    LLMCallLog,
    LLMCallStatus,
    RefreshRun,
    SessionStatus,
)

router = APIRouter(prefix="/api/doctor", tags=["doctor"])


# ---------------------------------------------------------------------------
# Response models
# ---------------------------------------------------------------------------


class RefreshRunRead(BaseModel):
    id: str
    command: str
    started_at: datetime
    completed_at: datetime | None
    status: str
    sessions_analyzed: int
    digests_generated: int
    total_prompt_tokens: int
    total_completion_tokens: int
    estimated_cost_usd: float | None
    wall_seconds: float | None
    db_size_bytes: int | None
    error_message: str | None
    metadata: dict | None


class DbSizePoint(BaseModel):
    timestamp: datetime
    bytes: int


class ConfigLimit(BaseModel):
    key: str
    value: int
    description: str


class ConfigSnapshot(BaseModel):
    model: str
    provider: str
    limits: list[ConfigLimit]


class SystemHealthResponse(BaseModel):
    total_sessions: int
    indexed_sessions: int
    analyzed_sessions: int
    failed_sessions: int
    total_projects: int
    total_developers: int
    db_size_bytes: int | None
    db_size_history: list[DbSizePoint]
    last_refresh: RefreshRunRead | None
    last_analyze: RefreshRunRead | None
    last_digest: RefreshRunRead | None
    config: ConfigSnapshot


class CommandCost(BaseModel):
    command: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float | None
    run_count: int


class ProjectCost(BaseModel):
    project_name: str
    prompt_tokens: int
    completion_tokens: int
    estimated_cost_usd: float | None
    session_count: int


class DailyCost(BaseModel):
    date: str
    prompt_tokens: int
    completion_tokens: int


class CostSummaryResponse(BaseModel):
    total_prompt_tokens: int
    total_completion_tokens: int
    estimated_cost_usd: float | None
    by_command: list[CommandCost]
    by_project: list[ProjectCost]
    daily_trend: list[DailyCost]


class CallKindCost(BaseModel):
    """Per-call-kind cost breakdown from ``LLMCallLog`` (ticket M-001)."""

    call_kind: str
    model: str
    provider: str
    call_count: int
    success_count: int
    failure_count: int
    prompt_tokens: int
    completion_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    total_duration_ms: float
    avg_duration_ms: float
    estimated_cost_usd: float | None  # sum of stored dollar_cost (None-skipped)


class CallKindCostResponse(BaseModel):
    total_calls: int
    total_cost_usd: float | None
    total_prompt_tokens: int
    total_completion_tokens: int
    by_kind: list[CallKindCost]


class ProjectCoverage(BaseModel):
    project_name: str
    total_sessions: int
    indexed: int
    analyzed: int
    failed: int
    coverage_pct: float
    avg_interestingness: float | None


class ScoreBucket(BaseModel):
    bucket: str
    count: int


class CoverageResponse(BaseModel):
    projects: list[ProjectCoverage]
    score_distribution: list[ScoreBucket]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _run_to_read(run: RefreshRun, digest_context: str | None = None) -> RefreshRunRead:
    from cinsights.costs import estimate_cost

    metadata = json.loads(run.metadata_json) if run.metadata_json else {}
    if digest_context and "project" not in metadata:
        metadata["project"] = digest_context
    return RefreshRunRead(
        id=run.id,
        command=run.command,
        started_at=run.started_at,
        completed_at=run.completed_at,
        status=run.status,
        sessions_analyzed=run.sessions_analyzed,
        digests_generated=run.digests_generated,
        total_prompt_tokens=run.total_prompt_tokens,
        total_completion_tokens=run.total_completion_tokens,
        estimated_cost_usd=estimate_cost(run.total_prompt_tokens, run.total_completion_tokens),
        wall_seconds=run.wall_seconds,
        db_size_bytes=run.db_size_bytes,
        error_message=run.error_message,
        metadata=metadata or None,
    )


async def _latest_run(db: AsyncSession, command: str) -> RefreshRunRead | None:
    from cinsights.db.models import RefreshRunCommand, RefreshRunStatus

    q = (
        select(RefreshRun)
        .where(
            RefreshRun.command == RefreshRunCommand(command),
            RefreshRun.status == RefreshRunStatus.SUCCESS,
        )
        .order_by(col(RefreshRun.started_at).desc())
        .limit(1)
    )
    result = await db.exec(q)
    run = result.first()
    return _run_to_read(run) if run else None


async def _enrich_with_digest_context(
    db: AsyncSession,
    runs: list[RefreshRun],
) -> dict[str, str]:
    """For digest/refresh runs, find which projects were targeted."""
    from cinsights.db.models import RefreshRunCommand

    digest_runs = [
        r for r in runs if r.command in (RefreshRunCommand.DIGEST, RefreshRunCommand.REFRESH)
    ]
    if not digest_runs:
        return {}

    context: dict[str, str] = {}
    for run in digest_runs:
        end = run.completed_at or run.started_at
        q = select(Digest.project_name).where(
            Digest.created_at >= run.started_at, Digest.created_at <= end
        )
        rows = (await db.exec(q)).all()
        projects = [p for p in rows if p]
        if projects:
            context[run.id] = ", ".join(projects)
    return context


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.get("/health", response_model=SystemHealthResponse)
async def get_health(db: AsyncSession = Depends(get_db)) -> SystemHealthResponse:
    # Session counts by status
    q = select(
        CodingSession.status,
        func.count(),
    ).group_by(CodingSession.status)
    rows = (await db.exec(q)).all()
    counts = {str(status): count for status, count in rows}
    analyzed = counts.get(SessionStatus.ANALYZED, 0)
    indexed = counts.get(SessionStatus.INDEXED, 0)
    failed = counts.get(SessionStatus.FAILED, 0)
    total = sum(counts.values())

    # Distinct projects and developers
    proj_q = select(func.count(CodingSession.project_name.distinct()))
    dev_q = select(func.count(CodingSession.user_id.distinct()))
    total_projects = (await db.exec(proj_q)).one()
    total_developers = (await db.exec(dev_q)).one()

    # Latest run per command
    last_refresh = await _latest_run(db, "refresh")
    last_analyze = await _latest_run(db, "analyze")
    last_digest = await _latest_run(db, "digest")

    # DB size history
    size_q = (
        select(RefreshRun.started_at, RefreshRun.db_size_bytes)
        .where(RefreshRun.db_size_bytes.isnot(None))
        .order_by(RefreshRun.started_at)
    )
    size_rows = (await db.exec(size_q)).all()
    db_size_history = [DbSizePoint(timestamp=ts, bytes=b) for ts, b in size_rows]
    latest_size = db_size_history[-1].bytes if db_size_history else None

    # Current config
    from cinsights.settings import LimitsConfig, get_config

    config = get_config()
    limits_schema = LimitsConfig.model_json_schema().get("properties", {})
    limits_list = [
        ConfigLimit(
            key=k,
            value=v,
            description=limits_schema.get(k, {}).get("description", ""),
        )
        for k, v in config.limits.model_dump().items()
    ]
    config_snap = ConfigSnapshot(
        model=config.llm.model,
        provider=config.llm.provider,
        limits=limits_list,
    )

    return SystemHealthResponse(
        total_sessions=total,
        indexed_sessions=indexed,
        analyzed_sessions=analyzed,
        failed_sessions=failed,
        total_projects=total_projects,
        total_developers=total_developers,
        db_size_bytes=latest_size,
        db_size_history=db_size_history,
        last_refresh=last_refresh,
        last_analyze=last_analyze,
        last_digest=last_digest,
        config=config_snap,
    )


@router.get("/runs", response_model=list[RefreshRunRead])
async def get_runs(
    command: str | None = None,
    status: str | None = None,
    skip: int = 0,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[RefreshRunRead]:
    q = select(RefreshRun).order_by(col(RefreshRun.started_at).desc())
    if command:
        q = q.where(RefreshRun.command == command)
    if status:
        q = q.where(RefreshRun.status == status)
    q = q.offset(skip).limit(limit)
    runs = list((await db.exec(q)).all())
    digest_ctx = await _enrich_with_digest_context(db, runs)
    return [_run_to_read(r, digest_ctx.get(r.id)) for r in runs]


@router.get("/cost", response_model=CostSummaryResponse)
async def get_cost(db: AsyncSession = Depends(get_db)) -> CostSummaryResponse:
    from cinsights.costs import estimate_cost

    # By command
    cmd_q = select(
        RefreshRun.command,
        func.sum(RefreshRun.total_prompt_tokens),
        func.sum(RefreshRun.total_completion_tokens),
        func.count(),
    ).group_by(RefreshRun.command)
    cmd_rows = (await db.exec(cmd_q)).all()

    total_prompt = 0
    total_completion = 0
    by_command = []
    for cmd, prompt, comp, cnt in cmd_rows:
        p, c = prompt or 0, comp or 0
        total_prompt += p
        total_completion += c
        by_command.append(
            CommandCost(
                command=str(cmd),
                prompt_tokens=p,
                completion_tokens=c,
                estimated_cost_usd=estimate_cost(p, c),
                run_count=cnt,
            )
        )

    # By project (from session analysis tokens)
    proj_q = (
        select(
            CodingSession.project_name,
            func.sum(CodingSession.analysis_prompt_tokens),
            func.sum(CodingSession.analysis_completion_tokens),
            func.count(),
        )
        .where(
            CodingSession.status == SessionStatus.ANALYZED,
        )
        .group_by(CodingSession.project_name)
    )
    proj_rows = (await db.exec(proj_q)).all()

    by_project = []
    for proj, prompt, comp, cnt in proj_rows:
        p, c = prompt or 0, comp or 0
        by_project.append(
            ProjectCost(
                project_name=proj or "unknown",
                prompt_tokens=p,
                completion_tokens=c,
                estimated_cost_usd=estimate_cost(p, c),
                session_count=cnt,
            )
        )
    by_project.sort(key=lambda x: (x.prompt_tokens + x.completion_tokens), reverse=True)

    # Daily trend
    daily_q = (
        select(
            func.date(RefreshRun.started_at),
            func.sum(RefreshRun.total_prompt_tokens),
            func.sum(RefreshRun.total_completion_tokens),
        )
        .group_by(func.date(RefreshRun.started_at))
        .order_by(func.date(RefreshRun.started_at))
    )
    daily_rows = (await db.exec(daily_q)).all()

    daily_trend = [
        DailyCost(date=str(d), prompt_tokens=p or 0, completion_tokens=c or 0)
        for d, p, c in daily_rows
    ]

    return CostSummaryResponse(
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        estimated_cost_usd=estimate_cost(total_prompt, total_completion),
        by_command=by_command,
        by_project=by_project,
        daily_trend=daily_trend,
    )


@router.get("/cost-by-kind", response_model=CallKindCostResponse)
async def get_cost_by_kind(db: AsyncSession = Depends(get_db)) -> CallKindCostResponse:
    """Aggregate ``LLMCallLog`` by (call_kind, model, provider).

    Per-call cost attribution added by ticket M-001. Each future metric
    ticket that adds a new LLM call kind will show up here without any
    additional wiring, as long as it tags calls with a new
    :class:`LLMCallKind` enum value.
    """
    success_case = func.sum(sa.case((LLMCallLog.status == LLMCallStatus.SUCCESS, 1), else_=0))
    failure_case = func.sum(sa.case((LLMCallLog.status == LLMCallStatus.FAILURE, 1), else_=0))

    q = select(
        LLMCallLog.call_kind,
        LLMCallLog.model,
        LLMCallLog.provider,
        func.count().label("call_count"),
        success_case.label("success_count"),
        failure_case.label("failure_count"),
        func.sum(LLMCallLog.prompt_tokens),
        func.sum(LLMCallLog.completion_tokens),
        func.sum(LLMCallLog.cache_read_tokens),
        func.sum(LLMCallLog.cache_write_tokens),
        func.sum(LLMCallLog.duration_ms),
        func.sum(LLMCallLog.dollar_cost),
    ).group_by(LLMCallLog.call_kind, LLMCallLog.model, LLMCallLog.provider)
    rows = (await db.exec(q)).all()

    by_kind: list[CallKindCost] = []
    total_calls = 0
    total_cost = 0.0
    any_cost = False
    total_prompt = 0
    total_completion = 0
    for (
        kind,
        model,
        provider,
        call_count,
        success_count,
        failure_count,
        prompt,
        comp,
        cache_read,
        cache_write,
        total_dur,
        dollar_sum,
    ) in rows:
        call_count = call_count or 0
        prompt = prompt or 0
        comp = comp or 0
        total_dur_f = float(total_dur or 0.0)
        total_calls += call_count
        total_prompt += prompt
        total_completion += comp
        if dollar_sum is not None:
            total_cost += float(dollar_sum)
            any_cost = True
        by_kind.append(
            CallKindCost(
                call_kind=str(kind),
                model=model,
                provider=provider,
                call_count=call_count,
                success_count=int(success_count or 0),
                failure_count=int(failure_count or 0),
                prompt_tokens=prompt,
                completion_tokens=comp,
                cache_read_tokens=cache_read or 0,
                cache_write_tokens=cache_write or 0,
                total_duration_ms=total_dur_f,
                avg_duration_ms=(total_dur_f / call_count) if call_count else 0.0,
                estimated_cost_usd=float(dollar_sum) if dollar_sum is not None else None,
            )
        )

    by_kind.sort(
        key=lambda r: (r.estimated_cost_usd or 0.0, r.prompt_tokens + r.completion_tokens),
        reverse=True,
    )
    return CallKindCostResponse(
        total_calls=total_calls,
        total_cost_usd=total_cost if any_cost else None,
        total_prompt_tokens=total_prompt,
        total_completion_tokens=total_completion,
        by_kind=by_kind,
    )


@router.get("/coverage", response_model=CoverageResponse)
async def get_coverage(db: AsyncSession = Depends(get_db)) -> CoverageResponse:
    # Per-project coverage
    cov_q = select(
        CodingSession.project_name,
        CodingSession.status,
        func.count(),
        func.avg(CodingSession.interestingness_score),
    ).group_by(CodingSession.project_name, CodingSession.status)
    rows = (await db.exec(cov_q)).all()

    # Aggregate by project
    proj_data: dict[str, dict] = {}
    for proj, status, count, avg_score in rows:
        name = proj or "unknown"
        if name not in proj_data:
            proj_data[name] = {"total": 0, "indexed": 0, "analyzed": 0, "failed": 0, "scores": []}
        proj_data[name]["total"] += count
        if str(status) == SessionStatus.INDEXED:
            proj_data[name]["indexed"] += count
        elif str(status) == SessionStatus.ANALYZED:
            proj_data[name]["analyzed"] += count
        elif str(status) == SessionStatus.FAILED:
            proj_data[name]["failed"] += count
        if avg_score is not None:
            proj_data[name]["scores"].append((avg_score, count))

    projects = []
    for name, d in sorted(
        proj_data.items(), key=lambda x: x[1]["analyzed"] / max(x[1]["total"], 1)
    ):
        total_w = sum(c for _, c in d["scores"])
        avg_int = sum(s * c for s, c in d["scores"]) / total_w if total_w else None
        projects.append(
            ProjectCoverage(
                project_name=name,
                total_sessions=d["total"],
                indexed=d["indexed"],
                analyzed=d["analyzed"],
                failed=d["failed"],
                coverage_pct=round(d["analyzed"] / max(d["total"], 1) * 100, 1),
                avg_interestingness=round(avg_int, 3) if avg_int is not None else None,
            )
        )

    # Score distribution
    score_q = select(CodingSession.interestingness_score).where(
        CodingSession.interestingness_score.isnot(None)
    )
    scores = (await db.exec(score_q)).all()
    buckets = {"0.0-0.2": 0, "0.2-0.4": 0, "0.4-0.6": 0, "0.6-0.8": 0, "0.8-1.0": 0}
    for s in scores:
        if s < 0.2:
            buckets["0.0-0.2"] += 1
        elif s < 0.4:
            buckets["0.2-0.4"] += 1
        elif s < 0.6:
            buckets["0.4-0.6"] += 1
        elif s < 0.8:
            buckets["0.6-0.8"] += 1
        else:
            buckets["0.8-1.0"] += 1

    return CoverageResponse(
        projects=projects,
        score_distribution=[ScoreBucket(bucket=k, count=v) for k, v in buckets.items()],
    )
