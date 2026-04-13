from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from pathlib import Path

from cinsights.sources.base import DiscoveredSession, SpanData
from cinsights.sources.entireio.git_reader import GitReader
from cinsights.sources.entireio.models import CheckpointSummary, CommittedMetadata, SessionFilePaths
from cinsights.sources.entireio.parser import parse_full_jsonl

logger = logging.getLogger(__name__)


class EntireioSource:
    """Fetch trace data from Entire.co checkpoints stored on a git branch."""

    def __init__(
        self,
        repo_path: Path,
        branch: str = "entire/checkpoints/v1",
    ) -> None:
        self.repo_path = repo_path
        self.reader = GitReader(repo_path, branch)
        self._session_index: dict[str, _SessionRef] | None = None
        self._authors: dict[str, str] | None = None

    def _build_index(self) -> dict[str, _SessionRef]:
        """Build an index of session_id → checkpoint/session info.

        For sessions spanning multiple checkpoints, keeps only the latest
        (most recent created_at) checkpoint.
        """
        if self._session_index is not None:
            return self._session_index

        checkpoint_dirs = self.reader.list_checkpoint_dirs()
        index: dict[str, _SessionRef] = {}

        # Batch-read all checkpoint-level metadata.json files in one git call
        cp_meta_paths = [f"{d}/metadata.json" for d in checkpoint_dirs]
        cp_meta_contents = self.reader.batch_read_files(cp_meta_paths)

        # Parse summaries and collect session metadata paths
        sess_meta_paths: list[str] = []
        sess_meta_refs: list[tuple[str, CheckpointSummary, int, SessionFilePaths]] = []

        for cp_dir, path in zip(checkpoint_dirs, cp_meta_paths, strict=True):
            data = cp_meta_contents.get(path)
            if not data:
                continue
            try:
                summary = CheckpointSummary.model_validate_json(data)
            except Exception:
                continue

            for sess_idx, sess_paths in enumerate(summary.sessions):
                sess_meta_path = sess_paths.metadata
                if sess_meta_path.startswith("/"):
                    sess_meta_path = sess_meta_path[1:]
                sess_meta_paths.append(sess_meta_path)
                sess_meta_refs.append((cp_dir, summary, sess_idx, sess_paths))

        # Batch-read all session-level metadata.json files
        sess_meta_contents = self.reader.batch_read_files(sess_meta_paths)

        for (cp_dir, summary, sess_idx, sess_paths), sess_meta_path in zip(
            sess_meta_refs, sess_meta_paths, strict=True
        ):
            data = sess_meta_contents.get(sess_meta_path)
            if not data:
                continue
            try:
                meta = CommittedMetadata.model_validate_json(data)
            except Exception:
                continue

            if meta.is_task:
                continue

            session_id = meta.session_id
            existing = index.get(session_id)
            if existing and existing.metadata.created_at >= meta.created_at:
                continue

            transcript_path = sess_paths.transcript
            if transcript_path and transcript_path.startswith("/"):
                transcript_path = transcript_path[1:]
            if not transcript_path:
                meta_dir = "/".join(sess_meta_path.split("/")[:-1])
                transcript_path = f"{meta_dir}/full.jsonl"

            index[session_id] = _SessionRef(
                checkpoint_id=summary.checkpoint_id,
                checkpoint_dir=cp_dir,
                session_idx=sess_idx,
                metadata=meta,
                transcript_path=transcript_path,
                summary=summary,
            )

        self._session_index = index
        logger.info("Indexed %d sessions from %d checkpoints", len(index), len(checkpoint_dirs))
        return index

    def _get_authors(self) -> dict[str, str]:
        if self._authors is None:
            self._authors = self.reader.get_commit_authors()
        return self._authors

    def discover_sessions(
        self,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[DiscoveredSession]:
        if not self.reader.branch_exists():
            logger.warning("Branch %s not found in %s", self.reader.branch, self.repo_path)
            return []

        index = self._build_index()
        results = []

        for _session_id, ref in index.items():
            created = ref.metadata.created_at
            if created.tzinfo is None:
                created = created.replace(tzinfo=UTC)

            if start_time and created < start_time:
                continue
            if end_time and created > end_time:
                continue

            # Estimate span count from checkpoints_count and session metrics
            turn_count = 0
            if ref.metadata.session_metrics and ref.metadata.session_metrics.turn_count:
                turn_count = ref.metadata.session_metrics.turn_count
            span_count = max(ref.metadata.checkpoints_count, turn_count, 1)

            results.append(
                DiscoveredSession(
                    session_id=f"entireio:{ref.checkpoint_id}:{ref.session_idx}",
                    span_count=span_count,
                    last_span_time=created,
                    start_time=created,
                    end_time=created,
                )
            )

        results.sort(key=lambda s: s.start_time, reverse=True)
        return results

    def get_spans_by_session(self, session_id: str) -> list[SpanData]:
        """Parse the full.jsonl for a session into SpanData."""
        index = self._build_index()
        authors = self._get_authors()

        # session_id format: "entireio:{checkpoint_id}:{session_idx}"
        parts = session_id.split(":")
        if len(parts) != 3 or parts[0] != "entireio":
            logger.error("Invalid entireio session_id format: %s", session_id)
            return []

        checkpoint_id = parts[1]
        session_idx = int(parts[2])

        # Find by checkpoint_id and session_idx
        ref = None
        for _sid, r in index.items():
            if r.checkpoint_id == checkpoint_id and r.session_idx == session_idx:
                ref = r
                break

        if not ref:
            logger.error("Session not found in index: %s", session_id)
            return []

        try:
            transcript_data = self.reader.read_file(ref.transcript_path)
        except Exception:
            logger.exception("Failed to read transcript: %s", ref.transcript_path)
            return []

        # Get user_id from git author
        user_id = authors.get(ref.checkpoint_dir)

        try:
            agent = (ref.metadata.agent or "").lower()
            trace_id = f"entireio:{checkpoint_id}:{session_idx}"

            if agent == "codex":
                from cinsights.sources.local.parsers.codex import parse_codex

                _, spans = parse_codex(
                    data=transcript_data,
                    trace_id=trace_id,
                    user_id=user_id,
                )
            elif agent in ("copilot", "copilot cli"):
                from cinsights.sources.local.parsers.copilot import parse_copilot

                _, spans = parse_copilot(
                    data=transcript_data,
                    trace_id=trace_id,
                    user_id=user_id,
                )
            else:
                _, spans = parse_full_jsonl(
                    data=transcript_data,
                    checkpoint_id=checkpoint_id,
                    session_idx=session_idx,
                    metadata=ref.metadata,
                    user_id=user_id,
                )
        except Exception:
            logger.exception("Failed to parse transcript: %s", ref.transcript_path)
            return []
        return spans

    def get_session_metadata_json(self, session_id: str) -> str | None:
        """Build metadata_json for storage on CodingSession."""
        index = self._build_index()

        parts = session_id.split(":")
        if len(parts) != 3:
            return None

        checkpoint_id = parts[1]
        session_idx = int(parts[2])

        ref = None
        for _, r in index.items():
            if r.checkpoint_id == checkpoint_id and r.session_idx == session_idx:
                ref = r
                break

        if not ref:
            return None

        meta = ref.metadata
        data: dict = {}

        if meta.token_usage:
            data["cache_creation_tokens"] = meta.token_usage.cache_creation_tokens
            data["cache_read_tokens"] = meta.token_usage.cache_read_tokens

        if meta.files_touched:
            data["files_touched"] = meta.files_touched

        if meta.initial_attribution:
            data["attribution"] = {
                "agent_lines": meta.initial_attribution.agent_lines,
                "human_added": meta.initial_attribution.human_added,
                "agent_percentage": meta.initial_attribution.agent_percentage,
            }

        if meta.branch:
            data["branch"] = meta.branch

        return json.dumps(data) if data else None


class _SessionRef:
    """Internal reference to a session within a checkpoint."""

    __slots__ = (
        "checkpoint_dir",
        "checkpoint_id",
        "metadata",
        "session_idx",
        "summary",
        "transcript_path",
    )

    def __init__(
        self,
        checkpoint_id: str,
        checkpoint_dir: str,
        session_idx: int,
        metadata: CommittedMetadata,
        transcript_path: str,
        summary: CheckpointSummary,
    ):
        self.checkpoint_id = checkpoint_id
        self.checkpoint_dir = checkpoint_dir
        self.session_idx = session_idx
        self.metadata = metadata
        self.transcript_path = transcript_path
        self.summary = summary
