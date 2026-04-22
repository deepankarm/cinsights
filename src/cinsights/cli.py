"""Typer command surface for cinsights.

This module is intentionally thin: it only contains the CLI command
definitions and the small ``_entry`` async wrappers that bridge sync Typer
to the async pipeline. All real work lives in:

- ``cinsights.runtime`` — observability primitives (``_track_run``,
  ``_RunHandle``, ``console``, ``_content_hash``)
- ``cinsights.pipeline`` — the index, score, analyze, and digest coroutines
"""

from __future__ import annotations

import asyncio
import os

# Suppress noisy third-party progress bars before any imports
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("TRANSFORMERS_VERBOSITY", "error")

from typing import TYPE_CHECKING

import typer

from cinsights.pipeline import _analyze_async, _digest_async, _index_async, _score_async
from cinsights.runtime import _track_run
from cinsights.settings import get_settings

if TYPE_CHECKING:
    from cinsights.settings import LLMConfig

import logging

logging.getLogger("httpx").setLevel(logging.WARNING)

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
def index(
    hours: int = typer.Option(24, help="Index sessions from the last N hours."),
    force: bool = typer.Option(False, help="Re-index already-indexed sessions."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
    source: str | None = typer.Option(None, help="Override source (phoenix, entireio, local)."),
    repo: str | None = typer.Option(None, help="Repo path for entireio source."),
    trace_ids: list[str] | None = typer.Argument(None, help="Specific trace/session IDs to index."),
) -> None:
    """Discover sessions, extract metadata + quality metrics, score against baselines. Zero LLM cost."""
    _apply_source_overrides(source, repo)

    async def _entry() -> None:
        async with _track_run("analyze") as run:
            await _index_async(
                hours=hours,
                force=force,
                verbose=verbose,
                trace_ids=trace_ids,
                run=run,
            )

    asyncio.run(_entry())


@app.command()
def score(
    user_id: str | None = typer.Option(None, "--user", help="Filter by user ID."),
    project: str | None = typer.Option(None, "--project", help="Filter by project name."),
    min_score: float = typer.Option(0.0, "--min-score", help="Show sessions above this score."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
) -> None:
    """Re-score existing sessions, show distribution and coverage gaps. Zero LLM cost."""

    async def _entry() -> None:
        await _score_async(
            user_id=user_id,
            project=project,
            min_score=min_score,
            verbose=verbose,
        )

    asyncio.run(_entry())


@app.command()
def analyze(
    limit: int = typer.Option(50, help="Max sessions to analyze. Use 0 for no limit."),
    force: bool = typer.Option(False, help="Re-analyze already-analyzed sessions."),
    concurrency: int = typer.Option(5, help="Max concurrent LLM analysis requests."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
    source: str | None = typer.Option(None, help="Override source (phoenix, entireio, local)."),
    repo: str | None = typer.Option(None, help="Repo path for entireio source."),
    min_score: float = typer.Option(
        0.0, "--min-score", help="Only analyze sessions with score >= this."
    ),
    yes: bool = typer.Option(False, "--yes", "-y", help="Skip confirmation prompt."),
    trace_ids: list[str] | None = typer.Argument(
        None, help="Specific trace/session IDs to analyze."
    ),
) -> None:
    """LLM-analyze INDEXED sessions above the score threshold. Costs tokens."""
    _apply_source_overrides(source, repo)

    async def _entry() -> None:
        async with _track_run("analyze") as run:
            run.extra["source"] = source
            run.extra["min_score"] = min_score
            run.extra["limit"] = limit
            await _analyze_async(
                hours=24,
                limit=limit,
                force=force,
                concurrency=concurrency,
                verbose=verbose,
                trace_ids=trace_ids,
                run=run,
                min_score=min_score,
                yes=yes,
            )

    asyncio.run(_entry())


# British English alias
app.registered_commands.append(
    typer.models.CommandInfo(name="analyse", callback=analyze, hidden=True)
)


@app.command()
def digest(
    scope_type: str = typer.Argument(help="Scope: 'project' or 'user'."),
    scope_value: str = typer.Argument(help="Project name or user ID."),
    days: int = typer.Option(7, help="Analyze sessions from the last N days."),
    stats_only: bool = typer.Option(False, "--stats-only", help="Only compute stats (no LLM)."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
) -> None:
    """Generate insights for a project or developer.

    Usage: cinsights digest project <name> | cinsights digest user <id>
    """
    if scope_type not in ("project", "user"):
        raise typer.BadParameter(f"scope_type must be 'project' or 'user', got '{scope_type}'")

    async def _entry() -> None:
        async with _track_run("digest") as run:
            run.extra["scope_type"] = scope_type
            run.extra[scope_type] = scope_value
            run.extra["days"] = days
            await _digest_async(
                scope_type=scope_type,
                scope_value=scope_value,
                days=days,
                stats_only=stats_only,
                verbose=verbose,
                run=run,
            )

    asyncio.run(_entry())


@app.command()
def refresh(
    hours: int = typer.Option(24, help="Index sessions from the last N hours."),
    days: int = typer.Option(7, help="Digest window in days."),
    limit: int = typer.Option(50, help="Max sessions to process."),
    force: bool = typer.Option(False, help="Re-process already-processed sessions."),
    concurrency: int = typer.Option(5, help="Max concurrent LLM analysis requests."),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging."),
    source: str | None = typer.Option(None, help="Override source (phoenix, entireio, local)."),
    repo: str | None = typer.Option(None, help="Repo path for entireio source."),
    min_score: float = typer.Option(
        0.4, "--min-score", help="Only analyze sessions with score >= this."
    ),
) -> None:
    """Refresh: index → analyze (scored). Run digest separately per project/user."""
    _apply_source_overrides(source, repo)

    async def _entry() -> None:
        async with _track_run("refresh") as run:
            run.extra["source"] = source
            run.extra["min_score"] = min_score
            await _index_async(
                hours=hours,
                force=force,
                verbose=verbose,
                run=run,
            )
            from cinsights.runtime import console

            console.print()
            await _analyze_async(
                hours=hours,
                limit=limit,
                force=force,
                concurrency=concurrency,
                verbose=verbose,
                trace_ids=None,
                run=run,
                min_score=min_score,
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


def _prompt_llm_config(
    current: LLMConfig,
    provider: str | None,
    model: str | None,
    base_url: str | None,
    extra_headers: str | None,
    interactive: bool,
    default_model: str | None = None,
) -> LLMConfig:
    """Prompt for LLM config values, reusing current as defaults."""
    import json

    from cinsights.settings import LLMConfig

    if provider is None:
        provider = typer.prompt("LLM Provider", default=current.provider)
    if model is None:
        model = typer.prompt("Model name", default=default_model or current.model)
    if interactive:
        if base_url is None:
            base_url = typer.prompt(
                "Base URL (blank for default)",
                default=current.base_url or "",
                show_default=False,
            )
        if extra_headers is None:
            current_headers = json.dumps(current.extra_headers) if current.extra_headers else ""
            extra_headers = typer.prompt(
                "Extra HTTP headers as JSON (blank for none)",
                default=current_headers,
                show_default=bool(current_headers),
            )

    import contextlib

    headers_dict: dict[str, str] = {}
    if extra_headers:
        with contextlib.suppress(json.JSONDecodeError):
            headers_dict = json.loads(extra_headers)

    return LLMConfig(
        provider=provider,
        model=model,
        base_url=base_url or None,
        extra_headers=headers_dict,
    )


@app.command()
def setup(
    provider: str | None = typer.Option(None, help="LLM provider (e.g. anthropic, openai)."),
    model: str | None = typer.Option(None, help="Model name."),
    base_url: str | None = typer.Option(None, help="Custom base URL (for gateways/proxies)."),
    extra_headers: str | None = typer.Option(None, help="Extra HTTP headers as JSON string."),
    digest: bool = typer.Option(
        False, "--digest", help="Configure the digest model (separate from analyze)."
    ),
    validate: bool = typer.Option(
        False, "--validate", help="Test current config without prompting."
    ),
) -> None:
    """Configure LLM provider settings (saved to ~/.cinsights/config.json).

    Interactive mode (no args): prompts for each value, like `aws configure`.
    One-shot mode: pass --provider, --model, etc. directly.
    Digest mode: --digest configures a separate model for digest generation.
    Validate mode: --validate tests the current config.
    """

    from cinsights.runtime import console
    from cinsights.settings import AppConfig, Paths

    app_config = AppConfig.load()
    llm = app_config.digest_llm or app_config.llm if digest else app_config.llm

    if validate:
        analyze_cfg = app_config.llm
        console.print("  [bold]Analyze model:[/bold]")
        console.print(
            f"    Provider: [bold]{analyze_cfg.provider}[/bold]\n"
            f"    Model:    [bold]{analyze_cfg.model}[/bold]\n"
            f"    Base URL: {analyze_cfg.base_url or '(default)'}"
        )
        digest_cfg = app_config.digest_llm
        if digest_cfg:
            console.print("\n  [bold]Digest model:[/bold]")
            console.print(
                f"    Provider: [bold]{digest_cfg.provider}[/bold]\n"
                f"    Model:    [bold]{digest_cfg.model}[/bold]\n"
                f"    Base URL: {digest_cfg.base_url or '(default)'}"
            )
        else:
            console.print("\n  [bold]Digest model:[/bold] (same as analyze)")
        _test_connection(analyze_cfg)
        return

    # One-shot mode (provider/model given) vs interactive mode (prompt for all)
    interactive = provider is None and model is None

    if interactive and not digest:
        console.print(
            "\n  [bold]Analyze model[/bold] — used for per-session analysis (high volume, cost-sensitive).\n"
            "  A fast, cheap model works best (e.g. gemini-2.5-flash-lite).\n"
        )
    elif interactive and digest:
        console.print(
            "\n  [bold]Digest model[/bold] — used for cross-session reports (low volume, quality matters).\n"
            "  A smarter model produces better insights (e.g. gemini-2.5-flash).\n"
        )

    new_config = _prompt_llm_config(llm, provider, model, base_url, extra_headers, interactive)

    if digest:
        app_config.digest_llm = new_config
    else:
        app_config.llm = new_config

    # In interactive mode, also ask about digest model
    if interactive and not digest:
        console.print()
        if typer.confirm("Configure a separate digest model?", default=False):
            digest_llm = app_config.digest_llm or new_config
            console.print(
                "\n  [bold]Digest model[/bold] — used for cross-session reports (low volume, quality matters).\n"
                "  A smarter model produces better insights (e.g. gemini-2.5-flash).\n"
            )
            app_config.digest_llm = _prompt_llm_config(
                digest_llm,
                None,
                None,
                None,
                None,
                interactive=True,
                default_model="gemini-2.5-flash",
            )

    app_config.save()
    console.print(f"\n  Configuration written to [bold]{Paths.config_file}[/bold]")

    # Download embedding model for label clustering (only on first setup)
    if not digest:
        console.print("\n  Downloading embedding model...")
        _download_embedding_model()

    # Offer to test
    if typer.confirm("Test connection?", default=True):
        _test_connection(new_config)


def _download_embedding_model() -> None:
    """Pre-download the sentence-transformers model so it's cached locally."""
    from cinsights.runtime import console

    try:
        import os

        os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
        from sentence_transformers import SentenceTransformer

        SentenceTransformer("all-MiniLM-L6-v2")
        console.print("  [green]✓[/green] Embedding model ready (all-MiniLM-L6-v2)")
    except Exception as e:
        console.print(f"  [yellow]⚠[/yellow] Could not download embedding model: {e}")
        console.print("    Label clustering will fall back to raw labels.")


def _test_connection(llm: LLMConfig) -> None:
    """Send a minimal request to verify the LLM config works."""
    import asyncio

    from cinsights.runtime import console

    async def _probe():
        if llm.is_local_ollama:
            return await _probe_ollama(llm)
        return await _probe_pydantic_ai(llm)

    async def _probe_pydantic_ai(llm: LLMConfig) -> int:
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

    async def _probe_ollama(llm: LLMConfig) -> int:
        import httpx

        async with httpx.AsyncClient(base_url=llm.base_url, timeout=30) as client:
            resp = await client.post(
                "/chat/completions",
                json={
                    "model": llm.model,
                    "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
                    "max_tokens": 20,
                },
            )
            resp.raise_for_status()
        return resp.json().get("usage", {}).get("completion_tokens", 0)

    try:
        tokens = asyncio.run(_probe())
        console.print(f"  Testing... [green]Got {tokens} tokens back from {llm.model}[/green]")
    except Exception as e:
        console.print(f"  Testing... [red]Failed: {e}[/red]")
        raise typer.Exit(1) from e


if __name__ == "__main__":
    app()
