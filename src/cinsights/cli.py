from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta

import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlmodel import Session

from cinsights.config import get_settings

app = typer.Typer(name="cinsights", help="LLM-powered insights from coding agent sessions.")
console = Console()


def _store_analysis(
    db: Session,
    trace_id: str,
    session_id: str,
    trace,
    spans: list,
    result,
    source,
    force: bool,
    existing,
):
    """Store trace data and analysis results in the database."""
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
        if s.parent_id is not None and (s.tool_name or "Permission" in s.name or "Notification" in s.name)
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

    if not existing:
        coding_session = CodingSession(
            id=trace_id,
            session_id=session_id,
            user_id=user_id,
            project_name=project_name,
            start_time=trace.start_time,
            end_time=trace.end_time,
            model=root.model_name if root else None,
            total_tokens=root.total_tokens if root else 0,
            prompt_tokens=root.prompt_tokens if root else 0,
            completion_tokens=root.completion_tokens if root else 0,
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
        coding_session.span_count = len(spans)
        coding_session.last_span_time = last_span_time

    # Clear old data if re-analyzing
    if force or existing:
        for tc in list(coding_session.tool_calls):
            db.delete(tc)
        for ins in list(coding_session.insights):
            db.delete(ins)
        db.flush()

    for span in tool_spans:
        tc = ToolCall(
            session_id=trace_id,
            span_id=span.span_id,
            tool_name=span.tool_name or span.name,
            input_value=span.input_value[:2000] if span.input_value else None,
            output_value=span.output_value[:2000] if span.output_value else None,
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
            session_id=trace_id,
            category=cat,
            title=item.title,
            content=item.content,
            severity=sev,
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
    asyncio.run(
        _analyze_async(
            hours=hours,
            limit=limit,
            force=force,
            concurrency=concurrency,
            verbose=verbose,
            trace_ids=trace_ids,
        )
    )


async def _analyze_async(
    hours: int,
    limit: int,
    force: bool,
    concurrency: int,
    verbose: bool,
    trace_ids: list[str] | None,
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
    from cinsights.db.engine import get_engine, init_db
    from cinsights.db.models import CodingSession, SessionStatus
    from cinsights.sources.phoenix import PhoenixSource

    init_db()

    source = PhoenixSource(
        base_url=settings.phoenix_endpoint, project=settings.phoenix_project
    )
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

    if trace_ids:
        # IDs can be session IDs or trace IDs — try both
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
                spans = source.get_spans_by_session(tid)
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
                    spans = source.get_spans(tid)
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
            discovered = source.discover_sessions(start_time=start_time)
            progress.update(task, description=f"Found {len(discovered)} sessions")

        if not discovered:
            console.print(f"[yellow]No sessions found in the last {hours} hours.[/yellow]")
            raise typer.Exit(0)

        # Filter to sessions needing analysis (new or changed)
        skipped = 0
        engine = get_engine()
        with Session(engine) as db:
            for d in discovered[:limit]:
                existing = db.get(CodingSession, d.session_id)
                if existing and existing.status == SessionStatus.ANALYZED and not force:
                    # Check if session has changed (more spans or newer span)
                    changed = existing.span_count != d.span_count
                    if not changed:
                        skipped += 1
                        continue
                    console.print(
                        f"  [cyan]↻[/cyan] {d.session_id[:16]}... changed "
                        f"({existing.span_count}→{d.span_count} spans)"
                    )

                spans = source.get_spans_by_session(d.session_id)
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
            console.print(f"  [dim]{skipped} session(s) unchanged, skipped[/dim]")

    if not work_items:
        console.print("[yellow]No traces to analyze (all already analyzed).[/yellow]")
        raise typer.Exit(0)

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
    engine = get_engine()
    with Session(engine) as db:
        for (trace_id, session_id, trace, spans), result in zip(
            work_items, results, strict=True
        ):
            try:
                existing = db.get(CodingSession, trace_id)
                n_insights = _store_analysis(
                    db, trace_id, session_id, trace, spans, result, source, force, existing
                )
                db.commit()
                analyzed += 1
                console.print(
                    f"  [green]✓[/green] {trace_id[:12]} — {n_insights} insights"
                )
            except Exception as e:
                db.rollback()
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
    force: bool = typer.Option(False, help="Regenerate even if a recent digest exists."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
):
    """Generate a cross-session insights report."""
    asyncio.run(
        _digest_async(
            days=days,
            user_id=user_id,
            project=project,
            stats_only=stats_only,
            force=force,
            verbose=verbose,
        )
    )


async def _digest_async(
    days: int,
    user_id: str | None,
    project: str | None,
    stats_only: bool,
    force: bool,
    verbose: bool,
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

    from cinsights.db.engine import get_engine, init_db
    from cinsights.db.models import (
        Digest,
        DigestStatus,
    )
    from cinsights.stats import compute_all

    init_db()

    end = datetime.now(UTC)
    start = end - timedelta(days=days)

    engine = get_engine()
    with Session(engine) as db:
        # Compute stats
        console.print(f"[bold]Computing stats for last {days} days...[/bold]")
        stats = compute_all(db, start, end, project_name=project)

        if stats.session_count == 0:
            console.print("[yellow]No analyzed sessions in this period.[/yellow]")
            console.print("Run [bold]cinsights analyze[/bold] first.")
            raise typer.Exit(0)

        # Print stats summary
        console.print()
        period = f"{stats.period_start.strftime('%m/%d')} - {stats.period_end.strftime('%m/%d')}"
        table = Table(title=f"Stats ({period})")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")
        table.add_row("Sessions", str(stats.session_count))
        table.add_row("Tool calls", str(stats.total_tool_calls))
        table.add_row("Tokens", f"{stats.total_tokens:,}")
        table.add_row("Duration", f"{stats.total_duration_minutes:.0f}min")
        table.add_row("Active days", str(stats.active_days))
        table.add_row("Top tool", next(iter(stats.tool_distribution), "-"))
        table.add_row("Languages", ", ".join(list(stats.language_distribution.keys())[:3]))
        table.add_row("Permissions", str(stats.permission_stats.count))
        console.print(table)

        if stats_only:
            console.print("\n[dim]--stats-only mode, skipping LLM analysis.[/dim]")
            raise typer.Exit(0)

        # Create digest record
        import json

        digest_record = Digest(
            user_id=user_id,
            project_name=project,
            period_start=start,
            period_end=end,
            session_count=stats.session_count,
            stats_json=stats.model_dump_json(),
            status=DigestStatus.ANALYZING,
        )
        db.add(digest_record)
        db.commit()
        db.refresh(digest_record)

        # Run LLM analysis
        console.print("\n[bold]Running digest analysis (3 concurrent LLM calls)...[/bold]")

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

        try:
            result = await analyzer.analyze(stats)
            _store_digest_sections(db, digest_record, result, json)
            console.print("\n[green]✓[/green] Digest complete — 10 sections")
            console.print(
                f"  LLM usage: {result.total_prompt_tokens:,} prompt + "
                f"{result.total_completion_tokens:,} completion tokens"
            )
            console.print(
                f"\n  View at: [bold]http://localhost:{settings.port}/report[/bold]"
            )
        except Exception as e:
            digest_record.status = DigestStatus.FAILED
            digest_record.error_message = str(e)
            db.commit()
            console.print(f"\n[red]✗[/red] Digest failed: {e}")
            raise typer.Exit(1) from None


def _store_digest_sections(db, digest_record, result, json_mod):
    """Store digest analysis results as DigestSection rows."""
    from cinsights.db.models import DigestSection, DigestSectionType, DigestStatus

    def _dump(items):
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

    for i, (stype, title, content, meta) in enumerate(sections):
        db.add(DigestSection(
            digest_id=digest_record.id,
            section_type=stype,
            title=title,
            content=content,
            order=i,
            metadata_json=meta,
        ))

    digest_record.status = DigestStatus.COMPLETE
    digest_record.analysis_prompt_tokens = result.total_prompt_tokens
    digest_record.analysis_completion_tokens = result.total_completion_tokens
    digest_record.completed_at = datetime.now(UTC)
    db.commit()


@app.command()
def serve(
    host: str = typer.Option(None, help="Override host."),
    port: int = typer.Option(None, help="Override port."),
):
    """Start the cinsights web server."""
    import uvicorn

    from cinsights.db.engine import init_db

    init_db()

    settings = get_settings()
    uvicorn.run(
        "cinsights.main:app",
        host=host or settings.host,
        port=port or settings.port,
    )


@app.command()
def init_db_cmd():
    """Initialize the database (create tables)."""
    from cinsights.db.engine import init_db

    init_db()
    console.print("[green]✓[/green] Database initialized.")


# Register as "init-db" command name
app.registered_commands[-1].name = "init-db"


if __name__ == "__main__":
    app()
