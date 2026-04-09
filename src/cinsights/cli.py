"""Typer command surface for cinsights.

This module is intentionally thin: it only contains the CLI command
definitions and the small ``_entry`` async wrappers that bridge sync Typer
to the async pipeline. All real work lives in:

- ``cinsights.runtime`` — observability primitives (``_track_run``,
  ``_RunHandle``, ``console``, ``_content_hash``)
- ``cinsights.pipeline`` — the analyze + digest orchestration coroutines
"""

from __future__ import annotations

import asyncio

import typer

from cinsights.config import get_settings
from cinsights.pipeline import _analyze_async, _digest_async
from cinsights.runtime import _track_run

app = typer.Typer(name="cinsights", help="LLM-powered insights from coding agent sessions.")


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
) -> None:
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


@app.command()
def digest(
    days: int = typer.Option(7, help="Analyze sessions from the last N days."),
    user_id: str | None = typer.Option(None, help="Filter by user ID."),
    project: str | None = typer.Option(None, help="Filter by project name."),
    stats_only: bool = typer.Option(False, "--stats-only", help="Only compute stats (no LLM)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
) -> None:
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


@app.command()
def refresh(
    hours: int = typer.Option(24, help="Analyze sessions from the last N hours."),
    days: int = typer.Option(7, help="Digest window in days."),
    limit: int = typer.Option(50, help="Max sessions to analyze."),
    force: bool = typer.Option(False, help="Re-analyze already-analyzed sessions."),
    concurrency: int = typer.Option(5, help="Max concurrent LLM analysis requests."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
) -> None:
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
            from cinsights.runtime import console

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


@app.command()
def serve(
    host: str | None = typer.Option(None, help="Override host."),
    port: int | None = typer.Option(None, help="Override port."),
) -> None:
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
