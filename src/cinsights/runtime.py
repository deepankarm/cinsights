"""Self-observability primitives shared by every cinsights entry point.

Provides:

- ``console`` — the singleton Rich Console used by both ``cli`` and
  ``pipeline`` modules so output styling stays consistent.
- ``_content_hash`` — content-only SHA-256 of digest stats, used for the
  hash-based digest skip in ``pipeline._run_one_digest``.
- ``_RunHandle`` + ``_track_run`` — async context manager that creates a
  ``refresh_run`` row at the start of an analyze/digest/refresh invocation
  and finalizes it with wall time, status, token totals, and DB size on exit
  (success or failure). This is the migration-trigger sensor — when its
  ``wall_seconds`` p95 climbs past 5 minutes consistently, that's the cue to
  ship Iter 5 (rollups); when ``db_size_bytes`` crosses 10GB, that's the cue
  to ship Iter 6 (Postgres).
"""

from __future__ import annotations

import hashlib
import json as _json
import os
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from rich.console import Console

from cinsights.settings import get_settings

console = Console()


def _content_hash(stats_json: str) -> str:
    """SHA-256 of digest stats with timestamp fields removed.

    ``period_start`` / ``period_end`` are set to ``now()`` on every digest
    run, so a naive hash of the full JSON would never match. We strip those
    fields before hashing so reruns within the same data window collapse to
    a single hash and the LLM step gets skipped.
    """
    payload = _json.loads(stats_json)
    for noise in ("period_start", "period_end"):
        payload.pop(noise, None)
    canonical = _json.dumps(payload, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()


class _RunHandle:
    """Mutable counters the body of a tracked run updates as it works.

    The context manager creates one of these, yields it to the caller, and
    persists its final values to the ``refresh_run`` row on exit.
    """

    __slots__ = (
        "digests_generated",
        "extra",
        "id",
        "sessions_analyzed",
        "total_completion_tokens",
        "total_prompt_tokens",
    )

    def __init__(self, run_id: str) -> None:
        self.id = run_id
        self.sessions_analyzed = 0
        self.digests_generated = 0
        self.total_prompt_tokens = 0
        self.total_completion_tokens = 0
        self.extra: dict[str, str | int | float | None] = {}


@asynccontextmanager
async def _track_run(command: str) -> AsyncIterator[_RunHandle]:
    """Persist a ``refresh_run`` row for self-observability.

    Wrap analyze/digest/refresh bodies with::

        async with _track_run("refresh") as run:
            ...
            run.sessions_analyzed += 1
            run.total_prompt_tokens += ...

    On exit (success or exception), the row is updated with wall time,
    status, DB size, and the final counter values. Exceptions propagate
    after the row is finalized so failure paths still get observability.
    """
    from cinsights.db.engine import get_sessionmaker
    from cinsights.db.models import RefreshRun, RefreshRunCommand, RefreshRunStatus

    settings = get_settings()
    sessionmaker = get_sessionmaker()
    started = datetime.now(UTC)
    started_perf = time.perf_counter()

    try:
        from cinsights.settings import get_config

        config = get_config()
        run_metadata = _json.dumps(
            {
                "model": (config.analyze_llm or config.llm).model,
                "provider": (config.analyze_llm or config.llm).provider,
            }
        )
    except Exception:
        run_metadata = None

    async with sessionmaker() as db:
        run = RefreshRun(
            tenant_id=settings.tenant_id,
            command=RefreshRunCommand(command),
            started_at=started,
            status=RefreshRunStatus.RUNNING,
            metadata_json=run_metadata,
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
        db_size: int | None = None
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
                run.status = RefreshRunStatus.FAILED if error else RefreshRunStatus.SUCCESS
                run.db_size_bytes = db_size
                run.sessions_analyzed = handle.sessions_analyzed
                run.digests_generated = handle.digests_generated
                run.total_prompt_tokens = handle.total_prompt_tokens
                run.total_completion_tokens = handle.total_completion_tokens
                if error:
                    run.error_message = error[:2000]
                if handle.extra and run.metadata_json:
                    merged = _json.loads(run.metadata_json)
                    merged.update(handle.extra)
                    run.metadata_json = _json.dumps(merged)
                elif handle.extra:
                    run.metadata_json = _json.dumps(handle.extra)
                db.add(run)
                await db.commit()
