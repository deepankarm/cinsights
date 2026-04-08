from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from cinsights.analysis.session import (
    AnalysisResult,
    InsightCategoryEnum,
    SessionAnalyzer,
    _build_prompts,
    _truncate,
)
from cinsights.sources.base import SpanData, TraceData


def _make_span(
    tool_name="Bash",
    span_kind="TOOL",
    success=True,
    duration_s=1.0,
    input_val="ls",
    output_val="file.py",
):
    start = datetime(2026, 4, 1, 10, 0, tzinfo=UTC)
    end = datetime(2026, 4, 1, 10, 0, int(duration_s), tzinfo=UTC)
    return SpanData(
        span_id="span-1",
        trace_id="trace-1",
        parent_id="root",
        name=tool_name,
        span_kind=span_kind,
        status_code="OK" if success else "ERROR",
        start_time=start,
        end_time=end,
        attributes={
            "tool.name": tool_name,
            "input.value": input_val,
            "output.value": output_val,
        },
    )


def test_truncate_short():
    assert _truncate("hello") == "hello"


def test_truncate_long():
    long_text = "x" * 1000
    result = _truncate(long_text, max_chars=100)
    assert len(result) < 1000
    assert "truncated" in result


def test_truncate_none():
    assert _truncate(None) == ""


def test_build_prompts():
    trace = TraceData(
        trace_id="trace-1",
        start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
        end_time=datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
        spans=[_make_span()],
    )
    system, user = _build_prompts(trace, [_make_span(), _make_span(tool_name="Read")])
    assert "expert" in system.lower()
    assert "Bash" in user
    assert "Read" in user
    assert "Session Overview" in user


def test_span_data_properties():
    span = _make_span()
    assert span.tool_name == "Bash"
    assert span.input_value == "ls"
    assert span.output_value == "file.py"
    assert span.is_success is True
    assert span.duration_ms >= 0


@pytest.mark.asyncio
async def test_analyze_structured_output():
    """Test that analyzer correctly parses tool_use structured output."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "record_analysis"
    tool_use_block.input = {
        "insights": [
            {
                "category": "summary",
                "title": "Test Summary",
                "content": "A test session that did things.",
                "severity": "info",
                "evidence": ["the Apply migration Bash call", "Read on file.py"],
            },
            {
                "category": "friction",
                "title": "File not found errors",
                "content": "Agent tried to read missing files.",
                "severity": "warning",
                "evidence": ["Read on missing.go"],
            },
        ]
    }

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        analyzer = SessionAnalyzer(api_key="test-key")
        trace = TraceData(
            trace_id="trace-1",
            start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
            spans=[_make_span()],
        )
        result = await analyzer.analyze(trace, [_make_span()])

        assert isinstance(result, AnalysisResult)
        assert len(result.insights) == 2
        assert result.insights[0].category == InsightCategoryEnum.SUMMARY
        assert result.insights[0].title == "Test Summary"
        assert result.insights[0].evidence == ["the Apply migration Bash call", "Read on file.py"]
        assert result.insights[1].category == InsightCategoryEnum.FRICTION
        assert result.insights[1].severity == "warning"


@pytest.mark.asyncio
async def test_analyze_batch():
    """Test concurrent batch analysis."""
    tool_use_block = MagicMock()
    tool_use_block.type = "tool_use"
    tool_use_block.name = "record_analysis"
    tool_use_block.input = {
        "insights": [
            {
                "category": "summary",
                "title": "Summary",
                "content": "Done.",
                "severity": "info",
            }
        ]
    }

    mock_response = MagicMock()
    mock_response.content = [tool_use_block]

    with patch("anthropic.AsyncAnthropic") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value = mock_client
        mock_client.messages.create.return_value = mock_response

        analyzer = SessionAnalyzer(api_key="test-key")
        trace1 = TraceData(
            trace_id="t1",
            start_time=datetime(2026, 4, 1, 10, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 1, 10, 30, tzinfo=UTC),
            spans=[_make_span()],
        )
        trace2 = TraceData(
            trace_id="t2",
            start_time=datetime(2026, 4, 1, 11, 0, tzinfo=UTC),
            end_time=datetime(2026, 4, 1, 11, 30, tzinfo=UTC),
            spans=[_make_span()],
        )

        results = await analyzer.analyze_batch(
            [(trace1, [_make_span()]), (trace2, [_make_span()])],
            max_concurrency=2,
        )

        assert len(results) == 2
        assert all(isinstance(r, AnalysisResult) for r in results)
