from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

import anthropic
from pydantic import BaseModel, Field

from cinsights.prompts import render
from cinsights.sources.base import SpanData, TraceData

logger = logging.getLogger(__name__)

MAX_IO_CHARS = 500  # Truncate tool I/O to keep prompt manageable


# --- Structured output schema ---


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


class InsightItem(BaseModel):
    category: InsightCategoryEnum = Field(
        description="The type of insight: summary, friction, win, recommendation, pattern, or skill_proposal"
    )
    title: str = Field(
        description="Short descriptive title for this insight (5-15 words)"
    )
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
    # Populated after LLM call (not part of structured output)
    usage_prompt_tokens: int = 0
    usage_completion_tokens: int = 0


# Tool schema for structured output via tool_use
_ANALYSIS_TOOL = {
    "name": "record_analysis",
    "description": "Record the structured analysis results for a coding agent session.",
    "input_schema": AnalysisResult.model_json_schema(),
}


# --- Prompt helpers ---


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


def _build_prompts(trace: TraceData, spans: list[SpanData]) -> tuple[str, str]:
    """Build system and user prompts from Jinja templates."""
    root = trace.root_span
    duration_s = (trace.end_time - trace.start_time).total_seconds()
    tool_spans = [s for s in spans if s.span_kind == "TOOL"]
    error_count = sum(1 for s in spans if not s.is_success)

    # Tool call counts sorted by frequency
    tool_counts: dict[str, int] = {}
    for s in tool_spans:
        name = s.tool_name or "unknown"
        tool_counts[name] = tool_counts.get(name, 0) + 1
    sorted_counts = sorted(tool_counts.items(), key=lambda x: -x[1])

    system_prompt = render("session_analysis_system.md.j2")
    user_prompt = render(
        "session_analysis_user.md.j2",
        model=root.model_name if root else "unknown",
        duration_s=duration_s,
        duration_min=duration_s / 60,
        total_spans=len(spans),
        tool_call_count=len(tool_spans),
        error_count=error_count,
        total_tokens=root.total_tokens if root else 0,
        start_time=trace.start_time.isoformat(),
        tool_counts=sorted_counts,
        spans=[_SpanView(s) for s in spans],
    )
    return system_prompt, user_prompt


# --- Analyzer ---


class SessionAnalyzer:
    """Analyze coding agent sessions using Claude API with structured output."""

    def __init__(
        self,
        api_key: str,
        model: str = "claude-sonnet-4-20250514",
        base_url: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ):
        kwargs: dict = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        if extra_headers:
            kwargs["default_headers"] = extra_headers
        self.async_client = anthropic.AsyncAnthropic(**kwargs)
        self.model = model

    async def analyze(self, trace: TraceData, spans: list[SpanData]) -> AnalysisResult:
        """Analyze a session's spans and produce structured insights."""
        system_prompt, user_prompt = _build_prompts(trace, spans)

        logger.info(
            "Analyzing trace %s (%d spans, prompt ~%d chars)",
            trace.trace_id,
            len(spans),
            len(user_prompt),
        )

        response = await self.async_client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
            tools=[_ANALYSIS_TOOL],
            tool_choice={"type": "tool", "name": "record_analysis"},
        )

        result = self._parse_response(response)
        result.usage_prompt_tokens = response.usage.input_tokens
        result.usage_completion_tokens = response.usage.output_tokens
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

    def _parse_response(self, response: anthropic.types.Message) -> AnalysisResult:
        """Parse structured output from tool_use response."""
        for block in response.content:
            if block.type == "tool_use" and block.name == "record_analysis":
                return AnalysisResult.model_validate(block.input)

        # Fallback if no tool_use block found (shouldn't happen with tool_choice)
        logger.error("No tool_use block in response, falling back to text parse")
        return AnalysisResult(
            insights=[
                InsightItem(
                    category=InsightCategoryEnum.SUMMARY,
                    title="Analysis Failed",
                    content="No structured output received from the model.",
                    severity=InsightSeverityEnum.WARNING,
                )
            ]
        )
