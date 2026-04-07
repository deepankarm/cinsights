from __future__ import annotations

import logging
from datetime import datetime

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


class PhoenixSource:
    """Fetch trace data from a local Arize Phoenix instance."""

    def __init__(self, base_url: str = "http://localhost:6006", project: str = "claude-code"):
        self.client = Client(base_url=base_url)
        self.project = project

    def get_sessions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
    ) -> list[SessionData]:
        """Fetch sessions from Phoenix with their traces."""
        try:
            phoenix_sessions = self.client.sessions.list(
                project_name=self.project, limit=limit
            )
        except Exception:
            # Fall back to fetching traces directly and grouping by session.id
            logger.info("sessions.list not available, falling back to traces")
            return self._sessions_from_traces(start_time, end_time, limit)

        results = []
        for ps in phoenix_sessions:
            session_start = _parse_dt(ps["start_time"])
            session_end = _parse_dt(ps["end_time"])

            if start_time and session_end < start_time:
                continue
            if end_time and session_start > end_time:
                continue

            traces = []
            for trace_ref in ps.get("traces", []):
                trace_id = trace_ref.get("trace_id", "")
                if not trace_id:
                    continue
                traces.append(
                    TraceData(
                        trace_id=trace_id,
                        start_time=_parse_dt(
                            trace_ref.get("start_time", ps["start_time"])
                        ),
                        end_time=_parse_dt(trace_ref.get("end_time", ps["end_time"])),
                    )
                )

            results.append(
                SessionData(
                    session_id=ps["session_id"],
                    traces=traces,
                    start_time=session_start,
                    end_time=session_end,
                )
            )

        return results[:limit]

    def _sessions_from_traces(
        self,
        start_time: datetime | None,
        end_time: datetime | None,
        limit: int,
    ) -> list[SessionData]:
        """Build session list from traces when sessions API is unavailable."""
        try:
            traces = self.client.traces.get_traces(
                project_identifier=self.project,
                start_time=start_time,
                end_time=end_time,
                limit=limit,
            )
        except Exception:
            logger.exception("Failed to fetch traces from Phoenix")
            return []

        # Group traces by session.id (from root span attributes)
        session_map: dict[str, list[TraceData]] = {}
        for t in traces:
            trace_id = t["trace_id"]
            trace_start = _parse_dt(t["start_time"])
            trace_end = _parse_dt(t["end_time"])

            # Try to get session.id from spans
            session_id = trace_id  # fallback
            for span in t.get("spans", []):
                attrs = span.get("attributes", {})
                if "session.id" in attrs:
                    session_id = attrs["session.id"]
                    break

            td = TraceData(
                trace_id=trace_id,
                start_time=trace_start,
                end_time=trace_end,
            )
            session_map.setdefault(session_id, []).append(td)

        results = []
        for session_id, trace_list in session_map.items():
            trace_list.sort(key=lambda t: t.start_time)
            results.append(
                SessionData(
                    session_id=session_id,
                    traces=trace_list,
                    start_time=trace_list[0].start_time,
                    end_time=trace_list[-1].end_time,
                )
            )

        results.sort(key=lambda s: s.start_time, reverse=True)
        return results[:limit]

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
        spans = [
            _span_from_phoenix(s, trace_id) for s in trace.get("spans", [])
        ]
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
        """Fetch all spans for a session ID (across all its traces).

        Session IDs are stored as span attributes (session.id / attributes.session.id).
        We fetch all spans via the dataframe API and filter by session.id.
        """
        try:
            df = self.client.spans.get_spans_dataframe(
                project_name=self.project,
                limit=5000,
            )
            if df.empty:
                return []

            # Filter by session.id attribute
            sid_col = "attributes.session.id"
            if sid_col not in df.columns:
                return []

            filtered = df[df[sid_col] == session_id]
            if filtered.empty:
                return []

            all_spans = []
            for span_id, row in filtered.iterrows():
                # Build attributes dict from attributes.* columns
                attrs = {}
                for col in filtered.columns:
                    if col.startswith("attributes."):
                        val = row[col]
                        if val is not None and str(val) != "nan":
                            # Strip "attributes." prefix for our normalized model
                            key = col[len("attributes."):]
                            attrs[key] = val

                parent_id = row.get("parent_id")
                if parent_id is not None and str(parent_id) == "nan":
                    parent_id = None

                span = SpanData(
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
                all_spans.append(span)

            all_spans.sort(key=lambda s: s.start_time)
            return all_spans
        except Exception:
            logger.exception("Failed to fetch spans for session %s", session_id)
            return []
