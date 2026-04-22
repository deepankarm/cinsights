"""Tests for interestingness scoring signals (scoring/signals.py).

These determine which sessions get analyzed (and cost money).
"""

from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from cinsights.scoring.signals import (
    ContextPressure,
    DurationDeviation,
    EditsWithoutReadDeviation,
    ErrorRateDeviation,
    NewProject,
    ReadEditRatioDeviation,
    ResearchMutationDeviation,
    RetryPattern,
    SessionAbandonment,
    TurnCountDeviation,
    _deviation,
)


def make_session(**kwargs):
    """Create a minimal CodingSession-like object."""
    defaults = {
        "error_rate": 0.0,
        "read_edit_ratio": 5.0,
        "edits_without_read_pct": 5.0,
        "repeated_edits_count": 0,
        "turn_count": 10,
        "context_pressure_score": 0.0,
        "research_mutation_ratio": 8.0,
        "start_time": datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        "end_time": datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def make_baseline(**kwargs):
    """Create a minimal SessionBaseline-like object."""
    defaults = {
        "avg_error_rate": 5.0,
        "avg_read_edit_ratio": 5.0,
        "avg_edits_without_read_pct": 5.0,
        "avg_research_mutation_ratio": 8.0,
        "avg_turns": 10,
        "avg_duration_ms": 30 * 60 * 1000,  # 30 min
        "session_count": 20,
        "tool_distribution_json": '{"Read": 50, "Edit": 10}',
    }
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


# --- _deviation ---


def test_deviation_at_baseline():
    assert _deviation(10.0, 10.0) == 0.0


def test_deviation_2x_above():
    assert _deviation(20.0, 10.0) == 1.0


def test_deviation_1_5x_above():
    assert _deviation(15.0, 10.0) == 0.5


def test_deviation_below_baseline_normal():
    # Below baseline, not inverted → 0
    assert _deviation(5.0, 10.0) == 0.0


def test_deviation_inverted():
    # Half of baseline, inverted → 0.5
    assert _deviation(5.0, 10.0, invert=True) == 0.5


def test_deviation_inverted_zero():
    # At baseline, inverted → 0
    assert _deviation(10.0, 10.0, invert=True) == 0.0


def test_deviation_none_value():
    assert _deviation(None, 10.0) == 0.0


def test_deviation_zero_baseline():
    assert _deviation(10.0, 0.0) == 0.0


# --- ErrorRateDeviation ---


def test_error_rate_deviation_high():
    s = make_session(error_rate=15.0)
    b = make_baseline(avg_error_rate=5.0)
    assert ErrorRateDeviation().score(s, b) == 1.0  # 3x = clamped to 1.0


def test_error_rate_deviation_normal():
    s = make_session(error_rate=5.0)
    b = make_baseline(avg_error_rate=5.0)
    assert ErrorRateDeviation().score(s, b) == 0.0


# --- ReadEditRatioDeviation (inverted) ---


def test_read_edit_ratio_drop():
    # Ratio dropped to half of baseline → interesting
    s = make_session(read_edit_ratio=2.5)
    b = make_baseline(avg_read_edit_ratio=5.0)
    assert ReadEditRatioDeviation().score(s, b) == 0.5


def test_read_edit_ratio_above_baseline():
    # Above baseline → not interesting (inverted signal)
    s = make_session(read_edit_ratio=10.0)
    b = make_baseline(avg_read_edit_ratio=5.0)
    assert ReadEditRatioDeviation().score(s, b) == 0.0


# --- EditsWithoutReadDeviation ---


def test_blind_edits_high():
    s = make_session(edits_without_read_pct=15.0)
    b = make_baseline(avg_edits_without_read_pct=5.0)
    assert EditsWithoutReadDeviation().score(s, b) == 1.0  # 3x


def test_blind_edits_normal():
    s = make_session(edits_without_read_pct=5.0)
    b = make_baseline(avg_edits_without_read_pct=5.0)
    assert EditsWithoutReadDeviation().score(s, b) == 0.0


# --- RetryPattern ---


def test_retry_pattern_high_thrashing():
    s = make_session(repeated_edits_count=10)
    b = make_baseline()
    assert RetryPattern().score(s, b) == 1.0


def test_retry_pattern_moderate():
    s = make_session(repeated_edits_count=3)
    b = make_baseline()
    assert RetryPattern().score(s, b) == pytest.approx(0.6)


def test_retry_pattern_none():
    s = make_session(repeated_edits_count=0)
    b = make_baseline()
    assert RetryPattern().score(s, b) == 0.0


# --- NewProject ---


def test_new_project_cold_start():
    s = make_session()
    b = make_baseline(session_count=2)
    assert NewProject().score(s, b) == 1.0


def test_new_project_warming_up():
    s = make_session()
    b = make_baseline(session_count=7)
    assert NewProject().score(s, b) == 0.5


def test_new_project_established():
    s = make_session()
    b = make_baseline(session_count=20)
    assert NewProject().score(s, b) == 0.0


# --- TurnCountDeviation ---


def test_turn_count_very_long():
    s = make_session(turn_count=40)  # 4x avg of 10
    b = make_baseline(avg_turns=10)
    assert TurnCountDeviation().score(s, b) == 1.0


def test_turn_count_very_short():
    s = make_session(turn_count=2)  # 0.2x avg of 10
    b = make_baseline(avg_turns=10)
    assert TurnCountDeviation().score(s, b) == 1.0


def test_turn_count_normal():
    s = make_session(turn_count=10)
    b = make_baseline(avg_turns=10)
    assert TurnCountDeviation().score(s, b) == 0.0


# --- DurationDeviation ---


def test_duration_very_long():
    s = make_session(
        start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 1, 12, 0, tzinfo=UTC),  # 2h vs 30m avg = 4x
    )
    b = make_baseline(avg_duration_ms=30 * 60 * 1000)
    assert DurationDeviation().score(s, b) == 1.0


def test_duration_normal():
    s = make_session(
        start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
    )
    b = make_baseline(avg_duration_ms=30 * 60 * 1000)
    assert DurationDeviation().score(s, b) == 0.0


def test_duration_no_times():
    s = make_session(start_time=None, end_time=None)
    b = make_baseline()
    assert DurationDeviation().score(s, b) == 0.0


# --- ContextPressure ---


def test_context_pressure_high():
    s = make_session(context_pressure_score=0.8)
    b = make_baseline()
    assert ContextPressure().score(s, b) == 1.0


def test_context_pressure_moderate():
    s = make_session(context_pressure_score=0.4)
    b = make_baseline()
    assert ContextPressure().score(s, b) == 0.6


def test_context_pressure_low():
    s = make_session(context_pressure_score=0.05)
    b = make_baseline()
    assert ContextPressure().score(s, b) == 0.0


# --- SessionAbandonment ---


def test_abandonment_long_few_turns():
    s = make_session(
        start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 1, 11, 30, tzinfo=UTC),  # 90 min, 2x avg
        turn_count=2,
    )
    b = make_baseline(avg_duration_ms=30 * 60 * 1000)
    assert SessionAbandonment().score(s, b) == 0.8


def test_abandonment_normal_session():
    s = make_session(turn_count=15)
    b = make_baseline()
    assert SessionAbandonment().score(s, b) == 0.0


# --- ResearchMutationDeviation ---


def test_research_mutation_drop():
    s = make_session(research_mutation_ratio=4.0)
    b = make_baseline(avg_research_mutation_ratio=8.0)
    assert ResearchMutationDeviation().score(s, b) == 0.5


def test_research_mutation_normal():
    s = make_session(research_mutation_ratio=8.0)
    b = make_baseline(avg_research_mutation_ratio=8.0)
    assert ResearchMutationDeviation().score(s, b) == 0.0


# --- Signal weights ---


def test_all_weights_sum_to_one():
    from cinsights.scoring.signals import DEFAULT_SIGNALS

    total = sum(s.weight for s in DEFAULT_SIGNALS)
    assert total == pytest.approx(1.0, abs=0.01)
