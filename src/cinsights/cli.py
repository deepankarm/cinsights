from __future__ import annotations

import asyncio
import logging
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col
from sqlmodel import select as select_fn
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.config import get_settings

if TYPE_CHECKING:
    from cinsights.analysis.digest import DigestAnalyzer

app = typer.Typer(name="cinsights", help="LLM-powered insights from coding agent sessions.")
console = Console()


def _content_hash(stats_json: str) -> str:
    """SHA-256 of digest stats with timestamp fields removed.

    `period_start` / `period_end` are set to now() on every digest run, so a
    naive hash of the full JSON would never match. We strip those fields (plus
    any other inherently-runtime fields) before hashing so reruns within the
    same data window collapse to a single hash and skip the LLM step.
    """
    import hashlib
    import json as json_mod

    payload = json_mod.loads(stats_json)
    # Remove fields that change every run regardless of underlying data.
    for noise in ("period_start", "period_end"):
        payload.pop(noise, None)
    canonical = json_mod.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class _RunHandle:
    """Mutable counters the body of a tracked run updates as it works.

    The context manager creates one of these, yields it to the caller, and
    persists its final values to the refresh_run row on exit.
    """

    __slots__ = (
        "digests_generated",
        "id",
        "sessions_analyzed",
        "total_completion_tokens",
        "total_prompt_tokens",
    )

    def __init__(self, run_id: str):
        self.id = run_id
        self.sessions_analyzed = 0
        self.digests_generated = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0


@asynccontextmanager
async def _track_run(command: str) -> AsyncIterator[_RunHandle]:
    """Persist a refresh_run row for self-observability.

    Wrap analyze/digest/refresh bodies with ``async with _track_run("refresh")
    as run:`` and mutate the yielded handle's counters. On exit, the row is
    updated with wall time, status, DB size, and the final counter values.
    """
    from cinsights.db.engine import get_sessionmaker
    from cinsights.db.models import RefreshRun, RefreshRunCommand, RefreshRunStatus

    settings = get_settings()
    sessionmaker = get_sessionmaker()
    started = datetime.now(UTC)
    started_perf = time.perf_counter()

    async with sessionmaker() as db:
        run = RefreshRun(
            tenant_id=settings.tenant_id,
            command=RefreshRunCommand(command),
            started_at=started,
            status=RefreshRunStatus.RUNNING,
        )
        db.add(run)
        await db.commit()
        await db.refresh(run)
        run_id = run.id

    handle = _RunHandle(run_id)
    error: str | None = None
    try:
        yield handle
    except BaseException as exc:
        error = str(exc)
        raise
    finally:
        wall = time.perf_counter() - started_perf
        db_size = None
        if settings.database_url.startswith("sqlite"):
            db_path = settings.database_url.replace("sqlite:///", "", 1)
            try:
                db_size = os.path.getsize(db_path)
            except OSError:
                db_size = None

        async with sessionmaker() as db:
            run = await db.get(RefreshRun, run_id)
            if run is not None:
                run.completed_at = datetime.now(UTC)
                run.wall_seconds = wall
                run.status = (
                    RefreshRunStatus.FAILED if error else RefreshRunStatus.SUCCESS
                )
                run.db_size_bytes = db_size
                run.sessions_analyzed = handle.sessions_analyzed
                run.digests_generated = handle.digests_generated
                run.total_prompt_tokens = handle.total_prompt_tokens
                run.total_completion_tokens = handle.total_completion_tokens
                if error:
                    run.error_message = error[:2000]
                db.add(run)
                await db.commit()


async def _store_analysis(
    db: AsyncSession,
    trace_id: str,
    session_id: str,
    trace,
    spans: list,
    result,
    source,
    force: bool,
    existing,
) -> int:
    """Store trace data and analysis results in the database.

    Returns the number of insights persisted. On re-analyze (existing row or
    --force), all prior tool_calls and insights for this session are deleted
    via explicit queries — we never touch lazy relationship attributes because
    AsyncSession does not support implicit lazy loads.
    """
    from cinsights.db.models import (
        CodingSession,
        Insight,
        InsightCategory,
        InsightSeverity,
        SessionStatus,
        ToolCall,
    )

    root = next((s for s in spans if s.parent_id is None), None)
    # CC traces: tool calls have tool.name, permission/notification use span name
    tool_spans = [
        s for s in spans
        if s.parent_id is not None
        and (s.tool_name or "Permission" in s.name or "Notification" in s.name)
    ]

    # Extract user.id from span attributes
    user_id = None
    for s in spans:
        if not user_id:
            user_id = s.user_id
        if user_id:
            break

    # Detect project from file paths in tool calls (heuristic)
    from cinsights.stats import detect_project_from_tool_calls

    project_name = detect_project_from_tool_calls(tool_spans)

    last_span_time = max(s.end_time for s in spans) if spans else None

    # Aggregate tokens from all Turn spans + build context growth data
    import json as json_mod

    turn_spans = sorted(
        [s for s in spans if s.name.startswith("Turn ")],
        key=lambda s: s.start_time,
    )
    total_completion = sum(s.completion_tokens for s in turn_spans)
    last_turn_prompt = turn_spans[-1].prompt_tokens if turn_spans else 0
    total_tokens = last_turn_prompt + total_completion

    context_growth = json_mod.dumps([
        {
            "turn": int(s.name.replace("Turn ", "")),
            "prompt_tokens": s.prompt_tokens,
            "completion_tokens": s.completion_tokens,
        }
        for s in turn_spans
    ])

    settings = get_settings()
    tenant_id = settings.tenant_id
    if not existing:
        coding_session = CodingSession(
            id=trace_id,
            tenant_id=tenant_id,
            source=settings.source,
            agent_type=settings.agent_type,
            session_id=session_id,
            user_id=user_id,
            project_name=project_name,
            start_time=trace.start_time,
            end_time=trace.end_time,
            model=root.model_name if root else None,
            total_tokens=total_tokens,
            prompt_tokens=last_turn_prompt,
            completion_tokens=total_completion,
            context_growth_json=context_growth,
            span_count=len(spans),
            last_span_time=last_span_time,
            status=SessionStatus.PENDING,
        )
        db.add(coding_session)
    else:
        coding_session = existing
        # Update metadata that may have changed
        coding_session.user_id = user_id or existing.user_id
        coding_session.project_name = project_name or existing.project_name
        coding_session.total_tokens = total_tokens
        coding_session.prompt_tokens = last_turn_prompt
        coding_session.completion_tokens = total_completion
        coding_session.context_growth_json = context_growth
        coding_session.span_count = len(spans)
        coding_session.last_span_time = last_span_time
        # tenant/source/agent are intentionally NOT overwritten on re-analyze —
        # they reflect where the row was first ingested.

    # Clear old data if re-analyzing. Use explicit FK queries — AsyncSession
    # doesn't support implicit lazy relationship loads.
    if force or existing:
        old_tcs_result = await db.exec(
            select_fn(ToolCall).where(ToolCall.session_id == trace_id)
        )
        for tc in old_tcs_result.all():
            await db.delete(tc)
        old_ins_result = await db.exec(
            select_fn(Insight).where(Insight.session_id == trace_id)
        )
        for ins in old_ins_result.all():
            await db.delete(ins)
        await db.flush()

    for span in tool_spans:
        # Only store output for failed calls (error classification) to save DB space
        output = None
        if not span.is_success and span.output_value:
            output = span.output_value[:2000]

        tc = ToolCall(
            tenant_id=tenant_id,
            session_id=trace_id,
            span_id=span.span_id,
            tool_name=span.tool_name or span.name,
            input_value=span.input_value[:2000] if span.input_value else None,
            output_value=output,
            duration_ms=span.duration_ms,
            success=span.is_success,
            timestamp=span.start_time,
        )
        db.add(tc)

    for item in result.insights:
        try:
            cat = InsightCategory(item.category)
        except ValueError:
            cat = InsightCategory.PATTERN
        try:
            sev = InsightSeverity(item.severity)
        except ValueError:
            sev = InsightSeverity.INFO

        insight = Insight(
            tenant_id=tenant_id,
            session_id=trace_id,
            category=cat,
            title=item.title,
            content=item.content,
            severity=sev,
            prompt_version=settings.prompt_version_session,
        )
        db.add(insight)

    coding_session.status = SessionStatus.ANALYZED
    coding_session.analysis_prompt_tokens = result.usage_prompt_tokens
    coding_session.analysis_completion_tokens = result.usage_completion_tokens
    return len(result.insights)


@app.command()
def analyze(
    hours: int = typer.Option(24, help="Analyze sessions from the last N hours."),
    limit: int = typer.Option(50, help="Max sessions to analyze."),
    force: bool = typer.Option(False, help="Re-analyze already-analyzed sessions."),
    concurrency: int = typer.Option(5, help="Max concurrent LLM analysis requests."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
    trace_ids: list[str] | None = typer.Argument(
        None, help="Specific trace IDs to analyze. If omitted, fetches from Phoenix."
    ),
):
    """Pull sessions from Phoenix, run LLM analysis, store insights."""

    async def _entry() -> None:
        async with _track_run("analyze") as run:
            await _analyze_async(
                hours=hours,
                limit=limit,
                force=force,
                concurrency=concurrency,
                verbose=verbose,
                trace_ids=trace_ids,
                run=run,
            )

    asyncio.run(_entry())


async def _analyze_async(
    hours: int,
    limit: int,
    force: bool,
    concurrency: int,
    verbose: bool,
    trace_ids: list[str] | None,
    run: _RunHandle | None = None,
):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    settings = get_settings()

    if not settings.anthropic_api_key:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY not set. "
            "Set it in your environment or .env file."
        )
        raise typer.Exit(1)

    from cinsights.analysis.session import SessionAnalyzer
    from cinsights.db.engine import get_sessionmaker
    from cinsights.db.models import CodingSession, SessionStatus
    from cinsights.sources.phoenix import PhoenixSource

    source = PhoenixSource(
        base_url=settings.phoenix_endpoint, project=settings.phoenix_project
    )
    sessionmaker = get_sessionmaker()
    import json

    extra_headers = None
    if settings.anthropic_extra_headers:
        extra_headers = json.loads(settings.anthropic_extra_headers)

    analyzer = SessionAnalyzer(
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        base_url=settings.anthropic_base_url,
        extra_headers=extra_headers,
    )

    # Collect traces to analyze
    # Each work item: (trace_id, session_id, TraceData, spans)
    work_items: list[tuple[str, str, object, list]] = []

    # PhoenixSource is sync (HTTP via the phoenix client). Push every blocking
    # call into a thread so the event loop stays free for the LLM analyzer.
    if trace_ids:
        from cinsights.sources.base import TraceData

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Fetching {len(trace_ids)} ID(s) from Phoenix...", total=None
            )
            for tid in trace_ids:
                # Try as session ID first (fetches all spans across traces)
                spans = await asyncio.to_thread(source.get_spans_by_session, tid)
                if spans:
                    trace = TraceData(
                        trace_id=tid,
                        start_time=spans[0].start_time,
                        end_time=spans[-1].end_time,
                        spans=spans,
                    )
                    work_items.append((tid, tid, trace, spans))
                else:
                    # Try as trace ID
                    spans = await asyncio.to_thread(source.get_spans, tid)
                    if spans:
                        trace = TraceData(
                            trace_id=tid,
                            start_time=spans[0].start_time,
                            end_time=spans[-1].end_time,
                            spans=spans,
                        )
                        work_items.append((tid, tid, trace, spans))
                    else:
                        console.print(f"  [yellow]No spans for {tid[:16]}...[/yellow]")
            progress.update(
                task, description=f"Found {len(work_items)} session(s) with spans"
            )
    else:
        # Discover all sessions from Phoenix
        start_time = datetime.now(UTC) - timedelta(hours=hours)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Discovering sessions from Phoenix...", total=None)
            discovered = await asyncio.to_thread(
                source.discover_sessions, start_time=start_time
            )
            progress.update(task, description=f"Found {len(discovered)} sessions")

        if not discovered:
            console.print(f"[yellow]No sessions found in the last {hours} hours.[/yellow]")
            return

        # Filter to sessions needing analysis. We re-analyze ANALYZED sessions only
        # when both conditions hold:
        #   1) the session has grown by at least 20% in span count, AND
        #   2) the last new span is at least 60s old
        # The first condition ignores trivial growth (1-2 new spans during a long
        # session). The second condition lets sessions "settle" before we burn
        # tokens re-analyzing them — a session that's actively being appended to
        # right now will probably grow more in the next minute.
        REANALYZE_GROWTH_RATIO = 0.20
        REANALYZE_QUIET_SECONDS = 60.0
        now = datetime.now(UTC)

        skipped = 0
        async with sessionmaker() as db:
            for d in discovered[:limit]:
                existing = await db.get(CodingSession, d.session_id)
                if existing and existing.status == SessionStatus.ANALYZED and not force:
                    prior = max(existing.span_count, 1)
                    growth = (d.span_count - existing.span_count) / prior
                    last_seen = existing.last_span_time
                    if last_seen is not None and last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=UTC)
                    quiet_for = (
                        (now - last_seen).total_seconds()
                        if last_seen is not None
                        else float("inf")
                    )

                    if growth < REANALYZE_GROWTH_RATIO or quiet_for < REANALYZE_QUIET_SECONDS:
                        skipped += 1
                        continue

                    console.print(
                        f"  [cyan]↻[/cyan] {d.session_id[:16]}... grew "
                        f"{existing.span_count}→{d.span_count} "
                        f"(+{growth:.0%}, quiet {quiet_for:.0f}s)"
                    )

                spans = await asyncio.to_thread(source.get_spans_by_session, d.session_id)
                if spans:
                    from cinsights.sources.base import TraceData

                    trace = TraceData(
                        trace_id=d.session_id,
                        start_time=d.start_time,
                        end_time=d.end_time,
                        spans=spans,
                    )
                    work_items.append((d.session_id, d.session_id, trace, spans))

        if skipped:
            console.print(f"  [dim]{skipped} session(s) unchanged or still active, skipped[/dim]")

    if not work_items:
        console.print("[yellow]No traces to analyze (all already analyzed).[/yellow]")
        return

    console.print(
        f"\n[bold]Analyzing {len(work_items)} trace(s) "
        f"(concurrency={concurrency})...[/bold]\n"
    )

    # Run LLM analysis concurrently
    from cinsights.sources.base import TraceData

    analysis_items = [(trace, spans) for _, _, trace, spans in work_items]
    results = await analyzer.analyze_batch(analysis_items, max_concurrency=concurrency)

    # Store results in DB
    analyzed = 0
    failed = 0
    async with sessionmaker() as db:
        for (trace_id, session_id, trace, spans), result in zip(
            work_items, results, strict=True
        ):
            try:
                existing = await db.get(CodingSession, trace_id)
                n_insights = await _store_analysis(
                    db, trace_id, session_id, trace, spans, result, source, force, existing
                )
                await db.commit()
                analyzed += 1
                if run is not None:
                    run.sessions_analyzed += 1
                    run.total_prompt_tokens += result.usage_prompt_tokens
                    run.total_completion_tokens += result.usage_completion_tokens
                console.print(
                    f"  [green]✓[/green] {trace_id[:12]} — {n_insights} insights"
                )
            except Exception as e:
                await db.rollback()
                failed += 1
                console.print(f"  [red]✗[/red] {trace_id[:12]} — {e}")

    # Summary
    console.print()
    table = Table(title="Analysis Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Analyzed", str(analyzed))
    table.add_row("Skipped", str(len(analysis_items) - analyzed - failed))
    table.add_row("Failed", str(failed))
    console.print(table)


@app.command()
def digest(
    days: int = typer.Option(7, help="Analyze sessions from the last N days."),
    user_id: str | None = typer.Option(None, help="Filter by user ID."),
    project: str | None = typer.Option(None, help="Filter by project name."),
    stats_only: bool = typer.Option(False, "--stats-only", help="Only compute stats (no LLM)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
):
    """Generate a cross-session insights report."""

    async def _entry() -> None:
        async with _track_run("digest") as run:
            await _digest_async(
                days=days,
                user_id=user_id,
                project=project,
                stats_only=stats_only,
                verbose=verbose,
                run=run,
            )

    asyncio.run(_entry())


async def _digest_async(
    days: int,
    user_id: str | None,
    project: str | None,
    stats_only: bool,
    verbose: bool,
    run: _RunHandle | None = None,
):
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    settings = get_settings()

    if not stats_only and not settings.anthropic_api_key:
        console.print(
            "[red]Error:[/red] ANTHROPIC_API_KEY not set. "
            "Use --stats-only for free stats, or set the key."
        )
        raise typer.Exit(1)

    import json

    from cinsights.db.engine import get_sessionmaker
    from cinsights.db.models import CodingSession, SessionStatus

    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    sessionmaker = get_sessionmaker()

    # Build scope list. Explicit --project always wins; otherwise we run a global
    # digest *and* one per detected project, in parallel.
    if project:
        scopes: list[str | None] = [project]
    else:
        async with sessionmaker() as db:
            project_rows_result = await db.exec(
                select_fn(CodingSession.project_name)
                .where(CodingSession.project_name.is_not(None))
                .where(CodingSession.start_time >= start)
                .where(CodingSession.start_time <= end)
                .where(CodingSession.status == SessionStatus.ANALYZED)
                .group_by(CodingSession.project_name)
            )
            project_rows = project_rows_result.all()
        # Global first, then projects in stable order
        scopes = [None, *sorted(p for p in project_rows if p)]

    # Build the analyzer once and share it across scopes (just an HTTP client).
    analyzer = None
    if not stats_only:
        extra_headers = None
        if settings.anthropic_extra_headers:
            extra_headers = json.loads(settings.anthropic_extra_headers)

        from cinsights.analysis.digest import DigestAnalyzer

        analyzer = DigestAnalyzer(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model,
            base_url=settings.anthropic_base_url,
            extra_headers=extra_headers,
        )

    console.print(
        f"[bold]Running {len(scopes)} digest(s) for last {days} days "
        f"(concurrent)...[/bold]\n"
    )

    tasks = [
        _run_one_digest(
            sessionmaker=sessionmaker,
            analyzer=analyzer,
            scope_project=scope,
            user_id=user_id,
            start=start,
            end=end,
            stats_only=stats_only,
        )
        for scope in scopes
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Summarize. Each non-exception result is (status, prompt_tokens, completion_tokens).
    def _status_of(r):
        return r[0] if isinstance(r, tuple) else r

    succeeded = sum(1 for r in results if _status_of(r) is True)
    skipped = sum(
        1 for r in results if _status_of(r) in ("empty", "stats_only", "unchanged")
    )
    failed = [
        (scope, r)
        for scope, r in zip(scopes, results, strict=True)
        if isinstance(r, Exception)
    ]

    if run is not None:
        for r in results:
            if isinstance(r, tuple) and r[0] is True:
                run.digests_generated += 1
                run.total_prompt_tokens += r[1]
                run.total_completion_tokens += r[2]

    console.print()
    table = Table(title="Digest Summary")
    table.add_column("Scope", style="bold")
    table.add_column("Result")
    for scope, result in zip(scopes, results, strict=True):
        label = scope or "global"
        status = _status_of(result)
        if status is True:
            table.add_row(label, "[green]✓ done[/green]")
        elif status == "empty":
            table.add_row(label, "[yellow]no sessions[/yellow]")
        elif status == "stats_only":
            table.add_row(label, "[cyan]· stats only[/cyan]")
        elif status == "unchanged":
            table.add_row(label, "[dim]· unchanged, reused[/dim]")
        elif isinstance(result, Exception):
            table.add_row(label, f"[red]✗ {result}[/red]")
    console.print(table)

    if not stats_only and succeeded:
        console.print(
            f"\n  View at: [bold]http://localhost:{settings.port}/report[/bold]"
        )

    if failed and not succeeded and not skipped:
        raise typer.Exit(1)


async def _run_one_digest(
    *,
    sessionmaker: async_sessionmaker[AsyncSession],
    analyzer: DigestAnalyzer | None,
    scope_project: str | None,
    user_id: str | None,
    start: datetime,
    end: datetime,
    stats_only: bool,
) -> tuple[bool | str, int, int]:
    """Compute + (optionally) LLM-analyze + persist a single digest scope.

    Returns ``(status, prompt_tokens, completion_tokens)`` where ``status`` is:

    - ``True`` — a new digest was generated and persisted
    - ``"empty"`` — no sessions in scope
    - ``"stats_only"`` — LLM step was skipped (--stats-only mode)
    - ``"unchanged"`` — stats hash matched a recently completed digest, so we
      reused it instead of paying for fresh LLM calls

    Tokens are zero in every non-True path. Raises on failure.

    Each call opens its own AsyncSession from the shared sessionmaker, so
    concurrent scopes (via ``asyncio.gather`` in ``_digest_async``) get
    independent sessions and don't violate AsyncSession's "no concurrent use
    on a single session" rule.
    """
    import json as json_mod

    from cinsights.db.models import Digest, DigestSection, DigestStatus
    from cinsights.stats import compute_all

    label = scope_project or "global"

    async with sessionmaker() as db:
        stats = await compute_all(db, start, end, project_name=scope_project)

        if stats.session_count == 0:
            console.print(f"  [yellow]·[/yellow] {label} — no sessions, skipped")
            return ("empty", 0, 0)

        if stats_only:
            console.print(
                f"  [cyan]·[/cyan] {label} — {stats.session_count} sessions, "
                f"{stats.total_tokens:,} tokens (stats only)"
            )
            return ("stats_only", 0, 0)

        # Find the most recent COMPLETE digest for this scope. If its stats hash
        # matches what we'd compute now, reuse it — no LLM cost. This makes
        # repeated `cinsights refresh` calls idempotent and cuts test/dev cost.
        scope_q = select_fn(Digest)
        if user_id:
            scope_q = scope_q.where(Digest.user_id == user_id)
        else:
            scope_q = scope_q.where(Digest.user_id.is_(None))
        if scope_project:
            scope_q = scope_q.where(Digest.project_name == scope_project)
        else:
            scope_q = scope_q.where(Digest.project_name.is_(None))

        completed_q = (
            scope_q.where(Digest.status == DigestStatus.COMPLETE)
            .order_by(col(Digest.completed_at).desc())
            .limit(1)
        )
        latest_complete_result = await db.exec(completed_q)
        latest_complete = latest_complete_result.first()

        # Hash on stats CONTENT — exclude period_start/period_end since they're
        # set to now() on every run and would prevent any skip from firing.
        new_stats_json = stats.model_dump_json()
        new_hash = _content_hash(new_stats_json)
        if latest_complete and latest_complete.stats_json:
            old_hash = _content_hash(latest_complete.stats_json)
            if old_hash == new_hash:
                console.print(
                    f"  [dim]·[/dim] {label} — stats unchanged since "
                    f"{latest_complete.completed_at:%Y-%m-%d %H:%M}, reused"
                )
                return ("unchanged", 0, 0)

        # Stats changed (or no prior digest). Delete every existing digest in this
        # scope (running, failed, or stale-complete) before creating a new one.
        existing_result = await db.exec(scope_q)
        existing_digests = existing_result.all()
        for old in existing_digests:
            sec_result = await db.exec(
                select_fn(DigestSection).where(DigestSection.digest_id == old.id)
            )
            for sec in sec_result.all():
                await db.delete(sec)
            await db.delete(old)
        if existing_digests:
            await db.flush()

        settings = get_settings()
        digest_record = Digest(
            tenant_id=settings.tenant_id,
            user_id=user_id,
            project_name=scope_project,
            period_start=start,
            period_end=end,
            session_count=stats.session_count,
            stats_json=stats.model_dump_json(),
            status=DigestStatus.ANALYZING,
        )
        db.add(digest_record)
        await db.commit()
        await db.refresh(digest_record)

        try:
            assert analyzer is not None  # not stats_only path
            result = await analyzer.analyze(stats)
            await _store_digest_sections(db, digest_record, result, json_mod)
            console.print(
                f"  [green]✓[/green] {label} — {stats.session_count} sessions, "
                f"{result.total_prompt_tokens + result.total_completion_tokens:,} LLM tokens"
            )
            return (True, result.total_prompt_tokens, result.total_completion_tokens)
        except Exception as e:
            digest_record.status = DigestStatus.FAILED
            digest_record.error_message = str(e)
            await db.commit()
            console.print(f"  [red]✗[/red] {label} — {e}")
            raise


@app.command()
def refresh(
    hours: int = typer.Option(24, help="Analyze sessions from the last N hours."),
    days: int = typer.Option(7, help="Digest window in days."),
    limit: int = typer.Option(50, help="Max sessions to analyze."),
    force: bool = typer.Option(False, help="Re-analyze already-analyzed sessions."),
    concurrency: int = typer.Option(5, help="Max concurrent LLM analysis requests."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
):
    """Refresh everything: pull + analyze new sessions, then regenerate all digests.

    This is the standard entrypoint for cron / scheduled jobs. It runs `analyze`
    followed by `digest` (global + per-project, concurrent) so dashboards always
    reflect the latest Phoenix data.
    """

    async def _entry() -> None:
        async with _track_run("refresh") as run:
            await _analyze_async(
                hours=hours,
                limit=limit,
                force=force,
                concurrency=concurrency,
                verbose=verbose,
                trace_ids=None,
                run=run,
            )
            console.print()
            await _digest_async(
                days=days,
                user_id=None,
                project=None,
                stats_only=False,
                verbose=verbose,
                run=run,
            )

    asyncio.run(_entry())


async def _store_digest_sections(
    db: AsyncSession,
    digest_record,
    result,
    json_mod,
) -> None:
    """Store digest analysis results as DigestSection rows."""
    from cinsights.db.models import DigestSection, DigestSectionType, DigestStatus

    def _dump(items: list) -> str:
        return json_mod.dumps([i.model_dump() for i in items])

    sections = [
        (DigestSectionType.AT_A_GLANCE, "At a Glance", "",
         json_mod.dumps(result.narrative.at_a_glance.model_dump())),
        (DigestSectionType.WORK_AREAS, "What You Work On", "",
         _dump(result.narrative.work_areas)),
        (DigestSectionType.DEVELOPER_PERSONA, "How You Use Claude Code",
         result.narrative.developer_persona, None),
        (DigestSectionType.IMPRESSIVE_WINS, "Impressive Things You Did", "",
         _dump(result.forward.impressive_wins)),
        (DigestSectionType.FRICTION_ANALYSIS, "Where Things Go Wrong", "",
         _dump(result.actions.friction_analysis)),
        (DigestSectionType.CLAUDE_MD_SUGGESTIONS, "Suggested CLAUDE.md Additions", "",
         _dump(result.actions.claude_md_suggestions)),
        (DigestSectionType.FEATURE_RECOMMENDATIONS, "CC Features to Try", "",
         _dump(result.actions.feature_recommendations)),
        (DigestSectionType.WORKFLOW_PATTERNS, "New Ways to Use Claude Code", "",
         _dump(result.forward.workflow_patterns)),
        (DigestSectionType.AMBITIOUS_WORKFLOWS, "On the Horizon", "",
         _dump(result.forward.ambitious_workflows)),
    ]

    settings = get_settings()
    for i, (stype, title, content, meta) in enumerate(sections):
        db.add(DigestSection(
            digest_id=digest_record.id,
            section_type=stype,
            title=title,
            content=content,
            order=i,
            metadata_json=meta,
            prompt_version=settings.prompt_version_digest,
        ))

    digest_record.status = DigestStatus.COMPLETE
    digest_record.analysis_prompt_tokens = result.total_prompt_tokens
    digest_record.analysis_completion_tokens = result.total_completion_tokens
    digest_record.completed_at = datetime.now(UTC)
    await db.commit()


@app.command()
def serve(
    host: str = typer.Option(None, help="Override host."),
    port: int = typer.Option(None, help="Override port."),
):
    """Start the cinsights web server."""
    import uvicorn

    settings = get_settings()
    uvicorn.run(
        "cinsights.main:app",
        host=host or settings.host,
        port=port or settings.port,
    )


if __name__ == "__main__":
    app()
