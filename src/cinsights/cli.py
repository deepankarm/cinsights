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

from cinsights.pipeline import _analyze_async, _digest_async
from cinsights.runtime import _track_run
from cinsights.settings import get_settings

app = typer.Typer(name="cinsights", help="LLM-powered insights from coding agent sessions.")


def _apply_source_overrides(source: str | None, repo: str | None) -> None:
    """Override settings.source and entireio_repo_path from CLI flags."""
    if source or repo:
        settings = get_settings()
        if source:
            settings.source = source
        if repo:
            settings.entireio_repo_path = repo


@app.command()
def analyze(
    hours: int = typer.Option(24, help="Analyze sessions from the last N hours."),
    limit: int = typer.Option(50, help="Max sessions to analyze."),
    force: bool = typer.Option(False, help="Re-analyze already-analyzed sessions."),
    concurrency: int = typer.Option(5, help="Max concurrent LLM analysis requests."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
    source: str | None = typer.Option(None, help="Override source (phoenix, entireio, local)."),
    repo: str | None = typer.Option(None, help="Repo path for entireio source."),
    index_only: bool = typer.Option(False, "--index-only", help="Index only, no LLM."),
    trace_ids: list[str] | None = typer.Argument(
        None, help="Specific trace/session IDs to analyze."
    ),
) -> None:
    """Pull sessions from a source, run LLM analysis, store insights."""
    _apply_source_overrides(source, repo)

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
                index_only=index_only,
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
    source: str | None = typer.Option(None, help="Override source (phoenix, entireio, local)."),
    repo: str | None = typer.Option(None, help="Repo path for entireio source."),
) -> None:
    """Refresh everything: pull + analyze new sessions, then regenerate all digests."""
    _apply_source_overrides(source, repo)

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


@app.command()
def setup(
    provider: str | None = typer.Option(None, help="LLM provider (e.g. anthropic, openai)."),
    model: str | None = typer.Option(None, help="Model name."),
    base_url: str | None = typer.Option(None, help="Custom base URL (for gateways/proxies)."),
    extra_headers: str | None = typer.Option(None, help="Extra HTTP headers as JSON string."),
    validate: bool = typer.Option(
        False, "--validate", help="Test current config without prompting."
    ),
) -> None:
    """Configure LLM provider settings (saved to ~/.cinsights/config.json).

    Interactive mode (no args): prompts for each value, like `aws configure`.
    One-shot mode: pass --provider, --model, etc. directly.
    Validate mode: --validate tests the current config.
    """
    import json

    from cinsights.runtime import console
    from cinsights.settings import AppConfig, LLMConfig, Paths

    app_config = AppConfig.load()
    llm = app_config.llm

    if validate:
        console.print(
            f"  Provider: [bold]{llm.provider}[/bold]\n"
            f"  Model:    [bold]{llm.model}[/bold]\n"
            f"  Base URL: {llm.base_url or '(default)'}\n"
            f"  Headers:  {llm.extra_headers or '(none)'}"
        )
        _test_connection(llm)
        return

    # Interactive mode: prompt for values with current defaults
    if provider is None:
        provider = typer.prompt("LLM Provider", default=llm.provider)
    if model is None:
        model = typer.prompt("Model name", default=llm.model)
    if base_url is None:
        base_url = typer.prompt(
            "Base URL (blank for default)",
            default=llm.base_url or "",
            show_default=False,
        )
    if extra_headers is None:
        current = json.dumps(llm.extra_headers) if llm.extra_headers else ""
        extra_headers = typer.prompt(
            "Extra HTTP headers as JSON (blank for none)",
            default=current,
            show_default=bool(current),
        )

    # Parse extra headers
    headers_dict: dict[str, str] = {}
    if extra_headers:
        try:
            headers_dict = json.loads(extra_headers)
        except json.JSONDecodeError as e:
            console.print("[red]Invalid JSON for extra headers.[/red]")
            raise typer.Exit(1) from e

    app_config.llm = LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url or None,
        extra_headers=headers_dict,
    )
    app_config.save()
    console.print(f"\n  Configuration written to [bold]{Paths.config_file}[/bold]")

    # Offer to test
    if typer.confirm("Test connection?", default=True):
        _test_connection(app_config.llm)


def _test_connection(llm) -> None:
    """Send a minimal request to verify the LLM config works."""
    import asyncio

    from cinsights.runtime import console

    async def _probe():
        from pydantic_ai import Agent
        from pydantic_ai.settings import ModelSettings

        agent = Agent(
            llm.build_model(),
            output_type=str,
            model_settings=ModelSettings(max_tokens=20),
            instrument=False,
        )
        result = await agent.run("Reply with exactly: OK")
        usage = result.usage()
        return usage.output_tokens or 0

    try:
        tokens = asyncio.run(_probe())
        console.print(f"  Testing... [green]Got {tokens} tokens back from {llm.model}[/green]")
    except Exception as e:
        console.print(f"  Testing... [red]Failed: {e}[/red]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
