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
    # CC traces use CHAIN spans with tool.name attribute for tool calls
    tool_spans = [s for s in spans if s.tool_name and s.parent_id is not None]

    # Extract user.id and project.name from span attributes
    # Note: project.name is an OTEL resource attribute — Phoenix doesn't expose it
    # via API yet (see Arize-ai/phoenix#11645). Will be null until that ships.
    user_id = None
    project_name = None
    for s in spans:
        if not user_id:
            user_id = s.user_id
        if not project_name:
            project_name = s.project_name
        if user_id and project_name:
            break

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
