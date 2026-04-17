from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

from pydantic import BaseModel, Field

from cinsights.analysis import LLMAnalyzer
from cinsights.prompts import render
from cinsights.settings import PromptTemplates
from cinsights.sources.base import SpanData, TraceData

logger = logging.getLogger(__name__)

MAX_IO_CHARS = 500  # Truncate tool I/O to keep prompt manageable


def _get_limits():
    from cinsights.settings import get_config

    return get_config().limits


class InsightCategoryEnum(StrEnum):
    SUMMARY = "summary"
    FRICTION = "friction"
    WIN = "win"
    RECOMMENDATION = "recommendation"
    PATTERN = "pattern"
    SKILL_PROPOSAL = "skill_proposal"


class InsightSeverityEnum(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class BehaviorCategoryEnum(StrEnum):
    OWNERSHIP_DODGE = "ownership_dodge"
    REASONING_LOOP = "reasoning_loop"
    PERMISSION_SEEKING = "permission_seeking"
    PREMATURE_STOP = "premature_stop"
    SIMPLEST_MENTALITY = "simplest_mentality"
    SELF_ADMITTED_ERROR = "self_admitted_error"


class BehaviorConfidenceEnum(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class BehavioralEvidenceItem(BaseModel):
    category: BehaviorCategoryEnum = Field(description="Which behavioral pattern was observed")
    turn_id: str = Field(
        description="The turn identifier (e.g. 'Turn 3') where this behavior occurred"
    )
    quote: str = Field(
        description="Verbatim excerpt from the agent's response in the original language"
    )
    explanation: str = Field(
        description="One sentence explaining why this qualifies as the given category"
    )
    confidence: BehaviorConfidenceEnum = Field(
        default=BehaviorConfidenceEnum.MEDIUM,
        description="How confident are you this is a genuine instance, not a false positive",
    )


class InsightItem(BaseModel):
    category: InsightCategoryEnum = Field(
        description="The type of insight: summary, friction, win, recommendation, pattern, or skill_proposal"
    )
    title: str = Field(description="Short descriptive title for this insight (5-15 words)")
    content: str = Field(
        description="Detailed markdown content explaining the insight with evidence from the timeline"
    )
    severity: InsightSeverityEnum = Field(
        default=InsightSeverityEnum.INFO,
        description="Impact level: info for observations, warning for notable issues, critical for major problems",
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Evidence supporting this insight. Reference tool calls by description (e.g., 'the Apply migration Bash call failed') or by pattern (e.g., 'Read was called 8 times on registry.go'). Never reference span numbers.",
    )


class AnalysisResult(BaseModel):
    insights: list[InsightItem] = Field(
        description="List of insights extracted from the session analysis"
    )
    behaviors: list[BehavioralEvidenceItem] = Field(
        default_factory=list,
        description="Behavioral patterns observed in the agent's responses. IMPORTANT: always check the Turn Exchanges for ownership_dodge patterns and report any found here. Return empty list if genuinely none.",
    )
    # Populated after LLM call (not part of structured output)
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0


def validate_behavioral_evidence(
    items: list[BehavioralEvidenceItem],
    spans: list[SpanData],
) -> list[tuple[BehavioralEvidenceItem, bool]]:
    """Check each item's quote against span data.

    Returns (item, is_valid) pairs. An item is valid if its quote appears
    as a substring in any span's input.value or output.value. Invalid items
    are kept but flagged — the caller decides whether to store them.
    """
    # Build a lookup of all text content across spans
    all_text = ""
    for s in spans:
        all_text += (s.attributes.get("input.value") or "") + "\n"
        all_text += (s.attributes.get("output.value") or "") + "\n"

    results = []
    for item in items:
        # Normalize whitespace for fuzzy matching
        quote = item.quote.strip()
        valid = len(quote) >= 5 and quote in all_text
        results.append((item, valid))
    return results


def _truncate(text: str | None, max_chars: int = MAX_IO_CHARS) -> str:
    if not text:
        return ""
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n... (truncated) ...\n" + text[-half:]


class _SpanView:
    """Lightweight wrapper to expose truncated I/O for Jinja templates."""

    def __init__(self, span: SpanData):
        self._span = span

    def __getattr__(self, name: str):
        return getattr(self._span, name)

    @property
    def input_display(self) -> str:
        return _truncate(self._span.input_value)

    @property
    def output_display(self) -> str:
        return _truncate(self._span.output_value)

    @property
    def tool_description(self) -> str | None:
        """Human-readable description from CC tool calls (e.g., 'Apply migration')."""
        desc = self._span.attributes.get("tool.description", "")
        if not desc:
            return None
        # CC sometimes puts the full input JSON as description, skip those
        if desc.startswith("{") or len(desc) > 100:
            return None
        return desc

    @property
    def error_message(self) -> str | None:
        return self._span.attributes.get("status_message")


def _sample_timeline_spans(spans: list[SpanData]) -> tuple[list[SpanData], str | None]:
    """Stratified sample of spans for the analysis prompt.

    Limits are read from ``config.json`` (``limits.max_timeline_spans`` and
    ``limits.timeline_head_tail``).
    """
    limits = _get_limits()
    max_spans = limits.max_timeline_spans
    head_tail = limits.timeline_head_tail

    n = len(spans)
    if n <= max_spans:
        return spans, None

    indexed = list(enumerate(spans))

    error_idxs = {i for i, s in indexed if not s.is_success}
    head_idxs = {i for i, _ in indexed[:head_tail]}
    tail_idxs = {i for i, _ in indexed[-head_tail:]}

    keep: set[int] = error_idxs | head_idxs | tail_idxs

    middle_candidates = [i for i, s in indexed if i not in keep and s.is_success]
    remaining_budget = max_spans - len(keep)
    if remaining_budget > 0 and middle_candidates:
        if remaining_budget >= len(middle_candidates):
            keep.update(middle_candidates)
        else:
            stride = len(middle_candidates) / remaining_budget
            keep.update(middle_candidates[int(k * stride)] for k in range(remaining_budget))

    sampled = [s for i, s in indexed if i in keep]
    notice = (
        f"TIMELINE TRUNCATED: showing {len(sampled)} of {n} spans "
        f"(all {len(error_idxs)} errors + first/last {head_tail} + uniform sample of the rest). "
        f"Tool counts and aggregate stats above reflect the FULL session."
    )
    return sampled, notice


def _build_prompts(trace: TraceData, spans: list[SpanData]) -> tuple[str, str]:
    """Build system and user prompts from Jinja templates."""
    root = trace.root_span
    wall_duration_s = (trace.end_time - trace.start_time).total_seconds()

    # Active duration = sum of Turn span durations. A session left open for
    # 46 hours but with 50 minutes of actual turns should report ~50 minutes,
    # not 46 hours. Fall back to wall-clock if no turns exist.
    turn_spans = [s for s in spans if s.name.startswith("Turn ")]
    active_duration_ms = sum(s.duration_ms for s in turn_spans) if turn_spans else 0
    duration_s = active_duration_ms / 1000 if active_duration_ms > 0 else wall_duration_s

    # Tool spans are identified by parent + tool name attributes.
    # Match the pipeline's _filter_tool_spans logic.
    tool_spans = [
        s
        for s in spans
        if s.parent_id is not None
        and (s.tool_name or "Permission" in s.name or "Notification" in s.name)
    ]
    error_count = sum(1 for s in tool_spans if not s.is_success)

    # Total tokens from turn spans, not the root span (which only has one turn's count).
    total_tokens = (
        sum(s.prompt_tokens + s.completion_tokens for s in turn_spans)
        if turn_spans
        else (root.total_tokens if root else 0)
    )

    # Tool call counts sorted by frequency. We compute this from the FULL span
    # list — even when the timeline is sampled below, the aggregates stay honest.
    tool_counts: dict[str, int] = {}
    for s in tool_spans:
        name = s.tool_name or "unknown"
        tool_counts[name] = tool_counts.get(name, 0) + 1
    sorted_counts = sorted(tool_counts.items(), key=lambda x: -x[1])

    timeline_spans, truncation_notice = _sample_timeline_spans(spans)

    # Determine which turns get agent text (error_adjacent: error turns ± 1)
    _turn_tool_map: dict[str, list[SpanData]] = {}
    for s in tool_spans:
        _turn_tool_map.setdefault(s.parent_id, []).append(s)

    _error_turn_indices: set[int] = set()
    for i, ts in enumerate(turn_spans):
        children = _turn_tool_map.get(ts.span_id, [])
        if any(not c.is_success for c in children):
            _error_turn_indices.update(range(max(0, i - 1), min(len(turn_spans), i + 2)))

    user_queries = []
    for i, ts in enumerate(turn_spans):
        query = ts.input_value
        if not query or not query.strip():
            continue
        turn_num = ts.name.replace("Turn ", "")
        entry: dict = {
            "turn": turn_num,
            "query": query.strip()[:200],
        }
        # Include agent text only for turns near errors (or all if few turns)
        include_agent = i in _error_turn_indices or len(turn_spans) <= 20
        agent_response = (ts.attributes.get("output.value") or "").strip()
        if agent_response and include_agent:
            max_half = 300
            if len(agent_response) <= max_half * 2:
                entry["agent_response"] = agent_response
            else:
                entry["agent_response"] = (
                    agent_response[:max_half] + "\n...\n" + agent_response[-max_half:]
                )
        user_queries.append(entry)

    system_prompt = render(PromptTemplates.SESSION_SYSTEM)
    user_prompt = render(
        PromptTemplates.SESSION_USER,
        model=root.model_name if root else "unknown",
        duration_s=duration_s,
        duration_min=duration_s / 60,
        total_spans=len(spans),
        tool_call_count=len(tool_spans),
        error_count=error_count,
        total_tokens=total_tokens,
        start_time=trace.start_time.isoformat(),
        tool_counts=sorted_counts,
        spans=[_SpanView(s) for s in timeline_spans],
        truncation_notice=truncation_notice,
        user_queries=user_queries,
    )
    return system_prompt, user_prompt


class SessionAnalyzer(LLMAnalyzer):
    """Analyze coding agent sessions using pydantic-ai with structured output."""

    async def analyze(self, trace: TraceData, spans: list[SpanData]) -> AnalysisResult:
        """Analyze a session's spans and produce structured insights."""
        system_prompt, user_prompt = _build_prompts(trace, spans)

        logger.info(
            "Analyzing trace %s (%d spans, prompt ~%d chars)",
            trace.trace_id,
            len(spans),
            len(user_prompt),
        )

        from cinsights.db.models import LLMCallKind, LLMCallScopeType

        result, prompt_tokens, completion_tokens = await self._run_llm(
            AnalysisResult,
            system_prompt,
            user_prompt,
            call_kind=LLMCallKind.SESSION_ANALYSIS,
            scope_type=LLMCallScopeType.SESSION,
            scope_id=trace.trace_id,
        )
        result.usage_prompt_tokens = prompt_tokens
        result.usage_completion_tokens = completion_tokens
        return result

    async def analyze_batch(
        self,
        items: list[tuple[TraceData, list[SpanData]]],
        max_concurrency: int = 5,
    ) -> list[AnalysisResult]:
        """Analyze multiple sessions concurrently."""
        semaphore = asyncio.Semaphore(max_concurrency)

        async def _bounded(trace: TraceData, spans: list[SpanData]) -> AnalysisResult:
            async with semaphore:
                return await self.analyze(trace, spans)

        tasks = [_bounded(trace, spans) for trace, spans in items]
        return await asyncio.gather(*tasks)
