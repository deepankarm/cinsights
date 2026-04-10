from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

import pandas as pd
from phoenix.client import Client

from cinsights.sources.base import SessionData, SpanData, TraceData

logger = logging.getLogger(__name__)


def _parse_dt(value: str) -> datetime:
    """Parse ISO datetime string from Phoenix, handling various formats."""
    value = value.replace("Z", "+00:00")
    return datetime.fromisoformat(value)


def _span_from_phoenix(span: dict, trace_id: str) -> SpanData:
    """Convert a Phoenix span dict to our normalized SpanData."""
    context = span.get("context", {})
    return SpanData(
        span_id=span.get("span_id") or context.get("span_id", ""),
        trace_id=trace_id or context.get("trace_id", ""),
        parent_id=span.get("parent_id"),
        name=span.get("name", ""),
        span_kind=span.get("span_kind", "UNKNOWN"),
        status_code=span.get("status_code", "UNSET"),
        start_time=_parse_dt(span["start_time"]),
        end_time=_parse_dt(span["end_time"]),
        attributes=dict(span.get("attributes", {})),
    )


def _df_rows_to_spans(df: pd.DataFrame) -> list[SpanData]:
    """Convert dataframe rows to SpanData objects."""
    spans = []
    for span_id, row in df.iterrows():
        attrs = {}
        for col in df.columns:
            if col.startswith("attributes."):
                val = row[col]
                if val is not None and str(val) != "nan":
                    key = col[len("attributes.") :]
                    attrs[key] = val

        parent_id = row.get("parent_id")
        if parent_id is not None and str(parent_id) == "nan":
            parent_id = None

        spans.append(
            SpanData(
                span_id=str(span_id),
                trace_id=str(row.get("context.trace_id", "")),
                parent_id=str(parent_id) if parent_id else None,
                name=str(row.get("name", "")),
                span_kind=str(row.get("span_kind", "UNKNOWN")),
                status_code=str(row.get("status_code", "UNSET")),
                start_time=row["start_time"].to_pydatetime(),
                end_time=row["end_time"].to_pydatetime(),
                attributes=attrs,
            )
        )
    return spans


@dataclass
class DiscoveredSession:
    """Lightweight session info discovered from span attributes."""

    session_id: str
    span_count: int
    last_span_time: datetime
    start_time: datetime
    end_time: datetime


class PhoenixSource:
    """Fetch trace data from a local Arize Phoenix instance."""

    def __init__(
        self, base_url: str = "http://localhost:6006", project: str = "claude-code"
    ) -> None:
        self.client = Client(base_url=base_url)
        self.project = project
        self._all_spans_df: pd.DataFrame | None = None  # Cache within a run

    def _fetch_all_spans_df(self) -> pd.DataFrame:
        """Fetch all spans as a dataframe, cached for the lifetime of this source."""
        if self._all_spans_df is not None:
            return self._all_spans_df
        try:
            self._all_spans_df = self.client.spans.get_spans_dataframe(
                project_name=self.project,
                limit=10000,
            )
        except Exception:
            logger.exception("Failed to fetch spans dataframe from Phoenix")
            self._all_spans_df = pd.DataFrame()
        return self._all_spans_df

    def discover_sessions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[DiscoveredSession]:
        """Discover all sessions by scanning span attributes.

        Returns lightweight session metadata (ID, span count, timestamps)
        for deciding what needs (re-)analysis.
        """
        df = self._fetch_all_spans_df()
        if df.empty:
            return []

        sid_col = "attributes.session.id"
        if sid_col not in df.columns:
            return []

        # Drop rows without session.id
        df_with_sid = df[df[sid_col].notna()]
        if df_with_sid.empty:
            return []

        results = []
        for session_id, group in df_with_sid.groupby(sid_col):
            session_start = group["start_time"].min().to_pydatetime()
            session_end = group["end_time"].max().to_pydatetime()
            last_span = group["end_time"].max().to_pydatetime()

            if start_time and session_end < start_time:
                continue
            if end_time and session_start > end_time:
                continue

            results.append(
                DiscoveredSession(
                    session_id=str(session_id),
                    span_count=len(group),
                    last_span_time=last_span,
                    start_time=session_start,
                    end_time=session_end,
                )
            )

        results.sort(key=lambda s: s.start_time, reverse=True)
        return results

    def get_sessions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[SessionData]:
        """Fetch sessions from Phoenix with their traces."""
        discovered = self.discover_sessions(start_time, end_time)
        return [
            SessionData(
                session_id=d.session_id,
                traces=[],
                start_time=d.start_time,
                end_time=d.end_time,
            )
            for d in discovered[:limit]
        ]

    def get_trace(self, trace_id: str) -> TraceData | None:
        """Fetch a single trace with all its spans."""
        try:
            traces = self.client.traces.get_traces(
                project_identifier=self.project,
                trace_ids=[trace_id],
                include_spans=True,
            )
        except Exception:
            logger.exception("Failed to fetch trace %s", trace_id)
            return None

        if not traces:
            return None

        trace = traces[0]
        spans = [_span_from_phoenix(s, trace_id) for s in trace.get("spans", [])]
        spans.sort(key=lambda s: s.start_time)

        return TraceData(
            trace_id=trace_id,
            start_time=_parse_dt(trace["start_time"]),
            end_time=_parse_dt(trace["end_time"]),
            spans=spans,
        )

    def get_spans(
        self,
        trace_id: str,
        span_kind: str | None = None,
    ) -> list[SpanData]:
        """Fetch spans for a trace, optionally filtered by kind."""
        try:
            kwargs: dict = {
                "project_identifier": self.project,
                "trace_ids": [trace_id],
                "limit": 1000,
            }
            if span_kind:
                kwargs["span_kind"] = span_kind

            phoenix_spans = self.client.spans.get_spans(**kwargs)
        except Exception:
            logger.exception("Failed to fetch spans for trace %s", trace_id)
            return []

        result = [_span_from_phoenix(dict(s), trace_id) for s in phoenix_spans]
        result.sort(key=lambda s: s.start_time)
        return result

    def get_spans_by_session(self, session_id: str) -> list[SpanData]:
        """Fetch all spans for a session ID (across all its traces)."""
        df = self._fetch_all_spans_df()
        if df.empty:
            return []

        sid_col = "attributes.session.id"
        if sid_col not in df.columns:
            return []

        filtered = df[df[sid_col] == session_id]
        if filtered.empty:
            return []

        spans = _df_rows_to_spans(filtered)
        spans.sort(key=lambda s: s.start_time)
        return spans
