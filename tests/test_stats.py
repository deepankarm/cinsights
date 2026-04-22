"""Tests for stats.py pure computation functions."""

from datetime import UTC, datetime
from types import SimpleNamespace

from cinsights.stats import _compute_cost_context, _compute_hourly_quality, _compute_weekly_trends


def _session(
    hour=10,
    day_offset=0,
    read_edit_ratio=5.0,
    error_rate=3.0,
    edits_without_read_pct=10.0,
    tokens_per_useful_edit=500.0,
    context_pressure_score=0.1,
    research_mutation_ratio=8.0,
    write_vs_edit_pct=5.0,
    tool_calls_per_turn=3.0,
    interrupt_count=0,
    effort_level=None,
    total_tokens=5000,
    prompt_tokens=4000,
    completion_tokens=1000,
    turn_count=10,
):
    return SimpleNamespace(
        start_time=datetime(2026, 4, 7 + day_offset, hour, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 7 + day_offset, hour, 30, tzinfo=UTC),
        read_edit_ratio=read_edit_ratio,
        error_rate=error_rate,
        edits_without_read_pct=edits_without_read_pct,
        tokens_per_useful_edit=tokens_per_useful_edit,
        context_pressure_score=context_pressure_score,
        research_mutation_ratio=research_mutation_ratio,
        write_vs_edit_pct=write_vs_edit_pct,
        tool_calls_per_turn=tool_calls_per_turn,
        interrupt_count=interrupt_count,
        effort_level=effort_level,
        total_tokens=total_tokens,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        turn_count=turn_count,
    )


# --- _compute_hourly_quality ---


def test_hourly_quality_single_hour():
    sessions = [_session(hour=9, read_edit_ratio=2.0), _session(hour=9, read_edit_ratio=4.0)]
    rows, variance = _compute_hourly_quality(sessions)
    assert len(rows) == 1
    assert rows[0]["hour"] == 9
    assert rows[0]["sessions"] == 2
    assert rows[0]["median_read_edit"] == 3.0  # median of 2.0 and 4.0


def test_hourly_quality_multiple_hours():
    sessions = [
        _session(hour=9, read_edit_ratio=2.0),
        _session(hour=14, read_edit_ratio=6.0),
    ]
    rows, variance = _compute_hourly_quality(sessions)
    assert len(rows) == 2
    assert rows[0]["hour"] == 9
    assert rows[1]["hour"] == 14
    assert variance == 3.0  # 6.0 / 2.0


def test_hourly_quality_empty():
    rows, variance = _compute_hourly_quality([])
    assert rows == []
    assert variance is None


def test_hourly_quality_none_metrics_skipped():
    sessions = [_session(hour=10, read_edit_ratio=None)]
    rows, _ = _compute_hourly_quality(sessions)
    assert rows[0]["median_read_edit"] is None


def test_hourly_quality_interrupt_summed():
    sessions = [_session(hour=10, interrupt_count=3), _session(hour=10, interrupt_count=5)]
    rows, _ = _compute_hourly_quality(sessions)
    assert rows[0]["total_interrupts"] == 8


def test_hourly_quality_effort_distribution():
    sessions = [
        _session(hour=10, effort_level="high"),
        _session(hour=10, effort_level="high"),
        _session(hour=10, effort_level="low"),
    ]
    rows, _ = _compute_hourly_quality(sessions)
    assert rows[0]["effort_distribution"] == {"high": 2, "low": 1}


# --- _compute_weekly_trends ---


def test_weekly_trends_single_week():
    # April 7, 2026 is a Monday
    sessions = [_session(day_offset=0), _session(day_offset=2)]
    trends = _compute_weekly_trends(sessions)
    assert len(trends) == 1
    assert trends[0].session_count == 2
    assert trends[0].week == "2026-04-06"  # Monday of that week


def test_weekly_trends_two_weeks():
    sessions = [_session(day_offset=0), _session(day_offset=7)]
    trends = _compute_weekly_trends(sessions)
    assert len(trends) == 2
    assert trends[0].session_count == 1
    assert trends[1].session_count == 1


def test_weekly_trends_averages():
    sessions = [
        _session(day_offset=0, read_edit_ratio=2.0, error_rate=10.0),
        _session(day_offset=1, read_edit_ratio=4.0, error_rate=20.0),
    ]
    trends = _compute_weekly_trends(sessions)
    assert trends[0].avg_read_edit_ratio == 3.0
    assert trends[0].avg_error_rate == 15.0


def test_weekly_trends_total_tokens():
    sessions = [
        _session(day_offset=0, total_tokens=1000),
        _session(day_offset=1, total_tokens=2000),
    ]
    trends = _compute_weekly_trends(sessions)
    assert trends[0].total_tokens == 3000


def test_weekly_trends_empty():
    assert _compute_weekly_trends([]) == []


def test_weekly_trends_sorted():
    sessions = [_session(day_offset=14), _session(day_offset=0)]
    trends = _compute_weekly_trends(sessions)
    assert trends[0].week < trends[1].week


# --- _compute_cost_context ---


def test_cost_context_basic():
    sessions = [
        _session(prompt_tokens=4000, completion_tokens=1000),
        _session(prompt_tokens=6000, completion_tokens=2000),
    ]
    ctx = _compute_cost_context(sessions, total_duration=60.0, error_breakdown={"timeout": 3})
    assert ctx.total_errors == 3
    assert ctx.error_rework_estimate_min == 6.0
    assert ctx.avg_duration_per_session_min == 30.0


def test_cost_context_empty():
    ctx = _compute_cost_context([], total_duration=0.0, error_breakdown={})
    assert ctx.total_errors == 0
    assert ctx.avg_duration_per_session_min == 0.0


def test_cost_context_multiple_error_types():
    sessions = [_session()]
    ctx = _compute_cost_context(
        sessions,
        total_duration=30.0,
        error_breakdown={"timeout": 2, "not_found": 3, "permission": 1},
    )
    assert ctx.total_errors == 6
    assert ctx.error_rework_estimate_min == 12.0
