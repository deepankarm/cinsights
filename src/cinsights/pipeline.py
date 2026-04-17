"""Analyze + digest pipeline orchestration."""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table
from sqlalchemy.ext.asyncio import async_sessionmaker
from sqlmodel import col
from sqlmodel import select as select_fn
from sqlmodel.ext.asyncio.session import AsyncSession

from cinsights.runtime import _content_hash, _RunHandle, console
from cinsights.settings import SourceType, get_settings

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from types import ModuleType

    from cinsights.analysis.digest import DigestAnalysisResult, DigestAnalyzer
    from cinsights.analysis.session import AnalysisResult
    from cinsights.db.models import CodingSession, Digest
    from cinsights.sources.base import SpanData, TraceData, TraceSource


def _filter_tool_spans(spans: list[SpanData]) -> list[SpanData]:
    """Tool calls + CC permission/notification spans."""
    return [
        s
        for s in spans
        if s.parent_id is not None
        and (s.tool_name or "Permission" in s.name or "Notification" in s.name)
    ]


async def _store_indexed(
    db: AsyncSession,
    trace_id: str,
    session_id: str,
    trace: TraceData,
    spans: list[SpanData],
    source: TraceSource,
    force: bool,
    existing: CodingSession | None,
    project_name: str | None,
) -> CodingSession:
    """Extract and store Tier 0 metadata + quality metrics (zero LLM cost).

    Creates/updates CodingSession and ToolCall rows. Computes quality metrics
    from the tool call sequence. Sets status = INDEXED.
    """
    from cinsights.db.models import (
        CodingSession,
        SessionStatus,
        ToolCall,
    )

    root = next((s for s in spans if s.parent_id is None), None)
    tool_spans = _filter_tool_spans(spans)

    user_id = None
    for s in spans:
        if not user_id:
            user_id = s.user_id
        if user_id:
            break

    last_span_time = max(s.end_time for s in spans) if spans else None

    import json as json_mod

    turn_spans = sorted(
        [s for s in spans if s.name.startswith("Turn ")],
        key=lambda s: s.start_time,
    )
    total_prompt = sum(s.prompt_tokens for s in turn_spans)
    total_completion = sum(s.completion_tokens for s in turn_spans)
    total_tokens = total_prompt + total_completion

    context_growth = json_mod.dumps(
        [
            {
                "turn": int(s.name.replace("Turn ", "")),
                "prompt_tokens": s.prompt_tokens,
                "completion_tokens": s.completion_tokens,
                "duration_ms": s.duration_ms,
            }
            for s in turn_spans
        ]
    )

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
            model=(root.model_name if root and root.model_name else None)
            or next((s.model_name for s in turn_spans if s.model_name), None),
            total_tokens=total_tokens,
            prompt_tokens=total_prompt,
            completion_tokens=total_completion,
            context_growth_json=context_growth,
            span_count=len(spans),
            last_span_time=last_span_time,
            status=SessionStatus.INDEXED,
        )
        db.add(coding_session)
    else:
        coding_session = existing
        coding_session.user_id = user_id or existing.user_id
        coding_session.project_name = project_name or existing.project_name
        coding_session.start_time = trace.start_time
        coding_session.end_time = trace.end_time
        coding_session.total_tokens = total_tokens
        coding_session.prompt_tokens = total_prompt
        coding_session.completion_tokens = total_completion
        coding_session.context_growth_json = context_growth
        coding_session.span_count = len(spans)
        coding_session.last_span_time = last_span_time

    # Source-specific agent_type detection
    if settings.source == SourceType.ENTIREIO:
        from cinsights.sources.entireio import EntireioSource

        if isinstance(source, EntireioSource):
            coding_session.metadata_json = source.get_session_metadata_json(trace_id)
            idx = source._build_index()
            for _, ref in idx.items():
                if ref.checkpoint_id == trace_id.split(":")[1] and ref.session_idx == int(
                    trace_id.split(":")[2]
                ):
                    if ref.metadata.agent:
                        agent_name = ref.metadata.agent.lower().replace(" ", "-")
                        if agent_name in ("agent", "mock-lifecycle-agent", "vogon-agent"):
                            agent_name = "unknown"
                        if not existing:
                            coding_session.agent_type = agent_name
                    break

    if settings.source == SourceType.LOCAL:
        from cinsights.sources.local import LocalSource

        if isinstance(source, LocalSource):
            detected = source.get_agent_type(trace_id)
            if detected and not existing:
                coding_session.agent_type = detected

    # Clear old tool calls if re-indexing (preserve insights — they require LLM cost to regenerate)
    if force or existing:
        old_tcs = await db.exec(select_fn(ToolCall).where(ToolCall.session_id == trace_id))
        for tc in old_tcs.all():
            await db.delete(tc)
        await db.flush()

    # Store tool calls
    tool_call_rows = []
    for span in tool_spans:
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
        tool_call_rows.append(tc)

    # Compute Tier 0 quality metrics
    from cinsights.metrics import compute_all as compute_metrics

    context_growth_list = None
    if context_growth:
        import contextlib

        with contextlib.suppress(json_mod.JSONDecodeError, TypeError):
            context_growth_list = json_mod.loads(context_growth)

    metrics = compute_metrics(tool_call_rows, context_growth_list, total_tokens)
    for key, value in metrics.items():
        if value is not None:
            setattr(coding_session, key, value)

    # Harness attribution from root span (local/entireio only; Phoenix stays None)
    if root:
        v = root.attributes.get("harness.agent_version")
        if v:
            coding_session.agent_version = str(v)
        eff = root.attributes.get("harness.effort_level")
        if eff:
            coding_session.effort_level = str(eff)
        atd = root.attributes.get("harness.adaptive_thinking_disabled")
        if atd is not None:
            coding_session.adaptive_thinking_disabled = bool(atd)

    # User-interrupt count (structural, no LLM)
    _INTERRUPT_MARKER = "[Request interrupted by user]"
    coding_session.interrupt_count = sum(
        1 for s in spans if _INTERRUPT_MARKER in (s.attributes.get("input.value") or "")
    )

    from cinsights.costs import estimate_session_analysis_tokens

    coding_session.estimated_analysis_tokens = estimate_session_analysis_tokens(spans)

    return coding_session


async def _store_insights(
    db: AsyncSession,
    coding_session: CodingSession,
    result: AnalysisResult,
) -> int:
    """Store LLM-generated insights on an already-INDEXED session.

    Updates status to ANALYZED. Returns the number of insights persisted.
    """
    from cinsights.db.models import (
        Insight,
        InsightCategory,
        InsightSeverity,
        SessionStatus,
    )

    settings = get_settings()

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
            tenant_id=coding_session.tenant_id,
            session_id=coding_session.id,
            category=cat,
            title=item.title,
            content=item.content,
            severity=sev,
            prompt_version=settings.prompt_version_session,
        )
        db.add(insight)

        # Store behavioral tag as a BehavioralEvidence row if present
        if item.behavioral_tag:
            from cinsights.db.models import (
                BehavioralEvidence as BehavioralEvidenceRow,
            )
            from cinsights.db.models import BehaviorCategory, BehaviorConfidence

            try:
                bcat = BehaviorCategory(item.behavioral_tag)
            except ValueError:
                bcat = None
            if bcat:
                # Map insight severity → behavioral confidence
                conf_map = {"critical": "high", "warning": "medium", "info": "low"}
                try:
                    bconf = BehaviorConfidence(conf_map.get(str(sev), "medium"))
                except ValueError:
                    bconf = BehaviorConfidence.MEDIUM

                db.add(
                    BehavioralEvidenceRow(
                        tenant_id=coding_session.tenant_id,
                        session_id=coding_session.id,
                        category=bcat,
                        turn_id=item.title,  # best we have — insight title as reference
                        quote=(item.behavioral_quote or "")[:2000],
                        explanation=item.content[:2000],
                        confidence=bconf,
                    )
                )

    coding_session.status = SessionStatus.ANALYZED
    coding_session.analysis_prompt_tokens = result.usage_prompt_tokens
    coding_session.analysis_completion_tokens = result.usage_completion_tokens
    return len(result.insights)


async def _store_digest_sections(
    db: AsyncSession,
    digest_record: Digest,
    result: DigestAnalysisResult,
    json_mod: ModuleType,
) -> None:
    """Store digest analysis results as DigestSection rows.

    ``json_mod`` is passed in instead of imported at module top so the LLM
    pieces (which import anthropic transitively) stay out of the import path
    for ``cinsights --help`` and other fast-exit commands.
    """
    from cinsights.db.models import DigestSection, DigestSectionType, DigestStatus

    def _dump(items: list) -> str:
        return json_mod.dumps([i.model_dump() for i in items])

    sections = [
        (
            DigestSectionType.AT_A_GLANCE,
            "At a Glance",
            "",
            json_mod.dumps(result.narrative.at_a_glance.model_dump()),
        ),
        (DigestSectionType.WORK_AREAS, "What You Work On", "", _dump(result.narrative.work_areas)),
        (
            DigestSectionType.DEVELOPER_PERSONA,
            "How You Use Coding Agents",
            result.narrative.developer_persona,
            None,
        ),
        (
            DigestSectionType.IMPRESSIVE_WINS,
            "Impressive Things You Did",
            "",
            _dump(result.forward.impressive_wins),
        ),
        (
            DigestSectionType.FRICTION_ANALYSIS,
            "Where Things Go Wrong",
            "",
            _dump(result.actions.friction_analysis),
        ),
        (
            DigestSectionType.CLAUDE_MD_SUGGESTIONS,
            "Suggested CLAUDE.md Additions",
            "",
            _dump(result.actions.claude_md_suggestions),
        ),
        (
            DigestSectionType.FEATURE_RECOMMENDATIONS,
            "Features to Try",
            "",
            _dump(result.actions.feature_recommendations),
        ),
        (
            DigestSectionType.RECOMMENDATIONS,
            "Recommendations",
            "",
            _dump(result.forward.recommendations),
        ),
    ]

    if result.actions.stop_hook_suggestions:
        sections.append(
            (
                DigestSectionType.STOP_HOOK_SUGGESTIONS,
                "Stop Hook Suggestions",
                "",
                _dump(result.actions.stop_hook_suggestions),
            )
        )

    settings = get_settings()
    for i, (stype, title, content, meta) in enumerate(sections):
        db.add(
            DigestSection(
                digest_id=digest_record.id,
                section_type=stype,
                title=title,
                content=content,
                order=i,
                metadata_json=meta,
                prompt_version=settings.prompt_version_digest,
            )
        )

    digest_record.status = DigestStatus.COMPLETE
    digest_record.analysis_prompt_tokens = result.total_prompt_tokens
    digest_record.analysis_completion_tokens = result.total_completion_tokens
    digest_record.completed_at = datetime.now(UTC)
    await db.commit()


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

    from cinsights.db.models import Digest, DigestSection, DigestSectionType, DigestStatus
    from cinsights.stats import compute_all

    label = scope_project or (f"user:{user_id}" if user_id else "global")

    async with sessionmaker() as db:
        stats = await compute_all(db, start, end, project_name=scope_project, user_id=user_id)

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

        # Extract previous digest summary before deleting for delta narratives.
        previous_summary = None
        if latest_complete:
            prev_sections_result = await db.exec(
                select_fn(DigestSection)
                .where(DigestSection.digest_id == latest_complete.id)
                .where(
                    col(DigestSection.section_type).in_(
                        [
                            DigestSectionType.AT_A_GLANCE,
                            DigestSectionType.FRICTION_ANALYSIS,
                        ]
                    )
                )
            )
            prev_parts = []
            for sec in prev_sections_result.all():
                prev_parts.append(f"### {sec.title}\n{sec.content}")
            if prev_parts:
                prev_date = latest_complete.completed_at
                date_str = f"{prev_date:%Y-%m-%d}" if prev_date else "unknown"
                previous_summary = (
                    f"Previous digest ({date_str}, {latest_complete.session_count} sessions):\n"
                    + "\n\n".join(prev_parts)
                )

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

        # Attach previous digest context to stats for the LLM
        if previous_summary:
            stats.previous_digest_summary = previous_summary

        settings = get_settings()
        digest_record = Digest(
            tenant_id=settings.tenant_id,
            user_id=user_id,
            project_name=scope_project,
            period_start=start,
            period_end=end,
            session_count=stats.session_count,
            stats_json=stats.model_dump_json(),
            analysis_model=analyzer._llm_config.model if analyzer else None,
            status=DigestStatus.ANALYZING,
        )
        db.add(digest_record)
        await db.commit()
        await db.refresh(digest_record)

        try:
            assert analyzer is not None  # not stats_only path
            result = await analyzer.analyze(stats, digest_id=digest_record.id)
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


async def _discover_work_items(
    settings,
    source: TraceSource,
    sessionmaker,
    hours: int,
    limit: int,
    force: bool,
    trace_ids: list[str] | None,
) -> list[tuple[str, str, object, list]]:
    """Discover sessions from source and return work items to process."""
    from cinsights.db.models import CodingSession, SessionStatus

    work_items: list[tuple[str, str, object, list]] = []

    if trace_ids:
        from cinsights.sources.base import TraceData

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(
                f"Fetching {len(trace_ids)} ID(s) from {settings.source}...", total=None
            )
            for tid in trace_ids:
                spans = await asyncio.to_thread(source.get_spans_by_session, tid)
                if spans:
                    trace = TraceData(
                        trace_id=tid,
                        start_time=spans[0].start_time,
                        end_time=spans[-1].end_time,
                        spans=spans,
                    )
                    work_items.append((tid, tid, trace, spans))
                elif hasattr(source, "get_spans"):
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
            progress.update(task, description=f"Found {len(work_items)} session(s) with spans")
    elif force:
        # Force mode: re-index all DB sessions belonging to the current source.
        from cinsights.sources.base import TraceData

        async with sessionmaker() as db:
            all_sessions = (
                await db.exec(
                    select_fn(CodingSession)
                    .where(CodingSession.source == str(settings.source))
                    .order_by(col(CodingSession.start_time).desc())
                    .limit(limit)
                )
            ).all()
            session_ids = [cs.id for cs in all_sessions]

        console.print(f"  Force re-indexing {len(session_ids)} {settings.source} session(s)...")

        not_found = 0
        for sid in session_ids:
            spans = await asyncio.to_thread(source.get_spans_by_session, sid)
            if not spans:
                not_found += 1
                continue
            trace = TraceData(
                trace_id=sid,
                start_time=spans[0].start_time,
                end_time=spans[-1].end_time,
                spans=spans,
            )
            work_items.append((sid, sid, trace, spans))

        if not_found:
            console.print(f"  [dim]{not_found} session(s) not found in source, skipped[/dim]")
    else:
        start_time = datetime.now(UTC) - timedelta(hours=hours)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task(f"Discovering sessions from {settings.source}...", total=None)
            discovered = await asyncio.to_thread(source.discover_sessions, start_time=start_time)
            progress.update(task, description=f"Found {len(discovered)} sessions")

        if not discovered:
            console.print(f"[yellow]No sessions found in the last {hours} hours.[/yellow]")
            return work_items

        REANALYZE_GROWTH_RATIO = 0.20
        REANALYZE_QUIET_SECONDS = 60.0
        now = datetime.now(UTC)

        skipped = 0
        async with sessionmaker() as db:
            for d in discovered[:limit]:
                existing = await db.get(CodingSession, d.session_id)
                if existing and existing.status == SessionStatus.ANALYZED:
                    prior = max(existing.span_count, 1)
                    growth = (d.span_count - existing.span_count) / prior
                    last_seen = existing.last_span_time
                    if last_seen is not None and last_seen.tzinfo is None:
                        last_seen = last_seen.replace(tzinfo=UTC)
                    quiet_for = (
                        (now - last_seen).total_seconds() if last_seen is not None else float("inf")
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
                        start_time=spans[0].start_time,
                        end_time=spans[-1].end_time,
                        spans=spans,
                    )
                    work_items.append((d.session_id, d.session_id, trace, spans))

        if skipped:
            console.print(f"  [dim]{skipped} session(s) unchanged or still active, skipped[/dim]")

    return work_items


def _get_project_name(
    settings,
    source: TraceSource,
    trace_id: str,
    previous_tag: str | None,
) -> tuple[str | None, str]:
    """Determine project name for a session based on source type."""
    if settings.source == SourceType.ENTIREIO and settings.entireio_repo_path:
        from pathlib import Path

        return Path(settings.entireio_repo_path).name, "From repo path"
    if settings.source == SourceType.LOCAL:
        from cinsights.sources.local import LocalSource

        if isinstance(source, LocalSource):
            return source.get_project_name(trace_id), "From directory"
    return previous_tag, "Previous tag"


async def _index_async(
    hours: int,
    limit: int,
    force: bool,
    verbose: bool,
    trace_ids: list[str] | None = None,
    run: _RunHandle | None = None,
) -> None:
    """Discover sessions, index metadata + quality metrics, score against baselines.

    Zero LLM cost. This is the workhorse command — run frequently.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    settings = get_settings()

    from cinsights.db.engine import get_sessionmaker
    from cinsights.db.models import CodingSession, SessionBaseline
    from cinsights.scoring import format_score_reason, score_session
    from cinsights.sources.factory import create_source
    from cinsights.trends import update_baseline, update_daily_trend

    source = create_source(settings)
    sessionmaker = get_sessionmaker()

    work_items = await _discover_work_items(
        settings,
        source,
        sessionmaker,
        hours,
        limit,
        force,
        trace_ids,
    )

    if not work_items:
        console.print("[yellow]No sessions to index.[/yellow]")
        return

    console.print(f"\n[bold]Indexing {len(work_items)} session(s)...[/bold]\n")

    # Fetch previous project tags
    async with sessionmaker() as _prev_db:
        previous_tags: dict[str, str | None] = {}
        for trace_id, _, _, _ in work_items:
            existing_row = await _prev_db.get(CodingSession, trace_id)
            previous_tags[trace_id] = existing_row.project_name if existing_row else None

    # Index all sessions
    indexed = 0
    failed = 0
    async with sessionmaker() as db:
        for trace_id, session_id, trace, spans in work_items:
            pn, _ = _get_project_name(settings, source, trace_id, previous_tags.get(trace_id))
            try:
                existing = await db.get(CodingSession, trace_id)
                coding_session = await _store_indexed(
                    db,
                    trace_id,
                    session_id,
                    trace,
                    spans,
                    source,
                    force,
                    existing,
                    project_name=pn,
                )
                await update_daily_trend(db, coding_session)
                await update_baseline(db, coding_session)
                await db.commit()
                indexed += 1
                console.print(f"  [cyan]○[/cyan] {trace_id[:12]} — indexed")
            except Exception as e:
                await db.rollback()
                failed += 1
                console.print(f"  [red]✗[/red] {trace_id[:12]} — {e}")

    # Score all indexed sessions against baselines
    console.print(f"\n[bold]Scoring {indexed} session(s)...[/bold]\n")

    scored_rows: list[tuple[str, float, str]] = []
    async with sessionmaker() as db:
        for trace_id, _, _, _ in work_items:
            cs = await db.get(CodingSession, trace_id)
            if not cs:
                continue
            user_id_val = cs.user_id or "unknown"
            project_val = cs.project_name
            baseline_id = f"{user_id_val}:{project_val or '_'}"
            baseline = await db.get(SessionBaseline, baseline_id)
            if not baseline:
                baseline = SessionBaseline(
                    id=baseline_id,
                    user_id=user_id_val,
                    project_name=project_val,
                    tenant_id=cs.tenant_id,
                    session_count=0,
                )
            total, breakdown = score_session(cs, baseline)
            cs.interestingness_score = total
            reason = format_score_reason(total, breakdown)
            scored_rows.append((trace_id, total, reason))
        await db.commit()

    # Display scores
    scored_rows.sort(key=lambda x: x[1], reverse=True)
    for trace_id, score, reason in scored_rows:
        if score >= 0.6:
            console.print(f"  [bold red]★[/bold red] {trace_id[:12]} — {reason}")
        elif score >= 0.4:
            console.print(f"  [yellow]◆[/yellow] {trace_id[:12]} — {reason}")
        else:
            console.print(f"  [dim]·[/dim] {trace_id[:12]} — {reason}")

    console.print()
    table = Table(title="Index Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Indexed", str(indexed))
    table.add_row("Failed", str(failed))
    if scored_rows:
        table.add_row("High interest (≥0.6)", str(sum(1 for _, s, _ in scored_rows if s >= 0.6)))
        table.add_row(
            "Medium interest (≥0.4)", str(sum(1 for _, s, _ in scored_rows if 0.4 <= s < 0.6))
        )
        table.add_row("Low interest (<0.4)", str(sum(1 for _, s, _ in scored_rows if s < 0.4)))
    console.print(table)


async def _score_async(
    user_id: str | None = None,
    project: str | None = None,
    min_score: float = 0.0,
    verbose: bool = False,
) -> None:
    """Re-score existing sessions and display distribution + coverage.

    Diagnostic command — does not re-index or trigger LLM analysis.
    Shows score distribution, per-user and per-project coverage, and
    highlights gaps where users/projects would get no analysis.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    from collections import defaultdict

    from cinsights.db.engine import get_sessionmaker
    from cinsights.db.models import CodingSession, SessionBaseline, SessionStatus
    from cinsights.scoring import format_score_reason, score_session

    sessionmaker = get_sessionmaker()

    query = select_fn(CodingSession).where(
        col(CodingSession.status).in_([SessionStatus.INDEXED, SessionStatus.ANALYZED]),
        # Skip sub-agent sessions (prompt_suggestion, compact, etc.)
        ~col(CodingSession.id).like("%agent-aprompt_suggestion%"),
        ~col(CodingSession.id).like("%agent-acompact%"),
    )
    if user_id:
        query = query.where(CodingSession.user_id == user_id)
    if project:
        query = query.where(CodingSession.project_name == project)
    query = query.order_by(col(CodingSession.start_time).desc()).limit(2000)

    # Score all sessions
    scored_rows: list[tuple[str, str | None, str | None, str, float, str]] = []

    async with sessionmaker() as db:
        result = await db.exec(query)
        sessions = result.all()

        for cs in sessions:
            user_id_val = cs.user_id or "unknown"
            project_val = cs.project_name
            baseline_id = f"{user_id_val}:{project_val or '_'}"
            baseline = await db.get(SessionBaseline, baseline_id)
            if not baseline:
                baseline = SessionBaseline(
                    id=baseline_id,
                    user_id=user_id_val,
                    project_name=project_val,
                    tenant_id=cs.tenant_id,
                    session_count=0,
                )
            total, breakdown = score_session(cs, baseline)
            cs.interestingness_score = total
            reason = format_score_reason(total, breakdown)
            scored_rows.append((cs.id, cs.user_id, cs.project_name, cs.status, total, reason))
        await db.commit()

    if not scored_rows:
        console.print("[yellow]No sessions to score. Run cinsights index first.[/yellow]")
        return

    scored_rows.sort(key=lambda x: x[4], reverse=True)

    # --- 1. Distribution table ---
    thresholds = [0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
    dist_table = Table(title="Score Distribution")
    dist_table.add_column("Threshold", justify="right")
    dist_table.add_column("Sessions", justify="right")
    dist_table.add_column("Unanalyzed", justify="right")
    dist_table.add_column("Bar")

    total_count = len(scored_rows)
    for t in thresholds:
        count = sum(1 for _, _, _, _, s, _ in scored_rows if s >= t)
        unanalyzed = sum(1 for _, _, _, st, s, _ in scored_rows if s >= t and st == "indexed")
        pct = count / total_count if total_count else 0
        bar = "█" * int(pct * 30)
        style = "bold red" if t >= 0.6 else "yellow" if t >= 0.4 else "dim"
        dist_table.add_row(
            f"[{style}]≥ {t:.1f}[/{style}]",
            str(count),
            str(unanalyzed) if unanalyzed else "-",
            f"[{style}]{bar}[/{style}] {pct:.0%}",
        )
    console.print(dist_table)

    # --- 2. Simulate selection at different thresholds ---
    # Build CodingSession-like objects for select_for_analysis
    from cinsights.db.models import CodingSession as CS
    from cinsights.scoring import select_for_analysis

    # Build scored tuples for select_for_analysis
    session_objs: dict[str, CS] = {}
    scored_tuples: list[tuple[CS, float, dict[str, float]]] = []

    async with sessionmaker() as db:
        for sid, _uid, _proj, _status, score, _ in scored_rows:
            cs = await db.get(CS, sid)
            if cs:
                session_objs[sid] = cs
                scored_tuples.append((cs, score, {}))

    # Compute per-session cost estimate
    import math

    from cinsights.costs import estimate_total_cost

    # Cache per-session cost
    _cost_cache: dict[str, float] = {}
    for sid, cs in session_objs.items():
        if cs.estimated_analysis_tokens:
            c = estimate_total_cost(cs.estimated_analysis_tokens)
            if c is not None:
                _cost_cache[sid] = c

    def _est_cost(sessions: list[CS]) -> float:
        return sum(_cost_cache.get(s.id, 0.0) for s in sessions)

    def _fmt_cost(cost: float) -> str:
        if not cost:
            return "-"
        rounded = math.ceil(cost * 2) / 2  # round up to nearest $0.50
        return f"~${rounded:.1f}" if rounded == int(rounded * 2) / 2 else f"~${rounded:.2f}"

    sim_thresholds = [0.6, 0.5, 0.4, 0.3, 0.2]
    sim_table = Table(title="What would be analyzed? (threshold → sessions selected)")
    sim_table.add_column("--min-score", justify="right")
    sim_table.add_column("By score", justify="right")
    sim_table.add_column("+ coverage fills", justify="right")
    sim_table.add_column("Total", justify="right", style="bold")
    sim_table.add_column("% of all")
    sim_table.add_column("Est. cost", justify="right")

    for t in sim_thresholds:
        to_analyze, _ = select_for_analysis(scored_tuples, min_score=t, min_per_user_project=2)
        by_score_only = sum(1 for _, _, _, _, s, _ in scored_rows if s >= t)
        fills = len(to_analyze) - by_score_only
        pct = len(to_analyze) / total_count * 100 if total_count else 0
        cost = _est_cost(to_analyze)
        cost_str = _fmt_cost(cost)
        if t == min_score:
            sim_table.add_row(
                f"[bold]{t:.1f}[/bold]",
                str(by_score_only),
                f"+{fills}" if fills > 0 else "-",
                f"[bold]{len(to_analyze)}[/bold]",
                f"{pct:.0f}%",
                f"[bold]{cost_str}[/bold]",
            )
        else:
            sim_table.add_row(
                f"{t:.1f}",
                str(by_score_only),
                f"+{fills}" if fills > 0 else "-",
                str(len(to_analyze)),
                f"{pct:.0f}%",
                cost_str,
            )

    console.print(sim_table)

    # --- 3. Coverage detail at chosen threshold ---
    to_analyze_ms, _ = select_for_analysis(
        scored_tuples, min_score=min_score, min_per_user_project=2
    )
    selected_ids = {s.id for s in to_analyze_ms}

    # Build nested project → user stats
    by_proj_user: dict[str, dict[str, dict]] = defaultdict(
        lambda: defaultdict(
            lambda: {"total": 0, "selected": 0, "analyzed": 0, "top_score": 0.0, "est_cost": 0.0}
        )
    )
    for sid, uid, proj, status, score, _ in scored_rows:
        p = proj or "Unknown"
        u = uid or "unknown"
        d = by_proj_user[p][u]
        d["total"] += 1
        d["top_score"] = max(d["top_score"], score)
        if sid in selected_ids:
            d["selected"] += 1
            d["est_cost"] += _cost_cache.get(sid, 0.0)
        if status == "analyzed":
            d["analyzed"] += 1

    def _pct(n: int, total: int) -> str:
        return f"{n / total * 100:.0f}%" if total else "-"

    def _score_style(score: float) -> str:
        if score >= 0.6:
            return "bold red"
        if score >= min_score:
            return "yellow"
        return "dim"

    cov_table = Table(title=f"Coverage (at --min-score {min_score})")
    cov_table.add_column("Project", max_width=20)
    cov_table.add_column("User", max_width=22)
    cov_table.add_column("Total", justify="right")
    cov_table.add_column("Selected", justify="right")
    cov_table.add_column("Sel %", justify="right")
    cov_table.add_column("Analyzed", justify="right")
    cov_table.add_column("Ana %", justify="right")
    cov_table.add_column("Top Score", justify="right")
    cov_table.add_column("Est. Cost", justify="right")

    sorted_projects = sorted(
        by_proj_user, key=lambda p: sum(u["total"] for u in by_proj_user[p].values()), reverse=True
    )
    for i, proj in enumerate(sorted_projects):
        users = by_proj_user[proj]
        # Project totals
        pt = sum(u["total"] for u in users.values())
        ps = sum(u["selected"] for u in users.values())
        pa = sum(u["analyzed"] for u in users.values())
        pts = max(u["top_score"] for u in users.values())
        pc = sum(u["est_cost"] for u in users.values())
        style = _score_style(pts)

        pc_str = f"${pc:.2f}" if pc else "-"
        cov_table.add_row(
            f"[bold]{proj}[/bold]",
            "",
            f"[bold]{pt}[/bold]",
            f"[bold]{ps}[/bold]",
            f"[bold]{_pct(ps, pt)}[/bold]",
            f"[bold]{pa}[/bold]",
            f"[bold]{_pct(pa, pt)}[/bold]",
            f"[bold][{style}]{pts:.2f}[/{style}][/bold]",
            f"[bold]{pc_str}[/bold]",
        )
        # User rows within project
        sorted_users = sorted(users, key=lambda u: users[u]["total"], reverse=True)
        for uid in sorted_users:
            d = users[uid]
            style = _score_style(d["top_score"])
            uc_str = f"${d['est_cost']:.2f}" if d["est_cost"] else "-"
            cov_table.add_row(
                "",
                f"  {uid}",
                str(d["total"]),
                str(d["selected"]),
                _pct(d["selected"], d["total"]),
                str(d["analyzed"]),
                _pct(d["analyzed"], d["total"]),
                f"[{style}]{d['top_score']:.2f}[/{style}]",
                uc_str,
            )
        if i < len(sorted_projects) - 1:
            cov_table.add_section()

    console.print(cov_table)

    # --- 4. Recommendation ---
    unanalyzed = [s for s in to_analyze_ms if s.status.value == "indexed"]
    if unanalyzed:
        cost = _est_cost(unanalyzed)
        cost_str = f", est. [bold]{_fmt_cost(cost)}[/bold]" if cost else ""
        console.print(
            f"\n  At [bold]--min-score {min_score}[/bold]: {len(to_analyze_ms)} sessions selected "
            f"({len(unanalyzed)} unanalyzed{cost_str})"
            f"\n  Run [cyan]cinsights analyze --min-score {min_score}[/cyan] to analyze them."
        )


async def _analyze_async(
    hours: int,
    limit: int,
    force: bool,
    concurrency: int,
    verbose: bool,
    trace_ids: list[str] | None,
    run: _RunHandle | None = None,
    min_score: float = 0.0,
) -> None:
    """LLM-analyze INDEXED sessions that meet the score threshold.

    Sessions must already be indexed (via ``cinsights index``). This command
    reads interestingness scores and selects sessions above ``min_score``
    for LLM analysis.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    settings = get_settings()

    from cinsights.analysis.project_detection import ProjectDetector
    from cinsights.analysis.session import SessionAnalyzer
    from cinsights.db.engine import get_sessionmaker
    from cinsights.db.models import CodingSession, SessionStatus
    from cinsights.settings import get_llm_config
    from cinsights.sources.factory import create_source

    source = create_source(settings)
    sessionmaker = get_sessionmaker()

    llm = get_llm_config()
    analyzer = SessionAnalyzer(llm_config=llm)
    project_detector = ProjectDetector(llm_config=llm)

    async with sessionmaker() as _kp_db:
        kp_result = await _kp_db.exec(
            select_fn(CodingSession.project_name)
            .where(CodingSession.project_name.is_not(None))
            .distinct()
        )
        known_projects = sorted({p for p in kp_result.all() if p})

    if trace_ids:
        # Analyze specific sessions by ID
        work_items = await _discover_work_items(
            settings,
            source,
            sessionmaker,
            hours,
            limit,
            force,
            trace_ids,
        )
    else:
        # Select INDEXED sessions using scoring + coverage fills
        from cinsights.scoring import select_for_analysis

        query = (
            select_fn(CodingSession)
            .where(CodingSession.status == SessionStatus.INDEXED)
            .where(CodingSession.interestingness_score.isnot(None))
            .order_by(col(CodingSession.interestingness_score).desc())
        )

        async with sessionmaker() as db:
            result = await db.exec(query)
            all_indexed = result.all()

        if not all_indexed:
            console.print("[yellow]No scored INDEXED sessions found.[/yellow]")
            console.print(
                "  Run [cyan]cinsights index[/cyan] first to discover and score sessions."
            )
            return

        # Build scored tuples and apply selection with coverage fills
        scored_tuples = [(s, s.interestingness_score or 0.0, {}) for s in all_indexed]
        candidates, _ = select_for_analysis(scored_tuples, min_score=min_score)
        candidates = candidates[:limit]

        if not candidates:
            console.print(f"[yellow]No sessions selected at --min-score {min_score}.[/yellow]")
            return

        by_score = sum(1 for s in candidates if (s.interestingness_score or 0) >= min_score)
        by_fill = len(candidates) - by_score
        console.print(
            f"\n[bold]Selected {len(candidates)} INDEXED session(s)[/bold] "
            f"({by_score} by score ≥ {min_score}, {by_fill} by coverage fills)\n"
        )

        work_items = []
        # Build source instances per source type to load spans
        from cinsights.sources.base import TraceData
        from cinsights.sources.factory import create_source as _create_source

        source_cache: dict[str, TraceSource] = {str(settings.source): source}

        def _get_source(source_name: str) -> TraceSource | None:
            if source_name in source_cache:
                return source_cache[source_name]
            try:
                from copy import copy

                s = copy(settings)
                s.source = SourceType(source_name)
                src = _create_source(s)
                source_cache[source_name] = src
                return src
            except Exception:
                return None

        for cs in candidates:
            src = _get_source(cs.source) or source
            spans = await asyncio.to_thread(src.get_spans_by_session, cs.id)
            if spans:
                trace = TraceData(
                    trace_id=cs.id,
                    start_time=spans[0].start_time,
                    end_time=spans[-1].end_time,
                    spans=spans,
                )
                work_items.append((cs.id, cs.id, trace, spans))
                console.print(
                    f"  [yellow]◆[/yellow] {cs.id[:12]} — score={cs.interestingness_score:.2f}, "
                    f"user={cs.user_id or '-'}, project={cs.project_name or '-'}"
                )

    if not work_items:
        console.print("[yellow]No sessions to analyze.[/yellow]")
        return

    # Fetch previous project tags
    async with sessionmaker() as _prev_db:
        previous_tags: dict[str, str | None] = {}
        for trace_id, _, _, _ in work_items:
            existing_row = await _prev_db.get(CodingSession, trace_id)
            previous_tags[trace_id] = existing_row.project_name if existing_row else None

    console.print(
        f"\n[bold]Analyzing {len(work_items)} session(s) (concurrency={concurrency})...[/bold]\n"
    )

    analysis_input = [(trace, spans) for _, _, trace, spans in work_items]

    # Project detection for phoenix source (others already have project names)
    if settings.source not in (SourceType.ENTIREIO, SourceType.LOCAL):
        detect_items_list: list[tuple[str, str | None, list[SpanData]]] = [
            (trace_id, previous_tags[trace_id], _filter_tool_spans(spans))
            for trace_id, _, _, spans in work_items
        ]
        analysis_results, project_guesses = await asyncio.gather(
            analyzer.analyze_batch(analysis_input, max_concurrency=concurrency),
            project_detector.detect_batch(
                detect_items_list, known_projects, max_concurrency=concurrency
            ),
        )
    else:
        from cinsights.analysis.project_detection import ProjectGuess

        analysis_results = await analyzer.analyze_batch(analysis_input, max_concurrency=concurrency)
        project_guesses = [
            ProjectGuess(
                project_name=_get_project_name(settings, source, tid, previous_tags.get(tid))[0],
                confidence="high",
                reasoning="From source",
            )
            for tid, _, _, _ in work_items
        ]

    # Store LLM results
    from cinsights.trends import update_daily_trend

    analyzed = 0
    failed = 0
    async with sessionmaker() as db:
        for (trace_id, _session_id, _trace, _spans), result, project_guess in zip(
            work_items, analysis_results, project_guesses, strict=True
        ):
            try:
                coding_session = await db.get(CodingSession, trace_id)
                if not coding_session:
                    continue
                if project_guess.project_name and not coding_session.project_name:
                    coding_session.project_name = project_guess.project_name
                n_insights = await _store_insights(db, coding_session, result)
                await update_daily_trend(db, coding_session)
                await db.commit()
                analyzed += 1
                if run is not None:
                    run.sessions_analyzed += 1
                    run.total_prompt_tokens += (
                        result.usage_prompt_tokens + project_guess.usage_prompt_tokens
                    )
                    run.total_completion_tokens += (
                        result.usage_completion_tokens + project_guess.usage_completion_tokens
                    )
                console.print(
                    f"  [green]✓[/green] {trace_id[:12]} — {n_insights} insights, "
                    f"project={project_guess.project_name or 'unknown'}"
                )
            except Exception as e:
                await db.rollback()
                failed += 1
                console.print(f"  [red]✗[/red] {trace_id[:12]} — {e}")

    console.print()
    table = Table(title="Analysis Summary")
    table.add_column("Metric", style="bold")
    table.add_column("Count", justify="right")
    table.add_row("Analyzed", str(analyzed))
    table.add_row("Failed", str(failed))
    console.print(table)


async def _digest_async(
    scope_type: str,
    scope_value: str,
    days: int,
    stats_only: bool,
    verbose: bool,
    run: _RunHandle | None = None,
) -> None:
    """Generate a digest for a project or developer.

    ``scope_type`` is ``"project"`` or ``"user"``. ``scope_value`` is the
    project name or user ID respectively.
    """
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    settings = get_settings()

    from cinsights.db.engine import get_sessionmaker

    end = datetime.now(UTC)
    start = end - timedelta(days=days)
    sessionmaker = get_sessionmaker()

    if scope_type == "project":
        scope_project, user_id = scope_value, None
        label = scope_value
    else:
        scope_project, user_id = None, scope_value
        label = f"user:{scope_value}"

    analyzer = None
    if not stats_only:
        from cinsights.analysis.digest import DigestAnalyzer
        from cinsights.settings import get_llm_config

        analyzer = DigestAnalyzer(llm_config=get_llm_config())

    console.print(f"[bold]Running digest for {label} (last {days} days)...[/bold]\n")

    result = await _run_one_digest(
        sessionmaker=sessionmaker,
        analyzer=analyzer,
        scope_project=scope_project,
        user_id=user_id,
        start=start,
        end=end,
        stats_only=stats_only,
    )

    if run is not None and isinstance(result, tuple) and result[0] is True:
        run.digests_generated += 1
        run.total_prompt_tokens += result[1]
        run.total_completion_tokens += result[2]

    status = result[0] if isinstance(result, tuple) else result
    if status is True:
        console.print(f"  [green]✓[/green] {label} — done")
        url_path = (
            f"/projects/{scope_value}" if scope_type == "project" else f"/users/{scope_value}"
        )
        console.print(f"\n  View at: [bold]http://localhost:{settings.port}{url_path}[/bold]")
    elif status == "empty":
        console.print(f"  [yellow]·[/yellow] {label} — no sessions")
    elif status == "stats_only":
        console.print(f"  [cyan]·[/cyan] {label} — stats only")
    elif status == "unchanged":
        console.print(f"  [dim]·[/dim] {label} — unchanged, reused")
