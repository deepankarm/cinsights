"""Local filesystem JSONL source for cinsights."""

from __future__ import annotations

import logging
import os
from datetime import UTC, datetime
from pathlib import Path

from cinsights.sources.base import DiscoveredSession, SpanData
from cinsights.sources.local.parsers import (
    AgentType,
    detect_agent,
    parse_claude_code,
    parse_codex,
    parse_copilot,
)

logger = logging.getLogger(__name__)


class LocalSource:
    """Read JSONL session files directly from the local filesystem."""

    def __init__(self, paths: list[Path]) -> None:
        self.paths = paths
        self._file_index: dict[str, _FileRef] | None = None

    def _build_index(self) -> dict[str, _FileRef]:
        if self._file_index is not None:
            return self._file_index

        index: dict[str, _FileRef] = {}

        for base_path in self.paths:
            if not base_path.is_dir():
                logger.debug("Skipping non-existent path: %s", base_path)
                continue

            for jsonl_file in base_path.rglob("*.jsonl"):
                if not jsonl_file.is_file() or jsonl_file.stat().st_size == 0:
                    continue

                # Read enough to detect agent type (Codex session_meta can be >14KB)
                try:
                    head = jsonl_file.read_bytes()[:32768]
                except OSError:
                    continue

                agent = detect_agent(head)
                if agent is None:
                    continue

                # Build session_id and derive project name
                stem = jsonl_file.stem
                session_id = f"local:{agent}:{stem}"

                # Use file mtime for session time
                mtime = datetime.fromtimestamp(jsonl_file.stat().st_mtime, tz=UTC)

                index[session_id] = _FileRef(
                    path=jsonl_file,
                    agent=agent,
                    mtime=mtime,
                )

        self._file_index = index
        logger.info("Indexed %d local JSONL files from %d paths", len(index), len(self.paths))
        return index

    def discover_sessions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[DiscoveredSession]:
        index = self._build_index()
        results = []

        for session_id, ref in index.items():
            if start_time and ref.mtime < start_time:
                continue
            if end_time and ref.mtime > end_time:
                continue

            # Estimate span count from file size (rough: ~500 bytes per line)
            file_size = ref.path.stat().st_size
            estimated_spans = max(file_size // 500, 1)

            results.append(
                DiscoveredSession(
                    session_id=session_id,
                    span_count=estimated_spans,
                    last_span_time=ref.mtime,
                    start_time=ref.mtime,
                    end_time=ref.mtime,
                )
            )

        results.sort(key=lambda s: s.start_time, reverse=True)
        return results

    def get_spans_by_session(self, session_id: str) -> list[SpanData]:
        index = self._build_index()
        ref = index.get(session_id)
        if not ref:
            logger.error("Session not found in index: %s", session_id)
            return []

        try:
            data = ref.path.read_bytes()
        except OSError:
            logger.exception("Failed to read file: %s", ref.path)
            return []

        user_id = os.environ.get("USER") or Path.home().name

        parsers = {
            AgentType.CLAUDE_CODE: parse_claude_code,
            AgentType.CODEX: parse_codex,
            AgentType.COPILOT: parse_copilot,
        }

        parser = parsers.get(ref.agent)
        if not parser:
            logger.error("No parser for agent type: %s", ref.agent)
            return []

        _, spans = parser(
            data=data,
            trace_id=session_id,
            user_id=user_id,
        )
        return spans

    def get_agent_type(self, session_id: str) -> str | None:
        index = self._build_index()
        ref = index.get(session_id)
        return ref.agent if ref else None


class _FileRef:
    __slots__ = ("agent", "mtime", "path")

    def __init__(
        self,
        path: Path,
        agent: AgentType,
        mtime: datetime,
    ):
        self.path = path
        self.agent = agent
        self.mtime = mtime
