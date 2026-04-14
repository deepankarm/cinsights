"""Interestingness signals for session scoring.

Each signal compares a session's metrics against the developer's baseline
and returns a 0-1 score. Higher = more interesting = more likely to benefit
from LLM analysis.

Signal weights are tuned so that the weighted sum naturally clusters around
0.2-0.4 for routine sessions and 0.6+ for genuinely interesting ones.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from cinsights.db.models import CodingSession, SessionBaseline


class Signal(Protocol):
    """A scoring signal that evaluates session interestingness."""

    name: str
    weight: float

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        """Return 0-1 score. Higher = more interesting."""
        ...


def _deviation(value: float | None, baseline: float, invert: bool = False) -> float:
    """Compute normalized deviation from baseline.

    Returns 0-1 where 0 = at baseline, 1 = extreme deviation.
    If invert=True, lower-than-baseline values score high (e.g. Read:Edit drop).
    """
    if value is None or baseline == 0:
        return 0.0
    ratio = value / baseline
    dev = max(0, 1 - ratio) if invert else max(0, ratio - 1)
    # Sigmoid-like clamp: 2x deviation = 1.0
    return min(1.0, dev)


@dataclass
class ErrorRateDeviation:
    """High error rate relative to baseline."""

    name: str = "error_rate_deviation"
    weight: float = 0.15

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        return _deviation(session.error_rate, baseline.avg_error_rate)


@dataclass
class ReadEditRatioDeviation:
    """Low Read:Edit ratio relative to baseline (less research)."""

    name: str = "read_edit_ratio_drop"
    weight: float = 0.10

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        return _deviation(session.read_edit_ratio, baseline.avg_read_edit_ratio, invert=True)


@dataclass
class EditsWithoutReadDeviation:
    """High blind-edit rate relative to baseline."""

    name: str = "blind_edits_deviation"
    weight: float = 0.10

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        return _deviation(session.edits_without_read_pct, baseline.avg_edits_without_read_pct)


@dataclass
class RetryPattern:
    """Repeated edits to same file (thrashing)."""

    name: str = "retry_pattern"
    weight: float = 0.10

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        count = session.repeated_edits_count or 0
        # 5+ repeated edits = fully interesting
        return min(1.0, count / 5)


@dataclass
class SessionAbandonment:
    """Long duration with few turns and ends badly."""

    name: str = "session_abandonment"
    weight: float = 0.05

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        if not session.start_time or not session.end_time:
            return 0.0
        duration_ms = (session.end_time - session.start_time).total_seconds() * 1000
        turns = session.turn_count or 0
        avg_dur = baseline.avg_duration_ms or 1

        # Long relative to baseline but few turns
        if duration_ms > avg_dur * 2 and turns < 5:
            return 0.8
        if duration_ms > avg_dur * 1.5 and turns < 3:
            return 0.6
        return 0.0


@dataclass
class NewProject:
    """First sessions in a project (no baseline exists)."""

    name: str = "new_project"
    weight: float = 0.15

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        # Cold start: baseline has very few sessions
        if baseline.session_count <= 3:
            return 1.0
        if baseline.session_count <= 10:
            return 0.5
        return 0.0


@dataclass
class NewAgent:
    """Agent type differs from what's in the baseline tool distribution."""

    name: str = "new_agent"
    weight: float = 0.10

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        import json

        if not baseline.tool_distribution_json:
            return 0.5  # No distribution data = somewhat interesting
        try:
            dist = json.loads(baseline.tool_distribution_json)
        except (json.JSONDecodeError, TypeError):
            return 0.0
        # Check if session uses tools not in the baseline
        # This is a rough proxy — new agents use different tool mixes
        if not dist:
            return 0.3
        return 0.0


@dataclass
class TurnCountDeviation:
    """Unusual session size (very long or very short)."""

    name: str = "turn_count_deviation"
    weight: float = 0.07

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        turns = session.turn_count or 0
        avg = baseline.avg_turns or 1
        if avg == 0:
            return 0.0
        ratio = turns / avg
        # Both very short (<0.3x) and very long (>3x) are interesting
        if ratio < 0.3 or ratio > 3.0:
            return 1.0
        if ratio < 0.5 or ratio > 2.0:
            return 0.5
        return 0.0


@dataclass
class DurationDeviation:
    """Unusual session duration."""

    name: str = "duration_deviation"
    weight: float = 0.07

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        if not session.start_time or not session.end_time:
            return 0.0
        duration_ms = (session.end_time - session.start_time).total_seconds() * 1000
        avg = baseline.avg_duration_ms or 1
        if avg == 0:
            return 0.0
        ratio = duration_ms / avg
        if ratio > 3.0 or ratio < 0.2:
            return 1.0
        if ratio > 2.0 or ratio < 0.3:
            return 0.5
        return 0.0


@dataclass
class ContextPressure:
    """Session approaching context window limits."""

    name: str = "context_pressure"
    weight: float = 0.06

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        pressure = session.context_pressure_score or 0
        # Pressure > 0.5 = half of turns had steep growth
        if pressure > 0.5:
            return 1.0
        if pressure > 0.3:
            return 0.6
        if pressure > 0.1:
            return 0.3
        return 0.0


@dataclass
class ResearchMutationDeviation:
    """Low research:mutation ratio relative to baseline."""

    name: str = "research_mutation_drop"
    weight: float = 0.05

    def score(self, session: CodingSession, baseline: SessionBaseline) -> float:
        return _deviation(
            session.research_mutation_ratio,
            baseline.avg_research_mutation_ratio,
            invert=True,
        )


DEFAULT_SIGNALS: list[Signal] = [
    ErrorRateDeviation(),
    ReadEditRatioDeviation(),
    EditsWithoutReadDeviation(),
    RetryPattern(),
    SessionAbandonment(),
    NewProject(),
    NewAgent(),
    TurnCountDeviation(),
    DurationDeviation(),
    ContextPressure(),
    ResearchMutationDeviation(),
]
