from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol, runtime_checkable


@dataclass
class SpanData:
    """Normalized span data from any trace source."""

    span_id: str
    trace_id: str
    parent_id: str | None
    name: str
    span_kind: str  # AGENT, TOOL, LLM, CHAIN, etc.
    status_code: str  # OK, ERROR, UNSET
    start_time: datetime
    end_time: datetime
    attributes: dict = field(default_factory=dict)

    @property
    def duration_ms(self) -> float:
        return (self.end_time - self.start_time).total_seconds() * 1000

    @property
    def tool_name(self) -> str | None:
        return self.attributes.get("tool.name") or self.attributes.get("name")

    @property
    def input_value(self) -> str | None:
        return self.attributes.get("input.value")

    @property
    def output_value(self) -> str | None:
        return self.attributes.get("output.value")

    @property
    def is_success(self) -> bool:
        return self.status_code != "ERROR"

    @property
    def model_name(self) -> str | None:
        return self.attributes.get("llm.model_name")

    @property
    def total_tokens(self) -> int:
        return int(self.attributes.get("llm.token_count.total", 0))

    @property
    def prompt_tokens(self) -> int:
        return int(self.attributes.get("llm.token_count.prompt", 0))

    @property
    def completion_tokens(self) -> int:
        return int(self.attributes.get("llm.token_count.completion", 0))


@dataclass
class SessionData:
    """Normalized session data from any trace source."""

    session_id: str
    traces: list[TraceData]
    start_time: datetime
    end_time: datetime


@dataclass
class TraceData:
    """A single trace (maps to one CC session or conversation turn)."""

    trace_id: str
    start_time: datetime
    end_time: datetime
    spans: list[SpanData] = field(default_factory=list)

    @property
    def root_span(self) -> SpanData | None:
        for span in self.spans:
            if span.parent_id is None:
                return span
        return None

    @property
    def tool_spans(self) -> list[SpanData]:
        return [s for s in self.spans if s.span_kind == "TOOL"]


@runtime_checkable
class TraceSource(Protocol):
    """Protocol for trace data sources (Phoenix, Langfuse, raw OTEL, etc.)."""

    def get_sessions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[SessionData]:
        """Return sessions with their traces."""
        ...

    def get_trace(self, trace_id: str) -> TraceData | None:
        """Return a single trace with all its spans."""
        ...

    def get_spans(
        self,
        trace_id: str,
        span_kind: str | None = None,
    ) -> list[SpanData]:
        """Return spans for a trace, optionally filtered by kind."""
        ...
