"""Tests for Phoenix source adapter (mocked client)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

from cinsights.sources.phoenix import PhoenixSource


def test_get_sessions_empty():
    with patch("cinsights.sources.phoenix.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.sessions.list.return_value = []

        source = PhoenixSource(base_url="http://localhost:6006")
        sessions = source.get_sessions()
        assert sessions == []


def test_get_sessions_returns_data():
    with patch("cinsights.sources.phoenix.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.sessions.list.return_value = [
            {
                "session_id": "sess-1",
                "start_time": "2026-04-01T10:00:00Z",
                "end_time": "2026-04-01T10:30:00Z",
                "traces": [
                    {
                        "trace_id": "trace-1",
                        "start_time": "2026-04-01T10:00:00Z",
                        "end_time": "2026-04-01T10:30:00Z",
                    }
                ],
            }
        ]

        source = PhoenixSource(base_url="http://localhost:6006")
        sessions = source.get_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-1"
        assert len(sessions[0].traces) == 1
        assert sessions[0].traces[0].trace_id == "trace-1"


def test_get_sessions_time_filter():
    with patch("cinsights.sources.phoenix.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.sessions.list.return_value = [
            {
                "session_id": "old-session",
                "start_time": "2026-01-01T10:00:00Z",
                "end_time": "2026-01-01T10:30:00Z",
                "traces": [],
            }
        ]

        source = PhoenixSource(base_url="http://localhost:6006")
        # Filter to only recent sessions
        sessions = source.get_sessions(
            start_time=datetime(2026, 4, 1, tzinfo=UTC)
        )
        assert len(sessions) == 0


def test_get_spans_returns_data():
    with patch("cinsights.sources.phoenix.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.spans.get_spans.return_value = [
            {
                "span_id": "span-1",
                "parent_id": None,
                "name": "agent",
                "span_kind": "AGENT",
                "status_code": "OK",
                "start_time": "2026-04-01T10:00:00Z",
                "end_time": "2026-04-01T10:30:00Z",
                "attributes": {"llm.model_name": "claude-sonnet-4-20250514"},
            }
        ]

        source = PhoenixSource(base_url="http://localhost:6006")
        spans = source.get_spans("trace-1")
        assert len(spans) == 1
        assert spans[0].span_kind == "AGENT"
        assert spans[0].model_name == "claude-sonnet-4-20250514"


def test_get_trace_not_found():
    with patch("cinsights.sources.phoenix.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.traces.get_traces.return_value = []

        source = PhoenixSource(base_url="http://localhost:6006")
        trace = source.get_trace("nonexistent")
        assert trace is None
