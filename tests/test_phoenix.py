"""Tests for Phoenix source adapter (mocked client)."""

from datetime import UTC, datetime
from unittest.mock import MagicMock, patch

import pandas as pd

from cinsights.sources.phoenix import PhoenixSource


def _mock_spans_df(sessions: dict[str, int]) -> pd.DataFrame:
    """Create a mock spans dataframe with session.id attributes."""
    rows = []
    for sid, count in sessions.items():
        for i in range(count):
            rows.append(
                {
                    "name": f"Tool {i}",
                    "span_kind": "CHAIN",
                    "parent_id": "parent" if i > 0 else None,
                    "start_time": pd.Timestamp(f"2026-04-01 10:{i:02d}:00", tz="UTC"),
                    "end_time": pd.Timestamp(f"2026-04-01 10:{i:02d}:30", tz="UTC"),
                    "status_code": "OK",
                    "status_message": None,
                    "events": None,
                    "context.span_id": f"span-{sid[:4]}-{i}",
                    "context.trace_id": f"trace-{sid[:4]}",
                    "attributes.session.id": sid,
                    "attributes.user.id": "test@example.com",
                    "attributes.project.name": "test-project",
                    "attributes.tool.name": f"Tool{i}",
                }
            )
    df = pd.DataFrame(rows)
    df.index = df["context.span_id"]
    df.index.name = None
    return df


def test_discover_sessions():
    with patch("cinsights.sources.phoenix.source.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.spans.get_spans_dataframe.return_value = _mock_spans_df(
            {"sess-1": 5, "sess-2": 3}
        )

        source = PhoenixSource(base_url="http://localhost:6006")
        discovered = source.discover_sessions()
        assert len(discovered) == 2
        assert discovered[0].session_id in ("sess-1", "sess-2")
        # sess-1 has 5 spans
        s1 = next(d for d in discovered if d.session_id == "sess-1")
        assert s1.span_count == 5


def test_discover_sessions_time_filter():
    with patch("cinsights.sources.phoenix.source.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.spans.get_spans_dataframe.return_value = _mock_spans_df({"old-session": 2})

        source = PhoenixSource(base_url="http://localhost:6006")
        # Filter to only sessions after April 2
        discovered = source.discover_sessions(start_time=datetime(2026, 4, 2, tzinfo=UTC))
        assert len(discovered) == 0


def test_get_sessions_returns_data():
    with patch("cinsights.sources.phoenix.source.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.spans.get_spans_dataframe.return_value = _mock_spans_df({"sess-1": 3})

        source = PhoenixSource(base_url="http://localhost:6006")
        sessions = source.get_sessions()
        assert len(sessions) == 1
        assert sessions[0].session_id == "sess-1"


def test_get_spans_by_session():
    with patch("cinsights.sources.phoenix.source.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.spans.get_spans_dataframe.return_value = _mock_spans_df(
            {"sess-1": 5, "sess-2": 3}
        )

        source = PhoenixSource(base_url="http://localhost:6006")
        spans = source.get_spans_by_session("sess-1")
        assert len(spans) == 5
        assert all(s.attributes.get("session.id") == "sess-1" for s in spans)


def test_get_spans_returns_data():
    with patch("cinsights.sources.phoenix.source.Client") as mock_cls:
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
    with patch("cinsights.sources.phoenix.source.Client") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        mock_client.traces.get_traces.return_value = []

        source = PhoenixSource(base_url="http://localhost:6006")
        trace = source.get_trace("nonexistent")
        assert trace is None
